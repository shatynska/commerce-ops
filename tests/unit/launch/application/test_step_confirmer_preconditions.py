"""`confirmer` as a write-time precondition, parallel to `assignee_faults`.

Derived strictly from the delta specs:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`
(ADDED requirement *A step names who confirms an automated result* —
every scenario stated as a write) and
`.../specs/playbook-authoring/spec.md` (MODIFIED requirement *Every write
is validated as the playbook it would produce* — the new confirmer-scoped
bullets and the new scenario *A roster change does not break an accepted
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
- *Correcting a person does not touch the steps that confirm through them*
- *A roster change does not break an accepted step's confirmer*
  (playbook-authoring)

Not covered here (unaffected by this delta, cited instead):

- *A collaborator of the wrong shape is refused by name*, *A mis-wiring is
  not reported as a rejection of the submission*, *A mis-shaped
  collaborator never passes for an absent one*, *No roster is still a
  permitted case* — the wiring-fault mechanics `confirmer_faults` shares
  with `assignee_faults` are unchanged by this delta and stay covered by
  `test_step_assignee_preconditions.py` and
  `test_authoring_roster_collaborator_shape.py`.

**Level.** The use cases over a step-store double, with the roster reader
as a collaborator — the same level `test_step_assignee_preconditions.py`
uses.

## INVENTED shapes

As `test_step_assignee_preconditions.py` records: `roster=` and
`handlers=` collaborators on each use case, the roster reader answering
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

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "helen"
A_DISCIPLINE: Final = next(iter(Discipline))

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
NOBODY: Final = "prs_00000000NO"

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)

HANDLER_NAME: Final = "price.buy_box_check"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "price.buy-box-check",
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
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


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


SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)


class _Record:
    def __init__(self, definition: StepDefinition, display_order: int = 10) -> None:
        self.definition = definition
        self.display_order = display_order
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None


class _FakeStepStore:
    def __init__(self, records: tuple[Any, ...], version: int = 41) -> None:
        self.records = tuple(records)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


class _Person:
    def __init__(
        self, person_id: str, display_name: str, *, active: bool = True
    ) -> None:
        self.id = person_id
        self.display_name = display_name
        self.active = active
        self.clickup_user_id: str | None = "clickup-1"


class _FakeRoster:
    def __init__(self, people: tuple[_Person, ...]) -> None:
        self.people_rows = people

    async def list_people(self) -> tuple[_Person, ...]:
        return self.people_rows

    people = list_people

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


class _FakeHandlerRegistry:
    def __init__(self, names: frozenset[str] = frozenset({HANDLER_NAME})) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self) -> Any:
        return iter(self._names)

    def names(self) -> frozenset[str]:
        return self._names


class _FakeRosterStore:
    """The roster store `access`'s own write use cases take — see
    `test_step_assignee_preconditions.py`'s identical double."""

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


_ROSTER_ID_NAMES: Final = ("id", "person_id", "identifier")
_ROSTER_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _roster_field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in (row, getattr(row, "person", None), getattr(row, "entry", None)):
        if target is None:
            continue
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(f"a stored roster row exposes no {what} under any of {names}")


def _roster_person_id(store: _FakeRosterStore, slack_identity: str) -> Any:
    for row in store.rows:
        if str(_roster_field(row, _ROSTER_SLACK_NAMES, "Slack identity")) == (
            slack_identity
        ):
            return _roster_field(row, _ROSTER_ID_NAMES, "generated identifier")
    pytest.fail(f"no stored roster row carries the Slack identity {slack_identity!r}")


def _roster(*, alice_active: bool = True, bohdan_active: bool = True) -> _FakeRoster:
    return _FakeRoster(
        (
            _Person(ALICE, ALICE_NAME, active=alice_active),
            _Person(BOHDAN, "Bohdan Colleague", active=bohdan_active),
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
    store: _FakeStepStore, *, roster: _FakeRoster | None = None, **overrides: Any
) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        roster=roster or _roster(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _update(
    store: _FakeStepStore,
    step_id: str,
    *,
    roster: _FakeRoster | None = None,
    **fields: Any,
) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        roster=roster or _roster(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


# ---------------------------------------------------------------------------
# Requirement: A step names who confirms an automated result — the
# roster-dependent write-time preconditions
# ---------------------------------------------------------------------------


async def test_an_unknown_confirmer_is_rejected() -> None:
    """Scenario: An unknown confirmer is rejected.

    WHEN a step names a confirmer identifier the roster does not carry
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
            name="Watch the Buy Box, confirmed by nobody the roster knows",
            status=StepStatus.DRAFT,
            confirmer=NOBODY,
        )

    assert NOBODY in str(caught.value)
    assert store.saves == []


async def test_an_active_automated_steps_confirmer_must_be_active() -> None:
    """Scenario: A deactivated confirmer does not satisfy the requirement.

    WHEN an `active` `automated` step is written naming a confirmer whose
    roster entry is deactivated
    THEN the write is rejected, exactly as if it named nobody.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Watch the Buy Box, confirmed by someone who has left",
            status=StepStatus.ACTIVE,
            confirmer=BOHDAN,
            roster=_roster(bohdan_active=False),
        )

    assert "price.buy-box-check" in str(caught.value) or BOHDAN in str(caught.value)
    assert store.saves == []


async def test_a_deactivated_confirmer_may_still_be_named_on_a_step_not_yet_active() -> (
    None
):
    """The bound of the rule above, SPECIFIED by its own wording: it is an
    **`active` `automated`** step whose confirmer "SHALL be active on the
    roster." A `draft` (or `in-development`) naming a deactivated person
    the roster still carries breaks no stated rule.

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
        roster=_roster(bohdan_active=False),
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

    WHEN a step names exactly one assignee, and names that same person as
    its confirmer
    THEN the write is rejected with a fault naming the step.

    The domain-level version of this rule (construction with no roster in
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


async def test_correcting_a_person_does_not_touch_the_steps_that_confirm_through_them() -> (
    None
):
    """Scenario: Correcting a person does not touch the steps that
    confirm through them.

    WHEN a person's display name is corrected on the roster
    THEN every step naming them as confirmer still names them, unchanged.

    Driven through the **real** roster write, exactly as
    `test_step_assignee_preconditions.py`'s identically-named test for
    `assignees` is, because a correction nobody performed would make the
    assertions below true of any implementation.
    """
    from commerce_ops.access.application import create_person, update_person

    roster_store = _FakeRosterStore()
    await create_person(
        roster=roster_store,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity="U01ALICE",
        clickup_user_id="clickup-1",
        admin=True,
    )
    person_id = _roster_person_id(roster_store, "U01ALICE")

    confirmed = _Record(
        _step(
            identifier="price.buy-box-check",
            name="Watch the Buy Box",
            confirmer=person_id,
        )
    )
    store = _store(extra=(confirmed,))
    definition_before = _record_named(store, "price.buy-box-check").definition

    await update_person(
        roster=roster_store,
        principal=PRINCIPAL,
        person_id=person_id,
        display_name="Alice Admin-Shatynska",
    )

    # SPECIFIED: the step set was not written to.
    assert store.saves == []
    definition_after = _record_named(store, "price.buy-box-check").definition
    assert definition_after == definition_before
    assert definition_after.confirmer == person_id
    assert "Alice Admin" not in repr(definition_after)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED, playbook-authoring): Every write is validated as
# the playbook it would produce — the new confirmer scenario
# ---------------------------------------------------------------------------


async def test_a_roster_change_does_not_break_an_accepted_steps_confirmer() -> None:
    """Scenario: A roster change does not break an accepted step's
    confirmer.

    WHEN the confirmer of an `active` `automated` step is deactivated on
    the roster
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

    stale_roster = _roster(bohdan_active=False)
    assert any(
        person.id == BOHDAN and not person.active
        for person in await stale_roster.list_people()
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
