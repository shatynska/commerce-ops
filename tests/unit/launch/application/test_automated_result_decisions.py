"""Deciding a pending automated result: who may, and what each decision does.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirements, every scenario stated over *a
decision arriving*:

- *Only a known, active member may decide a pending result* — both
  scenarios.
- *Accepting records the proposed outcome and names the accepter* — both
  scenarios.
- *Rejecting does not terminate the step* — both scenarios.
- *A pending result is decided once* — its one scenario.
- *A decision on a step the playbook no longer serves is refused* — its
  one scenario.

The clause "a decision SHALL be acknowledged within Slack's timeout
independently of whether the recording it triggers has completed" is a
property of the Slack adapter rather than of the decision, and is
recorded as uncovered in `test-manifest.md` with its reason.

See `test-manifest.md` at the change root for the full accounting.

## Level

Every scenario is stated over the decision itself — what it records, what
it settles, what it refuses. The use cases over in-memory doubles are the
smallest unit that can observe those; no Slack request and no database is
needed to see any of them, and the level `tests/unit/launch/application/`
already holds for this module's other write-side rules.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- Acceptance records "exactly the outcome the handler proposed, with
  source `automated`, naming the accepting member", and rejection records
  `Blocked` "with source `automated` and the rejecting member as the
  recorder" (`tasks.md` 3.3, 3.4).
- The four pending-result states, with `voided` its own state and never a
  flavour of `rejected` (`tasks.md` 1.1; `design.md`).
- That the deciding authority is membership and activity, not
  admin authority (`design.md`, "The deciding authority is members
  membership").
- Recording and settlement in one transaction, so a failed recording
  leaves the result decidable (`tasks.md` 3.3).

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The use-case names. `_decide` probes `launch.application` for an
  accept/reject pair and for a single decide-with-a-verdict use case, and
  fails loudly rather than defaulting.
- Its call shape — collaborators plus the decided-on identity as keyword
  arguments. `_decide` is the single correction point.
- The members collaborator's read. This was INVENTED and has since been
  RESOLVED: `_FakeMembers` once answered under every spelling this
  repository's members doubles use (`list_members`, `members`, `member`, a
  bare call), so that whichever shape the implementation picked was
  already satisfied. That was the right call while the shape was
  unstated — and the wrong one afterwards, because a double answering
  to everything cannot fail the way production failed. Production
  supplied a `load()`/`save()` store, matching none of the spellings,
  and every decision was refused as "the membership does not know that
  Slack identity". The double now answers `list_members` and nothing
  else, which is the one stated shape (`restore-automated-decisions`,
  design.md — Decision 5). No assertion here changed.
- How a refusal is *signalled*. The spec says a refused decision "SHALL
  tell the decider it was refused"; telling the decider is `tasks.md`
  6.4's Slack reply, and what the use case hands back for it is
  unstated. `_refusal_of` accepts either a raised error or a returned
  value that reads as refused — and every test additionally asserts the
  unambiguous half, which is what did *not* happen.

What must survive any correction is what each test asserts: which
decisions are refused, what is recorded, what the pending row becomes,
and — for the several rules stated in the negative — what is not
recorded.

## Expected first-run state

Neither use case exists (`tasks.md` 3.3–3.7), so every test here is
expected to fail on an absent target. Per `ai-toolkit:testing`, that
establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Hazard,
    LaunchPlaybook,
    NotApplicable,
    Refused,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
    permissible_terminal_outcomes,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeMembers
from tests.support.fixtures import (
    ALICE,
    ALICE_NAME,
    BOHDAN,
    HANDLER_NAME,
    LAUNCH_DATE,
    STEP_ID,
    product_id,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import MemberValue as _Member
from tests.support.values import PendingRow as _PendingRow

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
ALICE_SLACK: Final = "U01ALICE"
BOHDAN_SLACK: Final = "U02BOHDAN"
BOHDAN_NAME: Final = "Bohdan Retired"

STRANGER_SLACK: Final = "U99STRANGER"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home Decor, which "
    "carries no food-contact obligation."
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


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
        assignees=(ALICE,),
    )


def _playbook(step: StepDefinition | None = None) -> LaunchPlaybook:
    subject = step if step is not None else _step()
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(subject, *fillers))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeMembers(FakeMembers):
    def __init__(self, *members: Any) -> None:
        super().__init__(members)


def _members() -> _FakeMembers:
    """Alice is known and active; Bohdan is known and inactive; the
    stranger is on neither list."""
    return _FakeMembers(
        _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK),
        _Member(
            id=BOHDAN,
            display_name=BOHDAN_NAME,
            slack_identity=BOHDAN_SLACK,
            active=False,
        ),
    )


class _FakeResults:
    """In-memory stand-in for `AutomatedResultRepository` (`tasks.md` 1.4)."""

    def __init__(self, *rows: _PendingRow) -> None:
        self.rows: list[_PendingRow] = list(rows)

    async def pending_for(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        for row in self.rows:
            if (
                row.product_id == product_id
                and row.step_id == step_id
                and row.state == "pending"
            ):
                return row
        return None

    async def settle(
        self,
        row: object,
        *,
        state: str,
        decided_by: str,
        decided_at: datetime,
    ) -> None:
        target = self._row_of(row)
        target.state = state
        target.decided_by = decided_by
        target.decided_at = decided_at

    async def void(self, row: object) -> None:
        self._row_of(row).state = "voided"

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        rejected = [
            row
            for row in self.rows
            if row.product_id == product_id
            and row.step_id == step_id
            and row.state == "rejected"
        ]
        return rejected[-1] if rejected else None

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        for candidate in self.rows:
            if candidate is row:
                return candidate
        raise AssertionError(f"unknown pending row {row!r}")

    @property
    def only(self) -> _PendingRow:
        assert len(self.rows) == 1
        return self.rows[0]


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self._launch = launch

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launch if product_id == self._launch.product_id else None

    async def list_active(self) -> list[Launch]:
        return [self._launch]


class _RecordingOutcomes:
    def __init__(self, *, failing: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        if self.failing:
            raise RuntimeError("simulated recording failure")
        self.calls.append(kwargs)
        return ()

    @property
    def only(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected one recording, got {self.calls}"
        return self.calls[0]


def _pending(**overrides: Any) -> _PendingRow:
    attributes: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "handler": HANDLER_NAME,
        "proposed_outcome": Satisfied,
        "result_text": RECOMMENDATION,
        "produced_at": PRODUCED_AT,
        "delivered_at": PRODUCED_AT + timedelta(seconds=2),
    }
    attributes.update(overrides)
    return _PendingRow(**attributes)


@dataclass
class _Collaborators:
    results: _FakeResults
    members: _FakeMembers
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    recorder: _RecordingOutcomes


def _setup(
    *,
    step: StepDefinition | None = None,
    served_step: StepDefinition | None = None,
    row: _PendingRow | None = None,
    failing_recorder: bool = False,
) -> _Collaborators:
    """The launch is started against a playbook that defines the step;
    `served_step` is what the playbook now serves, which is how a step
    leaving `active` is expressed at this level."""
    started_against = _playbook(step)
    launch = _launch(started_against)
    served = _playbook(served_step) if served_step is not None else started_against
    return _Collaborators(
        results=_FakeResults(row if row is not None else _pending()),
        members=_members(),
        launches=_FakeLaunches(launch),
        playbook=served,
        recorder=_RecordingOutcomes(failing=failing_recorder),
    )


# ---------------------------------------------------------------------------
# The decision, reached through one correction point
# ---------------------------------------------------------------------------

_ACCEPT_NAMES: Final = (
    "accept_automated_result",
    "accept_pending_result",
    "accept_result",
)
_REJECT_NAMES: Final = (
    "reject_automated_result",
    "reject_pending_result",
    "reject_result",
)
_DECIDE_NAMES: Final = ("decide_automated_result", "decide_pending_result")


def _exported(names: tuple[str, ...]) -> Any | None:
    for name in names:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    return None


async def _decide(
    collaborators: _Collaborators,
    *,
    accept: bool,
    slack_identity: str = ALICE_SLACK,
    when: datetime = DECIDED_AT,
) -> Any:
    """INVENTED call shape — the single correction point."""
    supplied: dict[str, Any] = {
        "results": collaborators.results,
        "members": collaborators.members,
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "record_outcome": collaborators.recorder,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": slack_identity,
        "when": when,
    }

    use_case = _exported(_ACCEPT_NAMES if accept else _REJECT_NAMES)
    if use_case is None:
        use_case = _exported(_DECIDE_NAMES)
        if use_case is None:
            pytest.fail(
                "no decision use case is exported from "
                "`commerce_ops.launch.application` under any of "
                f"{_ACCEPT_NAMES + _REJECT_NAMES + _DECIDE_NAMES} — correct "
                "this file's probe to the implemented names"
            )
        supplied["accept"] = accept

    accepted = set(inspect.signature(use_case).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the decision use case does not accept {unknown}; correct `_decide` "
        "to the implemented collaborator names"
    )
    return await use_case(**supplied)


@dataclass
class _Refusal:
    raised: BaseException | None
    returned: Any


async def _decide_expecting_refusal(
    collaborators: _Collaborators, **kwargs: Any
) -> _Refusal:
    try:
        returned = await _decide(collaborators, **kwargs)
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001 -- the refusal signal is unfixed
        return _Refusal(raised=error, returned=None)
    return _Refusal(raised=None, returned=returned)


def _says_refused(refusal: _Refusal) -> bool:
    """Whether *something* said the decision was refused.

    The spec requires the decider be told; what the use case hands the
    Slack reply is unstated (see the module docstring), so this accepts a
    raised error or a returned value that reads as a refusal.
    """
    if refusal.raised is not None:
        return True
    returned = refusal.returned
    if returned is None or returned is False:
        return False
    for attribute in ("refused", "rejected_decision", "is_refused"):
        if getattr(returned, attribute, None) is True:
            return True
    for attribute in ("accepted", "recorded", "settled", "ok"):
        if getattr(returned, attribute, None) is False:
            return True
    return "refus" in str(returned).lower()


# ---------------------------------------------------------------------------
# Requirement: Only a known, active member may decide a pending result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_an_unknown_identity_cannot_decide(accept: bool) -> None:
    """Scenario: An unknown identity cannot decide.

    WHEN a decision arrives from a Slack identity the membership does not
    know
    THEN it is refused, no outcome is recorded, the pending result still
    stands, and the decider is told.

    Both verdicts are exercised: the rule is about who may decide, not
    about which decision, and rejection takes a different recording path
    that could plausibly skip the check.
    """
    collaborators = _setup()

    refusal = await _decide_expecting_refusal(
        collaborators, accept=accept, slack_identity=STRANGER_SLACK
    )

    # SPECIFIED: no outcome is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the pending result still stands.
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None
    # SPECIFIED: the decider is told it was refused.
    assert _says_refused(refusal), (
        "an unknown identity's decision was neither refused loudly nor "
        "answered with anything that reads as a refusal"
    )


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_deactivated_member_cannot_decide(accept: bool) -> None:
    """Scenario: A deactivated member cannot decide.

    WHEN a decision arrives from a Slack identity belonging to a member
    the membership holds as inactive
    THEN it is refused, no outcome is recorded, and the pending result
    still stands.

    Separate from the unknown-identity case because "known" and "active"
    are two facts, and an implementation resolving the member and then
    forgetting to read `active` passes the test above and fails here.
    """
    collaborators = _setup()

    refusal = await _decide_expecting_refusal(
        collaborators, accept=accept, slack_identity=BOHDAN_SLACK
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert _says_refused(refusal)


# ---------------------------------------------------------------------------
# Requirement: Accepting records the proposed outcome and names the accepter
# ---------------------------------------------------------------------------


async def test_an_accepted_result_becomes_the_steps_outcome() -> None:
    """Scenario: An accepted result becomes the step's outcome.

    WHEN a known active member accepts a pending result proposing
    `Satisfied`
    THEN `Satisfied` is recorded for that step with source `automated`,
    naming the accepter and the moment of the decision, with evidence
    naming the handler and carrying the produced text.
    """
    collaborators = _setup()

    await _decide(collaborators, accept=True)

    call = collaborators.recorder.only
    # SPECIFIED: exactly the outcome the handler proposed.
    assert call["outcome"] is Satisfied
    assert call["step_id"] == STEP_ID

    provenance = call["provenance"]
    # SPECIFIED: source stays `automated` — the work was the handler's.
    assert provenance.source == "automated"
    # SPECIFIED: the accepter is who the recorder names.
    assert ALICE in str(provenance.who) or ALICE_NAME in str(provenance.who)
    # SPECIFIED: the moment of the decision, not of the production.
    assert provenance.when == DECIDED_AT
    # SPECIFIED: evidence names both the handler and the produced text,
    # so the launch's own record answers what produced the result
    # without the pending-result store still holding the row.
    evidence = str(provenance.evidence)
    assert HANDLER_NAME in evidence
    assert RECOMMENDATION in evidence


async def test_an_accepted_result_is_settled_and_no_longer_suppresses() -> None:
    """Requirement statement: "The pending result SHALL then be settled
    and SHALL no longer suppress re-invocation."

    SPECIFIED, stated in the requirement rather than in a scenario. The
    suppression half is what the pass reads (*A pending result suppresses
    re-invocation*), so a row left `pending` after acceptance would park
    the step forever.
    """
    collaborators = _setup()

    await _decide(collaborators, accept=True)

    row = collaborators.results.only
    assert row.state != "pending"
    assert row.decided_by is not None
    assert await collaborators.results.pending_for(PRODUCT_ID, STEP_ID) is None


async def test_a_failed_recording_leaves_the_result_decidable() -> None:
    """Scenario: A failed recording leaves the result decidable.

    WHEN recording the outcome for an accepted pending result fails
    THEN the pending result is not settled and the decision can be made
    again.

    "The recording and the settlement SHALL both take effect, or
    neither: a settled result whose outcome was never recorded would be
    undecidable and unrecoverable."
    """
    collaborators = _setup(failing_recorder=True)

    await _decide_expecting_refusal(collaborators, accept=True)

    # SPECIFIED: not settled.
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None

    # SPECIFIED: the decision can be made again — and now succeeds.
    collaborators.recorder.failing = False
    await _decide(collaborators, accept=True)

    assert collaborators.recorder.only["outcome"] is Satisfied
    assert collaborators.results.only.state != "pending"


# ---------------------------------------------------------------------------
# Requirement: Rejecting does not terminate the step
# ---------------------------------------------------------------------------


async def test_a_rejected_result_leaves_the_step_live() -> None:
    """Scenario: A rejected result leaves the step live.

    WHEN a known active member rejects a pending result
    THEN a `Blocked` outcome is recorded whose reason names the
    rejecter, with source `automated` and the rejecter as recorder, and
    the step is not at a terminal outcome.
    """
    collaborators = _setup()

    await _decide(collaborators, accept=False)

    call = collaborators.recorder.only
    outcome = call["outcome"]
    # SPECIFIED: a `Blocked` outcome, whose reason names the rejecter and
    # states that an automated result was rejected.
    assert isinstance(outcome, Blocked)
    assert ALICE in outcome.reason or ALICE_NAME in outcome.reason
    assert "reject" in outcome.reason.lower()
    # SPECIFIED: source `automated`, the rejecter as recorder.
    assert call["provenance"].source == "automated"
    assert ALICE in str(call["provenance"].who) or ALICE_NAME in str(
        call["provenance"].who
    )
    # SPECIFIED: the step is not at a terminal outcome — `Blocked` is
    # not among the outcomes this step's hazard permits as terminal, so
    # recording it leaves the step live for a later pass.
    assert Blocked not in permissible_terminal_outcomes(Hazard.NONE)


async def test_a_rejected_result_is_settled_as_rejected_not_voided() -> None:
    """Requirement statement: "It SHALL settle the pending result as
    rejected, and SHALL leave the step available for a handler to resolve
    again on a later pass."

    SPECIFIED, and load-bearing beyond bookkeeping: `design.md` makes the
    cool-off key on "most recent settled result was **rejected**", and
    only a row settled as rejected triggers it.
    """
    collaborators = _setup()

    await _decide(collaborators, accept=False)

    row = collaborators.results.only
    assert row.state == "rejected"
    assert row.decided_by is not None
    assert row.decided_at == DECIDED_AT


async def test_rejection_is_never_a_refusal() -> None:
    """Scenario: Rejection is never a refusal.

    WHEN a pending result for a step whose hazard is not
    `prohibited-tactic` is rejected
    THEN the recorded outcome is not `Refused` and is not
    `NotApplicable`.

    Both exclusions matter for different reasons the requirement states:
    `Refused` is reserved for a recognised-and-declined tactic, and
    `NotApplicable` is terminal and would close a step whose work still
    stands.
    """
    collaborators = _setup(step=_step(hazard=Hazard.COMPLIANCE_OBLIGATION))

    await _decide(collaborators, accept=False)

    outcome = collaborators.recorder.only["outcome"]
    assert outcome is not Refused
    assert not isinstance(outcome, NotApplicable)


# ---------------------------------------------------------------------------
# Requirement: A pending result is decided once
# ---------------------------------------------------------------------------


async def test_a_repeated_decision_changes_nothing() -> None:
    """Scenario: A repeated decision changes nothing.

    WHEN a decision arrives for a pending result that has already been
    settled
    THEN it is refused, no further outcome is recorded, and the outcome
    recorded by the first decision stands.

    The second decision is the opposite verdict, which is the case the
    requirement's own reasoning names: "a second decision that recorded a
    second outcome would let a rejection silently overwrite an
    acceptance."
    """
    collaborators = _setup()

    await _decide(collaborators, accept=True)
    first = collaborators.recorder.only

    refusal = await _decide_expecting_refusal(collaborators, accept=False)

    # SPECIFIED: no further outcome is recorded.
    assert len(collaborators.recorder.calls) == 1
    # SPECIFIED: the outcome the first decision recorded stands.
    assert collaborators.recorder.calls[0] is first
    assert collaborators.results.only.state == "accepted"
    # SPECIFIED: the repeat is refused.
    assert _says_refused(refusal)


# ---------------------------------------------------------------------------
# Requirement: A decision on a step the playbook no longer serves is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_decision_on_a_de_activated_step_is_refused_and_the_result_voided(
    accept: bool,
) -> None:
    """Scenario: A decision on a de-activated step is refused and the
    result voided.

    WHEN a decision arrives for a pending result whose step has since
    been moved out of `active`
    THEN it is refused, no outcome is recorded, the pending result is
    voided, and the decider is told why.

    `voided`, not `rejected`: `design.md` makes the distinction
    load-bearing — folding it into `rejected` would misrecord a refused
    decision as that member's rejection and park the step for the whole
    cool-off after it returned to the served set.
    """
    collaborators = _setup(served_step=_step(status=StepStatus.IN_DEVELOPMENT))

    refusal = await _decide_expecting_refusal(collaborators, accept=accept)

    # SPECIFIED: no outcome is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the pending result is voided rather than left standing.
    row = collaborators.results.only
    assert row.state == "voided"
    assert await collaborators.results.pending_for(PRODUCT_ID, STEP_ID) is None
    # SPECIFIED: and it is not a rejection, so the cool-off is untouched.
    assert await collaborators.results.latest_rejection(PRODUCT_ID, STEP_ID) is None
    # SPECIFIED: the decider is told why.
    assert _says_refused(refusal)


async def test_a_decision_on_a_retired_step_is_refused_and_the_result_voided() -> None:
    """Requirement statement: "the step having been retired, **or** moved
    out of `active`, since the result was produced".

    The scenario names only the de-activation route. Retirement is the
    other route the statement names, and it is a different write in
    `playbook-authoring`, so an implementation keying on one need not
    handle the other.
    """
    collaborators = _setup(served_step=_step(status=StepStatus.RETIRED))

    refusal = await _decide_expecting_refusal(collaborators, accept=True)

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "voided"
    assert _says_refused(refusal)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - "a decision SHALL be acknowledged within Slack's timeout
#   independently of whether the recording it triggers has completed".
#   That is a property of the Slack adapter's acknowledgement, already
#   required and tested for this app's other listener
#   (`tests/unit/launch/infrastructure/driving/
#   test_slack_entry_ack_and_failure_visibility.py`), and it is
#   unobservable at the use-case level this file works at.
# - That decisions arrive on the verified `product_agent` surface. The
#   verification itself is `slack-trigger`'s requirement and is covered
#   by `tests/unit/launch/infrastructure/driving/
#   test_slack_entry_request_verification.py`; this delta adds no
#   scenario about it.
# ---------------------------------------------------------------------------
