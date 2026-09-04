"""A projected task carries its step's gate and discipline as Custom Field
values.

Derived strictly from the delta spec of the OpenSpec change
`record-gate-and-discipline-as-fields`:
`openspec/changes/record-gate-and-discipline-as-fields/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A projected task carries its step's gate
and discipline as Custom Field values*:

- *A newly created task is given both values*
- *A field fault cannot cost a step its task*
- *No value is written to a field found in a gap* -- the write half
- *A task projected before the fields existed gains its values*
- *A task already carrying its values is left alone*
- *A re-gated step's task is corrected*
- *A re-gated step whose new gate has no option keeps its former value* --
  the write half
- *An option differing only in wording is not a match* -- the write half
- *A step that is not projected is given no values*
- *A deployment configuring no field writes none* -- the write half
- *A field identifier configured but empty is a gap* -- the write half
- *A deployment configuring one field records only that one* -- the write
  half
- *A field write that fails costs only that field*

Five of those scenarios state a **reporting** clause as well as a write
clause ("the gap is reported once for the pass", "the missing option is
reported as a configuration gap", "no configuration report is made",
"nothing about the discipline field is reported"). A report is not
observable at this level -- the configuration check runs in the job, once,
before the walk -- so each reporting half is covered in
`tests/unit/launch/infrastructure/driving/test_clickup_field_configuration_check.py`
and each scenario is accounted for by both halves together.

*A stood-down pass writes no value* is not here at all, for the reason
`test_clickup_sync_job_tag_stand_down.py` records for its predecessor: the
stand-down happens in the job, which declines before the pass body is
entered, so `converge_launch` has no stand-down state to be tested in. It
is covered at the job level.

See this change's `test-manifest.md` for the full accounting.

## Level

`converge_launch`, over in-memory fakes -- the harness
`test_clickup_projection_step_fields.py` and
`test_clickup_sync_tags.py` already use in this directory. It is the
smallest unit that can observe what reaches a task: whether the create call
carried a value, whether a write was sent for a task that already agreed
with its step, and whether a failing write took the task's other field with
it.

## The control against an unfalsifiable absence

Six tests below assert that **no** value is written. `ai-toolkit:testing`'s
fourth failure state is exactly what that shape invites, and this change's
`tasks.md` 7.4 names the same trap against the predecessor's experience
("four tests that passed with the feature deleted because an absence
assertion is unfalsifiable when nothing writes"). Every such test therefore
carries a **control step in the same playbook and the same launch** whose
task must be observed carrying both values before the absence is asserted.
`_assert_control_is_valued` is that assertion, and it is not optional in
any of them.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts, so treated as SPECIFIED:

- That the create call carries no Custom Field value and that the values
  are set after the task exists (`tasks.md` 4.4/4.4a; the requirement says
  so in as many words).
- That a differing value is **corrected** rather than treated as a member's
  edit, and that a value the step does not resolve to is left standing
  rather than approximated or cleared.
- That a per-task write failure warns naming the step, the field and the
  task, still attempts the task's other field, and does not fail the run
  (`tasks.md` 4.7).
- That the resolution is threaded into `converge_launch` **as data**, read
  once per pass rather than per launch (`tasks.md` 4.2).
- The exact-match rule on the identifier string -- "no case-folding, no
  trimming, no fuzzy match" (`tasks.md` 3.1).

INVENTED, and each with one correction point:

- **`_Resolution`** -- the shape of the data `tasks.md` 4.2 threads in. No
  artifact fixes it. It is written as a hybrid: attributes
  (`gate_field_id`, `gate_options`, `discipline_field_id`,
  `discipline_options`) *and* a `Mapping` from field identifier to that
  field's `{name: option identifier}`, so an implementation reading it
  either way finds what it needs. A withheld field is expressed by its
  identifier being `None` -- the encoding of "write nothing for this
  field", which is what the pass needs to know and all it needs to know.
  Correction point: `_Resolution` and `_resolution()`.
- **How the resolution reaches `converge_launch`** -- `_converge` inspects
  the signature and passes it under whichever of a candidate set of
  parameter names is declared, failing with a directive when none is.
  Correction point: `_RESOLUTION_PARAMETERS`.
- **`clickup.set_task_field(task_id, field_id, value)`** on the port the
  pass drives -- named by `tasks.md` 2.5 for the client; that the pass
  calls it under that name, and positionally or by keyword, is not fixed.
  `_FakeClickUp.set_task_field` accepts either.
- **`custom_fields` on what `list_tasks` reports and on the create
  payload** -- read through `_custom_fields_in` / `_field_values`, so no
  wire container is pinned, exactly as `test_clickup_sync_tags.py` reads a
  tag claim.

## Expected first-run state

`converge_launch` declares no resolution parameter and the ClickUp port has
no `set_task_field`, so every test here is expected to fail on an **absent
target** -- `_converge` failing on the parameter probe. Per
`ai-toolkit:testing` that establishes only absence, and nothing about
whether the assertions below are well-formed.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` at the worktree root --
1130 passed, 0 failed.
"""

from __future__ import annotations

import datetime
import inspect
import logging
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeMembers as _FakeMembers
from tests.support.fixtures import (
    ALICE,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import CreatedTask as _CreatedTask
from tests.support.values import FakeTask as _FakeTask
from tests.support.values import Member as _Member
from tests.support.values import TaskMapping as _TaskMapping

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"
SEPARATOR: Final = " · "

GATE_FIELD_ID: Final = "4bd1f0f9-6f2a-4f0e-9d5d-0f4a1c6b2e11"
DISCIPLINE_FIELD_ID: Final = "5ce2a1f0-7a3b-4b1f-8e6e-1a5b2d7c3f22"

#: The step under test. Its gate (`listable`) and its discipline
#: (`listing`) are deliberately *different* words, so an implementation
#: that swapped the two fields fails rather than passes.
STEP_ID: Final = "listing.title-conforms"
STEP_NAME: Final = "Conform the title to the style guide"
STEP_DESCRIPTION: Final = "Match the style guide's title rules exactly."
STEP_GATE: Final = "listable"
STEP_DISCIPLINE: Final = Discipline.LISTING

#: The control step, in the same launch, whose task must be observed
#: carrying both values before any absence is asserted.
CONTROL_STEP_ID: Final = "finance.unit-economics"
CONTROL_STEP_NAME: Final = "Check the unit economics still clear"
CONTROL_GATE: Final = "commit"
CONTROL_DISCIPLINE: Final = Discipline.FINANCE

#: Option identifiers are deliberately unlike the option *names* they carry,
#: so a pass writing the name where the identifier is required fails.
GATE_OPTION_IDS: Final = {
    identifier: f"gopt-{index:02d}-{uuid.uuid5(uuid.NAMESPACE_OID, identifier).hex[:8]}"
    for index, identifier in enumerate(SPECIFIED_GATE_ORDER)
}
DISCIPLINE_OPTION_IDS: Final = {
    member.value: f"dopt-{index:02d}-"
    f"{uuid.uuid5(uuid.NAMESPACE_OID, member.value).hex[:8]}"
    for index, member in enumerate(Discipline)
}

ALICE_CLICKUP: Final = "clickup-alice"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_clickup_sync_tags.py`
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": STEP_NAME,
            "description": STEP_DESCRIPTION,
            "gate": STEP_GATE,
            "discipline": STEP_DISCIPLINE,
            "assignees": (ALICE,),
            **overrides,
        }
    )


def _control_step(**overrides: Any) -> StepDefinition:
    return _step(
        identifier=CONTROL_STEP_ID,
        name=CONTROL_STEP_NAME,
        description=None,
        gate=CONTROL_GATE,
        discipline=CONTROL_DISCIPLINE,
        **overrides,
    )


def _hold(gate: str) -> StepDefinition:
    """An `active` `automated` blocking filler, so no filler is ever
    projected and every assertion below is about this file's own steps."""
    return _build_hold(
        gate,
        discipline=STEP_DISCIPLINE,
        handler=f"hold.{gate.replace('-', '_')}",
        kind=StepKind.AUTOMATED,
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return _build_playbook(*steps, filler=_hold, held_must_be_active=True)


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _composed_name(step_id: str, name: str) -> str:
    return f"{name}{SEPARATOR}{step_id}"


# ---------------------------------------------------------------------------
# The resolution -- INVENTED, single correction point (see the docstring)
# ---------------------------------------------------------------------------


class _Resolution(Mapping):  # type: ignore[type-arg]
    """What `tasks.md` 4.2 threads into `converge_launch`.

    Carries, per field, the identifier the deployment configured and the
    map from the playbook's own vocabulary to the option identifier that
    names it. A field whose identifier is `None` is one the pass must write
    nothing for -- unconfigured, configured-but-empty, or found in a gap of
    the kinds that withhold writes. The pass needs no more than that, and
    the requirement asks it to distinguish no more than that: every other
    consequence of those states is the configuration check's to report.
    """

    def __init__(
        self,
        *,
        gate_field_id: str | None,
        gate_options: Mapping[str, str],
        discipline_field_id: str | None,
        discipline_options: Mapping[str, str],
    ) -> None:
        self.gate_field_id = gate_field_id
        self.gate_options = dict(gate_options)
        self.discipline_field_id = discipline_field_id
        self.discipline_options = dict(discipline_options)

    # -- attribute-style aliases an implementation might reach for --------

    @property
    def fields(self) -> dict[str, dict[str, str]]:
        return dict(self._as_mapping())

    def option_for(self, field_id: str, name: str) -> str | None:
        return self._as_mapping().get(field_id, {}).get(name)

    # -- Mapping over field identifier -> {vocabulary name: option id} ----

    def _as_mapping(self) -> dict[str, dict[str, str]]:
        mapping: dict[str, dict[str, str]] = {}
        if self.gate_field_id is not None:
            mapping[self.gate_field_id] = dict(self.gate_options)
        if self.discipline_field_id is not None:
            mapping[self.discipline_field_id] = dict(self.discipline_options)
        return mapping

    def __getitem__(self, key: str) -> dict[str, str]:
        return self._as_mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._as_mapping())

    def __len__(self) -> int:
        return len(self._as_mapping())

    def __repr__(self) -> str:
        return (
            f"_Resolution(gate_field_id={self.gate_field_id!r}, "
            f"discipline_field_id={self.discipline_field_id!r}, "
            f"gate_options={self.gate_options!r}, "
            f"discipline_options={self.discipline_options!r})"
        )


def _resolution(
    *,
    gate_field_id: str | None = GATE_FIELD_ID,
    discipline_field_id: str | None = DISCIPLINE_FIELD_ID,
    gate_option_names: Sequence[str] = SPECIFIED_GATE_ORDER,
    discipline_option_names: Sequence[str] | None = None,
) -> _Resolution:
    """A resolution over the playbook's own vocabularies.

    `gate_option_names` is the set of gate identifiers the gate field
    declares an exactly-matching option for; a gate left out of it is one
    the step resolves to nothing.
    """
    disciplines = (
        [member.value for member in Discipline]
        if discipline_option_names is None
        else list(discipline_option_names)
    )
    return _Resolution(
        gate_field_id=gate_field_id,
        gate_options={name: GATE_OPTION_IDS[name] for name in gate_option_names},
        discipline_field_id=discipline_field_id,
        discipline_options={name: DISCIPLINE_OPTION_IDS[name] for name in disciplines},
    )


_RESOLUTION_PARAMETERS: Final = (
    # The implemented name. The parameter carries the whole configuration --
    # the resolution, the findings and which fields may be written to -- so
    # "resolution" alone would understate it. Adding it here is the fixture
    # correction this probe's own directive invites; no assertion changes.
    "configuration",
    "custom_fields",
    "custom_field_resolution",
    "field_resolution",
    "fields",
    "resolution",
    "field_values",
)


def _resolution_parameter() -> str:
    declared = inspect.signature(converge_launch).parameters
    for name in _RESOLUTION_PARAMETERS:
        if name in declared:
            return name
    pytest.fail(
        "`converge_launch` declares none of "
        f"{list(_RESOLUTION_PARAMETERS)}, so the Custom Field resolution "
        "`tasks.md` 4.2 threads into it cannot be supplied. Until that "
        "parameter lands this is an absent target; correcting the name here "
        "is a fixture correction, not a change to what is asserted. "
        f"Declared parameters: {list(declared)}"
    )


# ---------------------------------------------------------------------------
# Test doubles -- transcribed from `test_clickup_sync_tags.py`
# ---------------------------------------------------------------------------


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return self._product


def _members() -> _FakeMembers:
    return _FakeMembers((_Member(ALICE, "Alice Admin", clickup_user_id=ALICE_CLICKUP),))


def _custom_fields_in(payload: Mapping[str, Any]) -> tuple[bool, Any]:
    """Any Custom Field claim on a create payload. Returns (present, value).

    Matched on the key rather than pinned to one spelling: the
    create-carries-nothing rule turns on telling "no claim" from "an empty
    claim", and a missed spelling would silently read as the former.
    """
    for key, value in payload.items():
        if key.lower().replace("_", "") in {"customfields", "fields", "fieldvalues"}:
            return True, value
    return False, None


def _field_values(value: Any) -> dict[str, Any]:
    """The `{field id: value}` inside a claim, whatever container it came
    in."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    values: dict[str, Any] = {}
    for item in value:
        if isinstance(item, Mapping):
            identifier = (
                item.get("id") or item.get("field_id") or item.get("identifier")
            )
            if identifier is not None:
                values[str(identifier)] = item.get("value")
    return values


class _FieldWriteRefused(RuntimeError):
    """What the ClickUp port raises when a Custom Field write fails.

    `clickup-task-client` requires the client to surface the failure rather
    than swallow it; no artifact names a type, so this file raises its own
    and the pass is only ever required to *survive* it.
    """


class _FakeClickUp:
    """In-memory ClickUp, offering exactly the operations the pass may use.

    Anything else the pass reaches for is recorded in `probed` and raises
    `AttributeError` in the ordinary way -- so a field *creation*, an option
    write, or a folder read from inside the per-launch pass leaves a named
    trace. The requirement forbids all three: the system "SHALL NOT create
    either field, change its type, or add, remove, reorder or rename any of
    its options", and the folder read is made once per pass in the job.
    """

    def __init__(self) -> None:
        self._probed: list[str] = []
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self.refuse_field_ids: tuple[str, ...] = ()
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
        has_fields, claimed = _custom_fields_in(payload)
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            description=description,
            body=description,
            due_date=payload.get("due_date"),
            assignees=tuple(str(item) for item in payload.get("assignees", ()) or ()),
            custom_fields=_field_values(claimed) if has_fields else {},
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        if "name" in fields:
            task.name = fields["name"]
        if "description" in fields:
            task.description = fields["description"]
            task.body = fields["description"]
        if "assignees" in fields:
            task.assignees = tuple(str(item) for item in fields["assignees"] or ())
        if "due_date" in fields:
            # Fixture correction: the pass sets a due date through this same
            # update, encoded as ClickUp's epoch milliseconds (or null to
            # clear one). Without applying it the fake could not express a
            # task carrying a due date at all, so an assertion that one is
            # present could never pass however correct the pass was.
            raw = fields["due_date"]
            task.due_date = (
                None
                if raw is None
                else datetime.datetime.fromtimestamp(
                    int(raw) / 1000, tz=datetime.UTC
                ).date()
            )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def set_task_field(self, task_id: str, field_id: str, value: Any) -> None:
        self.calls.append(
            (
                "set_task_field",
                {"task_id": task_id, "field_id": field_id, "value": value},
            )
        )
        if field_id in self.refuse_field_ids:
            raise _FieldWriteRefused(
                f"ClickUp refused a write to the field {field_id!r}"
            )
        self.tasks[task_id].custom_fields[field_id] = value

    # -- reads -------------------------------------------------------------

    async def read_list_state(self, list_id: str) -> Any:
        """Fixture correction: an operation the pass legitimately uses.

        `heal-a-launchs-deleted-list` has the pass verify a recorded list
        still exists before using it. That is none of this change's business
        and appears in no delta here, which is why it was absent -- but
        `converge_launch` calls it on every launch that already has a list,
        so without it no scenario reaching a mapped task can run at all.
        Reports the list as live; a deleted one is that change's own subject.
        """
        self.calls.append(("read_list_state", {"list_id": list_id}))
        return SimpleNamespace(deleted=False)

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

    def field_writes(self) -> list[tuple[str, str, Any]]:
        return [
            (payload["task_id"], payload["field_id"], payload["value"])
            for payload in self.calls_named("set_task_field")
        ]


class _FakeMapping:
    """In-memory stand-in for the two mapping tables.

    Deliberately carries no per-task Custom Field column: the requirement
    keeps no retained value for these two fields, because "a Custom Field is
    single-valued and wholly determined by the step, so a divergence is
    drift" -- there is no legitimate member-edit to distinguish and so
    nothing to retain. An implementation reaching for one is recorded in
    `probed`.
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
        retained_body: str | None = None,
        retained_assignees: tuple[str, ...] | None = None,
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            retained_name=retained_name,
            retained_body=retained_body,
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
    members: _FakeMembers = field(default_factory=_members)


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
    *,
    resolution: _Resolution | None = None,
    folder_id: str | None = FOLDER_ID,
) -> None:
    """INVENTED call shape -- see the module docstring. Single correction
    point for both the call and the resolution parameter's name."""
    extra: dict[str, Any] = {}
    if resolution is not None:
        extra[_resolution_parameter()] = resolution
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        members=collaborators.members,
        folder_id=folder_id,
        **extra,
    )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _task_for(collaborators: _Collaborators, step_id: str) -> _FakeTask:
    mapping = collaborators.mapping.tasks.get((PRODUCT_ID, step_id))
    assert mapping is not None, (
        f"no task was mapped for {step_id!r}; the projection did not run as "
        "this test needs it to"
    )
    task = collaborators.clickup.tasks.get(mapping.task_id)
    assert task is not None, f"the mapping for {step_id!r} names no ClickUp task"
    return task


def _assert_control_is_valued(collaborators: _Collaborators) -> None:
    """The control this file's absence assertions are worthless without.

    `tasks.md` 7.4: a control step whose task must be observed carrying both
    values *before* any absence is asserted, because an absence assertion is
    unfalsifiable when nothing writes at all.
    """
    task = _task_for(collaborators, CONTROL_STEP_ID)
    assert task.custom_fields.get(GATE_FIELD_ID) == GATE_OPTION_IDS[CONTROL_GATE], (
        "the control step's task carries no gate value, so nothing in this "
        "test distinguishes 'the pass withheld a value' from 'the pass "
        f"writes no values at all': {task.custom_fields!r}"
    )
    assert (
        task.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[CONTROL_DISCIPLINE.value]
    ), (
        "the control step's task carries no discipline value; see above: "
        f"{task.custom_fields!r}"
    )


def _writes_for(collaborators: _Collaborators, task_id: str) -> list[tuple[str, Any]]:
    return [
        (field_id, value)
        for written_task, field_id, value in collaborators.clickup.field_writes()
        if written_task == task_id
    ]


@pytest.fixture()
def captured_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


# ---------------------------------------------------------------------------
# Requirement: A projected task carries its step's gate and discipline as
# Custom Field values
# ---------------------------------------------------------------------------


async def test_a_newly_created_task_is_given_both_values() -> None:
    """Scenario: A newly created task is given both values.

    WHEN a task is projected for an `active` `human` step and both fields
    are configured and resolve
    THEN the create call carries no Custom Field value
    AND the task is then given the option matching the step's gate on the
    gate field, and the option matching its discipline on the discipline
    field.
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    # SPECIFIED: "the create call carries no Custom Field value". Asserted
    # over *every* create, and on the absence of the claim rather than on an
    # empty one -- the guarantee is that nothing about these two fields
    # reaches the call that brings a step's work into being.
    for payload in collaborators.clickup.calls_named("create_task"):
        has_fields, claimed = _custom_fields_in(payload)
        assert not has_fields, (
            "the create call carried a Custom Field claim "
            f"({claimed!r}); the requirement forbids it, because a value "
            "the task system refuses would then cost the step its whole "
            "task"
        )

    task = _task_for(collaborators, STEP_ID)
    # SPECIFIED: the option matching the step's gate, on the gate field.
    assert task.custom_fields.get(GATE_FIELD_ID) == GATE_OPTION_IDS[STEP_GATE]
    # SPECIFIED: the option matching its discipline, on the discipline
    # field. The two are different words here, so a swapped pair fails.
    assert (
        task.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value]
    )

    # SPECIFIED: the values are set *after* the task is created -- the write
    # names the task, which cannot happen before it exists.
    writes = _writes_for(collaborators, task.id)
    assert {field_id for field_id, _ in writes} == {
        GATE_FIELD_ID,
        DISCIPLINE_FIELD_ID,
    }, f"expected one write per field after the create, got {writes!r}"

    # SPECIFIED: the system creates no field and touches no option.
    forbidden = [
        name
        for name in collaborators.clickup.probed
        if any(
            word in name.lower()
            for word in ("create_field", "add_option", "update_field", "folder_field")
        )
    ]
    assert not forbidden, (
        "the pass reached for a field-configuration operation "
        f"({forbidden}); the requirement forbids creating a field, changing "
        "its type, or adding, removing, reordering or renaming an option, "
        "and the folder read is made once per pass by the job"
    )


async def test_a_field_fault_cannot_cost_a_step_its_task() -> None:
    """Scenario: A field fault cannot cost a step its task.

    WHEN every write of a Custom Field value fails for a step being
    projected for the first time
    THEN the task exists and carries its name, body, assignees and due date
    AND nothing about the failure causes the run to be recorded as failed.

    "Recorded as failed" is read at this level as *`converge_launch`
    raises* -- a raising pass is what
    `One launch's failure does not stop the other launches being converged`
    contains and then fails the run for. The run's own outcome has no signal
    below the job, and the job-level half is covered by that requirement's
    existing tests.
    """
    playbook = _playbook((_step(),))
    collaborators = _Collaborators()
    collaborators.clickup.refuse_field_ids = (GATE_FIELD_ID, DISCIPLINE_FIELD_ID)

    # SPECIFIED: nothing about the failure causes the run to be failed.
    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    task = _task_for(collaborators, STEP_ID)
    # SPECIFIED: the task exists and carries its name, body, assignees and
    # due date.
    assert task.name == _composed_name(STEP_ID, STEP_NAME)
    assert task.body == STEP_DESCRIPTION
    assert task.assignees == (ALICE_CLICKUP,)
    assert task.due_date is not None, (
        "the task was created with no due date; a Custom Field fault must "
        "cost the field values and nothing else"
    )


async def test_no_value_is_written_for_a_field_withheld_by_a_gap() -> None:
    """Scenario: No value is written to a field found in a gap -- the write
    half.

    WHEN a pass runs and the gate field is present and declares an option
    for every gate but is not of the type whose values the system writes
    THEN no gate value is written on any task.

    A field found in a gap of the kinds that withhold writes reaches the
    pass as a field it is to write nothing for; deciding *which* gap kinds
    withhold is the configuration check's job, and the second clause of this
    scenario ("the gap is reported once for the pass rather than once per
    task") is asserted there. What is asserted here is the guarantee the
    requirement states over the pass: for such a field, "no value is written
    on any task" -- not one write per task, and not an approximation.
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        # The wrong-typed gate field: it resolves perfectly well, and the
        # check has established the system did not intend to write to it.
        resolution=_resolution(gate_field_id=None),
    )

    # SPECIFIED: no gate value on any task -- asserted over every task in
    # the launch, not only the step under test.
    gate_writes = [
        write
        for write in collaborators.clickup.field_writes()
        if write[1] == GATE_FIELD_ID
    ]
    assert gate_writes == [], (
        "a gate value was written to a field found in a gap of the kinds "
        f"that withhold writes: {gate_writes!r}"
    )
    for task in collaborators.clickup.tasks.values():
        assert GATE_FIELD_ID not in task.custom_fields

    # The control: the discipline field, which is in no gap, is still
    # written -- so the absence above is a withholding and not a pass that
    # writes nothing.
    control = _task_for(collaborators, CONTROL_STEP_ID)
    assert (
        control.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[CONTROL_DISCIPLINE.value]
    ), "no value was written for either field, so this test establishes nothing"


async def test_a_task_projected_before_the_fields_existed_gains_its_values() -> None:
    """Scenario: A task projected before the fields existed gains its
    values.

    WHEN a pass runs over a mapped task that carries neither field's value
    and whose step resolves both
    THEN the task is given both values.

    This is the backfill the requirement insists on -- "so that tasks
    projected before this requirement existed gain their values rather than
    the behaviour reaching only launches started afterwards".
    """
    playbook = _playbook((_step(),))
    collaborators = _Collaborators()
    list_id = collaborators.clickup.seed_list("list-existing")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(
        list_id,
        "task-legacy",
        name=_composed_name(STEP_ID, STEP_NAME),
        description=STEP_DESCRIPTION,
        body=STEP_DESCRIPTION,
        assignees=(ALICE_CLICKUP,),
        custom_fields={},
    )
    collaborators.mapping.seed_task(
        STEP_ID,
        "task-legacy",
        retained_name=_composed_name(STEP_ID, STEP_NAME),
        retained_body=STEP_DESCRIPTION,
        retained_assignees=(ALICE,),
    )

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    task = collaborators.clickup.tasks["task-legacy"]
    # SPECIFIED: the task is given both values.
    assert task.custom_fields.get(GATE_FIELD_ID) == GATE_OPTION_IDS[STEP_GATE]
    assert (
        task.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value]
    )
    # SPECIFIED, by the create-path rule: no second task was created for a
    # step that already had one.
    assert collaborators.clickup.calls_named("create_task") == []


async def test_a_task_already_carrying_its_values_is_left_alone() -> None:
    """Scenario: A task already carrying its values is left alone.

    WHEN a pass runs over a mapped task already carrying the values its step
    resolves to
    THEN no Custom Field write is sent for that task
    AND a task in the same launch whose values are absent is still given
    them.

    This is the no-op guarantee the whole read/write representation
    argument rests on: two representations of the same value would report
    every task as differing on every pass, producing a write that succeeds
    and changes nothing. `tasks.md` 7.10a takes the end-to-end half of it
    against the real workspace, which a mocked test cannot establish.
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()
    list_id = collaborators.clickup.seed_list("list-existing")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(
        list_id,
        "task-valued",
        name=_composed_name(STEP_ID, STEP_NAME),
        description=STEP_DESCRIPTION,
        body=STEP_DESCRIPTION,
        assignees=(ALICE_CLICKUP,),
        custom_fields={
            GATE_FIELD_ID: GATE_OPTION_IDS[STEP_GATE],
            DISCIPLINE_FIELD_ID: DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value],
        },
    )
    collaborators.mapping.seed_task(
        STEP_ID,
        "task-valued",
        retained_name=_composed_name(STEP_ID, STEP_NAME),
        retained_body=STEP_DESCRIPTION,
        retained_assignees=(ALICE,),
    )

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    # AND-clause first, because it is this test's control: without it, a
    # pass that writes nothing at all would pass the assertion below.
    _assert_control_is_valued(collaborators)

    # SPECIFIED: no Custom Field write is sent for that task.
    assert _writes_for(collaborators, "task-valued") == [], (
        "a write was sent for a task already carrying the values its step "
        "resolves to; that is the standing write storm the representation "
        "rule exists to prevent"
    )


async def test_a_re_gated_steps_task_is_corrected() -> None:
    """Scenario: A re-gated step's task is corrected.

    WHEN a step's gate is changed by authoring and a pass runs over its
    mapped task, which still carries the option for the former gate
    THEN the task's gate field is set to the option matching the step's
    current gate.

    This is the defect the tag representation could not retire: "a step
    moved to a different gate keeps its old gate tag". Deliberately unlike
    the name, the body and the assignees -- a divergence here is drift, not
    a member's own meaning.
    """
    former_gate = "commit"
    playbook = _playbook((_step(gate="live"),))
    collaborators = _Collaborators()
    list_id = collaborators.clickup.seed_list("list-existing")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(
        list_id,
        "task-regated",
        name=_composed_name(STEP_ID, STEP_NAME),
        description=STEP_DESCRIPTION,
        body=STEP_DESCRIPTION,
        assignees=(ALICE_CLICKUP,),
        custom_fields={
            GATE_FIELD_ID: GATE_OPTION_IDS[former_gate],
            DISCIPLINE_FIELD_ID: DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value],
        },
    )
    collaborators.mapping.seed_task(
        STEP_ID,
        "task-regated",
        retained_name=_composed_name(STEP_ID, STEP_NAME),
        retained_body=STEP_DESCRIPTION,
        retained_assignees=(ALICE,),
    )

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    task = collaborators.clickup.tasks["task-regated"]
    # SPECIFIED: set to the option matching the step's *current* gate.
    assert task.custom_fields[GATE_FIELD_ID] == GATE_OPTION_IDS["live"], (
        "the task kept its former gate value; a Custom Field is wholly "
        "determined by the step, so a divergence is drift and is corrected"
    )
    # DERIVED: the discipline, which did not change, is not rewritten -- the
    # no-op guarantee holds per field, not per task.
    assert [write for write in _writes_for(collaborators, "task-regated")] == [
        (GATE_FIELD_ID, GATE_OPTION_IDS["live"])
    ]


async def test_a_re_gated_step_whose_new_gate_has_no_option_keeps_its_value() -> None:
    """Scenario: A re-gated step whose new gate has no option keeps its
    former value -- the write half.

    WHEN a step's gate is changed to one the gate field declares no option
    for, and a pass runs over its mapped task
    THEN the task's gate field is left carrying what it has.

    The second clause -- "the missing option is reported as a configuration
    gap" -- is asserted at the job level, where the report is made.

    Neither an approximation nor a clearing: "writing an approximation would
    state something the playbook does not say, and clearing the value would
    state nothing where something true was standing."
    """
    former_gate = "commit"
    playbook = _playbook((_step(gate="stock-ready"), _control_step()))
    collaborators = _Collaborators()
    list_id = collaborators.clickup.seed_list("list-existing")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(
        list_id,
        "task-regated",
        name=_composed_name(STEP_ID, STEP_NAME),
        description=STEP_DESCRIPTION,
        body=STEP_DESCRIPTION,
        assignees=(ALICE_CLICKUP,),
        custom_fields={
            GATE_FIELD_ID: GATE_OPTION_IDS[former_gate],
            DISCIPLINE_FIELD_ID: DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value],
        },
    )
    collaborators.mapping.seed_task(
        STEP_ID,
        "task-regated",
        retained_name=_composed_name(STEP_ID, STEP_NAME),
        retained_body=STEP_DESCRIPTION,
        retained_assignees=(ALICE,),
    )

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        # Every gate but `stock-ready` declares an option.
        resolution=_resolution(
            gate_option_names=[
                gate for gate in SPECIFIED_GATE_ORDER if gate != "stock-ready"
            ]
        ),
    )

    # Control first: the pass is writing gate values on this run.
    _assert_control_is_valued(collaborators)

    task = collaborators.clickup.tasks["task-regated"]
    # SPECIFIED: left carrying what it has -- neither approximated nor
    # cleared.
    assert task.custom_fields[GATE_FIELD_ID] == GATE_OPTION_IDS[former_gate], (
        "the task's gate value was changed although its new gate resolves "
        f"to no option: {task.custom_fields!r}"
    )
    assert _writes_for(collaborators, "task-regated") == []


async def test_an_option_differing_only_in_wording_is_not_a_match() -> None:
    """Scenario: An option differing only in wording is not a match -- the
    write half.

    WHEN the gate field declares an option whose name differs from a gate
    identifier by case or spacing
    THEN no task is given that option for that gate.

    The second clause -- "the gate is reported as having no matching
    option" -- is asserted at the job level, where the check composes the
    gap.

    "The match SHALL be exact on the identifier string ... a hand-typed
    option differing from one by case, spacing or wording is a configuration
    gap rather than a match." Modelled here by a resolution in which the
    step's gate resolves to nothing, because a near-miss is *not* a match:
    an implementation that case-folded would have resolved it, and would
    then write a value this test asserts is never written.
    """
    playbook = _playbook((_step(gate="stock-ready"), _control_step()))
    collaborators = _Collaborators()

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        resolution=_resolution(
            gate_option_names=[
                gate for gate in SPECIFIED_GATE_ORDER if gate != "stock-ready"
            ]
        ),
    )

    # Control first.
    _assert_control_is_valued(collaborators)

    task = _task_for(collaborators, STEP_ID)
    # SPECIFIED: no task is given that option for that gate.
    assert GATE_FIELD_ID not in task.custom_fields, (
        "a near-miss option was written for a gate the field does not name "
        f"exactly: {task.custom_fields!r}"
    )
    # SPECIFIED: the field the step *does* resolve is unaffected -- a
    # failure to resolve one field never withholds the other.
    assert (
        task.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value]
    )


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("not active", {"status": StepStatus.DRAFT}),
        (
            "not human",
            {"kind": StepKind.AUTOMATED, "handler": "listing.title_conforms"},
        ),
        ("carrying the prohibited-tactic hazard", {"hazard": Hazard.PROHIBITED_TACTIC}),
    ],
)
async def test_a_step_that_is_not_projected_is_given_no_values(
    label: str, overrides: dict[str, Any]
) -> None:
    """Scenario: A step that is not projected is given no values.

    WHEN a pass runs and a step is not `active`, or is not `human`, or
    carries the `prohibited-tactic` hazard, or is not defined by the served
    playbook
    THEN no Custom Field value is written for it
    AND a projected step in the same launch is still given both of its
    values.

    All three departure fields, not a subset (`tasks.md` 4.8): the
    requirement references *A step that is not active leaves the loop*
    rather than paraphrasing it, precisely because "a rule naming fewer
    would leave the rest undefined". The fourth ground -- a step the served
    playbook does not define -- is covered by
    `test_a_step_the_playbook_does_not_define_is_given_no_values` below,
    since it cannot be expressed as an override on a step the playbook
    holds.
    """
    attributes: dict[str, Any] = {**overrides}
    if attributes.get("kind") is StepKind.AUTOMATED:
        attributes["assignees"] = ()
    playbook = _playbook((_step(**attributes), _control_step()))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    # AND-clause first: it is the control, and without it the assertion
    # below holds against a pass that writes nothing at all.
    _assert_control_is_valued(collaborators)

    # SPECIFIED: no Custom Field value is written for it.
    mapping = collaborators.mapping.tasks.get((PRODUCT_ID, STEP_ID))
    assert mapping is None, (
        f"a step that is {label} was projected at all, so this test cannot "
        "say anything about its Custom Field values"
    )
    written_names = {
        payload["name"] for payload in collaborators.clickup.calls_named("create_task")
    }
    assert _composed_name(STEP_ID, STEP_NAME) not in written_names


async def test_a_step_the_playbook_does_not_define_is_given_no_values() -> None:
    """Scenario: A step that is not projected is given no values -- the
    fourth ground.

    "A step the served playbook does not define at all is likewise never
    given a value, on the projection requirement's own ground." Modelled as
    a mapping that survives a step's removal from the served playbook, which
    is how that state arises.
    """
    playbook = _playbook((_control_step(),))
    collaborators = _Collaborators()
    list_id = collaborators.clickup.seed_list("list-existing")
    await collaborators.mapping.record_list(PRODUCT_ID, list_id)
    collaborators.clickup.seed_task(
        list_id,
        "task-orphan",
        name=_composed_name(STEP_ID, STEP_NAME),
        custom_fields={},
    )
    collaborators.mapping.seed_task(
        STEP_ID,
        "task-orphan",
        retained_name=_composed_name(STEP_ID, STEP_NAME),
    )

    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    _assert_control_is_valued(collaborators)

    # SPECIFIED: no value is written for a step the served playbook does not
    # define.
    assert _writes_for(collaborators, "task-orphan") == []
    assert collaborators.clickup.tasks["task-orphan"].custom_fields == {}


async def test_a_deployment_configuring_no_field_writes_none() -> None:
    """Scenario: A deployment configuring no field writes none -- the write
    half.

    WHEN a pass runs in a deployment that configures neither field
    identifier
    THEN every task is projected with its name, body, assignees and due date
    as usual
    AND no Custom Field value is written.

    The remaining clause -- "and no configuration report is made" -- is
    asserted at the job level.

    The control here is not a control *step* but the projection itself: the
    tasks are asserted to be fully projected, so "no value was written" is
    read against a pass that plainly ran.
    """
    playbook = _playbook((_step(),))
    collaborators = _Collaborators()

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        resolution=_resolution(gate_field_id=None, discipline_field_id=None),
    )

    task = _task_for(collaborators, STEP_ID)
    # SPECIFIED: every task is projected as usual.
    assert task.name == _composed_name(STEP_ID, STEP_NAME)
    assert task.body == STEP_DESCRIPTION
    assert task.assignees == (ALICE_CLICKUP,)
    assert task.due_date is not None

    # SPECIFIED: no Custom Field value is written. A deployment that names
    # no field has declined the capability.
    assert collaborators.clickup.field_writes() == []
    assert task.custom_fields == {}


async def test_a_field_identifier_configured_but_empty_writes_no_value() -> None:
    """Scenario: A field identifier configured but empty is a gap -- the
    write half.

    WHEN a pass runs in a deployment where a field's identifier is present
    but empty
    THEN no value is written for it.

    The first clause -- "that field is reported as configured with no value,
    rather than treated as declined" -- is asserted at the job level, which
    is the only place the distinction between *absent* and *empty* is
    visible: both reach the pass as a field it writes nothing for, and the
    difference is entirely in what is reported.
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        resolution=_resolution(gate_field_id=None),
    )

    # Control: the discipline field is written on this run.
    control = _task_for(collaborators, CONTROL_STEP_ID)
    assert (
        control.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[CONTROL_DISCIPLINE.value]
    )

    # SPECIFIED: no value is written for the empty-identifier field.
    assert [
        write
        for write in collaborators.clickup.field_writes()
        if write[1] == GATE_FIELD_ID
    ] == []


async def test_a_deployment_configuring_one_field_records_only_that_one() -> None:
    """Scenario: A deployment configuring one field records only that one.

    WHEN a pass runs in a deployment that configures the gate field's
    identifier and not the discipline field's
    THEN every task is given its gate value
    AND no discipline value is written.

    The remaining clause -- "and nothing about the discipline field is
    reported" -- is asserted at the job level. "Silence therefore means 'not
    asked for' and a report means 'asked for and broken', for each field
    separately."
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()

    await _converge(
        _start(playbook),
        playbook,
        collaborators,
        resolution=_resolution(discipline_field_id=None),
    )

    # SPECIFIED: every task is given its gate value -- every one, which is
    # also this test's control against an absence that means nothing.
    for step_id, gate in ((STEP_ID, STEP_GATE), (CONTROL_STEP_ID, CONTROL_GATE)):
        task = _task_for(collaborators, step_id)
        assert task.custom_fields.get(GATE_FIELD_ID) == GATE_OPTION_IDS[gate]

    # SPECIFIED: no discipline value is written.
    assert [
        write
        for write in collaborators.clickup.field_writes()
        if write[1] == DISCIPLINE_FIELD_ID
    ] == []


async def test_a_field_write_that_fails_costs_only_that_field(
    captured_logs: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A field write that fails costs only that field.

    WHEN setting the gate value on a task fails
    THEN the discipline value is still attempted for that task
    AND the pass continues over the remaining launches
    AND nothing about this fault causes the run to be recorded as failed
    AND the omission is reported as a warning-level log record naming the
    step, the field and the task.

    "The pass continues over the remaining launches" has no signal below the
    job; what is asserted here is its precondition -- that `converge_launch`
    returns normally rather than raising, which is what
    `One launch's failure does not stop the other launches being converged`
    turns a raise into. The same reading covers "recorded as failed".
    """
    playbook = _playbook((_step(), _control_step()))
    collaborators = _Collaborators()
    collaborators.clickup.refuse_field_ids = (GATE_FIELD_ID,)

    # SPECIFIED: nothing about this fault fails the run.
    await _converge(_start(playbook), playbook, collaborators, resolution=_resolution())

    task = _task_for(collaborators, STEP_ID)
    # SPECIFIED: the discipline value is still attempted for that task.
    attempted = {field_id for field_id, _ in _writes_for(collaborators, task.id)}
    assert DISCIPLINE_FIELD_ID in attempted, (
        "a failing gate write took the task's other field with it; the "
        f"requirement requires the other field to still be attempted: {attempted!r}"
    )
    assert (
        task.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[STEP_DISCIPLINE.value]
    )

    # SPECIFIED: the pass continues -- the *other step's* task is still
    # projected and valued. (The cross-launch half is at the job level.)
    control = _task_for(collaborators, CONTROL_STEP_ID)
    assert (
        control.custom_fields.get(DISCIPLINE_FIELD_ID)
        == DISCIPLINE_OPTION_IDS[CONTROL_DISCIPLINE.value]
    )

    # SPECIFIED: a warning-level record naming the step, the field and the
    # task. All three, since the report exists to be actionable.
    warnings = [
        record
        for record in captured_logs.records
        if record.levelno >= logging.WARNING
        and STEP_ID in _rendered(record)
        and GATE_FIELD_ID in _rendered(record)
        and task.id in _rendered(record)
    ]
    assert warnings, (
        "no warning-level record names the step, the field and the task "
        "together; the rendered records were:\n"
        + "\n".join(
            f"{record.levelname}: {_rendered(record)}"
            for record in captured_logs.records
        )
    )


def _rendered(record: logging.LogRecord) -> str:
    """A record's message together with its structured arguments.

    Both, because this project's logging is structured -- a field named in
    an extra rather than interpolated into the message is still a record
    that names it.
    """
    parts = [record.getMessage(), str(getattr(record, "args", ""))]
    parts.extend(
        f"{key}={value}"
        for key, value in vars(record).items()
        if key
        not in {
            "args",
            "msg",
            "exc_info",
            "exc_text",
            "stack_info",
            "created",
            "msecs",
            "relativeCreated",
        }
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - "A launch that has reached `graduated` is not visited by any pass at
#   all" -- stated by the requirement as a consequence of *Each launch is
#   projected into its own ClickUp list*, which owns it and already has its
#   own coverage. Nothing about Custom Fields changes it, and a test here
#   would assert that requirement rather than this one.
# - The `graduated` backfill exclusion, for the same reason.
# - Which order the two writes are sent in. The requirement fixes that both
#   follow the create; nothing fixes their order relative to each other.
# - Whether a value is written for a step whose task is being re-projected
#   after deletion. The re-projection rule belongs to the projection
#   requirement, and the new task reaches this rule as any newly created
#   task does.
# ---------------------------------------------------------------------------
