"""The daily briefing, as a scheduled job.

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/briefing/spec.md

Covers, at the job level:

- *The daily briefing runs on a schedule* / Scenario: The briefing runs
  when its schedule is due. (Its second scenario -- the briefing cannot be
  started from outside the deployment -- is about the application's
  externally reachable surface, so it lives in
  `tests/unit/test_briefing_not_externally_startable.py`.)
- *A failure to assemble is surfaced, not treated like a delivery failure*
  / all three scenarios.

The remaining briefing requirements are decided inside
`run_daily_briefing` rather than by the job, and are covered at that level
in `tests/unit/briefing/application/`.

## Why the job level for these four

Each turns on something only the job knows: its declared schedule, which
attempt it is on, and whether the runner will retry. `design.md` Decision
7 puts the assemble-failure message behind "only once retries are
exhausted", which is unobservable anywhere the attempt count is not
available -- so this is the smallest level that can observe them
(`ai-toolkit:testing`'s level rule), not a level chosen for breadth.

## How the job is reached

Never by module path or task name: the job is reached the way the runner
reaches it -- through the runner application object's periodic registry --
and its module through the registered function's `__module__`. That is the
pattern `tests/unit/catalog/infrastructure/driving/test_daily_digest_job.py`
established for the retired daily digest, and it means an implementation
that names or places the briefing job differently needs no change here.

The one identifying assumption is that the registered task's name contains
"brief" (`_briefing_periodic` below). `tasks.md` 5.4 fixes that a briefing
job is registered, not what it is called.

## Reading the outcome clauses

"The run SHALL be recorded as failed" is read as *the job body raises*;
"recorded as succeeded" / "SHALL NOT be retried" as *it returns normally*.
That is the only outcome signal a job body has, and it is the reading the
retired digest's job tests recorded for the same words. The runner's own
recording of that outcome is integration-tier
(`tests/integration/shared/test_scheduled_run_history.py`).

## The interface under test does not exist yet

`briefing/infrastructure/driving/daily_briefing_job.py` and its
registration are introduced by this change, so every test here is expected
to fail on an absent target until tasks 4.4, 5.2, 5.4 and 5.5 land -- the
selector below finds no registered briefing task and fails loudly rather
than passing vacuously. Per `ai-toolkit:testing`, that failure establishes
only absence.

INVENTED, recorded in `test-manifest.md` at the change root:

- The job module imports `run_daily_briefing` by name into its own
  namespace, the collaborator pattern `daily_digest_job.py` already uses
  and that `monkeypatch.setattr` relies on. `raising=True` (the default)
  is used throughout, so a differently-named collaborator fails loudly
  here rather than leaving a test green against an unpatched real one.
- The notifier injection point's name. `tasks.md` 5.2 says the job
  declares module-level injection points "on `daily_digest_job.py`'s
  pattern" without fixing spellings, so the `notifier` fixture installs
  the double over whichever of `NOTIFIER_ATTRIBUTES` the module exposes,
  and fails loudly if it exposes neither.
"""

from __future__ import annotations

import datetime
import inspect
import itertools
import sys
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any, Final

import pytest
from procrastinate import job_context, jobs, periodic

import commerce_ops.worker  # noqa: F401  -- registers the job definitions
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio

# DERIVED (`tasks.md` 5.2: the briefing takes "the digest's schedule slot
# and tolerance"). The retired digest's slot, as
# `test_daily_digest_job.py` recorded it.
INHERITED_HOUR: Final = 6
INHERITED_MINUTE: Final = 0

# The two spellings the notifier injection point might carry.
NOTIFIER_ATTRIBUTES: Final = ("post_monitoring_message", "notifier")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# Reaching the briefing job
# --------------------------------------------------------------------------


def _briefing_periodic() -> periodic.PeriodicTask[Any, Any, Any]:
    """The one piece of recurring work this change schedules."""
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    briefing = [entry for entry in registered if "brief" in entry.task.name.lower()]
    assert len(briefing) == 1, (
        "expected exactly one registered periodic task for the daily "
        f"briefing; registered: {[entry.task.name for entry in registered]}"
    )
    return briefing[0]


def _job_module() -> ModuleType:
    return sys.modules[_briefing_periodic().task.func.__module__]


def _make_job(task: Any, *, attempts: int) -> jobs.Job:
    """A `Job` row as the runner hands it to a job body.

    `attempts` is the number of attempts that already failed: 0 on the
    first run, per the procrastinate behaviour `test_daily_digest_job.py`
    verified.
    """
    return jobs.Job(
        id=1,
        queue=task.queue,
        lock=task.lock,
        queueing_lock=task.queueing_lock,
        task_name=task.name,
        task_kwargs={},
        attempts=attempts,
    )


def _retry_decision(task: Any, *, attempts: int) -> Any:
    strategy = task.retry_strategy
    assert strategy is not None, (
        f"task {task.name} declares no retry strategy, so a failed run "
        "could never be retried"
    )
    return strategy.get_retry_decision(
        exception=RuntimeError("simulated failure"),
        job=_make_job(task, attempts=attempts),
    )


def _final_attempt(task: Any, *, ceiling: int = 50) -> int:
    """The `attempts` value on the run the strategy will *not* retry.

    Computed from the job's own strategy rather than transcribed, so this
    file pins no retry maximum -- no artifact fixes one for the briefing.
    """
    for attempts in range(ceiling):
        if _retry_decision(task, attempts=attempts) is None:
            return attempts
    pytest.fail(
        f"the retry strategy for {task.name} still retried after {ceiling} "
        "attempts; the briefing's assemble failures must stop at a declared "
        "maximum, or one outage can never reach its final attempt"
    )


async def _run_job(task: Any, *, attempts: int = 0) -> Any:
    """Invoke the job body the way the runner would."""
    parameters = inspect.signature(task.func).parameters
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=runner_app,
                job=_make_job(task, attempts=attempts),
                start_timestamp=time.time(),
                abort_reason=lambda: None,
            )
        )
    elif attempts != 0:
        pytest.fail(
            f"task {task.name} does not receive the job context "
            "(`pass_context=True`), so its body cannot know which attempt "
            "it is on -- required by 'An intermediate failed attempt does "
            "not post'"
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingNotifier:
    """Stands in for the job's notifier injection point.

    Exposes both a `post_monitoring_message` method and `__call__`, so it
    can be installed over either spelling (see the module docstring) and
    still record what was posted.
    """

    def __init__(self) -> None:
        self.posted: list[str] = []

    async def post_monitoring_message(self, message: str) -> None:
        self.posted.append(message)

    async def __call__(self, message: str) -> None:
        await self.post_monitoring_message(message)


class _ScriptedBriefingRun:
    """Stands in for `run_daily_briefing`: either it completes, or it
    raises the scripted assembly failure."""

    def __init__(self, *, failure: Exception | None = None) -> None:
        self._failure = failure
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        if self._failure is not None:
            raise self._failure


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    """Stands in for a process-wide session provider, if the job module
    has one. Yields `None`; nothing downstream of it runs, because
    `run_daily_briefing` is faked out. Keeps this file unit-tier -- no
    `DATABASE_URL`, no Postgres."""
    yield None


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture()
def sessionless(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize a session provider if the job module has one.

    `raising=False` here, and only here: `design.md` Decision 5 has the
    job's readers arrive already closed over their sessions, so a job
    module with no `session` attribute at all is the expected shape rather
    than a defect.
    """
    monkeypatch.setattr(job_module, "session", _fake_session, raising=False)


@pytest.fixture()
def notifier(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_RecordingNotifier]:
    fake = _RecordingNotifier()
    installed = [name for name in NOTIFIER_ATTRIBUTES if hasattr(job_module, name)]
    assert installed, (
        f"{job_module.__name__} exposes none of {NOTIFIER_ATTRIBUTES}, so "
        "the job has no notifier injection point and cannot post the "
        "'briefing could not be assembled' message at all"
    )
    for name in installed:
        monkeypatch.setattr(job_module, name, fake)
    yield fake


@pytest.fixture()
def install_run(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    def _install(fake: _ScriptedBriefingRun) -> _ScriptedBriefingRun:
        monkeypatch.setattr(job_module, "run_daily_briefing", fake)
        return fake

    yield _install


# --------------------------------------------------------------------------
# Requirement: The daily briefing runs on a schedule
# --------------------------------------------------------------------------


def test_the_briefing_has_a_declared_schedule() -> None:
    """Scenario: The briefing runs when its schedule is due.

    WHEN the daily briefing's declared schedule becomes due
    THEN the system SHALL run the daily briefing.

    SPECIFIED: the briefing is declared as recurring work with a schedule,
    so a due moment causes a run with no request from outside the
    deployment. That the schedule is *daily* is asserted below.
    """
    assert _briefing_periodic().cron, "the daily briefing's schedule is empty"


def test_the_declared_schedule_becomes_due_once_a_day() -> None:
    """Scenario: The briefing runs when its schedule is due.

    SPECIFIED by "The *daily* briefing runs on a schedule": consecutive
    due moments are one day apart. Asserted separately from the hour below
    so that an implementation choosing a different hour does not obscure
    whether the cadence itself is daily.
    """
    briefing = _briefing_periodic()
    reference = datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC).timestamp()

    first = briefing.croniter.get_next(ret_type=float, start_time=reference)
    second = briefing.croniter.get_next(ret_type=float, start_time=first)

    assert second - first == 24 * 60 * 60, (
        "expected consecutive due moments one day apart, got "
        f"{(second - first) / 3600:.1f} hours"
    )


def test_the_briefing_inherits_the_retired_digests_schedule_slot() -> None:
    """DERIVED, from `tasks.md` 5.2 ("the digest's schedule slot and
    tolerance") and `design.md` Decision 6 ("inherits its schedule slot").

    No spec scenario fixes an hour -- the requirement says only that the
    briefing runs on a declared schedule. Recorded as its own test so that
    a deliberate change of slot fails here alone, visibly, rather than
    inside a scenario assertion.
    """
    briefing = _briefing_periodic()
    reference = datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC).timestamp()

    moment = datetime.datetime.fromtimestamp(
        briefing.croniter.get_next(ret_type=float, start_time=reference),
        datetime.UTC,
    )

    assert (moment.hour, moment.minute) == (INHERITED_HOUR, INHERITED_MINUTE), (
        "expected the briefing to inherit the retired digest's 06:00 UTC "
        f"slot, got {moment}"
    )


# --------------------------------------------------------------------------
# Requirement: A failure to assemble is surfaced, not treated like a
# delivery failure
# --------------------------------------------------------------------------


async def test_an_assembly_failure_is_retried() -> None:
    """Scenario: An assembly failure is retried.

    WHEN an attempt of the daily briefing has failed because its source
    data could not be read, and the declared maximum number of attempts
    has not been reached
    THEN the system SHALL retry the run.
    """
    task = _briefing_periodic().task

    assert _retry_decision(task, attempts=0) is not None, (
        "a first failed run of the daily briefing was not retried, so "
        "`scheduled-jobs`' retry behaviour does not apply to it"
    )


async def test_successive_retries_are_declared_and_bounded() -> None:
    """Requirement statement: "so `scheduled-jobs`' retry and overdue
    reporting apply to it", read together with `scheduled-jobs`' own *A
    Failed Run Is Retried With Increasing Delay*.

    DERIVED here (the briefing delta states no delay behaviour of its
    own): the briefing's retry strategy must both back off and stop, or
    "only once the run's retries are exhausted" names a moment that never
    arrives.
    """
    task = _briefing_periodic().task
    final = _final_attempt(task)
    assert final >= 2, (
        "the declared maximum leaves fewer than two retries, so backing off "
        f"cannot be observed; retries stop after {final} failed attempt(s)"
    )

    now = datetime.datetime.now(datetime.UTC)
    delays = []
    for attempts in range(final):
        decision = _retry_decision(task, attempts=attempts)
        assert decision.retry_at is not None
        delays.append((decision.retry_at - now).total_seconds())

    assert all(later > earlier for earlier, later in itertools.pairwise(delays)), (
        "expected each retry to wait longer than the one before it, got "
        f"delays (seconds): {[round(delay) for delay in delays]}"
    )
    assert _retry_decision(task, attempts=final) is None


async def test_a_read_failure_on_the_final_attempt_fails_the_run_and_says_so(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_run: Any,
) -> None:
    """Scenario: A read failure on the final attempt fails the run and
    says so.

    WHEN assembling the daily briefing fails on the run's final attempt
    because its source data cannot be read
    THEN the run SHALL be recorded as failed
    AND the system SHALL attempt to post a message indicating the briefing
    could not be assembled.

    DELIBERATELY UNTESTED: the failure message's wording. No artifact pins
    a phrasing, and asserting one would impose a contract nobody agreed to
    -- the same reading the retired digest's tests applied to their own
    failure message.
    """
    task = _briefing_periodic().task
    install_run(
        _ScriptedBriefingRun(failure=RuntimeError("simulated launch-read failure"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- see below
        # Deliberately not narrowed to the scripted `RuntimeError`: what is
        # SPECIFIED is that the run is recorded as failed, and an
        # implementation wrapping the read failure in its own exception
        # type still satisfies that.
        await _run_job(task, attempts=_final_attempt(task))

    # SPECIFIED: a message indicating the briefing could not be assembled
    # is attempted.
    assert len(notifier.posted) == 1
    assert notifier.posted[0], "the attempted failure message was empty"


async def test_an_intermediate_failed_attempt_does_not_post(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_run: Any,
) -> None:
    """Scenario: An intermediate failed attempt does not post.

    WHEN assembling the daily briefing fails on an attempt that will be
    retried
    THEN the system SHALL NOT post a message for that attempt.

    The attempt used is the first, which
    `test_an_assembly_failure_is_retried` establishes will be retried.
    """
    task = _briefing_periodic().task
    install_run(
        _ScriptedBriefingRun(failure=RuntimeError("simulated launch-read failure"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- see the test above
        await _run_job(task, attempts=0)

    # SPECIFIED: no message for an attempt that will be retried.
    assert notifier.posted == [], (
        "an assembly failure posted a message on an attempt that will be "
        "retried, so one outage produces one message per attempt"
    )


async def test_one_outage_produces_exactly_one_message(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_run: Any,
) -> None:
    """Requirement statement: "so one outage produces one message".

    SPECIFIED by the requirement's own reason clause. The two scenarios
    above cover one intermediate attempt and the final one separately;
    this walks every attempt of a single outage and asserts the total.
    """
    task = _briefing_periodic().task
    install_run(
        _ScriptedBriefingRun(failure=RuntimeError("simulated launch-read failure"))
    )

    for attempts in range(_final_attempt(task) + 1):
        with pytest.raises(Exception):  # noqa: B017 -- see above
            await _run_job(task, attempts=attempts)

    assert len(notifier.posted) == 1, (
        "expected one outage to produce exactly one message across all of "
        f"its attempts, got {len(notifier.posted)}: {notifier.posted}"
    )


async def test_a_successful_assembly_leaves_the_job_reporting_success(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_run: Any,
) -> None:
    """DERIVED guard, not a scenario.

    Every assertion above observes a *failed* attempt. Without this, a job
    body that always raised would satisfy all of them, and the
    silent-when-clean and delivery-failure requirements -- both of which
    depend on `run_daily_briefing` returning normally reaching the runner
    as a successful run -- would be unreachable in practice.

    Also confirms the job posts nothing itself on a successful run: what
    is posted, and whether anything is, is `run_daily_briefing`'s decision
    (`tasks.md` 4.4), and a job posting on its own would double every
    briefing.
    """
    run = install_run(_ScriptedBriefingRun())

    await _run_job(_briefing_periodic().task, attempts=0)

    assert run.calls == 1, "the job did not run the briefing use case"
    assert notifier.posted == []


# --------------------------------------------------------------------------
# Guard, not a scenario
# --------------------------------------------------------------------------


def test_the_registry_this_file_reads_is_the_one_the_worker_defers_from() -> None:
    """DERIVED guard, mirroring the one the retired digest's job tests
    carried.

    Every schedule assertion above reads `runner_app.periodic_registry`.
    This asserts that object is what a `PeriodicDeferrer` built the way the
    worker builds one would actually read, so a change that registered the
    briefing on a second registry breaks here rather than leaving the
    assertions above green against something the worker never consults.
    """
    deferrer = periodic.PeriodicDeferrer(
        registry=runner_app.periodic_registry, **runner_app.periodic_defaults
    )

    assert deferrer.registry is runner_app.periodic_registry
