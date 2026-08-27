"""Projection half of `launch-clickup-sync`: the list, the tasks, the dates.

Derived strictly from the delta spec:
`openspec/changes/add-clickup-completion-loop/specs/launch-clickup-sync/spec.md`

Covers, as ADDED requirements:

- *Each launch is projected into its own ClickUp list* -- all four
  scenarios.
- *Human-attested steps are projected as tasks* -- all six scenarios.
- *Task due dates derive from the launch schedule* -- all three scenarios.

Every outcome these scenarios state is observable from the convergence
pass over one launch, against a fake ClickUp and a fake mapping store --
no HTTP, no Postgres -- so the fast mocked unit tier is the smallest level
that can observe them. The one exception is *A graduated launch is left
alone*, discussed below.

See `openspec/changes/add-clickup-completion-loop/test-manifest.md` for the
full specified/derived/deliberately-untested accounting.

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 4.1-4.3 fix the module
(`launch/infrastructure/driven/clickup_sync.py`) and what the pass must
do, but no artifact fixes a call shape. Assumed here, and recorded in the
manifest as unresolved project questions:

- `converge_launch(...)` in that module, taking its collaborators as
  keyword arguments the way `advance_gate` does in
  `tests/unit/launch/application/test_graduation.py`:
  `launch`, `playbook`, `clickup`, `mapping`, `read_product`, `folder_id`.
  `_converge()` below is the single place to correct if it differs.
- `ClickUpSyncError` exported from the same module as the pass's own
  failure signal (this project's one-exception-per-rejected-family
  precedent). The unconfigured-folder test accepts any exception, so only
  the import would need correcting.
- The ClickUp port's four operations, as `tasks.md` 1.2-1.4 name them:
  `create_list(folder_id, name)`, `create_task(list_id, name, ...)`,
  `update_task(task_id, fields)`, `list_tasks(list_id)`.
- The mapping store's method names (`_FakeMapping` below). `tasks.md` 3.1
  fixes the two tables and the last-observed-closed column; nothing names
  the store's methods.
- `read_product` as an async callable returning the catalog product,
  standing in for `catalog.application.get_product_by_id` -- the same
  public-surface crossing `design.md` names, injected rather than reached
  through a session, exactly as `test_graduation.py` injects the catalog
  stamp.

Correcting any name or call shape above is a fixture correction (failure
state 3 in `ai-toolkit:testing`). What must survive unweakened is what
each test asserts: which ClickUp writes happen, which do not, what
associations end up recorded, and what due date each task carries.

## Due dates are asserted on the effective value, not on one call

No artifact says whether a due date reaches ClickUp on the create call or
on a following update -- `create_task(list_id, name, description)` as
`clickup-task-client` specifies it carries no due-date parameter, so
either is a legitimate implementation. `_FakeClickUp` therefore folds any
due-date-bearing field from either call into the task's effective due
date, and the assertions read that. `_as_date()` normalises a `date`, a
`datetime` or an epoch-millisecond number, so nothing here pins a wire
encoding the spec does not state.

## At the time this pass was written, nothing under test exists

`commerce_ops.launch.infrastructure.driven.clickup_sync` is created by
task 4.1. Every test here is expected to fail on an absent target
(`ModuleNotFoundError`) until it lands. Per `ai-toolkit:testing`, that
failure establishes only absence -- nothing about whether these
assertions are any good.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Cadence,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
    WindowAnchor,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

# SPECIFIED (launch-playbook spec, unchanged): the eight gates, in order.
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
MOVED_LAUNCH_DATE: Final = date(2027, 3, 16)

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures -- shapes as `tests/unit/launch/domain/test_launch_run.py`
# and `test_launch_dates.py` record them
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
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": _any_discipline(),
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


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated, so the sync never projects a filler and
    every projection assertion is untouched by them."""
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        automation_brief="Held until the automated check reports green.",
        handler="fixture.holding_check",
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=_fill(steps))


def _start(
    playbook: LaunchPlaybook, *, launch_date: date | None = LAUNCH_DATE
) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=launch_date
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


def _graduated(playbook: LaunchPlaybook) -> Launch:
    """A launch walked along the ordinary advance path to `graduated`."""
    from commerce_ops.launch.domain.launch_run import (
        ApprovalDecision,
        GateApproval,
        Provenance,
    )

    launch = _start(playbook)
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=RECORDED_AT,
                        evidence="filler obligations satisfied by the walk",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=RECORDED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    assert launch.current_gate == "graduated"
    # No posture-carrying graduation approval is recorded: the walk stops
    # *at* `graduated` rather than advancing past it, and what the scenario
    # names is the launch having reached that gate.
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    """Stands in for `catalog.application.get_product_by_id`."""

    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product
        self.calls: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.calls.append(product_id)
        return self._product


@dataclass
class _FakeTask:
    """A ClickUp task as the fake holds it, and as `list_tasks` reports it."""

    id: str
    name: str
    list_id: str
    status: str = "to do"
    closed: bool = False
    due_date: Any = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CreatedTask:
    """What `create_task` hands back -- only `.id` is consumed."""

    id: str
    url: str


def _due_date_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    """Any due-date-bearing field in a create/update payload.

    Returns (present, value). Matched on the field name containing "due"
    so the pass may spell it `due_date`, `dueDate` or `due_date_time`
    without this fake caring -- none of those is fixed by an artifact.
    """
    for key, value in fields.items():
        if "due" in key.lower():
            return True, value
    return False, None


class _FakeClickUp:
    """In-memory ClickUp, recording every call.

    Implements the four operations `tasks.md` 1.2-1.4 name. A task's
    *effective* due date is whatever the most recent create or update
    payload carried, so the assertions never depend on which call the
    pass chose to put it on.
    """

    def __init__(self) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    # -- writes ------------------------------------------------------------

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

    # -- reads -------------------------------------------------------------

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

    # -- test-side helpers -------------------------------------------------

    def seed_list(self, list_id: str, name: str = "seeded list") -> str:
        self.lists[list_id] = name
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
    # `move-playbook-steps-to-postgres`: the retained last-written
    # compositions the conditional wording-healing keys on.
    retained_name: str | None = None
    retained_body: str | None = None
    retained_assignees: tuple[str, ...] | None = None


class _FakeMapping:
    """In-memory stand-in for the two mapping tables (`tasks.md` 3.1)."""

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
        # A newly projected task's retained observed state starts as not
        # closed -- SPECIFIED by the completion requirement.
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
        """`move-playbook-steps-to-postgres`: a system write of a field
        updates that field's retained value; `None` leaves it untouched."""
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


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(
        default_factory=lambda: _FakeCatalog(
            _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)
        )
    )


# ---------------------------------------------------------------------------
# The single correction point: how the convergence pass is invoked
# ---------------------------------------------------------------------------


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
    *,
    folder_id: str | None = FOLDER_ID,
) -> None:
    """INVENTED call shape (see the module docstring)."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=folder_id,
    )


def _as_date(value: Any) -> date | None:
    """Normalises a due date to the calendar day it names."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    pytest.fail(f"cannot read {value!r} as a due date")


# ---------------------------------------------------------------------------
# Requirement: Each launch is projected into its own ClickUp list
# ---------------------------------------------------------------------------


async def test_a_launch_without_a_list_gets_one() -> None:
    """Scenario: A launch without a list gets one.

    WHEN the reconciliation pass runs and an active launch has no recorded
    ClickUp list
    THEN a list is created in the configured folder, named with the
    product's catalog name and SKU
    AND the association between the launch and the created list is
    recorded.
    """
    playbook = _playbook()
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: a list is created, in the configured folder.
    created = collaborators.clickup.calls_named("create_list")
    assert len(created) == 1, f"expected exactly one list creation, got {created}"
    assert created[0]["folder_id"] == FOLDER_ID

    # SPECIFIED: named with the product's catalog name and SKU. DERIVED:
    # containment rather than an exact format -- no artifact fixes the
    # separator or ordering, only that both appear.
    name = created[0]["name"]
    assert PRODUCT_NAME in name, (
        f"the list name does not carry the product name: {name!r}"
    )
    # The SKU as the catalog records it -- `PRODUCT_SKU.value`, never
    # `str(PRODUCT_SKU)`. Asserting the latter is what let the name be
    # composed out of the value object's repr for four live lists: the
    # repr contains itself, so containment held while the name was
    # wrong. The second assertion keeps that reading from returning.
    assert PRODUCT_SKU.value in name, f"the list name does not carry the SKU: {name!r}"
    assert "Sku(" not in name, (
        f"the list name carries the SKU value object rather than its value: {name!r}"
    )

    # SPECIFIED: the name comes from the catalog, through its public
    # surface -- the product identifier is opaque and never parsed.
    assert collaborators.catalog.calls == [PRODUCT_ID]

    # SPECIFIED: the association between the launch and the created list is
    # recorded.
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) is not None


# `test_an_existing_list_is_not_recreated` stood here. `heal-a-launchs-deleted-list`
# revised its scenario's WHEN -- the no-second-list rule now holds because
# ClickUp reports the list as existing, not because a record is merely
# present -- and this file's ClickUp double cannot construct that state.
# Superseded by `test_clickup_sync_list_healing.py`::
# `test_a_list_clickup_reports_as_existing_is_not_recreated`, which carries
# both of its assertions unchanged and adds the once-per-pass probe the
# revised scenario turns on.


async def test_a_graduated_launch_is_left_alone() -> None:
    """Scenario: A graduated launch is left alone.

    WHEN the reconciliation pass runs and a launch has reached `graduated`
    THEN no list or task is created or updated for it and no outcome is
    recorded from it.

    LEVEL NOTE, recorded rather than glossed: `design.md` puts the filter
    upstream, in `LaunchRepository.list_active()`, so a graduated launch
    would normally never reach this pass at all -- that half is asserted in
    `tests/integration/launch/test_launch_clickup_mapping.py`. This test
    asserts the same specified outcome at the per-launch entry point, which
    is where "no list or task is created or updated for it" is observable
    without a database. If the implementation relies solely on
    `list_active()` and the pass is not itself graduated-safe, the correct
    response is to add the guard or move this assertion to the pass level
    -- not to weaken what it asserts.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    collaborators = _Collaborators()

    await _converge(_graduated(playbook), playbook, collaborators)

    # SPECIFIED: no list or task is created or updated for it.
    assert collaborators.clickup.calls == [], (
        f"a graduated launch caused ClickUp writes: {collaborators.clickup.calls}"
    )
    assert collaborators.mapping.lists == {}
    assert collaborators.mapping.tasks == {}


async def test_missing_folder_configuration_fails_the_run() -> None:
    """Scenario: Missing folder configuration fails the run.

    WHEN the reconciliation pass runs, an active launch needs a list, and
    no parent folder is configured
    THEN the pass reports failure rather than skipping the launch
    silently.

    SPECIFIED: failure is reported. DERIVED mechanism: the pass raises,
    which is how a job body reports a failed run to the scheduled-work
    machinery (the reading `tests/unit/catalog/infrastructure/driving/
    test_daily_digest_job.py` already records for this project). Not
    narrowed to a type, because no artifact names one.
    """
    playbook = _playbook()
    collaborators = _Collaborators()

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see above
        await _converge(_start(playbook), playbook, collaborators, folder_id=None)

    # SPECIFIED: rather than skipping the launch silently -- nothing may be
    # left half-recorded either.
    assert collaborators.clickup.calls_named("create_list") == []
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) is None


# ---------------------------------------------------------------------------
# Requirement: Human-attested steps are projected as tasks
# ---------------------------------------------------------------------------


async def test_a_human_attested_step_gets_a_task() -> None:
    """Scenario: A human-attested step gets a task.

    WHEN the reconciliation pass runs and an `active` `human` step of an
    active launch has no recorded task
    THEN a task named for the step is created in the launch's list
    AND the association between the step and the created task is recorded.
    """
    step = _step(identifier="listing.title-conforms", kind=StepKind.HUMAN)
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    # SPECIFIED: a task is created, in the launch's list.
    assert len(created) == 1, f"expected exactly one task creation, got {created}"
    recorded_list = await collaborators.mapping.list_id_for(PRODUCT_ID)
    assert created[0]["list_id"] == recorded_list

    # SPECIFIED: named for the step. DERIVED: "named for the step" is read
    # as the step's identifier being recoverable from the name; no artifact
    # fixes a title format, and `design.md` puts richer task bodies out of
    # scope for this slice.
    assert "listing.title-conforms" in created[0]["name"], (
        f"the task name does not name the step: {created[0]['name']!r}"
    )

    # SPECIFIED: the association between the step and the created task is
    # recorded.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert mapping is not None
    assert mapping.task_id in collaborators.clickup.tasks


async def test_an_existing_task_is_not_recreated() -> None:
    """Scenario: An existing task is not recreated.

    WHEN the reconciliation pass runs and a step already has a recorded
    task
    THEN no new task is created for that step.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(LIST_ID, "task-existing")
    collaborators.mapping.seed_task("listing.title-conforms", "task-existing")

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: no new task is created for that step.
    assert collaborators.clickup.calls_named("create_task") == []
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert mapping is not None
    assert mapping.task_id == "task-existing"


async def test_a_prohibited_tactic_step_is_never_projected() -> None:
    """Scenario: A prohibited-tactic step is never projected.

    WHEN the reconciliation pass runs and a step carries the
    `prohibited-tactic` hazard
    THEN no task is created for it, whatever its kind.

    Parametrised over the kinds inline rather than with
    `pytest.mark.parametrize`, because "whatever its kind" is a single
    specified fact: the hazard decides on its own.
    """
    steps = tuple(
        _step(
            identifier=f"reviews.purchase-ring-{kind.value}",
            hazard=Hazard.PROHIBITED_TACTIC,
            blocking=False,
            kind=kind,
            # An `automated` step beyond draft owes a brief, and an
            # `active` one owes a handler, for the playbook to be
            # coherent (launch-playbook spec).
            automation_brief=None if kind is StepKind.HUMAN else "decided",
            handler=None if kind is StepKind.HUMAN else "fixture.tactic_check",
        )
        for kind in (StepKind.HUMAN, StepKind.AUTOMATED)
    )
    playbook = _playbook(steps=steps)
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: no task is created for it, whatever its execution mode.
    assert collaborators.clickup.calls_named("create_task") == []
    assert collaborators.mapping.tasks == {}


async def test_a_deleted_task_for_unfinished_work_is_re_projected() -> None:
    """Scenario: A deleted task for unfinished work is re-projected.

    WHEN the reconciliation pass runs and a mapped task no longer exists
    in the launch's list while the step's recorded outcome is not terminal
    THEN a new task is created for the step and the mapping is replaced
    with the new task.

    The step's recorded outcome is left absent -- never recorded at all --
    which is the plainest non-terminal state.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    # Mapped, but absent from ClickUp: the task was deleted there.
    collaborators.mapping.seed_task("listing.title-conforms", "task-vanished")

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: a new task is created for the step.
    created = collaborators.clickup.calls_named("create_task")
    assert len(created) == 1, f"the vanished task was not re-projected: {created}"

    # SPECIFIED: the mapping is replaced with the new task.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert mapping is not None
    assert mapping.task_id != "task-vanished"
    assert mapping.task_id in collaborators.clickup.tasks
    # SPECIFIED by the completion requirement: a newly projected task's
    # retained observed state starts as not closed.
    assert mapping.last_observed_closed is False


async def test_a_deleted_task_for_finished_work_stays_gone() -> None:
    """Scenario: A deleted task for finished work stays gone.

    WHEN the reconciliation pass runs and a mapped task no longer exists
    in the launch's list while the step's recorded outcome is terminal
    THEN no task is recreated for that step.
    """
    step = _step(identifier="listing.title-conforms")
    playbook = _playbook(steps=(step,))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.mapping.seed_task("listing.title-conforms", "task-vanished")

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: no task is recreated for that step.
    assert collaborators.clickup.calls_named("create_task") == [], (
        "a task was recreated for work that is already finished"
    )
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert mapping is not None
    assert mapping.task_id == "task-vanished"


# ---------------------------------------------------------------------------
# Requirement: Task due dates derive from the launch schedule
# ---------------------------------------------------------------------------


async def test_tasks_carry_due_dates_resolved_from_the_launch_date() -> None:
    """Scenario: Tasks carry due dates resolved from the launch date.

    WHEN a task is projected for a step with a bounded due period and the
    launch has a launch date
    THEN the task's due date is the resolved due period's end.

    Two anchors are used: an offset (whose period starts and ends on the
    same day) and a window (whose end differs from its start), so a pass
    that used the period's *start* fails on the window step rather than
    passing by coincidence. Expected dates are written as literals rather
    than recomputed, the convention `test_timing_anchor.py` records.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms", timing_anchor=OffsetAnchor(days=-7)
            ),
            _step(
                identifier="rank.review-velocity",
                gate="ignition",
                timing_anchor=WindowAnchor(start=28, end=55),
            ),
        )
    )
    collaborators = _Collaborators()

    await _converge(_start(playbook, launch_date=LAUNCH_DATE), playbook, collaborators)

    tasks_by_step = {}
    for step_id in ("listing.title-conforms", "rank.review-velocity"):
        mapping = await collaborators.mapping.task_for(PRODUCT_ID, step_id)
        assert mapping is not None, f"{step_id} was never projected"
        tasks_by_step[step_id] = collaborators.clickup.tasks[mapping.task_id]

    # SPECIFIED: the resolved due period's end. Launch date 2027-03-02.
    assert _as_date(tasks_by_step["listing.title-conforms"].due_date) == date(
        2027, 2, 23
    )
    assert _as_date(tasks_by_step["rank.review-velocity"].due_date) == date(2027, 4, 26)


async def test_a_moved_launch_date_updates_existing_tasks() -> None:
    """Scenario: A moved launch date updates existing tasks.

    WHEN the launch date has moved since a step's task was created and the
    reconciliation pass runs
    THEN that task's due date is updated to the newly resolved due
    period's end.

    The already-created task carries the date the old launch date implied
    (2027-02-23); the launch is then moved 14 days later, so the newly
    resolved end is 2027-03-09.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms", timing_anchor=OffsetAnchor(days=-7)
            ),
        )
    )
    launch = _start(playbook, launch_date=LAUNCH_DATE)
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, "task-existing", due_date=datetime(2027, 2, 23, tzinfo=UTC)
    )
    collaborators.mapping.seed_task("listing.title-conforms", "task-existing")

    launch.move_launch_date(MOVED_LAUNCH_DATE)
    await _converge(launch, playbook, collaborators)

    # SPECIFIED: the task's due date is updated to the newly resolved end.
    assert _as_date(collaborators.clickup.tasks["task-existing"].due_date) == date(
        2027, 3, 9
    )
    # SPECIFIED corollary: the existing task is updated, not replaced.
    assert collaborators.clickup.calls_named("create_task") == []


async def test_an_unresolvable_due_period_means_no_due_date() -> None:
    """Scenario: An unresolvable due period means no due date.

    WHEN a task is projected for a step of a launch with no launch date,
    or for a step whose anchor is open-ended or recurring
    THEN the task carries no due date.

    All three of the scenario's cases are exercised: the open-ended and
    recurring anchors against a launch that *does* have a date (so the
    anchor is what makes the period unresolvable), and every anchor kind
    against a launch with no date.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="ops.stock-monitoring",
                timing_anchor=OpenEndedAnchor(start=59),
            ),
            _step(
                identifier="ops.weekly-review",
                gate="ignition",
                timing_anchor=RecurringAnchor(cadence=Cadence.WEEKLY),
            ),
            _step(
                identifier="listing.title-conforms", timing_anchor=OffsetAnchor(days=-7)
            ),
        )
    )

    # Case 1: a launch date exists, but the anchors do not yield an end.
    dated = _Collaborators()
    await _converge(_start(playbook, launch_date=LAUNCH_DATE), playbook, dated)
    for step_id in ("ops.stock-monitoring", "ops.weekly-review"):
        mapping = await dated.mapping.task_for(PRODUCT_ID, step_id)
        assert mapping is not None, f"{step_id} was never projected"
        # SPECIFIED: the task carries no due date.
        assert dated.clickup.tasks[mapping.task_id].due_date is None, (
            f"{step_id} was given a due date its anchor cannot yield"
        )

    # Case 2: no launch date at all -- no step has a resolvable period.
    undated = _Collaborators()
    await _converge(_start(playbook, launch_date=None), playbook, undated)
    for mapping in await undated.mapping.tasks_for(PRODUCT_ID):
        assert undated.clickup.tasks[mapping.task_id].due_date is None, (
            f"{mapping.step_id} was given a due date although the launch "
            "has no launch date"
        )
    # Guard: the steps really were projected, so the loop above is not
    # vacuous. A launch with no date still gets its tasks -- the
    # requirement withholds the due date, not the task.
    assert len(await undated.mapping.tasks_for(PRODUCT_ID)) == 3


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the per-launch list name excludes the opaque product
#   identifier. The requirement's parenthetical ("the product identifier
#   itself is opaque and never parsed for meaning") constrains how the name
#   is *derived*, which the catalog-read assertion above covers; it does
#   not forbid the identifier appearing in the name, so asserting its
#   absence would impose a constraint nobody stated.
# - Clearing a due date that has become unresolvable on an already-created
#   task (`design.md`: "the pass clears a stale one if the date becomes
#   unresolvable"). No `#### Scenario:` block states it -- the
#   unresolvable-period scenario is written over projection only -- so it
#   is left as design intent rather than asserted as a requirement.
# - The order in which lists and tasks are created within one pass, and
#   the create-then-record ordering `design.md`'s Risks section describes.
#   Neither is stated by a scenario.
# - Gate metric conditions never being projected. The requirement states
#   it, but a metric condition is not a step and there is no task-shaped
#   thing to assert the absence of beyond the per-step assertions above;
#   the projection is driven by the playbook's steps.
# ---------------------------------------------------------------------------
