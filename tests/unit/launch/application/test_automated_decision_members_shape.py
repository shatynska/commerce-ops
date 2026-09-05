"""The shape of the members collaborator a decision is judged against.

Derived strictly from the delta spec
`openspec/changes/restore-automated-decisions/specs/launch-step-automation/spec.md`
(MODIFIED requirement *Only a known, active member may decide a pending
result*).

This file carries the four scenarios that requirement **adds**, in their
use-case half:

- *A collaborator that cannot answer who the membership carries is refused by
  name*
- *An absent collaborator is refused the same way, not silently* — its
  "same named wiring error" half; the "decider is told" half is the
  adapter's and lives in
  `tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py`
- *A mis-wiring is never reported as an unknown identity* — its
  use-case half; the reply and the operator-visible log are the
  adapter's, same file
- *A member the membership carries can decide through the wiring production
  supplies* — **not here**; by `design.md` — Decision 6 it must observe
  the object `main.py` injects, so it lives in the driving file above

It also re-covers the requirement's two carried-over scenarios — *An
unknown identity cannot decide* and *A deactivated member cannot decide*
— against a **narrowed** double. `tests/unit/launch/application/
test_automated_result_decisions.py` already covers both, but against
`_FakeMembers`, which answers six read spellings at once and so cannot
observe the shape this delta states. `_ReaderMembers` below answers
`list_members` and nothing else, which is the shape `design.md` —
Decision 2 fixes. That existing file is untouched; `tasks.md` 4.2's
narrowing of `_FakeMembers` is implementation work and is not this
file's.

## Level

Every scenario here is stated over the decision itself — what it
refuses, what it records, what it leaves standing. The use cases over
in-memory doubles are the smallest unit that can observe those: no Slack
request and no database is needed to see any of them, and the members
collaborator's shape *is* the input under test, so a hand-built double is
the right instrument (`design.md` — *Risks*, last bullet). The one
scenario that cannot be observed this way — the production wiring — is
the one deliberately placed elsewhere.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- The collaborator's one stated shape, `list_members` (`design.md` —
  Decision 2; `tasks.md` 1.2).
- That an unanswerable collaborator is **raised** as a named error
  identifying what was supplied and what was expected, never returned as
  a decision refusal (delta, third paragraph; `tasks.md` 1.2).
- That "no collaborator at all" is the *same* error rather than a
  different one (`design.md` — Decision 4, "Both wiring faults raise the
  same type").
- That the read is not moved ahead of the settled lookup, so a repeat
  press on a settled result keeps its own refusal even on a mis-wired
  deployment (delta, third paragraph; `tasks.md` 1.3).
- That the existing "known" and "active" refusals are unchanged
  (`tasks.md` 1.4).

INVENTED, recorded in `test-manifest.md` as unresolved project questions
with their correction points:

- The use-case names and call shape. `_decide` probes the same name
  tuples `test_automated_result_decisions.py` established and is the
  single correction point, so this file cannot fail merely because the
  pair was renamed.
- The spelling by which a message "identifies the shape expected", read
  as naming the method the reader must answer. Correction point:
  `_EXPECTED_SHAPE_NAMES`. This follows
  `test_authoring_members_collaborator_shape.py`, which made the same
  reading for the same error at the sibling call site.
- The wording by which a refusal blames the decider's identity.
  Correction point: `_BLAMES_THE_IDENTITY`. It is not asserted blind:
  `test_a_mis_wiring_is_never_reported_as_an_unknown_identity` first
  establishes that a *genuine* unknown-identity refusal matches one of
  those markers, so the negative assertion beside it cannot pass
  vacuously.

Deliberately **not** pinned: the error's class in the two tests that can
avoid pinning it. `test_an_absent_collaborator_is_refused_the_same_way`
compares the two faults' types to each other rather than to a name, so
it survives the class being spelled differently than `tasks.md` 1.6
says. `test_a_collaborator_that_cannot_answer_is_refused_by_name` does
pin `launch.application.UnreadableMembersError`, because `tasks.md` 1.6
fixes that export as a deliverable of this change and an infrastructure
adapter can reach it no other way.

## Expected first-run state

- `test_an_unknown_identity_cannot_decide` and
  `test_a_deactivated_member_cannot_decide` — expected to **PASS**.
  Their behaviour is unchanged by this delta; they are here because the
  double is narrowed, and they are regression guards, not coverage of
  new behaviour. Today's implementation resolves the member through a
  three-spelling probe of which `list_members` is one, so the narrowed
  double is already answered.
- `test_the_shape_check_does_not_move_ahead_of_the_settled_lookup` —
  expected to **PASS**, for the same reason: today's read already sits
  after `results.pending_for`, and `tasks.md` 1.3 asks that narrowing the
  shape does not move it. A regression guard.
- The other four tests — expected to **FAIL**. Today `_member_for`
  probes three spellings, finds none on a store-shaped collaborator, and
  returns `None`, so the decision is refused as though the membership did not
  carry the decider (`proposal.md` — *Why*). Nothing raises, nothing is
  named, and the two wiring faults are not the same fault.

A test among the last four that passes before the implementation lands is
a defect in that test, not good news.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1155 passed, 0 failed, 96 skipped (the integration tier,
which finds no `DATABASE_URL` here), 2026-08-27, commit `ea9f31b`, clean
tree.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeLaunches
from tests.support.fixtures import (
    ALICE,
    ALICE_NAME,
    BOHDAN,
    HANDLER_NAME,
    LAUNCH_DATE,
    STEP_ID,
    product_id,
)
from tests.support.playbook import playbook as _build_playbook
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
    "food-contact declaration."
)

#: How a message may spell "the shape expected" (INVENTED — see the
#: module docstring). Correction point for the implemented wording.
_EXPECTED_SHAPE_NAMES: Final = ("list_members", "listpeople", "list members")

#: How a refusal may spell "the membership does not carry your identity"
#: (INVENTED). `proposal.md` — *Why* quotes the reply production
#: produces: "the membership does not know that Slack identity".
_BLAMES_THE_IDENTITY: Final = (
    "does not know",
    "doesn't know",
    "not on the membership",
    "unknown identity",
    "unrecognised",
    "unrecognized",
    "no such member",
    "not known",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures (the shape `test_automated_result_decisions.py` records)
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


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        _step(),
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Members collaborators: the stated shape, and the store production injects
# ---------------------------------------------------------------------------


class _ReaderMembers:
    """A collaborator answering the **one** stated shape, and no other.

    Deliberately narrower than `_FakeMembers` in
    `test_automated_result_decisions.py`, which answers six spellings at
    once "so the shape the implementation picks is satisfied". That is
    what made the suite unable to see the production fault: a double
    satisfying every shape cannot fail the way production failed
    (`design.md` — Decision 5).
    """

    def __init__(self, *members: _Member) -> None:
        self._members = list(members)
        self.reads = 0

    async def list_members(self) -> tuple[_Member, ...]:
        self.reads += 1
        return tuple(self._members)


class _StoreShapedMembers:
    """The shape `main.py:140` actually injects: `load()` / `save()` and
    nothing else.

    `PostgresMembers`'s shape, as `tests/unit/access/application/
    test_members_writes.py` records it for `access`'s own writes, and as
    `test_authoring_members_collaborator_shape.py` records it for the
    sibling call site. It answers nothing about who the membership carries.
    """

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.loads = 0

    async def load(self) -> tuple[tuple[Any, ...], int]:
        self.loads += 1
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
        self.version += 1


def _reader() -> _ReaderMembers:
    """Alice is known and active; Bohdan is known and inactive; the
    stranger is on neither list."""
    return _ReaderMembers(
        _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK),
        _Member(
            id=BOHDAN,
            display_name=BOHDAN_NAME,
            slack_identity=BOHDAN_SLACK,
            active=False,
        ),
    )


# ---------------------------------------------------------------------------
# The remaining collaborators (as `test_automated_result_decisions.py`
# records them)
# ---------------------------------------------------------------------------


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


class _FakeLaunches(FakeLaunches):
    """The shared launch store, adapted to this file's own surface."""

    def __init__(self, launch: Launch) -> None:
        super().__init__(launch)


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()


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
    members: Any
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    recorder: _RecordingOutcomes


#: "No members argument was given", as distinct from "the membership given is
#: `None`". `None` was doing both jobs, which made
#: `test_an_absent_collaborator_is_refused_the_same_way` unfalsifiable:
#: it asked for an absent collaborator and was handed a working reader,
#: so it could neither fail for its own reason nor pass for it.
_UNSUPPLIED: Final = object()


def _setup(
    *, members: Any = _UNSUPPLIED, row: _PendingRow | None = None
) -> _Collaborators:
    playbook = _playbook()
    return _Collaborators(
        results=_FakeResults(row if row is not None else _pending()),
        members=_reader() if members is _UNSUPPLIED else members,
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
    """INVENTED call shape — the single correction point, kept identical
    to `test_automated_result_decisions.py`'s so the two files correct
    together."""
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
class _Outcome:
    """What a decision handed back: an error it raised, or a value it
    returned. Never both."""

    raised: BaseException | None
    returned: Any

    @property
    def text(self) -> str:
        if self.raised is not None:
            return str(self.raised)
        returned = self.returned
        for attribute in ("reason", "message", "detail"):
            carried = getattr(returned, attribute, None)
            if isinstance(carried, str) and carried:
                return carried
        return str(returned)


async def _decide_capturing(collaborators: _Collaborators, **kwargs: Any) -> _Outcome:
    try:
        returned = await _decide(collaborators, **kwargs)
    except AssertionError:
        raise
    except Exception as error:  # noqa: BLE001 -- the raised/returned split is
        # exactly what several of these tests are here to observe
        return _Outcome(raised=error, returned=None)
    return _Outcome(raised=None, returned=returned)


def _says_refused(outcome: _Outcome) -> bool:
    """Whether *something* said the decision was refused — the same
    reading `test_automated_result_decisions.py` records, because what
    the use case hands the Slack reply is still unfixed by any artifact.
    """
    if outcome.raised is not None:
        return True
    returned = outcome.returned
    if returned is None or returned is False:
        return False
    for attribute in ("refused", "rejected_decision", "is_refused"):
        if getattr(returned, attribute, None) is True:
            return True
    for attribute in ("accepted", "recorded", "settled", "ok"):
        if getattr(returned, attribute, None) is False:
            return True
    return "refus" in str(returned).lower()


def _blames_the_identity(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _BLAMES_THE_IDENTITY)


def _wiring_error_type() -> type[BaseException]:
    """`UnreadableMembersError`, reached through the module's public
    surface — the only route an infrastructure adapter has (`tasks.md`
    1.6, `design.md` — Decision 2)."""
    found = getattr(launch_application, "UnreadableMembersError", None)
    if isinstance(found, type) and issubclass(found, BaseException):
        return found
    pytest.fail(
        "`commerce_ops.launch.application` exports no `UnreadableMembersError` "
        "— `tasks.md` 1.6 requires it on the module's public surface, "
        "because `automation_confirmation` may reach it no other way"
    )


# ---------------------------------------------------------------------------
# Carried-over scenarios, against the narrowed double
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_an_unknown_identity_cannot_decide(accept: bool) -> None:
    """Scenario: An unknown identity cannot decide.

    WHEN a decision arrives from a Slack identity the membership does not
    know
    THEN it is refused, no outcome is recorded, the pending result still
    stands, and the decider is told.

    Carried over verbatim by this delta. What is new here is only the
    collaborator: `_ReaderMembers` answers `list_members` and nothing else,
    so this asserts the rule still holds once the shape is narrowed to
    the one `design.md` — Decision 2 states. Expected to PASS on its
    first run; a regression guard, not new coverage.
    """
    collaborators = _setup()

    outcome = await _decide_capturing(
        collaborators, accept=accept, slack_identity=STRANGER_SLACK
    )

    # SPECIFIED: no outcome is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the pending result still stands.
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None
    # SPECIFIED: the decider is told it was refused.
    assert _says_refused(outcome), (
        "an unknown identity's decision was neither refused loudly nor "
        "answered with anything that reads as a refusal"
    )
    # SPECIFIED (this delta): the membership was actually read. "The membership
    # does not know that Slack identity" is reachable only when the
    # members was read and did not carry it.
    assert collaborators.members.reads >= 1, (
        "the decision was refused as unknown without the membership ever being "
        "read — the collapse this delta forbids"
    )


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_deactivated_member_cannot_decide(accept: bool) -> None:
    """Scenario: A deactivated member cannot decide.

    WHEN a decision arrives from a Slack identity belonging to a member
    the membership holds as inactive
    THEN it is refused, no outcome is recorded, and the pending result
    still stands.

    Kept distinct from the unknown case for the reason its sibling file
    records: "known" and "active" are two facts, decided in `launch` over
    the full membership including deactivated entries (`design.md` —
    Decision 2), and an implementation that narrowed the read to active
    members alone would pass the test above and fail here.

    Expected to PASS on its first run; a regression guard.
    """
    collaborators = _setup()

    outcome = await _decide_capturing(
        collaborators, accept=accept, slack_identity=BOHDAN_SLACK
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert _says_refused(outcome)


# ---------------------------------------------------------------------------
# Scenario: A collaborator that cannot answer who the membership carries is
# refused by name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_collaborator_that_cannot_answer_is_refused_by_name(
    accept: bool,
) -> None:
    """Scenario: A collaborator that cannot answer who the membership carries
    is refused by name.

    WHEN a decision is judged against a members collaborator that cannot
    answer who the membership carries
    THEN it is refused with a named error identifying the collaborator
    supplied and the shape expected, raised before the deciding identity
    is judged
    AND no outcome is recorded and the pending result still stands.

    The collaborator is not an arbitrary wrong object: `proposal.md` —
    *Why* names `load()`/`save()` as what `main.py:140` supplies today.

    Both verdicts are exercised because the delta binds "a decision", the
    proposal names two use cases taking the collaborator, and a fix
    applied to `accept` alone would leave `reject` refusing every
    identity.

    Expected to FAIL on its first run: today the probe finds none of its
    three spellings on this object and returns `None`, so nothing is
    raised and the decider is blamed instead.
    """
    supplied = _StoreShapedMembers()
    collaborators = _setup(members=supplied)

    outcome = await _decide_capturing(collaborators, accept=accept)

    # SPECIFIED: refused with a *raised* named error, not a returned
    # decision refusal.
    assert outcome.raised is not None, (
        "a collaborator that cannot answer who the membership carries was not "
        f"refused by a raised error; the decision returned {outcome.returned!r}"
    )
    assert type(outcome.raised) is _wiring_error_type(), (
        "the mis-wiring was refused as "
        f"{type(outcome.raised).__name__}, not as the named wiring error "
        "`UnreadableMembersError` that `design.md` — Decision 2 reuses for it"
    )

    message = str(outcome.raised)
    # SPECIFIED: it identifies the collaborator that was supplied.
    assert type(supplied).__name__ in message, (
        "the refusal does not identify the collaborator supplied "
        f"({type(supplied).__name__!r}); it says: {message!r}"
    )
    # SPECIFIED: and the shape that was expected.
    lowered = message.lower()
    assert any(name in lowered for name in _EXPECTED_SHAPE_NAMES), (
        "the refusal does not identify the shape that was expected — it "
        f"names only what arrived: {message!r}"
    )

    # SPECIFIED: no outcome is recorded, and the pending result stands.
    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"
    assert collaborators.results.only.decided_by is None


# ---------------------------------------------------------------------------
# Scenario: An absent collaborator is refused the same way, not silently
# ---------------------------------------------------------------------------


async def test_an_absent_collaborator_is_refused_the_same_way() -> None:
    """Scenario: An absent collaborator is refused the same way, not
    silently — its use-case half.

    WHEN a decision arrives at a deployment where no members collaborator
    was supplied at all
    THEN it is refused with the **same** named wiring error […] and the
    decision does not fail without an answer.

    "The same" is asserted by comparing the two faults' types to each
    other rather than to a name, so this test survives the class being
    spelled differently than `tasks.md` 1.6 says — which is the point
    `design.md` — Decision 4 makes: "they are one mistake made in two
    places and a decider cannot act differently on them".

    The half this cannot see — that the decider is told, and that the
    fault does not escape the Bolt listener after `ack()` — is the
    adapter's, and is
    `tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py`.

    Expected to FAIL on its first run: today neither case raises at all.
    """
    absent = _setup(members=None)
    mis_shaped = _setup(members=_StoreShapedMembers())

    with_nothing = await _decide_capturing(absent, accept=True)
    with_a_store = await _decide_capturing(mis_shaped, accept=True)

    # SPECIFIED: refused, rather than silently resolving to "nobody".
    assert with_nothing.raised is not None, (
        "a decision at a deployment with no members collaborator at all was "
        f"not refused by a raised error; it returned {with_nothing.returned!r}"
    )
    assert with_a_store.raised is not None, (
        "a decision judged against a store-shaped collaborator was not "
        f"refused by a raised error; it returned {with_a_store.returned!r}"
    )
    # SPECIFIED: the *same* named wiring error, not two different ones.
    assert type(with_nothing.raised) is type(with_a_store.raised), (
        "the two wiring faults are refused as different errors — "
        f"{type(with_nothing.raised).__name__} for the absent collaborator "
        f"and {type(with_a_store.raised).__name__} for the mis-shaped one. "
        "`design.md` — Decision 4 requires one type, so one catch in the "
        "adapter covers both"
    )
    # SPECIFIED: and nothing was decided on the way.
    assert absent.recorder.calls == []
    assert absent.results.only.state == "pending"


# ---------------------------------------------------------------------------
# Scenario: A mis-wiring is never reported as an unknown identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("accept", [True, False], ids=["accepting", "rejecting"])
async def test_a_mis_wiring_is_never_reported_as_an_unknown_identity(
    accept: bool,
) -> None:
    """Scenario: A mis-wiring is never reported as an unknown identity —
    its use-case half.

    WHEN a decision is judged against a members collaborator that cannot
    answer who the membership carries
    THEN the decider is not told that the membership does not know their
    Slack identity […].

    The decider here is Alice, whom the membership carries as active. That is
    what makes this different from the test above: the fault must not be
    resolvable into a statement about *her*, and today it is exactly
    that. The operator-visible half — that the mis-wiring is logged where
    faults are seen — is the adapter's and lives in the driving file.

    The contrast below is what stops the negative assertion passing
    vacuously: the same rule, given a readable membership and an identity it
    genuinely does not carry, *does* produce a refusal matching one of
    `_BLAMES_THE_IDENTITY`'s markers. Without that, a change in the
    implementation's wording would silently turn this test green.

    Expected to FAIL on its first run: today Alice's decision against a
    store-shaped collaborator is refused with "the membership does not know
    that Slack identity" (`proposal.md` — *Why*).
    """
    # The contrast, established first so the markers are known to match
    # something real.
    genuinely_unknown = await _decide_capturing(
        _setup(), accept=accept, slack_identity=STRANGER_SLACK
    )
    assert _blames_the_identity(genuinely_unknown.text), (
        "a genuine unknown-identity refusal does not match any marker in "
        f"`_BLAMES_THE_IDENTITY`; it says: {genuinely_unknown.text!r}. "
        "Correct those markers to the implemented wording — until they "
        "match, the assertion below establishes nothing"
    )

    collaborators = _setup(members=_StoreShapedMembers())

    outcome = await _decide_capturing(collaborators, accept=accept)

    # SPECIFIED: not resolved into a statement about the decider.
    assert not _blames_the_identity(outcome.text), (
        "a mis-wired collaborator was reported as a fact about the "
        f"decider's identity: {outcome.text!r}. The delta forbids leaving a "
        "decider any reason to believe their members entry is at fault"
    )
    # SPECIFIED: and it is not reachable as a decision refusal at all.
    assert outcome.raised is not None, (
        "the mis-wiring came back as a decision refusal "
        f"({outcome.returned!r}) rather than as a raised wiring error. A "
        "decision refusal is a statement about the decision that was made"
    )
    # SPECIFIED: the decider's own identity is not named in it either.
    assert ALICE_SLACK not in outcome.text, (
        "the wiring error names the identity that pressed the button "
        f"({ALICE_SLACK}): {outcome.text!r}"
    )

    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "pending"


# ---------------------------------------------------------------------------
# Requirement statement, not a scenario: where the shape check sits
# ---------------------------------------------------------------------------


async def test_the_shape_check_does_not_move_ahead_of_the_settled_lookup() -> None:
    """Requirement statement: "It is raised at the point the identity
    would be resolved, so a decision already refused for a reason that
    does not depend on the membership keeps that refusal."

    SPECIFIED, stated in the requirement rather than in a scenario, and
    carried as `tasks.md` 1.3 because it is observable and a reader would
    otherwise reorder it: a repeat press on an already-settled result
    must keep answering "already decided" even on a mis-wired deployment.

    Expected to PASS on its first run — today's read already sits after
    `results.pending_for`. It is a regression guard against narrowing the
    shape and hoisting the check, which is the tempting simplification.
    """
    settled = _pending(state="accepted", decided_by=ALICE, decided_at=DECIDED_AT)
    collaborators = _setup(members=_StoreShapedMembers(), row=settled)

    outcome = await _decide_capturing(collaborators, accept=False)

    # SPECIFIED: the settled result keeps its own refusal …
    assert _says_refused(outcome)
    assert not any(name in outcome.text.lower() for name in _EXPECTED_SHAPE_NAMES), (
        "a repeat decision on an already-settled result was refused as a "
        f"wiring fault rather than as already decided: {outcome.text!r}. The "
        "shape check was hoisted ahead of the settled lookup"
    )
    # … and nothing was recorded or re-settled.
    assert collaborators.recorder.calls == []
    assert collaborators.results.only.state == "accepted"
    assert collaborators.results.only.decided_by == ALICE


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That `read_members`'s declared type makes a store-shaped injection a
#   `mypy` error at the assigning line (`design.md` — Decision 3). That
#   is a static guarantee, verified by `uv run mypy` (`tasks.md` 2.5),
#   and no runtime assertion can observe it. Recorded in
#   `test-manifest.md` rather than expressed as a test that would pass
#   for the wrong reason.
# - The two clauses the requirement carries about the Slack surface — the
#   verified `product_agent` channel and acknowledgement within Slack's
#   timeout. Both are unchanged by this delta and already covered by
#   `test_slack_entry_request_verification.py` and
#   `test_slack_entry_ack_and_failure_visibility.py`, as
#   `test_automated_result_decisions.py` records.
# ---------------------------------------------------------------------------
