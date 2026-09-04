"""Deciding a gate: who may, what is recorded, and what is refused.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers, from the ADDED requirements:

- *Only a known, active member may approve a gate* — all five scenarios.
- *A decision records the approval and reports what it did* — the
  scenarios in the half a decision itself can observe: *An approving
  decision opens the gate and says so* (its recording half), *A rejecting
  decision keeps the gate closed*, *A decision arriving during a
  stand-down is refused*, *A decision on a condition that has since
  regressed reports why* (its recording half), *A decision naming the
  final gate is refused*, and *A decision on a gate the launch has left is
  refused*.

The three scenarios of that requirement stated over the Slack exchange —
*A decision whose gate the pass crossed first still reports it opened*, *A
decision is acknowledged before its work completes*, and *A decision and
the pass do not cross the same gate twice* — are not observable here: the
advance runs from the adapter and the lock is the adapter's
(`design.md` — Decision 6). They are in
`tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`
and `tests/integration/launch/test_gate_progression_atomicity_live.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The use case over in-memory doubles. Every scenario here is stated over
the decision itself — what it records, what it refuses, what it leaves
standing — and no Slack request and no database is needed to see any of
them. It is the level
`tests/unit/launch/application/test_automated_result_decisions.py` already
holds for this module's other decision.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts and by this module's existing surface:

- Membership **and** activity as the deciding authority, with
  `admin` explicitly not required (`design.md` — Decision 7; delta R6).
- The members collaborator's one stated shape — it must answer who the
  members carries, deactivated entries included (`tasks.md` 3.8; delta R6).
  `MembersReader` and `UnreadableMembersError` are already exported from
  `commerce_ops.launch.application`, so this file pins them rather than
  probing.
- That the wiring refusal is **raised**, is the same type for an absent
  collaborator as for an unreadable one, and is raised *before* the
  deciding identity is judged (`tasks.md` 3.9; delta R6).
- `Decision(refused, reason)` as the return shape (`tasks.md` 3.7,
  "modelled on `automated_decisions.py`'s `Decision` return shape rather
  than raising").
- The refusals a decision meets on grounds independent of the membership: the
  final gate, a gate that is no longer current, and a stand-down (delta
  R7).

INVENTED, each recorded in `test-manifest.md` with its correction point:

- The use case's exported name and call shape. `_decide` probes an
  approve/reject pair and a single decide-with-a-verdict, and fails loudly
  rather than defaulting; it is the single correction point.
- Which form of the member is written into `GateApproval.approver`
  — an identifier or a display name. `_names_the_member` accepts either,
  since the requirement fixes only that it is the member the membership
  resolved and never one the system supplied.
- The wording by which a refusal blames the decider's identity
  (`_BLAMES_UNKNOWN`, `_BLAMES_INACTIVE`). Neither is asserted blind: the
  unknown-identity test establishes that a genuine unknown refusal matches
  `_BLAMES_UNKNOWN`, which is what stops the inactive test's negative
  assertion from passing vacuously.

## Expected first-run state

No gate-decision use case exists (`tasks.md` 3.7), so every test here is
expected to fail on an absent target — `_decide`'s loud failure. Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import UnreadableMembersError
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
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
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.fixtures import ALICE, BOHDAN, product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.values import MemberValue as _Member

pytestmark = pytest.mark.anyio

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

PRODUCT_ID: Final = product_id()

ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Ordinary"

BOHDAN_SLACK: Final = "U02BOHDAN"
BOHDAN_NAME: Final = "Bohdan Retired"

STRANGER_SLACK: Final = "U99STRANGER"

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 5, 3, 10, 0, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

UNHELD_GATE: Final = "ignition"

#: Wording by which a refusal blames the decider's identity (INVENTED).
#: `test_an_unknown_identity_cannot_approve` establishes that a genuine
#: unknown refusal matches one of these, so the negative assertion in the
#: inactive test cannot pass vacuously.
_BLAMES_UNKNOWN: Final = (
    "does not know",
    "doesn't know",
    "not on the membership",
    "unknown",
    "unrecognised",
    "unrecognized",
    "no such member",
    "not known",
)

#: Wording by which a refusal names inactivity as the fact that refused
#: them (INVENTED).
_BLAMES_INACTIVE: Final = (
    "inactive",
    "not active",
    "no longer active",
    "deactivated",
)

#: What the message of a wiring refusal must identify (INVENTED reading of
#: "identifying what was supplied and what was expected"): the shape the
#: collaborator was expected to answer.
_EXPECTED_SHAPE_NAMES: Final = ("list_members", "MembersReader", "members reader")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    return _build_hold(
        gate,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=0),
        **overrides,
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        version="progression-v1",
        filler=_hold,
    )


def _unready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="progression-v1",
        gates=_gates(),
        steps=tuple(
            _hold(
                gate,
                status=StepStatus.DRAFT if gate == UNHELD_GATE else StepStatus.ACTIVE,
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
    )


def _provenance() -> Provenance:
    return Provenance(
        source="automated",
        who="hold-filler",
        when=NOW,
        evidence="the blocking check reported green",
    )


def _satisfy_everything(launch: Launch, playbook: LaunchPlaybook) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )
    if launch.current_gate in CONFIRMATION_GATES:
        launch.approve_gate(
            launch.current_gate,
            GateApproval(
                decision=ApprovalDecision.APPROVING,
                approver="Helen",
                when=NOW,
                posture=Posture.SCALE if launch.current_gate == FINAL_GATE else None,
            ),
        )


def _launch_at(gate: str, playbook: LaunchPlaybook, *, satisfy: bool = True) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != gate:
        _satisfy_everything(launch, playbook)
        launch.advance_gate(playbook)
    if satisfy:
        for step in playbook.steps_for_gate(gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(),
                )
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _ReaderMembers:
    """Answers `list_members` and nothing else — the one stated shape.

    Deliberately narrow, for the reason `restore-automated-decisions`
    records at the sibling call site: a double answering every plausible
    spelling is satisfied by a caller reaching for any of them, and so
    cannot tell a correctly wired deployment from the mis-wired one that
    shipped.
    """

    def __init__(self, *members: _Member) -> None:
        self._members = list(members)
        self.reads = 0

    async def list_members(self) -> tuple[_Member, ...]:
        self.reads += 1
        return tuple(self._members)


class _StoreShapedMembers:
    """The collaborator production once supplied by mistake: a store, not
    a reader. It cannot answer who the membership carries."""

    async def load(self) -> Any:
        raise AssertionError("the store was read; the decision should not reach it")

    async def save(self, members: Any) -> None:
        raise AssertionError("the store was written; nothing here writes a membership")


def _members() -> _ReaderMembers:
    """Alice is known, active and **not** an administrator; Bohdan is known
    and inactive; the stranger is on neither list.

    Alice carries `admin=False` deliberately: `design.md` — Decision 7
    refuses to make gate approval an act of system administration, so the
    ordinary case in this file is an ordinary member.
    """
    return _ReaderMembers(
        _Member(
            id=ALICE,
            display_name=ALICE_NAME,
            slack_identity=ALICE_SLACK,
            admin=False,
        ),
        _Member(
            id=BOHDAN,
            display_name=BOHDAN_NAME,
            slack_identity=BOHDAN_SLACK,
            active=False,
        ),
    )


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self._launches = {launch.product_id: launch}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_active(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    @property
    def only(self) -> Launch:
        return next(iter(self._launches.values()))


class _FakePlaybooks:
    def __init__(
        self, playbook: LaunchPlaybook, refusal: Exception | None = None
    ) -> None:
        self.playbook = playbook
        self.refusal = refusal

    async def get(self, version: str = "") -> LaunchPlaybook:
        if self.refusal is not None:
            raise self.refusal
        return self.playbook


class _FakeJournal:
    def __init__(self) -> None:
        self.appended: list[Any] = []
        self.rollbacks = 0

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        self.rollbacks += 1


class _FakeSuppression:
    """The ask cool-off store the decision use case also holds
    (`tasks.md` 3.11), so a rejection can refresh the record."""

    def __init__(self, *, failing: bool = False) -> None:
        self.writes: list[tuple[ProductId, str, str]] = []
        self.failing = failing

    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    get = read
    latest = read
    last_for = read

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        if self.failing:
            raise RuntimeError("simulated cool-off refresh failure")
        self.writes.append((PRODUCT_ID, "?", "rejection"))

    refresh = record_rejection
    note_rejection = record_rejection
    record = record_rejection
    record_delivery = record_rejection


class _Collaborators:
    def __init__(
        self,
        launch: Launch,
        playbook: LaunchPlaybook,
        *,
        members: Any,
        refusal: Exception | None = None,
        suppression: _FakeSuppression | None = None,
    ) -> None:
        self.playbook = playbook
        self.playbooks = _FakePlaybooks(playbook, refusal)
        self.launches = _FakeLaunches(launch)
        self.journal = _FakeJournal()
        self.members = members
        self.suppression = suppression or _FakeSuppression()


def _setup(
    gate: str = "commit",
    *,
    satisfy: bool = True,
    members: Any | None = None,
    unready: bool = False,
    suppression: _FakeSuppression | None = None,
) -> _Collaborators:
    playbook = _playbook()
    launch = _launch_at(gate, playbook, satisfy=satisfy)
    refusal: Exception | None = None
    if unready:
        from commerce_ops.launch.domain import launch_playbook as playbook_module

        error = getattr(playbook_module, "PlaybookNotReadyError", None)
        if error is None:
            pytest.fail(
                "commerce_ops.launch.domain.launch_playbook exports no "
                "`PlaybookNotReadyError`, so a stand-down cannot be provoked"
            )
        for args, kwargs in (
            ((), {"playbook": _unready_playbook(), "gates": (UNHELD_GATE,)}),
            ((), {"playbook": _unready_playbook(), "unheld_gates": (UNHELD_GATE,)}),
            (((UNHELD_GATE,), _unready_playbook()), {}),
            ((_unready_playbook(), (UNHELD_GATE,)), {}),
        ):
            try:
                refusal = error(*args, **kwargs)
                break
            except TypeError:
                continue
        if refusal is None:
            pytest.fail(
                "could not construct PlaybookNotReadyError under any probed "
                "signature; correct `_setup` to the implemented one"
            )
    return _Collaborators(
        launch,
        playbook,
        members=_members() if members is None else members,
        refusal=refusal,
        suppression=suppression,
    )


# ---------------------------------------------------------------------------
# The decision, reached through one correction point
# ---------------------------------------------------------------------------

_APPROVE_NAMES: Final = (
    "approve_gate_decision",
    "accept_gate_decision",
    "approve_launch_gate",
)
_REJECT_NAMES: Final = (
    "reject_gate_decision",
    "decline_gate_decision",
    "reject_launch_gate",
)
_DECIDE_NAMES: Final = ("decide_gate", "record_gate_decision", "decide_launch_gate")

_SENTINEL: Final = object()


def _exported(names: tuple[str, ...]) -> Any | None:
    for name in names:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    return None


async def _decide(
    collaborators: _Collaborators,
    *,
    approve: bool = True,
    slack_identity: str = ALICE_SLACK,
    gate_id: str = "commit",
    members: Any = _SENTINEL,
) -> Any:
    """INVENTED call shape — the single correction point."""
    use_case = _exported(_APPROVE_NAMES if approve else _REJECT_NAMES)
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbooks": collaborators.playbooks,
        "playbook": collaborators.playbook,
        "journal": collaborators.journal,
        "members": collaborators.members if members is _SENTINEL else members,
        "read_members": collaborators.members if members is _SENTINEL else members,
        "suppression": collaborators.suppression,
        "product_id": PRODUCT_ID,
        "gate_id": gate_id,
        "slack_identity": slack_identity,
        "when": DECIDED_AT,
    }
    if use_case is None:
        use_case = _exported(_DECIDE_NAMES)
        if use_case is None:
            pytest.fail(
                "no gate-decision use case is exported from "
                "`commerce_ops.launch.application` under any of "
                f"{_APPROVE_NAMES + _REJECT_NAMES + _DECIDE_NAMES} — correct "
                "this file's probe to the implemented names (`tasks.md` 3.7)"
            )
        supplied["approve"] = approve
        supplied["approving"] = approve
    accepted = set(inspect.signature(use_case).parameters)
    assert accepted & {"members", "read_members"}, (
        "the gate-decision use case takes no members collaborator "
        f"({sorted(accepted)}); delta R6 requires the membership be supplied by "
        "the caller. Correct `_decide` to the implemented parameter name"
    )
    assert "gate_id" in accepted, (
        "the gate-decision use case takes no gate identifier "
        f"({sorted(accepted)}); a decision names the gate it was asked "
        "about (`design.md` — Decision 9)"
    )
    return await use_case(**{k: v for k, v in supplied.items() if k in accepted})


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
    if refusal.raised is not None:
        return True
    returned = refusal.returned
    if returned is None or returned is False:
        return False
    if getattr(returned, "refused", None) is True:
        return True
    if getattr(returned, "accepted", None) is False:
        return True
    return "refus" in str(returned).lower()


def _reason(refusal: _Refusal) -> str:
    parts: list[str] = []
    if refusal.raised is not None:
        parts.append(str(refusal.raised))
    if refusal.returned is not None:
        parts.append(str(getattr(refusal.returned, "reason", "")))
        parts.append(str(refusal.returned))
    return " ".join(parts).lower()


def _matches(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _approval_of(collaborators: _Collaborators, gate: str) -> GateApproval | None:
    return collaborators.launches.only.approval_for(gate)


def _names_the_member(approval: GateApproval, member: _Member) -> bool:
    """Whether the approval names the member.

    Either form counts — the identifier or the display name — because the
    requirement fixes only that the approver is the member the membership
    resolved and is never supplied by the system.
    """
    approver = str(approval.approver)
    return member.id in approver or member.display_name in approver


# ---------------------------------------------------------------------------
# Requirement: Only a known, active member may approve a gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("approve", [True, False], ids=["approving", "rejecting"])
async def test_an_unknown_identity_cannot_approve(approve: bool) -> None:
    """Scenario: An unknown identity cannot approve.

    WHEN a gate decision arrives from a Slack identity the membership does not
    know
    THEN it is refused, no approval is recorded, the gate is unchanged, and
    the decider is told.

    Both verdicts are exercised: the rule is about who may decide, not
    which decision, and the rejecting path takes a different route that
    could plausibly skip the check.

    This test also establishes the premise the *inactive* test's negative
    assertion depends on — that a genuine unknown refusal really does match
    `_BLAMES_UNKNOWN`.
    """
    collaborators = _setup()

    refusal = await _decide_expecting_refusal(
        collaborators, approve=approve, slack_identity=STRANGER_SLACK
    )

    # SPECIFIED: it is refused, and the decider is told.
    assert _says_refused(refusal), (
        "an unknown identity's decision was neither refused loudly nor "
        "answered with anything that reads as a refusal"
    )
    # SPECIFIED: no approval is recorded.
    assert _approval_of(collaborators, "commit") is None, (
        "an approval was recorded for a decision from an identity the membership "
        "does not know"
    )
    # SPECIFIED: the gate is unchanged.
    assert collaborators.launches.only.current_gate == "commit"
    # Premise for the inactive test below, asserted here so it cannot pass
    # vacuously there: this refusal blames the identity as unknown.
    assert _matches(_reason(refusal), _BLAMES_UNKNOWN), (
        "an unknown identity's refusal matched none of the wordings this "
        f"file reads as blaming the identity: {_reason(refusal)!r}; correct "
        "`_BLAMES_UNKNOWN` to the implemented wording"
    )


@pytest.mark.parametrize("approve", [True, False], ids=["approving", "rejecting"])
async def test_a_deactivated_member_cannot_approve_and_is_told_which_fact(
    approve: bool,
) -> None:
    """Scenario: A deactivated member cannot approve, and is told which fact
    refused them.

    WHEN a gate decision arrives from a Slack identity belonging to a
    member the membership holds as inactive
    THEN it is refused as inactive rather than as unknown, no approval is
    recorded, and the gate is unchanged.

    Separate from the unknown-identity case because "known" and "active"
    are two facts: an implementation that resolved the member and then
    forgot to read `active` passes the test above and fails here, and one
    that answered "the membership does not know you" would tell a colleague
    something false about their own record.
    """
    collaborators = _setup()

    refusal = await _decide_expecting_refusal(
        collaborators, approve=approve, slack_identity=BOHDAN_SLACK
    )

    # SPECIFIED: it is refused.
    assert _says_refused(refusal)
    # SPECIFIED: no approval is recorded, and the gate is unchanged.
    assert _approval_of(collaborators, "commit") is None
    assert collaborators.launches.only.current_gate == "commit"
    # SPECIFIED: refused *as inactive*...
    reason = _reason(refusal)
    assert _matches(reason, _BLAMES_INACTIVE), (
        "a deactivated member's refusal did not name inactivity as the fact "
        f"that refused them: {reason!r}"
    )
    # ...rather than as unknown.
    assert not _matches(reason, _BLAMES_UNKNOWN), (
        "a deactivated member was told the membership does not know them, which "
        f"is false about their own record: {reason!r}"
    )


async def test_a_non_administrator_may_approve() -> None:
    """Scenario: A non-administrator may approve.

    WHEN a gate decision arrives from a Slack identity belonging to an
    active member the membership does not mark as an administrator
    THEN the approval is recorded naming that member.

    Alice carries `admin=False`. `design.md` — Decision 7 refuses to make
    gate approval an act of system administration, so this is the ordinary
    case rather than an exception.
    """
    collaborators = _setup()

    await _decide(collaborators, approve=True)

    approval = _approval_of(collaborators, "commit")
    # SPECIFIED: the approval is recorded...
    assert approval is not None, (
        "no approval was recorded for an active, known, non-administrator "
        "member's approving decision"
    )
    assert approval.decision is ApprovalDecision.APPROVING
    # SPECIFIED: ...naming that member. "no approver is ever supplied by
    # the system itself" is what this rules out.
    alice = _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
    assert _names_the_member(approval, alice), (
        "the recorded approval does not name the member the membership "
        f"resolved; its approver is {approval.approver!r}"
    )


async def test_an_absent_members_collaborator_is_refused_the_same_way() -> None:
    """Scenario: An absent members collaborator is refused the same way, not
    silently.

    WHEN a gate decision is judged with no members collaborator supplied at
    all
    THEN it is refused as the same wiring fault, by a named error, and not
    reported to the decider as a fact about their identity.

    "The same wiring fault" is asserted as the same **type** the unreadable
    collaborator raises, rather than against a spelling, so this survives
    the class being named differently than `tasks.md` says.
    """
    collaborators = _setup()

    absent = await _decide_expecting_refusal(collaborators, members=None)
    unreadable = await _decide_expecting_refusal(_setup(members=_StoreShapedMembers()))

    # SPECIFIED: by a named error — raised, not returned as a decision
    # refusal.
    assert absent.raised is not None, (
        "an absent members collaborator was answered as a decision refusal "
        f"rather than raised as a wiring fault: {absent.returned!r}"
    )
    # SPECIFIED: the *same* fault as an unreadable collaborator.
    assert unreadable.raised is not None
    assert type(absent.raised) is type(unreadable.raised), (
        "the two wiring faults raise different types, so one catch cannot "
        f"handle both: {type(absent.raised)} vs {type(unreadable.raised)}"
    )
    # SPECIFIED: not reported to the decider as a fact about their identity.
    assert not _matches(_reason(absent), _BLAMES_UNKNOWN), (
        "a mis-wiring was reported as though the membership did not carry the "
        f"decider: {_reason(absent)!r}"
    )
    # SPECIFIED: no approval is recorded.
    assert _approval_of(collaborators, "commit") is None


async def test_an_unreadable_members_collaborator_is_refused_by_name() -> None:
    """Scenario: An unreadable members collaborator is refused by name.

    WHEN a gate decision is judged against a members collaborator that
    cannot answer who the membership carries
    THEN it is refused with a named error identifying the collaborator
    supplied and the shape expected, no approval is recorded, and the
    decider is told their decision was not processed without being told
    anything about their own members entry.

    The type is pinned here — `UnreadableMembersError`, already exported
    from `commerce_ops.launch.application` — because an infrastructure
    adapter must catch it by type to answer the decider without implicating
    their members entry (`tasks.md` 5.7), and it can reach it no other way.
    The decider-facing half is the adapter's and is in
    `test_gate_decision_wiring.py`.
    """
    supplied = _StoreShapedMembers()
    collaborators = _setup(members=supplied)

    refusal = await _decide_expecting_refusal(collaborators)

    # SPECIFIED: refused with a named error.
    assert isinstance(refusal.raised, UnreadableMembersError), (
        "an unreadable members collaborator did not raise "
        f"`UnreadableMembersError`; it produced {refusal.raised!r} / "
        f"{refusal.returned!r}"
    )
    message = str(refusal.raised)
    # SPECIFIED: identifying the collaborator supplied...
    assert type(supplied).__name__ in message, (
        "the wiring error does not identify the collaborator that was "
        f"supplied: {message!r}"
    )
    # ...and the shape expected.
    assert any(name in message for name in _EXPECTED_SHAPE_NAMES), (
        "the wiring error does not identify the shape a members collaborator "
        f"was expected to answer: {message!r}"
    )
    # SPECIFIED: it is not resolved into "the membership does not carry that
    # identity".
    assert not _matches(message.lower(), _BLAMES_UNKNOWN), (
        f"the wiring error blames the decider's identity: {message!r}"
    )
    # SPECIFIED: no approval is recorded.
    assert _approval_of(collaborators, "commit") is None


async def test_a_wiring_fault_does_not_displace_a_refusal_it_had_already_earned() -> (
    None
):
    """Requirement statement, R6: the wiring refusal is "raised before the
    deciding identity is judged".

    `tasks.md` 3.9 states the consequence this asserts: "so a decision
    already refused on grounds independent of the membership keeps its own
    refusal". A decision naming the final gate is refused for a reason that
    has nothing to do with who sent it, so a mis-wired deployment must
    still answer with *that* refusal rather than a wiring fault.

    SPECIFIED by the requirement statement; no scenario states it alone.
    """
    collaborators = _setup(FINAL_GATE, members=_StoreShapedMembers())

    refusal = await _decide_expecting_refusal(collaborators, gate_id=FINAL_GATE)

    assert not isinstance(refusal.raised, UnreadableMembersError), (
        "a decision refused on grounds independent of the membership was "
        "displaced by the wiring fault, so the decider is told the wrong "
        "thing about a decision that was never going to be recorded"
    )
    assert _says_refused(refusal)
    assert _approval_of(collaborators, FINAL_GATE) is None


# ---------------------------------------------------------------------------
# Requirement: A decision records the approval and reports what it did
# ---------------------------------------------------------------------------


async def test_an_approving_decision_records_an_approving_approval() -> None:
    """Scenario: An approving decision opens the gate and says so — its
    recording half.

    WHEN an active member presses the approving control for a gate whose
    every other condition is satisfied
    THEN an approving approval naming that member is recorded...

    The gate opening and the reply are the adapter's, since the advance
    runs there under the lock (`design.md` — Decision 6); they are asserted
    in `test_gate_decision_wiring.py`.
    """
    collaborators = _setup()

    await _decide(collaborators, approve=True)

    approval = _approval_of(collaborators, "commit")
    assert approval is not None
    assert approval.decision is ApprovalDecision.APPROVING, (
        f"the recorded approval is not an approving one: {approval!r}"
    )


async def test_a_rejecting_decision_keeps_the_gate_closed() -> None:
    """Scenario: A rejecting decision keeps the gate closed.

    WHEN an active member presses the rejecting control
    THEN a rejecting approval naming that member is recorded, no advance is
    attempted, the gate is unchanged, and the reply states that the gate
    stays closed.

    The reply's wording is the adapter's; what is asserted here is the
    recording, the verdict, and that the gate did not move.
    """
    collaborators = _setup()

    await _decide(collaborators, approve=False)

    approval = _approval_of(collaborators, "commit")
    # SPECIFIED: a rejecting approval naming that member is recorded.
    assert approval is not None, "no approval was recorded for a rejection"
    assert approval.decision is ApprovalDecision.REJECTING, (
        f"the rejection was recorded as {approval.decision!r}"
    )
    alice = _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
    assert _names_the_member(approval, alice)
    # SPECIFIED: the gate is unchanged, and no advance was attempted.
    assert collaborators.launches.only.current_gate == "commit", (
        "a rejecting decision advanced the launch"
    )


async def test_a_rejecting_decision_refreshes_the_cool_off() -> None:
    """Requirement statement, R5: "Recording a rejecting decision SHALL
    refresh the record, so the day is counted from the decision rather than
    from the ask that prompted it."

    SPECIFIED by the requirement statement. Its atomicity — that the
    rejecting approval and the refresh land together or not at all — is a
    property of the transaction the adapter opens (`tasks.md` 5.5) and is
    asserted in `test_gate_decision_wiring.py` and, over a real
    transaction, in
    `tests/integration/launch/test_gate_progression_atomicity_live.py`.
    """
    suppression = _FakeSuppression()
    collaborators = _setup(suppression=suppression)

    await _decide(collaborators, approve=False)

    assert suppression.writes, (
        "a rejecting decision left the cool-off record untouched, so the gate "
        "is re-proposed on the next pass a member has just declined it"
    )


async def test_a_decision_arriving_during_a_stand_down_is_refused() -> None:
    """Scenario: A decision arriving during a stand-down is refused.

    WHEN a decision arrives while the served playbook cannot hold a launch
    THEN it is refused, no approval is recorded, and the decider is told
    why.

    "The pass stands down in that state rather than acting on a set that is
    being authored, and a decision recorded against it would commit a
    member to a gate the system has declined to evaluate."
    """
    collaborators = _setup(unready=True)

    refusal = await _decide_expecting_refusal(collaborators, approve=True)

    # SPECIFIED: it is refused, and the decider is told why.
    assert _says_refused(refusal), (
        "a decision arriving during a stand-down was not refused"
    )
    # SPECIFIED: no approval is recorded.
    assert _approval_of(collaborators, "commit") is None, (
        "an approval was recorded against a playbook the system has declined "
        "to evaluate"
    )


async def test_a_decision_naming_the_final_gate_is_refused() -> None:
    """Scenario: A decision naming the final gate is refused.

    WHEN a decision arrives naming the final gate of the sequence
    THEN it is refused, no approval is recorded, and the decider is told.

    "This capability does not obtain that gate's approval, and recording
    one without the posture `launch-instance` requires would be rejected in
    any case."
    """
    collaborators = _setup(FINAL_GATE)

    refusal = await _decide_expecting_refusal(collaborators, gate_id=FINAL_GATE)

    assert _says_refused(refusal), "a decision naming the final gate was not refused"
    assert _approval_of(collaborators, FINAL_GATE) is None, (
        "an approval was recorded for the final gate, which this capability "
        "does not obtain"
    )


async def test_a_decision_on_a_gate_the_launch_has_left_is_refused() -> None:
    """Scenario: A decision on a gate the launch has left is refused.

    WHEN a decision arrives naming a gate that is not the launch's current
    gate
    THEN it is refused, no approval is recorded, and the decider is told.

    The launch stands at `order`; the decision names `commit`, which it has
    already passed — a day-old ask still sitting in Slack. Recording it
    "would attach a human decision to a commitment point the launch has
    already passed or not yet reached".
    """
    collaborators = _setup("order")

    refusal = await _decide_expecting_refusal(collaborators, gate_id="commit")

    assert _says_refused(refusal), (
        "a decision naming a gate the launch has already passed was accepted"
    )
    # SPECIFIED: no approval is recorded — for the stale gate, and not for
    # the current one either, which would be worse.
    #
    # CORRECTED assertion: `commit` already carries an approval, because
    # `_launch_at("order")` walked the launch through `commit` and a
    # confirmation gate only opens on one. What the scenario forbids is
    # *this decision* recording, so what is asserted is that the stored
    # approval is still the historical one and not the decider's.
    stale = _approval_of(collaborators, "commit")
    assert stale is not None and stale.when != DECIDED_AT, (
        "the decision recorded an approval against a gate the launch has "
        f"already passed: {stale!r}"
    )
    assert _approval_of(collaborators, "order") is None
    assert collaborators.launches.only.current_gate == "order"


async def test_a_decision_on_a_regressed_condition_is_recorded_and_opens_nothing() -> (
    None
):
    """Scenario: A decision on a condition that has since regressed reports
    why — its recording half.

    WHEN an approving decision arrives after a blocking condition on that
    gate has stopped being satisfied
    THEN the approval is recorded, the gate does not open...

    The regression is modelled as the gate's blocking step never having
    been satisfied at the moment the decision arrives, which is the state
    the scenario describes however it was reached. The reply naming the
    condition is the adapter's and is in `test_gate_decision_wiring.py`.
    """
    collaborators = _setup(satisfy=False)

    await _decide(collaborators, approve=True)

    # SPECIFIED: the approval is recorded. "A decision is a fact about what
    # a member did" — it is not discarded because the gate cannot open.
    approval = _approval_of(collaborators, "commit")
    assert approval is not None, (
        "the approval was discarded because the gate could not open, so the "
        "member who pressed believes they approved and nothing records it"
    )
    assert approval.decision is ApprovalDecision.APPROVING
    # SPECIFIED: the gate does not open.
    assert collaborators.launches.only.current_gate == "commit", (
        "a gate with an unsatisfied blocking condition opened on an approval"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the wiring refusal is "reported where operators see faults".
#   That is the adapter's log (`tasks.md` 5.7) and is asserted in
#   `test_gate_decision_wiring.py`; a use case that raises has nowhere to
#   put it.
# - Whether the approval is written in its own transaction. The
#   transaction is opened by the adapter (`design.md` — Decision 6), so
#   there is nothing here to observe; what it buys — an approval surviving
#   a failed cascade — is asserted in `test_gate_decision_wiring.py`.
# - The second window `design.md` — Decision 11 names, in which two
#   genuinely concurrent presses each pass the gate-currency check. It is
#   recorded as accepted rather than closed, so there is no rule to assert.
# ---------------------------------------------------------------------------
