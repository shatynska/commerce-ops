"""The overdue check: what it determines, what it reports, and once.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Work Is Overdue Relative To Its Last Success Or To When It Was First
  Known" / Scenarios: Work is overdue after its tolerance elapses since its
  last success; Work that has never succeeded becomes overdue after its
  tolerance; A freshly deployed system does not report work as overdue
  immediately; Work within its tolerance is not overdue
- "Overdue Work Is Reported To Slack From Inside The Deployment" /
  Scenarios: Overdue work is reported; Work within its tolerance is not
  reported; Work with no declared schedule is never reported
- "The Process Running Scheduled Work Is Itself Monitored Work" / Scenario:
  A completed evaluation records a successful run despite a failed delivery
- "A Continuing Outage Is Reported Once, Not Repeatedly" / Scenarios: A
  continuing outage is not reported repeatedly; A failed delivery leaves
  the work eligible to be reported again; A restart does not resume
  reporting; Overdueness recurring after a success is reported again

See `test-manifest.md` at the change root for the full
specified/derived/deliberately-untested accounting and for the unresolved
project questions this file's assumptions are recorded under.

## How the check is reached, and what is not invented

The check is never named here. It is reached the way the runner reaches it
-- through the runner application object's periodic registry -- filtered by
the one placement tasks.md 4.1 does fix: the overdue check is a scheduled
job in ``shared/infrastructure/driving/``. Its module is then reached
through the registered function's ``__module__``. So neither its module
name, its function name, its task name nor its schedule is transcribed.

``commerce_ops.registrations.register_all`` is fixed by tasks.md 1.3 and is
called at module import here because it is what registers the check with
the runner.

"The run is recorded as successful" is read as *the job body returns
normally*, and "recorded as failed" as *it raises* -- the same reading
``tests/unit/products/infrastructure/driving/test_daily_digest_job.py``
records, and the only outcome signal a job body has. The runner's own
recording of that outcome is covered in the integration tier.

## THE SEAM CONTRACT -- the single largest invented surface in this pass

No artifact fixes how the check reaches its collaborators. This file
assumes the pattern ``daily_digest_job.py`` and ``monitoring.py`` already
use in this project: collaborators are imported **by name** into the job
module's own namespace and referenced as bare globals in the job body,
which is what lets a test substitute them with ``monkeypatch.setattr``.
The names assumed, all in the check module's namespace:

- ``registered_work()`` -- the registry accessor (sync)
- ``last_successful_run(name)`` -- the prerequisite's accessor (async);
  this name alone is *not* invented, it already exists in
  ``shared/infrastructure/driven/job_history.py``
- ``first_known_times()`` -- the anchors, as a mapping (async)
- ``record_first_known(identifiers)`` -- the idempotent upsert (async,
  tasks.md 3.2a); substituted only to keep this tier off the database, and
  nothing here asserts on it
- ``suppressed_identifiers()`` -- work already reported for its current
  period of overdueness (async)
- ``record_report_delivered(identifier)`` -- written only after a delivery
  succeeds (async, tasks.md 3.5)
- ``clear_report_suppression(identifier)`` -- cleared when the work next
  succeeds (async, tasks.md 3.6)
- ``notifier`` -- the ``MonitoringNotifier`` ``worker.py`` injects after
  ``register_all()`` (tasks.md 4.2)

``_substitute`` fails with an instructive message rather than an
``AttributeError`` when one of these is absent, so that an implementation
which reaches its collaborators differently produces a legible directive
instead of a puzzle. Correcting these names is a fixture correction; the
assertions below are about what is determined and what is posted, not
about where the collaborators live.

At the time this pass was written the check does not exist. Every test
here is expected to fail on an absent target until tasks 1.3, 4.1 and 4.2
land, and that failure establishes absence and nothing about whether the
assertions are any good.
"""

from __future__ import annotations

import dataclasses
import datetime
import inspect
import sys
import time
from collections.abc import Iterable, Mapping
from types import ModuleType
from typing import Any

import pytest
from procrastinate import job_context, jobs

from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio

# tasks.md 4.1 fixes the check's home; nothing else about it is transcribed.
OVERDUE_CHECK_PACKAGE = "commerce_ops.shared.infrastructure.driving"

SEAM_MESSAGE = (
    "the overdue check's module {module} exposes no module-level name "
    "{name!r}, so a test cannot substitute it. This file assumes the "
    "collaborator pattern daily_digest_job.py already uses -- imported by "
    "name into the job module's namespace and referenced as a bare global. "
    "See this file's SEAM CONTRACT docstring and test-manifest.md's "
    "unresolved project questions; correcting the name is a fixture "
    "correction, not a change to what is asserted."
)

# Registering the check with the runner is the point of importing this.
register_all()

_NOW = datetime.datetime.now(datetime.UTC)
# Every time in this module is an offset from this reference, so it has to
# be the same "now" the implementation reads. Pinning it to a fixed past
# date made every offset stale the moment the clock moved past it: work
# placed "10 minutes ago" was really two days ago, and scenarios written
# as within-tolerance evaluated as overdue. No collaborator substitutes a
# clock, so the reference must be the real one.
TOLERANCE = datetime.timedelta(hours=4)

WORK_ID = "shared.scheduled-runs.overdue-check-subject"
OTHER_WORK_ID = "shared.scheduled-runs.other-subject"
# Work the runner does run but that nothing declares a schedule for -- the
# four suspended cadences are the real instances (design.md, Non-Goals).
UNREGISTERED_WORK_ID = "products.monitoring.quarterly"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file in this
    # project: no trio dependency is installed.
    return "asyncio"


# --------------------------------------------------------------------------
# Reaching the check
# --------------------------------------------------------------------------


def _overdue_check_periodic() -> Any:
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    in_shared_driving = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(OVERDUE_CHECK_PACKAGE)
    ]
    assert len(in_shared_driving) == 1, (
        "expected exactly one scheduled job under "
        f"{OVERDUE_CHECK_PACKAGE!r} -- the overdue check, whose placement "
        "tasks.md 4.1 fixes. Registered periodics: "
        f"{[(entry.task.name, entry.task.func.__module__) for entry in registered]}"
    )
    return in_shared_driving[0]


def _check_module() -> ModuleType:
    return sys.modules[_overdue_check_periodic().task.func.__module__]


def _substitute(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, name: str, value: Any
) -> None:
    if not hasattr(module, name):
        pytest.fail(SEAM_MESSAGE.format(module=module.__name__, name=name))
    monkeypatch.setattr(module, name, value)


async def _run_check() -> Any:
    """Invokes the check's job body the way the runner would."""
    entry = _overdue_check_periodic()
    task = entry.task
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
        kwargs["timestamp"] = int(_NOW.timestamp())
    return await task.func(*args, **kwargs)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Registration:
    identifier: str
    task_name: str
    schedule: str
    tolerance: datetime.timedelta


class _RecordingNotifier:
    """Stands in for the injected `MonitoringNotifier`.

    Awaitable, because the port declares `post_monitoring_message` async
    (tasks.md 2.1): left synchronous, `await None` would raise inside
    whatever handles a delivery failure and every delivery assertion here
    would pass while proving nothing.
    """

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.posted: list[str] = []
        self.failure = failure

    async def post_monitoring_message(self, message: str) -> None:
        if self.failure is not None:
            raise self.failure
        self.posted.append(message)


class _RecordedState:
    """The recorded state the check reads and writes, held in memory.

    Every method is async because its real counterpart reads or writes
    Postgres. Nothing here is a database: this tier is I/O-free by
    `AGENTS.md`'s testing strategy, and the durable half of these
    behaviours is covered in `tests/integration/shared/`.
    """

    def __init__(
        self,
        *,
        registry: Mapping[str, _Registration],
        last_success: Mapping[str, datetime.datetime] | None = None,
        first_known: Mapping[str, datetime.datetime] | None = None,
        suppressed: Iterable[str] = (),
    ) -> None:
        self.registry = dict(registry)
        self.last_success = dict(last_success or {})
        self.first_known = dict(first_known or {})
        self.suppressed = set(suppressed)
        self.anchored: list[list[str]] = []
        self.cleared: list[str] = []

    def registered_work(self) -> Mapping[str, _Registration]:
        return self.registry

    async def last_successful_run(self, name: str) -> datetime.datetime | None:
        return self.last_success.get(name)

    async def first_known_times(self) -> Mapping[str, datetime.datetime]:
        return dict(self.first_known)

    async def record_first_known(self, identifiers: Iterable[str]) -> None:
        recorded = list(identifiers)
        self.anchored.append(recorded)
        for identifier in recorded:
            self.first_known.setdefault(identifier, _NOW)

    async def suppressed_identifiers(self) -> set[str]:
        return set(self.suppressed)

    async def record_report_delivered(self, identifier: str) -> None:
        self.suppressed.add(identifier)

    async def clear_report_suppression(self, identifier: str) -> None:
        self.cleared.append(identifier)
        self.suppressed.discard(identifier)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    state: _RecordedState,
    notifier: _RecordingNotifier,
) -> None:
    module = _check_module()
    _substitute(monkeypatch, module, "registered_work", state.registered_work)
    _substitute(monkeypatch, module, "last_successful_run", state.last_successful_run)
    _substitute(monkeypatch, module, "first_known_times", state.first_known_times)
    _substitute(
        monkeypatch, module, "suppressed_identifiers", state.suppressed_identifiers
    )
    _substitute(
        monkeypatch, module, "record_report_delivered", state.record_report_delivered
    )
    _substitute(
        monkeypatch, module, "clear_report_suppression", state.clear_report_suppression
    )
    _substitute(monkeypatch, module, "notifier", notifier)
    # Not asserted on anywhere in this file: substituted only so the check's
    # own anchor upsert (tasks.md 3.2a) does not reach the database from a
    # unit-tier test. `raising=False` deliberately -- if the check performs
    # the upsert under another name the substitution simply does not apply,
    # and the resulting database access fails loudly rather than passing.
    monkeypatch.setattr(
        module, "record_first_known", state.record_first_known, raising=False
    )


def _one_work(
    *,
    last_success: datetime.datetime | None = None,
    first_known: datetime.datetime | None = None,
    suppressed: Iterable[str] = (),
) -> _RecordedState:
    registration = _Registration(
        identifier=WORK_ID,
        task_name=WORK_ID,
        schedule="0 * * * *",
        tolerance=TOLERANCE,
    )
    return _RecordedState(
        registry={WORK_ID: registration},
        last_success={WORK_ID: last_success} if last_success else {},
        first_known={WORK_ID: first_known} if first_known else {},
        suppressed=suppressed,
    )


def _mentions(notifier: _RecordingNotifier, identifier: str) -> bool:
    return any(identifier in message for message in notifier.posted)


# --------------------------------------------------------------------------
# Requirement: Work Is Overdue Relative To Its Last Success Or To When It
# Was First Known
#
# "Considered overdue" is observed here through the check's own reporting:
# the check reports exactly the work it considers overdue, which is the
# only observation the check itself affords. The freshness interface's
# verdict on the same state is asserted in
# test_overdue_consumers_agree.py, per the "Every consumer reads the same
# declaration" scenario.
# --------------------------------------------------------------------------


async def test_work_is_overdue_after_its_tolerance_elapses_since_its_last_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Work is overdue after its tolerance elapses since its last
    success.

    WHEN a piece of recurring work's declared tolerance has elapsed since
    its most recent successful run
    THEN it SHALL be considered overdue.

    SPECIFIED. The last success is placed an hour past the tolerance
    rather than a second past it, so the verdict does not turn on how the
    boundary is rounded -- the boundary itself is deliberately untested,
    recorded in test-manifest.md.
    """
    state = _one_work(last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert _mentions(notifier, WORK_ID), (
        f"{WORK_ID} last succeeded more than its {TOLERANCE} tolerance ago "
        f"and was not considered overdue; posted: {notifier.posted}"
    )


async def test_work_that_has_never_succeeded_becomes_overdue_after_its_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Work that has never succeeded becomes overdue after its
    tolerance.

    WHEN a piece of recurring work has never succeeded and its declared
    tolerance has elapsed since the system first knew of its schedule
    THEN it SHALL be considered overdue, on the basis that it has never
    succeeded.

    SPECIFIED. No success is recorded at all, so the only anchor available
    is the first-known time -- which is the point: the run history has none
    for work that never ran.
    """
    state = _one_work(first_known=_NOW - TOLERANCE - datetime.timedelta(hours=1))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert _mentions(notifier, WORK_ID), (
        f"{WORK_ID} has never succeeded and has been known for longer than "
        f"its {TOLERANCE} tolerance, and was not considered overdue; "
        f"posted: {notifier.posted}"
    )


async def test_a_freshly_deployed_system_does_not_report_work_as_overdue_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A freshly deployed system does not report work as overdue
    immediately.

    WHEN the system has just started for the first time, knows of a piece
    of recurring work, and that work has not yet run
    THEN it SHALL NOT be considered overdue until its tolerance has elapsed
    since the system first knew of it.

    SPECIFIED. This is the scenario that makes the anchor necessary at all:
    with no success and no first-known time, an implementation comparing
    against the epoch -- or against nothing -- reports every piece of work
    overdue on the first check after every deploy.
    """
    state = _one_work(first_known=_NOW - datetime.timedelta(minutes=5))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert notifier.posted == [], (
        f"{WORK_ID} has never run but has only been known for five minutes, "
        f"well inside its {TOLERANCE} tolerance, and was reported anyway: "
        f"{notifier.posted}"
    )


async def test_work_within_its_tolerance_is_not_overdue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Work within its tolerance is not overdue.

    WHEN a piece of recurring work last succeeded within its declared
    tolerance
    THEN it SHALL NOT be considered overdue.

    SPECIFIED.
    """
    state = _one_work(last_success=_NOW - datetime.timedelta(minutes=30))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert notifier.posted == [], (
        f"{WORK_ID} succeeded half an hour ago, inside its {TOLERANCE} "
        f"tolerance, and was reported overdue anyway: {notifier.posted}"
    )


# --------------------------------------------------------------------------
# Requirement: Overdue Work Is Reported To Slack From Inside The Deployment
# --------------------------------------------------------------------------


async def test_overdue_work_is_reported_naming_it_and_its_last_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Overdue work is reported.

    WHEN a piece of recurring work is overdue and the process running
    scheduled work is alive
    THEN the system SHALL post a message to the team's Slack channel naming
    that work and when it last succeeded, or that it has never succeeded.

    SPECIFIED: exactly one message, naming the work.

    DERIVED, and the reason is recorded in test-manifest.md: "when it last
    succeeded" is unobservable without fixing some rendering of a time, and
    no artifact fixes one for this message. The ISO date of the last
    success is asserted as the weakest recognizable form -- it is present
    in `str(datetime)`, in `isoformat()` and in the RFC 3339 rendering
    design.md fixes for the freshness endpoint's `last_success`. A message
    naming the time in prose alone ("yesterday morning") would fail here;
    correcting this assertion, if that is the deliberate choice, is a
    change to a derived assertion and is recorded as one.
    """
    last_success = _NOW - TOLERANCE - datetime.timedelta(hours=2)
    state = _one_work(last_success=last_success)
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert len(notifier.posted) == 1, (
        f"expected exactly one message for one overdue piece of work, got "
        f"{notifier.posted}"
    )
    message = notifier.posted[0]
    # Specified: the message names the work.
    assert WORK_ID in message, f"the message does not name the work: {message!r}"
    # Derived: see the docstring.
    assert last_success.date().isoformat() in message, (
        "the message does not say when the work last succeeded in any form "
        f"carrying its ISO date ({last_success.date().isoformat()}): "
        f"{message!r}"
    )


async def test_work_that_has_never_succeeded_is_reported_as_never_having_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Overdue work is reported -- the "or that it has never
    succeeded" branch.

    SPECIFIED that the message distinguishes never-succeeded from
    succeeded-long-ago; DERIVED that it does so with the word "never",
    which is the weakest recognizable form and the spec's own wording. The
    distinction itself is not optional: it is the difference between work
    that has stopped and work that has never started, and a message
    rendering "never" as an epoch timestamp says the wrong thing.
    """
    state = _one_work(first_known=_NOW - TOLERANCE - datetime.timedelta(hours=2))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert len(notifier.posted) == 1, (
        f"expected exactly one message, got {notifier.posted}"
    )
    message = notifier.posted[0]
    assert WORK_ID in message, f"the message does not name the work: {message!r}"
    assert "never" in message.lower(), (
        "the message does not say the work has never succeeded, so it "
        f"cannot be told from work that succeeded long ago: {message!r}"
    )


async def test_work_within_its_tolerance_is_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Work within its tolerance is not reported.

    WHEN a piece of recurring work is not overdue
    THEN the system SHALL NOT report it.

    SPECIFIED. Distinct from "Work within its tolerance is not overdue"
    above in what it fixes: that one is about the determination, this one
    about the channel -- an implementation that determined correctly and
    posted a routine "all is well" message would satisfy that scenario and
    fail this one.
    """
    state = _RecordedState(
        registry={
            WORK_ID: _Registration(WORK_ID, WORK_ID, "0 * * * *", TOLERANCE),
            OTHER_WORK_ID: _Registration(
                OTHER_WORK_ID, OTHER_WORK_ID, "0 6 * * *", TOLERANCE
            ),
        },
        last_success={
            WORK_ID: _NOW - datetime.timedelta(minutes=10),
            OTHER_WORK_ID: _NOW - datetime.timedelta(minutes=10),
        },
    )
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert notifier.posted == [], (
        "nothing is overdue, so nothing should have been posted at all: "
        f"{notifier.posted}"
    )


async def test_work_with_no_declared_schedule_is_never_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Work with no declared schedule is never reported.

    WHEN a piece of work has no declared schedule
    THEN the system SHALL NOT report it as overdue, however long ago it
    last succeeded.

    SPECIFIED. The unregistered work's last success is placed a year in the
    past -- "however long ago" -- and it is present in the run history,
    which is exactly the state the four suspended cadences are in: they ran
    under the retired `cron` container and are not scheduled now.
    """
    state = _one_work(last_success=_NOW - datetime.timedelta(minutes=10))
    state.last_success[UNREGISTERED_WORK_ID] = _NOW - datetime.timedelta(days=365)
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert not _mentions(notifier, UNREGISTERED_WORK_ID), (
        f"{UNREGISTERED_WORK_ID} has no declared schedule and was reported "
        f"as overdue anyway: {notifier.posted}"
    )
    assert notifier.posted == [], (
        f"nothing registered is overdue, so nothing should have been "
        f"posted: {notifier.posted}"
    )


# --------------------------------------------------------------------------
# Requirement: The Process Running Scheduled Work Is Itself Monitored Work
# --------------------------------------------------------------------------


async def test_a_completed_evaluation_records_a_successful_run_despite_a_failed_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A completed evaluation records a successful run despite a
    failed delivery.

    WHEN the overdue check completes its evaluation and its attempt to
    deliver a report fails
    THEN its run SHALL be recorded as successful
    AND its liveness evidence SHALL remain fresh.

    SPECIFIED. "Recorded as successful" is read as the job body returning
    normally -- see the module docstring. A body that let the delivery
    failure propagate would make the worker's own liveness evidence stale
    for the duration of a Slack outage, and the freshness endpoint would
    report an absent worker while the worker was running normally.

    The endpoint's half of this -- that it does not then report the worker
    absent -- is asserted in test_scheduled_runs_freshness.py, under "The
    freshness interface is unaffected by a reporting-channel outage".
    """
    state = _one_work(last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1))
    notifier = _RecordingNotifier(failure=RuntimeError("slack is unreachable"))
    _install(monkeypatch, state, notifier)

    await _run_check()  # must not raise

    assert notifier.posted == [], "the scripted notifier recorded a delivery it failed"


# --------------------------------------------------------------------------
# Requirement: A Continuing Outage Is Reported Once, Not Repeatedly
# --------------------------------------------------------------------------


async def test_a_continuing_outage_is_not_reported_repeatedly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A continuing outage is not reported repeatedly.

    WHEN a piece of recurring work has been reported as overdue and remains
    overdue at the next check
    THEN the system SHALL NOT post a further message for that same period
    of overdueness.

    SPECIFIED. Two consecutive checks over unchanged, still-overdue state:
    the first reports, the second must not. The suppression the first check
    records is what the second reads -- nothing here presets it, so this
    also establishes that the first check records suppression after a
    delivery that succeeded.
    """
    state = _one_work(last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1))
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()
    posted_after_first = list(notifier.posted)
    await _run_check()

    assert len(posted_after_first) == 1, (
        f"the first check did not report the overdue work: {posted_after_first}"
    )
    assert notifier.posted == posted_after_first, (
        f"the same period of overdueness was reported a second time: {notifier.posted}"
    )


async def test_a_failed_delivery_leaves_the_work_eligible_to_be_reported_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed delivery leaves the work eligible to be reported
    again.

    WHEN a report for an overdue piece of work could not be delivered, and
    the work is still overdue at the next check
    THEN the system SHALL attempt to report it again.

    SPECIFIED, and this is the ordering design.md turns on: suppression is
    written only *after* a delivery succeeds, because suppression lifts
    when the work succeeds and not when the channel recovers -- so
    recording it before a failed delivery would silence the period's only
    alarm permanently.
    """
    state = _one_work(last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1))
    notifier = _RecordingNotifier(failure=RuntimeError("slack is unreachable"))
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert state.suppressed == set(), (
        "suppression was recorded although the report was never delivered, "
        "so this period of overdueness can never be reported again: "
        f"{state.suppressed}"
    )

    notifier.failure = None
    await _run_check()

    assert _mentions(notifier, WORK_ID), (
        "the work was still overdue at the next check after a failed "
        f"delivery and was not reported again: {notifier.posted}"
    )


async def test_a_restart_does_not_resume_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A restart does not resume reporting.

    WHEN a piece of recurring work has been reported as overdue, the
    process running scheduled work restarts, and the work is still overdue
    THEN the system SHALL NOT post a further message for that same period
    of overdueness.

    SPECIFIED, at the level a restart is observable in this tier: the check
    reads suppression from the recorded state rather than from anything it
    remembers, so a check invocation that has itself reported nothing --
    which is what a freshly restarted worker is -- still finds the work
    suppressed. That the record itself survives Postgres is the durable
    half, covered in
    `tests/integration/shared/test_overdue_report_suppression_store.py`.

    In-memory suppression would satisfy every other scenario in this
    requirement and fail here, and a crash-looping worker is exactly when
    the outage is ongoing -- which is why it would produce a message per
    restart, the flood the requirement exists to prevent, arriving by the
    worst route.
    """
    state = _one_work(
        last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1),
        suppressed=[WORK_ID],
    )
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    await _run_check()

    assert notifier.posted == [], (
        "a check that had reported nothing itself posted about work whose "
        "suppression record was already present, so the record is not what "
        f"is being read: {notifier.posted}"
    )


async def test_overdueness_recurring_after_a_success_is_reported_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Overdueness recurring after a success is reported again.

    WHEN a piece of recurring work was reported as overdue, subsequently
    succeeded, and later becomes overdue again
    THEN the system SHALL report it again.

    SPECIFIED. The three states are walked in order: reported and
    suppressed, then a success inside the tolerance (which must end the
    period of overdueness, clearing the suppression), then overdue again.
    Without the clearing step the second report never happens, since
    suppression is lifted by the work succeeding and by nothing else.
    """
    state = _one_work(
        last_success=_NOW - TOLERANCE - datetime.timedelta(hours=1),
        suppressed=[WORK_ID],
    )
    notifier = _RecordingNotifier()
    _install(monkeypatch, state, notifier)

    # The work succeeds: the period of overdueness ends here.
    state.last_success[WORK_ID] = _NOW - datetime.timedelta(minutes=5)
    await _run_check()

    assert notifier.posted == [], (
        f"work that has just succeeded was reported overdue: {notifier.posted}"
    )
    assert WORK_ID not in state.suppressed, (
        "the suppression record survived the work succeeding, so the next "
        "period of overdueness could never be reported"
    )

    # Time passes and it stops succeeding again.
    state.last_success[WORK_ID] = _NOW - TOLERANCE - datetime.timedelta(hours=1)
    await _run_check()

    assert _mentions(notifier, WORK_ID), (
        "work that recovered and then became overdue again was not reported "
        f"a second time: {notifier.posted}"
    )
