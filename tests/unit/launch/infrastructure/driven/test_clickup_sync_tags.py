"""A projected task carries its step's gate and discipline as tags.

Derived strictly from the delta spec of the OpenSpec change
`tag-tasks-with-gate-and-discipline`:
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/launch-clickup-sync/spec.md`

Covers every scenario of the ADDED requirement *A projected task carries
its step's gate and discipline as tags* except *No tag is written during a
stand-down*, which is not observable at this level — the stand-down happens
in the job, before the pass body — and is covered at the job level in
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py`.

The same delta **modifies** *Human steps are projected as tasks carrying
their name, description and assignees*, narrowing one clause of its
assignee paragraph ("Assignees are the one *retained* field where that
reading is right"). That modification changes no scenario — all twenty are
carried into the delta verbatim — and supersedes nothing this directory's
existing tests assert, so none of them is touched, duplicated or
superseded here. See
`openspec/changes/tag-tasks-with-gate-and-discipline/test-manifest.md` for
the full accounting.

## The two things these tests exist to discriminate

1. **Nothing space-level is reached.** `design.md` measured on 2026-08-26
   that attaching an unknown tag creates it in the task's space, which
   deleted a whole seeding subsystem six earlier drafts had built on the
   opposite premise. `_FakeClickUp` therefore offers *only* the four
   operations the pass may use, and records every attribute probed on it
   that it does not have — so an implementation reaching for a vocabulary
   read, a space resolution or a tag creation fails here by name rather
   than silently.
2. **Tags are added, never removed and never corrected.** The fake offers
   no removal at all, and `_assert_nothing_removed` reads the probe record.
   A stale `gate:commit` accumulating alongside `gate:listable` is the
   *specified* outcome, asserted as such rather than tolerated.

## INVENTED shapes

The harness follows `test_clickup_projection_step_fields.py` in this
directory — `converge_launch(launch=, playbook=, clickup=, mapping=,
read_product=, roster=, folder_id=)` over in-memory fakes — extended with:

- `clickup.add_task_tag(task_id, tag_name)`, the port operation this
  change's `clickup-task-client` delta adds. Its two argument names are
  fixed by `tasks.md` 1.4; that the pass calls it *positionally* is not,
  and `_FakeClickUp.add_task_tag` accepts either. Correction point:
  `_FakeClickUp`.
- `tags` on the create payload and on what `list_tasks` reports, per
  `tasks.md` 1.1/1.3. Read through `_tags_in`/`_tag_names`, so no wire
  container is pinned.

Fixed by `tasks.md` 2.1, so treated as SPECIFIED: the composed names are
`gate:<step.gate>` and `discipline:<step.discipline.value>` — which the
requirement states independently ("named `gate:<gate identifier>` and
`discipline:<discipline value>`, using the identifiers the playbook and
the shared vocabulary already fix").

## Expected first-run state

`converge_launch` composes no tags and the ClickUp port has no
`add_task_tag`, so every test here is expected to fail on an absent target
— the create-path tests on a missing `tags` claim, the backfill tests on
`add_task_tag` never being called. Per `ai-toolkit:testing` that
establishes only absence, and nothing about whether these assertions are
well-formed.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` at the worktree root —
1064 passed, 0 failed.
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

STEP_ID: Final = "listing.title-conforms"
STEP_NAME: Final = "Conform the title to the style guide"
STEP_GATE: Final = "listable"
STEP_DISCIPLINE: Final = Discipline.LISTING

# SPECIFIED: `gate:<gate identifier>` and `discipline:<discipline value>`.
# The gate and the discipline are deliberately *different* words here
# (`listable` vs `listing`), so an implementation that swapped the two
# prefixes fails on the exact-set assertions rather than passing.
GATE_TAG: Final = f"gate:{STEP_GATE}"
DISCIPLINE_TAG: Final = f"discipline:{STEP_DISCIPLINE.value}"

# A second step, used where a test needs the projection to keep working
# while the tag concern is faulting.
OTHER_STEP_ID: Final = "finance.unit-economics"
OTHER_STEP_NAME: Final = "Check the unit economics still clear"
OTHER_GATE_TAG: Final = "gate:commit"
OTHER_DISCIPLINE_TAG: Final = f"discipline:{Discipline.FINANCE.value}"

# Tags outside the two owned prefixes — a person's own labels, exactly as
# the requirement describes them.
FOREIGN_TAGS: Final = ("urgent", "waiting-on-supplier")

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_CLICKUP: Final = "clickup-alice"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_clickup_projection_step_fields.py`
# ---------------------------------------------------------------------------


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
        "name": STEP_NAME,
        "description": None,
        "gate": STEP_GATE,
        "discipline": STEP_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """An `active` `automated` blocking filler, so no filler is ever
    projected and every tag assertion below is about the test's own steps."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
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


def _composed_name(step_id: str = STEP_ID, name: str = STEP_NAME) -> str:
    return f"{name}{SEPARATOR}{step_id}"


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
        self, person_id: str, display_name: str, *, clickup_user_id: str | None
    ) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id = clickup_user_id
        self.active = True


class _FakeRoster:
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
    return _FakeRoster((_Person(ALICE, "Alice Admin", clickup_user_id=ALICE_CLICKUP),))


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
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


def _tags_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    """Any tag-bearing field of a create payload. Returns (present, value).

    Matched on the key rather than pinned to one spelling, so a `camelCase`
    variant still reads as a claim — the create-without-tags rule turns on
    telling "no claim" from "an empty claim", and a missed spelling would
    silently read as the former.
    """
    for key, value in fields.items():
        if key.lower() == "tags":
            return True, value
    return False, None


def _tag_names(value: Any) -> set[str]:
    """The names inside a tag claim, whatever container it arrived in."""
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    names: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
            if name is not None:
                names.add(str(name))
        else:
            names.add(str(item))
    return names


class _TagWriteRefused(RuntimeError):
    """What the ClickUp port raises when a tag write fails.

    The `clickup-task-client` delta requires the client to surface the
    failure rather than swallow it; no artifact names a type, so this file
    raises its own and the pass is only ever required to *survive* it.
    """


class _FakeClickUp:
    """In-memory ClickUp, offering exactly the operations the pass may use.

    Anything else the pass reaches for is recorded in `probed` and raises
    `AttributeError` in the ordinary way — so `hasattr`/`getattr(..., None)`
    still behave, while a space read, a tag creation or a tag *removal*
    leaves a named trace the assertions below can read.
    """

    def __init__(self) -> None:
        self._probed: list[str] = []
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self.refuse_tags_matching: tuple[str, ...] = ()
        self._next = 0

    def __getattr__(self, name: str) -> Any:
        probed = self.__dict__.get("_probed")
        if probed is not None and not name.startswith("__"):
            probed.append(name)
        raise AttributeError(name)

    @property
    def probed(self) -> tuple[str, ...]:
        return tuple(self._probed)

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    # -- writes ------------------------------------------------------------

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        payload: dict[str, Any] = {"list_id": list_id, "name": name, **fields}
        if description is not None:
            payload["description"] = description
        self.calls.append(("create_task", payload))
        task_id = self._identifier("task")
        has_tags, tags = _tags_in(payload)
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            tags=tuple(sorted(_tag_names(tags))) if has_tags else (),
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        if "name" in fields:
            task.name = fields["name"]
        has_tags, _ = _tags_in(fields)
        assert not has_tags, (
            "tags were sent on an update body; `design.md` measured that "
            "tags do not ride `PUT /task/{id}` at all — they go in the "
            "create body or through the add-tag call"
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag_name": tag_name}))
        if any(tag_name.startswith(prefix) for prefix in self.refuse_tags_matching):
            raise _TagWriteRefused(f"ClickUp refused the tag {tag_name!r}")
        task = self.tasks[task_id]
        if tag_name not in task.tags:
            task.tags = (*task.tags, tag_name)

    # -- reads -------------------------------------------------------------

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

    def tag_writes(self) -> list[tuple[str, str]]:
        return [
            (payload["task_id"], payload["tag_name"])
            for payload in self.calls_named("add_task_tag")
        ]


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
    """In-memory stand-in for the two mapping tables.

    Deliberately unchanged by this delta: "No database migration: the
    change retains no new state, so `ClickUpTaskMapping` and its table are
    untouched." There is no retained-tags column here, and an
    implementation reaching for one is recorded in `probed`.
    """

    def __init__(self) -> None:
        self._probed: list[str] = []
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}
        self.replacements: list[tuple[str, str]] = []

    def __getattr__(self, name: str) -> Any:
        probed = self.__dict__.get("_probed")
        if probed is not None and not name.startswith("__"):
            probed.append(name)
        raise AttributeError(name)

    @property
    def probed(self) -> tuple[str, ...]:
        return tuple(self._probed)

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
        retained_name: str | None = None,
        retained_assignees: tuple[str, ...] | None = None,
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            retained_name=retained_name,
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
    """INVENTED call shape — see the module docstring. Single correction
    point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        roster=collaborators.roster,
        folder_id=folder_id,
    )


# ---------------------------------------------------------------------------
# Shared assertions about what the pass must never reach for
# ---------------------------------------------------------------------------

_SPACE_WORDS: Final = ("space", "vocabulary", "seed", "ensure_tag", "create_tag")
_REMOVAL_WORDS: Final = ("remove", "delete", "untag", "detach", "clear_tag")


def _assert_nothing_space_level(collaborators: _Collaborators) -> None:
    """SPECIFIED: "no space-level tag request — no tag creation, and no read
    of a space's tags — is sent before or after the create", and "the system
    SHALL NOT maintain, seed, or verify any tag vocabulary of its own, and
    SHALL read and write nothing about a launch's space"."""
    reached = [
        name
        for name in collaborators.clickup.probed
        if any(word in name.lower() for word in _SPACE_WORDS)
    ]
    called = [
        name
        for name, _ in collaborators.clickup.calls
        if any(word in name.lower() for word in _SPACE_WORDS)
    ]
    assert reached == [] and called == [], (
        "the pass reached for a space-level tag operation. A tag needs no "
        "prior existence, so this change seeds nothing and reaches no "
        f"space. Probed: {reached}; called: {called}"
    )


def _assert_nothing_removed(collaborators: _Collaborators) -> None:
    """SPECIFIED: "The system SHALL NOT remove a tag from a task, and SHALL
    NOT replace one owned tag with another"."""
    reached = [
        name
        for name in collaborators.clickup.probed
        if any(word in name.lower() for word in _REMOVAL_WORDS)
    ]
    assert reached == [], f"the pass reached for a tag removal: {reached}"


def _created_for(collaborators: _Collaborators, step_id: str) -> dict[str, Any]:
    created = [
        payload
        for payload in collaborators.clickup.calls_named("create_task")
        if step_id in payload["name"]
    ]
    assert len(created) == 1, (
        f"expected exactly one task created for {step_id!r}, got "
        f"{[payload['name'] for payload in collaborators.clickup.calls_named('create_task')]}"
    )
    payload: dict[str, Any] = created[0]
    return payload


def _seed_mapped_task(
    collaborators: _Collaborators,
    *,
    step_id: str = STEP_ID,
    step_name: str = STEP_NAME,
    task_id: str = "task-mapped",
    tags: tuple[str, ...] = (),
) -> _FakeTask:
    """A task projected before tagging existed: present in ClickUp, mapped,
    and carrying whatever tags the test scripts."""
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID
    composed = _composed_name(step_id, step_name)
    task = collaborators.clickup.seed_task(
        LIST_ID,
        task_id,
        name=composed,
        assignees=(ALICE_CLICKUP,),
        tags=tags,
    )
    collaborators.mapping.seed_task(
        step_id,
        task_id,
        retained_name=composed,
        retained_assignees=(ALICE_CLICKUP,),
    )
    return task


#: A second, plainly projectable step. Every test below whose own assertion
#: is the *absence* of a tag write carries one, and asserts that its task
#: **was** tagged on the same pass.
#:
#: Without it, those tests pass against a system that cannot tag at all --
#: which is exactly the state this pass was written in, and the fourth
#: failure state `ai-toolkit:testing` names: "it passed on its first run,
#: before any implementation existed ... an alarm, not a result". The
#: control turns each of them into a test that fails on an absent target
#: and, once tagging exists, discriminates on the absence it was written
#: for.
def _control_step() -> StepDefinition:
    return _step(
        identifier=OTHER_STEP_ID,
        name=OTHER_STEP_NAME,
        gate="commit",
        discipline=Discipline.FINANCE,
    )


def _assert_the_pass_did_tag(collaborators: _Collaborators) -> None:
    """The control: the pass tagged the control step's own new task on this
    run, so an absence asserted elsewhere in the same test is the rule at
    work rather than tagging being absent altogether."""
    created = _created_for(collaborators, OTHER_STEP_ID)
    has_tags, tags = _tags_in(created)
    assert has_tags and _tag_names(tags) == {
        OTHER_GATE_TAG,
        OTHER_DISCIPLINE_TAG,
    }, (
        "the control step's task was not created carrying its tags, so no "
        "absence asserted in this test establishes anything -- the pass "
        f"does not tag at all. Create payload: {created!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: A projected task carries its step's gate and discipline as
# tags
# ---------------------------------------------------------------------------


async def test_a_newly_projected_task_carries_both_tags() -> None:
    """Scenario: A newly projected task carries both tags.

    WHEN a task is projected for an `active` `human` step whose gate is
    `listable` and whose discipline is `listing`
    THEN the created task carries the tags `gate:listable` and
    `discipline:listing`
    AND no space-level tag request — no tag creation, and no read of a
    space's tags — is sent before or after the create.

    Asserted on the **create payload**, not merely on the task's end state:
    "A task SHALL be created carrying both of its step's tags ... its tags
    travel inside the creation". An implementation creating the task bare
    and adding the two afterwards would leave the same end state while
    spending two extra calls per task on every new launch, which is exactly
    what the create-body route exists to avoid.
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = _created_for(collaborators, STEP_ID)
    has_tags, tags = _tags_in(created)
    assert has_tags, f"the create carried no tags at all: {created!r}"
    # SPECIFIED: exactly the two tags the step yields — a third of the
    # system's own invention would be a vocabulary this change does not own.
    assert _tag_names(tags) == {GATE_TAG, DISCIPLINE_TAG}

    # SPECIFIED: no space-level tag request, before or after.
    _assert_nothing_space_level(collaborators)
    _assert_nothing_removed(collaborators)


async def test_an_existing_untagged_task_gains_its_tags() -> None:
    """Scenario: An existing untagged task gains its tags.

    WHEN a pass runs over a mapped task that was projected before tagging
    existed
    THEN the task gains its step's `gate:` and `discipline:` tags.

    SPECIFIED, and the reason this is not create-time only: "so that tasks
    projected before this requirement existed gain their tags rather than
    the behaviour reaching only launches started afterwards — the same
    obligation the assignee requirement already carries".
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()
    task = _seed_mapped_task(collaborators, tags=())

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the existing task is backfilled, not replaced.
    assert collaborators.clickup.calls_named("create_task") == []
    # SPECIFIED: both tags, added through the add-tag call.
    assert set(collaborators.clickup.tag_writes()) == {
        ("task-mapped", GATE_TAG),
        ("task-mapped", DISCIPLINE_TAG),
    }
    assert set(task.tags) == {GATE_TAG, DISCIPLINE_TAG}

    _assert_nothing_space_level(collaborators)
    _assert_nothing_removed(collaborators)


async def test_a_task_already_carrying_its_tags_is_left_alone() -> None:
    """Scenario: A task already carrying its tags is left alone.

    WHEN a pass runs over a mapped task already carrying both of its step's
    tags
    THEN no tag write is sent for that task.

    This is the scenario that keeps the steady-state cost at zero writes
    (`design.md`, Goals). Its assertion is the absence of a call, so it is
    also the one an implementation that re-sent both tags every pass would
    fail alone — every other test here would stay green, because a repeated
    add is measured harmless.
    """
    playbook = _playbook(steps=(_step(), _control_step()))
    collaborators = _Collaborators()
    _seed_mapped_task(collaborators, tags=(GATE_TAG, DISCIPLINE_TAG))

    await _converge(_start(playbook), playbook, collaborators)

    # The control: the pass demonstrably tagged on this run.
    _assert_the_pass_did_tag(collaborators)

    # SPECIFIED: no tag write is sent for that task.
    assert collaborators.clickup.tag_writes() == [], (
        "a tag was written for a task already carrying both of its tags"
    )
    _assert_nothing_removed(collaborators)


async def test_a_persons_own_tags_are_never_touched() -> None:
    """Scenario: A person's own tags are never touched.

    WHEN a pass runs over a mapped task carrying tags outside the `gate:`
    and `discipline:` prefixes
    THEN those tags are left exactly as they stand.

    The task below is missing one owned tag, so the pass is **actively
    writing** while the person's two labels stand — which is the state the
    rule has to survive. A task where the pass does nothing at all would
    satisfy this scenario for the wrong reason.

    SPECIFIED: "A tag carrying neither prefix belongs to whoever put it
    there: it SHALL NOT be written or removed by any pass, and SHALL have
    no bearing on what any pass does."
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()
    task = _seed_mapped_task(collaborators, tags=(*FOREIGN_TAGS, DISCIPLINE_TAG))

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the foreign tags stand exactly as they were.
    assert set(FOREIGN_TAGS).issubset(set(task.tags)), (
        f"a person's own tags were lost: {task.tags}"
    )
    # SPECIFIED: no pass writes them, either — the only write is the owned
    # tag that was missing.
    assert collaborators.clickup.tag_writes() == [("task-mapped", GATE_TAG)], (
        "the pass wrote something other than the one missing owned tag: "
        f"{collaborators.clickup.tag_writes()}"
    )
    _assert_nothing_removed(collaborators)


async def test_a_step_moved_between_gates_keeps_its_original_gate_tag() -> None:
    """Scenario: A step moved between gates keeps its original gate tag.

    WHEN a step whose task carries `gate:commit` is moved to the `listable`
    gate and a pass runs
    THEN the task carries `gate:listable` in addition to `gate:commit`, and
    no tag is removed.

    This is an **accepted cost stated as a requirement**, not a defect to
    be tidied: "Correcting it would require deciding whether a person's own
    retagging is preserved or overruled, which this requirement
    deliberately does not settle." So the stale tag's survival is asserted
    positively. A later change that adds correction supersedes this test
    rather than fixing it.
    """
    playbook = _playbook(steps=(_step(gate=STEP_GATE),))
    collaborators = _Collaborators()
    task = _seed_mapped_task(collaborators, tags=("gate:commit", DISCIPLINE_TAG))

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the current gate tag is added...
    assert GATE_TAG in set(task.tags)
    # ...*in addition to* the one it was projected with.
    assert "gate:commit" in set(task.tags), (
        "the stale gate tag was removed; this change has no removal path "
        "and the accumulation is the stated cost"
    )
    assert collaborators.clickup.tag_writes() == [("task-mapped", GATE_TAG)]
    _assert_nothing_removed(collaborators)


async def test_a_hand_removed_tag_is_added_back() -> None:
    """Scenario: A hand-removed tag is added back.

    WHEN a person removes a mapped task's `gate:` tag in ClickUp and the
    next pass runs
    THEN the tag is added back to the task.

    Written as two passes with a hand edit between them, which is what the
    scenario describes and what a single seeded state cannot show: the
    first pass establishes the tag was there, the removal is a person's,
    and the second pass restores it. SPECIFIED, with its cost stated in
    the same breath: "the system retains nothing with which to tell 'never
    added' from 'added and then removed'. A person therefore cannot keep a
    projected task untagged."
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)

    created = _created_for(collaborators, STEP_ID)
    _, tags = _tags_in(created)
    assert _tag_names(tags) == {GATE_TAG, DISCIPLINE_TAG}
    task = next(iter(collaborators.clickup.tasks.values()))
    assert set(task.tags) == {GATE_TAG, DISCIPLINE_TAG}

    # A person removes the gate tag in ClickUp.
    task.tags = tuple(tag for tag in task.tags if not tag.startswith("gate:"))

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: the tag is added back.
    assert GATE_TAG in set(task.tags), (
        "a hand-removed owned tag was not restored on the next pass"
    )
    # SPECIFIED corollary: restored through the add-tag call, not by
    # re-projecting the task.
    assert collaborators.clickup.tag_writes() == [(task.id, GATE_TAG)]
    assert len(collaborators.clickup.calls_named("create_task")) == 1


def _departure_cases() -> list[Any]:
    """The four grounds on which a step leaves the projection.

    SPECIFIED, and enumerated in full deliberately: the requirement
    references *A step that is not active leaves the loop* "rather than
    paraphrased", because that requirement "states that projection turns on
    three fields and that 'a rule naming fewer would leave the rest
    undefined'". A parametrisation covering a subset would reintroduce the
    gap the reference was written to close. The fourth case — a step the
    served playbook does not define at all — arrives on the projection
    requirement's own ground.
    """
    return [
        pytest.param(
            (_step(status=StepStatus.RETIRED),),
            STEP_ID,
            id="status-retired",
        ),
        pytest.param(
            (_step(status=StepStatus.IN_DEVELOPMENT),),
            STEP_ID,
            id="status-in-development",
        ),
        pytest.param(
            (
                _step(
                    kind=StepKind.AUTOMATED,
                    assignees=(),
                    automation_brief="The title is checked against the guide.",
                    handler="listing.title_conforms",
                ),
            ),
            STEP_ID,
            id="kind-automated",
        ),
        pytest.param(
            (_step(hazard=Hazard.PROHIBITED_TACTIC),),
            STEP_ID,
            id="hazard-prohibited-tactic",
        ),
        pytest.param((), "listing.a-step-the-playbook-dropped", id="undefined"),
    ]


@pytest.mark.parametrize(("departed", "step_id"), _departure_cases())
async def test_a_step_that_has_left_the_projection_is_not_tagged(
    departed: tuple[StepDefinition, ...], step_id: str
) -> None:
    """Scenario: A step that has left the projection is not tagged.

    WHEN a pass runs and a mapped task's step is not defined by the served
    playbook, or is not `active`, or is no longer of kind `human`, or
    carries the `prohibited-tactic` hazard
    THEN no tag is written for that task.

    SPECIFIED: "Tagging SHALL follow the projection it belongs to and never
    run ahead of it." The `undefined` case is the one that catches a
    backfill driven from the *mapping* rather than from the playbook's
    served steps — an implementation iterating every mapped task would tag
    a step the playbook no longer defines, and every other case here would
    still pass.
    """
    playbook = _playbook(steps=(*departed, _control_step()))
    collaborators = _Collaborators()
    _seed_mapped_task(collaborators, step_id=step_id, tags=())

    await _converge(_start(playbook), playbook, collaborators)

    # The control: the pass demonstrably tagged on this run, so the absence
    # asserted below is the departure rule and not an absent implementation.
    _assert_the_pass_did_tag(collaborators)

    # SPECIFIED: no tag is written for that task.
    assert collaborators.clickup.tag_writes() == [], (
        f"a departed step's task was tagged: {collaborators.clickup.tag_writes()}"
    )
    # SPECIFIED corollary: nor is it re-projected carrying tags.
    assert [
        payload
        for payload in collaborators.clickup.calls_named("create_task")
        if step_id in payload["name"]
    ] == []
    _assert_nothing_removed(collaborators)


async def test_a_tag_that_cannot_be_set_is_reported_and_not_fatal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A tag that cannot be set on a task is reported, not fatal.

    WHEN a pass adds a missing tag to a mapped task and that tag write
    fails
    THEN the pass continues and still succeeds
    AND the omission is reported as a warning naming the step, the tag and
    the task
    AND the task's other missing tag is still added.

    SPECIFIED, and the reason the failure is caught per **tag** rather than
    per pass: "a fault in the tag concern SHALL cost tags and nothing else
    — never the projection of a launch's work, and never the completion
    intake that travels on the same pass". A second, unprojected step is in
    the playbook below so that "and nothing else" is asserted rather than
    assumed: an implementation that let the fault abort the launch's pass
    would leave it unprojected.
    """
    other = _step(
        identifier=OTHER_STEP_ID,
        name=OTHER_STEP_NAME,
        gate="commit",
        discipline=Discipline.FINANCE,
    )
    playbook = _playbook(steps=(_step(), other))
    collaborators = _Collaborators()
    task = _seed_mapped_task(collaborators, tags=())
    collaborators.clickup.refuse_tags_matching = ("gate:",)

    with caplog.at_level(logging.WARNING):
        # SPECIFIED: the pass continues and still succeeds — no
        # `pytest.raises`; returning normally is the assertion.
        await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the task's other missing tag is still added.
    assert ("task-mapped", DISCIPLINE_TAG) in collaborators.clickup.tag_writes(), (
        "the failing gate tag took the discipline tag down with it"
    )
    assert DISCIPLINE_TAG in set(task.tags)
    # SPECIFIED: the failed one is not on the task.
    assert GATE_TAG not in set(task.tags)

    # SPECIFIED: a fault in the tag concern costs tags and nothing else —
    # the launch's other work is still projected.
    other_created = _created_for(collaborators, OTHER_STEP_ID)
    assert _tag_names(_tags_in(other_created)[1]) == {
        OTHER_GATE_TAG,
        OTHER_DISCIPLINE_TAG,
    }

    # SPECIFIED: reported as a warning-level record naming the step, the
    # tag and the task.
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert warnings, "the failed tag write was swallowed without a warning record"
    reported = " ".join(warnings)
    assert STEP_ID in reported, f"the warning does not name the step: {reported!r}"
    assert GATE_TAG in reported, f"the warning does not name the tag: {reported!r}"
    assert "task-mapped" in reported, (
        f"the warning does not name the task: {reported!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - *No tag is written during a stand-down*. Not observable here: the
#   stand-down returns in the job before the pass body is entered, so
#   `converge_launch` has no stand-down state to be in. Covered at the job
#   level in
#   `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py`.
# - *A graduated launch's tasks are never tagged and never backfilled.*
#   Stated inside the tag requirement, but on another requirement's ground
#   ("as *Each launch is projected into its own ClickUp list* specifies"),
#   and it carries no `#### Scenario:` of its own. The existing
#   `test_a_graduated_launch_is_left_alone` already asserts that a
#   graduated launch causes no ClickUp call whatever, which subsumes a tag
#   write; a duplicate here would assert nothing further.
# - That the add-if-missing judgement costs **no extra read** (`design.md`,
#   Goals: the tags "arrive in the task list it already fetches"). A
#   performance property, stated in Goals rather than in any scenario, and
#   the fake's `list_tasks` call record is where it would be asserted if a
#   scenario ever stated it.
# - Tag colour and ordering. `design.md` puts both out of scope.
# - Tags on anything other than a projected task — the launch list itself,
#   metric conditions, automated steps. Named as non-goals in
#   `proposal.md`; the automated-step half is covered by the departure
#   parametrisation above, and the other two have no task-shaped thing to
#   assert the absence of.
# ---------------------------------------------------------------------------
