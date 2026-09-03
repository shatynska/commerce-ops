"""Creating and updating a step under the redesigned field set.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/playbook-authoring/spec.md`

Covers the MODIFIED requirements *A step can be created* (both scenarios)
and *A step can be updated* (all three), whose bodies this change
rewrites: the authorable shape is now "name, optional description, gate,
discipline, scope, timing anchor, blocking flag, kind, confirmation flag,
status, hazard, optional assignees, and — for an `automated` step — an
optional automation brief and handler", and a step "created in any other
status SHALL NOT be served, and SHALL be readable in the authored set".

The existing tests of these two requirements
(`tests/unit/launch/application/test_playbook_authoring.py`) assert the
same outcomes over the old field set — `description` as the required
single-line field, `binding`, `execution`. Their assertions survive this
change; their *fixtures* do not (`tasks.md` 6.3). They are recorded in
`test-manifest.md` as needing fixture migration rather than as
superseded, and nothing here edits them.

**Level.** The use cases over a step-store double: what an accepted
write hands the store, and what a rejected one does not. The "next read
serves it" halves are the adapter's and are integration-tier.

## INVENTED shapes

As `test_step_activation.py`'s docstring records: `members=` and
`handlers=` collaborators; `REJECTED` as the tuple of acceptable refusal
types for the non-coherence rejection (a discipline change), following
the precedent in `test_playbook_authoring.py`.

## Expected first-run state

The new field set does not exist, so every test here fails on an absent
target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

import re
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
from tests.support.fixtures import ALICE, BOHDAN, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]
ANOTHER_DISCIPLINE: Final = DISCIPLINES[1]

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
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
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
        return (_Member(ALICE, "Alice Admin"), _Member(BOHDAN, "Bohdan Confirmer"))

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeHandlerRegistry:
    def __contains__(self, name: object) -> bool:
        return name == "price.buy_box_check"

    def __iter__(self) -> Any:
        return iter(("price.buy_box_check",))

    def names(self) -> frozenset[str]:
        return frozenset({"price.buy_box_check"})


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


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


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


async def _update(store: _FakeStepStore, step_id: str, **fields: Any) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=_FakeMembers(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


def _created_since(store: _FakeStepStore, before: set[str]) -> Any:
    created = [
        record for record in store.records if record.definition.identifier not in before
    ]
    assert len(created) == 1, f"expected exactly one created record, got {created}"
    return created[0]


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step can be created
# ---------------------------------------------------------------------------


async def test_a_created_step_carries_the_whole_new_authorable_shape() -> None:
    """Scenario: A created step joins the served set — the write half.

    WHEN a step is created as `active` with valid authorable fields
    THEN the next read of the playbook serves it, carrying a generated
    identifier whose second segment is its discipline
    AND its provenance records who created it and when.

    Every field of the redesigned authorable shape is supplied and read
    back, because the shape is what this change rewrites: an
    implementation accepting the new fields and dropping any of them on
    the way to the store would satisfy the identifier and attribution
    assertions alone.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(
        store,
        name="Refresh the hero image ahead of ignition",
        description="The full statement of the work.\nOn several lines.",
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
        confirmer=BOHDAN,
    )

    record = _created_since(store, before)
    definition = record.definition
    # SPECIFIED: a generated identifier, in the authored namespace, whose
    # second segment is the discipline.
    assert re.fullmatch(r"mg\.[^.]+\.\S+", definition.identifier), definition.identifier
    assert definition.identifier.split(".")[1] == A_DISCIPLINE.value
    # SPECIFIED: the authorable fields round-trip as given.
    assert definition.name == "Refresh the hero image ahead of ignition"
    assert definition.description == (
        "The full statement of the work.\nOn several lines."
    )
    assert definition.gate == "ignition"
    assert definition.kind is StepKind.HUMAN
    assert definition.confirmer == BOHDAN
    assert definition.status is StepStatus.ACTIVE
    assert tuple(definition.assignees) == (ALICE,)
    # SPECIFIED: provenance records the authoring principal and date.
    assert record.created_by == PRINCIPAL
    assert record.created_on is not None


async def test_created_identifiers_never_collide_retired_included() -> None:
    """Scenario: Created identifiers never collide with the seeded
    namespace.

    WHEN a step is created
    THEN its generated identifier is not in the seeded set's namespace
    and equals no existing step's identifier, retired steps included.

    "Retired steps included" now means a step whose **status** is
    `retired` — the record-level retirement this change replaces. An
    implementation generating the next identifier from the *served* set
    would reissue a retired step's identifier, which is exactly what this
    scenario forbids.
    """
    earlier = _Record(
        _step(
            identifier=f"mg.{A_DISCIPLINE.value}.001",
            name="An earlier authored step",
            gate="ignition",
        )
    )
    retired = _Record(
        _step(
            identifier=f"mg.{A_DISCIPLINE.value}.002",
            name="A retired authored step",
            gate="ignition",
            status=StepStatus.RETIRED,
        )
    )
    retired.retired_by = "olena"
    retired.retired_on = "2026-08-01"
    store = _store(extra=(earlier, retired))
    before = {record.definition.identifier for record in store.records}

    await _create(store, discipline=A_DISCIPLINE)

    identifier = _created_since(store, before).definition.identifier
    assert not identifier.startswith("lp.")
    assert identifier not in before


async def test_creating_a_draft_requires_only_what_a_draft_carries() -> None:
    """Scenario: A created step joins the served set — the "any other
    status" half of the requirement statement.

    SPECIFIED: "a step created in any other status SHALL NOT be served,
    and SHALL be readable in the authored set. Creating a step as a
    `draft` SHALL require only what a draft carries, so that work can be
    written down before it is ready — which is the point of the status
    existing."

    The draft below is the un-authorable step of today: automated, no
    handler, nobody assigned.
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
        assignees=(),
    )

    record = _created_since(store, before)
    assert record.definition.status is StepStatus.DRAFT
    assert record.definition.confirmer is None
    assert record.definition.handler is None
    assert tuple(record.definition.assignees) == ()


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step can be updated
# ---------------------------------------------------------------------------


async def test_an_edit_to_the_name_is_served_on_the_next_read() -> None:
    """Scenario: An edit is served on the next read.

    WHEN an active step's name is updated
    THEN the next read of the playbook serves the step with the new name
    under its unchanged identifier.

    The delta restates this scenario against `name`; the pre-change
    version edits the description, which now means something else
    entirely.
    """
    store = _store()

    await _update(store, "hold.ignition", name="Hold ignition until QA signs off")

    record = _record_named(store, "hold.ignition")
    assert record.definition.name == "Hold ignition until QA signs off"
    assert record.definition.identifier == "hold.ignition"


async def test_a_description_can_be_added_to_a_step_that_had_none() -> None:
    """Requirement statement: the description is an authorable field, may
    span lines, and may be absent.

    The seeded set arrives description-less (`name` ← the reference row's
    text, `description` ← null), so "add the long form later" is the
    ordinary edit this field exists for. Asserted for its interaction
    with the ClickUp body rule, where the difference between *no
    description* and *an empty description* decides whether a task's body
    is written at all.
    """
    store = _store()
    assert _record_named(store, "hold.listable").definition.description is None

    await _update(
        store,
        "hold.listable",
        description="Check the title against the style guide.\n\nThen on mobile.",
    )

    assert _record_named(store, "hold.listable").definition.description == (
        "Check the title against the style guide.\n\nThen on mobile."
    )


async def test_a_discipline_change_is_rejected() -> None:
    """Scenario: A discipline change is rejected.

    WHEN an update attempts to change a step's discipline
    THEN the update is rejected and the step is unchanged.
    """
    store = _store()
    before = _record_named(store, "hold.ignition").definition

    with pytest.raises(REJECTED):
        await _update(store, "hold.ignition", discipline=ANOTHER_DISCIPLINE)

    assert store.saves == []
    after = _record_named(store, "hold.ignition").definition
    assert after == before


async def test_an_edit_to_a_seeded_step_keeps_its_citation_and_is_attributed() -> None:
    """Scenario: An edit to a seeded step keeps its citation and gains
    attribution.

    WHEN a seeded step is updated
    THEN its provenance still carries the reference row's source citation
    AND the update's principal and date are recorded.
    """
    seeded = _Record(
        _step(
            identifier=f"lp.{A_DISCIPLINE.value}.008",
            name="The reference row's own wording",
            provenance="product-launch.md · BUILD THE LISTING · row 8",
        )
    )
    store = _store(extra=(seeded,))

    await _update(
        store,
        seeded.definition.identifier,
        name="The reference row's wording, corrected",
    )

    record = _record_named(store, f"lp.{A_DISCIPLINE.value}.008")
    assert record.definition.name == "The reference row's wording, corrected"
    # SPECIFIED: the seed citation survives the edit...
    assert record.definition.provenance == (
        "product-launch.md · BUILD THE LISTING · row 8"
    )
    # ...while the edit itself is attributed.
    assert record.updated_by == PRINCIPAL
    assert record.updated_on is not None
