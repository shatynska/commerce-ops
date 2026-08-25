"""Projection under the redesigned step: name, body, assignees, filter.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *Human steps are projected as tasks
carrying their name, description and assignees*, the scenarios whose
**rule changed** or which are new:

- *A human step gets a task* (the name now comes from the step's `name`,
  not from a composition over its description),
- *A step's description becomes the task's body*, including its second
  clause — a step carrying **no** description is projected with **no
  body written at all**,
- *A task is assigned to the step's people*,
- *An existing unowned task gains its step's assignees*,
- *A person's own assignment change is not overwritten*,
- *An assignee with no ClickUp account is reported, not silently
  dropped*,
- *A step activated mid-launch is projected*,
- *A person's body note survives a wording edit* (the body's meaning
  changes, so the rule guarding it is re-established),
- *An unedited legacy task starts healing* (`tasks.md` 4.7: confirm an
  unedited existing task heals to the **new** composition),
- *An over-long name is shortened rather than failing* (shortening now
  cuts the step's `name`, and must still not spill into the body),
- *Automated steps are never projected* (the filter moves from the
  removed execution mode to `kind`),
- *A step that is not active is never projected* (new).

Scenarios of this requirement carried forward **unchanged** — a renamed
task still resolving through the mapping, an unedited task following the
current wording, an ambiguous legacy task never rewritten, an edited name
never restored, an existing task not recreated, the prohibited-tactic
exclusion, and the two deleted-task scenarios — are covered by the
existing tests in this directory and are accounted for against them in
`test-manifest.md`. Those tests need their fixtures migrated to the new
field set (`tasks.md` 6.3); that is a fixture correction and not a
licence to weaken what they assert.

**The body rule is the one to get right.** `design.md`'s risk register:
a task projected before this change whose name was shortened "carries the
step's full former text in its body, written by the system and therefore
matching its retained value, so a rule that rewrote it to empty would
leave that task stating its work nowhere". The spec therefore composes
**no** body for a description-less step, and the system never writes a
body it did not compose. `test_a_step_with_no_description_has_no_body_
written_at_all` is the test that discriminates, and an implementation
composing an empty string passes everything else here.

## INVENTED shapes

The harness follows `test_clickup_sync_projection.py` in this directory —
`converge_launch(launch=, playbook=, clickup=, mapping=, read_product=,
folder_id=)` over in-memory fakes — extended for this change with:

- a `roster=` collaborator, the same reader `launch`'s use cases take
  from `access`'s public application surface (`proposal.md` Impact:
  "`launch` needs to resolve roster people ... through `access`'s public
  application surface"). Correction point: `_converge`.
- assignees on the mapping's retained compositions, alongside the
  retained name and body (SPECIFIED: "The system SHALL retain, with the
  mapping, the assignees it last set, exactly as it retains the name and
  the body it last composed"). The fake accepts either
  `record_assignees(...)` or `record_composition(assignees=...)`, so the
  spelling is not pinned. Correction point: `_FakeMapping`.
- `_body_in` / `_assignees_in`, which read a create/update payload for a
  body-bearing or assignee-bearing field under any plausible key, so no
  wire spelling is pinned.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku

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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

FOLDER_ID: Final = "90110042424"
LIST_ID: Final = "901234002"
LAUNCH_DATE: Final = date(2027, 3, 2)

SEPARATOR: Final = " · "

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_CLICKUP: Final = "clickup-alice"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_CLICKUP: Final = "clickup-bohdan"
NO_ACCOUNT: Final = "prs_01HQ8Z6M4C"


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
        "identifier": "listing.title-conforms",
        "name": "Conform the title to the style guide",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """An `active` `automated` blocking filler, so no filler is ever
    projected and every assertion below is about the test's own steps."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        automation_brief="Held until the automated check reports green.",
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return self._product


class _Person:
    def __init__(
        self,
        person_id: str,
        display_name: str,
        *,
        clickup_user_id: str | None,
        active: bool = True,
    ) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id = clickup_user_id
        self.active = active


class _FakeRoster:
    """The roster reader, offering several plausible call shapes so a
    correction to the seam is one line here."""

    def __init__(self, people: tuple[_Person, ...]) -> None:
        self._people = people

    async def list_people(self) -> tuple[_Person, ...]:
        return self._people

    people = list_people

    async def person(self, person_id: str) -> _Person | None:
        for person in self._people:
            if person.id == person_id:
                return person
        return None

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


def _roster() -> _FakeRoster:
    return _FakeRoster(
        (
            _Person(ALICE, "Alice Admin", clickup_user_id=ALICE_CLICKUP),
            _Person(BOHDAN, "Bohdan Colleague", clickup_user_id=BOHDAN_CLICKUP),
            _Person(NO_ACCOUNT, "Chris Newcomer", clickup_user_id=None),
        )
    )


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    status: str = "to do"
    closed: bool = False
    due_date: Any = None
    body: Any = None
    assignees: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


_BODY_KEYS: Final = ("description", "body", "content", "markdown", "text_content")


def _body_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    """Any body-bearing field of a create/update payload, matched on the
    key so no wire spelling is pinned. Returns (present, value)."""
    for key, value in fields.items():
        lowered = key.lower()
        if any(candidate in lowered for candidate in _BODY_KEYS):
            return True, value
    return False, None


def _assignees_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    for key, value in fields.items():
        if "assign" in key.lower():
            return True, value
    return False, None


def _as_ids(value: Any) -> tuple[str, ...]:
    """Normalises an assignee payload to ClickUp user ids as strings.

    ClickUp's own API takes either a list of ids or an `{"add": [...],
    "rem": [...]}` object; neither is fixed by an artifact, so both are
    read here rather than one being pinned.
    """
    if value is None:
        return ()
    if isinstance(value, dict):
        return tuple(str(item) for item in value.get("add", ()))
    if isinstance(value, (str, int)):
        return (str(value),)
    return tuple(str(item) for item in value)


class _FakeClickUp:
    def __init__(self) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        payload = {"list_id": list_id, "name": name, **fields}
        if description is not None:
            payload["description"] = description
        self.calls.append(("create_task", payload))
        task_id = self._identifier("task")
        present, body = _body_in(payload)
        has_assignees, assignees = _assignees_in(fields)
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            body=body if present else None,
            assignees=_as_ids(assignees) if has_assignees else (),
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        if "name" in fields:
            task.name = fields["name"]
        present, body = _body_in(fields)
        if present:
            task.body = body
        has_assignees, assignees = _assignees_in(fields)
        if has_assignees:
            task.assignees = _as_ids(assignees)
        if "status" in fields:
            task.status = fields["status"]
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    # -- test-side helpers -------------------------------------------------

    def seed_list(self, list_id: str, name: str = "seeded list") -> str:
        self.lists[list_id] = name
        return list_id

    def seed_task(self, list_id: str, task_id: str, **overrides: Any) -> _FakeTask:
        attributes = {"name": task_id, **overrides}
        task = _FakeTask(id=task_id, list_id=list_id, **attributes)
        self.tasks[task_id] = task
        return task

    def calls_named(self, name: str) -> list[Any]:
        return [payload for called, payload in self.calls if called == name]

    def body_writes_for(self, task_id: str) -> list[Any]:
        """Every call that wrote a body for this task — a create carrying
        one, or an update carrying one."""
        writes = []
        for called, payload in self.calls:
            if called == "create_task":
                present, body = _body_in(payload)
                if present and self.tasks.get(task_id) is not None:
                    writes.append(body)
            elif called == "update_task" and payload["task_id"] == task_id:
                present, body = _body_in(payload["fields"])
                if present:
                    writes.append(body)
        return writes


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False
    retained_name: str | None = None
    retained_body: str | None = None
    retained_assignees: tuple[str, ...] | None = None


class _FakeMapping:
    def __init__(self) -> None:
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}
        self.replacements: list[tuple[str, str]] = []

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
        self.lists[product_id] = list_id

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> _TaskMapping | None:
        return self.tasks.get((product_id, step_id))

    async def tasks_for(self, product_id: ProductId) -> list[_TaskMapping]:
        return [
            mapping
            for (mapped_product, _), mapping in self.tasks.items()
            if mapped_product == product_id
        ]

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None:
        existing = self.tasks.get((product_id, step_id))
        if existing is not None:
            self.replacements.append((existing.task_id, task_id))
        self.tasks[(product_id, step_id)] = _TaskMapping(
            product_id=product_id, step_id=step_id, task_id=task_id
        )

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        self.tasks[(product_id, step_id)].last_observed_closed = closed

    async def record_composition(
        self,
        product_id: ProductId,
        step_id: str,
        *,
        name: str | None = None,
        body: str | None = None,
        assignees: Any = None,
    ) -> None:
        mapping = self.tasks[(product_id, step_id)]
        if name is not None:
            mapping.retained_name = name
        if body is not None:
            mapping.retained_body = body
        if assignees is not None:
            mapping.retained_assignees = tuple(str(item) for item in assignees)

    async def record_assignees(
        self, product_id: ProductId, step_id: str, assignees: Any
    ) -> None:
        """The alternative spelling, offered so the seam is not pinned."""
        self.tasks[(product_id, step_id)].retained_assignees = tuple(
            str(item) for item in assignees
        )

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    # -- test-side helpers -------------------------------------------------

    def seed_task(
        self,
        step_id: str,
        task_id: str,
        *,
        closed: bool = False,
        retained_name: str | None = None,
        retained_body: str | None = None,
        retained_assignees: tuple[str, ...] | None = None,
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
            retained_name=retained_name,
            retained_body=retained_body,
            retained_assignees=retained_assignees,
        )
        self.tasks[(PRODUCT_ID, step_id)] = mapping
        return mapping


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(
        default_factory=lambda: _FakeCatalog(
            _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)
        )
    )
    roster: _FakeRoster = field(default_factory=_roster)


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
    *,
    folder_id: str | None = FOLDER_ID,
) -> None:
    """INVENTED call shape — see the module docstring. The single
    correction point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        roster=collaborators.roster,
        folder_id=folder_id,
    )


def _created_named(collaborators: _Collaborators, fragment: str) -> dict[str, Any]:
    created = [
        payload
        for payload in collaborators.clickup.calls_named("create_task")
        if fragment in payload["name"]
    ]
    assert len(created) == 1, (
        f"expected exactly one task created for {fragment!r}, got "
        f"{[payload['name'] for payload in collaborators.clickup.calls_named('create_task')]}"
    )
    payload: dict[str, Any] = created[0]
    return payload


def _task_id_named(collaborators: _Collaborators, fragment: str) -> str:
    for task in collaborators.clickup.tasks.values():
        if fragment in task.name:
            return task.id
    pytest.fail(f"no task carries {fragment!r} in its name")


# ---------------------------------------------------------------------------
# Requirement: Human steps are projected as tasks carrying their name,
# description and assignees
# ---------------------------------------------------------------------------


async def test_a_human_step_gets_a_task_named_from_its_name() -> None:
    """Scenario: A human step gets a task.

    WHEN the reconciliation pass runs and an `active` `human` step of an
    active launch has no recorded task
    THEN a task named with the step's name, then ` · `, then its
    identifier is created in the launch's list
    AND the step's discipline is not appended as a further element of
    that name
    AND the association between the step and the created task is
    recorded.

    The change: the name is the step's **`name`** now, not a composition
    over its description. The two used to be the same field, so the test
    below gives the step a description that differs from its name — an
    implementation still composing from the description fails here rather
    than passing by coincidence.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        description="The long form nobody wants in a task name.",
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = _created_named(collaborators, "Conform the title")
    # SPECIFIED: exactly name, separator, identifier — three parts.
    assert created["name"] == (
        f"Conform the title to the style guide{SEPARATOR}listing.title-conforms"
    )
    # SPECIFIED: the discipline is not appended as a further element.
    assert not created["name"].endswith(_any_discipline().value)
    # SPECIFIED: the association is recorded.
    assert (
        await collaborators.mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    ) is not None


async def test_a_steps_description_becomes_the_tasks_body() -> None:
    """Scenario: A step's description becomes the task's body.

    WHEN a task is projected for a step carrying a description
    THEN the task's body is that description.

    SPECIFIED: "The body is no longer a place the name overflows into:
    the step's own two fields map onto the task's two". The description
    below spans lines, which the old single-field rule could never have
    produced.
    """
    body = (
        "Check the title against the style guide.\n"
        "\n"
        "Then check it renders on mobile, where the truncation differs."
    )
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        description=body,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    task_id = _task_id_named(collaborators, "Conform the title")
    # SPECIFIED: the task's body is that description, unaltered.
    assert collaborators.clickup.tasks[task_id].body == body


async def test_a_step_with_no_description_has_no_body_written_at_all() -> None:
    """Scenario: A step's description becomes the task's body — the
    second clause.

    ...AND a step carrying no description is projected with no body
    written at all, leaving whatever the task already holds.

    **This is the data-destroying case.** SPECIFIED: "Where a step
    carries no description the system SHALL compose no body at all, and
    SHALL neither write nor rewrite the task's body — leaving whatever
    stands there. Composing an *empty* body instead would destroy work: a
    task projected before this change whose name was shortened carries
    the step's full former text in its body, written by the system and
    therefore matching its retained value, so a rule that rewrote it to
    empty would leave that task stating its work nowhere."

    Asserted in the strong form — **no body-bearing field is sent at
    all** — because an empty string is exactly the value the destroying
    implementation sends, and asserting only "the body is not the
    description" would let it through.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        description=None,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = _created_named(collaborators, "Conform the title")
    present, body = _body_in(created)
    assert not present, (
        f"a body was written for a step carrying no description: {body!r} — "
        "the system composes no body at all in this case"
    )
    task_id = _task_id_named(collaborators, "Conform the title")
    assert collaborators.clickup.body_writes_for(task_id) == []


async def test_a_pre_existing_body_is_left_standing_when_the_step_has_none() -> None:
    """Scenario: A step's description becomes the task's body — the
    second clause, on a later pass.

    "...leaving whatever the task already holds." This is the migrated
    case exactly: a task projected under the old rule whose name was
    shortened, carrying the step's full former text in its body, matching
    what the system last wrote — the retained value the healing rules
    would otherwise licence rewriting.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        description=None,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    former_text = "The step's full former text, spilled here when the name was cut."
    collaborators.clickup.seed_task(
        LIST_ID,
        "task-legacy",
        name=f"Conform the title to the style…{SEPARATOR}listing.title-conforms",
        body=former_text,
    )
    collaborators.mapping.seed_task(
        "listing.title-conforms",
        "task-legacy",
        retained_name=(
            f"Conform the title to the style…{SEPARATOR}listing.title-conforms"
        ),
        retained_body=former_text,
    )

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the body is left exactly as it stands.
    assert collaborators.clickup.tasks["task-legacy"].body == former_text
    assert collaborators.clickup.body_writes_for("task-legacy") == []


async def test_a_task_is_assigned_to_the_steps_people() -> None:
    """Scenario: A task is assigned to the step's people.

    WHEN a task is projected for a step naming two assignees the roster
    records ClickUp user ids for
    THEN the created task is assigned to both of those ClickUp users.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        assignees=(ALICE, BOHDAN),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    task_id = _task_id_named(collaborators, "Conform the title")
    # SPECIFIED: assigned to both, resolved through the roster to their
    # ClickUp users — never to the roster's own identifiers.
    assert set(collaborators.clickup.tasks[task_id].assignees) == {
        ALICE_CLICKUP,
        BOHDAN_CLICKUP,
    }


async def test_an_existing_unowned_task_gains_its_steps_assignees() -> None:
    """Scenario: An existing unowned task gains its step's assignees.

    WHEN a pass runs over a task the system assigned to nobody and whose
    step now names an assignee
    THEN the task is assigned to that person.

    SPECIFIED, and the reason reconciliation is not create-time only: "so
    that tasks projected before steps had assignees stop being unowned —
    which is the problem this field exists to solve, and solving it only
    for new work would leave every in-flight launch as it is". The
    mapping below holds **no** retained assignees, the state every
    mapping made before this change is in, which the spec says is "to be
    treated as having last been set to nobody".
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    composed = f"Conform the title to the style guide{SEPARATOR}listing.title-conforms"
    collaborators.clickup.seed_task(LIST_ID, "task-legacy", name=composed, assignees=())
    collaborators.mapping.seed_task(
        "listing.title-conforms",
        "task-legacy",
        retained_name=composed,
        retained_assignees=None,
    )

    await _converge(_start(playbook), playbook, collaborators)

    assert set(collaborators.clickup.tasks["task-legacy"].assignees) == {ALICE_CLICKUP}


async def test_a_persons_own_assignment_change_is_not_overwritten() -> None:
    """Scenario: A person's own assignment change is not overwritten.

    WHEN a task's assignees have been changed in ClickUp from what the
    system last set, and a pass runs
    THEN the system leaves the task's assignees as they stand.

    The task below is assigned to Bohdan while the system last set Alice
    and the step still names Alice — so an implementation that simply
    reconciles towards the step would reassign it, discarding a person's
    deliberate handover.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    composed = f"Conform the title to the style guide{SEPARATOR}listing.title-conforms"
    collaborators.clickup.seed_task(
        LIST_ID, "task-1", name=composed, assignees=(BOHDAN_CLICKUP,)
    )
    collaborators.mapping.seed_task(
        "listing.title-conforms",
        "task-1",
        retained_name=composed,
        retained_assignees=(ALICE_CLICKUP,),
    )

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: left as they stand.
    assert collaborators.clickup.tasks["task-1"].assignees == (BOHDAN_CLICKUP,)


async def test_an_assignee_with_no_clickup_account_is_reported_not_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: An assignee with no ClickUp account is reported, not
    silently dropped.

    WHEN a task is projected for a step naming an assignee the roster
    carries without a ClickUp user id
    THEN the task is created and assigned to the step's remaining
    assignees, and the omission is reported.

    SPECIFIED: reported "as a warning-level application log record naming
    the step, the person and the task rather than silently dropped — the
    pass itself succeeds, since a failed run would hide a data gap behind
    a retry".
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        assignees=(ALICE, NO_ACCOUNT),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    with caplog.at_level(logging.WARNING):
        await _converge(_start(playbook), playbook, collaborators)

    task_id = _task_id_named(collaborators, "Conform the title")
    # SPECIFIED: the task is created, and carries the remaining assignee.
    assert set(collaborators.clickup.tasks[task_id].assignees) == {ALICE_CLICKUP}

    # SPECIFIED: the omission is reported at warning level or above,
    # naming the step and the person.
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    reported = " ".join(warnings)
    assert warnings, "the omitted assignee was dropped without a warning record"
    assert "listing.title-conforms" in reported
    assert NO_ACCOUNT in reported or "Chris Newcomer" in reported


async def test_a_step_activated_mid_launch_is_projected() -> None:
    """Scenario: A step activated mid-launch is projected.

    WHEN a `human` step is activated after a launch started and the next
    pass runs
    THEN a task is created for it in the launch's list like any other
    step's.

    The pre-change scenario is *A step authored mid-launch is projected*;
    activation is now the event that puts a step into the served set, so
    the same guarantee has to hold for it or every newly activated step
    would wait for the next launch.
    """
    before_activation = _step(
        identifier="listing.a-plus-content",
        name="Add A+ content",
        status=StepStatus.IN_DEVELOPMENT,
        assignees=(ALICE,),
    )
    first_playbook = _playbook(steps=(before_activation,))
    collaborators = _Collaborators()
    launch = _start(first_playbook)

    await _converge(launch, first_playbook, collaborators)
    assert collaborators.clickup.calls_named("create_task") == []

    activated = _step(
        identifier="listing.a-plus-content",
        name="Add A+ content",
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
    )
    second_playbook = _playbook(steps=(activated,))

    await _converge(launch, second_playbook, collaborators)

    created = _created_named(collaborators, "Add A+ content")
    assert "listing.a-plus-content" in created["name"]


async def test_a_persons_body_note_survives_a_wording_edit() -> None:
    """Scenario: A person's body note survives a wording edit.

    WHEN a person has edited a mapped task's body, the task's name still
    carries the system's retained composition, the step's name is edited,
    and the pass runs
    THEN the task's name is rewritten to the current composition
    AND the task's body is left exactly as the person wrote it.

    Re-established here rather than left to the existing test, because
    the body's *meaning* changes with this delta: it used to be the
    overflow of a too-long name, and is now the step's description. The
    guard — the two fields are guarded independently — must survive that.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide, revised",
        description="The authored description.",
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    retained_name = (
        f"Conform the title to the style guide{SEPARATOR}listing.title-conforms"
    )
    person_note = "The authored description.\n\nNB: waiting on legal — Alice"
    collaborators.clickup.seed_task(
        LIST_ID,
        "task-1",
        name=retained_name,
        body=person_note,
        assignees=(ALICE_CLICKUP,),
    )
    collaborators.mapping.seed_task(
        "listing.title-conforms",
        "task-1",
        retained_name=retained_name,
        retained_body="The authored description.",
        retained_assignees=(ALICE_CLICKUP,),
    )

    await _converge(_start(playbook), playbook, collaborators)

    task = collaborators.clickup.tasks["task-1"]
    # SPECIFIED: the name follows the step's current wording...
    assert task.name == (
        "Conform the title to the style guide, revised"
        f"{SEPARATOR}listing.title-conforms"
    )
    # ...and the person's body note is left exactly as written.
    assert task.body == person_note


async def test_an_unedited_task_heals_to_the_new_composition() -> None:
    """Scenario: An unedited legacy task starts healing — under the new
    composition (`tasks.md` 4.7).

    `design.md`'s risk register claims that "an unedited task composes to
    exactly what it already carries and heals to it", because the new
    `name` is the text that was the description. This test is that claim
    made checkable: a task carrying the old composition, with no retained
    values recorded, is observed carrying exactly what the system would
    now compose — so it is adopted and healed thereafter rather than
    treated as person-edited and frozen forever.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        description=None,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    old_composition = (
        f"Conform the title to the style guide{SEPARATOR}listing.title-conforms"
    )
    collaborators.clickup.seed_task(LIST_ID, "task-legacy", name=old_composition)
    mapping = collaborators.mapping.seed_task(
        "listing.title-conforms", "task-legacy", retained_name=None
    )

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the current content is adopted as the retained
    # composition, so the task heals under the rules thereafter.
    assert mapping.retained_name == old_composition
    # SPECIFIED corollary: adoption is not a rewrite — nothing was sent.
    assert [
        payload
        for payload in collaborators.clickup.calls_named("update_task")
        if "name" in payload["fields"]
    ] == []


async def test_an_over_long_name_is_shortened_and_never_spills_into_the_body() -> None:
    """Scenario: An over-long name is shortened rather than failing.

    WHEN a task is projected for a step whose composed name exceeds the
    length the task system accepts
    THEN the task is created with a shortened name that fits, ending in
    `… · ` followed by the step's identifier in full
    AND no more of the name is surrendered than the limit requires
    AND the surrendered text is not written into the body.

    The third clause is the one this change sharpens: "Shortening SHALL
    NOT move the surrendered text into the body: the body belongs to the
    description, and overwriting it with a fragment of the name would
    displace what an author wrote." The step below carries a description,
    so a shortening rule that still spilled would overwrite it.
    """
    # Long enough to exceed `CLICKUP_TASK_NAME_LIMIT` (2048, measured
    # against the live API), which is what the scenario is about.
    long_name = "Conform the title to the style guide " + ("and check it " * 400)
    authored_body = "The description the author wrote."
    step = _step(
        identifier="listing.title-conforms",
        name=long_name.strip(),
        description=authored_body,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    assert len(created) == 1
    name = created[0]["name"]
    # SPECIFIED: shortened, ending in the ellipsis, the separator and the
    # identifier in full.
    assert name.endswith(f"…{SEPARATOR}listing.title-conforms")
    assert len(name) < len(f"{long_name.strip()}{SEPARATOR}listing.title-conforms")
    # SPECIFIED: the surrendered text is not written into the body — the
    # body is the author's description and nothing else.
    task_id = _task_id_named(collaborators, "listing.title-conforms")
    assert collaborators.clickup.tasks[task_id].body == authored_body


# ---------------------------------------------------------------------------
# The projection filter: kind and status
# ---------------------------------------------------------------------------


async def test_automated_steps_are_never_projected() -> None:
    """Scenario: Automated steps are never projected.

    WHEN the reconciliation pass runs and a step's kind is `automated`
    THEN no task is created for it, whether or not it needs confirmation.

    The filter moves from the removed `human-attested` execution mode to
    `kind`, and the confirmation flag is explicitly not part of it: an
    implementation reading "needs confirmation" as "a person is
    involved, so project it" would project the step that used to be
    `ai-assisted`, which was never projected.
    """
    unconfirmed = _step(
        identifier="price.buy-box-check",
        name="Watch the Buy Box",
        gate="live",
        kind=StepKind.AUTOMATED,
        needs_confirmation=False,
        automation_brief="Buy Box share is at or above 90%.",
        handler="price.buy_box_check",
    )
    confirmed = _step(
        identifier="creative.image-brief",
        name="Draft the hero image brief",
        gate="ignition",
        kind=StepKind.AUTOMATED,
        needs_confirmation=True,
        automation_brief="A hero image brief exists and reads coherently.",
        handler="creative.image_brief",
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(unconfirmed, confirmed))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = [
        payload["name"] for payload in collaborators.clickup.calls_named("create_task")
    ]
    assert created == [], f"an automated step was projected: {created}"


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(StepStatus.DRAFT, id="draft"),
        pytest.param(StepStatus.IN_DEVELOPMENT, id="in-development"),
        pytest.param(StepStatus.RETIRED, id="retired"),
    ],
)
async def test_a_step_that_is_not_active_is_never_projected(
    status: StepStatus,
) -> None:
    """Scenario: A step that is not active is never projected.

    WHEN the reconciliation pass runs and a `human` step's status is
    `draft`, `in-development` or `retired`
    THEN no task is created for it.

    All three are exercised because the spec names all three, and because
    they arrive by different routes: a draft was never served, an
    `in-development` step may have been served and been de-activated, and
    a retired one is the case that already existed.
    """
    step = _step(
        identifier="listing.a-plus-content",
        name="Add A+ content",
        status=status,
        assignees=(ALICE,),
    )
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = [
        payload["name"] for payload in collaborators.clickup.calls_named("create_task")
    ]
    assert created == [], f"a {status} step was projected: {created}"
