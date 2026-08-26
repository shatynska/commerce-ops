"""A launch source that cannot supply reports, as the briefing reports it.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/briefing/spec.md`

Covers, from the ADDED requirement *A launch source that cannot supply
reports is reported, not treated as a clean day*, all five scenarios:

- *A failure to post the message does not fail the run*
- *An unavailable launch source posts a message rather than nothing*
- *An unavailable launch source is not a clean day*
- *An unavailable launch source is not an assembly failure*
- *The condition is reported on each run while it persists*

And from the MODIFIED requirement *A failure to assemble is surfaced, not
treated like a delivery failure*, its one new scenario:

- *A source that cannot supply reports is not a read failure*

That requirement's three existing scenarios are unchanged and keep their
tests in `test_daily_briefing_job.py`.

## Level

The job, for the same reason `test_daily_briefing_job.py` gives for the
assembly-failure scenarios: what distinguishes this condition's outcome
from an assembly failure's is *whether the run is recorded as failed* and
*whether it is retried*, and a job body's outcome signal — raising or
returning — is the only place either is observable. `tasks.md` 4.6 also
places the handling here, ahead of the generic assembly-failure branch.

## Reading the outcome clauses

"Recorded as succeeded" is read as *the job body returns normally*;
"recorded as failed" as *it raises*; "is not retried" as the same, since
the runner retries on a raised body alone. That is the reading
`test_daily_briefing_job.py` already recorded for the same words in the
same capability.

## Why this file names nothing from `launch`

Deliberate, and it is the point of `tasks.md` 5.10. The condition is a
**briefing-owned** type carrying opaque identifier strings; the translation
from `launch`'s `PlaybookNotReadyError` happens in `worker.py` and is
tested separately in
`tests/unit/test_worker_translates_unready_playbook.py`. A test here that
imported `launch` would quietly establish the coupling `design.md` says the
briefing does not have.

## What is fixed, and what is INVENTED

Fixed by the artifacts: that the condition is a sibling of `BriefingError`
in `briefing.domain.attention`, re-exported from `briefing.application`,
carrying opaque identifier strings (`tasks.md` 4.4); that the job handles it
ahead of the assembly-failure branch, posts through the existing
`_attempt_post` so a delivery failure is logged and does not fail the run,
records the run as succeeded and assembles nothing (`tasks.md` 4.6).

INVENTED, each with a correction point below:

- The condition type's **name**. `_condition_type()` probes
  `_CONDITION_NAMES` on the briefing's public surface and fails loudly
  rather than defaulting.
- Its constructor shape. `_condition(...)` probes.
- The job's notifier injection point, transcribed from
  `test_daily_briefing_job.py`'s `NOTIFIER_ATTRIBUTES`.

## Expected first-run state

The condition type does not exist, so every test here is expected to fail
on an absent target — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import inspect
import sys
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any, Final

import pytest
from procrastinate import job_context, jobs, periodic

import commerce_ops.briefing.application as briefing_application
import commerce_ops.worker  # noqa: F401  -- registers the job definitions
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio

NOTIFIER_ATTRIBUTES: Final = ("post_monitoring_message", "notifier")

# The identifiers the source carries. Two, because *An unavailable launch
# source posts a message rather than nothing* says "carrying two gate
# identifiers" and asserts "one message is posted naming those gates" —
# a single identifier would not establish that both are named.
CARRIED_IDENTIFIERS: Final = ("ignition", "graduated")

# INVENTED — the briefing-owned condition's name. `tasks.md` 4.4 fixes what
# it means and where it lives, not its spelling.
_CONDITION_NAMES: Final = (
    "LaunchReportsUnavailableError",
    "ReportsUnavailableError",
    "SourceUnavailableError",
    "LaunchSourceUnavailableError",
    "ReportSourceUnavailable",
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# The briefing-owned condition — the single correction point
# --------------------------------------------------------------------------


def _condition_type() -> type[Exception]:
    for name in _CONDITION_NAMES:
        found = getattr(briefing_application, name, None)
        if isinstance(found, type) and issubclass(found, BaseException):
            return found  # type: ignore[return-value]
    pytest.fail(
        "commerce_ops.briefing.application exports no condition meaning "
        "'the launch source cannot supply reports' under any of "
        f"{_CONDITION_NAMES} (`tasks.md` 4.4) — correct this file's probe "
        "to the implemented name"
    )


def _condition(identifiers: tuple[str, ...] = CARRIED_IDENTIFIERS) -> Exception:
    condition = _condition_type()
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"identifiers": identifiers}),
        ((), {"reasons": identifiers}),
        ((identifiers,), {}),
        ((", ".join(identifiers),), {}),
    )
    for args, kwargs in attempts:
        try:
            return condition(*args, **kwargs)
        except TypeError:
            continue
    pytest.fail(
        f"could not construct {condition.__name__} carrying opaque "
        "identifier strings under any probed signature; correct "
        "`_condition` to the implemented one"
    )


# --------------------------------------------------------------------------
# Reaching the briefing job — transcribed from `test_daily_briefing_job.py`
# --------------------------------------------------------------------------


def _briefing_periodic() -> periodic.PeriodicTask[Any, Any, Any]:
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
    assert strategy is not None
    return strategy.get_retry_decision(
        exception=RuntimeError("simulated failure"),
        job=_make_job(task, attempts=attempts),
    )


def _final_attempt(task: Any, *, ceiling: int = 50) -> int:
    for attempts in range(ceiling):
        if _retry_decision(task, attempts=attempts) is None:
            return attempts
    pytest.fail(
        f"the retry strategy for {task.name} still retried after {ceiling} attempts"
    )


async def _run_job(task: Any, *, attempts: int = 0) -> Any:
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
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingNotifier:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.posted: list[str] = []
        self.attempts = 0
        self._failure = failure

    async def post_monitoring_message(self, message: str) -> None:
        self.attempts += 1
        if self._failure is not None:
            raise self._failure
        self.posted.append(message)

    async def __call__(self, message: str) -> None:
        await self.post_monitoring_message(message)


class _ScriptedBriefingRun:
    """Stands in for `run_daily_briefing`.

    Either it completes, or it raises the scripted condition. The condition
    reaches the job by propagating out of the use case, which is where the
    port raised it — `tasks.md` 4.6 has the job handle it "ahead of the
    generic assembly-failure branch", so the job is what sees it.
    """

    def __init__(self, *, failure: Exception | None = None) -> None:
        self._failure = failure
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        if self._failure is not None:
            raise self._failure


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def job_module() -> ModuleType:
    return _job_module()


@pytest.fixture(autouse=True)
def sessionless(job_module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_module, "session", _fake_session, raising=False)


def install_notifier(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    notifier: _RecordingNotifier,
) -> _RecordingNotifier:
    installed = [name for name in NOTIFIER_ATTRIBUTES if hasattr(job_module, name)]
    assert installed, (
        f"{job_module.__name__} exposes none of {NOTIFIER_ATTRIBUTES}, so "
        "the job has no notifier injection point and cannot post the "
        "message this requirement asks for"
    )
    for name in installed:
        monkeypatch.setattr(job_module, name, notifier)
    return notifier


@pytest.fixture()
def notifier(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_RecordingNotifier]:
    yield install_notifier(job_module, monkeypatch, _RecordingNotifier())


@pytest.fixture()
def install_run(
    job_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    def _install(fake: _ScriptedBriefingRun) -> _ScriptedBriefingRun:
        monkeypatch.setattr(job_module, "run_daily_briefing", fake)
        return fake

    yield _install


# --------------------------------------------------------------------------
# Requirement (ADDED): A launch source that cannot supply reports is
# reported, not treated as a clean day
# --------------------------------------------------------------------------


async def test_an_unavailable_launch_source_posts_a_message_rather_than_nothing(
    sessionless: None, notifier: _RecordingNotifier, install_run: Any
) -> None:
    """Scenario: An unavailable launch source posts a message rather than
    nothing.

    WHEN the daily briefing runs and its launch-report source reports it
    cannot supply reports, carrying two gate identifiers
    THEN one message is posted naming those gates
    AND the run is recorded as succeeded.
    """
    task = _briefing_periodic().task
    install_run(_ScriptedBriefingRun(failure=_condition()))

    # SPECIFIED: the run is recorded as succeeded — no `pytest.raises`;
    # returning normally is the assertion.
    await _run_job(task)

    # SPECIFIED: one message is posted...
    assert len(notifier.posted) == 1, (
        f"expected exactly one message posted, got {notifier.posted}"
    )
    # ...naming those gates. The briefing treats them as opaque strings, so
    # what is asserted is that both appear, not how they are phrased.
    message = notifier.posted[0]
    for identifier in CARRIED_IDENTIFIERS:
        assert identifier in message, (
            f"the posted message does not name the carried identifier "
            f"{identifier!r}: {message!r}"
        )


async def test_an_unavailable_launch_source_is_not_a_clean_day(
    sessionless: None, notifier: _RecordingNotifier, install_run: Any
) -> None:
    """Scenario: An unavailable launch source is not a clean day.

    WHEN the daily briefing runs and its launch-report source reports it
    cannot supply reports
    THEN no briefing is assembled, and the message posted states the source
    could not supply reports rather than reporting an absence of attention
    items.

    "No briefing is assembled" is asserted as *exactly one message was
    posted and it is the condition's*: a briefing that had been assembled
    and found clean would post nothing at all (the clean-day rule), which
    is the silence this requirement exists to prevent — so a run posting
    zero messages fails here.

    DELIBERATELY UNTESTED: the message's wording beyond naming the carried
    identifiers. No artifact pins a phrasing, and asserting one would
    impose a contract nobody agreed to — the reading
    `test_daily_briefing_job.py` recorded for the assembly-failure message.
    """
    task = _briefing_periodic().task
    install_run(_ScriptedBriefingRun(failure=_condition()))

    await _run_job(task)

    assert len(notifier.posted) == 1, (
        "an unavailable launch source produced "
        f"{len(notifier.posted)} messages; zero is the clean-day silence "
        "this requirement forbids"
    )
    assert all(identifier in notifier.posted[0] for identifier in CARRIED_IDENTIFIERS)


async def test_an_unavailable_launch_source_is_not_an_assembly_failure(
    sessionless: None, notifier: _RecordingNotifier, install_run: Any
) -> None:
    """Scenario: An unavailable launch source is not an assembly failure.

    WHEN the daily briefing runs and its launch-report source reports it
    cannot supply reports
    THEN the run is not recorded as failed, is not retried, and does not
    produce the message an assembly failure produces.

    Also covers, from the MODIFIED requirement *A failure to assemble is
    surfaced, not treated like a delivery failure*, its scenario *A source
    that cannot supply reports is not a read failure* — same WHEN, and its
    THEN ("this requirement does not apply, and the run is not recorded as
    failed") is the first clause here.

    Run on the **final** attempt, which is where an assembly failure both
    fails the run and posts its message: on any earlier attempt an
    implementation mishandling the condition would post nothing and the
    message assertion could not discriminate.
    """
    task = _briefing_periodic().task
    install_run(_ScriptedBriefingRun(failure=_condition()))

    # SPECIFIED: not recorded as failed, and not retried — the job returns
    # rather than raising, which is the only signal for either.
    await _run_job(task, attempts=_final_attempt(task))

    # SPECIFIED: it does not produce the message an assembly failure
    # produces. Distinguished by content, not by count: both paths post one
    # message, and only this one names the carried identifiers.
    assert len(notifier.posted) == 1
    message = notifier.posted[0]
    assert all(identifier in message for identifier in CARRIED_IDENTIFIERS), (
        "the message posted is not the one naming the carried identifiers, "
        f"so the assembly-failure branch claimed this condition: {message!r}"
    )


async def test_the_condition_is_reported_on_each_run_while_it_persists(
    sessionless: None, notifier: _RecordingNotifier, install_run: Any
) -> None:
    """Scenario: The condition is reported on each run while it persists.

    WHEN the daily briefing runs on consecutive days and its launch-report
    source reports the same condition each time
    THEN a message is posted on each of those runs.

    Deliberately not suppressed to one message per outage: "the existing
    suppression hook is retry exhaustion, which a run recorded as succeeded
    never reaches". So this is the direct inverse of
    `test_daily_briefing_job.py::test_one_outage_produces_exactly_one_message`,
    and an implementation reusing that suppression here fails it.

    Two consecutive runs, both first attempts — which is what a succeeded
    run's successor always is, since a succeeded run is never retried.
    """
    task = _briefing_periodic().task
    install_run(_ScriptedBriefingRun(failure=_condition()))

    await _run_job(task)
    await _run_job(task)

    assert len(notifier.posted) == 2, (
        "the condition was reported on fewer than both consecutive runs, so "
        "a deployment being set up goes quiet about what is still missing; "
        f"posted: {notifier.posted}"
    )


async def test_a_failure_to_post_the_message_does_not_fail_the_run(
    job_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sessionless: None,
    install_run: Any,
) -> None:
    """Scenario: A failure to post the message does not fail the run.

    WHEN the message naming the carried identifiers cannot be delivered
    THEN the failure is logged, the run is still recorded as succeeded, and
    it is not retried.

    Without this, "a Slack outage during a stand-down would fail a run this
    requirement has just said succeeds" — the capability's existing
    assembly/delivery decoupling is scoped to a briefing that *was*
    assembled, so it does not reach a message posted when nothing was.
    """
    task = _briefing_periodic().task
    failing = install_notifier(
        job_module,
        monkeypatch,
        _RecordingNotifier(failure=RuntimeError("simulated Slack outage")),
    )
    install_run(_ScriptedBriefingRun(failure=_condition()))

    # SPECIFIED: the run is still recorded as succeeded, and not retried —
    # returning normally is the assertion.
    await _run_job(task)

    # Precondition: delivery really was attempted, so the assertion above
    # cannot pass for the wrong reason (a job that posted nothing at all).
    assert failing.attempts == 1, (
        "the message was never attempted, so this test establishes nothing "
        "about a delivery failure"
    )
    assert failing.posted == []


async def test_a_successful_run_still_leaves_the_condition_path_unreached(
    sessionless: None, notifier: _RecordingNotifier, install_run: Any
) -> None:
    """DERIVED control, not a scenario.

    Every assertion above observes a run whose source reported the
    condition. Without this, a job body that always posted the condition
    message would satisfy all of them, and the clean-day rule — which this
    requirement is careful *not* to override for an ordinary run — would be
    unreachable in practice.
    """
    task = _briefing_periodic().task
    run = install_run(_ScriptedBriefingRun())

    await _run_job(task)

    assert run.calls == 1
    assert notifier.posted == [], (
        "the job posted the unavailable-source message on a run whose source "
        f"reported nothing of the kind: {notifier.posted}"
    )
