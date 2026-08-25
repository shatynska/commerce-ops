"""A retired step leaves the ClickUp completion loop in both directions.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-clickup-sync/spec.md`

Covers the ADDED requirement *A retired step leaves the loop* — all four
scenarios. "Retired", at this level, is the step's absence from the
served playbook passed to the pass: the adapter excludes retired steps
(`tasks.md` 3.1), so the pass meets retirement only as a mapped task
whose step the playbook no longer defines.

The webhook half of *A retired step's closure is not recorded* ("by
webhook or by the reconciliation pass") is not restated here: the
webhook records through `record_step_outcome`, which rejects an
identifier the served playbook does not define
(`tests/unit/launch/domain/test_outcomes_after_retirement.py`), so no
outcome can be recorded on that path either. Whether the webhook
surfaces that rejection as a quiet skip or an error is left unspecified
by the delta and is recorded in the manifest as an unresolved project
question.

**Level.** The convergence/reconciliation pass over one launch against
fake ports — the same level `test_clickup_sync_projection.py` and
`test_clickup_sync_reconciliation.py` record.

**Doubles and call shapes are inherited** from those files (INVENTED
there): `converge_launch(launch=, playbook=, clickup=, mapping=,
read_product=, folder_id=)` and `reconcile_launch(launch=, playbook=,
clickup=, mapping=, record_outcome=)`, re-declared because those files
are existing tests this pass must not edit. Playbook fixtures hold every
gate with automated filler steps for the gate-holding floor this change
adds; automated steps are never projected.

**Expected first-run state.** Mixed. The outward tests may already pass
(the current pass iterates the playbook's steps, so an unmapped-in-
playbook task is naturally left alone); the inward tests are expected to
fail if the current reconciliation records for any mapped task
regardless of playbook membership, and the never-replayed test exercises
ordering the current implementation has no reason to satisfy. A first-run
pass on the outward tests establishes the current pass already behaves as
specified and pins it (`ai-toolkit:testing`, target-exists case).

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

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
    InProgress,
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
    reconcile_launch,
)
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
TASK_ID: Final = "task-retired-step"

LAUNCH_DATE: Final = date(2027, 3, 2)

STEP_ID: Final = "lp.creative.008"
STEP_DESCRIPTION: Final = "Main image designed to be scroll-stopping"
COMPOSED_NAME: Final = f"{STEP_DESCRIPTION} · {STEP_ID}"


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
        "name": STEP_DESCRIPTION,
        "gate": "listable",
        "discipline": Discipline("creative"),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _holding_steps() -> tuple[StepDefinition, ...]:
    return tuple(
        _step(
            identifier=f"hold.{gate}",
            name=f"Blocking work holding the {gate} gate",
            gate=gate,
            blocking=True,
            kind=StepKind.AUTOMATED,
            status=StepStatus.ACTIVE,
            automation_brief="Held until the automated check reports green.",
            handler="fixture.holding_check",
        )
        for gate in SPECIFIED_GATE_ORDER
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1", gates=_gates(), steps=(*_holding_steps(), *steps)
    )


# The step retired: served before, absent now.
PLAYBOOK_WITHOUT_STEP: Final = _playbook()
PLAYBOOK_WITH_STEP: Final = _playbook(steps=(_step(),))


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (inherited; see the module docstring)
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


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    description: str | None = None
    status: str = "to do"
    closed: bool = False
    due_date: Any = None


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


def _due_date_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    for key, value in fields.items():
        if "due" in key.lower():
            return True, value
    return False, None


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
        self.calls.append(
            (
                "create_task",
                {
                    "list_id": list_id,
                    "name": name,
                    "description": description,
                    **fields,
                },
            )
        )
        task_id = self._identifier("task")
        present, due = _due_date_in(fields)
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            description=description,
            due_date=due if present else None,
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        present, due = _due_date_in(fields)
        if present:
            task.due_date = due
        if "name" in fields:
            task.name = fields["name"]
        if "description" in fields:
            task.description = fields["description"]
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

    def writes_touching(self, task_id: str) -> list[tuple[str, Any]]:
        """Every mutating call referencing the task — reads excluded."""
        return [
            (called, payload)
            for called, payload in self.calls
            if called != "list_tasks" and payload.get("task_id") == task_id
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
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
            retained_name=retained_name,
        )
        self.tasks[(PRODUCT_ID, step_id)] = mapping
        return mapping


class _FakeRecorder:
    """Stands in for `launch.application.record_step_outcome`, exactly as
    `test_clickup_sync_reconciliation.py` injects it."""

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
    recorder: _FakeRecorder = field(default_factory=_FakeRecorder)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def _converge(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape — a single correction point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=FOLDER_ID,
    )


async def _reconcile(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape — a single correction point."""
    await reconcile_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        record_outcome=collaborators.recorder,
    )


def _retired_collaborators(*, task_closed: bool = False) -> _Collaborators:
    """A mapped, still-standing task for a step the playbook no longer
    serves — the shape retirement leaves behind."""
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, TASK_ID, name=COMPOSED_NAME, closed=task_closed
    )
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID
    collaborators.mapping.seed_task(STEP_ID, TASK_ID, retained_name=COMPOSED_NAME)
    return collaborators


# ---------------------------------------------------------------------------
# Requirement (ADDED): A retired step leaves the loop
# ---------------------------------------------------------------------------


async def test_a_retired_steps_task_is_left_unmanaged() -> None:
    """Scenario: A retired step's task is left unmanaged.

    WHEN a step with a mapped, unfinished task is retired and the next
    pass runs
    THEN no create, rename, due-date update, close, or delete is sent
    for that task.
    """
    collaborators = _retired_collaborators(task_closed=False)
    launch = _start(PLAYBOOK_WITHOUT_STEP)

    await _converge(launch, PLAYBOOK_WITHOUT_STEP, collaborators)

    # SPECIFIED: nothing mutating touches the leftover task.
    assert collaborators.clickup.writes_touching(TASK_ID) == []
    # SPECIFIED: no second task is created for the retired step either —
    # nothing composed from its description appears in any create call.
    created_names = [
        payload["name"]
        for called, payload in collaborators.clickup.calls
        if called == "create_task"
    ]
    assert all(STEP_ID not in name for name in created_names)
    # The task itself is left standing.
    assert TASK_ID in collaborators.clickup.tasks


async def test_a_retired_steps_closure_is_not_recorded() -> None:
    """Scenario: A retired step's closure is not recorded — the
    reconciliation path.

    WHEN a retired step's mapped task changes state in ClickUp and that
    change reaches the system by the reconciliation pass
    THEN no outcome is recorded for the step.

    The requirement also obliges the pass to keep observing: "Observations
    of the task SHALL nonetheless keep updating its retained observed
    state, recording nothing."
    """
    collaborators = _retired_collaborators(task_closed=True)
    launch = _start(PLAYBOOK_WITHOUT_STEP)

    await _reconcile(launch, PLAYBOOK_WITHOUT_STEP, collaborators)

    # SPECIFIED: nothing recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the observation still updates the retained state.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is True


async def test_a_closure_during_retirement_is_never_replayed() -> None:
    """Scenario: A closure during retirement is never replayed.

    WHEN a retired step's mapped task is closed while the step is
    retired, and the step is later un-retired with the task still closed
    THEN no outcome is recorded for that closure — before or after the
    un-retirement
    AND a reopening observed after the un-retirement records `InProgress`.
    """
    collaborators = _retired_collaborators(task_closed=True)
    launch = _start(PLAYBOOK_WITHOUT_STEP)

    # Observed while retired: retained state updates, nothing recorded.
    await _reconcile(launch, PLAYBOOK_WITHOUT_STEP, collaborators)
    assert collaborators.recorder.calls == []

    # Un-retired with the task still closed: no transition, so the
    # closure that happened during retirement is not replayed.
    await _reconcile(launch, PLAYBOOK_WITH_STEP, collaborators)
    assert collaborators.recorder.calls == []

    # A reopening after the un-retirement is a real transition.
    collaborators.clickup.tasks[TASK_ID].closed = False
    await _reconcile(launch, PLAYBOOK_WITH_STEP, collaborators)

    assert len(collaborators.recorder.calls) == 1
    recorded = collaborators.recorder.calls[0]
    assert recorded["step_id"] == STEP_ID
    # SPECIFIED (completion requirement): a reopening records InProgress
    # with provenance source `clickup`.
    assert recorded["outcome"] is InProgress
    assert recorded["provenance"].source == "clickup"


async def test_an_unretired_step_resumes_through_its_existing_task() -> None:
    """Scenario: An un-retired step resumes through its existing task.

    WHEN a retired step whose mapped task still exists is un-retired and
    the next pass runs
    THEN the existing mapping and task are reused — no second task is
    created — and the loop resumes for the step.
    """
    collaborators = _retired_collaborators(task_closed=False)
    launch = _start(PLAYBOOK_WITH_STEP)

    await _converge(launch, PLAYBOOK_WITH_STEP, collaborators)

    # SPECIFIED: no second task, and the mapping still names the old one.
    created_names = [
        payload["name"]
        for called, payload in collaborators.clickup.calls
        if called == "create_task"
    ]
    assert all(STEP_ID not in name for name in created_names)
    assert collaborators.mapping.replacements == []
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.task_id == TASK_ID
