"""Tests for a failed journal append never failing, nor disturbing, the
command it records.

Derived from the delta spec:
openspec/changes/add-launch-journal/specs/launch-journal/spec.md

Covers the ADDED requirement *A failed append never fails the command it
records, nor disturbs its work* — all four scenarios:

- *A failed append leaves the command's own work standing*
- *A failed append does not prevent the graduation stamp*
- *A failed append on a refused advance leaves the refusal unchanged*
- *A failed append is reported*

## The fake models a poisoned transaction, not merely an exception

`tasks.md` 1.2 and `design.md` Decision 3 both record the trap this file
is written around, inherited from `contain-a-failing-launch` (archived
2026-08-27): **a fake journal that merely raises reproduces the exception
but not the failed transaction state the rollback exists for**, so a test
built on one passes whether or not the rollback was ever written.

So `FakeSession` here models the state a failed `INSERT` really leaves an
`AsyncSession` in: once poisoned, *every* later use of it raises
`PendingRollbackError` until `rollback()` is called. The launch store,
the journal and the catalog stamp all share one, exactly as the five
composing adapters share one real session. Omitting the rollback
therefore turns the graduation-stamp scenario red — which `tasks.md` 5.3
names as the scenario the whole guarantee exists for.

The delta spec's requirement is stated in the same two halves, and the
tests keep them apart: *catching* the failure (the command returns) and
*leaving the command able to finish* (the session is usable afterwards).
A test that only checks the first half is the one the trap produces.

## Level

The application layer, fast mocked unit tier — the containment is in the
use case (`design.md` Decision 3), and the poisoned-session fake gives
this tier the discriminating power the scenarios need. `tasks.md` 1.2
offers the integration tier as the alternative for the same scenarios;
this file takes the fake option it names, so the guarantee is checked at
commit time rather than only at `pre-push`.

## The interface under test does not exist yet, and its shape is INVENTED

Every test here is expected to fail on an absent target (a `TypeError`
for the unexpected `journal` argument). Per `ai-toolkit:testing`, that
establishes only absence.

Fixed by this change's artifacts: that the append is wrapped in `except
Exception`, that the handler rolls the session back **through the journal
port** and then logs at `error` naming the launch and the occurrence
(`design.md` Decision 3, `tasks.md` 5.1); that the append sits after the
command's own save and before the catalog stamp (Decision 2).

INVENTED, with correction points: the port being async (`FakeJournal` /
`PoisonedJournal`); that the failure is reported through the standard
library's `logging`, which is the only report the artifacts name
(`_errors`); and that a real session's poisoned state surfaces as
SQLAlchemy's `PendingRollbackError` — any exception type would do, and
the implementation's `except Exception` does not depend on it
(`FakeSession`).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from sqlalchemy.exc import PendingRollbackError

from commerce_ops.launch.application import (
    advance_gate,
    record_step_outcome,
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
    GateBlockedError,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture, SteadyState
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
RECORDED_AT: Final = datetime(2027, 6, 2, 14, 30, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 6, 3, 9, 0, tzinfo=UTC)
ATTESTED_AT: Final = datetime(2027, 6, 4, 9, 0, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 11, 1)

APPROVER: Final = "Helen"
RECORDER: Final = "Dana"
ATTESTER: Final = "Mira"

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

TRACKED_STEP: Final = "listing.title-conforms"
TRACKED_STEP_NAME: Final = "Write the listing title to the conformance rules"

APPEND_FAILURE: Final = "the journal insert failed at the database"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A session that a failed write really poisons
# ---------------------------------------------------------------------------


class FakeSession:
    """The one session the store, the journal and the stamp share.

    A failed statement poisons it: every later use raises until
    `rollback()` is called. This is what makes the containment tests
    discriminate — an implementation that catches the append's exception
    but never rolls back leaves the session poisoned, and the command's
    remaining work fails on it.
    """

    def __init__(self) -> None:
        self.poisoned = False
        self.rollbacks = 0

    def use(self, what: str) -> None:
        if self.poisoned:
            raise PendingRollbackError(
                f"{what} attempted on a session poisoned by a failed "
                f"journal append; the transaction must be rolled back first"
            )

    def fail(self, what: str) -> None:
        self.use(what)
        self.poisoned = True
        raise RuntimeError(APPEND_FAILURE)

    def rollback(self) -> None:
        self.rollbacks += 1
        self.poisoned = False


class PoisonedJournal:
    """A `LaunchJournal` whose every append fails at the database, taking
    the shared session down with it until `rollback()` is called."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.attempted: list[Any] = []

    async def append(self, entry: Any) -> None:
        self.attempted.append(entry)
        self.session.fail("a journal append")

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        self.session.use("a journal read")
        return ()

    async def rollback(self) -> None:
        self.session.rollback()


class SessionBoundLaunchStore:
    """`LaunchStore` over the shared session — so a poisoned session makes
    a read-back fail exactly as a real one would."""

    def __init__(self, session: FakeSession, *launches: Launch) -> None:
        self.session = session
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        self.session.use("a launch read")
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self.session.use("a launch save")
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        self.session.use("a launch enumeration")
        return tuple(self._launches.values())


class SessionBoundStamper:
    """The graduation's catalog stamp, over the same session. The stamp is
    the work that follows the append (`design.md` Decision 2), and it is
    the thing a poisoned session breaks."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.calls: list[tuple[ProductId, object, str]] = []

    async def __call__(
        self, product_id: ProductId, stage: object, *, confirmed_by: str
    ) -> None:
        self.session.use("the catalog steady-state stamp")
        self.calls.append((product_id, stage, confirmed_by))


class FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self.playbook


# ---------------------------------------------------------------------------
# Playbook and launch fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": TRACKED_STEP,
        "name": TRACKED_STEP_NAME,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        handler="fixture.holding_check",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (*(_hold(gate) for gate in SPECIFIED_GATE_ORDER), _step())
    return LaunchPlaybook(version="journal-v1", gates=gates, steps=steps)


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": RECORDER,
        "when": RECORDED_AT,
        "evidence": "ClickUp task closed with its checklist complete",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _started(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _satisfy_gate(launch: Launch, playbook: LaunchPlaybook) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(source="automated", who="hold-filler"),
            )
    if launch.current_gate in CONFIRMATION_GATES:
        posture = Posture.SCALE if launch.current_gate == "graduated" else None
        launch.approve_gate(launch.current_gate, _approval(posture=posture))


def _walked_to(playbook: LaunchPlaybook, gate: str) -> Launch:
    launch = _started(playbook)
    while launch.current_gate != gate:
        _satisfy_gate(launch, playbook)
        launch.advance_gate(playbook)
    _satisfy_gate(launch, playbook)
    return launch


def _errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.ERROR
    ]


def _normalised(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# ---------------------------------------------------------------------------
# R6
# ---------------------------------------------------------------------------


async def test_a_failed_append_leaves_the_commands_own_work_standing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed append leaves the command's own work standing.

    WHEN a step outcome is recorded and appending its entry fails
    THEN the command reports success, and reading the launch back reports
    the outcome as recorded.

    The read-back goes through the same session the append poisoned, so
    this fails unless the containment left the session usable — the
    second half of the requirement ("SHALL NOT leave the command's
    persistence unusable for the work that follows it"), not only the
    first.
    """
    playbook = _playbook()
    session = FakeSession()
    journal = PoisonedJournal(session)
    launches = SessionBoundLaunchStore(session, _started(playbook))

    with caplog.at_level(logging.ERROR):
        events = await record_step_outcome(
            launches,
            FakePlaybooks(playbook),
            product_id=PRODUCT_ID,
            step_id=TRACKED_STEP,
            outcome=Satisfied,
            provenance=_provenance(),
            journal=journal,
        )

    # The premise: the append really was attempted, and really failed.
    assert len(journal.attempted) == 1

    # SPECIFIED: the command reports success — no exception, and its
    # returned events are unchanged by the journal's failure.
    assert [type(event).__name__ for event in events] == ["StepSatisfied"]

    # SPECIFIED: reading the launch back reports the outcome as recorded.
    stored = await launches.get_by_product_id(PRODUCT_ID)
    assert stored is not None
    progress = stored.progress_for(TRACKED_STEP)
    assert progress is not None
    assert progress.outcome is Satisfied
    assert progress.provenance.who == RECORDER


async def test_a_failed_append_does_not_prevent_the_graduation_stamp(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed append does not prevent the graduation stamp.

    WHEN an advance opens `graduated` and appending its entry fails
    THEN the advance stands persisted and the catalog product is still
    stamped steady-state with the posture the approver chose.

    This is the scenario the whole containment guarantee exists for
    (`proposal.md`; `tasks.md` 5.3): the stamp runs on the session the
    append poisoned, so catching the exception without rolling back
    leaves this red.
    """
    playbook = _playbook()
    session = FakeSession()
    journal = PoisonedJournal(session)
    launch = _walked_to(playbook, "graduated")
    launches = SessionBoundLaunchStore(session, launch)
    stamp = SessionBoundStamper(session)

    with caplog.at_level(logging.ERROR):
        await advance_gate(
            launches=launches,
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=stamp,
            product_id=PRODUCT_ID,
            journal=journal,
        )

    assert len(journal.attempted) == 1

    # SPECIFIED: the catalog product is still stamped steady-state, with
    # the posture the approver chose and the approver as confirmer.
    assert len(stamp.calls) == 1, (
        "the graduation stamp did not happen; a failed append must not "
        "leave the command unable to finish its work"
    )
    stamped_id, stamped_stage, confirmed_by = stamp.calls[0]
    assert stamped_id == PRODUCT_ID
    assert stamped_stage == SteadyState(posture=Posture.SCALE)
    assert confirmed_by == APPROVER

    # SPECIFIED: the advance stands persisted.
    stored = await launches.get_by_product_id(PRODUCT_ID)
    assert stored is not None
    assert stored.current_gate == "graduated"


async def test_a_failed_append_on_a_refused_advance_leaves_the_refusal_unchanged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed append on a refused advance leaves the refusal
    unchanged.

    WHEN an advance is refused and appending its entry fails
    THEN the command fails with the same rejection, naming the same
    unsatisfied conditions.
    """
    playbook = _playbook()
    session = FakeSession()
    journal = PoisonedJournal(session)
    launch = _started(playbook)
    launches = SessionBoundLaunchStore(session, launch)

    # The rejection with no journal in the picture, for comparison.
    with pytest.raises(GateBlockedError) as unjournaled:
        launch.advance_gate(playbook)

    with caplog.at_level(logging.ERROR), pytest.raises(GateBlockedError) as caught:
        await advance_gate(
            launches=launches,
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=SessionBoundStamper(session),
            product_id=PRODUCT_ID,
            journal=journal,
        )

    assert len(journal.attempted) == 1

    # SPECIFIED: the same rejection — not the append's failure surfacing
    # in its place, and not a different exception.
    assert caught.value.blocked.gate_id == unjournaled.value.blocked.gate_id
    # SPECIFIED: naming the same unsatisfied conditions.
    assert caught.value.blocked.unsatisfied == unjournaled.value.blocked.unsatisfied
    assert str(caught.value) == str(unjournaled.value)
    assert launch.current_gate == "commit"


async def test_a_failed_append_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed append is reported.

    WHEN appending an entry fails
    THEN the failure is reported to the application log at error
    severity, naming the launch and the occurrence that went unrecorded.
    """
    playbook = _playbook()
    session = FakeSession()
    journal = PoisonedJournal(session)

    with caplog.at_level(logging.ERROR):
        await record_step_outcome(
            SessionBoundLaunchStore(session, _started(playbook)),
            FakePlaybooks(playbook),
            product_id=PRODUCT_ID,
            step_id=TRACKED_STEP,
            outcome=Satisfied,
            provenance=_provenance(),
            journal=journal,
        )

    reported = _errors(caplog)
    # SPECIFIED: reported at error severity.
    assert reported, (
        "a failed append must be reported at error severity; the records "
        f"captured were {[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
    together = _normalised(" ".join(reported))
    # SPECIFIED: naming the launch.
    assert _normalised(PRODUCT_ID.value) in together, (
        f"the report must name the launch; it said {reported!r}"
    )
    # SPECIFIED: naming the occurrence that went unrecorded. Which words
    # identify an occurrence is not fixed, so either its kind or the
    # subject it concerned satisfies this.
    assert (
        _normalised("step-outcome-recorded") in together
        or _normalised(TRACKED_STEP) in together
    ), f"the report must name the occurrence that went unrecorded; it said {reported!r}"
