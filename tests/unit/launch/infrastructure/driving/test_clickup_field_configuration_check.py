"""The Custom Field configuration is checked once per pass, and a gap is
reported to Slack without stopping the pass.

Derived strictly from the delta spec of the OpenSpec change
`record-gate-and-discipline-as-fields`:
`openspec/changes/record-gate-and-discipline-as-fields/specs/launch-clickup-sync/spec.md`

Covers every scenario of the ADDED requirement *The Custom Field
configuration is checked once per pass and a gap is reported without
stopping the pass* -- all thirty -- and the **reporting half** of six
scenarios of the ADDED requirement *A projected task carries its step's gate
and discipline as Custom Field values*, whose write half is covered at the
projection level in
`tests/unit/launch/infrastructure/driven/test_clickup_sync_custom_fields.py`:

- *No value is written to a field found in a gap* -- "the gap is reported
  once for the pass rather than once per task"
- *A re-gated step whose new gate has no option keeps its former value* --
  "the missing option is reported as a configuration gap"
- *An option differing only in wording is not a match* -- "the gate is
  reported as having no matching option"
- *A deployment configuring no field writes none* -- "no configuration
  report is made"
- *A field identifier configured but empty is a gap* -- "that field is
  reported as configured with no value, rather than treated as declined"
- *A deployment configuring one field records only that one* -- "nothing
  about the discipline field is reported"

and the whole of one further scenario of that requirement, which has no
signal below this level at all:

- *A stood-down pass writes no value*

See this change's `test-manifest.md` for the full accounting.

## Level

The job body. Every scenario here is stated over "a pass" -- what is read
once, what reaches Slack, what is suppressed, and whether the run is
recorded as failed. None of it has a signal below the job: the check runs
before the walk, in the same phase as readiness, and the two pass functions
each take one launch and do not know the check exists.

"Reported as a failed run" is read as *the job body raises*, and "succeeded"
as *it returns normally* -- the reading
`test_clickup_sync_job_stand_down.py` and
`test_clickup_sync_job_containment.py` already record for the same words,
and the only outcome signal a job body has.

## THE SEAM CONTRACT

No artifact fixes how the check reaches its collaborators. This file
follows the pattern `test_overdue_check.py` records for the overdue check --
collaborators imported by name into the job module's namespace and
referenced as bare globals -- and probes for each, failing with a directive
rather than an `AttributeError`.

Transcribed from `test_clickup_sync_job_containment.py`, unchanged:

- reaching the job through the runner's periodic registry, never by module
  path or task name (`_completion_periodic`, `_run_job`)
- `converge_launch` / `reconcile_launch` / `LaunchRepository` /
  `PlaybookRepository` / `session`|`transaction` as the substituted
  collaborators
- `_build_not_ready`'s four-way signature probe for
  `PlaybookNotReadyError`

Added by this change, and INVENTED:

- **The folder read.** Installed both on the job module (under any of
  `_FOLDER_READ_NAMES`) and on `clickup_client` itself, so a job that
  imported the operation by name and one that calls it through the module
  both reach the fake. `tasks.md` 2.3 fixes the operation's name
  (`folder_fields`); that the job holds it as a bare global is the invented
  part.
- **The notifier.** `worker.py` injects a `MonitoringNotifier` for the
  overdue check already (`tasks.md` 5.2 -- "a new consumer, not new
  plumbing"), so this file installs a fake under `notifier` and
  `monitoring_notifier` on the job module. A job reading it under some
  third name delivers nothing here, and the assertion says so by name.
- **The suppression record.** `tasks.md` 5.1 fixes that there is one and
  what it holds ("the identity of the last gap **reported**, and when"); no
  artifact names its accessors. `install_suppression_store` therefore
  *discovers* them -- any job-module global whose name mentions a gap --
  and classifies each by verb (`record_`/`save_`/`write_` writes,
  `clear_`/`lift_`/`delete_` clears, anything else reads), substituting a
  class with a factory over the same fake. Where nothing is discovered, a
  default name set is installed and `_require_store_used` fails the
  suppression-specific tests with a directive, so the seam does not take
  the other twenty tests down with it.
- **The field definition value object.** `_FieldDefinition` /
  `_FieldOption` carry the four facts `tasks.md` 2.1 fixes plus the
  uninterpretable marker 2.3a fixes, under both plausible attribute
  spellings each (`id`/`identifier`, `type`/`field_type`), so a
  structurally-typed implementation finds what it reads for.
- **What the resolution looks like.** Nothing here pins it.
  `_writable_fields` asks only "does anything handed to the pass name this
  field identifier?", which is the whole of what the write-withholding
  clauses require to be observable from here.

Correcting any of the above is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: whether a read was made, how many messages were delivered, what
they name, whether suppression was written or cleared, whether every launch
was walked, and whether the job raised.

## Assertions about a message's wording

Several scenarios are *about* what a report says -- that an absent field is
not reported as each of its options missing, that an uninterpretable field
is not reported as declaring no options, that a wrong order names the order
found. Those are assertions on the message text, and there is no other
place they could be made. Each such assertion is written against a word the
delta itself uses (`uninterpretable`, `order`), or -- better where it is
available -- as a **comparison between two messages** the requirement says
must differ, which pins no vocabulary at all. Both kinds are labelled
DERIVED at their site.

## Expected first-run state

No configuration check exists: the job makes no folder read, delivers no
message and keeps no suppression record. Every test here is expected to
fail on an **absent target**, most of them on "no report was delivered".
Per `ai-toolkit:testing` that establishes absence and nothing about whether
these assertions are well-formed.

**One test is expected to pass**, and it is not the fourth failure state:
`test_a_stood_down_pass_writes_no_value` states behaviour the change must
preserve rather than introduce, and its own docstring records why.

Every other test asserting an **absence** -- no report, no read, no write,
no suppression -- carries a positive control **in the same test**: the same
state under which the thing does happen. Eight of them passed on their
first draft for exactly the reason `ai-toolkit:testing`'s fourth state
names, and each was given its control rather than left as coverage.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` at the worktree root --
1130 passed, 0 failed.
"""

from __future__ import annotations

import datetime
import inspect
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Final

import pytest
from procrastinate import job_context, jobs

import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
from commerce_ops.launch.domain import launch_playbook as playbook_module
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
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven import clickup_client

pytestmark = pytest.mark.anyio

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

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

UNHELD_GATE: Final = "graduated"

DISCIPLINES: Final = tuple(member.value for member in Discipline)

#: Three launches, so "once for the pass rather than once per task" is
#: distinguishable from "once per launch".
FIRST: Final = ProductId(str(uuid.uuid4()))
SECOND: Final = ProductId(str(uuid.uuid4()))
THIRD: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FIRST, SECOND, THIRD)

PASS_NAMES: Final = ("converge_launch", "reconcile_launch")

FOLDER_ID: Final = "90110042424"
GATE_FIELD_ID: Final = "4bd1f0f9-6f2a-4f0e-9d5d-0f4a1c6b2e11"
DISCIPLINE_FIELD_ID: Final = "5ce2a1f0-7a3b-4b1f-8e6e-1a5b2d7c3f22"

GATE_FIELD_NAME: Final = "Gate"
DISCIPLINE_FIELD_NAME: Final = "Discipline"

#: The type whose values the system writes, and one that declares options
#: but is not it. DERIVED from ClickUp's own type names, which `design.md`
#: uses ("a multi-select declares options too").
DROP_DOWN: Final = "drop_down"
MULTI_SELECT: Final = "labels"

_FOLDER_READ_NAMES: Final = (
    "folder_fields",
    "read_folder_fields",
    "clickup_folder_fields",
    "list_folder_fields",
)

_NOTIFIER_NAMES: Final = ("notifier", "monitoring_notifier")

_DEFAULT_STORE_NAMES: Final = (
    "last_reported_field_gap",
    "record_field_gap_reported",
    "clear_field_gap_report",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_clickup_sync_job_containment.py`
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


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=0),
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": "Held until the automated check reports green.",
        "handler": "fixture.holding_check",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _ready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


def _unready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=tuple(
            _hold(
                gate,
                status=StepStatus.DRAFT if gate == UNHELD_GATE else StepStatus.ACTIVE,
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
    )


def _launch_for(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id,
        playbook=_ready_playbook(),
        launch_date=datetime.date(2027, 3, 2),
    )
    return launch


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    """`PlaybookNotReadyError`, under whichever signature it carries --
    transcribed from `test_clickup_sync_job_stand_down.py`."""
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError`, so a stand-down cannot be provoked here"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": (UNHELD_GATE,)}),
        ((), {"playbook": playbook, "unheld_gates": (UNHELD_GATE,)}),
        (((UNHELD_GATE,), playbook), {}),
        ((playbook, (UNHELD_GATE,)), {}),
    )
    for args, kwargs in attempts:
        try:
            return error(*args, **kwargs)  # type: ignore[no-any-return]
        except TypeError:
            continue
    pytest.fail(
        "could not construct PlaybookNotReadyError under any probed "
        "signature; correct `_build_not_ready` to the implemented one"
    )


# ---------------------------------------------------------------------------
# Reaching the job -- transcribed from `test_clickup_sync_job_containment.py`
# ---------------------------------------------------------------------------


def _runner_app() -> Any:
    from commerce_ops.shared.infrastructure.driven.job_runner import app

    return app


def _completion_periodic() -> Any:
    registered = list(_runner_app().periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "clickup" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the ClickUp completion pass "
        f"under {JOB_PACKAGE!r}; registered periodics are "
        f"{[entry.task.name for entry in registered]}"
    )
    return matching[0]


def _job_module() -> ModuleType:
    return sys.modules[_completion_periodic().task.func.__module__]


async def _run_job() -> Any:
    task = _completion_periodic().task
    parameters = inspect.signature(task.func).parameters
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=_runner_app(),
                job=jobs.Job(
                    id=1,
                    queue=task.queue,
                    lock=task.lock,
                    queueing_lock=task.queueing_lock,
                    task_name=task.name,
                    task_kwargs={},
                    attempts=0,
                ),
                start_timestamp=time.time(),
                abort_reason=lambda: None,
            )
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Field definitions -- INVENTED value objects (see the SEAM CONTRACT)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FieldOption:
    id: str
    name: str

    @property
    def identifier(self) -> str:
        return self.id

    @property
    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class _FieldDefinition:
    id: str
    name: str
    type: str
    options: tuple[_FieldOption, ...] = ()
    uninterpretable: bool = False

    @property
    def identifier(self) -> str:
        return self.id

    @property
    def field_type(self) -> str:
        return self.type

    @property
    def is_uninterpretable(self) -> bool:
        return self.uninterpretable

    @property
    def interpretable(self) -> bool:
        return not self.uninterpretable


def _option(name: str) -> _FieldOption:
    """An option whose identifier is deliberately unlike its name, so an
    implementation matching on the wrong one fails rather than passes."""
    return _FieldOption(
        id=f"opt-{uuid.uuid5(uuid.NAMESPACE_OID, name).hex[:12]}", name=name
    )


def _gate_field(
    names: Sequence[str] = SPECIFIED_GATE_ORDER,
    *,
    field_type: str = DROP_DOWN,
    uninterpretable: bool = False,
) -> _FieldDefinition:
    return _FieldDefinition(
        id=GATE_FIELD_ID,
        name=GATE_FIELD_NAME,
        type=field_type,
        options=tuple(_option(name) for name in names),
        uninterpretable=uninterpretable,
    )


def _discipline_field(
    names: Sequence[str] = DISCIPLINES,
    *,
    field_type: str = DROP_DOWN,
    uninterpretable: bool = False,
) -> _FieldDefinition:
    return _FieldDefinition(
        id=DISCIPLINE_FIELD_ID,
        name=DISCIPLINE_FIELD_NAME,
        type=field_type,
        options=tuple(_option(name) for name in names),
        uninterpretable=uninterpretable,
    )


def _well_formed() -> tuple[_FieldDefinition, ...]:
    """A folder in which nothing is wrong -- the control every "a gap is
    reported" test is read against."""
    return (_gate_field(), _discipline_field())


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _Timeline:
    """What happened, in the order it happened -- so "before any task is
    written" is assertable rather than merely counted."""

    events: list[str] = field(default_factory=list)

    def note(self, event: str) -> None:
        self.events.append(event)

    def index_of(self, prefix: str) -> int | None:
        for position, event in enumerate(self.events):
            if event.startswith(prefix):
                return position
        return None

    @property
    def rendered(self) -> str:
        return "\n".join(self.events)


class _Pass:
    """Stands in for `converge_launch` / `reconcile_launch`."""

    def __init__(self, name: str, timeline: _Timeline) -> None:
        self.name = name
        self.timeline = timeline
        self.seen: list[ProductId] = []
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.failures: dict[ProductId, Any] = {}

    def fail_for(self, product_id: ProductId, build: Any) -> None:
        self.failures[product_id] = build

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        self.seen.append(product_id)
        self.calls.append((args, kwargs))
        self.timeline.note(f"{self.name}:{product_id}")
        build = self.failures.get(product_id)
        if build is not None:
            raise build()


class _WritingPass(_Pass):
    """A `converge_launch` stand-in that writes one Custom Field value.

    Exists for exactly one test: the stand-down's "no Custom Field value is
    written on any task of any launch" is an absence, and an absence is
    unfalsifiable where nothing writes. This pass makes the ready run write,
    so the stood-down run's silence means something.
    """

    def __init__(self, timeline: _Timeline) -> None:
        super().__init__("converge_launch", timeline)

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        await super().__call__(*args, **kwargs)
        setter = getattr(clickup_client, "set_task_field", None)
        if setter is not None:
            await setter("task-001", GATE_FIELD_ID, "opt-control")


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    for candidate in (*args, *kwargs.values()):
        if isinstance(candidate, Launch):
            return candidate.product_id
        if isinstance(candidate, ProductId) and candidate in WALK:
            return candidate
        if isinstance(candidate, str) and candidate in {p.value for p in WALK}:
            return ProductId(candidate)
    pytest.fail(
        "a pass was called with no launch and no product identifier among "
        f"its arguments (args={args!r}, kwargs={kwargs!r})"
    )


class _FolderRead:
    """The one folder-scope read the pass may make."""

    def __init__(self, timeline: _Timeline) -> None:
        self.timeline = timeline
        self.calls: list[str] = []
        self.fields: tuple[_FieldDefinition, ...] = _well_formed()
        self.raises: BaseException | None = None

    async def __call__(self, *args: Any, **kwargs: Any) -> Sequence[_FieldDefinition]:
        folder_id = str(kwargs.get("folder_id") or (args[0] if args else ""))
        self.calls.append(folder_id)
        self.timeline.note(f"folder_read:{folder_id}")
        if self.raises is not None:
            raise self.raises
        return self.fields


class _DeliveryRefused(RuntimeError):
    """What the monitoring notifier raises when Slack cannot be reached."""


class _FakeNotifier:
    """A `MonitoringNotifier`, satisfied structurally by an object rather
    than a module -- the distinction `test_monitoring_notifier_port.py`
    insists on for the wiring, and irrelevant to what is asserted here."""

    def __init__(self, timeline: _Timeline) -> None:
        self.timeline = timeline
        self.messages: list[str] = []
        self.refuse = False

    async def post_monitoring_message(self, message: str) -> None:
        self.timeline.note(f"report:{message}")
        if self.refuse:
            raise _DeliveryRefused("Slack refused the message")
        self.messages.append(message)


class _SuppressionStore:
    """The record that keeps a continuing gap to one message.

    Opaque by design: it stores whatever identity the implementation hands
    it and compares by equality, so nothing here pins the identity's shape.
    That is what lets *A gap repaired into a different gap is reported
    again* and *Reordering options during a duplicate does not re-report it*
    be asserted at all -- each turns on whether two identities differ, not
    on what they are.
    """

    def __init__(self, timeline: _Timeline) -> None:
        self.timeline = timeline
        self.row: Any = None
        self.reads = 0
        self.writes: list[Any] = []
        self.clears = 0
        self.fail_read: BaseException | None = None
        self.fail_write: BaseException | None = None
        self.fail_clear: BaseException | None = None
        self.used = False

    async def read(self, *args: Any, **kwargs: Any) -> Any:
        self.used = True
        self.reads += 1
        self.timeline.note("store_read")
        if self.fail_read is not None:
            raise self.fail_read
        return self.row

    async def record(self, *args: Any, **kwargs: Any) -> None:
        self.used = True
        identity = next(
            (value for value in (*args, *kwargs.values()) if value is not None), None
        )
        self.writes.append(identity)
        self.timeline.note("store_write")
        if self.fail_write is not None:
            raise self.fail_write
        self.row = identity

    async def clear(self, *args: Any, **kwargs: Any) -> None:
        self.used = True
        self.clears += 1
        self.timeline.note("store_clear")
        if self.fail_clear is not None:
            raise self.fail_clear
        self.row = None

    # Spellings a discovered *class* might be driven through.
    last_reported = read
    get = read
    current = read
    save = record
    lift = clear
    delete = clear


class _FakeSession:
    """The `AsyncSession` the walk shares -- transcribed from
    `test_clickup_sync_job_containment.py`."""

    def __init__(self, rollback_error: BaseException | None = None) -> None:
        self.rollbacks = 0
        self.commits = 0
        self.rollback_error = rollback_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None


class _FakeLaunches:
    def __init__(self, launches: tuple[Launch, ...]) -> None:
        self._launches = launches

    async def list_active(self) -> tuple[Launch, ...]:
        return self._launches

    active = list_active
    all_active = list_active

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return self._launches


# ---------------------------------------------------------------------------
# The world: every seam, installed together
# ---------------------------------------------------------------------------


@dataclass
class _World:
    job_module: ModuleType
    timeline: _Timeline
    passes: dict[str, _Pass]
    folder_read: _FolderRead
    notifier: _FakeNotifier
    store: _SuppressionStore
    session: _FakeSession
    store_discovered: bool

    @property
    def messages(self) -> list[str]:
        return self.notifier.messages

    @property
    def reports(self) -> int:
        return len(self.notifier.messages)


def _install_session(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: _FakeSession
) -> _FakeSession:
    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[_FakeSession]:
        yield fake

    installed = [
        name for name in ("session", "transaction") if hasattr(job_module, name)
    ]
    assert installed, (
        f"{job_module.__name__} exposes neither `session` nor `transaction`, "
        "so this file cannot hand the walk a session it can observe"
    )
    for name in installed:
        monkeypatch.setattr(job_module, name, _provider)
    return fake


def _install_playbook_read(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    refusing_with: LaunchPlaybook | None,
) -> None:
    class _Repository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str = "") -> LaunchPlaybook:
            if refusing_with is not None:
                raise _build_not_ready(refusing_with)
            return _ready_playbook()

    monkeypatch.setattr(job_module, "PlaybookRepository", _Repository)


def _install_launches(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    products: Sequence[ProductId],
) -> None:
    monkeypatch.setattr(
        job_module,
        "LaunchRepository",
        lambda *a, **k: _FakeLaunches(tuple(_launch_for(p) for p in products)),
        raising=False,
    )


def _install_folder_read(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: _FolderRead
) -> None:
    """Installed on the job module *and* on the client module.

    Both, because nothing fixes whether the job imported the operation by
    name into its own namespace or calls it through the adapter module, and
    a test that installed only one of the two would silently observe no read
    from a job that made one.
    """
    for name in _FOLDER_READ_NAMES:
        monkeypatch.setattr(job_module, name, fake, raising=False)
        monkeypatch.setattr(clickup_client, name, fake, raising=False)


def _install_notifier(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: _FakeNotifier
) -> None:
    for name in _NOTIFIER_NAMES:
        monkeypatch.setattr(job_module, name, fake, raising=False)


def _install_suppression_store(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: _SuppressionStore
) -> bool:
    """Substitutes whatever the job holds for the suppression record.

    Discovery rather than transcription: any job-module global whose name
    mentions a gap is taken to be one of the record's three accessors and
    classified by its verb. A discovered *class* is replaced by a factory
    over the same fake, so a repository object is driven too. Returns
    whether anything was discovered.
    """
    discovered = [
        name
        for name in dir(job_module)
        if not name.startswith("__") and "gap" in name.lower()
    ]
    for name in discovered:
        current = getattr(job_module, name)
        if isinstance(current, type):
            monkeypatch.setattr(job_module, name, lambda *a, **k: fake)
            continue
        lowered = name.lower()
        if lowered.startswith(("record", "save", "write", "note", "remember")):
            monkeypatch.setattr(job_module, name, fake.record)
        elif lowered.startswith(("clear", "lift", "delete", "forget", "reset")):
            monkeypatch.setattr(job_module, name, fake.clear)
        else:
            monkeypatch.setattr(job_module, name, fake.read)
    if discovered:
        return True
    for name, member in zip(
        _DEFAULT_STORE_NAMES, (fake.read, fake.record, fake.clear), strict=True
    ):
        monkeypatch.setattr(job_module, name, member, raising=False)
    return False


def _clear_settings_cache(job_module: ModuleType) -> None:
    from commerce_ops.shared.application.settings import get_settings

    get_settings.cache_clear()
    for value in list(vars(job_module).values()):
        cache_clear = getattr(value, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


@pytest.fixture()
def configuration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Both field identifiers and the launch folder, configured.

    Set through the environment rather than by substituting a settings
    object, so this file pins no accessor: `tasks.md` 1.1 declares both on
    the settings model and 1.4 requires them to be read by their literal
    names.
    """
    monkeypatch.setenv("CLICKUP_LAUNCH_FOLDER_ID", FOLDER_ID)
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", GATE_FIELD_ID)
    monkeypatch.setenv("CLICKUP_DISCIPLINE_FIELD_ID", DISCIPLINE_FIELD_ID)
    module = _job_module()
    _clear_settings_cache(module)
    yield
    _clear_settings_cache(module)


@pytest.fixture()
def world(monkeypatch: pytest.MonkeyPatch, configuration: None) -> _World:
    """Every seam installed, with a ready playbook and three launches."""
    job_module = _job_module()
    timeline = _Timeline()

    missing = [name for name in PASS_NAMES if not hasattr(job_module, name)]
    assert not missing, (
        f"{job_module.__name__} exposes none of {missing}; correct "
        "`PASS_NAMES` to the implemented collaborator names"
    )
    passes = {name: _Pass(name, timeline) for name in PASS_NAMES}
    for name, fake in passes.items():
        monkeypatch.setattr(job_module, name, fake)

    _install_launches(job_module, monkeypatch, WALK)
    _install_playbook_read(job_module, monkeypatch, refusing_with=None)
    session = _install_session(job_module, monkeypatch, _FakeSession())

    folder_read = _FolderRead(timeline)
    _install_folder_read(job_module, monkeypatch, folder_read)

    notifier = _FakeNotifier(timeline)
    _install_notifier(job_module, monkeypatch, notifier)

    store = _SuppressionStore(timeline)
    discovered = _install_suppression_store(job_module, monkeypatch, store)

    return _World(
        job_module=job_module,
        timeline=timeline,
        passes=passes,
        folder_read=folder_read,
        notifier=notifier,
        store=store,
        session=session,
        store_discovered=discovered,
    )


def _stand_down(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_playbook_read(
        world.job_module, monkeypatch, refusing_with=_unready_playbook()
    )


def _no_launches(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_launches(world.job_module, monkeypatch, ())


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _require_store_used(world: _World) -> None:
    """The suppression seam, asserted only where a test turns on it."""
    assert world.store_discovered or world.store.used, (
        f"{world.job_module.__name__} holds no global whose name mentions a "
        "gap, and none of "
        f"{list(_DEFAULT_STORE_NAMES)} was called, so this file cannot "
        "observe the record `tasks.md` 5.1 requires. Correct "
        "`_install_suppression_store` to the implemented accessors -- a "
        "fixture correction, not a change to what is asserted."
    )


def _require_a_report(world: _World) -> None:
    assert world.messages, (
        "no message reached the monitoring notifier. This file installs the "
        f"fake under {list(_NOTIFIER_NAMES)} on "
        f"{world.job_module.__name__}; a job reading it under some other "
        "name delivers nothing observable here. Timeline:\n" + world.timeline.rendered
    )


def _only_report(world: _World) -> str:
    _require_a_report(world)
    assert len(world.messages) == 1, (
        f"expected exactly one report, got {len(world.messages)}:\n"
        + "\n".join(world.messages)
    )
    return world.messages[0]


def _walked(world: _World) -> list[ProductId]:
    return world.passes["converge_launch"].seen


def _writable_fields(world: _World) -> set[str]:
    """The field identifiers anything handed to a pass names.

    Nothing here pins the resolution's shape -- see the SEAM CONTRACT. A
    field the check found in a gap of the kinds that withhold writes must
    not appear, which is the whole of what those clauses require to be
    observable from this level.
    """
    found: set[str] = set()
    known = {GATE_FIELD_ID, DISCIPLINE_FIELD_ID}
    for args, kwargs in world.passes["converge_launch"].calls:
        for candidate in (*args, *kwargs.values()):
            found |= _field_ids_within(candidate, known)
    return found


def _field_ids_within(candidate: Any, known: set[str], depth: int = 0) -> set[str]:
    if depth > 3:
        return set()
    if isinstance(candidate, str):
        return {candidate} & known
    if isinstance(candidate, Mapping):
        found = set(candidate) & known
        for value in candidate.values():
            found |= _field_ids_within(value, known, depth + 1)
        return found
    if isinstance(candidate, list | tuple | set | frozenset):
        found = set()
        for item in candidate:
            found |= _field_ids_within(item, known, depth + 1)
        return found
    found = set()
    for name in dir(candidate):
        if name.startswith("_"):
            continue
        try:
            value = getattr(candidate, name)
        except Exception:  # noqa: BLE001,S112 -- a property that raises is
            # not this reader's business; it is looking for field ids.
            continue
        if isinstance(value, str):
            found |= {value} & known
        elif isinstance(value, Mapping | list | tuple | set | frozenset):
            found |= _field_ids_within(value, known, depth + 1)
    return found


def _positions(message: str, names: Sequence[str]) -> list[int]:
    return [message.find(name) for name in names]


# ---------------------------------------------------------------------------
# Requirement: The Custom Field configuration is checked once per pass and a
# gap is reported without stopping the pass
# ---------------------------------------------------------------------------


async def test_a_missing_option_is_reported_before_any_task_is_written(
    world: _World,
) -> None:
    """Scenario: A missing option is reported before any task is written.

    WHEN a pass runs and the gate field declares no option naming one of the
    playbook's gates
    THEN the gap is reported to Slack naming that gate and that field
    AND the report is made once for the pass, not once per task.

    Also covers, from *A re-gated step whose new gate has no option keeps
    its former value*, its second clause: "the missing option is reported as
    a configuration gap".
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "stock-ready"]),
        _discipline_field(),
    )

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: naming that gate...
    assert "stock-ready" in message, (
        f"the report does not name the missing gate: {message!r}"
    )
    # ...and that field. Either the identifier the deployment configured or
    # the name the field carries answers "which field"; nothing fixes which.
    assert GATE_FIELD_ID in message or GATE_FIELD_NAME in message, (
        f"the report does not say which field the gate is missing from: {message!r}"
    )
    # SPECIFIED: "It SHALL name what the field does declare where an
    # expected option is missing, so a hand-typed mismatch is diagnosable."
    assert "listable" in message, (
        "the report does not name what the field does declare, so a "
        f"hand-typed mismatch is not diagnosable from it: {message!r}"
    )
    # SPECIFIED: once for the pass, not once per task -- three launches.
    assert len(world.messages) == 1
    # SPECIFIED: before any task is written.
    read_at = world.timeline.index_of("folder_read")
    reported_at = world.timeline.index_of("report:")
    first_pass_at = world.timeline.index_of("converge_launch")
    assert read_at is not None and reported_at is not None
    assert first_pass_at is not None, (
        "no launch was converged, so 'before any task is written' asserts nothing here"
    )
    assert read_at < first_pass_at and reported_at < first_pass_at, (
        "the check ran after the walk had begun; it is required once per "
        f"pass, before any task is written:\n{world.timeline.rendered}"
    )


async def test_a_gap_does_not_stop_the_pass(world: _World) -> None:
    """Scenario: A gap does not stop the pass.

    WHEN a pass runs with a configuration gap standing
    THEN every task is still projected and corrected, and every value that
    does resolve is still written
    AND nothing about the gap causes the run to be recorded as failed.
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "stock-ready"]),
        _discipline_field(),
    )

    # SPECIFIED: the run is not recorded as failed.
    await _run_job()

    # SPECIFIED: every task is still projected and corrected...
    assert _walked(world) == list(WALK)
    assert world.passes["reconcile_launch"].seen == list(WALK)
    # ...and every value that does resolve is still written: both fields
    # reach the pass, since neither is in a gap of the kinds that withhold
    # writes.
    assert _writable_fields(world) == {GATE_FIELD_ID, DISCIPLINE_FIELD_ID}


async def test_a_gap_is_not_a_per_launch_failure(world: _World) -> None:
    """Requirement clause, asserted for `tasks.md` 4.3b.

    "A gap is likewise **not** a per-launch failure and SHALL NOT be
    contained, reported or counted as one" -- while an unrelated launch
    failure still fails the run, which is
    *One launch's failure does not stop the other launches being converged*
    deciding the outcome and this requirement taking nothing away from it.

    DERIVED as a test: no `#### Scenario:` block states the pairing, and it
    is `tasks.md` 4.3b that asks for it in as many words ("Add tests
    asserting a gap leaves the run's outcome untouched while an unrelated
    launch failure still fails it"). Recorded in the manifest as derived.
    """
    world.folder_read.fields = (_gate_field(field_type=MULTI_SELECT),)
    world.passes["converge_launch"].fail_for(
        SECOND, lambda: RuntimeError("an unrelated launch failure")
    )

    with pytest.raises(Exception) as raised:
        await _run_job()

    # The gap did not become a launch failure of its own: only the launch
    # that actually failed is named.
    message = str(raised.value)
    assert SECOND.value in message
    assert FIRST.value not in message and THIRD.value not in message, (
        f"a configuration gap was counted as a per-launch failure: {message!r}"
    )
    assert _walked(world) == list(WALK)
    # The control, without which this test holds against a pass that never
    # checked the configuration at all: the gap was found and reported.
    assert world.folder_read.calls == [FOLDER_ID]
    assert len(world.messages) == 1, (
        "no gap was reported, so nothing here distinguishes 'a gap is not a "
        "per-launch failure' from 'there was no gap'"
    )


async def test_every_gap_is_named_together(world: _World) -> None:
    """Scenario: Every gap is named together.

    WHEN a pass runs and two gates and one discipline have no matching
    option
    THEN the report names all three.

    "The report SHALL name every gap found, not the first, so that one
    repair round closes them all."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g not in {"order", "live"}]),
        _discipline_field([d for d in DISCIPLINES if d != "ppc"]),
    )

    await _run_job()

    message = _only_report(world)

    # SPECIFIED: all three.
    for missing in ("order", "live", "ppc"):
        assert missing in message, (
            f"the report does not name {missing!r}; every gap must be named "
            f"so one repair round closes them all: {message!r}"
        )


async def test_a_configured_field_that_is_absent_is_a_gap(world: _World) -> None:
    """Scenario: A configured field that is absent is a gap.

    WHEN a pass runs and a configured field identifier is not among the
    folder's Custom Fields
    THEN the gap is reported as that field being absent, rather than as each
    of its options being missing.

    Also covers, from *A projected task carries its step's gate and
    discipline as Custom Field values*, that no value is written for an
    absent field.
    """
    world.folder_read.fields = (_discipline_field(),)

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: the report says which field.
    assert GATE_FIELD_ID in message or GATE_FIELD_NAME in message
    # SPECIFIED: rather than as each of its options being missing. The
    # narrowing clause: "no option-level or order finding SHALL be composed
    # for that field".
    named_gates = [gate for gate in SPECIFIED_GATE_ORDER if gate in message]
    assert len(named_gates) < len(SPECIFIED_GATE_ORDER), (
        "the report names every gate as missing an option, which is the "
        "narrowing an absent field is supposed to produce instead: "
        f"{message!r}"
    )
    # SPECIFIED (write-withholding): nothing is written for an absent field.
    assert GATE_FIELD_ID not in _writable_fields(world)


async def test_a_field_declaring_one_option_name_twice_is_a_gap(
    world: _World,
) -> None:
    """Scenario: A field declaring one option name twice is a gap.

    WHEN a pass runs and the gate field declares two options both named for
    the same gate
    THEN the gap is reported, naming the duplicated name
    AND no value is written for that field on any task.
    """
    world.folder_read.fields = (
        _gate_field((*SPECIFIED_GATE_ORDER, "listable")),
        _discipline_field(),
    )

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: naming the duplicated name.
    assert "listable" in message
    # SPECIFIED: no value is written for that field on any task -- "any
    # write picks one arbitrarily, and a pick that is not stable across
    # passes makes every pass disagree with the task and write again".
    assert GATE_FIELD_ID not in _writable_fields(world)
    # The control: the discipline field, in no gap, is still writable.
    assert DISCIPLINE_FIELD_ID in _writable_fields(world)


async def test_a_duplicate_under_a_name_that_is_no_gate_is_not_a_gap(
    world: _World,
) -> None:
    """Scenario: A field declaring one option name twice is a gap -- its
    third clause.

    AND a gate field declaring two options under a name that is no gate at
    all is not a gap.

    "It makes no write ambiguous, and reporting it would disable a field
    over a duplicate that has nothing to do with this system's use of it."
    """
    world.folder_read.fields = (
        _gate_field((*SPECIFIED_GATE_ORDER, "internal", "internal")),
        _discipline_field(),
    )

    await _run_job()

    # SPECIFIED: not a gap.
    assert world.messages == [], (
        "a duplicate under a name the system never resolves against was "
        f"reported: {world.messages!r}"
    )
    # SPECIFIED: and the field is not disabled by it.
    assert GATE_FIELD_ID in _writable_fields(world)


async def test_a_field_the_read_could_not_interpret_is_reported_as_such(
    world: _World,
) -> None:
    """Scenario: A field the read could not interpret is reported as such.

    WHEN a pass runs and a configured field is reported by the read as
    uninterpretable
    THEN the gap names it as uninterpretable, not as declaring no options
    AND no value is written for that field on any task.

    The first THEN is asserted two ways: on the delta's own word
    (DERIVED -- it is the vocabulary the requirement itself uses), and as a
    **comparison** against the message a genuinely optionless field
    produces, which pins no vocabulary at all. The comparison is the
    load-bearing half: "telling someone to add options to a field that has
    them sends them to argue with their own screen".
    """
    world.folder_read.fields = (
        _gate_field((), uninterpretable=True),
        _discipline_field(),
    )
    await _run_job()
    uninterpretable_message = _only_report(world)

    # SPECIFIED: no value is written for that field on any task.
    assert GATE_FIELD_ID not in _writable_fields(world)
    assert DISCIPLINE_FIELD_ID in _writable_fields(world)

    # The same field, genuinely declaring no options, on a fresh pass.
    world.notifier.messages.clear()
    world.store.row = None
    world.folder_read.fields = (_gate_field(()), _discipline_field())
    await _run_job()
    optionless_message = _only_report(world)

    # SPECIFIED: not reported as the other.
    assert uninterpretable_message != optionless_message, (
        "an uninterpretable field and one declaring no options produced the "
        "same report; the delta requires them to be distinguishable, "
        "because they call for different repairs"
    )
    # DERIVED, on the delta's own word.
    assert "uninterpret" in uninterpretable_message.lower(), (
        "the report does not name the field as uninterpretable: "
        f"{uninterpretable_message!r}"
    )


async def test_a_configured_field_of_the_wrong_type_is_a_gap(world: _World) -> None:
    """Scenario: A configured field of the wrong type is a gap.

    WHEN a pass runs and a configured field is present but is not of the
    type whose values the system writes
    THEN the gap is reported as that field being of the wrong type.

    Also covers, from *No value is written to a field found in a gap*, its
    second clause: "the gap is reported once for the pass rather than once
    per task" -- three launches, one message.

    The type check is not optional: a multi-select declares options too, so
    an optionless-only check would let one through, and the field here
    declares an option for every gate.
    """
    world.folder_read.fields = (
        _gate_field(field_type=MULTI_SELECT),
        _discipline_field(),
    )

    await _run_job()

    message = _only_report(world)
    assert GATE_FIELD_ID in message or GATE_FIELD_NAME in message
    # DERIVED, on the delta's own word for the finding.
    assert "type" in message.lower(), (
        f"the report does not name the field as being of the wrong type: {message!r}"
    )
    # SPECIFIED: once for the pass, over three launches, rather than once
    # per task.
    assert len(world.messages) == 1
    # SPECIFIED: no value is written -- "writing anyway would send a value
    # to a field whose write behaviour the system has just established it
    # did not intend".
    assert GATE_FIELD_ID not in _writable_fields(world)
    # SPECIFIED: no option-level finding is composed for such a field.
    named_gates = [gate for gate in SPECIFIED_GATE_ORDER if gate in message]
    assert len(named_gates) < len(SPECIFIED_GATE_ORDER)


async def test_an_empty_identifier_is_reported_even_when_clickup_is_unreachable(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An empty identifier is reported even when ClickUp cannot be
    reached.

    WHEN a pass runs with a field's identifier present but empty, and the
    read of the folder's Custom Fields does not complete
    THEN the empty identifier is reported
    AND nothing is reported about the other field's options, since they
    could not be read.

    "The catch for a mis-rendered deployment must not depend on the service
    whose configuration is in question." This repository has already lost a
    deployment to exactly this shape.
    """
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", "")
    _clear_settings_cache(world.job_module)
    world.folder_read.raises = RuntimeError("ClickUp is unreachable")

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: the empty identifier is reported. DERIVED: that the report
    # says "gate" is how it names which field, there being no identifier to
    # name it by -- that is the point of the finding.
    assert "gate" in message.lower(), (
        f"the report does not say which field is configured with no value: {message!r}"
    )
    # SPECIFIED: nothing about the other field's options.
    named_disciplines = [name for name in DISCIPLINES if name in message.lower()]
    assert not named_disciplines, (
        "the report names the discipline field's options although they "
        f"could not be read: {named_disciplines} in {message!r}"
    )
    # SPECIFIED: the pass still runs.
    assert _walked(world) == list(WALK)


async def test_an_unreachable_clickup_is_not_reported_as_a_gap(world: _World) -> None:
    """Scenario: An unreachable ClickUp is not reported as a gap.

    WHEN a pass runs with both identifiers configured and non-empty, and the
    read of the folder's Custom Fields does not complete
    THEN no configuration gap is reported to Slack
    AND no suppression is written or cleared
    AND the pass still projects, corrects and reconciles every launch,
    writing no Custom Field values.

    "Reporting an unreachable ClickUp as two absent fields would deliver a
    false repair instruction and then suppress the truth behind it."
    """
    world.folder_read.raises = RuntimeError("ClickUp is unreachable")

    # SPECIFIED: the run is not recorded as failed.
    await _run_job()

    # The control: the read was attempted and failed. Without it, every
    # assertion below holds against a pass that makes no read at all.
    assert world.folder_read.calls == [FOLDER_ID], (
        "no folder read was attempted, so this test cannot distinguish 'a "
        "reachability fault is not a gap' from 'there is no check'"
    )
    # SPECIFIED: no gap is reported.
    assert world.messages == [], (
        f"a reachability fault was reported as a configuration gap: {world.messages!r}"
    )
    # SPECIFIED: no suppression is written or cleared.
    assert world.store.writes == []
    assert world.store.clears == 0
    # SPECIFIED: the pass still projects, corrects and reconciles.
    assert _walked(world) == list(WALK)
    assert world.passes["reconcile_launch"].seen == list(WALK)
    # SPECIFIED: writing no Custom Field values.
    assert _writable_fields(world) == set()


async def test_a_malformed_folder_read_is_not_reported_as_a_gap(
    world: _World,
) -> None:
    """Scenario: An unreachable ClickUp is not reported as a gap -- its
    "or a read whose result cannot be interpreted" half.

    The requirement states the clause over "A failure to read the folder's
    Custom Fields, **or a read whose result cannot be interpreted**", and
    `tasks.md` 4.3 requires the catch to cover a malformed payload as well
    as a transport fault ("do not narrow the catch to the client's HTTP
    error type alone"). `tasks.md` 2.3a makes this unreachable by contract;
    this is the belt to its braces.
    """
    world.folder_read.raises = ValueError("the folder read returned nonsense")

    await _run_job()

    # The control: the read was attempted and failed.
    assert world.folder_read.calls == [FOLDER_ID], (
        "no folder read was attempted, so this test cannot distinguish a "
        "tolerated malformed payload from an absent check"
    )
    assert world.messages == []
    assert world.store.writes == [] and world.store.clears == 0
    assert _walked(world) == list(WALK)


async def test_a_cancellation_during_the_check_is_not_absorbed(world: _World) -> None:
    """Requirement clause, asserted for `tasks.md` 5.5a.

    "A cancellation or shutdown of the process running the pass is **not**
    among the failures any clause of this requirement or the one above
    absorbs. It SHALL be left to propagate."

    DERIVED as a test: no `#### Scenario:` block states it for this
    requirement, though the clause is stated in as many words and
    `test_clickup_sync_job_containment.py` already asserts the same property
    for the walk. Recorded in the manifest as derived.
    """
    world.folder_read.raises = KeyboardInterrupt("the worker was stopped")

    with pytest.raises(BaseException) as raised:
        await _run_job()

    assert isinstance(raised.value, KeyboardInterrupt), (
        "a cancellation of the process running the pass was absorbed by the "
        f"folder read's catch: {raised.value!r}"
    )
    assert _walked(world) == [], (
        "the walk continued after the process was told to stop; a worker "
        "being stopped must stop"
    )


async def test_a_pass_with_no_active_launches_still_checks_the_configuration(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A pass with no active launches still checks the
    configuration.

    WHEN a pass runs, the playbook is ready, and no launch is active
    THEN the folder's Custom Fields are still read and a standing gap is
    still reported
    AND the check does not depend on any launch existing.

    `tasks.md` 4.3c: "Answering when no launch exists is the whole reason
    folder scope was chosen over list scope, and an implementation that
    skips it satisfies every other scenario while defeating that."
    """
    _no_launches(world, monkeypatch)
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "ignition"]),
        _discipline_field(),
    )

    await _run_job()

    # SPECIFIED: the folder's Custom Fields are still read.
    assert world.folder_read.calls == [FOLDER_ID], (
        "no folder read was made on a pass with no active launch; the check "
        "must not sit behind an early return on an empty launch set"
    )
    # SPECIFIED: a standing gap is still reported.
    assert "ignition" in _only_report(world)
    # The control: nothing was walked, so the report cannot have come from a
    # launch.
    assert _walked(world) == []


async def test_a_pass_with_no_launch_folder_reports_only_the_empty_identifier(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A pass with no launch folder configured reports only the
    empty identifier.

    WHEN a pass runs with no launch folder configured and a field's
    identifier present but empty
    THEN no read of the folder's Custom Fields is made
    AND the empty identifier is reported and nothing else is
    AND no suppression is cleared.
    """
    monkeypatch.delenv("CLICKUP_LAUNCH_FOLDER_ID", raising=False)
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", "")
    _clear_settings_cache(world.job_module)
    # A gap that would be found if a read were made, so "nothing else is
    # reported" is read against a folder that has something to say.
    world.folder_read.fields = (_gate_field(()), _discipline_field(()))

    await _run_job()

    # SPECIFIED: no read is made -- leaving *Each launch is projected into
    # its own ClickUp list* the sole authority on the folder condition.
    assert world.folder_read.calls == [], (
        "a folder read was made with no launch folder configured: "
        f"{world.folder_read.calls!r}"
    )
    # SPECIFIED: the empty identifier is reported and nothing else is.
    message = _only_report(world)
    assert "gate" in message.lower()
    assert not [name for name in DISCIPLINES if name in message.lower()]
    # SPECIFIED: no suppression is cleared -- that state says nothing about
    # the two fields.
    assert world.store.clears == 0


async def test_an_empty_identifier_is_not_reported_during_a_stand_down(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An empty identifier is not reported during a stand-down.

    WHEN the passes stand down because the playbook cannot hold a launch,
    and a field's identifier is present but empty
    THEN nothing is reported, the empty identifier included.

    "A stood-down pass declines entirely rather than doing a reduced amount
    of work."
    """
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", "")
    _clear_settings_cache(world.job_module)
    _stand_down(world, monkeypatch)

    await _run_job()

    assert world.messages == [], (
        f"a stood-down pass reported the empty-identifier finding: {world.messages!r}"
    )

    # The control, in the same test: the identical state on a ready pass
    # reports. Without it, "nothing is reported" holds against a system that
    # reports nothing ever.
    _install_playbook_read(world.job_module, monkeypatch, refusing_with=None)
    await _run_job()
    assert len(world.messages) == 1, (
        "the same empty identifier is not reported on a ready pass either, "
        "so the stand-down assertion above establishes nothing"
    )


async def test_a_stood_down_pass_performs_no_check(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A stood-down pass performs no check.

    WHEN the passes stand down because the playbook cannot hold a launch
    THEN no read of the folder's Custom Fields is made and no gap is
    reported.

    "A stood-down pass declines the whole pass and SHALL reach ClickUp for
    nothing at all, this check included."

    The control against vacuity is
    `test_clickup_sync_job_stand_down.py::test_a_ready_playbook_restores_the_passes`,
    which establishes that these same fixtures let the passes run when the
    playbook is ready; it is not duplicated here. Every other test in this
    file is a second control, since each makes the read under the ready
    playbook this fixture installs by default.
    """
    world.folder_read.fields = (_gate_field(()), _discipline_field(()))
    _stand_down(world, monkeypatch)

    await _run_job()

    assert world.folder_read.calls == [], (
        f"a stood-down pass read the folder's fields: {world.folder_read.calls!r}"
    )
    assert world.messages == []

    # The control, in the same test rather than only by reference: the same
    # folder, read on a ready pass, produces both a read and a report.
    _install_playbook_read(world.job_module, monkeypatch, refusing_with=None)
    await _run_job()
    assert world.folder_read.calls == [FOLDER_ID], (
        "a ready pass made no folder read either, so the stand-down "
        "assertion above establishes nothing"
    )
    assert len(world.messages) == 1


async def test_a_stood_down_pass_writes_no_value(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario (from *A projected task carries its step's gate and
    discipline as Custom Field values*): A stood-down pass writes no value.

    WHEN the passes stand down because the playbook cannot hold a launch
    THEN no Custom Field value is written on any task of any launch.

    Covered here rather than at the projection level for the reason
    `test_clickup_sync_job_tag_stand_down.py` records for its predecessor:
    the stand-down happens in the job, which declines before the pass body
    is entered, so `converge_launch` has no stand-down state to be tested
    in. What this adds over "neither pass ran" is a Custom Field **backfill
    placed in the job body itself** -- a loop over mapped tasks written
    outside `converge_launch`, which would run whether or not the passes
    did. That is a plausible shape for a one-off backfill, and it is the
    failure mode the strict spy below exists for.
    """
    written: list[tuple[str, str, Any]] = []

    async def _spy(task_id: str, field_id: str, value: Any) -> None:
        written.append((task_id, field_id, value))

    monkeypatch.setattr(clickup_client, "set_task_field", _spy, raising=False)
    # A `converge_launch` that writes one value per launch, so "no value was
    # written" is read against fixtures under which values plainly are. The
    # real pass's own writing is covered at the projection level; what is
    # modelled here is only that writing happens inside the pass.
    monkeypatch.setattr(
        world.job_module, "converge_launch", _WritingPass(world.timeline)
    )

    await _run_job()
    assert written, (
        "the control pass wrote nothing on a ready run, so the stand-down "
        "assertion below would establish nothing"
    )

    written.clear()
    _stand_down(world, monkeypatch)

    await _run_job()

    assert written == [], (
        f"a Custom Field value was written during a stand-down: {written!r}"
    )


async def test_options_declared_out_of_the_playbooks_order_are_a_gap(
    world: _World,
) -> None:
    """Scenario: Options declared out of the playbook's order are a gap.

    WHEN a pass runs and the gate field declares an option naming every
    gate, but not in the playbook's gate-sequence order
    THEN the gap is reported, naming the order found
    AND it is reported even though no gate is missing an option.

    The clause every other check passes on: "a field naming all eight gates
    in the wrong sequence produces a view that reads as meaninglessly as the
    tags it replaced, silently and permanently". It is also what a hand
    repair creates, since an appended option lands last.
    """
    declared = (
        "commit",
        "order",
        "stock-ready",  # moved ahead of `listable`
        "listable",
        "live",
        "ignition",
        "phase-one-complete",
        "graduated",
    )
    world.folder_read.fields = (_gate_field(declared), _discipline_field())

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: naming the order found, "so the repair is a reordering
    # someone can perform rather than a fault they have to reconstruct".
    # Asserted as the observed sequence appearing in order in the message,
    # which pins no formatting.
    positions = _positions(message, list(declared))
    assert all(position >= 0 for position in positions), (
        "the report does not name every option the field declares, so the "
        f"order found is not readable from it: {message!r}"
    )
    assert positions == sorted(positions), (
        "the report names the options, but not in the order the field "
        f"declares them, so it does not name the order found: {message!r}"
    )
    # SPECIFIED: reported even though no gate is missing an option -- the
    # message must not be a missing-option report.
    assert len(world.messages) == 1


async def test_options_the_playbook_does_not_know_are_not_an_order_gap(
    world: _World,
) -> None:
    """Scenario: Options the playbook does not know are not an order gap.

    WHEN the gate field declares an option for every gate in playbook order,
    and additionally declares options naming no gate at all
    THEN no gap is reported
    AND the extra options are neither reported nor written to any task.

    The extras are interleaved rather than appended, so an implementation
    that judged the order over *every* option rather than over the gate
    options alone fails here.
    """
    declared: list[str] = []
    for gate in SPECIFIED_GATE_ORDER:
        declared.append(gate)
        declared.append(f"{gate}-internal-note")
    world.folder_read.fields = (_gate_field(declared), _discipline_field())

    await _run_job()

    # SPECIFIED: no gap is reported.
    assert world.messages == [], (
        f"options the playbook does not know were reported as a gap: {world.messages!r}"
    )
    # SPECIFIED: the gate field is still written to, so this is a pass that
    # accepted the configuration rather than one that withheld it.
    assert GATE_FIELD_ID in _writable_fields(world)


async def test_missing_gates_are_one_gap_not_two(world: _World) -> None:
    """Scenario: Missing gates are one gap, not two.

    WHEN the gate field declares options for only some gates, and those it
    does declare are in playbook order relative to one another
    THEN the missing gates are reported
    AND no order gap is reported alongside them.

    DERIVED: that an order finding is recognisable by the word "order" or
    "sequence". The delta requires an order finding to "name the order
    found", so a report carrying one must say something about order; that
    is the only handle a message-level assertion has here. The comparison
    against `test_options_declared_out_of_the_playbooks_order_are_a_gap`'s
    message is the check that the word is in fact the implementation's.
    """
    declared = ("commit", "listable", "live", "graduated")
    world.folder_read.fields = (_gate_field(declared), _discipline_field())

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: the missing gates are reported.
    for missing in ("order", "stock-ready", "ignition", "phase-one-complete"):
        assert missing in message, f"the report does not name {missing!r}: {message!r}"
    # SPECIFIED: no order gap alongside them. `order` is itself a gate
    # identifier here, so the word is looked for in a form that cannot be
    # the gate: an order finding names the order *found*, so it would carry
    # the declared options in their declared sequence.
    positions = _positions(message, list(declared))
    assert not (
        all(position >= 0 for position in positions) and positions == sorted(positions)
    ), (
        "the report names the field's declared options in their declared "
        "sequence, which is an order finding; the delta withholds one where "
        f"options are merely missing: {message!r}"
    )


async def test_a_duplicate_withholds_the_order_finding(world: _World) -> None:
    """Scenario: A duplicate withholds the order finding.

    WHEN a pass runs and the gate field declares two options named for the
    same gate, and its gate options are also out of playbook order
    THEN the duplicate is reported
    AND no order gap is reported alongside it, since the order cannot be
    judged until the duplicate is resolved.

    "Reporting an order that may be an artefact of the duplicate would name
    a repair that is not yet the right one."
    """
    declared = (
        "commit",
        "order",
        "stock-ready",
        "listable",
        "listable",
        "live",
        "ignition",
        "phase-one-complete",
        "graduated",
    )
    world.folder_read.fields = (_gate_field(declared), _discipline_field())

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: the duplicate is reported.
    assert "listable" in message
    # SPECIFIED: no order gap alongside it -- the report does not lay the
    # declared options out in their declared sequence, which is what naming
    # the order found looks like.
    positions = _positions(message, ["commit", "order", "stock-ready", "live"])
    assert not (
        all(position >= 0 for position in positions) and positions == sorted(positions)
    ), (
        "an order finding was composed alongside a duplicate; the order "
        f"cannot be judged until the duplicate is resolved: {message!r}"
    )


# ---------------------------------------------------------------------------
# Reporting halves of *A projected task carries its step's gate and
# discipline as Custom Field values*
# ---------------------------------------------------------------------------


async def test_an_option_differing_only_in_wording_is_reported_as_no_match(
    world: _World,
) -> None:
    """Scenario: An option differing only in wording is not a match -- the
    reporting half.

    WHEN the gate field declares an option whose name differs from a gate
    identifier by case or spacing
    THEN the gate is reported as having no matching option.

    Three near-misses in one field, because the requirement names three
    kinds -- case, spacing and wording -- and a rule matching on a folded
    or stripped string would resolve one of them and pass a test carrying
    only the others.
    """
    declared = [
        "commit",
        "Order",  # case
        " listable ",  # spacing
        "stock ready",  # wording
        "live",
        "ignition",
        "phase-one-complete",
        "graduated",
    ]
    world.folder_read.fields = (_gate_field(declared), _discipline_field())

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: each near-missed gate is reported as having no matching
    # option -- "the match SHALL be exact on the identifier string".
    for gate in ("order", "listable", "stock-ready"):
        assert gate in message, (
            f"the gate {gate!r} was not reported as having no matching "
            f"option, so a near-miss was treated as a match: {message!r}"
        )
    # SPECIFIED: the report names what the field does declare.
    assert "Order" in message or "stock ready" in message, (
        "the report does not name what the field does declare, so a "
        f"hand-typed mismatch is not diagnosable: {message!r}"
    )


async def test_a_deployment_configuring_no_field_makes_no_report(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A deployment configuring no field writes none -- the
    reporting half.

    WHEN a pass runs in a deployment that configures neither field
    identifier
    THEN no configuration report is made.

    "A deployment that names no field has declined that field rather than
    misconfigured it." `tasks.md` 4.3a additionally requires no read at all
    in that state.

    The control against vacuity: the folder is loaded with a gap that every
    other test here reports, so a silent pass is a decline rather than a
    check that finds nothing.
    """
    monkeypatch.delenv("CLICKUP_GATE_FIELD_ID", raising=False)
    monkeypatch.delenv("CLICKUP_DISCIPLINE_FIELD_ID", raising=False)
    _clear_settings_cache(world.job_module)
    world.folder_read.fields = (_gate_field(()), _discipline_field(()))

    await _run_job()

    # SPECIFIED: no report.
    assert world.messages == [], (
        f"a deployment that declined both fields was reported on: {world.messages!r}"
    )
    # `tasks.md` 4.3a: and no read is made.
    assert world.folder_read.calls == []
    # The pass is otherwise untouched.
    assert _walked(world) == list(WALK)

    # The control, in the same test: the identical folder, with the two
    # identifiers configured, is read and reported on. Without it, "no
    # report" holds against a system with no check at all.
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", GATE_FIELD_ID)
    monkeypatch.setenv("CLICKUP_DISCIPLINE_FIELD_ID", DISCIPLINE_FIELD_ID)
    _clear_settings_cache(world.job_module)
    await _run_job()
    assert world.folder_read.calls == [FOLDER_ID], (
        "no read is made even with both identifiers configured, so the "
        "decline assertion above establishes nothing"
    )
    assert len(world.messages) == 1


async def test_a_deployment_configuring_one_field_reports_only_that_one(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A deployment configuring one field records only that one --
    the reporting half.

    WHEN a pass runs in a deployment that configures the gate field's
    identifier and not the discipline field's
    THEN nothing about the discipline field is reported.

    "Silence therefore means 'not asked for' and a report means 'asked for
    and broken', for each field separately." The discipline field in the
    folder declares no option at all, so a check that assessed it anyway
    would have plenty to say.
    """
    monkeypatch.delenv("CLICKUP_DISCIPLINE_FIELD_ID", raising=False)
    _clear_settings_cache(world.job_module)
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(()),
    )

    await _run_job()

    message = _only_report(world)
    # SPECIFIED: the configured field is reported on...
    assert "live" in message
    # ...and nothing about the other is.
    assert DISCIPLINE_FIELD_ID not in message, (
        f"an unconfigured field was reported on: {message!r}"
    )
    named_disciplines = [name for name in DISCIPLINES if name in message.lower()]
    assert not named_disciplines, (
        "an unconfigured field's options were reported on: "
        f"{named_disciplines} in {message!r}"
    )


async def test_an_empty_identifier_is_reported_as_configured_with_no_value(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A field identifier configured but empty is a gap -- the
    reporting half.

    WHEN a pass runs in a deployment where a field's identifier is present
    but empty
    THEN that field is reported as configured with no value, rather than
    treated as declined.

    Asserted as a **comparison**, which pins no vocabulary: the message an
    empty identifier produces must differ from the one an absent field
    produces, since "the two call for different repairs, and reporting a
    rendering mistake as a missing field sends someone looking in the wrong
    place". The absent-field message is produced by the second pass below,
    against a deployment that did configure the identifier.
    """
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", "")
    _clear_settings_cache(world.job_module)
    world.folder_read.fields = (_discipline_field(),)

    await _run_job()
    empty_message = _only_report(world)

    # SPECIFIED: not treated as declined -- something was reported at all.
    assert "gate" in empty_message.lower()

    # The same folder, with the identifier actually configured: the field is
    # then absent rather than empty.
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", GATE_FIELD_ID)
    _clear_settings_cache(world.job_module)
    world.notifier.messages.clear()
    world.store.row = None
    await _run_job()
    absent_message = _only_report(world)

    # SPECIFIED: reported as configured with no value, never as absent.
    assert empty_message != absent_message, (
        "a field configured with no value and a field the folder does not "
        "include produced the same report; the delta requires them to be "
        "distinguishable, because they call for different repairs"
    )


# ---------------------------------------------------------------------------
# Report once, and lift it when the configuration changes
# ---------------------------------------------------------------------------


async def test_a_continuing_gap_is_reported_once(world: _World) -> None:
    """Scenario: A continuing gap is reported once.

    WHEN a gap is reported on one pass and the same gap still stands on the
    next
    THEN no second report is made.

    "A misconfiguration left in place over days produces one message rather
    than a wall of identical ones that trains the team to ignore the
    channel."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )

    await _run_job()
    assert len(world.messages) == 1, "the first pass did not report the gap"

    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 1, (
        f"the same standing gap was reported twice: {world.messages!r}"
    )


async def test_a_continuing_gap_is_reported_once_across_a_restart(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A continuing gap is reported once across a restart.

    WHEN a gap is reported, the process running the pass restarts, and the
    same gap still stands
    THEN no second report is made.

    A restart is modelled by replacing every in-process fake **except the
    suppression record**, which is what survives one: `tasks.md` 5.1 and
    `report-overdue-scheduled-runs` both require the retention to be
    durable, "so a worker restart does not resume the flood". An
    implementation holding suppression in memory passes
    `test_a_continuing_gap_is_reported_once` and fails here.
    """
    gap = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.folder_read.fields = gap

    await _run_job()
    assert len(world.messages) == 1

    # The restart: fresh in-process state, the same durable record.
    restarted_timeline = _Timeline()
    restarted_notifier = _FakeNotifier(restarted_timeline)
    restarted_read = _FolderRead(restarted_timeline)
    restarted_read.fields = gap
    _install_notifier(world.job_module, monkeypatch, restarted_notifier)
    _install_folder_read(world.job_module, monkeypatch, restarted_read)
    for name in PASS_NAMES:
        monkeypatch.setattr(world.job_module, name, _Pass(name, restarted_timeline))

    await _run_job()

    _require_store_used(world)
    assert restarted_read.calls == [FOLDER_ID], (
        "the restarted pass made no folder read, so nothing here says the "
        "gap still stood"
    )
    assert restarted_notifier.messages == [], (
        "a restart resumed the flood; suppression must survive one: "
        f"{restarted_notifier.messages!r}"
    )


async def test_a_stand_down_does_not_lift_suppression(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A stand-down does not lift suppression.

    WHEN a gap is reported, a later pass stands down because the playbook
    cannot hold a launch, and a pass afterwards finds the same gap standing
    THEN no second report is made.

    "A stand-down is not a withdrawal of the capability and says nothing
    about the configuration: lifting on one would make a deployment whose
    playbook moves in and out of readiness report the same unrepaired gap on
    every ready pass."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )

    await _run_job()
    assert len(world.messages) == 1

    _stand_down(world, monkeypatch)
    await _run_job()
    # SPECIFIED, by the same clause: the stood-down pass clears nothing.
    assert world.store.clears == 0, (
        "a stand-down cleared the suppression record; it says nothing about "
        "the configuration"
    )

    _install_playbook_read(world.job_module, monkeypatch, refusing_with=None)
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 1, (
        "a playbook flapping in and out of readiness re-reported the same "
        f"unrepaired gap: {world.messages!r}"
    )


async def test_an_undelivered_report_leaves_the_gap_eligible(world: _World) -> None:
    """Scenario: An undelivered report leaves the gap eligible.

    WHEN a gap is found and the report cannot be delivered to Slack
    THEN no suppression is retained and the gap is reported again on the
    next pass
    AND nothing about the failed delivery causes the run to be recorded as
    failed.

    "The record that suppresses further reports SHALL be written only after
    a report has been delivered successfully."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.notifier.refuse = True

    # SPECIFIED: the run is not recorded as failed.
    await _run_job()

    # SPECIFIED: no suppression is retained.
    assert world.store.writes == [], (
        "suppression was written for a report that was never delivered, "
        "which silences the gap permanently"
    )
    # SPECIFIED: the pass continues -- delivery sits on the pre-walk path.
    assert _walked(world) == list(WALK)

    # SPECIFIED: the gap is reported again on the next pass.
    world.notifier.refuse = False
    await _run_job()
    assert len(world.messages) == 1, (
        "a transient failure of the reporting channel silenced the gap: "
        f"{world.messages!r}"
    )


async def test_a_repaired_configuration_lifts_suppression(world: _World) -> None:
    """Scenario: A repaired configuration lifts suppression.

    WHEN a reported gap is repaired, a pass finds no gap, and a gap appears
    again afterwards
    THEN the later gap is reported.
    """
    gap = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.folder_read.fields = gap

    await _run_job()
    assert len(world.messages) == 1

    world.folder_read.fields = _well_formed()
    await _run_job()
    assert len(world.messages) == 1, "a repaired configuration was reported on"

    world.folder_read.fields = gap
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 2, (
        "a gap appearing again after a repair was suppressed as though it "
        f"were the gap already reported: {world.messages!r}"
    )


async def test_opting_out_lifts_suppression(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Opting out lifts suppression.

    WHEN a gap is reported, both field identifiers are then unconfigured,
    and a later deployment configures them again with the same gap standing
    THEN the gap is reported again.

    Without this, the design's own rollback -- unset both variables --
    leaves a row standing that nothing will ever clear, so opting back in
    later with the same unrepaired gap finds a matching identity and reports
    nothing: silence meaning "broken", which is the one thing this whole
    requirement exists to prevent.
    """
    gap = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.folder_read.fields = gap

    await _run_job()
    assert len(world.messages) == 1

    monkeypatch.delenv("CLICKUP_GATE_FIELD_ID", raising=False)
    monkeypatch.delenv("CLICKUP_DISCIPLINE_FIELD_ID", raising=False)
    _clear_settings_cache(world.job_module)
    await _run_job()
    assert len(world.messages) == 1, "a withdrawn capability was reported on"

    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", GATE_FIELD_ID)
    monkeypatch.setenv("CLICKUP_DISCIPLINE_FIELD_ID", DISCIPLINE_FIELD_ID)
    _clear_settings_cache(world.job_module)
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 2, (
        "opting back in with the same unrepaired gap standing met silence; "
        "a withdrawal must lift suppression"
    )


async def test_a_changed_gap_is_reported_again(world: _World) -> None:
    """Scenario: A changed gap is reported again.

    WHEN a gap is reported, and a later pass finds a gap naming a different
    set of missing options
    THEN the later gap is reported rather than suppressed.

    "A gap that grows or changes names a repair nobody has been asked for
    yet, so it must be reported."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    await _run_job()
    assert len(world.messages) == 1

    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g not in {"live", "ignition"}]),
        _discipline_field(),
    )
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 2, (
        f"a changed gap was suppressed as though it were the one already reported: "
        f"{world.messages!r}"
    )
    assert "ignition" in world.messages[1]


async def test_a_gap_repaired_into_a_different_gap_is_reported_again(
    world: _World,
) -> None:
    """Scenario: A gap repaired into a different gap is reported again.

    WHEN a wrong-typed gate field is reported, then replaced by a drop-down
    whose gate options are out of playbook order
    THEN the order gap is reported, rather than suppressed as the gap
    already reported.

    This is what forces identity over the **whole finding**: seven of the
    eight gap kinds name nothing missing, so an identity over missing
    options alone would make a wrong-typed field and a wrongly-ordered one
    indistinguishable, and this repair would meet silence.
    """
    world.folder_read.fields = (
        _gate_field(field_type=MULTI_SELECT),
        _discipline_field(),
    )
    await _run_job()
    assert len(world.messages) == 1

    world.folder_read.fields = (
        _gate_field(
            (
                "commit",
                "order",
                "stock-ready",
                "listable",
                "live",
                "ignition",
                "phase-one-complete",
                "graduated",
            )
        ),
        _discipline_field(),
    )
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 2, (
        "a wrong-typed field repaired into a wrongly-ordered one met "
        "silence; the identity must be taken over the whole finding, not "
        "over the missing options alone"
    )


async def test_reordering_options_during_a_duplicate_does_not_re_report_it(
    world: _World,
) -> None:
    """Scenario: Reordering options during a duplicate does not re-report it.

    WHEN a duplicate on the gate field is reported, and a later pass finds
    the same duplicate with that field's options reordered
    THEN no second report is made, since neither the order kind nor the
    order observed entered that field's identity.
    """
    first = (
        "commit",
        "order",
        "listable",
        "listable",
        "stock-ready",
        "live",
        "ignition",
        "phase-one-complete",
        "graduated",
    )
    reordered = (
        "graduated",
        "commit",
        "listable",
        "order",
        "listable",
        "live",
        "stock-ready",
        "ignition",
        "phase-one-complete",
    )
    world.folder_read.fields = (_gate_field(first), _discipline_field())
    await _run_job()
    assert len(world.messages) == 1

    world.folder_read.fields = (_gate_field(reordered), _discipline_field())
    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 1, (
        "shuffling options while an unrepaired duplicate stood re-reported "
        f"it: {world.messages!r}"
    )


async def test_an_empty_identifier_report_on_a_read_less_pass_is_suppressed(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An empty-identifier report on a read-less pass is
    suppressed like any other.

    WHEN an empty identifier is reported on a pass whose folder read did not
    complete, and the next pass finds the same state
    THEN no second report is made.

    "Withholding it because the pass made no read would deliver that same
    message on every pass for as long as the reachability fault lasted,
    which is the flood this rule forbids."
    """
    monkeypatch.setenv("CLICKUP_GATE_FIELD_ID", "")
    _clear_settings_cache(world.job_module)
    world.folder_read.raises = RuntimeError("ClickUp is unreachable")

    await _run_job()
    assert len(world.messages) == 1, "the empty identifier was not reported at all"

    await _run_job()

    _require_store_used(world)
    assert len(world.messages) == 1, (
        "the empty-identifier finding repeated on every pass of a "
        f"reachability outage: {world.messages!r}"
    )


# ---------------------------------------------------------------------------
# The suppression record's own failures
# ---------------------------------------------------------------------------


async def test_a_failure_of_the_suppression_record_costs_only_the_field_values(
    world: _World,
) -> None:
    """Scenario: A failure of the suppression record costs only the field
    values.

    WHEN the record that suppresses repeated reports cannot be read or
    written, and the store it lives in is left in a state where the
    launches' writes can still be recorded
    THEN every launch is still projected, corrected and reconciled
    AND nothing about the failure causes the run to be recorded as failed.

    The record "sits on the pre-walk path, ahead of every launch, so a fault
    there would otherwise abort a pass before any launch was projected -- a
    fault wholly inside this concern costing the projection and the
    completion intake of every launch, which the guarantee forbids."

    "Left in a state where the launches' writes can still be recorded" is
    modelled as the session's restore succeeding, which is what the
    following scenario inverts.
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.store.fail_read = RuntimeError("the suppression record cannot be read")
    world.store.fail_write = RuntimeError("the suppression record cannot be written")

    # SPECIFIED: the run is not recorded as failed.
    await _run_job()

    # The control: the record was actually reached, and failed. Without it,
    # every assertion here holds against a pass that keeps no record.
    _require_store_used(world)
    assert world.store.reads or world.store.writes, (
        "neither a read nor a write of the suppression record was attempted"
    )
    # SPECIFIED: every launch is still projected, corrected and reconciled.
    assert _walked(world) == list(WALK)
    assert world.passes["reconcile_launch"].seen == list(WALK)


async def test_a_failed_suppression_read_and_a_failed_write_after_delivery_differ(
    world: _World,
) -> None:
    """Scenario: A failed suppression read and a failed write after delivery
    differ.

    WHEN the suppression record cannot be **read** on a pass
    THEN no gap is reported on that pass, since a standing gap cannot be
    told from a new one
    AND WHEN on a later pass a gap is reported and the suppression record
    cannot then be **written**
    THEN the gap remains eligible and is reported again on the pass after.

    The two must not be conflated: "a repeated message is a nuisance, while
    a gap silenced permanently is the failure this requirement exists to
    prevent."
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )

    # A failed read: no report on that pass.
    world.store.fail_read = RuntimeError("the suppression record cannot be read")
    await _run_job()
    _require_store_used(world)
    assert world.messages == [], (
        "a gap was reported on a pass that could not tell a standing gap "
        f"from a new one: {world.messages!r}"
    )

    # A failed write after a delivered report: the gap stays eligible.
    world.store.fail_read = None
    world.store.fail_write = RuntimeError("the suppression record cannot be written")
    await _run_job()
    assert len(world.messages) == 1, "the gap was not reported once the read recovered"

    world.store.fail_write = None
    await _run_job()
    assert len(world.messages) == 2, (
        "a report whose suppression could not be written silenced the gap; "
        "it must remain eligible, since the report has already gone out and "
        "cannot be recalled"
    )


async def test_a_store_this_concern_cannot_restore_ends_the_walk(
    world: _World,
) -> None:
    """Scenario: A store this concern cannot restore ends the walk.

    WHEN an access of the suppression record fails on a store shared with
    the launches' writes, and the restore of that store before the first
    launch itself fails
    THEN no launch is attempted
    AND the run is recorded as failed.

    The one path on which a fault of this concern costs more than the field
    values: "continuing against a store that cannot record is worse than not
    continuing", on the ground
    *One launch's failure does not stop the other launches being converged*
    gives for a failed recovery between launches, extended here to the
    pre-walk restore.

    The restore is modelled as the shared session's `rollback()`, which is
    what that requirement's own *A contained failure rolls the session back*
    fixes and what
    `test_clickup_sync_job_containment.py::test_a_failure_of_the_recovery_between_launches_ends_the_walk`
    already drives.
    """
    world.folder_read.fields = (
        _gate_field([g for g in SPECIFIED_GATE_ORDER if g != "live"]),
        _discipline_field(),
    )
    world.store.fail_read = RuntimeError("the shared session is unusable")
    world.session.rollback_error = RuntimeError("the restore itself failed")

    # SPECIFIED: the run is recorded as failed.
    with pytest.raises(Exception):  # noqa: B017 -- no type is specified
        await _run_job()

    _require_store_used(world)
    # SPECIFIED: no launch is attempted.
    assert _walked(world) == [], (
        "a launch was projected against a store that cannot record its "
        f"writes: {_walked(world)!r}"
    )
    assert world.passes["reconcile_launch"].seen == []


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Which Slack channel the report reaches. The requirement says "the team's
#   Slack channel", and the channel is `MonitoringNotifier`'s own concern --
#   `product-monitoring` owns it and `test_monitoring_notifier_port.py`
#   covers the wiring. Asserting a channel identifier here would test that
#   capability through this one.
# - The `when` half of the suppression row (`tasks.md` 5.1 -- "the identity
#   of the last gap reported, **and when**"). No scenario turns on the
#   timestamp; it is written for diagnosis, and the report-once behaviour is
#   decided by the identity alone.
# - The migration that creates the suppression table (`tasks.md` 5.1). It is
#   schema, driven in the integration tier by `tasks.md` 7.6, and a unit
#   test over a substituted store establishes nothing about it.
# - That `import-linter` still passes with the pass reaching
#   `MonitoringNotifier` in `shared.application` (`tasks.md` 7.8). That is a
#   structural gate the project runs directly, not a scenario.
# ---------------------------------------------------------------------------
