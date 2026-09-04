"""Only the step's named confirmer may decide a pending result.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-step-automation/spec.md`

Covers the ADDED requirement *Only the step's named confirmer may decide
a pending result*, whose behavior genuinely narrows on the requirement it
replaces (*Only a known, active member may decide a pending result*,
REMOVED): decision authority moves from "any known, active members
member" to "the one identity the step names as its `confirmer`". This is
the change the proposal states as **BREAKING**, so — unlike the coherence
-rule rename in `launch-playbook` (a structural REMOVED+ADDED pair over
otherwise-unchanged content, per `design.md`) — every scenario of this
requirement is written fresh here:

- *The named confirmer can decide*
- *An unknown identity cannot decide*
- *Someone other than the confirmer cannot decide* — the scenario that
  most directly discriminates the new rule from the old: an identity the
  members holds as active, but who is not the step's confirmer, must now
  be refused, where the old rule would have let them decide.
- *A deactivated confirmer cannot decide*

The requirement's three wiring scenarios — *A collaborator that cannot
answer who the membership carries is refused by name*, *An absent
collaborator is refused the same way, not silently*, *A mis-wiring is
never reported as an unknown identity* — turn on mechanics `tasks.md` 4.3
states are explicitly unchanged ("Preserve the existing wiring-fault
handling unchanged — only the identity-matching rule changes, not how a
broken members collaborator is reported"), and stay covered by
`tests/unit/launch/application/test_automated_decision_members_shape.py`
and `tests/unit/launch/infrastructure/driving/
test_automated_decision_wiring.py`. The one genuinely new clause inside
that third scenario — that a mis-wired reply must not blame the decider's
"standing as confirmer" either, not only their membership — is
covered separately in
`tests/unit/launch/infrastructure/driving/
test_confirmer_mis_wiring_reply_wording.py`.

Also covers, from the two MODIFIED requirements this narrowing touches:

- *Accepting records the proposed outcome and names the accepter* —
  scenario *An accepted result becomes the step's outcome*, restated:
  "the step's named confirmer accepts".
- *Rejecting does not terminate the step* — scenario *A rejected result
  leaves the step live*, restated: "the step's named confirmer rejects".

`test_automated_result_decisions.py` is not superseded outright: its
"known, active member" framing is now narrower than the rule actually
implemented (it never asserts that a *different* active member may also
decide, so nothing in it contradicts the new rule), but the requirement it
was derived from is REMOVED, so it is recorded in `test-manifest.md`'s
obsolete list as a candidate for confirmation — its accept/reject
mechanics tests (settlement, evidence, once-only decision, voided-step
refusal) remain accurate descriptions of behavior this delta does not
touch, and only its authority framing is superseded.

**Level.** The use cases over in-memory doubles — the same level and the
same `_decide` probing pattern `test_automated_result_decisions.py`
already established, reused here rather than reinvented.

## INVENTED shapes

Identical to `test_automated_result_decisions.py`'s: the use-case names
(`_ACCEPT_NAMES`/`_REJECT_NAMES`/`_DECIDE_NAMES`), its call shape
(`_decide`), the members collaborator's one stated read (`list_members`),
and how a refusal is signalled (`_says_refused`, accepting either a
raised error or a returned refusal-shaped value).

## Expected first-run state

`confirmer` does not exist on `StepDefinition` yet, and the decision use
cases (however named) authorize by membership and activity alone,
not by matching the step's confirmer — so every test here fails either on
an absent field or on a decision from a non-confirmer active member being
wrongly accepted.
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
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
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
from tests.support.steps import step as _build_step
from tests.support.values import MemberValue as _Member
from tests.support.values import PendingRow as _PendingRow

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
ALICE_SLACK: Final = "U01ALICE"
BOHDAN_SLACK: Final = "U02BOHDAN"
BOHDAN_NAME: Final = "Bohdan Active-But-Not-Confirmer"

CHARLIE: Final = "prs_01HQ8Z6M4C"
CHARLIE_SLACK: Final = "U03CHARLIE"
CHARLIE_NAME: Final = "Charlie Deactivated-Confirmer"

STRANGER_SLACK: Final = "U99STRANGER"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration."
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
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        confirmer=None,
        assignees=(ALICE,),
        handler=None,
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
# Test doubles (matching `test_automated_result_decisions.py`)
# ---------------------------------------------------------------------------


class _FakeMembers:
    """Answers `list_members` and nothing else — the one stated shape."""

    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


def _members() -> _FakeMembers:
    """Alice, Bohdan and Charlie are all known; Bohdan is active but is
    never the step's confirmer; Charlie is the step's confirmer on some
    tests but has since been deactivated; the stranger is on no list."""
    return _FakeMembers(
        _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK),
        _Member(id=BOHDAN, display_name=BOHDAN_NAME, slack_identity=BOHDAN_SLACK),
        _Member(
            id=CHARLIE,
            display_name=CHARLIE_NAME,
            slack_identity=CHARLIE_SLACK,
            active=False,
        ),
    )


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
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
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
    row: _PendingRow | None = None,
) -> _Collaborators:
    playbook = _playbook(step)
    launch = _launch(playbook)
    return _Collaborators(
        results=_FakeResults(row if row is not None else _pending()),
        members=_members(),
        launches=_FakeLaunches(launch),
        playbook=playbook,
        recorder=_RecordingOutcomes(),
    )


# ---------------------------------------------------------------------------
# The decision, reached through one correction point (identical shape to
# `test_automated_result_decisions.py`)
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
# Requirement (ADDED): Only the step's named confirmer may decide a
# pending result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_the_named_confirmer_can_decide(accept: bool) -> None:
    """Scenario: The named confirmer can decide.

    WHEN a decision arrives from the Slack identity belonging to the
    step's named confirmer, whom the membership holds as active
    THEN it is accepted, and the pending result is settled per
    *Accepting records the proposed outcome and names the accepter* or
    *Rejecting does not terminate the step*.
    """
    collaborators = _setup(step=_step(confirmer=ALICE))

    await _decide(collaborators, accept=accept, slack_identity=ALICE_SLACK)

    assert len(collaborators.recorder.calls) == 1
    assert collaborators.results.only.state != "pending"
    assert collaborators.results.only.decided_by is not None


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_an_unknown_identity_cannot_decide(accept: bool) -> None:
    """Scenario: An unknown identity cannot decide.

    WHEN a decision arrives from a Slack identity the membership does not
    know
    THEN it is refused, no outcome is recorded, the pending result still
    stands, and the decider is told.
    """
    collaborators = _setup(step=_step(confirmer=ALICE))

    refusal = await _decide_expecting_refusal(
        collaborators, accept=accept, slack_identity=STRANGER_SLACK
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None
    assert _says_refused(refusal), (
        "an unknown identity's decision was neither refused loudly nor "
        "answered with anything that reads as a refusal"
    )


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_someone_other_than_the_confirmer_cannot_decide(accept: bool) -> None:
    """Scenario: Someone other than the confirmer cannot decide.

    WHEN a decision arrives from a Slack identity belonging to a member
    the membership holds as active, who is not the step's named confirmer
    THEN it is refused, no outcome is recorded, and the pending result
    still stands.

    The scenario that most directly discriminates this requirement from
    the one it replaces: Bohdan is known to the membership **and** active —
    under the superseded "any known, active member" rule this decision
    would have been accepted. The step names Alice, not Bohdan, as its
    confirmer.
    """
    collaborators = _setup(step=_step(confirmer=ALICE))

    refusal = await _decide_expecting_refusal(
        collaborators, accept=accept, slack_identity=BOHDAN_SLACK
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None
    assert _says_refused(refusal), (
        "a known, active member who is not the step's confirmer decided a "
        "pending result — this is exactly the latitude this requirement "
        "removes"
    )


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_deactivated_confirmer_cannot_decide(accept: bool) -> None:
    """Scenario: A deactivated confirmer cannot decide.

    WHEN a decision arrives from the Slack identity belonging to the
    step's named confirmer, whose members entry the membership holds as
    inactive
    THEN it is refused, no outcome is recorded, and the pending result
    still stands.
    """
    collaborators = _setup(step=_step(confirmer=CHARLIE))

    refusal = await _decide_expecting_refusal(
        collaborators, accept=accept, slack_identity=CHARLIE_SLACK
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert _says_refused(refusal)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Accepting records the proposed outcome and
# names the accepter
# ---------------------------------------------------------------------------


async def test_the_named_confirmer_accepting_becomes_the_steps_outcome() -> None:
    """Scenario: An accepted result becomes the step's outcome (restated).

    WHEN the step's named confirmer accepts a pending result proposing
    `Satisfied`
    THEN `Satisfied` is recorded for that step with source `automated`,
    naming the accepter and the moment of the decision, with evidence
    naming the handler and carrying the produced text.
    """
    collaborators = _setup(step=_step(confirmer=ALICE))

    await _decide(collaborators, accept=True, slack_identity=ALICE_SLACK)

    call = collaborators.recorder.only
    assert call["outcome"] is Satisfied
    provenance = call["provenance"]
    assert provenance.source == "automated"
    assert ALICE in str(provenance.who) or ALICE_NAME in str(provenance.who)
    assert provenance.when == DECIDED_AT
    evidence = str(provenance.evidence)
    assert HANDLER_NAME in evidence
    assert RECOMMENDATION in evidence


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Rejecting does not terminate the step
# ---------------------------------------------------------------------------


async def test_the_named_confirmer_rejecting_leaves_the_step_live() -> None:
    """Scenario: A rejected result leaves the step live (restated).

    WHEN the step's named confirmer rejects a pending result
    THEN a `Blocked` outcome is recorded whose reason names the rejecter,
    with source `automated` and the rejecter as recorder, and the step is
    not at a terminal outcome.
    """
    collaborators = _setup(step=_step(confirmer=ALICE))

    await _decide(collaborators, accept=False, slack_identity=ALICE_SLACK)

    call = collaborators.recorder.only
    outcome = call["outcome"]
    assert isinstance(outcome, Blocked)
    assert ALICE in outcome.reason or ALICE_NAME in outcome.reason
    assert "reject" in outcome.reason.lower()
    assert call["provenance"].source == "automated"
