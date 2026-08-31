"""A step that becomes `automated` leaves the ClickUp loop, staying active.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-clickup-sync/spec.md`

Covers the two scenarios the MODIFIED requirement *A step that is not
active leaves the loop* adds when it is generalised to *a step the loop
no longer projects*:

- *A step that becomes automated leaves the loop while staying active* —
  both directions.
- *Closing the orphaned task of an automated step records nothing* — the
  reconciliation half. The webhook half of that same scenario ("reaches
  the system by webhook **or** by the reconciliation pass") is covered in
  `tests/unit/launch/infrastructure/driving/test_clickup_webhook_automated_step.py`.

The requirement's five carried-forward scenarios are unchanged in
statement and behaviour and are already covered by
`tests/unit/launch/infrastructure/driven/test_clickup_non_active_steps_leave_loop.py`
and `.../test_clickup_sync_retired_steps.py`; they are accounted for
against those tests in `test-manifest.md`, and this pass does not edit
them.

See `test-manifest.md` at the change root for the full accounting,
including the obsolete-test candidates this delta produces.

## Why this case is the one the rule most needs

The requirement says so itself: "a step that becomes `automated` stays
`active`: it is still part of the launch's obligations, so nothing about
its status signals its departure from the loop, and a person closing its
orphaned task would otherwise record a `clickup`-sourced completion for
work a handler was about to do." `design.md` records that the inward
reconciliation builds its `defined` set from `served_steps`, which
filters on status alone — so before this change the flip that enables the
automation is also what would permanently suppress it, `Satisfied` being
terminal for hazard `none`.

## Level

Both scenarios are stated over a pass — what it sends, and what it
records — so `converge_launch(...)`/`reconcile_launch(...)` over in-memory
fakes is the smallest unit that can observe them, and it is the level the
sibling leave-the-loop file already establishes.

## INVENTED

Nothing new. The harness below is the one
`test_clickup_non_active_steps_leave_loop.py` records — `converge_launch`
and `reconcile_launch` over in-memory fakes with the outcome recorder
injected as `record_outcome=` and the roster as `roster=`. It is
re-declared here rather than imported because that file must not be
edited by this pass and these directories carry no shared test package.

## Expected first-run state

`is_projectable`'s kind-awareness already exists on the **outward** side,
so the outward halves below may pass on their first run against the
current implementation — the target-exists case, which establishes that
the projection already behaves as the revised requirement states. The
**inward** halves are expected to fail: `tasks.md` 4a.1 is what changes
`reconcile_launch`'s `defined` set, and `design.md` records that it keys
on status alone today. Per `ai-toolkit:testing`, a first-run pass on the
outward halves is coverage of existing behaviour; a first-run failure on
the inward halves is the wrong-value state, not an absent target.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
`uv run pytest tests/integration` — 3 passed, 81 skipped (no database is
configured here).
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
from commerce_ops.shared.domain.clickup import ClickUpListState
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
TASK_ID: Final = "task-1"
LAUNCH_DATE: Final = date(2027, 3, 2)

STEP_ID: Final = "lp.listing.007"
STEP_NAME: Final = "Choose the sub-category node"
COMPOSED_NAME: Final = f"{STEP_NAME} · {STEP_ID}"

HANDLER_NAME: Final = "listing.subcategory_advisor"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_CLICKUP: Final = "clickup-alice"


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
        "name": STEP_NAME,
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
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


def _human_step() -> StepDefinition:
    """The step as it stands today: `active`, `human`, projected."""
    return _step()


def _automated_step() -> StepDefinition:
    """The same step after the flip `tasks.md` 9.1 performs by hand:
    `automated`, naming a confirmer, and still `active`."""
    return _step(
        kind=StepKind.AUTOMATED,
        assignees=(),
        confirmer=ALICE,
        handler=HANDLER_NAME,
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


def _playbook_with(step: StepDefinition) -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(step, *fillers))


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (the shapes `test_clickup_non_active_steps_leave_loop.py`
# records)
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
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = ALICE_CLICKUP
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_Person, ...]:
        return (_Person(ALICE, "Alice Admin"),)

    people = list_people

    async def person(self, person_id: str) -> _Person | None:
        return _Person(ALICE, "Alice Admin") if person_id == ALICE else None

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


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
    roster: _FakeRoster = field(default_factory=_FakeRoster)
    recorder: _FakeRecorder = field(default_factory=_FakeRecorder)


async def _converge(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """The call shape `test_clickup_non_active_steps_leave_loop.py`
    records — the single correction point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        roster=collaborators.roster,
        folder_id=FOLDER_ID,
    )


async def _reconcile(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """The call shape `test_clickup_non_active_steps_leave_loop.py`
    records — the single correction point."""
    await reconcile_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        record_outcome=collaborators.recorder,
    )


def _standing_task(*, task_closed: bool = False) -> _Collaborators:
    """A mapped, still-standing task for the step under test — exactly
    what the flip to `automated` leaves behind, since the sync does not
    tear down a task for a step it no longer projects."""
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
# Requirement (MODIFIED): A step that is not active leaves the loop
# ---------------------------------------------------------------------------


async def test_a_step_that_becomes_automated_leaves_the_loop_while_staying_active() -> (
    None
):
    """Scenario: A step that becomes automated leaves the loop while
    staying active.

    WHEN an `active` `human` step with a mapped task is changed to kind
    `automated`, remains `active`, and the next pass runs
    THEN no update is sent for its task and no state change on it is
    recorded.

    The task is seeded **closed** so the inward half has something to
    record if the implementation wrongly does — an assertion over an
    unchanged task would pass vacuously, which is the trap the sibling
    de-activation test records for the same reason.
    """
    collaborators = _standing_task(task_closed=True)
    playbook = _playbook_with(_automated_step())
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)
    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED (outward): no update is sent for its task, and its
    # existing task is neither renamed, re-dated, closed nor deleted.
    assert collaborators.clickup.writes_touching(TASK_ID) == []
    assert TASK_ID in collaborators.clickup.tasks
    # SPECIFIED: nor is a second task created for it.
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())
    # SPECIFIED (inward): no state change on it is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the step is still `active` — this rule cannot be keyed
    # on status, which is the whole point of the generalisation.
    served = {step.identifier for step in playbook.served_steps}
    assert STEP_ID in served, (
        "the fixture's automated step is not in the served set, so this "
        "test would pass for the wrong reason"
    )


async def test_closing_the_orphaned_task_of_an_automated_step_records_nothing() -> None:
    """Scenario: Closing the orphaned task of an automated step records
    nothing — the reconciliation half.

    WHEN the mapped task of an `active` `automated` step is closed in
    ClickUp, and that closure reaches the system by the reconciliation
    pass
    THEN no outcome is recorded for that step, and its retained observed
    state is updated so the closure is never replayed.

    This is the case `tasks.md` 9.2 creates by hand and 4a.4 exists to
    verify: without it, the hand-closure records a `clickup`-sourced
    `Satisfied`, which is terminal for hazard `none` and permanently
    suppresses the automation the flip was performed to enable.
    """
    collaborators = _standing_task(task_closed=True)
    # The step was projected while it was `human`, so its retained state
    # is "not closed" — a genuine transition is available to be recorded.
    mapping = collaborators.mapping.tasks[(PRODUCT_ID, STEP_ID)]
    assert mapping.last_observed_closed is False

    playbook = _playbook_with(_automated_step())
    launch = _start(playbook)

    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED: no outcome is recorded for that step.
    assert collaborators.recorder.calls == []
    # SPECIFIED: its retained observed state is updated, so the closure
    # is never replayed as a transition later.
    assert mapping.last_observed_closed is True


async def test_a_closure_while_automated_is_not_replayed_if_the_step_returns() -> None:
    """Requirement statement: "Observations of the task SHALL nonetheless
    keep updating its retained observed state, recording nothing, so that
    what happened while the step was out of the projection is never
    replayed as a transition later: a closure that occurred then is not
    recorded, not even after the step returns to the projection."

    The generalised form of the carried-forward *A closure during
    retirement is never replayed*, applied to the kind route. Stated in
    the requirement rather than in the new scenarios, and it is the half
    that makes the observed-state update above load-bearing rather than
    bookkeeping: an implementation that skipped the step entirely — no
    recording *and* no observation — would pass the scenario above and
    fail here the moment the step came back.
    """
    collaborators = _standing_task(task_closed=True)
    automated = _playbook_with(_automated_step())
    launch = _start(automated)

    await _reconcile(launch, automated, collaborators)
    assert collaborators.recorder.calls == []

    # The flip is reverted: the step is `human` and `active` again, its
    # task still closed and never re-opened.
    human_again = _playbook_with(_human_step())
    await _reconcile(launch, human_again, collaborators)

    # SPECIFIED: the closure that happened while it was out of the
    # projection is not recorded, before or after the return.
    assert collaborators.recorder.calls == []


async def test_a_step_returning_to_human_work_rejoins_the_loop() -> None:
    """Requirement statement: "A step returning to `active` `human` work
    SHALL rejoin the loop on the next pass, resuming through its existing
    mapping and task where they still stand".

    The revised wording of the carried-forward *An un-retired step
    resumes through its existing task*: this delta narrows "returning to
    `active`" to "returning to `active` **`human`** work", because a step
    returning to `active` as `automated` must not rejoin. Both halves are
    asserted — no second task on the return, and no rejoining while the
    step is still automated.
    """
    collaborators = _standing_task()
    automated = _playbook_with(_automated_step())
    launch = _start(automated)

    # Out of the loop while automated.
    await _converge(launch, automated, collaborators)
    assert collaborators.clickup.writes_touching(TASK_ID) == []

    # Back to `active` `human` work: the loop resumes through the
    # existing mapping.
    human_again = _playbook_with(_human_step())
    await _converge(launch, human_again, collaborators)

    # SPECIFIED: no second task, and the mapping still names the old one.
    assert all(STEP_ID not in name for name in collaborators.clickup.created_names())
    assert collaborators.mapping.replacements == []
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.task_id == TASK_ID


async def test_a_prohibited_tactic_step_also_leaves_the_loop() -> None:
    """Requirement statement: "or its hazard became `prohibited-tactic`,
    which the projection requirement already excludes."

    The third field the generalised rule names, stated in no scenario.
    Covered because the rule's whole content is that it keys on the
    departure rather than on any one field — a rule rewritten to test
    kind *and* status, and still not hazard, would leave this undefined
    exactly as the status-only rule left the kind case.
    """
    collaborators = _standing_task(task_closed=True)
    prohibited = _playbook_with(_step(hazard=Hazard.PROHIBITED_TACTIC))
    launch = _start(prohibited)

    await _converge(launch, prohibited, collaborators)
    await _reconcile(launch, prohibited, collaborators)

    assert collaborators.clickup.writes_touching(TASK_ID) == []
    assert collaborators.recorder.calls == []
