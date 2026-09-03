"""The retained-results read against a real Postgres
(`launch-step-automation`).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/launch-step-automation/spec.md`
— the ADDED requirement *A retained result is kept and stays readable as
the product's record*, in the halves no in-memory fake can observe:

- *Results are answered newest first*
- *Results sharing a produced moment are answered in the tiebreak's
  order*
- *A settled result is still readable*
- *A voided result is readable and is not a rejection*
- *A voided result carries no decider*
- *A graduated launch's results are still readable*
- *A product with nothing retained answers emptily, not with a failure*

The ordering pair is here rather than in the unit tier because
`design.md` — Decision 5 puts the order in the repository's query
(`produced_at DESC, id DESC`): a fake repository asserting it would
assert only the fake. `tasks.md` 8.4 requires exactly this — the
tiebreak asserted **at the read**, against a real database, as a
*direction* (of two rows sharing a produced moment, the higher row
identifier is answered first) that holds **whichever order the two were
stored in**. Two renders compared against each other cannot establish
it: a query with no tiebreak commonly returns equal keys in the same
order twice, so such a test passes against the defect.

`tasks.md` 8.4a is why the tiebreak is not also asserted at the page:
the record `tasks.md` 2.4 exposes carries no row identifier, so the page
cannot see what the tiebreak turns on.

The requirement's remaining scenarios — the scope refusal, a result for
a step the playbook no longer serves, and the record's boundary — are
covered in `tests/unit/launch/application/test_retained_results_read.py`
and `tests/unit/launch/infrastructure/driving/
test_retained_record_boundary.py`. See `test-manifest.md` at the change
root for the full accounting.

## What is fixed, and what is INVENTED

Fixed by the artifacts: one read added to `AutomatedResultRepository`
answering every row for a product ordered `produced_at DESC, id DESC`,
with no state filter, no step filter and no knowledge of access scope
(`tasks.md` 2.1, 2.2); the use case exposing it through
`launch.application` with the scope applied there (`tasks.md` 2.3, 2.5);
that settled and voided rows are kept, never deleted; that `void` leaves
`decided_by` untouched (`tasks.md` 2.6).

INVENTED, each recorded in the manifest with its correction point:

- The repository module and class name (`_repository_class`), and the
  write/settle/void call shapes (`_store`, `_settle`, `_void`) — the
  same probes `test_automated_result_store_live.py` already records.
- The use case's name and call shape (`_USE_CASE_NAMES`, `_read`). The
  repository's own read is driven through it rather than directly: the
  requirement is stated about what *the system* answers, and the use
  case is that surface.
- The answered record's attribute spellings (`_ATTRIBUTE_ALIASES`).
- That the stored row exposes its identifier as `id`. `design.md` —
  Decision 5 names "the row's `id`"; `_identifier_of` fails loudly if it
  is not readable, because without it the tiebreak's *direction* cannot
  be asserted at all and only insertion order would be left.

What must survive any correction: that results come back newest first,
that the higher row identifier wins a shared produced moment in both
storage orders, that settled and voided rows are still answered, that a
voided one names no decider, and that a graduated launch changes none of
it.

## Test-database lifecycle

The convention of this directory: a fresh product and launch per test,
no truncate fixture, `alembic upgrade head` assumed applied, and a skip
when no database is configured.

## Expected first-run state

Absent target: neither the repository read nor the use case exists.
Where no database is configured — as here — the tier's gate skips
before the body runs, so these assertions have never been executed at
all. Both facts are recorded in `test-manifest.md`, and `tasks.md` 8.3
is the check that this tier actually ran before the change is called
verified.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27); the 96
skips are this whole tier, which finds no database here and says so.
"""

from __future__ import annotations

import importlib
import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import commerce_ops.launch.application as launch_application
from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
FIRST_STEP: Final = "listing.sub-category"
SECOND_STEP: Final = "listing.compliance-fields"
HANDLER_NAME: Final = "listing.subcategory_advisor"
ALICE: Final = "Alice Admin"
LAUNCH_DATE: Final = date(2027, 3, 2)

OLDEST: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
MIDDLE: Final = datetime(2027, 1, 7, 9, 30, tzinfo=UTC)
NEWEST: Final = datetime(2027, 1, 8, 9, 30, tzinfo=UTC)
SHARED_MOMENT: Final = datetime(2027, 1, 9, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 10, 10, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 5, 9, 30, tzinfo=UTC)

OLDEST_TEXT: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards."
MIDDLE_TEXT: Final = "Sports & Outdoors > Camping & Hiking > Cookware."
NEWEST_TEXT: Final = "Toys & Games > Puzzles > Jigsaw Puzzles."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# The repository, reached through one correction point
# ---------------------------------------------------------------------------

_REPOSITORY_MODULES: Final = (
    "commerce_ops.launch.infrastructure.driven.automated_results",
    "commerce_ops.launch.infrastructure.driven.automated_result_repository",
)

_REPOSITORY_NAMES: Final = (
    "AutomatedResultRepository",
    "AutomatedStepResultRepository",
)

_USE_CASE_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)


def _repository_class() -> Any:
    for module_name in _REPOSITORY_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for name in _REPOSITORY_NAMES:
            found = getattr(module, name, None)
            if found is not None:
                return found
    pytest.fail(
        "no automated-result repository found under any of "
        f"{_REPOSITORY_MODULES} as any of {_REPOSITORY_NAMES} — correct "
        "this file's probe to the implemented module and class"
    )


async def _store(
    repository: Any,
    *,
    product_id: ProductId,
    step_id: str,
    result_text: str,
    produced_at: datetime,
) -> Any:
    """INVENTED call shape — the single correction point for the write.

    Taken verbatim from `test_automated_result_store_live.py`, with the
    step and the produced moment supplied per row: this file needs two
    rows sharing a moment, and the partial unique index forbids two
    *pending* rows for one product and step.
    """
    for name in ("store", "insert", "hold", "add"):
        writer = getattr(repository, name, None)
        if callable(writer):
            return await writer(
                product_id=product_id,
                step_id=step_id,
                handler=HANDLER_NAME,
                proposed_outcome="Satisfied",
                result_text=result_text,
                produced_at=produced_at,
            )
    pytest.fail("the automated-result repository exposes no write")


async def _settle(repository: Any, row: Any, *, state: str) -> None:
    for name in ("settle", "decide", "resolve"):
        settler = getattr(repository, name, None)
        if callable(settler):
            await settler(row, state=state, decided_by=ALICE, decided_at=DECIDED_AT)
            return
    pytest.fail("the automated-result repository exposes no settle")


async def _void(repository: Any, row: Any) -> None:
    voider = getattr(repository, "void", None)
    if callable(voider):
        await voider(row)
        return
    pytest.fail("the automated-result repository exposes no void")


def _identifier_of(row: Any) -> Any:
    """The stored row's identifier — the tiebreak `design.md` — Decision
    5 names.

    Read while the row is still attached, and failing loudly rather than
    defaulting: without it, the only thing left to assert about a shared
    produced moment is insertion order, which is precisely what
    `tasks.md` 8.4 forbids the assertion from reading.
    """
    found = getattr(row, "id", None)
    if found is None:
        pytest.fail(
            "the stored automated-result row exposes no populated `id`, so "
            "the ordering tiebreak's direction cannot be asserted — "
            "correct `_identifier_of` to the implemented identifier"
        )
    return found


# ---------------------------------------------------------------------------
# The read, reached through one correction point
# ---------------------------------------------------------------------------


def _use_case() -> Any:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no retained-results read is exported from `launch.application` "
        f"under any of {_USE_CASE_NAMES} — correct `_USE_CASE_NAMES` to "
        "the implemented name"
    )


async def _read(repository: Any, product_id: ProductId) -> tuple[Any, ...]:
    """The whole read, driven through the public surface with an
    unrestricted scope: the scope's own behaviour is unit-tier, and what
    this tier is for is the order and the retention the query decides."""
    use_case = _use_case()
    names = list(inspect.signature(use_case).parameters)
    arguments: dict[str, Any] = {}
    for name in names[1:]:
        if "scope" in name:
            arguments[name] = AccessScope.unrestricted()
        elif "product" in name or name in ("identifier", "id"):
            arguments[name] = product_id
    return tuple(await use_case(repository, **arguments))


_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "step_id": ("step_id", "step", "step_identifier", "identifier"),
    "result_text": ("result_text", "text", "produced_text", "result"),
    "produced_at": ("produced_at", "produced", "produced_on", "when"),
    "state": ("state", "fate", "status"),
    "decided_by": ("decided_by", "decider", "decided_by_name"),
    "decided_at": ("decided_at", "decided_on", "decision_moment"),
}


def _read_field(subject: object, field: str) -> Any:
    for name in _ATTRIBUTE_ALIASES[field]:
        if hasattr(subject, name):
            return getattr(subject, name)
    pytest.fail(
        f"{type(subject).__name__} exposes none of "
        f"{_ATTRIBUTE_ALIASES[field]} for '{field}' (`tasks.md` 2.4)"
    )


def _state_of(record: object) -> str:
    value = _read_field(record, "state")
    for attribute in ("value", "name"):
        found = getattr(value, attribute, None)
        if isinstance(found, str):
            return found.lower()
    return str(value).lower()


def _texts(records: tuple[Any, ...]) -> list[str]:
    return [str(_read_field(record, "result_text")) for record in records]


def _entry_for(records: tuple[Any, ...], text: str) -> Any:
    found = [record for record in records if _read_field(record, "result_text") == text]
    assert len(found) == 1, (
        f"expected exactly one answered result carrying {text!r}, got {len(found)}"
    )
    return found[0]


# ---------------------------------------------------------------------------
# Domain and database fixtures
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"RR-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": FIRST_STEP,
        "name": "Choose the sub-category node",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "confirmer": "prs_confirmer",
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": HANDLER_NAME,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    steps = (_step(), _step(identifier=SECOND_STEP, name="List the demanded fields"))
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(*steps, *fillers))


def _graduate(launch: Launch, playbook: LaunchPlaybook) -> Launch:
    """Walk a launch to `graduated` by satisfying only its blocking
    work — the walk `test_automation_pass.py` records."""
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="clickup",
                        who="Helen",
                        when=APPROVED_AT,
                        evidence="blocking work signed off",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=APPROVED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    return launch


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
def new_results(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[Any]]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    repository = _repository_class()

    @asynccontextmanager
    async def _open() -> AsyncIterator[Any]:
        async with maker() as session:
            yield repository(session)

    return _open


@pytest.fixture()
def launched_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product with a launch record — the state a
    retained result can reference, since `automated_step_results`
    carries a foreign key to `launch_positions.product_id`."""

    async def _launch() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        launch, _ = Launch.start(
            product_id=product.id, playbook=_playbook(), launch_date=LAUNCH_DATE
        )
        async with maker() as session:
            await LaunchRepository(session).save(launch)
        return product.id

    return _launch


@pytest.fixture()
def graduate_launch(engine: AsyncEngine) -> Callable[[ProductId], Awaitable[None]]:
    """Walk that product's launch to `graduated` and persist it."""

    async def _graduated(product_id: ProductId) -> None:
        playbook = _playbook()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            repository = LaunchRepository(session)
            launch = await repository.get_by_product_id(product_id)
            assert launch is not None, "the fixture's launch was not persisted"
            await repository.save(_graduate(launch, playbook))

    return _graduated


# ---------------------------------------------------------------------------
# Requirement: A retained result is kept and stays readable as the
# product's record
# ---------------------------------------------------------------------------


async def test_results_are_answered_newest_first(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Results are answered newest first.

    WHEN every result retained for a product is read and results were
    produced at different moments
    THEN they are answered ordered by the moment produced, most recent
    first.

    Stored oldest-last, so a query with no ordering at all — which in
    Postgres commonly returns heap order, i.e. insertion order — cannot
    produce this answer by accident.
    """
    product_id = await launched_product_id()

    async with new_results() as writer:
        middle = await _store(
            writer,
            product_id=product_id,
            step_id=SECOND_STEP,
            result_text=MIDDLE_TEXT,
            produced_at=MIDDLE,
        )
        await _settle(writer, middle, state="accepted")
        newest = await _store(
            writer,
            product_id=product_id,
            step_id=SECOND_STEP,
            result_text=NEWEST_TEXT,
            produced_at=NEWEST,
        )
        await _settle(writer, newest, state="rejected")
        await _store(
            writer,
            product_id=product_id,
            step_id=FIRST_STEP,
            result_text=OLDEST_TEXT,
            produced_at=OLDEST,
        )

    async with new_results() as reader:
        answered = await _read(reader, product_id)

    # SPECIFIED: ordered by the moment produced, most recent first.
    assert _texts(answered) == [NEWEST_TEXT, MIDDLE_TEXT, OLDEST_TEXT]


@pytest.mark.parametrize(
    "reversed_storage", [False, True], ids=["first-then-second", "second-then-first"]
)
async def test_results_sharing_a_produced_moment_use_the_tiebreak(
    reversed_storage: bool,
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Results sharing a produced moment are answered in the
    tiebreak's order.

    WHEN every result retained for a product is read and two of them
    share a produced moment and differ in row identifier
    THEN the one whose row identifier sorts higher is answered first
    AND it is answered first whichever order the two were stored in.

    `tasks.md` 8.4: the assertion is the *direction*, read off the row
    identifiers the store actually assigned, and it is run under both
    storage orders — so what is being asserted cannot be the order the
    two rows happened to be written in. Two rows on different steps,
    because the partial unique index forbids two pending rows for one
    product and step.
    """
    product_id = await launched_product_id()
    first, second = (
        (SECOND_STEP, FIRST_STEP) if reversed_storage else (FIRST_STEP, SECOND_STEP)
    )
    text_of = {first: OLDEST_TEXT, second: MIDDLE_TEXT}

    identifiers: dict[str, Any] = {}
    async with new_results() as writer:
        for step_id in (first, second):
            row = await _store(
                writer,
                product_id=product_id,
                step_id=step_id,
                result_text=text_of[step_id],
                produced_at=SHARED_MOMENT,
            )
            identifiers[step_id] = _identifier_of(row)

    async with new_results() as reader:
        answered = await _read(reader, product_id)

    assert len(answered) == 2, "both retained results must be answered"
    higher = max(identifiers, key=lambda step_id: identifiers[step_id])
    lower = min(identifiers, key=lambda step_id: identifiers[step_id])
    assert identifiers[higher] != identifiers[lower], (
        "the two stored rows share a row identifier, so this test cannot "
        "observe a tiebreak at all"
    )

    # SPECIFIED: the higher row identifier is answered first — and this
    # is the whole assertion, run under both storage orders above.
    assert _texts(answered) == [text_of[higher], text_of[lower]]


async def test_settled_and_voided_results_are_all_still_answered(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenarios: *A settled result is still readable*, *A voided result
    is readable and is not a rejection*, and *A voided result carries no
    decider* — all three over the same stored set, because each is a
    property of the row after a different decision and one read answers
    them together.

    WHEN every result retained for a product is read after one was
    accepted, another rejected and a third voided
    THEN all are answered, each carrying the state it reached; the
    voided one is distinct from the rejected one and names no decider.
    """
    product_id = await launched_product_id()

    async with new_results() as writer:
        accepted = await _store(
            writer,
            product_id=product_id,
            step_id=FIRST_STEP,
            result_text=OLDEST_TEXT,
            produced_at=OLDEST,
        )
        await _settle(writer, accepted, state="accepted")
        rejected = await _store(
            writer,
            product_id=product_id,
            step_id=FIRST_STEP,
            result_text=MIDDLE_TEXT,
            produced_at=MIDDLE,
        )
        await _settle(writer, rejected, state="rejected")
        voided = await _store(
            writer,
            product_id=product_id,
            step_id=SECOND_STEP,
            result_text=NEWEST_TEXT,
            produced_at=NEWEST,
        )
        await _void(writer, voided)

    async with new_results() as reader:
        answered = await _read(reader, product_id)

    # SPECIFIED: nothing in the decision flow deleted a row.
    assert len(answered) == 3

    accepted_entry = _entry_for(answered, OLDEST_TEXT)
    rejected_entry = _entry_for(answered, MIDDLE_TEXT)
    voided_entry = _entry_for(answered, NEWEST_TEXT)

    # SPECIFIED: each carries the state it reached, the member who
    # decided it and the moment of the decision.
    assert _state_of(accepted_entry) == "accepted"
    assert _read_field(accepted_entry, "decided_by") == ALICE
    assert _read_field(accepted_entry, "decided_at") is not None
    assert _state_of(rejected_entry) == "rejected"
    assert _read_field(rejected_entry, "decided_by") == ALICE

    # SPECIFIED: the voided one carries the voided state, distinct from
    # a rejected one.
    assert _state_of(voided_entry) == "voided"
    assert _state_of(voided_entry) != _state_of(rejected_entry)
    # SPECIFIED: and names no decider, because voiding refuses a
    # decision rather than recording one (`tasks.md` 2.6).
    assert _read_field(voided_entry, "decided_by") is None


async def test_a_graduated_launchs_results_are_still_answered(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
    graduate_launch: Callable[[ProductId], Awaitable[None]],
) -> None:
    """Scenario: A graduated launch's results are still readable.

    WHEN every result retained for a product is read after that
    product's launch has reached `graduated`
    THEN every result retained for it is answered.
    """
    product_id = await launched_product_id()

    async with new_results() as writer:
        await _store(
            writer,
            product_id=product_id,
            step_id=FIRST_STEP,
            result_text=OLDEST_TEXT,
            produced_at=OLDEST,
        )
        await _store(
            writer,
            product_id=product_id,
            step_id=SECOND_STEP,
            result_text=MIDDLE_TEXT,
            produced_at=MIDDLE,
        )

    await graduate_launch(product_id)

    async with new_results() as reader:
        answered = await _read(reader, product_id)

    # SPECIFIED: every result retained for it is answered.
    assert sorted(_texts(answered)) == sorted([OLDEST_TEXT, MIDDLE_TEXT])


async def test_a_product_with_nothing_retained_answers_emptily(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A product with nothing retained answers emptily, not
    with a failure.

    WHEN every result retained for a product that has never had a result
    stored is read
    THEN nothing is answered and the read succeeds.

    A second product carries results, so "nothing" is this product's
    answer rather than an empty table.
    """
    bare = await launched_product_id()
    populated = await launched_product_id()

    async with new_results() as writer:
        await _store(
            writer,
            product_id=populated,
            step_id=FIRST_STEP,
            result_text=OLDEST_TEXT,
            produced_at=OLDEST,
        )

    async with new_results() as reader:
        answered = await _read(reader, bare)
        elsewhere = await _read(reader, populated)

    # SPECIFIED: nothing is answered, and the read succeeded rather than
    # raising — reaching this line at all is the second half.
    assert answered == ()
    # DERIVED guard: the read is not simply answering nothing to
    # everything.
    assert _texts(elsewhere) == [OLDEST_TEXT]


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED here, recorded rather than omitted
#
# - The cascade `design.md` — Risks names: `automated_step_results`
#   cascades on deletion of a `LaunchPosition`, so the retention this
#   change specifies is guaranteed by nothing deleting launch positions
#   rather than by the schema. Asserting the cascade would test the
#   hazard rather than the requirement, and asserting its absence would
#   pin a schema decision no requirement states.
# - The scope refusal. It is applied in the use case (`design.md` —
#   Decision 4) and needs no database to observe; it is asserted in
#   `tests/unit/launch/application/test_retained_results_read.py`.
# ---------------------------------------------------------------------------
