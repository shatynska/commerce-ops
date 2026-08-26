"""No tag is written while the passes have stood down.

Derived strictly from the delta spec of the OpenSpec change
`tag-tasks-with-gate-and-discipline`:
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/launch-clickup-sync/spec.md`

Covers exactly one scenario of the ADDED requirement *A projected task
carries its step's gate and discipline as tags*:

- *No tag is written during a stand-down*

Every other scenario of that requirement is covered at the projection level
in `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py`. See
`openspec/changes/tag-tasks-with-gate-and-discipline/test-manifest.md`.

## Why this scenario cannot live with the others

The stand-down happens in the **job**, which declines before the pass body
is entered — `converge_launch` is never called, so it has no stand-down
state to be tested in. The smallest unit that can observe "no tag is
written while the passes have stood down" is therefore the job body, the
same level `test_clickup_sync_job_stand_down.py` already sits at for the
stand-down's own scenarios.

## What this adds over the existing stand-down test

`test_clickup_sync_job_stand_down.py` already asserts that neither pass
function runs during a stand-down, and tagging lives inside
`converge_launch` — so on today's shape, that test entails this one. What
it does not catch, and this file does, is a tag **backfill placed in the
job body itself**: a loop over mapped tasks written outside
`converge_launch`, which would run whether or not the passes did. That is
a plausible shape for a one-off backfill, and it is the failure mode the
spy below exists for.

The control against vacuity is that file's own
`test_a_ready_playbook_restores_the_passes`, which establishes that these
same fixtures let the passes run when the playbook is ready. It is not
duplicated here.

## INVENTED shapes

The harness — reaching the job through the runner's periodic registry,
substituting `PlaybookRepository`, `LaunchRepository` and the two pass
functions on the job module — is transcribed from
`test_clickup_sync_job_stand_down.py`, including its `_build_not_ready`
signature probe. Correcting any of it there and here is a fixture
correction.

Added for this change: a spy installed over
`clickup_client.add_task_tag` **strictly** (`raising=True`), so an absent
operation fails this test by name rather than leaving it green against a
system that cannot tag at all.

## Expected first-run state

`clickup_client.add_task_tag` does not exist, so the spy fixture fails on
an absent target (`AttributeError` from `monkeypatch.setattr`) — absence,
and nothing more.

Baseline recorded before this test was written:
`uv run pytest tests/unit tests/agents` at the worktree root —
1064 passed, 0 failed.
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
from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

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
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

PASS_ATTRIBUTES: Final = ("converge_launch", "reconcile_launch")

# The two tag-writing operations of the shared adapter. `create_task` is
# included because a task created carrying tags is a tag write too, and a
# job-body backfill could plausibly take either route.
TAG_WRITING_OPERATIONS: Final = ("add_task_tag", "create_task")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_clickup_sync_job_stand_down.py`
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


def _active_launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID,
        playbook=_ready_playbook(),
        launch_date=datetime.date(2027, 3, 2),
    )
    return launch


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError`"
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


class _FakeLaunches:
    """Hands the job one active launch, so "nothing was tagged" cannot pass
    for the wrong reason — a job with no launches to visit would write no
    tag whatever it did about the stand-down."""

    def __init__(self) -> None:
        self._launches = (_active_launch(),)

    async def list_active(self) -> tuple[Launch, ...]:
        return self._launches

    active = list_active
    all_active = list_active

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return self._launches


class _TagSpy:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        pytest.fail(
            f"{self.name} reached ClickUp during a stand-down: "
            f"args={args!r} kwargs={kwargs!r}"
        )


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


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


@pytest.fixture()
def tag_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, _TagSpy]:
    """Substitute every tag-writing operation of the shared adapter.

    Installed **strictly**: `raising=True`, so an adapter with no
    `add_task_tag` fails this test on an absent target rather than leaving
    it green against a system that cannot write a tag at all.
    """
    spies: dict[str, _TagSpy] = {}
    for name in TAG_WRITING_OPERATIONS:
        spy = _TagSpy(f"clickup_client.{name}")
        monkeypatch.setattr(clickup_client, name, spy)
        spies[name] = spy
    return spies


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
# Requirement: A projected task carries its step's gate and discipline as
# tags
# ---------------------------------------------------------------------------


async def test_no_tag_is_written_during_a_stand_down(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    passes: dict[str, _RecordingPass],
    tag_spies: dict[str, _TagSpy],
) -> None:
    """Scenario: No tag is written during a stand-down.

    WHEN a pass stands down because the served playbook cannot hold a
    launch
    THEN no tag is written to any task.

    SPECIFIED: "No tag is written while the passes have stood down, for the
    reason the stand-down requirement already gives." The job is given one
    active launch, so the absence of a tag write traces to the stand-down
    rather than to there having been nothing to tag.

    The run returning normally is asserted too, not incidentally: the
    stand-down requirement says a stood-down pass is "recorded as having
    **succeeded**", and a job that raised here would satisfy "no tag was
    written" for the wrong reason entirely.
    """
    install_playbook_read(job_module, monkeypatch, refusing_with=_unready_playbook())

    # SPECIFIED: the run succeeds — returning normally is the assertion.
    await _run_job(_reconciliation_periodic().task)

    # SPECIFIED: no tag is written to any task. The spies fail the test at
    # the point of call; these assertions are the record for a spy that was
    # somehow bypassed.
    for name, spy in tag_spies.items():
        assert spy.calls == [], f"clickup_client.{name} was called during a stand-down"

    # The mechanism today: tagging lives inside the projection pass, which
    # never ran. Asserted so a future implementation that hoisted tagging
    # into the job body is distinguishable from one that did not.
    for name, recorded in passes.items():
        assert recorded.calls == 0, (
            f"{name} ran during a stand-down, so the pass did not decline"
        )
