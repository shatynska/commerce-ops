"""Creating and activating a step under the `confirmer`/no-brief field set.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/playbook-authoring/spec.md`

Covers the MODIFIED requirements:

- *A step can be created* — the authorable shape now reads "... kind,
  status, hazard, optional assignees, an optional confirmer, an optional
  start gate ... and — for an `automated` step — an optional handler",
  with `confirmation flag` and `automation brief` both gone.
- *Activation is a validated transition* — an `automated` step's
  activation requirement narrows to "a handler the code registers" alone;
  the automation-brief clause is dropped.

Not covered here (unaffected by this delta, cited instead): *A step can be
updated*, *A step can be retired and un-retired*, *Authoring never touches
the framework*, *A gate's steps can be reordered*, *Every live step holds
a slot in its gate's order*, *A dependency may only be authored on an
active step*, *A `prohibited-tactic` step may not be depended upon* — none
of these requirements or their scenarios mention `confirmer`,
`automation_brief` or the confirmation flag, and stay covered by the
existing suite (`test_playbook_authoring_new_field_set.py`,
`test_step_retirement_and_slots.py`, `test_playbook_reorder.py`,
`test_step_dependency_preconditions.py`), whose fixtures need only the
mechanical field-set rename `tasks.md` 7.1 already tracks.

**Level.** The use cases over a step-store double — the level
`test_playbook_authoring_new_field_set.py` already uses for these same
two requirements.

## Expected first-run state

`confirmer` does not exist and `automation_brief` still gates leaving
`draft`, so every test here fails on an absent target or on a write
being wrongly refused/accepted against the pre-change rules.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

from commerce_ops.launch.application import create_step
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "helen"
DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

ALICE: Final = "prs_01HQ8Z6M4A"
REGISTERED_HANDLER: Final = "price.buy_box_check"


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
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "confirmer": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


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


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member(ALICE, "Alice Admin"),)

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeHandlerRegistry:
    def __contains__(self, name: object) -> bool:
        return name == REGISTERED_HANDLER

    def __iter__(self) -> Any:
        return iter((REGISTERED_HANDLER,))

    def names(self) -> frozenset[str]:
        return frozenset({REGISTERED_HANDLER})


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                blocking=True,
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return _FakeStepStore(records + extra)


def _created_since(store: _FakeStepStore, before: set[str]) -> Any:
    created = [
        record for record in store.records if record.definition.identifier not in before
    ]
    assert len(created) == 1, f"expected exactly one created record, got {created}"
    return created[0]


_CREATE_DEFAULTS: Final = {
    "name": "Refresh the hero image ahead of ignition",
    "description": None,
    "gate": "ignition",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (ALICE,),
    "confirmer": None,
    "handler": None,
}


async def _create(store: _FakeStepStore, **overrides: Any) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=_FakeMembers(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step can be created
# ---------------------------------------------------------------------------


async def test_a_created_step_carries_the_confirmer_field_and_no_brief() -> None:
    """Scenario: A created step joins the served set — the write half,
    restated for the new authorable shape.

    WHEN a step is created as `active` with valid authorable fields
    THEN the next read of the playbook serves it, carrying a generated
    identifier whose second segment is its discipline
    AND its provenance records who created it and when.

    Every field of the redesigned authorable shape is supplied and read
    back: `confirmer` in place of the confirmation flag, and no
    `automation_brief` anywhere in the accepted keyword set.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(
        store,
        name="Refresh the hero image ahead of ignition",
        description="The full statement of the work.\nOn several lines.",
        kind=StepKind.HUMAN,
        confirmer=None,
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
    )

    record = _created_since(store, before)
    definition = record.definition
    assert re.fullmatch(r"mg\.[^.]+\.\S+", definition.identifier), definition.identifier
    assert definition.identifier.split(".")[1] == A_DISCIPLINE.value
    assert definition.name == "Refresh the hero image ahead of ignition"
    assert definition.kind is StepKind.HUMAN
    assert definition.confirmer is None
    assert definition.status is StepStatus.ACTIVE
    assert tuple(definition.assignees) == (ALICE,)
    assert not hasattr(definition, "automation_brief")
    assert not hasattr(definition, "needs_confirmation")
    assert record.created_by == PRINCIPAL
    assert record.created_on is not None


async def test_an_automated_step_is_created_naming_a_confirmer() -> None:
    """Requirement statement: the authorable shape includes "an optional
    confirmer" alongside "for an `automated` step — an optional handler."

    Exercised together, since the two fields are independent and an
    implementation dropping either on the way to the store would satisfy
    a test that supplied only one.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(
        store,
        name="Watch the Buy Box",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        confirmer=ALICE,
        handler=REGISTERED_HANDLER,
    )

    record = _created_since(store, before)
    assert record.definition.confirmer == ALICE
    assert record.definition.handler == REGISTERED_HANDLER


async def test_creating_a_draft_requires_neither_confirmer_nor_handler() -> None:
    """Scenario: A step is created declaring neither / A created step
    joins the served set — the "any other status" half.

    The draft below is the un-authorable step of today: automated, no
    handler, nobody assigned, naming no confirmer.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(
        store,
        name="Watch the Buy Box, once something can",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.DRAFT,
        handler=None,
        confirmer=None,
        assignees=(),
    )

    record = _created_since(store, before)
    assert record.definition.status is StepStatus.DRAFT
    assert record.definition.handler is None
    assert record.definition.confirmer is None


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Activation is a validated transition
# ---------------------------------------------------------------------------


async def test_an_automated_step_activates_on_a_handler_alone_no_brief_owed() -> None:
    """Scenario: An activation that satisfies its kind's rules lands
    (restated).

    WHEN an `automated` step carrying a registered handler is activated
    THEN the write lands and the next read serves the step.

    SPECIFIED restatement: "an `automated` step needs a handler the code
    registers" — the automation-brief clause the pre-change requirement
    also demanded is gone. An implementation still requiring a brief to
    reach `active` would refuse this write, which supplies none.
    """
    store = _store()

    await _create(
        store,
        name="Watch the Buy Box",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        confirmer=None,
        handler=REGISTERED_HANDLER,
    )

    created = [
        record
        for record in store.records
        if record.definition.name == "Watch the Buy Box"
    ]
    assert len(created) == 1
    assert created[0].definition.status is StepStatus.ACTIVE
    assert created[0].definition.handler == REGISTERED_HANDLER
