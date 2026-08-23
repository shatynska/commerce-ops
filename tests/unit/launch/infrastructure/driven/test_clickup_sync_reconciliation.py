"""Pull half of `launch-clickup-sync`: what reconciliation records, and what
it must leave alone.

Derived strictly from the delta spec:
`openspec/changes/add-clickup-completion-loop/specs/launch-clickup-sync/spec.md`

Covers, as ADDED requirements:

- *The reconciliation pass records completions and reopenings the webhook
  missed* -- all four scenarios.
- *Completion flows from ClickUp to the launch as a recorded outcome* --
  scenario *The system never closes a task* (the four scenarios stated over
  a received status change are covered on the webhook path, in
  `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`).

The transition rule these scenarios rest on is keyed on the mapping row's
last-observed closed state, never on the step's recorded outcome
(`design.md`, "Recording is transition-based, keyed on the last observed
state"). That distinction is what the last two tests below exist to hold:
a pass that compared against the recorded outcome instead would pass the
first two tests and fail these.

See `openspec/changes/add-clickup-completion-loop/test-manifest.md` for the
full accounting.

## The interface under test does not exist yet, and its shape is INVENTED

The same assumptions as
`test_clickup_sync_projection.py` -- see that file's docstring for the
list -- plus:

- `reconcile_launch(...)` in
  `launch/infrastructure/driven/clickup_sync.py` (`tasks.md` 4.4), taking
  `launch`, `playbook`, `clickup`, `mapping` and `record_outcome`.
  `_reconcile()` below is the single place to correct if it differs.
- `record_outcome` as an async callable
  `(product_id=, step_id=, outcome=, provenance=)`, standing in for
  `launch.application.record_step_outcome` -- the seam `tasks.md` 4.4
  names, injected rather than reached through a store, exactly as
  `tests/unit/launch/application/test_graduation.py` injects the catalog
  stamp. Whatever the real use case's parameter list, what these tests
  assert is *what* is recorded, not how it is passed.
- `"clickup-reconciliation"` as the recorder identity, which `design.md`
  fixes in as many words. The spec itself says only "the reconciliation's
  own identity"; a different literal is a fixture correction, a *human*
  recorder is not.

## At the time this pass was written, nothing under test exists

Expected to fail on an absent target (`ModuleNotFoundError`) until tasks
4.1 and 4.4 land. Per `ai-toolkit:testing`, that failure establishes only
absence.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    InProgress,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
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
TASK_ID: Final = "task-mapped"
STEP_ID: Final = "listing.title-conforms"

LAUNCH_DATE: Final = date(2027, 3, 2)
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

# SPECIFIED (launch-instance, unchanged): the provenance source ClickUp
# recordings carry.
CLICKUP_SOURCE: Final = "clickup"
# Fixed by design.md; see the module docstring.
RECONCILIATION_RECORDER: Final = "clickup-reconciliation"


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
        "identifier": STEP_ID,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "binding": Binding.FRAMEWORK,
        "blocking": False,
        "execution": ExecutionMode.HUMAN_ATTESTED,
        "hazard": Hazard.NONE,
        "rule_policy": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook(steps: tuple[StepDefinition, ...] = (_step(),)) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "attestation",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "screenshot in the launch Slack thread",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


# ---------------------------------------------------------------------------
# Test doubles -- duplicated from `test_clickup_sync_projection.py` on
# purpose: a shared helper would have to live in a `conftest.py`, which is
# outside this pass's test-path glob.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    def __init__(self) -> None:
        self.calls: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.calls.append(product_id)
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
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
        self.calls.append(("create_task", {"list_id": list_id, "name": name, **fields}))
        task_id = self._identifier("task")
        present, due = _due_date_in(fields)
        self.tasks[task_id] = _FakeTask(
            id=task_id, name=name, list_id=list_id, due_date=due if present else None
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        present, due = _due_date_in(fields)
        if present:
            task.due_date = due
        if "status" in fields:
            task.status = fields["status"]
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    def seed_list(self, list_id: str) -> str:
        self.lists[list_id] = "seeded list"
        return list_id

    def seed_task(self, list_id: str, task_id: str, **overrides: Any) -> _FakeTask:
        task = _FakeTask(id=task_id, name=task_id, list_id=list_id, **overrides)
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

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

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


class _RecordingOutcomes:
    """Stands in for `launch.application.record_step_outcome`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        *,
        product_id: ProductId,
        step_id: str,
        outcome: Any,
        provenance: Any,
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
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    record: _RecordingOutcomes = field(default_factory=_RecordingOutcomes)


# ---------------------------------------------------------------------------
# The single correction points: how each pass is invoked
# ---------------------------------------------------------------------------


async def _reconcile(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape (see the module docstring)."""
    await reconcile_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        record_outcome=collaborators.record,
    )


async def _converge(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=FOLDER_ID,
    )


def _mapped(
    collaborators: _Collaborators, *, closed_in_clickup: bool, last_observed: bool
) -> None:
    """A launch already projected: one list, one mapped task, with the
    task's state in ClickUp and the retained observed state set
    independently -- which is the whole subject of these tests."""
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID,
        TASK_ID,
        status="complete" if closed_in_clickup else "in progress",
        closed=closed_in_clickup,
    )
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID
    collaborators.mapping.seed_task(STEP_ID, TASK_ID, closed=last_observed)


# ---------------------------------------------------------------------------
# Requirement: The reconciliation pass records completions and reopenings
# the webhook missed
# ---------------------------------------------------------------------------


async def test_a_missed_completion_is_recorded_on_reconciliation() -> None:
    """Scenario: A missed completion is recorded on reconciliation.

    WHEN the reconciliation pass reads a mapped task as closed and its
    last observed state is not closed
    THEN a `Satisfied` outcome is recorded for the mapped step with
    provenance source `clickup` and the reconciliation's own identity as
    recorder
    AND the task's retained observed state becomes closed.
    """
    playbook = _playbook()
    collaborators = _Collaborators()
    _mapped(collaborators, closed_in_clickup=True, last_observed=False)

    await _reconcile(_start(playbook), playbook, collaborators)

    # SPECIFIED: a `Satisfied` outcome is recorded for the mapped step.
    assert len(collaborators.record.calls) == 1, (
        f"expected exactly one recording, got {collaborators.record.calls}"
    )
    recorded = collaborators.record.calls[0]
    assert recorded["product_id"] == PRODUCT_ID
    assert recorded["step_id"] == STEP_ID
    assert recorded["outcome"] is Satisfied

    # SPECIFIED: provenance source `clickup`, the reconciliation's own
    # identity as recorder, and the task as evidence.
    provenance = recorded["provenance"]
    assert provenance.source == CLICKUP_SOURCE
    assert provenance.who == RECONCILIATION_RECORDER, (
        "a read exposes no acting user, so the recorder must be the "
        f"reconciliation's own identity, not {provenance.who!r}"
    )
    assert TASK_ID in str(provenance.evidence), (
        f"the task is not identifiable in the evidence: {provenance.evidence!r}"
    )

    # SPECIFIED: the task's retained observed state becomes closed.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is True


async def test_a_missed_reopening_is_recorded_on_reconciliation() -> None:
    """Scenario: A missed reopening is recorded on reconciliation.

    WHEN the reconciliation pass reads a mapped task as open and its last
    observed state is closed
    THEN an `InProgress` outcome is recorded for the mapped step with
    provenance source `clickup`
    AND the task's retained observed state becomes open.
    """
    playbook = _playbook()
    collaborators = _Collaborators()
    _mapped(collaborators, closed_in_clickup=False, last_observed=True)

    await _reconcile(_start(playbook), playbook, collaborators)

    # SPECIFIED: an `InProgress` outcome with provenance source `clickup`.
    assert len(collaborators.record.calls) == 1, (
        f"expected exactly one recording, got {collaborators.record.calls}"
    )
    recorded = collaborators.record.calls[0]
    assert recorded["step_id"] == STEP_ID
    assert recorded["outcome"] is InProgress
    assert recorded["provenance"].source == CLICKUP_SOURCE

    # SPECIFIED: the task's retained observed state becomes open.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is False


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(True, id="closed-and-observed-closed"),
        pytest.param(False, id="open-and-observed-open"),
    ],
)
async def test_no_transition_means_no_recording(state: bool) -> None:
    """Scenario: No transition means no recording.

    WHEN the reconciliation pass reads a mapped task whose state matches
    its last observed state
    THEN no outcome is recorded for that step.

    Both agreeing states are exercised: a pass that recorded `Satisfied`
    on every closed read, or `InProgress` on every open read, fails one of
    them. This is also what makes a re-delivered webhook a no-op --
    `design.md` derives both from the same mechanism.
    """
    playbook = _playbook()
    collaborators = _Collaborators()
    _mapped(collaborators, closed_in_clickup=state, last_observed=state)

    await _reconcile(_start(playbook), playbook, collaborators)

    # SPECIFIED: no outcome is recorded for that step.
    assert collaborators.record.calls == [], (
        "an outcome was recorded although the task's state had not changed"
    )
    # SPECIFIED corollary: the retained state is left where it was.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.last_observed_closed is state


async def test_reconciliation_never_overwrites_other_recording_paths() -> None:
    """Scenario: Reconciliation never overwrites other recording paths.

    WHEN a step's outcome was recorded through a non-ClickUp path and the
    step's mapped task has never been observed closed
    THEN the reconciliation pass records nothing for that step, leaving
    the recorded outcome standing.

    This is the scenario the observed-state column exists for: the step is
    `Satisfied` by attestation while its ClickUp task is still open -- the
    state the one-way-status non-goal *guarantees* will occur. A pass that
    compared ClickUp's state against the step's recorded outcome would
    overwrite it with `InProgress` here.
    """
    playbook = _playbook()
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id=STEP_ID,
        outcome=Satisfied,
        provenance=_provenance(source="attestation", who="Helen"),
    )
    collaborators = _Collaborators()
    _mapped(collaborators, closed_in_clickup=False, last_observed=False)

    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED: the reconciliation pass records nothing for that step.
    assert collaborators.record.calls == [], (
        "reconciliation overwrote an outcome recorded through another "
        f"path: {collaborators.record.calls}"
    )
    # SPECIFIED: leaving the recorded outcome standing.
    progress = launch.progress_for(STEP_ID)
    assert progress is not None
    assert progress.outcome is Satisfied
    assert progress.provenance.source == "attestation"


# ---------------------------------------------------------------------------
# Requirement: Completion flows from ClickUp to the launch as a recorded
# outcome -- the one-way clause
# ---------------------------------------------------------------------------


async def test_the_system_never_closes_a_task() -> None:
    """Scenario: The system never closes a task.

    WHEN a mapped step's outcome is recorded through any non-ClickUp path
    THEN the step's ClickUp task keeps whatever status it has -- the
    system does not write task status.

    Both passes are run over the launch, because either could be the place
    a status write crept in: the convergence pass writes to ClickUp, and
    the reconciliation pass is the one that sees the disagreement between
    an attested `Satisfied` and an open task.
    """
    playbook = _playbook()
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id=STEP_ID,
        outcome=Satisfied,
        provenance=_provenance(source="attestation"),
    )
    collaborators = _Collaborators()
    _mapped(collaborators, closed_in_clickup=False, last_observed=False)
    status_before = collaborators.clickup.tasks[TASK_ID].status

    await _converge(launch, playbook, collaborators)
    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED: the system does not write task status.
    status_writes = [
        payload
        for payload in collaborators.clickup.calls_named("update_task")
        if "status" in payload["fields"]
    ]
    assert status_writes == [], (
        f"the sync wrote a task status to ClickUp: {status_writes}"
    )
    # SPECIFIED: the task keeps whatever status it has.
    assert collaborators.clickup.tasks[TASK_ID].status == status_before
    assert collaborators.clickup.tasks[TASK_ID].closed is False


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - How many ClickUp reads one pass makes per launch (`design.md`'s "one
#   read per launch plus writes proportional to actual drift"). A
#   performance property of the design, not a stated requirement.
# - What the reconciliation pass does when `record_step_outcome` itself
#   rejects a recording -- e.g. a closed task mapped to a
#   `prohibited-tactic` step, which the hazard rules forbid satisfying.
#   The projection requirement forbids ever creating such a task, so the
#   state is unreachable through this capability's own behaviour, and no
#   scenario states what should happen if it arises anyway.
# - Ordering between the convergence and pull halves within one run.
# ---------------------------------------------------------------------------
