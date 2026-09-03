"""What a member's decision does with a finding stored beside a pending
result (`launch-step-automation`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-step-automation/spec.md`

Covers, from its one ADDED requirement *A written finding is kept on the
recording it produced*, the three scenarios stated over a decision:

- A rejected result keeps no finding (`tasks.md` 1.12)
- An unreadable stored finding does not fail an acceptance (1.18a)
- The value kept is the value as written (1.18b) — the decision-side half

together with the rules the requirement imports for a stored finding
("one spelling of an empty value, an absent comment carried as absent,
and a stored finding that cannot be read reported as none"), and the
*accepting* half of *A confirmable step's finding survives until the
result is accepted* (1.11).

The whole of 1.11 and 1.18b end to end — the pass storing, the product's
value changing beneath, and the acceptance recording the earlier value —
lives in `tests/unit/launch/test_confirmable_finding_end_to_end.py`,
which is where a sink exists at all. This file asserts the half the
decision use case owns.

A separate file from `test_automated_result_decisions.py`, per this
pass's additive-only rule: that file is not edited, and its fixtures are
duplicated here rather than imported, following the precedent it and
`test_automation_pass_finding.py` set for the same reason. See
`test-manifest.md` at the change root for the full accounting of all 28
scenarios.

## Level

The application tier: the accept and reject use cases over in-memory
doubles. That is where the recording-and-settlement pair the delta calls
atomic actually happens (`design.md`; `tasks.md` 2.7), and the smallest
unit that can observe an acceptance surviving an unreadable field beside
it.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The pending-result store gains the same nullable `finding` column, and
  the accept path carries it onto the recording it makes **without
  re-reading the sink**; the reject path carries none (`tasks.md` 2.6,
  2.7; `design.md`, *The finding travels with the pending result*).
- The recording and the settlement must both take effect or neither, and
  a finding that cannot be read must not lose the member's decision
  (delta; `tasks.md` 2.7).
- A stored finding follows `launch-instance`'s own rules: one spelling of
  an empty value, an absent comment carried as absent, an unreadable
  stored finding reported as none (delta; `tasks.md` 2.8).

INVENTED, each recorded in `test-manifest.md`:

- **The attribute the pending row exposes its finding under.** The fake
  row sets every name in `_KEPT_KWARGS` to the same value, so the use
  case reaching for any of them finds it. That deliberately does not
  discriminate between the spellings — none of these scenarios is about
  which name is used — and `_KEPT_KWARGS` is the correction point.
- **The keyword a kept finding travels under onto the recording**, read
  off the recording double's captured keywords, same list.
- Which stored payloads count as "unreadable" (`_UNREADABLE_PAYLOADS`) —
  the delta names the state but no shape. Each row is DERIVED; what is
  SPECIFIED is only that such a row reads as none and does not fail the
  acceptance.
- The doubles, the call shape and the fixture identities, carried from
  `test_automated_result_decisions.py`'s own documented assumptions.

## Expected first-run state

**Two halves.**

- The scenarios asserting that a finding *reaches* the recording are
  expected to fail on an **absent target**: nothing reads a finding off a
  pending row today (`tasks.md` 2.7).
- The scenarios asserting that a finding *does not* reach it — the
  rejection, and the unreadable payloads — are expected to **pass** on
  first run, because nothing carries a finding anywhere yet. Per
  `ai-toolkit:testing` a first-run pass where the behaviour is stated in
  the negative is not evidence the assertion discriminates; each of those
  tests therefore also asserts that the acceptance itself took effect,
  which is what keeps them from being vacuous, and they become
  discriminating once the accept path carries a finding at all. This is
  recorded in `test-manifest.md` rather than hidden.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import pytest

from commerce_ops.launch import application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Admin"

LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration."
)
FIELD: Final = "sub_category"
VALUE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = "Rejected alternative: Home & Kitchen > Home Decor."

#: The keyword/attribute a stored or kept finding is assumed to travel
#: under. The single correction point for both directions.
_KEPT_KWARGS: Final = ("finding", "carried_finding", "kept_finding")

_ABSENT: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "confirmer": ALICE,
        "status": StepStatus.ACTIVE,
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
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(_step(), *fillers))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _Member:
    id: str
    display_name: str
    slack_identity: str
    active: bool = True
    clickup_user_id: str | None = None
    admin: bool = False


class _FakeMembers:
    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


def _members() -> _FakeMembers:
    return _FakeMembers(
        _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
    )


class _PendingRow:
    """A pending result, carrying whatever finding was stored beside it.

    The stored finding is exposed under **every** name in `_KEPT_KWARGS`,
    so an implementation reading any of them finds it. That is deliberate:
    none of the scenarios below is about which name the column has, and a
    row answering only one spelling would fail as a fixture defect rather
    than as a finding about the code.
    """

    #: Declared so the row reads as a row rather than as a bag of
    #: attributes; the values are supplied by the constructor below.
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    delivered_at: datetime | None

    def __init__(self, *, finding: Any = None, **attributes: Any) -> None:
        for key, value in attributes.items():
            setattr(self, key, value)
        for name in _KEPT_KWARGS:
            setattr(self, name, finding)
        self.state = "pending"
        self.decided_by: str | None = None
        self.decided_at: datetime | None = None


class _FakeResults:
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
        return None

    def _row_of(self, row: object) -> _PendingRow:
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
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    @property
    def only(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected one recording, got {self.calls}"
        return self.calls[0]


def _pending(finding: Any = None) -> _PendingRow:
    return _PendingRow(
        finding=finding,
        product_id=PRODUCT_ID,
        step_id=STEP_ID,
        handler=HANDLER_NAME,
        proposed_outcome=Satisfied,
        result_text=RECOMMENDATION,
        produced_at=PRODUCED_AT,
        delivered_at=PRODUCED_AT + timedelta(seconds=2),
    )


@dataclass
class _Collaborators:
    results: _FakeResults
    members: _FakeMembers
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    recorder: _RecordingOutcomes


def _setup(finding: Any = None) -> _Collaborators:
    playbook = _playbook()
    return _Collaborators(
        results=_FakeResults(_pending(finding)),
        members=_members(),
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        recorder=_RecordingOutcomes(),
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


def _exported(names: tuple[str, ...]) -> Any:
    for name in names:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no decision use case is exported from "
        f"`commerce_ops.launch.application` under any of {list(names)}"
    )


async def _decide(collaborators: _Collaborators, *, accept: bool) -> Any:
    use_case = _exported(_ACCEPT_NAMES if accept else _REJECT_NAMES)
    supplied: dict[str, Any] = {
        "results": collaborators.results,
        "members": collaborators.members,
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "record_outcome": collaborators.recorder,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }
    accepted = set(inspect.signature(use_case).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the decision use case does not accept {unknown}; correct `_decide`"
    )
    return await use_case(**supplied)


def _kept(call: Mapping[str, Any]) -> Any:
    for name in _KEPT_KWARGS:
        if name in call:
            return call[name]
    return _ABSENT


def _carries_nothing(kept: Any) -> bool:
    return kept is _ABSENT or kept is None


def _parts(kept: Any) -> tuple[Any, Any, Any]:
    def _part(key: str) -> Any:
        if isinstance(kept, Mapping):
            return kept.get(key, _ABSENT)
        return getattr(kept, key, _ABSENT)

    comment = _part("comment")
    return _part("field"), _part("value"), _ABSENT if comment is None else comment


def _stored(field_name: str = FIELD, value: Any = VALUE, comment: Any = COMMENT) -> Any:
    """A finding as the pending-result store holds it — the `jsonb`
    payload `tasks.md` 2.5 spells."""
    payload: dict[str, Any] = {"field": field_name, "value": value}
    if comment is not _ABSENT:
        payload["comment"] = comment
    return payload


def _assert_accepted(collaborators: _Collaborators, decision: Any) -> Mapping[str, Any]:
    """Every fact an acceptance is obliged to produce, whatever became of
    the finding beside it."""
    assert getattr(decision, "refused", True) is False, (
        f"the acceptance was refused: {getattr(decision, 'reason', decision)!r}"
    )
    call = collaborators.recorder.only
    assert call["outcome"] is Satisfied
    assert RECOMMENDATION in str(call["provenance"].evidence)
    assert collaborators.results.only.state == "accepted"
    assert collaborators.results.only.decided_at == DECIDED_AT
    return call


# ---------------------------------------------------------------------------
# Scenario: A confirmable step's finding survives until the result is
# accepted — the accepting half (tasks.md 1.11)
# ---------------------------------------------------------------------------


async def test_the_recording_an_acceptance_makes_carries_the_stored_finding() -> None:
    """WHEN a member accepts a pending result whose finding was stored
    THEN the recording that acceptance makes carries the field name, the
    value and the comment.
    """
    collaborators = _setup(_stored())

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    kept = _kept(call)
    assert not _carries_nothing(kept), (
        "the acceptance recorded no finding, so nothing the handler "
        "established reaches the launch for a confirmable step"
    )
    field_name, value, comment = _parts(kept)
    assert field_name == FIELD
    assert value == VALUE
    assert comment == COMMENT


async def test_accepting_a_result_with_no_stored_finding_carries_none() -> None:
    """The absent counterpart, so the assertion above is falsifiable."""
    collaborators = _setup(None)

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    assert _carries_nothing(_kept(call))


# ---------------------------------------------------------------------------
# Scenario: The value kept is the value as written (tasks.md 1.18b) — the
# decision-side half
# ---------------------------------------------------------------------------


async def test_the_acceptance_records_the_stored_value_and_reads_no_sink() -> None:
    """WHEN a pending result's finding is kept on the recording an
    acceptance makes THEN the value kept is the one written when the
    handler ran, and the sink is not re-read at acceptance.

    Two assertions, because the clause has two halves: the recorded value
    is the *stored* one, and the use case is handed nothing it could
    re-read a value through. A sink or product reader appearing among its
    collaborators is what the second half forbids.
    """
    collaborators = _setup(_stored(value="the value as written"))

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    _field, value, _comment = _parts(_kept(call))
    assert value == "the value as written"

    use_case = _exported(_ACCEPT_NAMES)
    parameters = set(inspect.signature(use_case).parameters)
    forbidden = {
        name
        for name in parameters
        if any(
            token in name
            for token in ("sink", "recorder", "recorders", "read_product", "catalog")
        )
    }
    assert not forbidden, (
        f"the accept use case takes {sorted(forbidden)}, which is something "
        "it could re-read the value through; the delta forbids re-reading "
        "the sink at acceptance"
    )


# ---------------------------------------------------------------------------
# Scenario: A rejected result keeps no finding (tasks.md 1.12)
# ---------------------------------------------------------------------------


async def test_a_rejected_result_keeps_no_finding() -> None:
    """WHEN a member rejects a pending result whose finding was written
    THEN the outcome recorded from that rejection carries no finding.

    "A member rejecting the proposal has declined the fact it asserted,
    and a `Blocked` recorded from that rejection SHALL NOT carry a finding
    asserting it anyway."
    """
    collaborators = _setup(_stored())

    decision = await _decide(collaborators, accept=False)

    assert getattr(decision, "refused", True) is False
    call = collaborators.recorder.only
    assert isinstance(call["outcome"], Blocked)
    assert _carries_nothing(_kept(call)), (
        "the rejection recorded a finding asserting the very fact the member declined"
    )
    assert collaborators.results.only.state == "rejected"


# ---------------------------------------------------------------------------
# Scenario: An unreadable stored finding does not fail an acceptance
# (tasks.md 1.18a)
# ---------------------------------------------------------------------------

#: DERIVED, on the same reasoning as the row-mapping file's list: the
#: delta names the state, not the shape.
_UNREADABLE_PAYLOADS: Final = (
    pytest.param("just a string", id="bare-string"),
    pytest.param(17, id="number"),
    pytest.param([FIELD, VALUE], id="array"),
    pytest.param({}, id="empty-object"),
    pytest.param({"value": VALUE}, id="no-field"),
    pytest.param({"field": FIELD}, id="no-value"),
    pytest.param({"field": FIELD, "value": None}, id="null-value"),
)


@pytest.mark.parametrize("payload", _UNREADABLE_PAYLOADS)
async def test_an_unreadable_stored_finding_does_not_fail_an_acceptance(
    payload: Any,
) -> None:
    """WHEN a member accepts a pending result whose stored finding cannot
    be read THEN the acceptance takes effect, the outcome is recorded, and
    that recording carries no finding.

    "The recording and the settlement must both take effect or neither, so
    a decision a member has made must not be lost to an unreadable field
    beside it." This is the store this change adds, and the one whose
    failure loses a member's decision.
    """
    collaborators = _setup(payload)

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    assert _carries_nothing(_kept(call)), (
        f"the stored payload {payload!r} was carried onto the recording as "
        "a present finding"
    )


@pytest.mark.parametrize("payload", _UNREADABLE_PAYLOADS)
async def test_an_unreadable_stored_finding_does_not_fail_a_rejection(
    payload: Any,
) -> None:
    """The same obligation on the other decision: a rejection keeps no
    finding either way, and must not be lost to an unreadable field."""
    collaborators = _setup(payload)

    decision = await _decide(collaborators, accept=False)

    assert getattr(decision, "refused", True) is False
    assert isinstance(collaborators.recorder.only["outcome"], Blocked)
    assert _carries_nothing(_kept(collaborators.recorder.only))
    assert collaborators.results.only.state == "rejected"


# ---------------------------------------------------------------------------
# A stored finding follows `launch-instance`'s own rules (tasks.md 1.18a)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("empty", [[], "", {}], ids=["list", "text", "map"])
async def test_a_stored_empty_value_reaches_the_recording_as_a_finding(
    empty: Any,
) -> None:
    """One spelling of an empty value, at the pending-result store: an
    empty value lives *inside* a finding that exists, so an acceptance
    must carry it rather than reporting that nothing was established.

    This is `tasks.md` 1.3's rule applied to the store this change adds,
    and the row that decides whether `lp.strategy.006` can ever render "no
    hazardous categories".
    """
    collaborators = _setup(_stored(value=empty))

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    kept = _kept(call)
    assert not _carries_nothing(kept), (
        f"a stored finding whose value is {empty!r} reached the recording "
        "as carrying nothing"
    )
    _field, value, _comment = _parts(kept)
    assert value == empty


async def test_a_stored_absent_comment_reaches_the_recording_as_absent() -> None:
    """An absent comment carried as absent, through the acceptance."""
    collaborators = _setup(_stored(comment=_ABSENT))

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    kept = _kept(call)
    assert not _carries_nothing(kept)
    _field, _value, comment = _parts(kept)
    assert comment is _ABSENT


async def test_a_stored_empty_comment_reaches_the_recording_as_empty() -> None:
    """And its counterpart: `""` is not normalised to absent."""
    collaborators = _setup(_stored(comment=""))

    decision = await _decide(collaborators, accept=True)

    call = _assert_accepted(collaborators, decision)
    _field, _value, comment = _parts(_kept(call))
    assert comment == ""
