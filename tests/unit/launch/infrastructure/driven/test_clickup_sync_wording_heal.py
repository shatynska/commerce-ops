"""Convergence healing a task's name and body toward the step's current
composition — only while each field still carries the system's own words.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-clickup-sync/spec.md`

Covers, from the MODIFIED requirement *Human-attested steps are projected
as tasks*, the scenarios this delta adds or revises:

- *A step authored mid-launch is projected* (new).
- *An unedited task follows the step's current wording* (new).
- *A member's body note survives a wording edit* (new — the two fields
  guarded independently).
- *An unedited legacy task starts healing* (new).
- *An ambiguous legacy task is never rewritten* (new).
- *An edited task name is never restored* — as revised: restated over
  the retained-composition machinery, with the description changed since
  the member's edit.

The requirement's unchanged scenarios (a human-attested step gets a
task, a renamed task resolves, over-long shortening, not-recreated,
never-projected, the deleted-task pair) are already covered by
`test_clickup_sync_projection.py` and `test_clickup_task_naming.py` and
are not restated here.

**Level.** Every outcome is observable from the convergence pass over one
launch against a fake ClickUp and a fake mapping store — the same level
`test_clickup_task_naming.py` records for the same pass.

**The doubles and the call shape are inherited from
`test_clickup_sync_projection.py` / `test_clickup_task_naming.py`**
(INVENTED there: `converge_launch(launch=, playbook=, clickup=,
mapping=, read_product=, folder_id=)` and the ClickUp port's operations),
re-declared because those files are existing tests this pass must not
edit. New INVENTED pieces, recorded in the manifest:

- `_TaskMapping.retained_name` / `_TaskMapping.retained_body` — the two
  retained-composition columns `tasks.md` 2.2 adds to the mapping table.
- `_FakeMapping.record_composition(product_id, step_id, *, name, body)`
  — the mapping-port write the pass uses to update retained values
  (every system write of a field updates its retained value). If the
  implementation updates retained values through a different mapping
  call, correcting the fake is a fixture correction; the postconditions
  on `retained_name`/`retained_body` are not.
- Task-body updates travelling as a `description` field on
  `update_task`, matching the `description` parameter `create_task`
  already carries in the inherited fakes.

**Playbook fixtures hold every gate** (eight automated blocking filler
steps): the gate-holding floor this change promotes to a construction
rule would otherwise reject them once `tasks.md` 1.1 lands. Automated
steps are never projected, so the fillers cannot touch these assertions.

**Expected first-run state.** The healing tests are expected to fail
against the current implementation (names are never rewritten today, and
nothing retains compositions). The never-rewritten tests
(*ambiguous legacy*, *edited name never restored*) may already pass,
because the current freeze-everything behavior is a superset of the
revised guarantee — the discriminating half of this requirement is the
healing tests, which is why both directions are asserted here.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
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
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import LAUNCH_DATE, PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import CreatedTask as _CreatedTask
from tests.support.values import FakeTask as _FakeTask
from tests.support.values import TaskMapping as _TaskMapping

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"
LIST_ID: Final = "901234002"
TASK_ID: Final = "task-mapped"

STEP_ID: Final = "lp.creative.008"
OLD_DESCRIPTION: Final = "Main image designed to be scroll-stopping"
NEW_DESCRIPTION: Final = "Main image designed to stop the scroll dead"

# SPECIFIED (unchanged composition rule): description, ` · `, identifier.
SEPARATOR: Final = " · "


def _composed(description: str, step_id: str = STEP_ID) -> str:
    return f"{description}{SEPARATOR}{step_id}"


OLD_COMPOSITION: Final = _composed(OLD_DESCRIPTION)
NEW_COMPOSITION: Final = _composed(NEW_DESCRIPTION)


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": OLD_DESCRIPTION,
            "discipline": Discipline("creative"),
            **overrides,
        }
    )


def _holding_steps() -> tuple[StepDefinition, ...]:
    """Eight automated blocking fillers satisfying the gate-holding floor;
    automated steps are never projected, so they touch nothing here."""
    return tuple(
        _step(
            identifier=f"hold.{gate}",
            name=f"Blocking work holding the {gate} gate",
            gate=gate,
            blocking=True,
            kind=StepKind.AUTOMATED,
            status=StepStatus.ACTIVE,
            handler="fixture.holding_check",
        )
        for gate in SPECIFIED_GATE_ORDER
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1", gates=_gates(), steps=(*_holding_steps(), *steps)
    )


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (inherited; see the module docstring)
# ---------------------------------------------------------------------------


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return self._product


def _due_date_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    for key, value in fields.items():
        if "due" in key.lower():
            return True, value
    return False, None


class _FakeClickUp:
    """In-memory ClickUp, recording every call — bodies included."""

    def __init__(self) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

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
        attributes = {"name": task_id, **overrides}
        task = _FakeTask(id=task_id, list_id=list_id, **attributes)
        self.tasks[task_id] = task
        return task

    def name_updates_for(self, task_id: str) -> list[str]:
        return [
            payload["fields"]["name"]
            for called, payload in self.calls
            if called == "update_task"
            and payload["task_id"] == task_id
            and "name" in payload["fields"]
        ]

    def body_updates_for(self, task_id: str) -> list[str]:
        return [
            payload["fields"]["description"]
            for called, payload in self.calls
            if called == "update_task"
            and payload["task_id"] == task_id
            and "description" in payload["fields"]
        ]


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
        """INVENTED — see the module docstring. Updates a field's retained
        value; a `None` leaves that field's retained value untouched."""
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
        retained_body: str | None = None,
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
            retained_name=retained_name,
            retained_body=retained_body,
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
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape — the single correction point."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=FOLDER_ID,
    )


def _mapped_collaborators(
    *,
    task_name: str,
    task_body: str | None = None,
    retained_name: str | None = None,
    retained_body: str | None = None,
) -> _Collaborators:
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.clickup.seed_task(
        LIST_ID, TASK_ID, name=task_name, description=task_body
    )
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID
    collaborators.mapping.seed_task(
        STEP_ID, TASK_ID, retained_name=retained_name, retained_body=retained_body
    )
    return collaborators


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Human-attested steps are projected as tasks
# ---------------------------------------------------------------------------


async def test_a_step_authored_mid_launch_is_projected() -> None:
    """Scenario: A step authored mid-launch is projected.

    WHEN a `human-attested` step is added to the playbook after a launch
    started and the next pass runs
    THEN a task is created for it in the launch's list like any other
    step's.
    """
    before = _playbook()
    launch = _start(before)
    collaborators = _Collaborators()
    collaborators.clickup.seed_list(LIST_ID)
    collaborators.mapping.lists[PRODUCT_ID] = LIST_ID

    # The step joins the served playbook only after the launch started.
    after = _playbook(steps=(_step(),))
    await _converge(launch, after, collaborators)

    created = [
        payload
        for called, payload in collaborators.clickup.calls
        if called == "create_task" and payload["name"] == OLD_COMPOSITION
    ]
    assert len(created) == 1
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    # SPECIFIED ("whenever the system writes a name ... it SHALL update
    # that field's retained value"): creation retains what was written.
    assert mapping.retained_name == OLD_COMPOSITION


async def test_an_unedited_task_follows_the_steps_current_wording() -> None:
    """Scenario: An unedited task follows the step's current wording.

    WHEN a step's description has been edited, the mapped task's name in
    ClickUp is still exactly the composition the system last wrote, and
    the pass runs
    THEN the task's name is rewritten to the step's current composition
    AND the retained composition is updated to what was written.
    """
    collaborators = _mapped_collaborators(
        task_name=OLD_COMPOSITION, retained_name=OLD_COMPOSITION
    )
    playbook = _playbook(steps=(_step(name=NEW_DESCRIPTION),))
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: the name is rewritten to the current composition.
    assert collaborators.clickup.tasks[TASK_ID].name == NEW_COMPOSITION
    assert NEW_COMPOSITION in collaborators.clickup.name_updates_for(TASK_ID)
    # SPECIFIED: the retained value follows the write.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.retained_name == NEW_COMPOSITION


async def test_a_members_body_note_survives_a_wording_edit() -> None:
    """Scenario: A member's body note survives a wording edit.

    WHEN a member has edited a mapped task's body, the task's name still
    carries the system's retained composition, the step's description is
    edited, and the pass runs
    THEN the task's name is rewritten to the current composition
    AND the task's body is left exactly as the member wrote it.

    The two fields are guarded independently: the member's body note must
    not freeze the name, and the name rewrite must not touch the body.
    """
    note = "Waiting on the photographer — chased 12 Aug."
    collaborators = _mapped_collaborators(
        task_name=OLD_COMPOSITION,
        task_body=note,
        retained_name=OLD_COMPOSITION,
        retained_body=None,  # the system never wrote a body for this task
    )
    playbook = _playbook(steps=(_step(name=NEW_DESCRIPTION),))
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: the name heals...
    assert collaborators.clickup.tasks[TASK_ID].name == NEW_COMPOSITION
    # ...and the member's body is never rewritten.
    assert collaborators.clickup.body_updates_for(TASK_ID) == []
    assert collaborators.clickup.tasks[TASK_ID].description == note


async def test_an_unedited_legacy_task_starts_healing() -> None:
    """Scenario: An unedited legacy task starts healing.

    WHEN a mapped task predating retained compositions is observed
    carrying exactly the name the system would currently compose
    THEN that name is adopted as the retained composition, and the task
    heals under the rules above thereafter.
    """
    collaborators = _mapped_collaborators(task_name=OLD_COMPOSITION, retained_name=None)
    playbook = _playbook(steps=(_step(),))
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: the matching content is adopted as retained.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.retained_name == OLD_COMPOSITION

    # "…and the task heals thereafter": an authored edit now reaches it.
    edited = _playbook(steps=(_step(name=NEW_DESCRIPTION),))
    await _converge(launch, edited, collaborators)
    assert collaborators.clickup.tasks[TASK_ID].name == NEW_COMPOSITION


async def test_an_ambiguous_legacy_task_is_never_rewritten() -> None:
    """Scenario: An ambiguous legacy task is never rewritten.

    WHEN a mapped task predating retained compositions is observed
    carrying a name that differs from the current composition
    THEN no retained composition is adopted and no pass ever rewrites
    that task's name.
    """
    collaborators = _mapped_collaborators(
        task_name="Someone's own task title", retained_name=None
    )
    playbook = _playbook(steps=(_step(),))
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)
    # A second pass, after an authored edit, must not rewrite either.
    edited = _playbook(steps=(_step(name=NEW_DESCRIPTION),))
    await _converge(launch, edited, collaborators)

    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    # SPECIFIED: nothing adopted — the member wins the ambiguity.
    assert mapping.retained_name is None
    # SPECIFIED: the field is forever unrewritten.
    assert collaborators.clickup.name_updates_for(TASK_ID) == []
    assert collaborators.clickup.tasks[TASK_ID].name == "Someone's own task title"


async def test_an_edited_task_name_is_never_restored() -> None:
    """Scenario: An edited task name is never restored — as revised.

    WHEN a mapped task's name has been edited in ClickUp, the step's
    description has since changed, and the reconciliation pass runs
    THEN the task keeps the name it has in ClickUp
    AND no update is sent for that task's name.
    """
    members_name = "Hero image — Olena owns this"
    collaborators = _mapped_collaborators(
        task_name=members_name, retained_name=OLD_COMPOSITION
    )
    playbook = _playbook(steps=(_step(name=NEW_DESCRIPTION),))
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: no update is sent for that task's name.
    assert collaborators.clickup.name_updates_for(TASK_ID) == []
    assert collaborators.clickup.tasks[TASK_ID].name == members_name
    # DERIVED (retained values move only on system writes): the retained
    # composition is not silently replaced by the member's edit.
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, STEP_ID)
    assert mapping is not None
    assert mapping.retained_name == OLD_COMPOSITION
