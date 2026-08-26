"""Gate and discipline tags on a projected task.

Derived from this change's delta spec:
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A projected task carries its step's
gate and discipline as tags*:

- *A newly projected task carries both tags*
- *The tag vocabulary is ensured before tags are used*
- *Ensuring the vocabulary twice is not an error*
- *An existing untagged task gains its tags*
- *A task already carrying its tags is left alone*
- *A person's own tags are never touched*
- *A step moved between gates keeps its original gate tag*
- *A step that is not served is not tagged*
- *A tag that cannot be set is reported, not fatal*

*No tag is written during a stand-down* is covered where the stand-down
itself is, in `tests/unit/launch/infrastructure/driving/
test_clickup_sync_job_stand_down.py`: that file substitutes every pass the
job drives and asserts none ran, and `ensure_tag_vocabulary` was added to
the set it substitutes. Asserting it here would need this file to
reconstruct the job, which is where the stand-down decision actually
lives.

## The tests that discriminate

Two rules here are easy to pass by accident and are asserted in their
strong form:

- **Add-only.** `test_a_step_moved_between_gates_keeps_its_original_gate_
  tag` is the one that fails an implementation which "reconciles" tags the
  way the projection reconciles assignees. The spec is explicit that the
  stale tag stays: telling a re-gated step from a person's own retagging
  needs retained state, which this change deliberately does not add.
- **Costing nothing when correct.** `test_a_task_already_carrying_its_
  tags_is_left_alone` asserts *no request was sent*, not merely that the
  tags ended up right. An implementation re-adding both tags every ten
  minutes satisfies the weaker reading and spends the API budget the
  design reserves.

## Harness

Transcribed from `test_clickup_projection_step_fields.py` in this
directory -- the same `converge_launch(...)` call over in-memory fakes,
extended with `tags` on the fake task and `add_task_tag` on the fake
client, which this change adds to those fakes too.
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
    GATE_SEQUENCE,
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
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    converge_launch,
    ensure_tag_vocabulary,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

FOLDER_ID: Final = "90110042424"
SPACE_ID: Final = "90110099999"
LIST_ID: Final = "901234002"
LAUNCH_DATE: Final = date(2027, 3, 2)

SEPARATOR: Final = " · "

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_CLICKUP: Final = "clickup-alice"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(GATE_SEQUENCE, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Conform the title to the style guide",
        "description": None,
        "gate": "listable",
        "discipline": Discipline.LISTING,
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
    projected and every assertion below is about the test's own steps."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
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
    fillers = tuple(_hold(gate) for gate in GATE_SEQUENCE if gate not in held)
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
    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


class _Person:
    def __init__(self, person_id: str, clickup_user_id: str | None) -> None:
        self.id = person_id
        self.display_name = "Alice Admin"
        self.clickup_user_id = clickup_user_id
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_Person, ...]:
        return (_Person(ALICE, ALICE_CLICKUP),)


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    status: str = "to do"
    closed: bool = False
    due_date: Any = None
    description: str | None = None
    assignees: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


class _FakeClickUp:
    def __init__(self, *, failing_tags: frozenset[str] = frozenset()) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self.space_tag_names: set[str] = set()
        self._failing_tags = failing_tags
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
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        **fields: Any,
    ) -> _CreatedTask:
        payload = {"list_id": list_id, "name": name, **fields}
        self.calls.append(("create_task", payload))
        task_id = self._identifier("task")
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            description=description,
            assignees=tuple(str(item) for item in (fields.get("assignees") or ())),
            tags=tuple(str(item) for item in (fields.get("tags") or ())),
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag": tag_name}))
        if tag_name in self._failing_tags:
            raise RuntimeError(f"ClickUp refused the tag {tag_name!r}")
        task = self.tasks[task_id]
        if tag_name not in task.tags:
            task.tags = (*task.tags, tag_name)

    async def space_id_for_folder(self, folder_id: str) -> str:
        self.calls.append(("space_id_for_folder", {"folder_id": folder_id}))
        return SPACE_ID

    async def space_tags(self, space_id: str) -> tuple[str, ...]:
        self.calls.append(("space_tags", {"space_id": space_id}))
        return tuple(sorted(self.space_tag_names))

    async def create_space_tag(self, space_id: str, name: str) -> None:
        self.calls.append(("create_space_tag", {"space_id": space_id, "name": name}))
        self.space_tag_names.add(name)

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

    # -- test-side helpers -------------------------------------------------

    def seed_task(
        self, step_id: str, task_id: str, *, retained_name: str | None = None
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            retained_name=retained_name,
        )
        self.tasks[(PRODUCT_ID, step_id)] = mapping
        return mapping


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    roster: _FakeRoster = field(default_factory=_FakeRoster)


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
    *,
    folder_id: str | None = FOLDER_ID,
) -> None:
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        roster=collaborators.roster,
        folder_id=folder_id,
    )


def _composed_name(step: StepDefinition) -> str:
    return f"{step.name}{SEPARATOR}{step.identifier}"


def _task_named(collaborators: _Collaborators, fragment: str) -> _FakeTask:
    for task in collaborators.clickup.tasks.values():
        if fragment in task.name:
            return task
    pytest.fail(f"no task carries {fragment!r} in its name")


# ---------------------------------------------------------------------------
# Requirement: A projected task carries its step's gate and discipline as
# tags
# ---------------------------------------------------------------------------


async def test_a_newly_projected_task_carries_both_tags() -> None:
    """Scenario: A newly projected task carries both tags.

    WHEN a task is projected for an `active` `human` step whose gate is
    `listable` and whose discipline is `listing`
    THEN the created task carries the tags `gate:listable` and
    `discipline:listing`.
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    task = _task_named(collaborators, "Conform the title")
    assert set(task.tags) == {"gate:listable", "discipline:listing"}
    # SPECIFIED corollary: the tags ride the create, so a new task costs no
    # extra request for them (design.md, and the API budget it reserves).
    assert collaborators.clickup.calls_named("add_task_tag") == []


async def test_the_tag_vocabulary_is_ensured_before_tags_are_used() -> None:
    """Scenario: The tag vocabulary is ensured before tags are used.

    WHEN a pass runs against a space whose tag vocabulary is incomplete
    THEN the missing gate and discipline tags are created in the space
    derived from the configured launch folder
    AND a tag that already exists is left exactly as it stands.
    """
    clickup = _FakeClickUp()
    # One member already present, so "only what is missing" is observable
    # rather than indistinguishable from "create all of them".
    clickup.space_tag_names.add("gate:listable")

    await ensure_tag_vocabulary(clickup=clickup, folder_id=FOLDER_ID)

    # SPECIFIED: derived from the configured folder, not separately
    # configured.
    assert clickup.calls_named("space_id_for_folder") == [{"folder_id": FOLDER_ID}]

    created = {payload["name"] for payload in clickup.calls_named("create_space_tag")}
    expected = {f"gate:{gate}" for gate in GATE_SEQUENCE} | {
        f"discipline:{d.value}" for d in Discipline
    }
    # SPECIFIED: the vocabulary is one tag per gate and one per discipline.
    assert clickup.space_tag_names == expected
    # SPECIFIED: the one already present was left as it stands -- not
    # recreated.
    assert "gate:listable" not in created
    assert created == expected - {"gate:listable"}


async def test_ensuring_the_vocabulary_twice_is_not_an_error() -> None:
    """Scenario: Ensuring the vocabulary twice is not an error.

    WHEN a pass runs against a space that already holds the full
    vocabulary
    THEN no tag is recreated and the pass does not fail.

    The steady state, and the reason seeding reads before it writes: this
    runs every ten minutes, and the design reserves the budget on the
    strength of it costing one read rather than twenty writes.
    """
    clickup = _FakeClickUp()

    await ensure_tag_vocabulary(clickup=clickup, folder_id=FOLDER_ID)
    first_pass_writes = len(clickup.calls_named("create_space_tag"))
    await ensure_tag_vocabulary(clickup=clickup, folder_id=FOLDER_ID)

    assert first_pass_writes > 0, "the first pass seeded nothing"
    # SPECIFIED: nothing is recreated on the second pass.
    assert len(clickup.calls_named("create_space_tag")) == first_pass_writes


async def test_an_existing_untagged_task_gains_its_tags() -> None:
    """Scenario: An existing untagged task gains its tags.

    WHEN a pass runs over a mapped task that was projected before tagging
    existed
    THEN the task gains its step's `gate:` and `discipline:` tags.

    SPECIFIED, and the reason tagging is not create-time only: "solving it
    only for new work would leave every in-flight launch as it is". An
    implementation that tagged on create alone passes every other test in
    this file and fails this one.
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, "task-legacy", name=_composed_name(step), tags=()
    )
    collaborators.mapping.seed_task(
        step.identifier, "task-legacy", retained_name=_composed_name(step)
    )

    await _converge(_start(playbook), playbook, collaborators)

    assert set(collaborators.clickup.tasks["task-legacy"].tags) == {
        "gate:listable",
        "discipline:listing",
    }


async def test_a_task_already_carrying_its_tags_is_left_alone() -> None:
    """Scenario: A task already carrying its tags is left alone.

    WHEN a pass runs over a mapped task already carrying both of its
    step's tags
    THEN no tag write is sent for that task.

    Asserted as *no request*, not as *the tags are still right*: an
    implementation re-adding both tags on every pass leaves them right and
    spends two calls per task every ten minutes, which is the cost the
    design's budget argument rules out.
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID,
        "task-1",
        name=_composed_name(step),
        tags=("gate:listable", "discipline:listing"),
    )
    collaborators.mapping.seed_task(
        step.identifier, "task-1", retained_name=_composed_name(step)
    )

    await _converge(_start(playbook), playbook, collaborators)

    assert collaborators.clickup.calls_named("add_task_tag") == []


async def test_a_persons_own_tags_are_never_touched() -> None:
    """Scenario: A person's own tags are never touched.

    WHEN a pass runs over a mapped task carrying tags outside the `gate:`
    and `discipline:` prefixes
    THEN those tags are left exactly as they stand.

    SPECIFIED: "The prefixes are what the system owns. A tag carrying
    neither belongs to whoever put it there." A person's `urgent` survives
    the pass that adds the owned tags around it.
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID,
        "task-1",
        name=_composed_name(step),
        tags=("urgent", "waiting-on-supplier"),
    )
    collaborators.mapping.seed_task(
        step.identifier, "task-1", retained_name=_composed_name(step)
    )

    await _converge(_start(playbook), playbook, collaborators)

    tags = collaborators.clickup.tasks["task-1"].tags
    # SPECIFIED: the person's tags are left exactly as they stand...
    assert "urgent" in tags
    assert "waiting-on-supplier" in tags
    # ...and the owned ones are added around them.
    assert {"gate:listable", "discipline:listing"} <= set(tags)


async def test_a_step_moved_between_gates_keeps_its_original_gate_tag() -> None:
    """Scenario: A step moved between gates keeps its original gate tag.

    WHEN a step whose task carries `gate:commit` is moved to the
    `listable` gate and a pass runs
    THEN the task carries `gate:listable` in addition to `gate:commit`,
    and no tag is removed.

    **The test that pins add-only.** An implementation reconciling tags
    the way the projection reconciles assignees would swap the stale tag
    for the current one and fail here. The spec accepts the stale tag
    deliberately: telling a re-gated step from a person's own retagging
    needs retained state, which this change does not add (design.md,
    Decision 4).
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID,
        "task-1",
        name=_composed_name(step),
        tags=("gate:commit", "discipline:listing"),
    )
    collaborators.mapping.seed_task(
        step.identifier, "task-1", retained_name=_composed_name(step)
    )

    await _converge(_start(playbook), playbook, collaborators)

    tags = set(collaborators.clickup.tasks["task-1"].tags)
    # SPECIFIED: the current gate is added...
    assert "gate:listable" in tags
    # ...and the stale one is not removed.
    assert "gate:commit" in tags


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(StepStatus.DRAFT, id="draft"),
        pytest.param(StepStatus.IN_DEVELOPMENT, id="in-development"),
        pytest.param(StepStatus.RETIRED, id="retired"),
    ],
)
async def test_a_step_that_is_not_served_is_not_tagged(status: StepStatus) -> None:
    """Scenario: A step that is not served is not tagged.

    WHEN a pass runs and a mapped task's step is not defined by the served
    playbook, or is not `active`
    THEN no tag is written for that task.

    Inherited rather than newly enforced: a step that is not `active` is
    absent from the served set, so the pass never reaches its task at all.
    This test is what confirms that inheritance holds -- `tasks.md` 2.7.
    """
    step = _step(status=status)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, "task-1", name=_composed_name(step), tags=()
    )
    collaborators.mapping.seed_task(step.identifier, "task-1")

    await _converge(_start(playbook), playbook, collaborators)

    assert collaborators.clickup.calls_named("add_task_tag") == []
    assert collaborators.clickup.tasks["task-1"].tags == ()


async def test_a_tag_that_cannot_be_set_is_reported_not_fatal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A tag that cannot be set is reported, not fatal.

    WHEN a task is projected and one of its tags cannot be set
    THEN the task is still created and the pass still succeeds
    AND the omission is reported as a warning naming the step, the tag and
    the task.

    The same trade the projection already makes for an assignee with no
    ClickUp account: `scheduled-jobs` records only whether a run
    succeeded, so a failed run would hide the gap behind a retry.

    The failure is injected on an *existing* task's add, which is the path
    that issues per-tag requests; the pass returning normally is half the
    assertion.
    """
    step = _step(gate="listable", discipline=Discipline.LISTING)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators(
        clickup=_FakeClickUp(failing_tags=frozenset({"discipline:listing"}))
    )
    collaborators.clickup.seed_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, "task-1", name=_composed_name(step), tags=()
    )
    collaborators.mapping.seed_task(
        step.identifier, "task-1", retained_name=_composed_name(step)
    )

    with caplog.at_level(logging.WARNING):
        # SPECIFIED: the pass still succeeds -- no `pytest.raises`.
        await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the tag that could be set still was.
    assert "gate:listable" in collaborators.clickup.tasks["task-1"].tags

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    reported = " ".join(warnings)
    assert warnings, "the failed tag was dropped without a warning record"
    # SPECIFIED: naming the step, the tag and the task.
    assert step.identifier in reported
    assert "discipline:listing" in reported
    assert "task-1" in reported
