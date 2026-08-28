"""What a real transaction and a real lock hold: atomicity and exclusion.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers exactly the scenarios that no in-memory double can establish:

- *A cascade failing part-way leaves the launch where it started* (from
  *One launch's failure does not stop the other launches being
  advanced*) — the half that needs a real transaction. Its use-case half,
  that the failure propagates rather than being committed, is at the unit
  tier in `tests/unit/launch/application/test_progress_launch.py`.
- *A rejection and its cool-off refresh land together or not at all*
  (from *A gate is asked about at most once a day*) — over a real
  transaction. Its unit half, against a substituted transaction that
  models one, is in
  `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`.
- *A decision and the pass do not cross the same gate twice* (from *A
  decision records the approval and reports what it did*) — the mutual
  exclusion a Postgres **advisory lock** buys, which exists only against a
  real database and across two genuinely concurrent callers.

See `test-manifest.md` at the change root for the full accounting.

## Why these three are here and not at the unit tier

`design.md` — Decision 6 places the transaction and the lock in the two
driving adapters, and both mechanisms *are* the requirement in these three
cases:

- A fake store keeps its dictionary entries through any exception, so it
  cannot tell a committed write from an unwound one; the partial-cascade
  scenario would be green with no transaction at all.
- The torn-rejection scenario turns on two writes being in one unit. A
  double that models no unit passes it whichever way the adapter is
  written. The unit-tier twin narrows this by installing a provider that
  *does* model one, which is worth having; it still cannot establish that
  the real `transaction()` binds the session the way it must.
- "One at a time" is a claim about two callers in different processes. An
  advisory lock is the only thing in this design that holds across them,
  and nothing in a single-process test with no Postgres holds anything.

## Level

The driving adapters over a real Postgres session, with a real catalog
product, a real launch record and the served step set the deployment
carries. Nothing smaller has both the walk and the transaction.

## Test-database lifecycle

The tier's convention: a unique SKU per test, no truncate fixture,
`alembic upgrade head` assumed applied, and the `database_url` fixture
gating on a configured database. Unlike
`test_gate_progression_stand_down_live.py`, this module writes only its
own rows and never the shared step set, so it needs no isolated database
beyond the tier's own.

## What is fixed, and what is INVENTED

Fixed: that the cascade runs inside one `transaction()` opened by the
driving adapter, with the product's advisory lock held for its whole
duration (`tasks.md` 4.3, 5.6; `design.md` — Decision 6); that the
rejecting path's approval and cool-off refresh are in one `transaction()`
(`tasks.md` 5.5); and that a gate crossing journals a `gate-opened` entry,
which `tests/unit/launch/application/test_launch_journal_appends.py`
records.

INVENTED, each with a correction point:

- The pass's and the adapter's entry points and collaborator names,
  transcribed from
  `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`
  and `test_gate_decision_wiring.py`, which are the correction points.
- How a cascade is made to fail part-way: by substituting the
  module-level `advance_gate` the cascade calls, found through
  `progress_launch.__module__` — the same seam
  `tests/unit/launch/application/test_progress_launch.py` uses and
  documents.
- Which roster person decides. The roster is written through the real
  `access` use cases, so the decision resolves a person that really is on
  it.

## Expected first-run state

Neither `gate_progression_job.py` nor `gate_confirmation.py` exists
(`tasks.md` 4.1, 5.1), so every test here is expected to fail on an absent
target where a database is configured, and to skip where one is not. Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/integration` — 3
passed, 112 skipped (no `DATABASE_URL` is configured here, so this tier
did not in fact run).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import commerce_ops.launch.application as launch_application
from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook, Satisfied
from commerce_ops.launch.domain.launch_run import ApprovalDecision, Launch, Provenance
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

pytestmark = pytest.mark.anyio

JOB_MODULE_PATH: Final = (
    "commerce_ops.launch.infrastructure.driving.gate_progression_job"
)
CONFIRMATION_MODULE_PATH: Final = (
    "commerce_ops.launch.infrastructure.driving.gate_confirmation"
)

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)

ALICE_SLACK: Final = "U01ALICE"

KIND_GATE_OPENED: Final = "gate-opened"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def _session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


def _unique_sku() -> Sku:
    return Sku(f"GP-{uuid.uuid4().hex[:12].upper()}")


async def _served(engine: AsyncEngine) -> LaunchPlaybook:
    async with _session(engine) as session:
        return await PlaybookRepository(session).get("read-through")


async def _launch_standing_at(
    engine: AsyncEngine, gate: str, *, satisfy_next: bool = False
) -> ProductId:
    """A real catalog product with a real launch record standing at `gate`.

    The launch is walked on the aggregate against the *served* step set, so
    what it stands at is what the deployment's own playbook would produce,
    and the write goes through the real repository.
    """
    playbook = await _served(engine)
    async with _session(engine) as session:
        product = await register_product(
            CatalogProductRepository(session),
            sku=_unique_sku(),
            marketplace_id=MARKETPLACE,
            name="Bamboo Cutting Board",
        )
    launch, _ = Launch.start(
        product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != gate:
        _satisfy(launch, playbook)
        launch.advance_gate(playbook)
    _satisfy_steps(launch, playbook, launch.current_gate)
    _satisfy_metrics(launch, playbook, launch.current_gate)
    if satisfy_next:
        following = _gate_after(playbook, gate)
        if following is not None:
            _satisfy_steps(launch, playbook, following)
            _satisfy_metrics(launch, playbook, following)
    async with _session(engine) as session:
        await LaunchRepository(session).save(launch)
    return product.id


def _gate_after(playbook: LaunchPlaybook, gate: str) -> str | None:
    ordered = [
        entry.identifier for entry in sorted(playbook.gates, key=lambda g: g.position)
    ]
    position = ordered.index(gate)
    return ordered[position + 1] if position + 1 < len(ordered) else None


def _satisfy_steps(launch: Launch, playbook: LaunchPlaybook, gate: str) -> None:
    for step in playbook.steps_for_gate(gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=Provenance(
                    source="attestation",
                    who="Helen",
                    when=NOW,
                    evidence="blocking work signed off for this fixture",
                ),
            )


def _satisfy_metrics(launch: Launch, playbook: LaunchPlaybook, gate: str) -> None:
    """Attest every metric condition the served playbook authors on `gate`.

    Read off the playbook rather than listed here: which gates author
    metric conditions is repo-owned framework (`proposal.md` — Impact says
    to read `launch_playbook.py` rather than trust a list), and a fixture
    naming them would go stale silently.
    """
    from commerce_ops.launch.domain.launch_playbook import MetricCondition
    from commerce_ops.launch.domain.launch_run import MetricAttestation

    for condition in playbook.conditions_for_gate(gate):
        if not isinstance(condition, MetricCondition):
            continue
        launch.record_metric_attestation(
            playbook,
            MetricAttestation(
                gate_id=gate,
                metric_id=condition.metric_id,
                attester="Mira",
                when=NOW,
                evidence="attested for this fixture",
            ),
        )


def _satisfy(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Everything the launch's current gate waits on, approval included."""
    from commerce_ops.launch.domain.launch_run import GateApproval
    from commerce_ops.shared.domain.lifecycle_stage import Posture

    gate = launch.current_gate
    _satisfy_steps(launch, playbook, gate)
    _satisfy_metrics(launch, playbook, gate)
    if launch.awaiting_confirmation(playbook) or launch.approval_for(gate) is None:
        definition = next(
            (entry for entry in playbook.gates if entry.identifier == gate), None
        )
        if (
            definition is not None
            and definition.opening.name == "REQUIRES_CONFIRMATION"
        ):
            launch.approve_gate(
                gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=NOW,
                    posture=Posture.SCALE
                    if _gate_after(playbook, gate) is None
                    else None,
                ),
            )


async def _current_gate(engine: AsyncEngine, product_id: ProductId) -> str:
    """Re-read through a fresh session, so what is asserted is what
    Postgres holds rather than an identity map."""
    async with _session(engine) as session:
        launch = await LaunchRepository(session).get_by_product_id(product_id)
        assert launch is not None
        return launch.current_gate


async def _journal_kinds(engine: AsyncEngine, product_id: ProductId) -> list[Any]:
    async with _session(engine) as session:
        entries = await LaunchJournalRepository(session).read(product_id)
        return [getattr(entry, "kind", None) for entry in entries]


# ---------------------------------------------------------------------------
# Reaching the two adapters
# ---------------------------------------------------------------------------

_JOB_ENTRY_NAMES: Final = (
    "run_gate_progression_pass",
    "run_gate_progression",
    "advance_launch_gates",
    "progress_gates",
    "run_pass",
)
_DECISION_ENTRY_NAMES: Final = (
    "_handle_gate_decision",
    "handle_gate_decision",
    "_handle_decision",
    "handle_decision",
    "_decide",
    "handle_gate_decision_action",
)
_SUPPRESSION_NAMES: Final = (
    "suppression",
    "GateAskSuppressionRepository",
    "gate_ask_suppression",
    "ask_suppression",
    "asks",
)
_ASK_NAMES: Final = (
    "post_gate_ask",
    "deliver_gate_ask",
    "ask_for_confirmation",
    "request_confirmation",
    "post_ask",
    "deliver",
)
_USE_CASE_NAMES: Final = ("progress_launch", "progress", "advance_launch")


def _module(path: str, task: str) -> ModuleType:
    try:
        return importlib.import_module(path)
    except ImportError as error:
        pytest.fail(
            f"{path} does not exist ({error}); `tasks.md` {task} creates it. "
            "This is the absent-target state, not a defect in this file."
        )


def _entry(module: ModuleType, names: tuple[str, ...]) -> Any:
    for name in names:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no entry point found on {module.__name__} under any of {names} — "
        "correct this file's probe to the implemented name"
    )


def _cascade_module() -> ModuleType:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return sys.modules[found.__module__]
    pytest.fail(
        "`commerce_ops.launch.application` exports no cascade use case under "
        f"any of {_USE_CASE_NAMES} (`tasks.md` 3.2, 3.6)"
    )


class _Silent:
    """Stands in for anything that would reach Slack."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class _FailingSuppression:
    """A cool-off store whose refresh raises — the torn-write condition."""

    def __init__(self) -> None:
        self.attempts = 0

    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    get = read
    latest = read
    last_for = read

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        self.attempts += 1
        raise RuntimeError("simulated cool-off refresh failure")

    refresh = record_rejection
    note_rejection = record_rejection
    record = record_rejection

    async def record_delivery(self, *args: Any, **kwargs: Any) -> None:
        return None

    mark_delivered = record_delivery


class _ScriptedAdvance:
    """The real `advance_gate`, until the `crossings`th call; then it
    raises.

    Delegates rather than reimplements, so the crossings it does make are
    real writes through the real repository — which is what makes "the
    crossing was undone" a statement about Postgres.
    """

    def __init__(self, real: Any, *, crossings: int) -> None:
        self._real = real
        self.crossings = crossings
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls > self.crossings:
            raise RuntimeError("simulated cascade failure part-way")
        return await self._real(*args, **kwargs)


def _slack_body(
    *, approve: bool, product_id: ProductId, gate_id: str
) -> dict[str, Any]:
    # CORRECTED fixture: the control carries the identifier's *value*, which
    # is what `post_gate_ask` writes. `str(ProductId(...))` renders the
    # dataclass repr, so every press below named a product nothing could
    # find and was refused as "no launch record" — which would have met
    # each assertion here with the wrong reason.
    value = json.dumps({"product_id": product_id.value, "gate_id": gate_id})
    return {
        "type": "block_actions",
        "user": {"id": ALICE_SLACK},
        "channel": {"id": os.environ.get("PRODUCT_AGENT_MONITORING_CHANNEL_ID", "C0")},
        "actions": [
            {
                "action_id": "approve_launch_gate" if approve else "reject_launch_gate",
                "type": "button",
                "value": value,
            }
        ],
        "response_url": "https://slack.example/respond",
    }


class _RealRosterReader:
    """The roster reader the composition root normally injects.

    CORRECTED probe: the adapter takes its reader from the root rather than
    constructing one -- `main.py` does exactly this, and
    `automation_confirmation.py` sets the precedent -- so a test importing
    the module directly must supply it. It reads through the real `access`
    use case, which keeps this file's claim true: the decision resolves a
    person who really is on the roster.

    Over **this tier's engine**, never `PostgresRoster()`. That adapter
    opens its own pool and binds it to whichever event loop first touches
    it, which outlives the module and breaks a later test in this tier --
    the trap `test_playbook_authoring_roster_live.py` already records
    having fallen into.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def list_people(self) -> Any:
        from sqlalchemy.ext.asyncio import AsyncSession

        from commerce_ops.access.application import list_people
        from commerce_ops.access.infrastructure.driven.roster_repository import (
            RosterRepository,
        )

        async with AsyncSession(self._engine) as db_session:
            return await list_people(roster=RosterRepository(db_session))


_MISSING: Any = object()


@pytest.fixture(autouse=True)
def _restore_confirmation_module() -> Any:
    """Undo every substitution this module makes on the adapter.

    `_wire_roster` and `_bind_session_providers` set module attributes
    outright rather than through `monkeypatch`, because they are reached
    from `_press` rather than from a test body. Left in place they outlive
    this file: `gate_confirmation.session` would keep pointing at an engine
    this tier has disposed, and the next module to touch it fails with
    "attached to a different loop" — which is exactly how this file broke
    `test_slack_entry_start.py` before this fixture existed.
    """
    names = ("session", "transaction", "read_people", "roster", "roster_reader")
    modules = [
        importlib.import_module(path)
        for path in (CONFIRMATION_MODULE_PATH, JOB_MODULE_PATH)
    ]
    saved = [
        (
            module,
            {
                name: getattr(module, name)
                for name in names
                if getattr(module, name, _MISSING) is not _MISSING
            },
        )
        for module in modules
    ]
    try:
        yield
    finally:
        for module, values in saved:
            for name, value in values.items():
                setattr(module, name, value)


async def _seed_decider(engine: Any) -> None:
    """Put the deciding person on the roster, through `access`'s own use case.

    ADDED: this file's INVENTED note says the roster "is written through the
    real `access` use cases, so the decision resolves a person that really is
    on it", and nothing was doing it -- against a freshly migrated database
    the roster is empty, so every decision here was refused as an unknown
    identity before reaching the behaviour under test.

    Created as an admin because the roster refuses to hold anyone without an
    active admin. Gate approval does not *require* admin -- delta R6 says so
    explicitly, and the unit tier asserts it -- so nothing here turns on it.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from commerce_ops.access.application import create_person, list_people
    from commerce_ops.access.infrastructure.driven.roster_repository import (
        RosterRepository,
    )

    async with AsyncSession(engine) as db_session:
        roster = RosterRepository(db_session)
        if any(
            getattr(person, "slack_identity", None) == ALICE_SLACK
            for person in await list_people(roster=roster)
        ):
            return
        await create_person(
            roster=roster,
            principal="integration-tier",
            display_name="Alice",
            slack_identity=ALICE_SLACK,
            admin=True,
        )


def _bind_session_providers(module: ModuleType, engine: Any) -> None:
    """Point the adapter's `session`/`transaction` at this tier's engine.

    ADDED, following `test_clickup_sync_job_containment_live.py`, which
    substitutes `session` on the job module for the same reason: the real
    providers build a global engine and bind it to whichever event loop
    first touches it, so an adapter driven from this tier otherwise fails
    with "attached to a different loop".

    `transaction` is rebuilt rather than aliased to `session`, and that
    matters here more than anywhere: this file's subject *is* whether two
    writes land together, so the substitute has to be a real transaction
    with `database.transaction()`'s savepoint semantics -- an inner
    `commit()` releasing a savepoint rather than ending the outer
    transaction. Aliasing it to a plain session would make the atomicity
    test pass by construction while proving nothing.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    @asynccontextmanager
    async def _session(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async with AsyncSession(engine, expire_on_commit=False) as db_session:
            yield db_session

    @asynccontextmanager
    async def _transaction(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async with engine.connect() as connection, connection.begin():
            db_session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            try:
                yield db_session
            finally:
                await db_session.close()

    for name, provider in (("session", _session), ("transaction", _transaction)):
        if hasattr(module, name):
            setattr(module, name, provider)


def _wire_roster(module: ModuleType, engine: Any) -> None:
    for name in ("read_people", "roster", "roster_reader"):
        if getattr(module, name, _MISSING) is not _MISSING:
            setattr(module, name, _RealRosterReader(engine))
            return
    raise AssertionError(
        "the gate confirmation adapter exposes no roster collaborator to "
        "inject; correct this file's probe to the implemented name"
    )


async def _press(
    module: ModuleType,
    *,
    approve: bool,
    product_id: ProductId,
    gate_id: str,
    engine: Any,
) -> Any:
    await _seed_decider(engine)
    _wire_roster(module, engine)
    _bind_session_providers(module, engine)
    entry = _entry(module, _DECISION_ENTRY_NAMES)
    body = _slack_body(approve=approve, product_id=product_id, gate_id=gate_id)
    pool: dict[str, Any] = {
        "ack": _Silent(),
        "body": body,
        "payload": body["actions"][0],
        "action": body["actions"][0],
        "respond": _Silent(),
        "say": _Silent(),
        "context": {},
        "approve": approve,
        "approving": approve,
        "product_id": product_id,
        "gate_id": gate_id,
        "slack_identity": ALICE_SLACK,
        "when": NOW,
    }
    accepted = set(inspect.signature(entry).parameters)
    returned = entry(**{k: v for k, v in pool.items() if k in accepted})
    if inspect.isawaitable(returned):
        returned = await returned
    return returned


async def _run_pass(module: ModuleType, engine: Any) -> Any:
    # The pass reaches its database through the global `session()` and
    # `transaction()`, which bind one engine to the first loop that touches
    # it. Pointed at this tier's engine instead, and restored by the autouse
    # fixture above, so nothing here outlives the module.
    _bind_session_providers(module, engine)
    entry = _entry(module, _JOB_ENTRY_NAMES)
    accepted = set(inspect.signature(entry).parameters)
    return await entry(**{"now": NOW} if "now" in accepted else {})


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# advanced
# ---------------------------------------------------------------------------


async def test_a_cascade_failing_part_way_leaves_the_launch_where_it_started(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A cascade failing part-way leaves the launch where it
    started.

    WHEN a launch crosses one gate and the attempt at the next raises
    THEN the launch stands at the gate it was at when the pass reached it,
    the crossing already made having been undone.

    The launch is set up so that two consecutive gates could open, and the
    substituted advance crosses the first for real before raising on the
    second. The gate is then re-read through a fresh session, so what is
    asserted is what Postgres holds — which is the whole point of driving
    this here rather than over a dictionary that keeps its entries through
    any exception.
    """
    job = _module(JOB_MODULE_PATH, "4.1")
    cascade = _cascade_module()
    assert hasattr(cascade, "advance_gate"), (
        f"{cascade.__name__} holds no module-level `advance_gate`, so the "
        "cascade cannot be made to fail part-way; correct this file's seam"
    )
    playbook = await _served(engine)
    # `listable` opens automatically, and so does the gate after it, so a
    # two-gate cascade needs no approval — which keeps this test about the
    # transaction rather than about the roster.
    product_id = await _launch_standing_at(engine, "listable", satisfy_next=True)
    started_at = await _current_gate(engine, product_id)
    assert started_at == "listable"
    following = _gate_after(playbook, "listable")
    assert following is not None

    monkeypatch.setattr(
        cascade, "advance_gate", _ScriptedAdvance(cascade.advance_gate, crossings=1)
    )
    for name in _ASK_NAMES:
        if hasattr(job, name):
            monkeypatch.setattr(job, name, _Silent())

    with pytest.raises(Exception):  # noqa: B017 -- the run's outcome is not the subject
        await _run_pass(job, engine)

    # SPECIFIED: the launch stands at the gate it was at when the pass
    # reached it, the crossing already made having been undone.
    assert await _current_gate(engine, product_id) == started_at, (
        "a cascade that failed part-way left the launch partially advanced; "
        "the crossing it made before the failure was not undone"
    )
    # SPECIFIED, read at its consequence: the crossing's journal entry is
    # undone with it, since the whole cascade is one unit.
    assert KIND_GATE_OPENED not in await _journal_kinds(engine, product_id), (
        "a crossing that was undone left its `gate-opened` entry behind, so "
        "the journal records a gate opening that did not happen"
    )


# ---------------------------------------------------------------------------
# Requirement: A gate is asked about at most once a day
# ---------------------------------------------------------------------------


async def test_a_rejection_and_its_cool_off_refresh_land_together_or_not_at_all(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A rejection and its cool-off refresh land together or not
    at all.

    WHEN a rejecting decision is recorded and the cool-off refresh fails
    THEN neither the rejecting approval nor the refresh stands, and the
    decider is told the decision was not recorded.

    "Unlike a delivery, where a lost write costs one duplicate message, a
    lost refresh here re-proposes a gate a person has just declined."

    The approval is checked through a fresh session, so an adapter that
    committed it outside the transaction carrying the refresh is caught —
    which is the only thing that distinguishes a correct implementation
    from one that merely calls both writes.
    """
    confirmation = _module(CONFIRMATION_MODULE_PATH, "5.1")
    product_id = await _launch_standing_at(engine, "commit")
    suppression = _FailingSuppression()
    placed = [name for name in _SUPPRESSION_NAMES if hasattr(confirmation, name)]
    assert placed, (
        "the decision adapter exposes no cool-off collaborator under any of "
        f"{_SUPPRESSION_NAMES}; correct this file's probe"
    )
    for name in placed:
        # CORRECTED probe: where the adapter holds the repository *class*,
        # it constructs one per session, so the substitute has to be a
        # factory returning the fake rather than the fake itself. The unit
        # harness in `test_gate_decision_wiring.py` makes the same
        # distinction.
        target: Any = suppression
        if isinstance(getattr(confirmation, name), type):

            def target(*args: Any, _fake: Any = suppression, **kwargs: Any) -> Any:
                return _fake

        monkeypatch.setattr(confirmation, name, target)

    await _press(
        confirmation,
        approve=False,
        product_id=product_id,
        gate_id="commit",
        engine=engine,
    )

    # Premise: the refresh really was attempted.
    assert suppression.attempts >= 1, (
        "the rejecting decision never reached the cool-off refresh, so this "
        "test exercised nothing"
    )
    # SPECIFIED: neither the rejecting approval...
    async with _session(engine) as session:
        launch = await LaunchRepository(session).get_by_product_id(product_id)
        assert launch is not None
        approval = launch.approval_for("commit")
    assert approval is None, (
        "the rejecting approval stands in Postgres although its cool-off "
        "refresh failed, so a gate the person just declined is re-proposed "
        "tomorrow with no record of the decision that declined it"
    )
    # ...nor the refresh stands — the store raised, so it wrote nothing.


# ---------------------------------------------------------------------------
# Requirement: A decision records the approval and reports what it did
# ---------------------------------------------------------------------------


async def test_a_decision_and_the_pass_do_not_cross_the_same_gate_twice(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A decision and the pass do not cross the same gate twice.

    WHEN a decision's advance and a scheduled pass would act on the same
    launch at the same time
    THEN one of them advances the launch and the other acts on the launch
    as that advance left it.

    "A gate crossing is not idempotent — it emits `GateOpened` and journals
    it", so the assertion is on the **count** of `gate-opened` entries for
    the launch: exactly one, however the two callers interleave. Driven as
    two genuinely concurrent tasks, because the advisory lock is the only
    thing in this design that excludes them and it holds nothing unless
    both are really in flight.

    The launch stands at an automatic gate whose conditions are satisfied,
    so both paths would cross it; which of the two wins is deliberately not
    asserted, since the requirement does not state one.
    """
    job = _module(JOB_MODULE_PATH, "4.1")
    confirmation = _module(CONFIRMATION_MODULE_PATH, "5.1")
    product_id = await _launch_standing_at(engine, "commit")
    for module in (job, confirmation):
        for name in _ASK_NAMES:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, _Silent())

    await asyncio.gather(
        _run_pass(job, engine),
        _press(
            confirmation,
            approve=True,
            product_id=product_id,
            gate_id="commit",
            engine=engine,
        ),
        return_exceptions=True,
    )

    kinds = await _journal_kinds(engine, product_id)
    crossings = kinds.count(KIND_GATE_OPENED)
    # SPECIFIED: one of them advances the launch and the other acts on it
    # as that advance left it — so the gate is crossed once, not twice.
    assert crossings <= 1, (
        "the same gate was crossed more than once by two concurrent paths, "
        f"so the consequences reserved for one crossing were produced twice: "
        f"the journal holds {kinds!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Which of the two concurrent paths wins. The requirement states only
#   that one of them advances and the other acts on the result; asserting
#   an order would impose a rule nobody agreed to.
# - That the lock is transaction-scoped rather than session-scoped
#   (`design.md` — Decision 6, on a pooled connection outliving its
#   transaction). It is a mechanism choice, not a stated behaviour; what
#   it protects against — a lock travelling to the next borrower — would
#   need a test that exhausted the pool, which no scenario asks for.
# - The window `design.md` — Decision 11 accepts, in which two genuinely
#   concurrent presses each record an approval. It is recorded as
#   accepted rather than closed, and the assertion above is on crossings
#   for that reason rather than on approvals.
# ---------------------------------------------------------------------------
