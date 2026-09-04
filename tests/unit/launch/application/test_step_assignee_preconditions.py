"""Assignees as write-time preconditions, evaluated over the touched steps.

Derived strictly from the delta specs:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`
(ADDED requirement *A step names the membership responsible for it* — all
four scenarios, each stated as a write) and
`.../specs/playbook-authoring/spec.md` (MODIFIED requirement *Every write
is validated as the playbook it would produce* — the scenarios about
what the preconditions are evaluated **over**).

Two rules here are easy to implement backwards, and each has a test
below whose only job is to catch that:

1. **The preconditions are write-time only.** A load never evaluates
   them — covered at the load end in
   `tests/unit/launch/domain/test_step_assignees_are_not_a_load_rule.py`;
   covered here as *A membership change does not break an accepted set*.
2. **They are evaluated over the steps the write creates or modifies,
   never over the whole resulting set.** Set-wide evaluation would mean
   the migrated step set — 95 `active` steps deliberately left unowned —
   "refuses every subsequent create, update, retirement and status
   change until all 95 are assigned, which is the backfill the migration
   declined to invent". An implementation validating set-wide passes the
   two rejection scenarios and then bricks the admin page.

Scenarios of *Every write is validated...* covered elsewhere:
*Retiring a gate's last blocking step is rejected* is in
`test_step_retirement_and_slots.py`, which owns the retirement write.

**Level.** The use cases over a step-store double, with the members
reader as a collaborator (`tasks.md` 2.6) — the smallest unit that can
observe a write being refused and nothing being persisted.

## INVENTED shapes

As `test_step_activation.py`'s docstring records in full: `members=` and
`handlers=` collaborators on each use case, the members reader answering
rows carrying an identifier, display name, ClickUp user id and active
flag, and `REJECTED` as the tuple of acceptable refusal types since the
delta fixes the outcome and not the exception type.

## Expected first-run state

The new field set does not exist, so every test here fails on an absent
target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import create_step, update_step
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fakes import FakeHandlerRegistry as _FakeHandlerRegistry
from tests.support.fakes import FakeMembersStore, FakeStepStore
from tests.support.fixtures import ALICE, ALICE_NAME, BOHDAN, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))

NOBODY: Final = "prs_00000000NO"

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"assignees": (ALICE,), **overrides})


def _holding_step(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
    )


_FakeStepStore = FakeStepStore[Any]


class _FakeMembers:
    def __init__(self, members: tuple[_Member, ...]) -> None:
        self.members_rows = members
        self.reads = 0

    async def list_members(self) -> tuple[_Member, ...]:
        self.reads += 1
        return self.members_rows

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeMembersStore(FakeMembersStore):
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        super().__init__(rows, version)


_MEMBERS_ID_NAMES: Final = ("id", "member_id", "identifier")
_MEMBERS_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _members_field(row: Any, names: tuple[str, ...], what: str) -> Any:
    """Reads one field of a stored membership row, failing loudly rather than
    defaulting — the accessor pattern `access`'s own tests use, since no
    artifact of *this* change fixes the membership row's attribute
    spellings."""
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
    "name": "Newly authored listable work",
    "description": None,
    "gate": "listable",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (ALICE,),
    "handler": None,
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


async def _set_status(
    store: _FakeStepStore,
    step_id: str,
    status: StepStatus,
    *,
    members: _FakeMembers | None = None,
) -> Any:
    for name in ("change_step_status", "set_step_status"):
        use_case = getattr(launch_application, name, None)
        if use_case is not None:
            return await use_case(
                steps=store,
                principal=PRINCIPAL,
                step_id=step_id,
                status=status,
                members=members or _members(),
                handlers=_FakeHandlerRegistry(),
            )
    return await _update(store, step_id, status=status, members=members)


def _load(store: _FakeStepStore) -> LaunchPlaybook:
    """What the adapter does on read: construct the playbook from the
    stored definitions and the code-owned gates. No members is in reach —
    which is the point of the load-side tests below."""
    return LaunchPlaybook(
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


# ---------------------------------------------------------------------------
# Requirement: A step names the membership responsible for it
# ---------------------------------------------------------------------------


async def test_an_active_human_step_needs_someone_responsible() -> None:
    """Scenario: An active human step needs someone responsible.

    WHEN a `human` step naming no assignee is made `active`
    THEN the write is rejected with a fault naming the step.

    SPECIFIED reason: "human work nobody is responsible for is work that
    will not happen, and a projected task nobody is assigned is the shape
    that failure takes today".
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Work nobody has accepted",
            status=StepStatus.ACTIVE,
            assignees=(),
        )

    assert (
        "Work nobody has accepted" in str(caught.value)
        or "assign" in str(caught.value).lower()
    )
    assert store.saves == []


async def test_an_active_human_step_naming_an_active_member_is_accepted() -> None:
    """The permitted side, without which an implementation refusing every
    `active` `human` step would pass the rejection tests above.
    """
    store = _store()

    await _create(store, name="Work Alice has accepted", assignees=(ALICE,))

    created = [
        record
        for record in store.records
        if record.definition.name == "Work Alice has accepted"
    ]
    assert len(created) == 1
    assert tuple(created[0].definition.assignees) == (ALICE,)


async def test_an_unknown_member_is_rejected() -> None:
    """Scenario: An unknown member is rejected.

    WHEN a step names an assignee identifier the membership does not carry
    THEN the write is rejected with a fault naming the step and that
    identifier.

    Written on a `draft`, so the *unknown-member* rule is what refuses it
    rather than the active-human-needs-an-owner rule: an implementation
    with only the latter would pass a test using an `active` step.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Work assigned to nobody the membership knows",
            status=StepStatus.DRAFT,
            assignees=(NOBODY,),
        )

    # SPECIFIED: the fault names that identifier.
    assert NOBODY in str(caught.value)
    assert store.saves == []


async def test_a_deactivated_member_does_not_satisfy_the_requirement() -> None:
    """Scenario: A deactivated member does not satisfy the requirement.

    WHEN a `human` step is made `active` naming only assignees whose
    members entries are deactivated
    THEN the write is rejected, exactly as if it named nobody.

    "Exactly as if it named nobody" is what makes this more than a
    restatement: an implementation checking only *existence* would accept
    this write, and the step would go on holding a gate with nobody able
    to do it.
    """
    in_development = _Record(
        _step(
            identifier="listing.handed-over",
            status=StepStatus.IN_DEVELOPMENT,
            assignees=(BOHDAN,),
        )
    )
    store = _store(extra=(in_development,))

    with pytest.raises(REJECTED) as caught:
        await _set_status(
            store,
            "listing.handed-over",
            StepStatus.ACTIVE,
            members=_members(bohdan_active=False),
        )

    assert "listing.handed-over" in str(caught.value)
    assert store.saves == []
    assert (
        _record_named(store, "listing.handed-over").definition.status
        is StepStatus.IN_DEVELOPMENT
    )


async def test_a_deactivated_member_may_still_be_named_on_a_step_not_yet_active() -> (
    None
):
    """The bound of the rule above, SPECIFIED by its own wording: it is
    an **`active` `human`** step that "SHALL name at least one assignee
    who is active on the membership". A `draft` naming a deactivated member
    the membership still carries breaks no stated rule — the member exists,
    which is what the other rule checks.

    DERIVED where the spec is silent, and recorded as derived: nothing
    states that a non-active step's assignees must be active, and reading
    the stricter rule in would make a step un-editable the moment a
    colleague left, which is the retroactive-refusal shape `design.md`
    Decision 6 rejects.
    """
    store = _store()

    await _create(
        store,
        name="Work drafted while Bohdan is away",
        status=StepStatus.DRAFT,
        assignees=(BOHDAN,),
        members=_members(bohdan_active=False),
    )

    created = [
        record
        for record in store.records
        if record.definition.name == "Work drafted while Bohdan is away"
    ]
    assert len(created) == 1


async def test_correcting_a_member_does_not_touch_the_steps() -> None:
    """Scenario: Correcting a member does not touch the steps.

    WHEN a member's display name is corrected on the membership
    THEN every step naming them still names them, unchanged.

    SPECIFIED reason: "Assignees SHALL be referenced by identifier rather
    than by name or Slack identity, so that correcting a member's details
    never rewrites the steps that point at them" — and `design.md`
    Decision 7's rejected alternative, copying the member's name and
    ClickUp id onto the step at authoring time.

    Driven through the **real** members write (`access.application`'s
    `update_member`, over the membership-store double that capability's own
    tests record), because a correction nobody performed would make the
    assertions below true of any implementation, copied details included.
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

    owned = _Record(
        _step(
            identifier="listing.owned",
            name="Work Alice has accepted",
            assignees=(member_id,),
        )
    )
    store = _store(extra=(owned,))
    definition_before = _record_named(store, "listing.owned").definition

    await update_member(
        members=members_store,
        principal=PRINCIPAL,
        member_id=member_id,
        display_name="Alice Admin-Shatynska",
    )

    # SPECIFIED: the step set was not written to — a membership correction is
    # not a step write.
    assert store.saves == []
    # SPECIFIED: every step naming them still names them, unchanged.
    definition_after = _record_named(store, "listing.owned").definition
    assert definition_after == definition_before
    assert tuple(definition_after.assignees) == (member_id,)
    # SPECIFIED corollary: no copy of the member's details rode on the
    # step — the only way the assertions above could hold while the step
    # nonetheless carried a name that is now stale.
    assert "Alice Admin" not in repr(definition_after)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Every write is validated as the playbook it
# would produce — and what the preconditions are evaluated over
# ---------------------------------------------------------------------------


async def test_an_untouched_unowned_step_does_not_block_an_unrelated_write() -> None:
    """Scenario: An untouched unowned step does not block an unrelated
    write.

    WHEN a step is edited in a set that also holds `active` `human` steps
    naming no assignee
    THEN the write is judged on the step it touches, and the unowned
    steps elsewhere do not refuse it.

    This is the state the migration leaves behind, at small scale: the
    set below holds three unowned `active` `human` steps the write never
    touches. An implementation evaluating the preconditions over the
    whole resulting set refuses this write — and, at migration scale,
    every write anyone makes until all 95 steps are assigned.
    """
    unowned = tuple(
        _Record(
            _step(
                identifier=f"lp.migrated.{index:03d}",
                name=f"Migrated work {index}",
                gate="ignition",
                assignees=(),
            )
        )
        for index in (1, 2, 3)
    )
    edited = _Record(
        _step(identifier="listing.owned", name="Owned work", assignees=(ALICE,))
    )
    store = _store(extra=(*unowned, edited))

    await _update(store, "listing.owned", name="Owned work, reworded")

    # SPECIFIED: the write lands, judged on the step it touches.
    assert _record_named(store, "listing.owned").definition.name == (
        "Owned work, reworded"
    )
    assert len(store.saves) == 1
    # SPECIFIED: and the unowned steps are left exactly as they were —
    # not refused, and not silently repaired either.
    for record in store.records:
        if record.definition.identifier.startswith("lp.migrated."):
            assert tuple(record.definition.assignees) == ()


async def test_editing_an_unowned_step_requires_giving_it_an_owner() -> None:
    """Scenario: Editing an unowned step requires giving it an owner.

    WHEN an `active` `human` step naming no assignee is itself updated
    THEN the write is refused until it names an assignee who is active.

    The other side of the scoping rule, and the reason it is not a
    softening: "an author who edits a migrated step must give it an owner
    before it saves".
    """
    unowned = _Record(
        _step(identifier="lp.migrated.001", name="Migrated work", assignees=())
    )
    store = _store(extra=(unowned,))

    with pytest.raises(REJECTED) as caught:
        await _update(store, "lp.migrated.001", name="Migrated work, reworded")

    assert "lp.migrated.001" in str(caught.value)
    assert store.saves == []

    # SPECIFIED: "until it names an assignee who is active" — the same
    # edit carrying an owner is accepted.
    await _update(
        store,
        "lp.migrated.001",
        name="Migrated work, reworded",
        assignees=(ALICE,),
    )
    assert _record_named(store, "lp.migrated.001").definition.name == (
        "Migrated work, reworded"
    )


async def test_a_members_change_does_not_break_an_accepted_set() -> None:
    """Scenario: A membership change does not break an accepted set.

    WHEN the sole assignee of an `active` `human` step is deactivated on
    the membership
    THEN the playbook still loads and still serves that step, and the
    step is reported as needing an assignee.

    The load half is asserted here (over the very set the write
    accepted); the report half is covered in
    `test_report_activation_blockers.py`.

    SPECIFIED, and the guarantee this requirement narrows deliberately:
    "what a write cannot persist, a load cannot see — but a set a load
    accepts is not necessarily one a write would accept today, because
    the membership may have moved underneath it".
    """
    store = _store()

    await _create(store, name="Work Bohdan accepted", assignees=(BOHDAN,))

    # The membership moves underneath the accepted set.
    stale_members = _members(bohdan_active=False)
    assert any(
        member.id == BOHDAN and not member.active
        for member in await stale_members.list_members()
    )

    playbook = _load(store)

    # SPECIFIED: the playbook still loads and still serves that step.
    served = {step.name for step in playbook.steps_for_gate("listable")}
    assert "Work Bohdan accepted" in served


async def test_a_rejected_write_reports_all_faults_and_persists_nothing() -> None:
    """Scenario: A rejected write reports all faults and persists nothing.

    WHEN an update would leave a step's name empty and would also mark a
    `prohibited-tactic` step as blocking
    THEN the write is rejected reporting both faults
    AND the served step set is unchanged.

    The delta restates this scenario's two faults: it used to pair an
    empty **description** with a **lesson-bound** blocking step, and
    neither of those faults exists after this change (`tasks.md` 6.2).
    """
    tactic = _Record(
        _step(
            identifier="reviews.purchase-ring",
            name="Refuse to buy reviews",
            hazard=Hazard.PROHIBITED_TACTIC,
            blocking=False,
        )
    )
    store = _store(extra=(tactic,))
    records_before = store.records

    with pytest.raises(InvalidPlaybookError) as caught:
        await _update(store, "reviews.purchase-ring", name="   ", blocking=True)

    message = str(caught.value)
    # SPECIFIED: every fault is reported, naming the offending step.
    assert "reviews.purchase-ring" in message
    # DERIVED (fault wording): the two faults are recognisably distinct —
    # one about the name, one about a prohibited tactic blocking.
    # Correcting these substrings to the implemented wording is a fixture
    # correction; collapsing to a single-fault check is not.
    lowered = message.lower()
    assert "name" in lowered
    assert "prohibited" in lowered or "block" in lowered

    # SPECIFIED: nothing of a rejected write is persisted.
    assert store.saves == []
    assert store.records == records_before


async def test_what_a_write_cannot_persist_a_load_cannot_see() -> None:
    """Scenario: What a write cannot persist, a load cannot see.

    WHEN any sequence of accepted writes has been applied
    THEN loading the playbook succeeds — the served set is coherent by
    construction.

    The sequence below deliberately crosses the new fields: a draft with
    no owner, an activation, a status change out of `active`, and an
    edit — each of which the pre-change validation had no rule for.
    """
    store = _store()

    await _create(
        store,
        name="Drafted work",
        gate="ignition",
        status=StepStatus.DRAFT,
        assignees=(),
    )
    drafted = next(
        record for record in store.records if record.definition.name == "Drafted work"
    )
    identifier = drafted.definition.identifier

    await _update(store, identifier, assignees=(ALICE,))
    await _set_status(store, identifier, StepStatus.ACTIVE)
    await _update(store, identifier, name="Drafted work, now owned")
    await _set_status(store, identifier, StepStatus.IN_DEVELOPMENT)

    # SPECIFIED: loading the resulting set succeeds.
    playbook = _load(store)
    served = {step.identifier for step in playbook.steps_for_gate("ignition")}
    assert identifier not in served
    assert "hold.ignition" in served
