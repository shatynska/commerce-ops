"""How a projected ClickUp task is named, and when its name is left alone.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-clickup-sync/spec.md`

Covers the four scenarios the `MODIFIED` requirement *Human-attested
steps are projected as tasks* revises or adds:

- *A human-attested step gets a task* — as revised: "a task named with the
  step's description followed by its identifier".
- *A renamed task still resolves to its step* (new).
- *An edited task name is never restored* (new).
- *An over-long name is shortened rather than failing* (new).

The requirement's five unchanged scenarios (an existing task is not
recreated, a prohibited-tactic step is never projected, the two
deleted-task scenarios, automated/ai-assisted steps are never projected)
are already covered in `test_clickup_sync_projection.py` and are not
restated here.

**Level.** Every outcome these scenarios state is observable from the
convergence pass over one launch, against a fake ClickUp and a fake
mapping store — no HTTP, no Postgres — so the fast mocked unit tier is
the smallest level that can observe them, exactly as
`test_clickup_sync_projection.py` records.

**The doubles and the call shape are inherited from
`test_clickup_sync_projection.py`**, which records them as INVENTED
(`converge_launch(launch=, playbook=, clickup=, mapping=, read_product=,
folder_id=)`, and the ClickUp port's four operations). They are
re-declared here rather than imported because that file is an existing
test this pass must not edit. One deliberate difference: `_FakeClickUp`
here also records the `description` passed to `create_task`, which the
projection file's fake drops — the over-long-name scenario asserts on the
created task's *body*, so it has to be observable. Correcting any name or
call shape is a fixture correction (failure state 3 in
`ai-toolkit:testing`); changing what these tests assert about the
resulting name is not.

**The task-name limit is read from the implementation's own named
constant** rather than hard-coded. `tasks.md` 1.1 requires the confirmed
limit to be "express[ed] ... as a named constant rather than a bare
literal" but no artifact fixes the constant's *name*, and `design.md`
Decision 4 leaves the number itself to be confirmed ("believed to be 255
... the rule holds whatever the number turns out to be"). `_task_name_
limit()` below locates it; both the name and the number are recorded as
unresolved project questions in
`openspec/changes/describe-playbook-steps/test-manifest.md`.

At the time of writing `StepDefinition` has no `description` field and
`_task_name` composes something else, so these tests are expected to fail
— the constructions on an unexpected keyword argument, which per
`ai-toolkit:testing` establishes only that the field is absent.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 584 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres, which is
not available here.
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
from commerce_ops.launch.infrastructure.driven import clickup_sync
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

# A step as the shipped set carries it: a reference-row identifier and the
# row's own wording. The wording asserts nothing on its own.
STEP_ID: Final = "lp.creative.008"
STEP_DESCRIPTION: Final = (
    "Main image designed to be scroll-stopping and explicitly different "
    "from competitors, not blending in"
)

# DERIVED (design.md Decision 4): "The separator matches the one the name
# already uses." Only `test_the_composed_name_uses_the_authored_separator`
# depends on this; every other assertion below reads the description and
# the identifier separately.
SEPARATOR: Final = " · "


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


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (inherited from `test_clickup_sync_projection.py`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product
        self.calls: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.calls.append(product_id)
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
    """In-memory ClickUp, recording every call — including task bodies."""

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
        # `name` defaults to the id but is overridable, which is what the
        # renamed-task tests seed. Merged rather than passed twice.
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
    # `move-playbook-steps-to-postgres`: the retained last-written
    # compositions the conditional wording-healing keys on.
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


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
) -> None:
    """INVENTED call shape — the single correction point (see docstring)."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=FOLDER_ID,
    )


def _task_name_limit() -> int:
    """The implementation's own task-name limit constant.

    `tasks.md` 1.1 requires the confirmed ClickUp limit to be expressed as
    a named constant in `clickup_sync.py`. Its name is not fixed by any
    artifact, so it is located by shape: a public, integer, module-level
    constant whose name mentions the task name.
    """
    candidates = {
        name: value
        for name, value in vars(clickup_sync).items()
        if not name.startswith("_")
        and isinstance(value, int)
        and not isinstance(value, bool)
        and "NAME" in name.upper()
    }
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    pytest.fail(
        "expected exactly one public integer task-name-limit constant in "
        f"clickup_sync (tasks.md 1.1), found: {sorted(candidates)}"
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Human-attested steps are projected as tasks
# ---------------------------------------------------------------------------


async def test_a_projected_task_is_named_description_then_identifier() -> None:
    """Scenario: A human-attested step gets a task (as revised).

    WHEN the reconciliation pass runs and a `human-attested` step of an
    active launch has no recorded task
    THEN a task named with the step's description followed by its
    identifier is created in the launch's list
    AND the association between the step and the created task is
    recorded.

    Asserted as three separate facts — the description is there, the
    identifier is there, and the description comes *first* — rather than
    as one string equality, because the delta fixes the two parts and
    their order while leaving the joining text to `design.md` (see
    `test_the_composed_name_uses_the_authored_separator`).
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    # SPECIFIED: a task is created, in the launch's list.
    assert len(created) == 1, f"expected exactly one task creation, got {created}"
    assert created[0]["list_id"] == await collaborators.mapping.list_id_for(PRODUCT_ID)

    name = created[0]["name"]
    # SPECIFIED: named with the step's description ...
    assert name.startswith(STEP_DESCRIPTION), (
        f"the task name does not lead with the step's description: {name!r}"
    )
    # SPECIFIED: ... followed by the step's identifier, so the task
    # remains traceable to the step it stands for.
    assert name.endswith(STEP_ID), (
        f"the task name does not end with the step's identifier: {name!r}"
    )

    # SPECIFIED: the association between the step and the created task is
    # recorded — and it is the mapping, not the name, that records it.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.task_id in collaborators.clickup.tasks


async def test_the_composed_name_uses_the_authored_separator() -> None:
    """Scenario: A human-attested step gets a task (composed form).

    DERIVED from `design.md` Decision 4, which fixes the composed name as
    `<description> · <identifier>` and the separator as "the one the name
    already uses". The delta itself states only the two parts and their
    order, so this is the one assertion in the file that a change of
    separator would legitimately supersede — recorded here rather than
    folded into the test above, so that superseding it costs nothing
    else.
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    assert len(created) == 1
    assert created[0]["name"] == f"{STEP_DESCRIPTION}{SEPARATOR}{STEP_ID}"


async def test_a_renamed_task_still_resolves_to_its_step() -> None:
    """Scenario: A renamed task still resolves to its step.

    WHEN a mapped task's name has been edited in ClickUp and the
    reconciliation pass runs
    THEN the task still resolves to the step it is mapped to
    AND no second task is created for that step.

    The seeded name shares nothing with the composed one — it carries
    neither the description nor the identifier — so a pass that matched
    on names would fail to resolve it and would project a duplicate,
    which is exactly what this scenario forbids.
    """
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, "task-existing", name="Hero shot — my own wording"
    )
    collaborators.mapping.seed_task(STEP_ID, "task-existing")

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: no second task is created for that step.
    assert collaborators.clickup.calls_named("create_task") == [], (
        "a renamed task was treated as missing and projected a second time"
    )
    # SPECIFIED: the task still resolves to the step it is mapped to —
    # the association is the recorded mapping and never the name.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.task_id == "task-existing"
    assert collaborators.mapping.replacements == []


async def test_an_edited_task_name_is_never_restored() -> None:
    """Scenario: An edited task name is never restored.

    WHEN a mapped task's name has been edited in ClickUp, the step's
    description has since changed, and the reconciliation pass runs
    THEN the task keeps the name it has in ClickUp
    AND no update is sent for that task's name.

    The changed description is modelled by the playbook now carrying
    wording the existing task's name does not reflect — the state a later
    playbook version produces. Both THENs are asserted: the observable
    end state, and the absence of the write, because a pass that set the
    name back to the same value it already had would satisfy neither the
    spirit nor a later step whose description really did change.
    """
    edited_name = "Hero shot — my own wording"
    playbook = _playbook(
        steps=(_step(name="A newly reworded description for this step"),)
    )
    collaborators = _Collaborators()
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(LIST_ID, "task-existing", name=edited_name)
    collaborators.mapping.seed_task(STEP_ID, "task-existing")

    await _converge(_start(playbook), playbook, collaborators)

    # SPECIFIED: the task keeps the name it has in ClickUp.
    assert collaborators.clickup.tasks["task-existing"].name == edited_name
    # SPECIFIED: no update is sent for that task's name. Other updates —
    # a due date the launch schedule moved — remain permitted, so this
    # asserts on the fields written rather than on the call count.
    name_updates = [
        payload
        for payload in collaborators.clickup.calls_named("update_task")
        if any("name" in field.lower() for field in payload["fields"])
    ]
    assert name_updates == [], (
        f"the authored name was written back over a person's edit: {name_updates}"
    )
    # SPECIFIED corollary: the task is not replaced instead of renamed.
    assert collaborators.clickup.calls_named("create_task") == []


async def test_an_over_long_name_is_shortened_rather_than_failing() -> None:
    """Scenario: An over-long name is shortened rather than failing.

    WHEN a task is projected for a step whose composed name exceeds the
    length the task system accepts
    THEN the task is created with a shortened name that still carries the
    step's identifier.

    The clause that carried the surrendered text into the body is gone:
    `redesign-step-fields` states outright that "Shortening SHALL NOT
    move the surrendered text into the body: the body belongs to the
    description, and overwriting it with a fragment of the name would
    displace what an author wrote." What replaced it is asserted in
    `test_clickup_projection_step_fields.py::
    test_an_over_long_name_is_shortened_and_never_spills_into_the_body`.

    The name is built from the limit the implementation itself
    declares, so this holds whatever `tasks.md` 1.1 confirms that limit
    to be (`design.md` Decision 4: "the rule holds whatever the number
    turns out to be").
    """
    limit = _task_name_limit()
    long_name = "Long row wording. " * ((limit // 18) + 4)
    assert len(long_name) + len(STEP_ID) > limit, (
        "the fixture name is not long enough to exceed the limit"
    )
    playbook = _playbook(steps=(_step(name=long_name),))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    # SPECIFIED: "no step fails to project merely because its name is
    # long" — the task is created, not skipped and not raised on.
    assert len(created) == 1, f"the over-long step did not project: {created}"

    name = created[0]["name"]
    # SPECIFIED: the name is shortened to fit.
    assert len(name) <= limit, (
        f"the composed name was not shortened to the {limit}-character "
        f"limit: {len(name)} characters"
    )
    # SPECIFIED: shortening preserves the step's identifier, "since that
    # is what makes the task traceable".
    assert STEP_ID in name, f"shortening dropped the step's identifier: {name!r}"

    # SPECIFIED: the association is still recorded, as for any projection.
    assert await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID) is not None


async def test_a_name_within_the_limit_is_not_shortened() -> None:
    """Scenario: An over-long name is shortened ... (permitted side).

    The rule is conditioned on the composed name *exceeding* the limit.
    Without this, an implementation that truncated every name would pass
    the test above while destroying the wording this change exists to
    surface.
    """
    limit = _task_name_limit()
    playbook = _playbook(steps=(_step(),))
    collaborators = _Collaborators()
    assert len(STEP_DESCRIPTION) + len(SEPARATOR) + len(STEP_ID) <= limit

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    assert len(created) == 1
    # SPECIFIED: a name that fits is left whole — description and
    # identifier both intact.
    assert created[0]["name"].startswith(STEP_DESCRIPTION)
    assert created[0]["name"].endswith(STEP_ID)


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - *Where* the shortened name is cut, and whether an ellipsis marks it.
#   The delta requires only that the name fit and keep the identifier.
# - Whether the task body is set for a step whose name already fits. The
#   delta states the body requirement for the over-long case only; a body
#   written in every case would violate nothing.
# - Whether a name-bearing `update_task` is ever legitimate for an
#   *unmapped* task. Out of this requirement's scope — the rule is about a
#   task the sync itself projected.
# - The five unchanged scenarios of this requirement, covered in
#   `test_clickup_sync_projection.py`; re-asserting them here would
#   duplicate coverage rather than add it.
# - Due dates. This file's subject is the name; due-date behaviour is
#   `test_clickup_sync_projection.py`'s and is unchanged by this delta.
