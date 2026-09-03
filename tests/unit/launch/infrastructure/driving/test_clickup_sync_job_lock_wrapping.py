"""The periodic pass's own `converge_launch` call now takes the advance lock.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers the structural half of *The eager run and the pass do not duplicate
each other's work* that belongs to the **pass's own side** of the race:

    Because the eager run and the periodic pass perform the same idempotent
    convergence, either running before, after, or concurrently with the
    other for the same launch SHALL produce the same converged state as
    either running alone.

Closing that race for real means both sides taking the lock (`design.md`).
The eager side's own half is `test_eager_convergence_helper.py`'s; this
file covers `clickup_sync_job.py`'s restructured per-launch call
(`tasks.md` 4.1): each launch's `converge_launch` call now runs inside a
`transaction()` opened solely to hold `hold_launch_advance_lock`, and
`converge_launch`'s own collaborators stay bound to the pass's existing
outer session rather than being rebound to that lock-only transaction.

The concurrent-race half — that this lock genuinely excludes a real
concurrently locking eager call — is integration-tier, in
`test_eager_convergence_atomicity_live.py` (`tasks.md` 6.3).

`tasks.md` 4.2's own obligation — that the pass's existing per-launch
`try`/`except` containment still holds once the lock wraps the call — is
asserted here as a **regression guard**, not restated at length: the full
containment surface (a failing launch does not stop the others, each
failure reported, the run's aggregate outcome, the database-recovery path)
is `test_clickup_sync_job_containment.py`'s own, already passing today,
and this change leaves it untouched; a lock acquisition that broke it
would show up there without this file's help. What this file adds is the
one thing that suite cannot see: that the lock sits around the call at
all, and that it does not disturb which collaborators reach
`converge_launch`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The job body over in-memory doubles, the level
`test_clickup_sync_job_containment.py` already holds for this pass's walk.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that each launch's `converge_launch`
call runs inside a `transaction()` held solely for
`hold_launch_advance_lock`; that `converge_launch`'s own collaborators
stay bound to the pass's existing outer `session()`, never rebound to the
lock's own transaction (`tasks.md` 4.1; `design.md`); and that the
existing per-launch containment and the `reconcile_launch` call are
otherwise unaffected.

INVENTED: the lock collaborator's name (`_LOCK_NAMES`, transcribed from
`test_gate_decision_wiring.py`'s own convention); everything else —
reaching the job, its collaborator names, the walk fixtures — is
transcribed from `test_clickup_sync_job_containment.py`, which records the
provenance of each.

## Expected first-run state

The pass takes no lock around its `converge_launch` call yet (`tasks.md`
4.1). Run against this repository's current state before any of `tasks.md`
was implemented:

- `test_the_lock_is_acquired_for_each_launchs_convergence_call` **fails**
  on a *wrong value* (`ai-toolkit:testing`'s first failure state, not the
  absent-target one): the job itself already exists and runs today, and
  `lock.calls` is simply empty because nothing in the current,
  pre-restructuring pass reaches an advisory-lock collaborator around this
  call.
- `test_converge_launchs_collaborators_are_reused_across_launches_not_rebuilt`
  and `test_a_failing_launchs_convergence_still_does_not_stop_the_walk`
  **pass already**, for the same reason
  `test_clickup_sync_job_containment.py`'s own docstring records for its
  two similarly-early-passing tests: each states behaviour this change
  must **preserve** rather than introduce — the pass's collaborators are
  already constructed once per run today, and its existing containment
  already holds — so their job is to catch a restructuring that reaches
  further than `tasks.md` 4.1 intends, not to prove the lock exists.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import datetime
import inspect
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any, Final

import pytest
from procrastinate import job_context, jobs

import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
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
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

FIRST: Final = ProductId(str(uuid.uuid4()))
SECOND: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FIRST, SECOND)

PASS_NAMES: Final = ("converge_launch", "reconcile_launch")
_LOCK_NAMES: Final = ("hold_launch_advance_lock", "advance_lock", "hold_advance_lock")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_clickup_sync_job_containment.py`
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


def _launch_for(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id,
        playbook=_ready_playbook(),
        launch_date=datetime.date(2027, 3, 2),
    )
    return launch


# ---------------------------------------------------------------------------
# Reaching the job — transcribed from `test_clickup_sync_job_containment.py`
# ---------------------------------------------------------------------------


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


def _runner_app() -> Any:
    from commerce_ops.shared.infrastructure.driven.job_runner import app

    return app


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
# Test doubles
# ---------------------------------------------------------------------------


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
        f"its arguments (args={args!r}, kwargs={kwargs!r}); correct "
        "`_product_of`"
    )


class _RecordingConverge:
    """Stands in for `converge_launch`.

    Records, per call, which collaborator objects it was handed — so a
    test can assert they are the *same* objects across every launch in one
    run, which is what "stay bound to the pass's existing outer session,
    never rebound to the lock-only transaction" means observably at this
    level: a per-launch rebuild would hand a fresh object to at least one
    of these calls.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _RecordingReconcile:
    def __init__(self) -> None:
        self.seen: list[ProductId] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.seen.append(_product_of(args, kwargs))


class _RecordingLock:
    def __init__(self, order: list[str]) -> None:
        self.calls: list[ProductId] = []
        self._order = order

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        self.calls.append(product_id)
        self._order.append(f"lock:{product_id.value}")


class _FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0
        self.commits = 0

    async def rollback(self) -> None:
        self.rollbacks += 1

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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture()
def order() -> list[str]:
    return []


@pytest.fixture()
def shared_session(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> _FakeSession:
    fake = _FakeSession()

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
def converge(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> _RecordingConverge:
    fake = _RecordingConverge()
    assert hasattr(job_module, "converge_launch"), (
        f"{job_module.__name__} exposes no `converge_launch`; correct "
        "`PASS_NAMES` to the implemented collaborator name"
    )
    monkeypatch.setattr(job_module, "converge_launch", fake)
    return fake


@pytest.fixture()
def reconcile(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> _RecordingReconcile:
    fake = _RecordingReconcile()
    if hasattr(job_module, "reconcile_launch"):
        monkeypatch.setattr(job_module, "reconcile_launch", fake)
    return fake


@pytest.fixture()
def lock(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch, order: list[str]
) -> _RecordingLock:
    fake = _RecordingLock(order)
    for name in _LOCK_NAMES:
        if hasattr(job_module, name):
            monkeypatch.setattr(job_module, name, fake)
    return fake


@pytest.fixture()
def launches(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_module,
        "LaunchRepository",
        lambda *a, **k: _FakeLaunches(tuple(_launch_for(product) for product in WALK)),
        raising=False,
    )


@pytest.fixture()
def ready(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str = "") -> LaunchPlaybook:
            return _ready_playbook()

    monkeypatch.setattr(job_module, "PlaybookRepository", _Repository)


# ---------------------------------------------------------------------------
# "closing this race for real means both sides taking it" — the pass's
# own half
# ---------------------------------------------------------------------------


async def test_the_lock_is_acquired_for_each_launchs_convergence_call(
    converge: _RecordingConverge,
    reconcile: _RecordingReconcile,
    lock: _RecordingLock,
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """SPECIFIED-BY-DESIGN (`tasks.md` 4.1; `design.md` — "closing the race
    for real means both sides taking it"): every active launch's
    `converge_launch` call now runs with `hold_launch_advance_lock`
    acquired for it, not only the eager path's own call.

    Without this, `clickup_sync_job`'s own pass would still race a
    concurrent eager call on a brand-new launch's first list exactly as it
    did before this change — an advisory lock only serializes callers that
    both attempt to take it.
    """
    await _run_job()

    # Premise: the walk really did attempt both launches.
    assert converge.calls, (
        "convergence was never attempted, so this test exercised nothing"
    )
    assert lock.calls, (
        "the pass's own convergence call never reached the advisory lock "
        "collaborator, so it does not serialize against a concurrent eager "
        "call for the same launch's first list"
    )
    for product_id in WALK:
        assert product_id.value in {p.value for p in lock.calls}, (
            f"the lock was not acquired for {product_id}'s convergence call: "
            f"{lock.calls!r}"
        )


async def test_converge_launchs_collaborators_are_reused_across_launches_not_rebuilt(
    converge: _RecordingConverge,
    reconcile: _RecordingReconcile,
    lock: _RecordingLock,
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """SPECIFIED-BY-DESIGN (`design.md`: "`converge_launch`'s own
    collaborators stay bound to the pass's existing outer `session()`,
    exactly as today" — never rebound to the lock-only transaction).

    Observed here as object identity across the walk's two launches: the
    pass constructs `mapping`, `clickup`, `read_product` and `members` once
    per **run**, not once per **launch**, so the same objects reach
    `converge_launch` for every launch the lock now wraps. A restructuring
    that rebuilt any of them inside the new per-launch lock block would
    hand at least one launch a different object and fail here.
    """
    await _run_job()

    assert len(converge.calls) == len(WALK), (
        f"convergence did not run once per launch: {converge.calls!r}"
    )
    for name in ("mapping", "clickup", "read_product", "members"):
        seen = [call[name] for call in converge.calls if name in call]
        if not seen:
            continue
        first = seen[0]
        assert all(candidate is first for candidate in seen), (
            f"the `{name}` collaborator reaching `converge_launch` differed "
            "across launches in the same run, so it was rebuilt somewhere "
            f"rather than reused from the pass's own outer session: {seen!r}"
        )


# ---------------------------------------------------------------------------
# `tasks.md` 4.2 — the existing per-launch containment still holds, as a
# regression guard (the full surface is `test_clickup_sync_job_containment.py`'s)
# ---------------------------------------------------------------------------


async def test_a_failing_launchs_convergence_still_does_not_stop_the_walk(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    reconcile: _RecordingReconcile,
    lock: _RecordingLock,
    launches: None,
    ready: None,
    shared_session: _FakeSession,
) -> None:
    """Regression guard for `tasks.md` 4.2: adding the lock around the
    call must not narrow or remove the pass's existing per-launch
    containment.

    The full containment surface — reporting, the run's aggregate outcome,
    the database-recovery path — is asserted at length in
    `test_clickup_sync_job_containment.py`, which this change leaves
    untouched; this is a minimal guard that the lock wrapping specifically
    does not regress the one property this file's own fixtures can
    exercise.
    """
    from commerce_ops.launch.infrastructure.driven.clickup_sync import ClickUpSyncError

    async def _failing_first(*args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        if product_id == FIRST:
            raise ClickUpSyncError("create_task -> 404 Not Found")

    monkeypatch.setattr(job_module, "converge_launch", _failing_first)

    with pytest.raises(Exception):  # noqa: B017 -- outcome asserted below
        await _run_job()

    # SPECIFIED (unchanged by this file's own change): the walk still
    # reaches the launch after the one that failed.
    assert SECOND in reconcile.seen, (
        "a launch after one whose (now lock-wrapped) convergence failed was "
        f"not reached: {reconcile.seen!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The full containment surface (per-failure reporting, the run's
#   aggregate error, the database-recovery-fails-the-walk path). Already
#   covered at length by `test_clickup_sync_job_containment.py`, which
#   this change leaves untouched; duplicating it here would make this file
#   fail for reasons it does not itself state.
# - That the lock genuinely excludes a concurrently locking eager call
#   against a real Postgres `pg_advisory_xact_lock`. An advisory lock
#   holds nothing without a database; see
#   `test_eager_convergence_atomicity_live.py` (`tasks.md` 6.3).
# - That `reconcile_launch`'s own call is unaffected by the restructuring
#   (`tasks.md` 4.1: "the `reconcile_launch` call for each launch
#   unchanged"). Implicit in every test above continuing to reach it
#   normally through the untouched `reconcile` fixture; no scenario states
#   anything further about it.
# ---------------------------------------------------------------------------
