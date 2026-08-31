"""A decision and the webhook's trigger cross a gate once, not twice.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-from-clickup-webhook`:
`openspec/changes/advance-gates-from-clickup-webhook/specs/launch-gate-progression/spec.md`

Covers exactly one scenario, from the MODIFIED requirement *A decision
records the approval and reports what it did*:

    #### Scenario: A decision and a webhook-triggered advance do not cross
    the same gate twice
    - **WHEN** a decision's advance and the ClickUp webhook's
      advance-and-ask trigger would act on the same launch at the same
      time
    - **THEN** one of them advances the launch and the other acts on the
      launch as that advance left it

The requirement sentence it comes from is the one this change amends:
"The decision path, the recurring pass, **and the ClickUp webhook's own
advance-and-ask trigger** SHALL NOT advance the same launch concurrently."

## Why this is at the integration tier

For the reason its neighbour
`tests/integration/launch/test_gate_progression_atomicity_live.py`
records for the pass's own version of this scenario, unchanged by this
change: "one at a time" is a claim about two callers in different
processes, an advisory lock is the only thing in this design that holds
across them, and nothing in a single-process test with no Postgres holds
anything. This change adds a third contender for the same lock
(`design.md` — Risks), which is a new pairing rather than a new
mechanism — so it is tested the same way, in its own file rather than by
editing that one.

## Level

The two driving adapters over a real Postgres session, with a real
catalog product, a real launch record and the served step set the
deployment carries — the tier's own convention, and identical to the
neighbour file's.

## Test-database lifecycle

The tier's convention: a unique SKU per test, no truncate fixture,
`alembic upgrade head` assumed applied, and the `database_url` fixture
gating on a configured database. This module writes only its own rows and
never the shared step set, so it needs no isolated database beyond the
tier's own.

## What is fixed, and what is INVENTED

Fixed: that the trigger runs the cascade inside `transaction()` with the
product's advisory lock held (`tasks.md` 1.1; `design.md` — Decision 1),
and that a gate crossing journals a `gate-opened` entry.

INVENTED, each with a correction point:

- The trigger's name and call shape. `_TRIGGER_NAMES` and `_advance`
  probe; correction point is this file, kept in step with
  `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py`.
- Everything else — the adapters' entry points, the collaborator names,
  the Slack press body, the roster wiring and the session rebinding — is
  transcribed wholesale from
  `tests/integration/launch/test_gate_progression_atomicity_live.py`,
  which records the provenance and the traps behind each. Correcting any
  of it is a fixture correction there as much as here.

## Expected first-run state

`gate_progression_job.py` carries no `advance_and_ask` (`tasks.md` 1.1),
so this test is expected to fail on an **absent target** where a database
is configured, and to skip where one is not. Per `ai-toolkit:testing`
that establishes absence only.

**This file has never been executed.** The environment it was written in
configures no `DATABASE_URL`, so the tier skipped rather than ran, and
nothing here has been observed to do anything at all — not even to fail
for the reason stated above. Whoever implements the change should run
`uv run pytest tests/integration/launch/test_webhook_advance_atomicity_live.py`
against a real database *before* trusting a green result from it, since a
fixture defect and a satisfied requirement are indistinguishable in a run
that never happened.

Baseline recorded before this test was written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `96303a7`: `uv run pytest tests/integration` — 3 passed, 124
skipped (no `DATABASE_URL` is configured here). `uv run pytest tests/unit
tests/agents` — 1727 passed, 0 failed.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
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

#: Kept in step with `test_advance_and_ask.py`, which is the correction
#: point for the trigger's name.
_TRIGGER_NAMES: Final = (
    "advance_and_ask",
    "advance_and_ask_for",
    "advance_one_and_ask",
    "advance_launch_and_ask",
)

_DECISION_ENTRY_NAMES: Final = (
    "_handle_gate_decision",
    "handle_gate_decision",
    "_handle_decision",
    "handle_decision",
    "_decide",
    "handle_gate_decision_action",
)
_ASK_NAMES: Final = (
    "post_gate_ask",
    "deliver_gate_ask",
    "ask_for_confirmation",
    "request_confirmation",
    "post_ask",
    "deliver",
)

_MISSING: Any = object()


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
    return Sku(f"WA-{uuid.uuid4().hex[:12].upper()}")


async def _served(engine: AsyncEngine) -> LaunchPlaybook:
    async with _session(engine) as session:
        return await PlaybookRepository(session).get("read-through")


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
                    source="clickup",
                    who="183",
                    when=NOW,
                    evidence="the mapped ClickUp task was closed",
                ),
            )


def _satisfy_metrics(launch: Launch, playbook: LaunchPlaybook, gate: str) -> None:
    """Attest every metric condition the served playbook authors on `gate`,
    read off the playbook rather than listed here — transcribed from
    `test_gate_progression_atomicity_live.py`, which records why."""
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


async def _launch_standing_at(engine: AsyncEngine, gate: str) -> ProductId:
    """A real catalog product with a real launch record standing at `gate`,
    with everything but the approval satisfied — the state a ClickUp
    closure leaves behind for a confirmation gate, and the state in which
    both a decision and the webhook's trigger would act."""
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
    async with _session(engine) as session:
        await LaunchRepository(session).save(launch)
    return product.id


async def _journal_kinds(engine: AsyncEngine, product_id: ProductId) -> list[Any]:
    async with _session(engine) as session:
        entries = await LaunchJournalRepository(session).read(product_id)
        return [getattr(entry, "kind", None) for entry in entries]


async def _launch_state(engine: AsyncEngine, product_id: ProductId) -> tuple[str, Any]:
    """The gate the launch stands at, and its approval for `commit`, read
    through a fresh session so what is asserted is what Postgres holds."""
    async with _session(engine) as session:
        launch = await LaunchRepository(session).get_by_product_id(product_id)
        assert launch is not None
        return launch.current_gate, launch.approval_for("commit")


# ---------------------------------------------------------------------------
# Reaching the two adapters — transcribed from
# `test_gate_progression_atomicity_live.py`
# ---------------------------------------------------------------------------


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


class _Silent:
    """Stands in for anything that would reach Slack."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class _RealRosterReader:
    """The roster reader the composition root normally injects, over this
    tier's engine — transcribed from
    `test_gate_progression_atomicity_live.py`, which records why it must
    never be `PostgresRoster()`."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def list_people(self) -> Any:
        from commerce_ops.access.application import list_people
        from commerce_ops.access.infrastructure.driven.roster_repository import (
            RosterRepository,
        )

        async with AsyncSession(self._engine) as db_session:
            return await list_people(roster=RosterRepository(db_session))


@pytest.fixture(autouse=True)
def _restore_module_globals() -> Any:
    """Undo every substitution this module makes on the two adapters.

    `_wire_roster` and `_bind_session_providers` set module attributes
    outright rather than through `monkeypatch`, because they are reached
    from helpers rather than from a test body. Left in place they outlive
    this file and break the next module to touch either adapter with
    "attached to a different loop" — the trap the neighbour file records
    having fallen into.
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
    """Put the deciding person on the roster, through `access`'s own use
    case — without it every decision here is refused as an unknown
    identity before reaching the behaviour under test."""
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
    """Point an adapter's `session`/`transaction` at this tier's engine.

    `transaction` is rebuilt rather than aliased to `session`: this file's
    subject is what one transaction plus one advisory lock exclude, so the
    substitute has to carry `database.transaction()`'s savepoint
    semantics.
    """

    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
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

    for name, provider in (("session", _provider), ("transaction", _transaction)):
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


def _slack_body(
    *, approve: bool, product_id: ProductId, gate_id: str
) -> dict[str, Any]:
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


async def _advance(module: ModuleType, engine: Any, product_id: ProductId) -> Any:
    """Invoke the webhook's trigger the way a background task would: with
    the product identifier alone, over its own sessions."""
    _bind_session_providers(module, engine)
    entry = _entry(module, _TRIGGER_NAMES)
    parameters = inspect.signature(entry).parameters
    kwargs: dict[str, Any] = {"now": NOW} if "now" in parameters else {}
    for name in ("product_id", "product", "launch_id"):
        if (
            name in parameters
            and parameters[name].kind is not inspect.Parameter.POSITIONAL_ONLY
        ):
            return await entry(**{name: product_id, **kwargs})
    return await entry(product_id, **kwargs)


# ---------------------------------------------------------------------------
# Requirement: A decision records the approval and reports what it did
# ---------------------------------------------------------------------------


async def test_a_decision_and_a_webhook_triggered_advance_do_not_cross_the_same_gate_twice(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A decision and a webhook-triggered advance do not cross
    the same gate twice.

    WHEN a decision's advance and the ClickUp webhook's advance-and-ask
    trigger would act on the same launch at the same time
    THEN one of them advances the launch and the other acts on the launch
    as that advance left it.

    A gate crossing is not idempotent — it emits `GateOpened` and journals
    it — so the assertion is on the **count** of `gate-opened` entries for
    the launch: at most one, however the two callers interleave. Driven as
    two genuinely concurrent tasks, because the advisory lock is the only
    thing in this design that excludes them and it holds nothing unless
    both are really in flight.

    Which of the two wins is deliberately not asserted: the requirement
    states only that one advances and the other acts on the result, and
    both orderings are legitimate here — a trigger that takes the lock
    first finds no approval and does nothing, and one that takes it second
    finds the gate already crossed.
    """
    job = _module(JOB_MODULE_PATH, "1.1")
    confirmation = _module(CONFIRMATION_MODULE_PATH, "5.1")
    product_id = await _launch_standing_at(engine, "commit")
    for module in (job, confirmation):
        for name in _ASK_NAMES:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, _Silent())

    await asyncio.gather(
        _advance(job, engine, product_id),
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
        "so the consequences reserved for one crossing were produced twice: "
        f"the journal holds {kinds!r}"
    )
    # Premise, not the requirement: at least one of the two paths did
    # something, so a green result here cannot come from both of them
    # having quietly done nothing at all.
    gate, approval = await _launch_state(engine, product_id)
    assert approval is not None or gate != "commit", (
        "neither the decision nor the webhook's trigger left any mark on the "
        "launch — no approval recorded and no gate crossed — so this test "
        "exercised no concurrency at all"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Which of the two concurrent paths wins. The requirement states only
#   that one of them advances and the other acts on the result; asserting
#   an order would impose a rule nobody agreed to.
# - The webhook's trigger against the *recurring pass*, as opposed to
#   against a decision. The delta states the three-way rule but gives a
#   scenario only for the decision pairing, and the pass-versus-decision
#   pairing already has its own test in
#   `test_gate_progression_atomicity_live.py`. Adding an unstated third
#   pairing would assert a case nobody wrote down; the lock it would
#   exercise is the same one.
# - That the trigger reaches the lock at all, as distinct from happening
#   not to collide. A test that established it would have to observe the
#   lock itself rather than its effect, which no scenario asks for.
# ---------------------------------------------------------------------------
