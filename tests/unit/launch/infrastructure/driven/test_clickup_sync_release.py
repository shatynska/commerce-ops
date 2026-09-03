"""Release governs what the projection creates, never what it withdraws
or accepts (`launch-clickup-sync`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-clickup-sync/spec.md`:

- MODIFIED *Human steps are projected as tasks carrying their name,
  description and assignees* — only its six new scenarios: *A step
  activated mid-launch that the launch has not released is not
  projected*, *An unreleased step is not projected*, *A step is projected
  on the pass after the launch releases it*, *A step waiting on another
  is not projected until that one is resolved*, *A step released by its
  dependency being retired is projected*, and *A task already created is
  not withdrawn*.
- MODIFIED *A step that is not active leaves the loop* — only its two new
  scenarios: *An unreleased step has not left the loop* and *Release does
  not suppress reconciliation*.

Every other scenario of both requirements is reproduced from the served
spec — one with "is activated after a launch started" reworded to add
"the launch has released it" — and is covered by the existing files in
this directory, whose fixtures declare no start gate and are therefore
released from a launch's first gate. They are accounted for against
those tests in the manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`.

## Level

`converge_launch` and `reconcile_launch` over in-memory fakes — no HTTP,
no Postgres — which is the level every other test of these two passes
sits at and the smallest that can observe which ClickUp writes happen.

## INVENTED, with correction points

Inherited from `test_clickup_projection_step_fields.py` and
`test_clickup_non_active_steps_leave_loop.py`, whose docstrings record
them: both call shapes, the ClickUp port's four operations, the mapping
store's methods, `read_product`, `members=` and `record_outcome=`.
Correction points: `_converge`, `_reconcile`.

Added by this file: `starts_at_gate` / `after_steps` as constructor
keywords on `StepDefinition`. Correction point: `_step`.

## Expected first-run state

Neither field exists, so every test here is expected to fail on an
**absent target** (`TypeError` from the constructor). That establishes
absence and nothing about these assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    converge_launch,
    reconcile_launch,
)
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId("6f1d5b1c-6f0e-4d0f-9d84-6b0a1f1d5b1c")
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

FOLDER_ID: Final = "90110042424"

LAUNCH_DATE: Final = date(2027, 3, 2)
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

A_DISCIPLINE: Final = next(iter(Discipline))

#: The step this file's projection assertions are about.
WAITING_STEP: Final = "listing.waits-for-listable"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


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
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`. `automated`, so the projection
    never creates a task for a filler and every assertion about which
    tasks were created is untouched by them; and declaring neither start
    field, so a filler is released from the first gate."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="release-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who="Helen",
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=RECORDED_AT,
        posture=None,
    )


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _satisfy(launch: Launch, playbook: LaunchPlaybook, step_id: str) -> None:
    launch.record_step_outcome(
        playbook, step_id=step_id, outcome=Satisfied, provenance=_provenance()
    )


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and launch.progress_for(step.identifier) is None:
                _satisfy(launch, playbook, step.identifier)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
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


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeMembers:
    def __init__(self) -> None:
        self._members = (_Member("prs_01HQ8Z6M4A", "Alice Admin"),)

    async def list_members(self) -> tuple[_Member, ...]:
        return self._members

    members = list_members

    async def member(self, member_id: str) -> _Member | None:
        for member in self._members:
            if member.id == member_id:
                return member
        return None

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

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    async def read_list_state(self, list_id: str) -> ClickUpListState:
        return ClickUpListState(deleted=False)

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
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag": tag_name}))
        task = self.tasks[task_id]
        if tag_name not in task.tags:
            task.tags = (*task.tags, tag_name)

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    # -- test-side helpers -------------------------------------------------

    def seed_list(self, list_id: str, name: str = "seeded list") -> str:
        self.lists[list_id] = name
        return list_id

    def seed_task(self, list_id: str, task_id: str, **overrides: Any) -> _FakeTask:
        attributes: dict[str, Any] = {"name": task_id, **overrides}
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
        self, step_id: str, task_id: str, *, closed: bool = False
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
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


def _created_for(collaborators: _Collaborators, step_id: str) -> list[Any]:
    """Every task creation whose composed name carries that identifier.

    The projected name ends in the step's identifier, which is what makes
    a task traceable to its step — asserted by
    `test_clickup_task_naming.py` and relied on, not restated, here.
    """
    return [
        payload
        for payload in collaborators.clickup.calls_named("create_task")
        if step_id in str(payload["name"])
    ]


# ---------------------------------------------------------------------------
# MODIFIED Requirement: Human steps are projected as tasks (new scenarios)
# ---------------------------------------------------------------------------


async def test_an_unreleased_step_is_not_projected() -> None:
    """Scenario: An unreleased step is not projected.

    WHEN the reconciliation pass runs over a launch standing at `commit`
    and the served playbook carries an `active` `human` step whose start
    gate is `listable`
    THEN no task is created for it, and no mapping is recorded.

    SPECIFIED reason: "Release is what stops a launch's list opening with
    the whole playbook in it on its first pass."
    """
    waiting = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    playbook = _playbook(waiting)
    launch = _start(playbook)
    collaborators = _Collaborators()

    assert launch.current_gate == "commit"

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: no task is created for it.
    assert _created_for(collaborators, WAITING_STEP) == []
    # SPECIFIED: and no mapping is recorded.
    assert await collaborators.mapping.task_for(PRODUCT_ID, WAITING_STEP) is None


async def test_a_step_is_projected_on_the_pass_after_the_launch_releases_it() -> None:
    """Scenario: A step is projected on the pass after the launch releases
    it.

    WHEN a launch that stood at `commit` advances to `listable`, and the
    next reconciliation pass runs
    THEN a task is created for each `listable`-gate step the launch has
    now released.

    Read across two passes, so what is observed is the *change* — a
    single pass over a released step could not tell the release rule from
    its absence.
    """
    waiting = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    playbook = _playbook(waiting)
    launch = _start(playbook)
    collaborators = _Collaborators()

    await _converge(launch, playbook, collaborators)
    assert _created_for(collaborators, WAITING_STEP) == []

    _advance_to(launch, playbook, "listable")
    await _converge(launch, playbook, collaborators)

    # SPECIFIED: a task is created for it now.
    assert len(_created_for(collaborators, WAITING_STEP)) == 1
    assert await collaborators.mapping.task_for(PRODUCT_ID, WAITING_STEP) is not None


async def test_a_step_activated_mid_launch_that_is_not_released_is_not_projected() -> (
    None
):
    """Scenario: A step activated mid-launch that the launch has not
    released is not projected.

    WHEN a `human` step whose start gate the launch has not reached is
    activated after that launch started, and the next pass runs
    THEN no task is created for it.

    The activation is modelled as the served playbook changing between
    two passes, which is what the live step set does: "The served
    playbook is live, so a step activated after the launch started is
    projected on the next pass like any other."
    """
    drafted = _step(
        identifier=WAITING_STEP,
        status=StepStatus.DRAFT,
        starts_at_gate="listable",
    )
    before = _playbook(drafted)
    launch = _start(before)
    collaborators = _Collaborators()

    await _converge(launch, before, collaborators)

    activated = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    after = _playbook(activated)

    await _converge(launch, after, collaborators)

    assert launch.current_gate == "commit"
    assert _created_for(collaborators, WAITING_STEP) == []


async def test_a_step_waiting_on_another_is_not_projected_until_it_is_resolved() -> (
    None
):
    """Scenario: A step waiting on another is not projected until that one
    is resolved.

    WHEN the reconciliation pass runs over a launch that has reached a
    step's start gate, and that step names an `after_steps` dependency
    whose outcome is not yet resolved
    THEN no task is created for it.
    """
    dependency = _step(identifier="listing.photos-approved", gate="commit")
    depending = _step(
        identifier=WAITING_STEP,
        starts_at_gate="commit",
        after_steps=("listing.photos-approved",),
    )
    playbook = _playbook(dependency, depending)
    launch = _start(playbook)
    collaborators = _Collaborators()

    await _converge(launch, playbook, collaborators)

    # DERIVED guard: the start gate is reached, so the dependency is what
    # holds the step back rather than the gate.
    assert launch.current_gate == "commit"
    assert _created_for(collaborators, WAITING_STEP) == []

    _satisfy(launch, playbook, "listing.photos-approved")
    await _converge(launch, playbook, collaborators)

    # DERIVED complement: resolving it projects the step, so the
    # assertion above is about the dependency and not about the step
    # never being projectable at all.
    assert len(_created_for(collaborators, WAITING_STEP)) == 1


async def test_a_step_released_by_its_dependency_being_retired_is_projected() -> None:
    """Scenario: A step released by its dependency being retired is
    projected.

    WHEN a step's only `after_steps` dependency is retired, and the
    reconciliation pass runs over a launch that has reached that step's
    start gate
    THEN a task is created for it, the retired dependency being satisfied
    vacuously.
    """
    retired = _step(
        identifier="listing.photos-approved",
        gate="commit",
        status=StepStatus.RETIRED,
    )
    depending = _step(
        identifier=WAITING_STEP,
        starts_at_gate="commit",
        after_steps=("listing.photos-approved",),
    )
    playbook = _playbook(retired, depending)
    launch = _start(playbook)
    collaborators = _Collaborators()

    await _converge(launch, playbook, collaborators)

    assert len(_created_for(collaborators, WAITING_STEP)) == 1


async def test_a_task_already_created_is_not_withdrawn() -> None:
    """Scenario: A task already created is not withdrawn.

    WHEN a step's task exists and the step is subsequently authored to
    start at a gate the launch has not reached
    THEN the task is left standing in ClickUp, and its mapping is left
    recorded.

    SPECIFIED: "Release governs what is created, never what is taken
    away." `tasks.md` 4.2 asks for this specifically.
    """
    projected = _step(identifier=WAITING_STEP)
    playbook = _playbook(projected)
    launch = _start(playbook)
    collaborators = _Collaborators()

    await _converge(launch, playbook, collaborators)
    created = _created_for(collaborators, WAITING_STEP)
    assert len(created) == 1, "the fixture step was not projected on the first pass"
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, WAITING_STEP)
    assert mapping is not None
    task_id = mapping.task_id

    re_authored = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    after = _playbook(re_authored)

    await _converge(launch, after, collaborators)

    # SPECIFIED: the task is left standing.
    assert task_id in collaborators.clickup.tasks
    # SPECIFIED: and its mapping is left recorded.
    still_mapped = await collaborators.mapping.task_for(PRODUCT_ID, WAITING_STEP)
    assert still_mapped is not None
    assert still_mapped.task_id == task_id


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A step that is not active leaves the loop
# (the two new scenarios)
# ---------------------------------------------------------------------------


async def test_an_unreleased_step_has_not_left_the_loop() -> None:
    """Scenario: An unreleased step has not left the loop.

    WHEN a task stands for a step that is `active` and `human` but that
    its launch has since stopped releasing, and that task is closed in
    ClickUp
    THEN the outcome is recorded for the step, exactly as it would be for
    a released one.

    SPECIFIED: "Release is not one of these fields" — departure keys on
    the step ceasing to be work of the kind the projection represents,
    which is a fact about the *step*, while release is a fact about one
    launch's position.
    """
    projected = _step(identifier=WAITING_STEP)
    playbook = _playbook(projected)
    launch = _start(playbook)
    collaborators = _Collaborators()

    await _converge(launch, playbook, collaborators)
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, WAITING_STEP)
    assert mapping is not None
    collaborators.clickup.tasks[mapping.task_id].closed = True

    re_authored = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    after = _playbook(re_authored)

    await _reconcile(launch, after, collaborators)

    recorded = [
        call for call in collaborators.recorder.calls if call["step_id"] == WAITING_STEP
    ]
    # SPECIFIED: the outcome is recorded, exactly as for a released step.
    assert recorded, (
        "closing the task of an `active` `human` step recorded nothing "
        "because the launch had stopped releasing it — release governs what "
        "the system asks for, never what it accepts"
    )


async def test_release_does_not_suppress_reconciliation() -> None:
    """Scenario: Release does not suppress reconciliation.

    WHEN the reconciliation pass observes a state change on a task whose
    step the launch has not released
    THEN the change is recorded, no rule of this requirement applying to
    it.

    `tasks.md` 4.4 states the reason to record in a comment rather than
    only in the spec: "completing work early is still work done".

    The step here has *never* been released — its start gate is ahead of
    the launch — and a task stands for it all the same, which is the
    state a mapping made before an authoring change leaves behind.
    """
    waiting = _step(identifier=WAITING_STEP, starts_at_gate="listable")
    playbook = _playbook(waiting)
    launch = _start(playbook)
    collaborators = _Collaborators()

    list_id = collaborators.clickup.seed_list("list-001")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(list_id, "task-001", closed=True)
    collaborators.mapping.seed_task(WAITING_STEP, "task-001", closed=False)

    assert launch.current_gate == "commit"

    await _reconcile(launch, playbook, collaborators)

    recorded = [
        call for call in collaborators.recorder.calls if call["step_id"] == WAITING_STEP
    ]
    assert recorded, (
        "a closure observed on the task of an unreleased step recorded "
        "nothing; reconciliation is deliberately ungated"
    )
