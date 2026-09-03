"""A step that is not active leaves the completion loop, both ways.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-clickup-sync/spec.md`

Covers the ADDED requirement *A step that is not active leaves the loop*,
which generalises the REMOVED *A retired step leaves the loop*:

> This change gives a step three ways to leave the served set —
> retirement, and a move back to `draft` or `in-development` — and a rule
> keyed on retirement alone would leave a de-activated step's live task
> undefined in both directions.

Covered here:

- *A de-activated step leaves the loop exactly as a retired one does* —
  the new scenario, in **both** directions (no update sent outward; no
  state change recorded inward), which is where a rule keyed on
  retirement fails.
- *A retired step's task is left unmanaged* and *A retired step's closure
  is not recorded*, re-established against the new served filter: the
  step is now absent from the served set because of its `status`, not
  because a record-level flag says it was retired.
- *An un-retired step resumes through its existing task*, which changes:
  un-retiring returns a step to `in-development`, so the scenario's
  "un-retired, **activated**" is now two acts, and a step that is merely
  un-retired must stay out of the loop.

*A closure during retirement is never replayed* is carried forward
unchanged and is covered by
`tests/unit/launch/infrastructure/driven/test_clickup_sync_retired_steps.py`;
it is accounted for against that test in `test-manifest.md` (its fixtures
need migrating to the new field set, per `tasks.md` 6.3).

## INVENTED shapes

The harness follows `test_clickup_sync_retired_steps.py` in this
directory: `converge_launch(...)` and `reconcile_launch(...)` over
in-memory fakes, with the outcome recorder injected as `record_outcome=`.
This change adds the `members=` collaborator to the convergence pass;
`_converge` is the single correction point.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    converge_launch,
    reconcile_launch,
)
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import (
    ALICE,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"
LIST_ID: Final = "901234002"
TASK_ID: Final = "task-1"
STEP_ID: Final = "listing.a-plus-content"
STEP_NAME: Final = "Add A+ content"
COMPOSED_NAME: Final = f"{STEP_NAME} · {STEP_ID}"

ALICE_CLICKUP: Final = "clickup-alice"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{"identifier": STEP_ID, "name": STEP_NAME, "assignees": (ALICE,), **overrides}
    )


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook_with(status: StepStatus) -> LaunchPlaybook:
    """The eight-gate playbook carrying the step under test at `status`."""
    step = _step(status=status)
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(step, *fillers))


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (the shapes `test_clickup_sync_retired_steps.py` records)
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


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = ALICE_CLICKUP
        self.active = True


class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member(ALICE, "Alice Admin"),)

    members = list_members

    async def member(self, member_id: str) -> _Member | None:
        return _Member(ALICE, "Alice Admin") if member_id == ALICE else None

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


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


class _FakeClickUp:
    def __init__(self) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    async def read_list_state(self, list_id: str) -> ClickUpListState:
        """Every list this file uses is one that still exists.

        `heal-a-launchs-deleted-list` makes the projection verify a
        recorded list before it uses it, so a double that cannot answer
        this stops the pass before any scenario here is reached. Nothing
        below asserts on the answer -- the deleted case belongs to
        `test_clickup_sync_list_healing.py`.
        """
        return ClickUpListState(deleted=False)

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        self._next += 1
        list_id = f"list-{self._next:03d}"
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        self.calls.append(("create_task", {"list_id": list_id, "name": name, **fields}))
        self._next += 1
        task_id = f"task-{self._next:03d}"
        self.tasks[task_id] = _FakeTask(id=task_id, name=name, list_id=list_id)
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        if "name" in fields:
            task.name = fields["name"]
        if "status" in fields:
            task.status = fields["status"]
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        """Added with `tag-tasks-with-gate-and-discipline`: the projection
        attaches a tag through its own endpoint, since ClickUp accepts no
        `tags` key on a task update."""
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag": tag_name}))
        task = self.tasks[task_id]
        if tag_name not in task.tags:
            task.tags = (*task.tags, tag_name)

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    def seed_list(self, list_id: str, name: str = "seeded list") -> str:
        self.lists[list_id] = name
        return list_id

    def seed_task(self, list_id: str, task_id: str, **overrides: Any) -> _FakeTask:
        attributes = {"name": task_id, **overrides}
        task = _FakeTask(id=task_id, list_id=list_id, **attributes)
        self.tasks[task_id] = task
        return task

    def writes_touching(self, task_id: str) -> list[tuple[str, Any]]:
        """Every mutating call referencing the task — reads excluded."""
        return [
            (called, payload)
            for called, payload in self.calls
            if called != "list_tasks" and payload.get("task_id") == task_id
        ]

    def created_names(self) -> list[str]:
        return [
            payload["name"] for called, payload in self.calls if called == "create_task"
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
    def __init__(self) -> None:
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}
        self.replacements: list[tuple[str, str]] = []

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def replace_list_discarding_tasks(
        self,
        product_id: ProductId,
        list_id: str,
        *,
        spare: Sequence[str] = (),
    ) -> None:
        """Present so this double still stands in for the whole
        `MappingStore` port, which `heal-a-launchs-deleted-list` widened.
        No scenario in this file replaces a list; the behaviour is
        exercised in `test_clickup_sync_list_healing.py`."""
        spared = {str(step_id) for step_id in spare}
        self.tasks = {
            key: mapped
            for key, mapped in self.tasks.items()
            if key[0] != product_id or key[1] in spared
        }
        self.lists[product_id] = list_id

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
        self.tasks[(PRODUCT_ID, step_id)].retained_assignees = tuple(
            str(item) for item in assignees
        )

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    def seed_task(
        self,
        step_id: str,
        task_id: str,
        *,
        closed: bool = False,
        retained_name: str | None = None,
        retained_assignees: tuple[str, ...] | None = None,
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
            retained_name=retained_name,
            retained_assignees=retained_assignees,
        )
        self.tasks[(PRODUCT_ID, step_id)] = mapping
        return mapping


class _FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, *, product_id: ProductId, step_id: str, outcome: Any, provenance: Any
    ) -> None:
        self.calls.append(
            {
                "product_id": product_id,
                "step_id": step_id,
                "outcome": outcome,
                "provenance": provenance,
            }
        )


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(
        default_factory=lambda: _FakeCatalog(
            _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)
        )
    )
    members: _FakeMembers = field(default_factory=_FakeMembers)
    recorder: _FakeRecorder = field(default_factory=_FakeRecorder)


async def _converge(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape — the single correction point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        members=collaborators.members,
        folder_id=FOLDER_ID,
    )


async def _reconcile(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape — the single correction point."""
    await reconcile_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        record_outcome=collaborators.recorder,
    )


def _standing_task(*, task_closed: bool = False) -> _Collaborators:
    """A mapped, still-standing task for the step under test — the shape
    leaving the served set leaves behind, whichever route it took."""
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, TASK_ID, name=COMPOSED_NAME, closed=task_closed
    )
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID
    collaborators.mapping.seed_task(
        STEP_ID,
        TASK_ID,
        retained_name=COMPOSED_NAME,
        retained_assignees=(ALICE_CLICKUP,),
    )
    return collaborators


# ---------------------------------------------------------------------------
# Requirement: A step that is not active leaves the loop
# ---------------------------------------------------------------------------


async def test_a_retired_steps_task_is_left_unmanaged() -> None:
    """Scenario: A retired step's task is left unmanaged.

    WHEN a step with a mapped, unfinished task is retired and the next
    pass runs
    THEN no create, rename, due-date update, close, or delete is sent for
    that task.

    Re-established against the new mechanism: the step is out of the
    served set because its **status** is `retired`, not because a
    record-level flag says so. `design.md` Decision 2 replaces one with
    the other, so an implementation still keying on the flag has nothing
    to read.
    """
    collaborators = _standing_task()
    playbook = _playbook_with(StepStatus.RETIRED)

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: nothing mutating touches the leftover task.
    assert collaborators.clickup.writes_touching(TASK_ID) == []
    # SPECIFIED: and no second task is created for it either.
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())
    assert TASK_ID in collaborators.clickup.tasks


async def test_a_de_activated_step_leaves_the_loop_exactly_as_a_retired_one_does() -> (
    None
):
    """Scenario: A de-activated step leaves the loop exactly as a retired
    one does.

    WHEN an `active` step with a mapped task is moved to `in-development`
    and the next pass runs
    THEN no update is sent for its task and no state change on it is
    recorded.

    **The new scenario, and the one a rule keyed on retirement fails in
    both directions**: outward, the leftover task would keep being
    renamed and re-dated; inward, closing it would record a completion
    for a step "no longer part of the launch's obligations".

    The task is seeded closed so the inward half has something to record
    if the implementation wrongly does — an assertion over an unchanged
    task would pass vacuously.
    """
    collaborators = _standing_task(task_closed=True)
    playbook = _playbook_with(StepStatus.IN_DEVELOPMENT)
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)
    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED (outward): no update is sent for its task.
    assert collaborators.clickup.writes_touching(TASK_ID) == []
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())
    # SPECIFIED (inward): no state change on it is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: observations keep updating the retained observed state,
    # recording nothing — so what happened while it was out is never
    # replayed as a transition later.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is True


async def test_a_draft_step_with_a_leftover_task_is_left_alone() -> None:
    """The third route out of the served set, SPECIFIED by the
    requirement's own wording — "whether it became `retired`, or moved
    back to `draft` or `in-development`" — and stated in no scenario.

    Covered separately from the `in-development` case because an
    implementation could plausibly treat `in-development` as "still being
    worked on, keep the task fresh" while treating `draft` differently,
    or vice versa. The rule is the served set, and neither is in it.
    """
    collaborators = _standing_task()
    playbook = _playbook_with(StepStatus.DRAFT)

    await _converge(_start(playbook), playbook, collaborators)

    assert collaborators.clickup.writes_touching(TASK_ID) == []
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())


async def test_a_step_returning_to_active_resumes_through_its_existing_task() -> None:
    """Scenario: An un-retired step resumes through its existing task.

    WHEN a retired step whose mapped task still exists is un-retired,
    activated, and the next pass runs
    THEN the existing mapping and task are reused — no second task is
    created — and the loop resumes for the step.

    The scenario now names two acts, because un-retiring returns a step
    to `in-development` (`playbook-authoring`). The middle pass below is
    what that intermediate state looks like to the sync, and it must
    still leave the task alone: an implementation resuming on
    un-retirement rather than on activation fails there.
    """
    collaborators = _standing_task()
    launch = _start(_playbook_with(StepStatus.RETIRED))

    # Un-retired: `in-development`, and still out of the loop.
    in_development = _playbook_with(StepStatus.IN_DEVELOPMENT)
    await _converge(launch, in_development, collaborators)
    assert collaborators.clickup.writes_touching(TASK_ID) == []

    # Activated: the loop resumes through the existing mapping.
    active = _playbook_with(StepStatus.ACTIVE)
    await _converge(launch, active, collaborators)

    # SPECIFIED: no second task, and the mapping still names the old one.
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())
    assert collaborators.mapping.replacements == []
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.task_id == TASK_ID


async def test_a_retired_steps_closure_is_not_recorded() -> None:
    """Scenario: A retired step's closure is not recorded.

    WHEN a retired step's mapped task changes state in ClickUp, and that
    change reaches the system by webhook or by the reconciliation pass
    THEN no outcome is recorded for the step.

    The reconciliation path is covered here; the webhook path is covered
    in `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`
    and is unchanged by this delta beyond which steps count as served.
    """
    collaborators = _standing_task(task_closed=True)
    playbook = _playbook_with(StepStatus.RETIRED)

    await _reconcile(_start(playbook), playbook, collaborators)

    assert collaborators.recorder.calls == []
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is True
