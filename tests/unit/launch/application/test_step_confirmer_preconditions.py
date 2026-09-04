"""`confirmer` as a write-time precondition, parallel to `assignee_faults`.

Derived strictly from the delta specs:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`
(ADDED requirement *A step names who confirms an automated result* —
every scenario stated as a write) and
`.../specs/playbook-authoring/spec.md` (MODIFIED requirement *Every write
is validated as the playbook it would produce* — the new confirmer-scoped
bullets and the new scenario *A membership change does not break an accepted
step's confirmer*).

Mirrors `test_step_assignee_preconditions.py`'s structure and doubles,
since `design.md` fixes that `confirmer_faults` sits at "the same
write-time precondition site ... the same way `assignee_faults` is
today."

Covered here:

- *An unknown confirmer is rejected*
- *A deactivated confirmer does not satisfy the requirement*
- *A sole assignee cannot also be the confirmer* (write path — the
  load-time version is
  `tests/unit/launch/domain/test_confirmer_assignee_coherence.py`)
- *A confirmer among several assignees is not rejected*
- *Correcting a member does not touch the steps that confirm through them*
- *A membership change does not break an accepted step's confirmer*
  (playbook-authoring)

Not covered here (unaffected by this delta, cited instead):

- *A collaborator of the wrong shape is refused by name*, *A mis-wiring is
  not reported as a rejection of the submission*, *A mis-shaped
  collaborator never passes for an absent one*, *No members is still a
  permitted case* — the wiring-fault mechanics `confirmer_faults` shares
  with `assignee_faults` are unchanged by this delta and stay covered by
  `test_step_assignee_preconditions.py` and
  `test_authoring_members_collaborator_shape.py`.

**Level.** The use cases over a step-store double, with the members reader
as a collaborator — the same level `test_step_assignee_preconditions.py`
uses.

## INVENTED shapes

As `test_step_assignee_preconditions.py` records: `members=` and
`handlers=` collaborators on each use case, the members reader answering
rows carrying an identifier, display name and active flag, and `REJECTED`
as the tuple of acceptable refusal types since the delta fixes the
outcome and not the exception type.

## Expected first-run state

`confirmer` does not exist as a field or a precondition, so every test
here fails on an absent target (`TypeError` for the unexpected keyword,
or a write that is silently *accepted* where it should be rejected) —
absence, and nothing more.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.application import create_step, update_step
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fakes import FakeHandlerRegistry, FakeMembersStore, FakeStepStore
from tests.support.fakes import FakeMembers as _FakeMembers
from tests.support.fixtures import ALICE, ALICE_NAME, BOHDAN, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))

NOBODY: Final = "prs_00000000NO"

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)

HANDLER_NAME: Final = "price.buy_box_check"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": "price.buy-box-check",
            "name": "Watch the Buy Box",
            "gate": "live",
            "timing_anchor": OffsetAnchor(days=-3),
            "kind": StepKind.AUTOMATED,
            "confirmer": None,
            "handler": HANDLER_NAME,
            **overrides,
        }
    )


def _holding_step(gate: str) -> StepDefinition:
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        discipline=A_DISCIPLINE,
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-7),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
        provenance=None,
    )


_FakeStepStore = FakeStepStore[Any]


class _FakeHandlerRegistry(FakeHandlerRegistry):
    def __init__(self, names: frozenset[str] = frozenset({HANDLER_NAME})) -> None:
        super().__init__(names)


class _FakeMembersStore(FakeMembersStore):
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        super().__init__(rows, version)


_MEMBERS_ID_NAMES: Final = ("id", "member_id", "identifier")
_MEMBERS_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _members_field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in (row, getattr(row, "member", None), getattr(row, "entry", None)):
        if target is None:
            continue
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(f"a stored membership row exposes no {what} under any of {names}")


def _member_id(store: _FakeMembersStore, slack_identity: str) -> Any:
    for row in store.rows:
        if str(_members_field(row, _MEMBERS_SLACK_NAMES, "Slack identity")) == (
            slack_identity
        ):
            return _members_field(row, _MEMBERS_ID_NAMES, "generated identifier")
    pytest.fail(f"no stored members row carries the Slack identity {slack_identity!r}")


def _members(*, alice_active: bool = True, bohdan_active: bool = True) -> _FakeMembers:
    return _FakeMembers(
        (
            _Member(ALICE, ALICE_NAME, active=alice_active),
            _Member(BOHDAN, "Bohdan Colleague", active=bohdan_active),
        )
    )


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(_Record(_holding_step(gate)) for gate in SPECIFIED_GATE_ORDER)
    return _FakeStepStore(records + extra)


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


_CREATE_DEFAULTS: Final = {
    "name": "Watch the Buy Box",
    "description": None,
    "gate": "live",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.AUTOMATED,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (),
    "confirmer": None,
    "handler": HANDLER_NAME,
}


async def _create(
    store: _FakeStepStore, *, members: _FakeMembers | None = None, **overrides: Any
) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=members or _members(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _update(
    store: _FakeStepStore,
    step_id: str,
    *,
    members: _FakeMembers | None = None,
    **fields: Any,
) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=members or _members(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


# ---------------------------------------------------------------------------
# Requirement: A step names who confirms an automated result — the
# members-dependent write-time preconditions
# ---------------------------------------------------------------------------


async def test_an_unknown_confirmer_is_rejected() -> None:
    """Scenario: An unknown confirmer is rejected.

    WHEN a step names a confirmer identifier the membership does not carry
    THEN the write is rejected with a fault naming the step and that
    identifier.

    Written as a `draft`, so the *unknown-confirmer* rule is what refuses
    it rather than the active-automated-confirmer-must-be-active rule: an
    implementation with only the latter would pass a test using an
    `active` step.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Watch the Buy Box, confirmed by nobody the membership knows",
            status=StepStatus.DRAFT,
            confirmer=NOBODY,
        )

    assert NOBODY in str(caught.value)
    assert store.saves == []


async def test_an_active_automated_steps_confirmer_must_be_active() -> None:
    """Scenario: A deactivated confirmer does not satisfy the requirement.

    WHEN an `active` `automated` step is written naming a confirmer whose
    members entry is deactivated
    THEN the write is rejected, exactly as if it named nobody.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Watch the Buy Box, confirmed by someone who has left",
            status=StepStatus.ACTIVE,
            confirmer=BOHDAN,
            members=_members(bohdan_active=False),
        )

    assert "price.buy-box-check" in str(caught.value) or BOHDAN in str(caught.value)
    assert store.saves == []


async def test_a_deactivated_confirmer_may_still_be_named_on_a_step_not_yet_active() -> (
    None
):
    """The bound of the rule above, SPECIFIED by its own wording: it is an
    **`active` `automated`** step whose confirmer "SHALL be active on the
    members." A `draft` (or `in-development`) naming a deactivated member
    the membership still carries breaks no stated rule.

    DERIVED where the spec is silent about non-`active` statuses, mirroring
    `test_step_assignee_preconditions.py`'s identically-shaped test for
    assignees.
    """
    store = _store()

    await _create(
        store,
        name="Watch the Buy Box, drafted while Bohdan is away",
        status=StepStatus.DRAFT,
        confirmer=BOHDAN,
        members=_members(bohdan_active=False),
    )

    created = [
        record
        for record in store.records
        if record.definition.name == "Watch the Buy Box, drafted while Bohdan is away"
    ]
    assert len(created) == 1
    assert created[0].definition.confirmer == BOHDAN


async def test_a_sole_assignee_cannot_also_be_the_confirmer_write() -> None:
    """Scenario: A sole assignee cannot also be the confirmer.

    WHEN a step names exactly one assignee, and names that same member as
    its confirmer
    THEN the write is rejected with a fault naming the step.

    The domain-level version of this rule (construction with no members in
    reach) is
    `tests/unit/launch/domain/test_confirmer_assignee_coherence.py`; this
    is the write path, which is how the rule is actually reached in
    practice — "what a write cannot persist, a load cannot see."
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Watch the Buy Box, confirming its own sole assignee",
            status=StepStatus.ACTIVE,
            assignees=(ALICE,),
            confirmer=ALICE,
        )

    assert (
        "price.buy-box-check" in str(caught.value)
        or "confirm" in str(caught.value).lower()
    )
    assert store.saves == []


async def test_a_confirmer_among_several_assignees_is_not_rejected() -> None:
    """Scenario: A confirmer among several assignees is not rejected.

    WHEN a step names two or more assignees, one of whom is also its
    confirmer
    THEN the write is accepted.
    """
    store = _store()

    await _create(
        store,
        name="Watch the Buy Box, confirmed by one of two assignees",
        status=StepStatus.ACTIVE,
        assignees=(ALICE, BOHDAN),
        confirmer=BOHDAN,
    )

    created = [
        record
        for record in store.records
        if record.definition.name
        == "Watch the Buy Box, confirmed by one of two assignees"
    ]
    assert len(created) == 1
    assert tuple(created[0].definition.assignees) == (ALICE, BOHDAN)
    assert created[0].definition.confirmer == BOHDAN


async def test_correcting_a_member_does_not_touch_the_steps_that_confirm_through_them() -> (
    None
):
    """Scenario: Correcting a member does not touch the steps that
    confirm through them.

    WHEN a member's display name is corrected on the membership
    THEN every step naming them as confirmer still names them, unchanged.

    Driven through the **real** members write, exactly as
    `test_step_assignee_preconditions.py`'s identically-named test for
    `assignees` is, because a correction nobody performed would make the
    assertions below true of any implementation.
    """
    from commerce_ops.access.application import create_member, update_member

    members_store = _FakeMembersStore()
    await create_member(
        members=members_store,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity="U01ALICE",
        clickup_user_id="clickup-1",
        admin=True,
    )
    member_id = _member_id(members_store, "U01ALICE")

    confirmed = _Record(
        _step(
            identifier="price.buy-box-check",
            name="Watch the Buy Box",
            confirmer=member_id,
        )
    )
    store = _store(extra=(confirmed,))
    definition_before = _record_named(store, "price.buy-box-check").definition

    await update_member(
        members=members_store,
        principal=PRINCIPAL,
        member_id=member_id,
        display_name="Alice Admin-Shatynska",
    )

    # SPECIFIED: the step set was not written to.
    assert store.saves == []
    definition_after = _record_named(store, "price.buy-box-check").definition
    assert definition_after == definition_before
    assert definition_after.confirmer == member_id
    assert "Alice Admin" not in repr(definition_after)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED, playbook-authoring): Every write is validated as
# the playbook it would produce — the new confirmer scenario
# ---------------------------------------------------------------------------


async def test_a_members_change_does_not_break_an_accepted_steps_confirmer() -> None:
    """Scenario: A membership change does not break an accepted step's
    confirmer.

    WHEN the confirmer of an `active` `automated` step is deactivated on
    the membership
    THEN the playbook still loads and still serves that step, and its
    automated results continue to be held pending.

    Asserted here over the accepted write, at the level the sibling
    assignee scenario asserts it: the load-time half (that the playbook
    continues to load and serve the step) rather than the pending-result
    half, which belongs to `launch-step-automation` and is covered in
    `test_step_confirmer_preconditions.py`'s sibling files for that
    capability.
    """
    from commerce_ops.launch.domain.launch_playbook import (
        Gate,
        GateOpening,
        LaunchPlaybook,
    )

    store = _store()

    await _create(
        store, name="Watch the Buy Box, confirmed by Bohdan", confirmer=BOHDAN
    )

    stale_members = _members(bohdan_active=False)
    assert any(
        member.id == BOHDAN and not member.active
        for member in await stale_members.list_members()
    )

    def _opening_for(identifier: str) -> GateOpening:
        if identifier in {"commit", "order", "phase-one-complete", "graduated"}:
            return GateOpening.REQUIRES_CONFIRMATION
        return GateOpening.AUTOMATIC

    playbook = LaunchPlaybook(
        version=f"set-v{store.version}",
        gates=tuple(
            Gate(
                identifier=identifier,
                position=position,
                opening=_opening_for(identifier),
            )
            for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
        ),
        steps=tuple(record.definition for record in store.records),
    )

    served = {step.name for step in playbook.steps_for_gate("live")}
    assert "Watch the Buy Box, confirmed by Bohdan" in served
