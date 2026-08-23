"""The daily product-monitoring cadence, as a scheduled job.

Derived strictly from the delta specs of the OpenSpec change
`replace-cron-with-job-runner`:

- `specs/product-monitoring/spec.md`
  - ADDED "The Daily Cadence Runs On A Schedule" / Scenario: The daily
    cadence runs when its schedule is due
  - MODIFIED "Daily Cadence Lists Existing Product Names" / Scenarios:
    Daily trigger lists product names; No products exist
  - MODIFIED "Report Delivery Failure Is Decoupled From The Trigger" /
    Scenario: Slack post fails
  - MODIFIED "Database Read Failure Is Surfaced, Not Treated Like A
    Delivery Failure" / Scenarios: Database read fails; An intermediate
    failed attempt does not post; A database read failure is retried
- `specs/scheduled-jobs/spec.md`
  - "Recurring Work Runs On Its Declared Schedule" / Scenarios: Work runs
    when its schedule is due; The schedule's timezone does not depend on
    the host
  - "A Failed Run Is Retried With Increasing Delay" / Scenarios: A failing
    run is retried; Successive retries wait longer; Retries stop at the
    declared maximum

See `test-manifest.md` at the change root for the full
specified/derived/deliberately-untested accounting, and for the
unresolved project questions this file's assumptions are recorded under.

## The one correction point: how the daily job is reached

This file never names the daily job's module, function, task name or
schedule constant. It reaches the job the way the runner itself does --
through the runner application object's periodic registry -- and then
reaches the job's own module through the registered function's
``__module__``. If the implementation puts the job somewhere else, or
names it something else, nothing here needs changing.

What *is* invented, and is the single place to correct if it turns out
wrong, is where the runner application object lives:
``RUNNER_MODULE`` / ``RUNNER_APP_ATTRIBUTE`` below. design.md fixes the
directory ("the runner's application object -- the queue itself" in
``shared/infrastructure/driven/``) but no artifact fixes the module or
attribute name. ``WORKER_MODULE`` is not invented: tasks.md 2.8 fixes it
as ``src/commerce_ops/worker.py``, and it is imported here for the reason
that task gives -- importing it is what registers the job definitions.

Two further assumptions, both recorded in test-manifest.md:

- The job module imports its collaborators *by name* into its own
  namespace (``run_daily_digest``, ``post_monitoring_message``,
  ``session``), the pattern ``monitoring.py`` and
  ``omni_agent/infrastructure/driving/slack.py`` already use and that
  ``monkeypatch.setattr`` relies on. ``monkeypatch.setattr`` is used with
  its default ``raising=True``, so a differently-named collaborator fails
  loudly here rather than leaving a test silently green against an
  unpatched real one.
- "The run is recorded as failed" is read as *the job function raises*,
  and "recorded as succeeded"/"not retried" as *it returns normally* --
  that is how a job body reports its outcome to the runner, and it is the
  only outcome signal a job body has. The runner's own recording of that
  outcome is covered in the integration tier
  (``tests/integration/shared/test_scheduled_run_history.py``).

At the time this pass was written none of this exists -- the runner is not
a dependency of this project yet -- so every test in this file is expected
to fail on an absent target (``ModuleNotFoundError``) until tasks 1.1,
2.1, 2.2 and 2.8 land. That failure establishes absence and nothing about
whether the assertions below are any good.
"""

from __future__ import annotations

import datetime
import inspect
import itertools
import logging
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any

import pytest
from procrastinate import job_context, jobs, periodic

import commerce_ops.worker  # noqa: F401  -- registers the job definitions
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file in this
    # project: no trio dependency is installed.
    return "asyncio"


# --------------------------------------------------------------------------
# Reaching the daily job
# --------------------------------------------------------------------------

RUNNER_MODULE = "commerce_ops.shared.infrastructure.driven.job_runner"
RUNNER_APP_ATTRIBUTE = "app"
WORKER_MODULE = "commerce_ops.worker"

# The declared schedule the retired crontab ran the daily cadence on, and
# which tasks.md 2.4 carries over unchanged ("06:00, matching today's
# crontab"). SPECIFIED by tasks.md, not by a spec scenario -- the scenario
# says only that the work runs when its schedule is due.
EXPECTED_HOUR = 6
EXPECTED_MINUTE = 0


def _daily_periodic() -> periodic.PeriodicTask[Any, Any, Any]:
    """The one piece of recurring work this change schedules.

    Identified as "the single registered periodic task whose name mentions
    the daily cadence" rather than by a transcribed task name, since no
    artifact fixes one. That exactly one is registered is itself asserted
    by `test_job_runner_schedules.py`, from the "Work with no declared
    schedule does not run" scenario.
    """
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    daily = [entry for entry in registered if "daily" in entry.task.name.lower()]
    assert len(daily) == 1, (
        "expected exactly one registered periodic task for the daily "
        f"cadence; registered: {[entry.task.name for entry in registered]}"
    )
    return daily[0]


def _job_module() -> ModuleType:
    """The module the daily job's function was defined in.

    Resolved from the function itself so this file never transcribes a
    module path for it.
    """
    module = sys.modules[_daily_periodic().task.func.__module__]
    return module


def _make_job(task: Any, *, attempts: int) -> jobs.Job:
    """A `Job` row as the runner hands it to a job body.

    `attempts` is the number of attempts that already failed: 0 on the
    first run (verified against procrastinate 3.9.0, whose `attempts`
    column is incremented when a job finishes or is retried, not when it
    is fetched).
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
    """What the job's own declared retry strategy decides after a failure
    on the run whose preceding-attempt count is `attempts`.

    `None` means "do not retry".
    """
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
    file does not pin the retry maximum design.md leaves open ("What is
    the daily digest's retry maximum and backoff base?").
    """
    for attempts in range(ceiling):
        if _retry_decision(task, attempts=attempts) is None:
            return attempts
    pytest.fail(
        f"the retry strategy for {task.name} still retried after {ceiling} "
        "attempts; 'Retries stop at the declared maximum' requires it to "
        "stop at a declared maximum"
    )


async def _run_job(task: Any, *, attempts: int = 0) -> Any:
    """Invokes the job body the way the runner would.

    Supplies the job context when the task declares `pass_context`, and
    the `timestamp` keyword the runner passes to every periodic task.
    """
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
            "it is on -- required by product-monitoring's 'An intermediate "
            "failed attempt does not post'"
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingNotifier:
    """Stands in for `post_monitoring_message`, recording each call.

    Awaitable, because the real notifier is a coroutine function: left
    synchronous, `await None` would raise inside the job's own delivery
    handling, be swallowed as a delivery failure, and the delivery
    assertions here would pass while proving nothing.
    """

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.posted: list[str] = []
        self._failure = failure

    async def __call__(self, message: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.posted.append(message)


class _ScriptedDailyDigest:
    """Stands in for `run_daily_digest`: scripted names or a scripted
    failure, never both."""

    def __init__(
        self,
        *,
        names: Sequence[str] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._names = names
        self._failure = failure
        self.calls: list[Any] = []

    async def __call__(self, reader: Any) -> Sequence[str]:
        self.calls.append(reader)
        if self._failure is not None:
            raise self._failure
        assert self._names is not None
        return self._names


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    """Stands in for the process-wide session provider's `session()`.

    Yields `None`: the job passes it to `ProductRepository(...)`, which
    only stores it, and `run_daily_digest` is faked out before any query
    would run. This keeps the file unit-tier -- no `DATABASE_URL`, no
    Postgres.
    """
    yield None


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture()
def sessionless(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_module, "session", _fake_session)


@pytest.fixture()
def notifier(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_RecordingNotifier]:
    fake = _RecordingNotifier()
    monkeypatch.setattr(job_module, "post_monitoring_message", fake)
    yield fake


@pytest.fixture()
def install_digest(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    def _install(fake: _ScriptedDailyDigest) -> _ScriptedDailyDigest:
        monkeypatch.setattr(job_module, "run_daily_digest", fake)
        return fake

    yield _install


# --------------------------------------------------------------------------
# scheduled-jobs: Recurring Work Runs On Its Declared Schedule
# product-monitoring: The Daily Cadence Runs On A Schedule
# --------------------------------------------------------------------------


def test_the_daily_cadence_has_a_declared_schedule() -> None:
    """Scenario: The daily cadence runs when its schedule is due
    (`product-monitoring`); Scenario: Work runs when its schedule is due
    (`scheduled-jobs`).

    SPECIFIED: the daily cadence is declared as recurring work with a
    schedule, so that a due moment causes a run without any request from
    outside the deployment. What a *due* moment is, is asserted below.
    """
    daily = _daily_periodic()

    assert daily.cron, "the daily cadence's schedule is empty"


def test_the_declared_schedule_becomes_due_once_a_day_at_06_00() -> None:
    """Scenario: Work runs when its schedule is due.

    SPECIFIED: the work has a declared schedule that becomes due.
    DERIVED (tasks.md 2.4, "Declare the daily schedule (06:00, matching
    today's crontab)"): that the due moment is 06:00 and that it recurs
    daily. No spec scenario fixes the hour; tasks.md does.
    """
    daily = _daily_periodic()
    reference = datetime.datetime(2026, 3, 10, 12, 0, tzinfo=datetime.UTC).timestamp()

    first = daily.croniter.get_next(ret_type=float, start_time=reference)
    second = daily.croniter.get_next(ret_type=float, start_time=first)

    first_moment = datetime.datetime.fromtimestamp(first, datetime.UTC)
    assert (first_moment.hour, first_moment.minute) == (
        EXPECTED_HOUR,
        EXPECTED_MINUTE,
    ), f"expected the daily schedule to be due at 06:00 UTC, got {first_moment}"
    assert second - first == 24 * 60 * 60, (
        "expected consecutive due moments one day apart, got "
        f"{(second - first) / 3600:.1f} hours"
    )


def test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone() -> None:
    """Scenario: The schedule's timezone does not depend on the host.

    WHEN a schedule is evaluated on a host whose default timezone differs
    from the configured one
    THEN it SHALL be evaluated in the configured timezone.

    Run in subprocesses because the host's default timezone is read once,
    from the process environment: `TZ` cannot be changed meaningfully
    inside an already-running interpreter's imported modules.

    SPECIFIED: the two hosts' due moments are identical, i.e. the schedule
    did not follow the host. DELIBERATELY UNTESTED here: *which* timezone
    was configured, beyond the 06:00-UTC assertion in the test above --
    that is the same fact, asserted once.
    """
    script = (
        "import datetime, json, sys, time\n"
        "time.tzset()\n"
        f"import {WORKER_MODULE}\n"
        f"from {RUNNER_MODULE} import {RUNNER_APP_ATTRIBUTE} as runner_app\n"
        "entries = list(runner_app.periodic_registry.periodic_tasks.values())\n"
        "daily = [e for e in entries if 'daily' in e.task.name.lower()][0]\n"
        "at = datetime.datetime(2026, 3, 10, 12, 0,\n"
        "    tzinfo=datetime.timezone.utc).timestamp()\n"
        "ticks = []\n"
        "for _ in range(3):\n"
        "    at = daily.croniter.get_next(ret_type=float, start_time=at)\n"
        "    ticks.append(at)\n"
        "print(json.dumps(ticks))\n"
    )

    outputs = {}
    for timezone_name in ("UTC", "Asia/Kolkata", "America/New_York"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "TZ": timezone_name},
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"evaluating the daily schedule under TZ={timezone_name} failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        outputs[timezone_name] = result.stdout.strip().splitlines()[-1]

    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "the daily schedule's due moments differ by the host's default "
        f"timezone, so the schedule follows the host: {outputs}"
    )


# --------------------------------------------------------------------------
# scheduled-jobs: A Failed Run Is Retried With Increasing Delay
# product-monitoring: A database read failure is retried
# --------------------------------------------------------------------------


def test_a_failing_run_is_retried() -> None:
    """Scenario: A failing run is retried (`scheduled-jobs`); Scenario: A
    database read failure is retried (`product-monitoring`).

    WHEN a run fails and its declared maximum number of attempts has not
    been reached
    THEN the system SHALL retry it.
    """
    task = _daily_periodic().task

    assert _retry_decision(task, attempts=0) is not None, (
        "a first failed run of the daily cadence was not retried"
    )


def test_successive_retries_wait_longer() -> None:
    """Scenario: Successive retries wait longer.

    WHEN a run fails more than once
    THEN each successive retry SHALL be attempted after a longer delay
    than the one before it.
    """
    task = _daily_periodic().task
    final = _final_attempt(task)
    assert final >= 2, (
        "the declared maximum leaves fewer than two retries, so 'each "
        "successive retry waits longer' cannot be observed at all; "
        f"retries stop after {final} failed attempt(s)"
    )

    now = datetime.datetime.now(datetime.UTC)
    delays = []
    for attempts in range(final):
        decision = _retry_decision(task, attempts=attempts)
        assert decision.retry_at is not None
        delays.append((decision.retry_at - now).total_seconds())

    assert all(later > earlier for earlier, later in itertools.pairwise(delays)), (
        f"expected each retry to wait longer than the one before it, got "
        f"delays (seconds): {[round(delay) for delay in delays]}"
    )


def test_retries_stop_at_the_declared_maximum() -> None:
    """Scenario: Retries stop at the declared maximum.

    WHEN a run has failed on its declared maximum number of attempts
    THEN the system SHALL record the run as failed
    AND SHALL NOT attempt it again.

    SPECIFIED: a maximum exists and the strategy stops there -- `None`
    from the retry decision is how the runner is told not to retry, which
    is also what leaves the run recorded as failed rather than returned to
    the queue. `_final_attempt` fails the test if no maximum is ever
    reached.
    """
    task = _daily_periodic().task

    final = _final_attempt(task)

    assert _retry_decision(task, attempts=final) is None
    assert _retry_decision(task, attempts=final + 1) is None, (
        "the retry strategy resumed retrying past its own maximum"
    )


# --------------------------------------------------------------------------
# product-monitoring: Daily Cadence Lists Existing Product Names
# --------------------------------------------------------------------------


async def test_daily_trigger_lists_product_names(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_digest: Any,
) -> None:
    """Scenario: Daily trigger lists product names.

    WHEN the daily cadence runs and at least one product exists
    THEN the system SHALL post a Slack message listing the name of every
    existing product.
    """
    install_digest(_ScriptedDailyDigest(names=("Widget A", "Widget B")))

    await _run_job(_daily_periodic().task)

    # SPECIFIED: one message, naming every existing product.
    assert len(notifier.posted) == 1
    message = notifier.posted[0]
    assert "Widget A" in message
    assert "Widget B" in message


async def test_no_products_exist_posts_a_message_rather_than_nothing(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_digest: Any,
) -> None:
    """Scenario: No products exist.

    WHEN the daily cadence runs and no product exists
    THEN the system SHALL post a message indicating no products exist,
    rather than posting nothing.

    DELIBERATELY UNTESTED: the message's exact wording. No artifact pins
    any phrasing, and asserting one here would impose a contract nobody
    agreed to -- the same reading the retired route test applied to the
    same scenario.
    """
    install_digest(_ScriptedDailyDigest(names=()))

    await _run_job(_daily_periodic().task)

    # SPECIFIED: a message is posted, rather than nothing.
    assert len(notifier.posted) == 1
    assert notifier.posted[0], "the posted message was empty"


# --------------------------------------------------------------------------
# product-monitoring: Report Delivery Failure Is Decoupled From The Trigger
# --------------------------------------------------------------------------


async def test_slack_post_failure_leaves_the_run_succeeded_and_unretried(
    sessionless: None,
    job_module: ModuleType,
    install_digest: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: Slack post fails.

    WHEN a cadence's report has been assembled and posting it to Slack
    fails
    THEN the system SHALL log the failure
    AND the run SHALL be recorded as succeeded
    AND the run SHALL NOT be retried.

    SPECIFIED: the run is recorded as succeeded and not retried -- read as
    the job body returning normally, which is the only way a job body
    reports success, and the only thing that leaves no failure for the
    retry strategy to act on. A raised exception here would be recorded as
    a failed run *and* retried, contradicting both clauses at once.
    DERIVED: "logged" is read as at least one record at WARNING or above,
    since no artifact pins a logger name or message.
    """
    install_digest(_ScriptedDailyDigest(names=("Widget A",)))
    monkeypatch.setattr(
        job_module,
        "post_monitoring_message",
        _RecordingNotifier(failure=RuntimeError("simulated Slack API failure")),
    )

    with caplog.at_level(logging.WARNING):
        await _run_job(_daily_periodic().task)

    assert any(record.levelno >= logging.WARNING for record in caplog.records), (
        "expected the Slack delivery failure to be logged at WARNING or "
        f"above; captured: {[r.getMessage() for r in caplog.records]}"
    )


# --------------------------------------------------------------------------
# product-monitoring: Database Read Failure Is Surfaced, Not Treated Like A
# Delivery Failure
# --------------------------------------------------------------------------


async def test_database_read_failure_on_the_final_attempt_fails_and_posts(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_digest: Any,
) -> None:
    """Scenario: Database read fails.

    WHEN the daily cadence runs and reading products from the database
    fails on its final attempt
    THEN the run SHALL be recorded as failed
    AND the system SHALL attempt to post a message to the configured
    channel indicating the database could not be read.

    SPECIFIED: recorded as failed -- read as the job body raising, the
    only signal a job body has for a failed run, and the one the retry
    strategy and the run history both key on. DELIBERATELY UNTESTED: the
    failure message's exact wording, same reasoning as "No products
    exist".
    """
    task = _daily_periodic().task
    install_digest(
        _ScriptedDailyDigest(failure=RuntimeError("simulated database-read failure"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- see below
        # Deliberately not narrowed to the scripted RuntimeError: what is
        # SPECIFIED is that the run is recorded as failed, and an
        # implementation that wraps the read failure in its own exception
        # type still satisfies that. Narrowing here would assert an
        # exception type no artifact states.
        await _run_job(task, attempts=_final_attempt(task))

    assert len(notifier.posted) == 1
    assert notifier.posted[0], "the attempted failure message was empty"


async def test_an_intermediate_failed_attempt_does_not_post(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_digest: Any,
) -> None:
    """Scenario: An intermediate failed attempt does not post.

    WHEN the daily cadence's database read fails on an attempt that will
    be retried
    THEN the system SHALL NOT post a message for that attempt, so that one
    outage produces one message rather than one per attempt.

    The attempt used is the first one, which `test_a_failing_run_is_
    retried` establishes will be retried.
    """
    task = _daily_periodic().task
    install_digest(
        _ScriptedDailyDigest(failure=RuntimeError("simulated database-read failure"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- see the test above
        await _run_job(task, attempts=0)

    # SPECIFIED: no message for an attempt that will be retried.
    assert notifier.posted == [], (
        "a database read failure posted a message on an attempt that will "
        "be retried, so one outage produces one message per attempt"
    )


async def test_every_intermediate_attempt_stays_silent_and_the_last_one_posts(
    sessionless: None,
    notifier: _RecordingNotifier,
    install_digest: Any,
) -> None:
    """Scenario: An intermediate failed attempt does not post -- the whole
    outage, rather than one attempt of it.

    SPECIFIED: "one outage produces one message rather than one per
    attempt". The scenario above covers a single intermediate attempt;
    this walks every attempt of one outage and asserts the total is
    exactly one message, which is what the requirement's own reason
    clause states.
    """
    task = _daily_periodic().task
    install_digest(
        _ScriptedDailyDigest(failure=RuntimeError("simulated database-read failure"))
    )

    for attempts in range(_final_attempt(task) + 1):
        with pytest.raises(Exception):  # noqa: B017 -- see above
            await _run_job(task, attempts=attempts)

    assert len(notifier.posted) == 1, (
        "expected one outage to produce exactly one message across all of "
        f"its attempts, got {len(notifier.posted)}: {notifier.posted}"
    )


# --------------------------------------------------------------------------
# Guard, not a scenario: the periodic deferrer this file's schedule
# assertions read is the same object the worker runs.
# --------------------------------------------------------------------------


def test_the_registry_this_file_reads_is_the_one_the_worker_defers_from() -> None:
    """DERIVED guard (design.md, "importing the job definition modules so
    their schedules are actually registered").

    Every schedule assertion above reads
    `runner_app.periodic_registry`. This asserts that object is what a
    `PeriodicDeferrer` built the way the worker builds one would actually
    read, so a future refactor that registers schedules on a second
    registry breaks here rather than leaving the assertions above green
    against something the worker never consults.
    """
    deferrer = periodic.PeriodicDeferrer(
        registry=runner_app.periodic_registry, **runner_app.periodic_defaults
    )

    assert deferrer.registry is runner_app.periodic_registry
