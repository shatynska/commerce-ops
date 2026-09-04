"""Both `finding` columns against a real Postgres (`launch-instance`,
`launch-step-automation`).

Derived strictly from the delta specs of the change
`separate-the-result-from-the-comment`, and asked for by `tasks.md` 1.21:

    1.21 `tests/integration/launch/` — both `finding` columns round-trip
    through Postgres, and rows written before the migration read back as
    carrying nothing.

Covers, at the one level that can observe it, the storage half of:

- *A recording made before this capability reads as carrying nothing*
  (`launch-instance`)
- *An absent finding is distinguishable from an empty value*
  (`launch-instance`)
- *A finding with no comment is carried as such* (`launch-instance`)
- *A confirmable step's finding survives until the result is accepted*
  (`launch-step-automation`) — the store's own half of it

Every one of these is also asserted at the unit tier, over fakes
(`tests/unit/launch/infrastructure/driven/test_launch_progress_finding_rows.py`,
`tests/unit/launch/application/test_accepted_result_carried_finding.py`).
What only a database can establish is that `jsonb` really holds the
payload, that `NULL` really is the state a pre-migration row is in, and
that an empty value survives a real round trip rather than a Python
dict's. That is the level rule, not duplication for its own sake.

See `test-manifest.md` at the change root for the full accounting of all
28 scenarios.

## Test-database lifecycle

The convention of this directory: a fresh product and launch per test, no
truncate fixture, `alembic upgrade head` (including this change's
revision, `tasks.md` 2.1) assumed applied, and a skip when no database is
configured. Note this worktree's `AGENTS.md`: a skipped tier is not a
green one.

## What is fixed, and what is INVENTED

Fixed by the artifacts: one Alembic revision adds `finding jsonb NULL` to
**both** `launch_step_progress` and `automated_step_results`, with no
backfill, because absent is the correct reading for every existing row
(`tasks.md` 2.1; `design.md`, *Migration Plan*). The payload is
`{"field": ..., "value": ..., "comment": ...}` (`tasks.md` 2.5).

INVENTED, each recorded in `test-manifest.md`:

- The column name (`_COLUMN`), the keyword `record_step_outcome` accepts
  (`_FINDING_KWARGS`) and the keyword `store` accepts for it — the same
  correction points as the unit-tier files.
- That a row "written before the migration" is modelled by an `INSERT`
  naming every column *except* `finding`, which is what an older code
  path emitted and what leaves the column at its `NULL` default.

## Expected first-run state

**Absent target.** Neither column exists, so every test here is expected
to fail — most through a loud probe, and the column-type assertions
through their own message naming the absent column. Per
`ai-toolkit:testing` that establishes absence and nothing about whether
these assertions are any good.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03, against the seeded `commerce_ops_screen_test` database:
`uv run pytest tests/integration` — 137 passed, 0 failed, **0 skipped**,
so the tier genuinely ran; `uv run pytest tests/unit tests/agents` —
2167 passed, 0 failed.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain import launch_run
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.launch.infrastructure.driven.automated_results import (
    AutomatedResultRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import (
    ALICE,
    HANDLER_NAME,
    LAUNCH_DATE,
    MARKETPLACE,
    STEP_ID,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

RECORDED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

EVIDENCE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards."
FIELD: Final = "sub_category"
VALUE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = "Rejected alternative: Home & Kitchen > Home Decor."

#: The column both stores gain (`tasks.md` 2.1). The single correction
#: point for its name.
_COLUMN: Final = "finding"
_FINDING_KWARGS: Final = (_COLUMN, "carried_finding", "kept_finding")
_FINDING_TYPES: Final = (
    "CarriedFinding",
    "RecordedFinding",
    "KeptFinding",
    "Finding",
)

_ABSENT: Final = object()
_UNSET: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"CF-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": "Choose the sub-category node",
            "kind": StepKind.AUTOMATED,
            "confirmer": ALICE,
            "handler": HANDLER_NAME,
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        confirmer=ALICE,
        handler=f"hold.{gate.replace('-', '_')}",
        kind=StepKind.AUTOMATED,
        name="Choose the sub-category node",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(_step(), *fillers))


def _provenance() -> Provenance:
    return Provenance(
        source="automated", who=HANDLER_NAME, when=RECORDED_AT, evidence=EVIDENCE
    )


# ---------------------------------------------------------------------------
# Correction points
# ---------------------------------------------------------------------------


def _carry(field_name: str, value: Any, comment: Any = _ABSENT) -> Any:
    parts: dict[str, Any] = {"field": field_name, "value": value}
    if comment is not _ABSENT:
        parts["comment"] = comment
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            return found(**parts)
    return parts


def _finding_kwarg(callable_: Any) -> str:
    accepted = set(inspect.signature(callable_).parameters)
    for name in _FINDING_KWARGS:
        if name in accepted:
            return name
    pytest.fail(
        f"`{getattr(callable_, '__qualname__', callable_)}` accepts no "
        f"keyword for a finding among {list(_FINDING_KWARGS)}; its "
        f"parameters are {sorted(accepted)} — correct `_FINDING_KWARGS`"
    )


def _record(launch: Launch, playbook: LaunchPlaybook, *, finding: Any = _UNSET) -> None:
    kwargs: dict[str, Any] = {
        "step_id": STEP_ID,
        "outcome": Satisfied,
        "provenance": _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg(Launch.record_step_outcome)] = finding
    launch.record_step_outcome(playbook, **kwargs)


def _part(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key, _ABSENT)
    return getattr(raw, key, _ABSENT)


def _read(carrier: Any) -> tuple[Any, Any, Any] | None:
    """What a hydrated recording or pending row carries, or `None`."""
    for name in _FINDING_KWARGS:
        if hasattr(carrier, name):
            raw = getattr(carrier, name)
            break
    else:
        pytest.fail(
            f"{type(carrier).__name__} exposes no finding under any of "
            f"{list(_FINDING_KWARGS)} — correct `_FINDING_KWARGS`"
        )
    if raw is None:
        return None
    comment = _part(raw, "comment")
    return (
        _part(raw, "field"),
        _part(raw, "value"),
        _ABSENT if comment is None else comment,
    )


# ---------------------------------------------------------------------------
# Database fixtures — the convention of this directory
# ---------------------------------------------------------------------------


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_async_engine(database_url)
    try:
        yield created
    finally:
        await created.dispose()


@pytest.fixture()
def sessions(engine: AsyncEngine) -> async_sessionmaker[Any]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def launched_product_id(
    sessions: async_sessionmaker[Any],
) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product that also has a launch record."""

    async def _launch() -> ProductId:
        async with sessions() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        playbook = _playbook()
        launch, _ = Launch.start(
            product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
        )
        async with sessions() as session:
            await LaunchRepository(session).save(launch)
        return product.id

    return _launch


async def _column_type(engine: AsyncEngine, table: str) -> str | None:
    async with engine.connect() as connection:
        found = await connection.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": _COLUMN},
        )
        row = found.first()
    return None if row is None else str(row[0])


async def _is_nullable(engine: AsyncEngine, table: str) -> str | None:
    async with engine.connect() as connection:
        found = await connection.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": _COLUMN},
        )
        row = found.first()
    return None if row is None else str(row[0])


async def _raw_finding(engine: AsyncEngine, table: str, product_id: ProductId) -> Any:
    if await _column_type(engine, table) is None:
        pytest.fail(
            f"`{table}` has no `{_COLUMN}` column, so what it stores cannot "
            "be read; `tasks.md` 2.1 adds one — correct `_COLUMN` if the "
            "implemented name differs"
        )
    async with engine.connect() as connection:
        found = await connection.execute(
            text(
                f"SELECT {_COLUMN} FROM {table} WHERE product_id = :pid "
                "AND step_id = :step"
            ),
            {"pid": uuid.UUID(product_id.value), "step": STEP_ID},
        )
        row = found.first()
    assert row is not None, f"no row in {table} for the launch under test"
    return row[0]


async def _reload(sessions: async_sessionmaker[Any], product_id: ProductId) -> Any:
    async with sessions() as session:
        launch = await LaunchRepository(session).get_by_product_id(product_id)
    assert launch is not None, "the launch was not read back"
    progress = launch.progress_for(STEP_ID)
    assert progress is not None, "the recording was not read back"
    return progress


# ---------------------------------------------------------------------------
# The migration itself (tasks.md 2.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", ["launch_step_progress", "automated_step_results"])
async def test_both_tables_carry_a_nullable_jsonb_finding_column(
    engine: AsyncEngine, table: str
) -> None:
    """One revision adds `finding jsonb NULL` to both stores.

    `jsonb` rather than `json` or `text` is what makes the shape absorbable
    without a schema change when a later step puts an array in `value`
    (`design.md`, *One `jsonb` column per store*); nullable is what makes
    "carries nothing" representable at all, and is why no backfill is owed.
    """
    kind = await _column_type(engine, table)
    assert kind is not None, (
        f"`{table}` has no `{_COLUMN}` column; `tasks.md` 2.1 adds one to "
        "both stores in a single revision"
    )
    assert kind == "jsonb", f"`{table}.{_COLUMN}` is `{kind}`, not `jsonb`"
    assert await _is_nullable(engine, table) == "YES"


# ---------------------------------------------------------------------------
# `launch_step_progress` (tasks.md 1.21, `launch-instance`)
# ---------------------------------------------------------------------------


async def test_a_carried_finding_round_trips_through_postgres(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Written through the repository, held as `jsonb`, and read back
    whole."""
    product_id = await launched_product_id()
    playbook = _playbook()
    async with sessions() as session:
        repository = LaunchRepository(session)
        launch = await repository.get_by_product_id(product_id)
        assert launch is not None
        _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))
        await repository.save(launch)

    stored = await _raw_finding(engine, "launch_step_progress", product_id)
    assert stored is not None, "the column was written as NULL"
    assert stored["field"] == FIELD
    assert stored["value"] == VALUE
    assert stored["comment"] == COMMENT

    carried = _read(await _reload(sessions, product_id))
    assert carried == (FIELD, VALUE, COMMENT)


async def test_an_empty_value_round_trips_and_is_not_null(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """The assertion the whole change turns on, at the storage boundary
    that decides it: an empty list is a *value*, and the column that holds
    it is not `NULL`."""
    product_id = await launched_product_id()
    playbook = _playbook()
    async with sessions() as session:
        repository = LaunchRepository(session)
        launch = await repository.get_by_product_id(product_id)
        assert launch is not None
        _record(launch, playbook, finding=_carry(FIELD, [], COMMENT))
        await repository.save(launch)

    stored = await _raw_finding(engine, "launch_step_progress", product_id)
    assert stored is not None, (
        "an empty value was persisted as `NULL`, collapsing 'nothing was "
        "established' into 'what was established was empty'"
    )
    assert stored["value"] == []

    field_name, value, _comment = _read(await _reload(sessions, product_id)) or (
        None,
        None,
        None,
    )
    assert field_name == FIELD
    assert value == []


async def test_a_recording_carrying_nothing_persists_null(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """The other side of the same distinction: `NULL` is the whole of
    "carries nothing"."""
    product_id = await launched_product_id()
    playbook = _playbook()
    async with sessions() as session:
        repository = LaunchRepository(session)
        launch = await repository.get_by_product_id(product_id)
        assert launch is not None
        _record(launch, playbook)
        await repository.save(launch)

    assert await _raw_finding(engine, "launch_step_progress", product_id) is None
    assert _read(await _reload(sessions, product_id)) is None


async def test_an_absent_comment_survives_postgres_as_absent(
    sessions: async_sessionmaker[Any],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """An absent comment must not become `""` on the way through `jsonb`."""
    product_id = await launched_product_id()
    playbook = _playbook()
    async with sessions() as session:
        repository = LaunchRepository(session)
        launch = await repository.get_by_product_id(product_id)
        assert launch is not None
        _record(launch, playbook, finding=_carry(FIELD, VALUE))
        await repository.save(launch)

    carried = _read(await _reload(sessions, product_id))
    assert carried is not None
    assert carried[2] is _ABSENT


async def test_a_row_written_before_the_migration_reads_as_carrying_nothing(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """`tasks.md` 1.21's second clause, and `launch-instance`'s scenario
    *A recording made before this capability reads as carrying nothing*.

    The pre-migration row is modelled by an `INSERT` naming every column
    the older code path named and not this one — which is exactly what
    every existing row in the deployment is, since `design.md` states no
    backfill.
    """
    product_id = await launched_product_id()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO launch_step_progress "
                "(product_id, step_id, outcome_kind, outcome_reason, source, "
                " who, recorded_at, evidence) "
                "VALUES (:pid, :step, 'satisfied', NULL, 'automated', :who, "
                " :when, :evidence)"
            ),
            {
                "pid": uuid.UUID(product_id.value),
                "step": STEP_ID,
                "who": HANDLER_NAME,
                "when": RECORDED_AT,
                "evidence": EVIDENCE,
            },
        )

    assert await _raw_finding(engine, "launch_step_progress", product_id) is None

    progress = await _reload(sessions, product_id)
    assert _read(progress) is None, (
        "a row written before this capability read back as carrying an "
        "empty finding rather than none"
    )
    # Every other fact about the recording is still returned.
    assert progress.outcome is Satisfied
    assert progress.provenance.evidence == EVIDENCE
    assert progress.provenance.who == HANDLER_NAME


async def test_an_unreadable_stored_finding_does_not_fail_a_live_read(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """*An unreadable stored finding does not fail the read*, against a
    real column.

    `jsonb` accepts any JSON, so a payload the reader cannot make a
    finding of is representable in the deployment and must not deny a
    reader every other fact about the launch.
    """
    product_id = await launched_product_id()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO launch_step_progress "
                "(product_id, step_id, outcome_kind, outcome_reason, source, "
                f" who, recorded_at, evidence, {_COLUMN}) "
                "VALUES (:pid, :step, 'satisfied', NULL, 'automated', :who, "
                " :when, :evidence, CAST(:payload AS jsonb))"
            ),
            {
                "pid": uuid.UUID(product_id.value),
                "step": STEP_ID,
                "who": HANDLER_NAME,
                "when": RECORDED_AT,
                "evidence": EVIDENCE,
                "payload": '"just a string"',
            },
        )

    progress = await _reload(sessions, product_id)

    assert _read(progress) is None
    assert progress.outcome is Satisfied
    assert progress.provenance.evidence == EVIDENCE


# ---------------------------------------------------------------------------
# `automated_step_results` (tasks.md 1.21, `launch-step-automation`)
# ---------------------------------------------------------------------------


async def _store(
    repository: AutomatedResultRepository,
    *,
    product_id: ProductId,
    finding: Any = _UNSET,
) -> Any:
    kwargs: dict[str, Any] = {
        "product_id": product_id,
        "step_id": STEP_ID,
        "handler": HANDLER_NAME,
        "proposed_outcome": "Satisfied",
        "result_text": EVIDENCE,
        "produced_at": RECORDED_AT,
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg(repository.store)] = finding
    return await repository.store(**kwargs)


async def test_a_pending_results_finding_round_trips_through_postgres(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """The second column, and the one that carries a finding across the
    wait for a confirmer (`design.md`, *The finding travels with the
    pending result*).
    """
    product_id = await launched_product_id()
    async with sessions() as session:
        await _store(
            AutomatedResultRepository(session),
            product_id=product_id,
            finding={"field": FIELD, "value": VALUE, "comment": COMMENT},
        )

    stored = await _raw_finding(engine, "automated_step_results", product_id)
    assert stored is not None, "the pending result's finding column is NULL"
    assert stored["field"] == FIELD
    assert stored["value"] == VALUE
    assert stored["comment"] == COMMENT

    async with sessions() as session:
        pending = await AutomatedResultRepository(session).pending_for(
            product_id, STEP_ID
        )
    assert pending is not None
    assert _read(pending) == (FIELD, VALUE, COMMENT)


async def test_a_pending_results_empty_value_is_not_null(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """The `lp.strategy.006` shape at the store that holds it while a
    member decides."""
    product_id = await launched_product_id()
    async with sessions() as session:
        await _store(
            AutomatedResultRepository(session),
            product_id=product_id,
            finding={"field": FIELD, "value": [], "comment": COMMENT},
        )

    stored = await _raw_finding(engine, "automated_step_results", product_id)
    assert stored is not None
    assert stored["value"] == []

    async with sessions() as session:
        pending = await AutomatedResultRepository(session).pending_for(
            product_id, STEP_ID
        )
    assert pending is not None
    carried = _read(pending)
    assert carried is not None
    assert carried[1] == []


async def test_a_pending_row_written_before_the_migration_carries_nothing(
    sessions: async_sessionmaker[Any],
    engine: AsyncEngine,
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """The 25 rows `lp.strategy.006` has already written are in exactly
    this state, and `design.md` states no backfill."""
    product_id = await launched_product_id()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO automated_step_results "
                "(id, product_id, step_id, handler, proposed_outcome, "
                " result_text, produced_at, state) "
                "VALUES (:id, :pid, :step, :handler, 'Satisfied', :text, "
                " :when, 'pending')"
            ),
            {
                "id": uuid.uuid4(),
                "pid": uuid.UUID(product_id.value),
                "step": STEP_ID,
                "handler": HANDLER_NAME,
                "text": EVIDENCE,
                "when": RECORDED_AT,
            },
        )

    assert await _raw_finding(engine, "automated_step_results", product_id) is None

    async with sessions() as session:
        pending = await AutomatedResultRepository(session).pending_for(
            product_id, STEP_ID
        )
    assert pending is not None
    assert _read(pending) is None
    assert pending.result_text == EVIDENCE
