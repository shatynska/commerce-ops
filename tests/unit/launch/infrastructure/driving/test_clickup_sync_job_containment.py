"""One launch's failure is contained to that launch, and the run still fails.

Derived strictly from the delta spec of the OpenSpec change
`contain-a-failing-launch`:
`openspec/changes/contain-a-failing-launch/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *One launch's failure does not stop the
other launches being converged*:

- *A launch that fails does not stop the launches after it*
- *Each contained failure is reported against its own launch*
- *A run carrying a failed launch is reported as failed*
- *A run in which every launch succeeds is reported as succeeded*
- *A stand-down is not a contained failure*
- *A launch whose projection failed is not reconciled on that run*
- *A completion withheld by a skipped reconciliation is recorded later*
- *A failure of the recovery between launches ends the walk*
- *A cancelled pass stops rather than containing the cancellation*
- *Missing folder configuration is not turned into a skip*

And, from the MODIFIED requirement *The reconciliation pass records
completions and reopenings the webhook missed*, the one scenario the delta
adds to it:

- *A launch whose projection failed is left unreconciled and unobserved*

Two scenarios of the ADDED requirement are **not** here and are driven in
`tests/integration/launch/test_clickup_sync_job_containment_live.py`
instead, for the reason `tasks.md` 1.2 states: *A partially projected
launch keeps what its failed attempt achieved* and *A launch attempted
after one that failed on the database is unaffected by it* both turn on a
real transaction, and a fake that models none passes them whether or not
the rollback was implemented. One scenario is in a third file,
`test_clickup_webhook_intake_unaffected_by_a_failing_pass.py`: *A webhook
delivery still records for a launch whose projection is failing* is stated
over an HTTP delivery and is only observable at the route.

See `openspec/changes/contain-a-failing-launch/test-manifest.md` for the
full accounting.

## Level

The job body. The subject of every scenario here is the *walk* across
launches, which `design.md` places in `clickup_sync_job` and nowhere else:
the two pass functions each take one launch and do not know other launches
exist. Nothing below the job can observe "the walk continued", and the
run's outcome has no signal below it either.

## Reading the outcome clauses

"Reported to the scheduled-work machinery as a failed run" is read as *the
job body raises*; "reported as succeeded" as *it returns normally*. The
same reading `test_clickup_sync_job_stand_down.py` already records for the
same words, and for the same reason: a job body's only outcome signal is
whether it raises.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that containment lives in the job's loop
around the `converge_launch` + `reconcile_launch` pair (`design.md` --
*Containment lives in the job's loop*); that the catch is `Exception` and
excludes `BaseException` (*Any exception is contained*); that the session
is rolled back between launches and that a raising rollback ends the walk
(*A contained failure rolls the session back*); that the aggregate names
each failed launch by **product identifier** (*The run fails after the
walk*); and that readiness stays above the loop (`design.md` -- Context).

INVENTED, each with a correction point named below:

- How the job is reached -- through the runner's periodic registry and the
  registered function's `__module__`, never by module path or task name.
  Transcribed from `test_clickup_sync_job_schedule.py` by way of
  `test_clickup_sync_job_stand_down.py`. Correction point:
  `_completion_periodic`.
- The collaborator names substituted on the job module: `converge_launch`,
  `reconcile_launch`, `LaunchRepository`, `PlaybookRepository`, and
  `session` / `transaction`. Each is probed and fails loudly rather than
  defaulting, so a differently-named collaborator cannot leave a test
  green against an unpatched real one. Correction points: `PASS_NAMES`,
  `passes`, `launches`, `install_playbook_read`, `shared_session`.
- How a launch is identified in a pass call -- `_product_of` scans the
  call's arguments for a `Launch` (or a bare `ProductId`) rather than
  assuming a parameter name or position.
- `PlaybookNotReadyError`'s constructor signature, probed the same four
  ways `test_clickup_sync_job_stand_down.py` probes it.
- That the contained failure is reported through the standard library's
  logging, which is the only report `design.md` names ("the message is the
  report ... each contained failure is additionally logged with its own
  traceback").

Correcting any of the above is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: which launches were attempted, what was recorded against them,
whether the job raised, and which product identifiers the raised error
names.

## Expected first-run state

`reconcile_clickup_completions` has no containment yet, so the walk abandons
on the first failure. Every test whose scenario states that the walk
continues, that each failure is reported, or that the aggregate names the
failed launches is expected to fail on a *wrong value* -- launches after
the failing one going unconverged -- not on an absent target.

Two tests here are expected to **pass** on their first run, and that is
not the alarm `ai-toolkit:testing` describes for a test written ahead of
its implementation. Each states behaviour this change must **preserve**
rather than introduce, so the current code already satisfies it and their
job is to catch containment reaching further than the requirement allows:

- `test_a_run_in_which_every_launch_succeeds_is_reported_as_succeeded`
- `test_a_stand_down_is_not_a_contained_failure`

Two further tests -- the withheld-completion one and the MODIFIED
requirement's *left unreconciled and unobserved* -- passed on their first
draft for a reason that was **not** the scenario they state: a pass that
abandons its walk also withholds, so their assertions held against the
abandonment this change removes. Each now asserts the premise its scenario
is stated over, that the failure was *contained* and the walk went on, and
each fails today on that assertion. Recorded here because the first draft
is exactly the fourth failure state `ai-toolkit:testing` names.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` -- 1114 passed, 0 failed;
`uv run pytest tests/integration` -- 93 passed, 2 skipped (both skips
pre-existing and unrelated).
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
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
from commerce_ops.launch.infrastructure.driven.clickup_sync import ClickUpSyncError
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

UNHELD_GATE: Final = "graduated"

#: Three launches, so "the walk continued" is distinguishable from "the
#: walk did one more thing": a failure in the middle has both a launch
#: before it and a launch after it.
FIRST: Final = ProductId(str(uuid.uuid4()))
SECOND: Final = ProductId(str(uuid.uuid4()))
THIRD: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FIRST, SECOND, THIRD)

#: The two pass functions the job drives, as
#: `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`
#: names them.
PASS_NAMES: Final = ("converge_launch", "reconcile_launch")

STEP_ID: Final = "listing.title-conforms"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


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
        "hazard": Hazard.NONE,
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
# Reaching the job
# ---------------------------------------------------------------------------


def _completion_periodic() -> Any:
    """The ClickUp completion pass, found by placement and subject."""
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


def _runner_app() -> Any:
    from commerce_ops.shared.infrastructure.driven.job_runner import app

    return app


def _job_module() -> ModuleType:
    return sys.modules[_completion_periodic().task.func.__module__]


async def _run_job() -> Any:
    """Invoke the job body the way the runner would."""
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
# Test doubles
# ---------------------------------------------------------------------------


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    """The launch a pass call is for, without assuming a call shape.

    Nothing in this change's artifacts fixes how the job passes a launch to
    the two passes, so the launch is *found* rather than read off a named
    parameter. Fails loudly rather than guessing, so a call this file
    cannot attribute never silently attributes to the wrong launch.
    """
    for candidate in (*args, *kwargs.values()):
        if isinstance(candidate, Launch):
            return candidate.product_id
        if isinstance(candidate, ProductId) and candidate in WALK:
            return candidate
        if isinstance(candidate, str) and candidate in {p.value for p in WALK}:
            return ProductId(candidate)
    pytest.fail(
        "a pass was called with no launch and no product identifier among "
        f"its arguments (args={args!r}, kwargs={kwargs!r}); correct "
        "`_product_of` to the implemented call shape"
    )


@dataclass
class _Timeline:
    """What happened, in the order it happened.

    Log records and pass calls land in one sequence, which is what makes
    "reported *as it happens*" assertable at all: a report that only
    appeared after the walk finished would satisfy a per-launch count while
    failing the requirement.
    """

    events: list[tuple[str, str]] = field(default_factory=list)

    def note(self, kind: str, detail: str) -> None:
        self.events.append((kind, detail))

    def index_of(self, kind: str, detail: str) -> int | None:
        for position, event in enumerate(self.events):
            if event == (kind, detail):
                return position
        return None

    @property
    def rendered(self) -> str:
        return "\n".join(f"{kind}: {detail}" for kind, detail in self.events)


class _TimelineHandler(logging.Handler):
    def __init__(self, timeline: _Timeline) -> None:
        super().__init__(level=logging.NOTSET)
        self._timeline = timeline
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        rendered = record.getMessage()
        if record.exc_info is not None and record.exc_info[1] is not None:
            rendered = f"{rendered} || {record.exc_info[1]!r}"
        self._timeline.note("log", rendered)


class _Pass:
    """Stands in for `converge_launch` / `reconcile_launch`.

    Records the launch it was called for, in order, and raises for whichever
    launches the test told it to fail on.
    """

    def __init__(
        self,
        name: str,
        timeline: _Timeline,
        failures: dict[ProductId, Any] | None = None,
    ) -> None:
        self.name = name
        self.timeline = timeline
        self.failures: dict[ProductId, Any] = dict(failures or {})
        self.seen: list[ProductId] = []

    def fail_for(self, product_id: ProductId, build: Any) -> None:
        self.failures[product_id] = build

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        self.seen.append(product_id)
        self.timeline.note(self.name, str(product_id))
        build = self.failures.get(product_id)
        if build is not None:
            raise build()


@dataclass
class _TaskState:
    """The one mapped task of one launch, as the reconciliation pass sees it.

    Modelled here rather than driven through the real pass because these
    tests are about the *walk*, not about the reconciliation: what they need
    is something whose retained observed state is consumed when the launch
    is reconciled and untouched when it is not. The real transition
    arithmetic is covered in
    `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`.
    """

    closed_in_clickup: bool = False
    last_observed_closed: bool = False
    recorded: list[str] = field(default_factory=list)


class _ObservingReconcile(_Pass):
    """`reconcile_launch`, standing in with the one behaviour these
    scenarios turn on: it observes the launch's task and records on a
    transition, so *being called at all* is what consumes the transition."""

    def __init__(
        self,
        timeline: _Timeline,
        world: dict[ProductId, _TaskState],
        failures: dict[ProductId, Any] | None = None,
    ) -> None:
        super().__init__("reconcile_launch", timeline, failures)
        self.world = world

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        await super().__call__(*args, **kwargs)
        state = self.world.get(product_id)
        if state is None:
            return
        if state.closed_in_clickup != state.last_observed_closed:
            state.recorded.append(
                "Satisfied" if state.closed_in_clickup else "InProgress"
            )
        state.last_observed_closed = state.closed_in_clickup


class _FakeSession:
    """The `AsyncSession` the walk shares, with only what the walk uses.

    `rollback()` is counted, and optionally raises -- which is what the
    *failure of the recovery* scenario needs.
    """

    def __init__(self, rollback_error: BaseException | None = None) -> None:
        self.rollbacks = 0
        self.commits = 0
        self._rollback_error = rollback_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self._rollback_error is not None:
            raise self._rollback_error

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        # `hold_launch_advance_lock` (`trigger-clickup-projection-on-
        # launch-events`) issues `SELECT pg_advisory_xact_lock(...)` and
        # discards the result; a no-op is all this fake needs to support.
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture()
def timeline() -> Iterator[_Timeline]:
    line = _Timeline()
    handler = _TimelineHandler(line)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield line
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


@pytest.fixture()
def log_records(timeline: _Timeline) -> list[logging.LogRecord]:
    """The records behind the timeline, for assertions about level and
    attached traceback rather than about order."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, _TimelineHandler):
            return handler.records
    pytest.fail("the timeline handler was not installed")


@pytest.fixture()
def shared_session(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> _FakeSession:
    """The session the walk shares, installed over the job's own provider.

    Installed under both spellings the module might use; at least one must
    exist, or the job would reach the real provider and this file would
    silently need a database.
    """
    return install_session(job_module, monkeypatch, _FakeSession())


def install_session(
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


@pytest.fixture()
def passes(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, timeline: _Timeline
) -> dict[str, _Pass]:
    """Both pass functions, substituted.

    Both are required, not merely one: the containment requirement
    distinguishes a launch whose *projection* raised from one whose
    reconciliation did, and a file that could not tell the two calls apart
    could not assert that distinction.
    """
    missing = [name for name in PASS_NAMES if not hasattr(job_module, name)]
    assert not missing, (
        f"{job_module.__name__} exposes none of {missing}; correct "
        "`PASS_NAMES` to the implemented collaborator names"
    )
    installed = {name: _Pass(name, timeline) for name in PASS_NAMES}
    for name, fake in installed.items():
        monkeypatch.setattr(job_module, name, fake)
    return installed


def install_reconcile(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    reconcile: _ObservingReconcile,
) -> _ObservingReconcile:
    monkeypatch.setattr(job_module, "reconcile_launch", reconcile)
    return reconcile


@pytest.fixture()
def launches(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_module,
        "LaunchRepository",
        lambda *a, **k: _FakeLaunches(tuple(_launch_for(product) for product in WALK)),
        raising=False,
    )


def install_playbook_read(
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


@pytest.fixture()
def ready(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    install_playbook_read(job_module, monkeypatch, refusing_with=None)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _identifier_text(product_id: ProductId) -> str:
    """The product identifier as it would appear in a message.

    The bare value rather than `str(product_id)`, so the assertion holds
    whichever of the two an implementation formats: `ProductId`\'s own
    `repr` contains the value, so the value is a substring of both.
    """
    return product_id.value


def _reports_naming(
    records: list[logging.LogRecord], product_id: ProductId
) -> list[logging.LogRecord]:
    identifier = _identifier_text(product_id)
    return [
        record
        for record in records
        if identifier in record.getMessage()
        or identifier in str(getattr(record, "args", ""))
    ]


def _carries_what_was_raised(record: logging.LogRecord, marker: str) -> bool:
    """Whether a report carries the exception it was raised for.

    Either shape counts: the message quoting it, or the record carrying
    `exc_info` (which is what `logger.exception` / `exc_info=True`
    produces, and what `design.md`'s "with its own traceback" describes).
    """
    if marker in record.getMessage():
        return True
    info = record.exc_info
    return info is not None and info[1] is not None and marker in repr(info[1])


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# converged
# ---------------------------------------------------------------------------


async def test_a_launch_that_fails_does_not_stop_the_launches_after_it(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A launch that fails does not stop the launches after it.

    WHEN the completion pass runs over several active launches and
    projecting or reconciling one of them raises
    THEN every other active launch is still converged and reconciled on
    that same run.

    Both halves are exercised in one run -- the second launch's projection
    raises and the first launch's reconciliation raises -- because the
    requirement names both ("raised while projecting or reconciling"), and
    a walk contained around only one of them would satisfy a test that
    provoked the other.
    """
    passes["converge_launch"].fail_for(
        SECOND, lambda: ClickUpSyncError("create_task -> 404 Not Found")
    )
    passes["reconcile_launch"].fail_for(
        FIRST, lambda: ClickUpSyncError("list_tasks -> 404 Not Found")
    )

    with pytest.raises(Exception):  # noqa: B017 -- outcome asserted below
        await _run_job()

    # SPECIFIED: every other active launch is still converged...
    assert passes["converge_launch"].seen == list(WALK), (
        "the walk did not converge every active launch; it converged "
        f"{passes['converge_launch'].seen}"
    )
    # ...and reconciled. The second launch is the one exception the
    # requirement states -- its projection raised, so it is not reconciled.
    assert passes["reconcile_launch"].seen == [FIRST, THIRD], (
        "the walk did not reconcile every launch whose projection stood; "
        f"it reconciled {passes['reconcile_launch'].seen}"
    )


async def test_each_contained_failure_is_reported_against_its_own_launch(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
    timeline: _Timeline,
    log_records: list[logging.LogRecord],
) -> None:
    """Scenario: Each contained failure is reported against its own launch.

    WHEN the walk contains failures for more than one launch on the same run
    THEN each is reported separately as it happens, naming the product its
    launch is for and carrying what was raised.

    "A walk that failed on three launches is required to say so three times
    rather than once" -- so the count, the attribution and the timing are
    each asserted, not just that something was logged.
    """
    markers = {
        FIRST: "first-launch-fault",
        SECOND: "second-launch-fault",
        THIRD: "third-launch-fault",
    }
    for product, marker in markers.items():
        passes["converge_launch"].fail_for(
            product, lambda marker=marker: ClickUpSyncError(marker)
        )

    with pytest.raises(Exception):  # noqa: B017 -- outcome asserted elsewhere
        await _run_job()

    for product, marker in markers.items():
        naming = _reports_naming(log_records, product)
        # SPECIFIED: each failure is reported separately, naming the
        # product its launch is for.
        assert naming, (
            f"no report named the product {product} whose launch failed; "
            f"the timeline was:\n{timeline.rendered}"
        )
        # SPECIFIED: carrying what was raised.
        assert any(_carries_what_was_raised(record, marker) for record in naming), (
            f"the report for product {product} carried nothing of what was "
            f"raised ({marker!r}); the timeline was:\n{timeline.rendered}"
        )

    # SPECIFIED: "as it happens" -- the first launch's failure is reported
    # before the second launch is attempted, rather than summarised after
    # the walk.
    first_report = next(
        position
        for position, (kind, detail) in enumerate(timeline.events)
        if kind == "log" and _identifier_text(FIRST) in detail
    )
    second_attempt = timeline.index_of("converge_launch", str(SECOND))
    assert second_attempt is not None
    assert first_report < second_attempt, (
        "the first launch's failure was not reported until after the walk "
        f"had moved on; the timeline was:\n{timeline.rendered}"
    )


async def test_a_run_carrying_a_failed_launch_is_reported_as_failed(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A run carrying a failed launch is reported as failed.

    WHEN the completion pass finishes its walk and at least one launch
    failed
    THEN the run is reported to the scheduled-work machinery as a failed run
    AND the error that fails the run names every launch that failed, by its
    product identifier.

    The launch that succeeded is asserted absent from the message too: an
    error that named every launch would satisfy "names every launch that
    failed" while telling the reader nothing.
    """
    passes["converge_launch"].fail_for(FIRST, lambda: ClickUpSyncError("first fault"))
    passes["reconcile_launch"].fail_for(THIRD, lambda: ClickUpSyncError("third fault"))

    # SPECIFIED: the run is reported as a failed run.
    with pytest.raises(Exception) as raised:
        await _run_job()

    message = str(raised.value)
    # SPECIFIED: the error names every launch that failed, by product
    # identifier.
    assert _identifier_text(FIRST) in message, (
        f"the run's error did not name the failed launch {FIRST}: {message!r}"
    )
    assert _identifier_text(THIRD) in message, (
        f"the run's error did not name the failed launch {THIRD}: {message!r}"
    )
    # DERIVED, from "the per-launch report is what makes a fault
    # diagnosable": naming a launch that did not fail would make the
    # aggregate useless for that purpose. No scenario states it.
    assert _identifier_text(SECOND) not in message, (
        f"the run's error named {SECOND}, whose launch did not fail: {message!r}"
    )


async def test_a_run_in_which_every_launch_succeeds_is_reported_as_succeeded(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A run in which every launch succeeds is reported as
    succeeded.

    WHEN the completion pass walks every active launch and none of them
    fails
    THEN the run is reported as succeeded.

    Expected to pass before the implementation lands (see the module
    docstring): it states what containment must not disturb.
    """
    # SPECIFIED: the run is reported as succeeded -- returning normally is
    # the assertion, so there is no `pytest.raises` here.
    await _run_job()

    # Guard: the walk really did run, so "it did not raise" cannot hold for
    # the wrong reason.
    assert passes["converge_launch"].seen == list(WALK)
    assert passes["reconcile_launch"].seen == list(WALK)


async def test_a_stand_down_is_not_a_contained_failure(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _Pass],
    launches: None,
    shared_session: _FakeSession,
    log_records: list[logging.LogRecord],
) -> None:
    """Scenario: A stand-down is not a contained failure.

    WHEN the pass runs while the served playbook cannot hold a launch
    THEN no launch is attempted and nothing is reported as a failed launch.

    The requirement's reason for this is a constraint on where readiness is
    read: "readiness is determined once, before the walk begins". A job
    that moved the serving read inside the loop would turn a stand-down
    into one contained failure per launch and a failed run -- which is what
    the two assertions below rule out, in that order.

    Expected to pass before the implementation lands (see the module
    docstring): readiness already sits above the loop, and this states that
    containment must leave it there.
    """
    install_playbook_read(job_module, monkeypatch, refusing_with=_unready_playbook())

    # SPECIFIED: a stand-down does not fail the run.
    await _run_job()

    # SPECIFIED: no launch is attempted.
    for name, fake in passes.items():
        assert fake.seen == [], (
            f"{name} was called during a stand-down, so a launch was "
            f"attempted: {fake.seen}"
        )
    # SPECIFIED: nothing is reported as a failed launch.
    for product in WALK:
        assert not _reports_naming(log_records, product), (
            f"a stand-down reported product {product} as a failed launch"
        )


async def test_a_launch_whose_projection_failed_is_not_reconciled_on_that_run(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A launch whose projection failed is not reconciled on that
    run.

    WHEN projecting a launch raises during the pass
    THEN that launch's reconciliation is not attempted on that run: no
    outcome is recorded for it and none of its tasks is observed
    AND the walk continues to the next launch.

    Both halves of "not attempted" are asserted -- that `reconcile_launch`
    was not called for it, and that its task's retained observed state is
    exactly as it was. The second is what the requirement forbids
    separating from the first: a variant that read the launch and declined
    to record would advance the state and consume the transition.
    """
    world = {
        product: _TaskState(closed_in_clickup=True, last_observed_closed=False)
        for product in WALK
    }
    reconcile = install_reconcile(
        job_module, monkeypatch, _ObservingReconcile(_Timeline(), world)
    )
    passes["converge_launch"].fail_for(
        SECOND, lambda: ClickUpSyncError("create_task -> 404 Not Found")
    )

    with pytest.raises(Exception):  # noqa: B017
        await _run_job()

    # SPECIFIED: that launch's reconciliation is not attempted.
    assert SECOND not in reconcile.seen, (
        f"a launch whose projection raised was reconciled anyway: {reconcile.seen}"
    )
    # SPECIFIED: no outcome is recorded for it, and none of its tasks is
    # observed.
    assert world[SECOND].recorded == []
    assert world[SECOND].last_observed_closed is False, (
        "the launch's retained observed state was advanced, so the "
        "transition its withheld completion depends on was consumed"
    )
    # SPECIFIED: the walk continues to the next launch.
    assert THIRD in reconcile.seen, (
        f"the walk did not continue past the failing launch: {reconcile.seen}"
    )
    # Guard: the model does record when a launch *is* reconciled, so the
    # assertions above cannot hold because nothing ever records.
    assert world[THIRD].recorded == ["Satisfied"]


async def test_a_completion_withheld_by_a_skipped_reconciliation_is_recorded_later(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A completion withheld by a skipped reconciliation is
    recorded later.

    WHEN a launch's task is closed in ClickUp and no webhook delivery for
    it arrives, while that launch's projection is failing on every run
    AND a later run projects the launch successfully and reconciles it, the
    task's step being one the loop still projects on that run
    THEN the completion is recorded then, from the transition the task's
    unchanged retained observed state still shows.

    This is the scenario that makes the skip a *delay* rather than a loss,
    so it is driven over two runs rather than asserted as a property of
    one: the first run withholds, the second records.
    """
    world = {SECOND: _TaskState(closed_in_clickup=True, last_observed_closed=False)}
    reconcile = install_reconcile(
        job_module, monkeypatch, _ObservingReconcile(_Timeline(), world)
    )

    # Run one: the launch's projection is failing.
    passes["converge_launch"].fail_for(
        SECOND, lambda: ClickUpSyncError("create_task -> 404 Not Found")
    )
    with pytest.raises(Exception):  # noqa: B017
        await _run_job()

    # SPECIFIED, as this scenario's premise rather than as its outcome: the
    # run it describes is one in which the failure was *contained*, not one
    # in which the walk abandoned. Without this the assertions below hold
    # against a pass that aborts on the first failure, which is exactly the
    # behaviour this change removes -- the scenario would then be satisfied
    # for a reason it does not state.
    assert reconcile.seen == [FIRST, THIRD], (
        "the run that withheld the completion did not contain the failure "
        f"and walk on; it reconciled {reconcile.seen}"
    )

    # SPECIFIED: nothing is recorded while the projection is failing, and
    # the transition still stands.
    assert world[SECOND].recorded == []
    assert world[SECOND].last_observed_closed is False

    # Run two: the launch projects successfully.
    passes["converge_launch"].failures.pop(SECOND)
    await _run_job()

    # SPECIFIED: the completion is recorded then, from the transition the
    # unchanged retained observed state still shows.
    assert world[SECOND].recorded == ["Satisfied"], (
        "the completion withheld by the skipped reconciliation was never "
        "recorded once the launch projected successfully"
    )
    assert reconcile.seen.count(SECOND) == 1


async def test_a_failure_of_the_recovery_between_launches_ends_the_walk(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
) -> None:
    """Scenario: A failure of the recovery between launches ends the walk.

    WHEN a launch's failure is contained and the database then becomes
    unusable in a way the pass cannot recover from before the next launch
    THEN no further launch is attempted
    AND the run is reported as a failed run, its error naming the launches
    contained before that point.

    The recovery is the session rollback `design.md` places between
    launches, so "a way the pass cannot recover from" is a rollback that
    itself raises.
    """
    unusable = RuntimeError("the connection is gone; rollback failed")
    session = install_session(job_module, monkeypatch, _FakeSession(unusable))
    passes["converge_launch"].fail_for(FIRST, lambda: ClickUpSyncError("first fault"))

    with pytest.raises(Exception) as raised:
        await _run_job()

    # SPECIFIED: no further launch is attempted.
    assert passes["converge_launch"].seen == [FIRST], (
        "the walk carried on past a recovery it could not perform, and "
        f"attempted {passes['converge_launch'].seen}"
    )
    assert passes["reconcile_launch"].seen == []
    # Guard: the recovery really was attempted, so "no further launch" is
    # not simply the walk never having reached it.
    assert session.rollbacks == 1, (
        "no rollback was attempted after the contained failure, so this "
        "test did not exercise the recovery at all"
    )

    message = str(raised.value)
    # SPECIFIED: the error names the launches contained before that point.
    assert _identifier_text(FIRST) in message, (
        f"the run's error did not name the launch contained before the "
        f"recovery failed: {message!r}"
    )
    # SPECIFIED: "those, rather than all that would have failed" -- the
    # launches never attempted are not named.
    assert (
        _identifier_text(SECOND) not in message
        and _identifier_text(THIRD) not in message
    ), f"the run's error named a launch that was never attempted: {message!r}"
    # DERIVED, from `design.md` -- *A contained failure rolls the session
    # back* ("raise the aggregate ... chained to it") and `tasks.md` 2.3.
    # No scenario states the chaining.
    chain: list[BaseException] = []
    current: BaseException | None = raised.value
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    assert unusable in chain, (
        "the run's error did not carry the rollback failure as its cause, "
        "so the reason the walk ended is nowhere in the record"
    )


async def test_a_cancelled_pass_stops_rather_than_containing_the_cancellation(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
    log_records: list[logging.LogRecord],
) -> None:
    """Scenario: A cancelled pass stops rather than containing the
    cancellation.

    WHEN the process running the pass is cancelled or shut down partway
    through the walk
    THEN the walk stops rather than continuing to the next launch
    AND nothing is reported as a failed launch on account of the
    cancellation.

    `asyncio.CancelledError` is a `BaseException`, which is exactly the
    distinction `design.md` rests this on ("`BaseException` is deliberately
    excluded"). The launch before the cancellation fails first, so the test
    also establishes that the launches contained before it still stand in
    their own reports.

    Expected to pass before the implementation lands (see the module
    docstring): with no containment at all, nothing is contained either.
    Its job is to catch a containment written too broadly.
    """
    passes["converge_launch"].fail_for(FIRST, lambda: ClickUpSyncError("first fault"))
    passes["converge_launch"].fail_for(SECOND, asyncio.CancelledError)

    # SPECIFIED: the cancellation is left to propagate.
    with pytest.raises(asyncio.CancelledError):
        await _run_job()

    # SPECIFIED: the walk stops rather than continuing to the next launch.
    assert THIRD not in passes["converge_launch"].seen, (
        "the walk continued past a cancellation, and attempted "
        f"{passes['converge_launch'].seen}"
    )
    # SPECIFIED: nothing is reported as a failed launch on account of the
    # cancellation.
    assert not _reports_naming(log_records, SECOND), (
        "the cancellation was reported against the product whose launch was "
        "being walked when the process was stopped"
    )
    # SPECIFIED: "the launches contained before it stand in their own
    # reports".
    assert _reports_naming(log_records, FIRST), (
        "the launch contained before the cancellation lost its own report"
    )


async def test_missing_folder_configuration_is_not_turned_into_a_skip(
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: Missing folder configuration is not turned into a skip.

    WHEN the completion pass runs, several active launches need lists, and
    no parent folder is configured
    THEN each such launch is attempted and fails, rather than being skipped.

    The unconfigured-folder check is raised from inside projection, per
    launch (`design.md` -- Context), so the condition is modelled here as
    every launch's projection raising it. The behavioural half -- that
    `converge_launch` raises when no folder is configured -- is already
    covered by
    `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_missing_folder_configuration_fails_the_run`;
    what is asserted here is only what the walk does with it.
    """
    for product in WALK:
        passes["converge_launch"].fail_for(
            product, lambda: ClickUpSyncError("no ClickUp parent folder is configured")
        )

    with pytest.raises(Exception) as raised:
        await _run_job()

    # SPECIFIED: each such launch is attempted...
    assert passes["converge_launch"].seen == list(WALK), (
        "a launch was skipped rather than attempted and failed: "
        f"{passes['converge_launch'].seen}"
    )
    # ...and fails. The run fails naming all three, which is "it does not
    # become a skip" stated at the run's level.
    message = str(raised.value)
    for product in WALK:
        assert _identifier_text(product) in message, (
            f"the run's error did not name {product}, so its launch was "
            f"skipped rather than failed: {message!r}"
        )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The reconciliation pass records completions and
# reopenings the webhook missed
# ---------------------------------------------------------------------------


async def test_a_launch_whose_projection_failed_is_left_unreconciled_and_unobserved(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _Pass],
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Scenario: A launch whose projection failed is left unreconciled and
    unobserved.

    WHEN the reconciliation pass would reach a launch whose projection
    raised on the same run
    THEN that launch's tasks are neither read for recording nor observed,
    and their retained observed states are left exactly as they were.

    Stated on the reconciliation requirement rather than on the containment
    one, and asserted separately from its containment twin above, because
    it constrains a different thing: the *exception* to "every active
    launch's mapped tasks". The retained state is seeded as *closed* here,
    the opposite of the twin, so a skip that reset the state rather than
    leaving it would be caught too.
    """
    world = {
        SECOND: _TaskState(closed_in_clickup=False, last_observed_closed=True),
        THIRD: _TaskState(closed_in_clickup=True, last_observed_closed=False),
    }
    reconcile = install_reconcile(
        job_module, monkeypatch, _ObservingReconcile(_Timeline(), world)
    )
    passes["converge_launch"].fail_for(
        SECOND, lambda: ClickUpSyncError("list_tasks -> 404 Not Found")
    )

    with pytest.raises(Exception):  # noqa: B017
        await _run_job()

    # SPECIFIED: this is an *exception* to "every active launch's mapped
    # tasks", so the launches it does not except are still reconciled on
    # that run. Asserted first, because without it every assertion below
    # holds against a pass that abandoned its walk and reconciled nothing
    # -- which is not the run this scenario is stated over.
    assert reconcile.seen == [FIRST, THIRD], (
        "the run left more than the excepted launch unreconciled; it "
        f"reconciled {reconcile.seen}"
    )
    assert world[THIRD].recorded == ["Satisfied"], (
        "a launch the exception does not cover recorded nothing, so the "
        "assertions below establish nothing about the exception"
    )

    # SPECIFIED: the excepted launch's tasks are neither read for
    # recording...
    assert SECOND not in reconcile.seen
    assert world[SECOND].recorded == []
    # ...nor observed -- the retained state is left exactly as it was.
    assert world[SECOND].last_observed_closed is True, (
        "the retained observed state of a launch whose projection raised "
        "was changed, so the launch was observed after all"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the catch is literally `except Exception` rather than a curated
#   list. `design.md` decides it, no scenario states it, and the
#   containment tests above provoke `ClickUpSyncError` and a bare
#   `RuntimeError` between them, which is what a curated list would miss.
# - What `scheduled-jobs` records for a run whose process was cancelled.
#   The requirement explicitly leaves it: "nothing further is required of
#   the run's outcome, which is `scheduled-jobs`' to decide".
# - The order the walk visits launches in. `design.md` -- *The walk's order
#   is left as it is* -- states it is unspecified; the fixtures here fix an
#   order only so that "before" and "after" are sayable.
# - That the rollback happens after *every* contained failure rather than
#   only after a database one. `design.md` decides it unconditional, and no
#   scenario states it; the integration-tier database test is what would
#   fail if it were made conditional and the classification got it wrong.
# ---------------------------------------------------------------------------
