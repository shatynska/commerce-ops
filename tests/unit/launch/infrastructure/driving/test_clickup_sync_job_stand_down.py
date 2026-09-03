"""The sync pass stands down while the served playbook cannot hold a launch.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *Projection and intake stand down while
the playbook cannot hold a launch*:

- *A pass stands down rather than failing*
- *A ready playbook restores the passes* — the pass half. (Its intake half
  is in `test_clickup_webhook_stand_down.py`.)

And, from the MODIFIED requirement *Each launch is projected into its own
ClickUp list*, the clause this change adds to its statement — "A pass that
stands down because the served playbook cannot hold a launch SHALL create
nothing and write nothing ... that is a decline rather than the silent skip
this requirement forbids, and it is recorded as a successful run." That
clause names no `#### Scenario:` of its own; the requirement's four
scenarios are stated outside a stand-down and keep their existing tests in
`tests/unit/launch/infrastructure/driven/`.

## Level

The job body, which is the smallest unit that can observe two of the three
things the scenario asserts: it is the job that takes the serving read
(`design.md`'s consumer table), and "the run is recorded as succeeded" has
no signal below it — a job body's only outcome signal is whether it raises,
the reading `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`
already recorded for the same words. The runner's own recording of that
outcome is integration-tier
(`tests/integration/shared/test_scheduled_run_history.py`).

## Reading the outcome clauses

"Recorded as succeeded" is read as *the job body returns normally*;
"recorded as failed" as *it raises*. Same reading as the briefing job's
tests, and the same reason: it is the only outcome signal a job body has.

## What is fixed, and what is INVENTED

Fixed by the artifacts: that `clickup_sync_job` stands the pass down, logs
the stand-down and the unheld gates, and lets the run record as succeeded
(`tasks.md` 4.2); and `PlaybookNotReadyError` as the refusal's type.

INVENTED, each with a correction point below:

- How the job is reached — through the runner's periodic registry and the
  registered function's `__module__`, never by module path or task name.
  That is `test_clickup_sync_job_schedule.py`'s own convention, transcribed.
- The collaborator names substituted on the job module: `PlaybookRepository`
  for the serving read, and the two pass functions. The `passes` fixture
  probes and fails loudly rather than defaulting, so a differently-named
  collaborator cannot leave a test green against an unpatched real one.
- How the job reaches the launches to run the pass over. The `launches`
  fixture installs its double over `LaunchRepository` with `raising=False`,
  because no artifact fixes that name; where the job reaches them some
  other way the double is simply not installed, and the *ready-playbook*
  test below is what surfaces it — the passes never run and it fails,
  loudly and for a reason its message names. Correction point:
  `_FakeLaunches` and the `launches` fixture.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import datetime
import inspect
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
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
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

UNHELD_GATE: Final = "graduated"
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

# The two pass functions the job drives, as
# `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`
# names them. Probed on the job module rather than assumed present under
# both spellings.
PASS_ATTRIBUTES: Final = ("converge_launch", "reconcile_launch")


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


def _active_launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID,
        playbook=_ready_playbook(),
        launch_date=datetime.date(2027, 3, 2),
    )
    return launch


# ---------------------------------------------------------------------------
# The refusal — INVENTED constructor keywords, one correction point
# ---------------------------------------------------------------------------


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
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


def _reconciliation_periodic() -> Any:
    """The ClickUp sync job, found by placement and subject — transcribed
    from `test_clickup_sync_job_schedule.py`."""
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "clickup" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the ClickUp sync pass under "
        f"{JOB_PACKAGE!r}; registered periodics are "
        f"{[entry.task.name for entry in registered]}"
    )
    return matching[0]


def _job_module() -> ModuleType:
    return sys.modules[_reconciliation_periodic().task.func.__module__]


async def _run_job(task: Any) -> Any:
    """Invoke the job body the way the runner would."""
    parameters = inspect.signature(task.func).parameters
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=runner_app,
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


class _RecordingPass:
    """Stands in for `converge_launch` / `reconcile_launch`.

    Records that it ran. Whether it *did* is the whole of "no list is
    created, no task is written, and no outcome is recorded": the pass
    functions are the only things in the job that create, write or record,
    so a job that never calls them creates, writes and records nothing.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


class _FakeLaunches:
    """Hands the job one active launch, so the pass has something to run
    against and "it did not run" cannot pass for the wrong reason."""

    def __init__(self) -> None:
        self._launches = (_active_launch(),)

    async def list_active(self) -> tuple[Launch, ...]:
        return self._launches

    active = list_active
    all_active = list_active

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return self._launches


class _SessionlessStub:
    """A session standing for nothing real: `converge_launch` and
    `reconcile_launch` are substituted wholesale by `_RecordingPass` below,
    so nothing here should need real DB access -- except that
    `hold_launch_advance_lock` (`trigger-clickup-projection-on-launch-
    events`) now wraps the (also-substituted) `converge_launch` call, and
    still issues a real `execute()` on whatever session it is given.
    `None` sufficed before that lock existed; a no-op stub is what it
    needs now, and `rollback` covers the pass's own fault-recovery path.
    """

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None


@asynccontextmanager
async def _fake_session() -> AsyncIterator[_SessionlessStub]:
    yield _SessionlessStub()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture(autouse=True)
def sessionless(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_module, "session", _fake_session, raising=False)
    monkeypatch.setattr(job_module, "transaction", _fake_session, raising=False)


@pytest.fixture()
def passes(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, _RecordingPass]]:
    """Substitute every pass function the job drives.

    Fails loudly where the module exposes none of them, rather than leaving
    every assertion below trivially satisfied by an unpatched real pass that
    could not run without a database anyway.
    """
    installed: dict[str, _RecordingPass] = {}
    for name in PASS_ATTRIBUTES:
        if hasattr(job_module, name):
            fake = _RecordingPass(name)
            monkeypatch.setattr(job_module, name, fake)
            installed[name] = fake
    assert installed, (
        f"{job_module.__name__} exposes none of {PASS_ATTRIBUTES}, so this "
        "file cannot tell a pass that ran from one that stood down"
    )
    yield installed


@pytest.fixture(autouse=True)
def launches(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_module, "LaunchRepository", lambda *a, **k: _FakeLaunches(), raising=False
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


# ---------------------------------------------------------------------------
# Requirement: Projection and intake stand down while the playbook cannot
# hold a launch
# ---------------------------------------------------------------------------


async def test_a_pass_stands_down_rather_than_failing(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _RecordingPass],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A pass stands down rather than failing.

    WHEN the reconciliation pass runs while a gate holds no active blocking
    step
    THEN no list is created, no task is written, and no outcome is recorded
    AND the run is recorded as succeeded, with the stand-down and the
    unheld gates logged.

    "Recorded as succeeded" matters more than it looks: the requirement
    says recording a failure "would put a working deployment into retry and
    overdue reporting for a condition retrying cannot resolve", so a job
    that raised here would be wrong in a way no other assertion catches.
    """
    install_playbook_read(job_module, monkeypatch, refusing_with=_unready_playbook())

    with caplog.at_level("INFO"):
        # SPECIFIED: the run is recorded as succeeded — no `pytest.raises`;
        # returning normally is the assertion.
        await _run_job(_reconciliation_periodic().task)

    # SPECIFIED: no list is created, no task is written, no outcome is
    # recorded — the passes that would do any of those never ran.
    for name, recorded in passes.items():
        assert recorded.calls == 0, (
            f"{name} ran during a stand-down, so the pass did not decline"
        )

    # SPECIFIED: the stand-down and the unheld gates are logged.
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert UNHELD_GATE in logged, (
        "the stand-down did not log the gate holding no active blocking "
        f"step; captured log was: {logged!r}"
    )


async def test_a_ready_playbook_restores_the_passes(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _RecordingPass],
) -> None:
    """Scenario: A ready playbook restores the passes.

    WHEN every gate holds at least one active blocking step
    THEN the projection and reconciliation passes run exactly as they do
    today.

    The control for the test above: without it, a job that stood down
    unconditionally — or one that had simply stopped working — would
    satisfy every assertion there.
    """
    install_playbook_read(job_module, monkeypatch, refusing_with=None)

    await _run_job(_reconciliation_periodic().task)

    for name, recorded in passes.items():
        assert recorded.calls >= 1, (
            f"{name} did not run against a ready playbook, so the passes "
            "were not restored"
        )
