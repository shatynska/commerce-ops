"""Retirement as a status, and the slot rules once four statuses exist.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/playbook-authoring/spec.md`

Covers the MODIFIED requirements:

- *A step can be retired and un-retired* — all four scenarios, including
  the new one, *Activating a retired step from the status control still
  records the reversal*.
- *Every live step holds a slot in its gate's order* — all five
  scenarios, restated against `active` rather than "live": a created
  step takes the last slot **where it is created `active`**, a step
  leaving `active` by any route loses its slot, and a step entering
  `active` takes the last slot rather than reclaiming a remembered one.

`design.md` Decision 2 is what these tests exist to pin: `status`
replaces record-level retirement rather than sitting beside it, and the
attribution (`retired_by`/`retired_on` and their un-retire counterparts)
stays exactly as it is, recording *who moved the step and when*. What
goes is the *derivation* of liveness from those fields — so a test
reading "is this step retired" off `retired_by` would be reading the
mechanism this change removes, and every check below reads the status.

The hard-won rule, stated in three artifacts and easy to implement
backwards: **a move into or out of `retired` is the retire / un-retire
write itself**, from every surface including the admin page's status
control, and **a move out arrives at `in-development`, never at
`active`**.

**Level.** The use cases over a step-store double, as
`test_playbook_authoring.py` and `test_playbook_reorder.py` establish.
The serving halves are integration-tier.

## INVENTED shapes

As `test_step_activation.py`'s docstring records: `roster=` and
`handlers=` collaborators, and a status change expressed through
`update_step(status=...)` unless a dedicated use case is exported.
`display_order` as the slot attribute is the spelling
`test_playbook_reorder.py` already records; `_gate_order` below is this
file's single correction point for it, now filtered to `active` steps
because "Slots belong to the served order".

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
from commerce_ops.launch.application import (
    create_step,
    retire_step,
    unretire_step,
    update_step,
)
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

PRINCIPAL: Final = "helen"
EARLIER_PRINCIPAL: Final = "olena"
A_DISCIPLINE: Final = next(iter(Discipline))

PERSON_ACTIVE: Final = "prs_01HQ8Z6M4A"

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (PERSON_ACTIVE,),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _holding_step(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
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
    def __init__(self, person_id: str, display_name: str, *, active: bool) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeRoster:
    def __init__(self, people: tuple[_Person, ...]) -> None:
        self._people = people

    async def list_people(self) -> tuple[_Person, ...]:
        return self._people

    people = list_people

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


class _FakeHandlerRegistry:
    def __init__(self, names: frozenset[str]) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self) -> Any:
        return iter(self._names)

    def names(self) -> frozenset[str]:
        return self._names


def _roster() -> _FakeRoster:
    return _FakeRoster((_Person(PERSON_ACTIVE, "Alice Admin", active=True),))


def _registry() -> _FakeHandlerRegistry:
    return _FakeHandlerRegistry(frozenset({"price.buy_box_check"}))


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(_Record(_holding_step(gate)) for gate in SPECIFIED_GATE_ORDER)
    return _FakeStepStore(records + extra)


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _status(store: _FakeStepStore, identifier: str) -> StepStatus:
    status: StepStatus = _record_named(store, identifier).definition.status
    return status


def _gate_order(store: _FakeStepStore, gate: str) -> list[str]:
    """The gate's **active** steps in served order.

    SPECIFIED: "Slots belong to the served order, so a `draft` or
    `in-development` step holds none". Single correction point for the
    slot attribute's spelling.
    """
    active = [
        record
        for record in store.records
        if record.definition.gate == gate
        and record.definition.status is StepStatus.ACTIVE
    ]
    active.sort(key=lambda record: (record.display_order, record.definition.identifier))
    return [record.definition.identifier for record in active]


# -- call shapes: the single correction point -------------------------------

_CREATE_DEFAULTS: Final = {
    "name": "Newly authored listable work",
    "description": None,
    "gate": "listable",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "needs_confirmation": False,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (PERSON_ACTIVE,),
    "automation_brief": None,
    "handler": None,
}


async def _create(store: _FakeStepStore, **overrides: Any) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        roster=_roster(),
        handlers=_registry(),
        **fields,
    )


async def _update(store: _FakeStepStore, step_id: str, **fields: Any) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        roster=_roster(),
        handlers=_registry(),
        **fields,
    )


async def _retire(store: _FakeStepStore, step_id: str) -> Any:
    return await retire_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        roster=_roster(),
        handlers=_registry(),
    )


async def _unretire(store: _FakeStepStore, step_id: str) -> Any:
    return await unretire_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        roster=_roster(),
        handlers=_registry(),
    )


async def _set_status(store: _FakeStepStore, step_id: str, status: StepStatus) -> Any:
    """A status change made the way the admin page's status control makes
    one — through the general status surface, *not* through
    `retire_step`/`unretire_step`.

    This is the whole point of the scenarios below: the general surface
    must itself *be* the retire / un-retire write when the move crosses
    `retired`.
    """
    for name in ("change_step_status", "set_step_status"):
        use_case = getattr(launch_application, name, None)
        if use_case is not None:
            return await use_case(
                steps=store,
                principal=PRINCIPAL,
                step_id=step_id,
                status=status,
                roster=_roster(),
                handlers=_registry(),
            )
    return await _update(store, step_id, status=status)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step can be retired and un-retired
# ---------------------------------------------------------------------------


async def test_retiring_sets_the_status_and_deletes_nothing() -> None:
    """Scenario: A retired step leaves the served set — the write half.

    WHEN a step is retired
    THEN its stored definition and identifier persist, with the
    retirement's principal and date recorded.

    SPECIFIED, and the change from today: "retiring SHALL set the step's
    status to `retired`". The attribution stays where it was.
    """
    extra = _Record(
        _step(identifier="listing.a-plus-content", name="Optional A+ content")
    )
    store = _store(extra=(extra,))
    count_before = len(store.records)

    await _retire(store, "listing.a-plus-content")

    # SPECIFIED: retired, never deleted.
    assert len(store.records) == count_before
    record = _record_named(store, "listing.a-plus-content")
    # SPECIFIED: the status is what says it is retired...
    assert record.definition.status is StepStatus.RETIRED
    # ...and the attribution records who and when.
    assert record.retired_by == PRINCIPAL
    assert record.retired_on is not None
    # SPECIFIED: no longer in the gate's served order.
    assert "listing.a-plus-content" not in _gate_order(store, "listable")


async def test_a_retired_steps_definition_survives_whole() -> None:
    """Scenario: A retired step's history stays readable — the store half.

    WHEN outcomes were recorded against a step and the step is then
    retired
    THEN those recorded outcomes remain readable and still name the
    step's identifier.

    Recorded outcomes live on the launch aggregate, and that half is
    covered in
    `tests/unit/launch/domain/test_outcomes_after_retirement.py`. What is
    observable here is the precondition it rests on: retirement leaves
    the identifier and the definition standing, so an outcome naming the
    step still resolves to something.
    """
    extra = _Record(
        _step(
            identifier="listing.a-plus-content",
            name="Optional A+ content",
            description="The longer statement of the work.",
            provenance="product-launch.md · BUILD THE LISTING · row 41",
        )
    )
    store = _store(extra=(extra,))

    await _retire(store, "listing.a-plus-content")

    definition = _record_named(store, "listing.a-plus-content").definition
    assert definition.identifier == "listing.a-plus-content"
    assert definition.name == "Optional A+ content"
    assert definition.description == "The longer statement of the work."
    assert definition.provenance == "product-launch.md · BUILD THE LISTING · row 41"


async def test_an_un_retired_step_returns_to_in_development() -> None:
    """Scenario: An un-retired step rejoins the served set.

    WHEN a retired step is un-retired
    THEN it returns to the authored set under its original identifier as
    `in-development`, and is served once it is activated
    AND the un-retirement's principal and date are recorded.

    SPECIFIED, and a real change to existing behaviour: "Un-retiring
    SHALL return the step to `in-development`, not to `active`" —
    because "a step retired months ago may name an assignee who has
    since left, or a handler nothing registers any more".
    """
    retired = _Record(
        _step(
            identifier="listing.a-plus-content",
            name="Optional A+ content",
            status=StepStatus.RETIRED,
        )
    )
    retired.retired_by = EARLIER_PRINCIPAL
    retired.retired_on = "2026-08-01"
    store = _store(extra=(retired,))

    await _unretire(store, "listing.a-plus-content")

    record = _record_named(store, "listing.a-plus-content")
    # SPECIFIED: `in-development`, not `active`.
    assert record.definition.status is StepStatus.IN_DEVELOPMENT
    # SPECIFIED: under its original identifier.
    assert record.definition.identifier == "listing.a-plus-content"
    # SPECIFIED: and not served until it is activated.
    assert "listing.a-plus-content" not in _gate_order(store, "listable")
    # SPECIFIED: the reversal is as attributed as the retirement was.
    assert record.unretired_by == PRINCIPAL
    assert record.unretired_on is not None


async def test_the_status_control_moving_a_step_out_of_retired_records_the_reversal() -> (
    None
):
    """Scenario: Activating a retired step from the status control still
    records the reversal.

    WHEN an author uses the status control to move a `retired` step to
    `active`
    THEN the step arrives at `in-development`, not `active`, and the
    un-retirement's principal and date are recorded.

    SPECIFIED: "A status change that moves a step into or out of
    `retired`, from any surface including the admin page's status
    control, SHALL **be** this write rather than a plain status update"
    — "so that a status control cannot become a second way out of
    `retired` that lands somewhere else and records nobody".

    This is the test that discriminates: an implementation treating the
    status control as a plain field update would land the step at
    `active` with nobody recorded, and would pass every other test in
    this file.
    """
    retired = _Record(
        _step(
            identifier="listing.a-plus-content",
            name="Optional A+ content",
            status=StepStatus.RETIRED,
        )
    )
    retired.retired_by = EARLIER_PRINCIPAL
    retired.retired_on = "2026-08-01"
    store = _store(extra=(retired,))

    await _set_status(store, "listing.a-plus-content", StepStatus.ACTIVE)

    record = _record_named(store, "listing.a-plus-content")
    # SPECIFIED: it arrives at `in-development`, not at the status asked
    # for.
    assert record.definition.status is StepStatus.IN_DEVELOPMENT
    # SPECIFIED: the un-retirement's principal and date are recorded.
    assert record.unretired_by == PRINCIPAL
    assert record.unretired_on is not None


async def test_the_status_control_moving_a_step_into_retired_records_the_retirement() -> (
    None
):
    """Scenario: the *into* half of the same requirement statement, which
    the scenario list states only for the way out.

    SPECIFIED: a status change moving a step into `retired`, "from any
    surface", "SHALL record the retiring or un-retiring principal and
    date". Without this, retiring from the status control would leave the
    set with a `retired` step nobody is recorded as having retired — the
    same silence the way-out scenario exists to prevent.
    """
    extra = _Record(
        _step(identifier="listing.a-plus-content", name="Optional A+ content")
    )
    store = _store(extra=(extra,))

    await _set_status(store, "listing.a-plus-content", StepStatus.RETIRED)

    record = _record_named(store, "listing.a-plus-content")
    assert record.definition.status is StepStatus.RETIRED
    assert record.retired_by == PRINCIPAL
    assert record.retired_on is not None


async def test_retiring_a_gates_last_active_blocking_step_is_rejected() -> None:
    """Scenario (*Every write is validated as the playbook it would
    produce*): Retiring a gate's last blocking step is rejected.

    WHEN a retire targets the only active blocking step attached to a
    gate
    THEN the write is rejected, naming the gate that would be left
    unheld.

    Restated by this change against **active** blocking steps, which is
    what makes the comparison in *Un-activating a gate's last blocking
    step is refused* (`test_step_activation.py`) exact.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _retire(store, "hold.live")

    assert "live" in str(caught.value)
    assert store.saves == []
    assert _status(store, "hold.live") is StepStatus.ACTIVE


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Every live step holds a slot in its gate's order
# ---------------------------------------------------------------------------


def _listable(
    *identifiers: str, status: StepStatus = StepStatus.ACTIVE
) -> tuple[_Record, ...]:
    return tuple(
        _Record(
            _step(
                identifier=identifier,
                name=f"Work of {identifier}",
                gate="listable",
                status=status,
            ),
            display_order=slot * 10,
        )
        for slot, identifier in enumerate(identifiers, start=2)
    )


async def test_a_created_active_step_appends_to_its_gate() -> None:
    """Scenario: A created step appends to its gate.

    WHEN a step is created as `active` for a gate that already has active
    steps
    THEN the next read serves it as that gate's last step.
    """
    store = _store(extra=_listable("listing.alpha", "listing.beta"))
    before = _gate_order(store, "listable")

    await _create(store, name="Newly authored listable work", status=StepStatus.ACTIVE)

    order = _gate_order(store, "listable")
    assert order[: len(before)] == before
    assert len(order) == len(before) + 1


async def test_a_created_draft_holds_no_slot() -> None:
    """Scenario: A draft holds no slot.

    WHEN a step is created as a `draft`
    THEN it holds no position in its gate's order, and the gate's active
    steps keep the positions they had.
    """
    store = _store(extra=_listable("listing.alpha", "listing.beta"))
    before = _gate_order(store, "listable")

    await _create(
        store,
        name="Work written down before it is ready",
        status=StepStatus.DRAFT,
        assignees=(),
    )

    # SPECIFIED: the gate's active steps keep the positions they had...
    assert _gate_order(store, "listable") == before
    # ...and the draft is stored all the same.
    created = [
        record
        for record in store.records
        if record.definition.name == "Work written down before it is ready"
    ]
    assert len(created) == 1
    assert created[0].definition.status is StepStatus.DRAFT


async def test_a_step_entering_active_takes_the_last_slot() -> None:
    """Scenario: An un-retired step rejoins at the end.

    WHEN a step is retired and later un-retired and activated
    THEN the next read serves it as the last step of its gate, whatever
    slot it held before retirement.

    SPECIFIED, and restated by this change for every route into `active`:
    "a step entering `active` SHALL take the last slot of its gate rather
    than reclaiming a remembered position".

    The step below held the *first* slot of its gate before retirement,
    so an implementation restoring a remembered position fails here
    rather than passing by coincidence.
    """
    first_slot = _Record(
        _step(identifier="listing.was-first", name="Work of listing.was-first"),
        display_order=1,
    )
    store = _store(extra=(first_slot, *_listable("listing.alpha", "listing.beta")))
    assert _gate_order(store, "listable")[0] == "listing.was-first"

    await _retire(store, "listing.was-first")
    await _unretire(store, "listing.was-first")
    await _set_status(store, "listing.was-first", StepStatus.ACTIVE)

    # SPECIFIED: last, not first.
    assert _gate_order(store, "listable")[-1] == "listing.was-first"


async def test_a_gate_change_appends_to_the_new_gate() -> None:
    """Scenario: A gate change appends to the new gate.

    WHEN an update moves a step to a different gate
    THEN the next read serves it as the last step of its new gate
    AND the steps of its old gate keep their relative order.
    """
    store = _store(extra=_listable("listing.alpha", "listing.beta", "listing.gamma"))
    listable_before = _gate_order(store, "listable")
    ignition_before = _gate_order(store, "ignition")

    await _update(store, "listing.beta", gate="ignition")

    # SPECIFIED: last of its new gate.
    assert _gate_order(store, "ignition") == [*ignition_before, "listing.beta"]
    # SPECIFIED: the old gate's remaining steps keep their relative order.
    assert _gate_order(store, "listable") == [
        identifier for identifier in listable_before if identifier != "listing.beta"
    ]


async def test_retirement_closes_the_gap() -> None:
    """Scenario: Retirement closes the gap.

    WHEN a step is retired from the middle of its gate's order
    THEN the next read serves the gate's remaining steps in their
    previous relative order with no gap in the listing.
    """
    store = _store(extra=_listable("listing.alpha", "listing.beta", "listing.gamma"))
    before = _gate_order(store, "listable")
    assert "listing.beta" in before[1:-1]

    await _retire(store, "listing.beta")

    # SPECIFIED: previous relative order, minus the retired step.
    assert _gate_order(store, "listable") == [
        identifier for identifier in before if identifier != "listing.beta"
    ]
    # SPECIFIED: no gap in the listing — every remaining active step of
    # the gate holds a distinct slot.
    slots = [
        record.display_order
        for record in store.records
        if record.definition.gate == "listable"
        and record.definition.status is StepStatus.ACTIVE
    ]
    assert len(set(slots)) == len(slots)


async def test_a_step_leaving_active_without_being_retired_loses_its_slot() -> None:
    """Requirement statement: "A step leaving `active` — by retirement or
    by **any other status change** — SHALL be removed from its gate's
    order without disturbing the relative order of the steps that
    remain".

    No scenario states the non-retirement route, and it is new with this
    change: before it, retirement was the only way out of the served set.
    An implementation hooking slot removal to `retire_step` alone would
    pass every scenario above and leave an `in-development` step holding
    a slot in the order a launch is held to.
    """
    store = _store(extra=_listable("listing.alpha", "listing.beta", "listing.gamma"))
    before = _gate_order(store, "listable")

    await _set_status(store, "listing.beta", StepStatus.IN_DEVELOPMENT)

    assert _gate_order(store, "listable") == [
        identifier for identifier in before if identifier != "listing.beta"
    ]
    assert _status(store, "listing.beta") is StepStatus.IN_DEVELOPMENT
