"""Every run's outcome is recorded, survives the process, and can be
asked about afterwards.

Derived strictly from `specs/scheduled-jobs/spec.md` in the OpenSpec
change `replace-cron-with-job-runner`:

- "Every Run's Outcome Is Recorded And Can Be Asked About Afterwards" /
  Scenarios: A completed run is recorded; A run's record outlives the
  process; The most recent successful run can be identified
- "A Failed Run Is Retried With Increasing Delay" / Scenario: A retried
  run that succeeds is recorded as succeeded

See `test-manifest.md` at the change root for the full accounting.

## Why this is integration tier

The requirement's own words are "This record SHALL survive the process
that produced it, and SHALL be queryable afterwards". Survival past a
process is not observable against an in-memory double at any level: the
smallest unit that can observe it is a real Postgres holding the row and
a second, independent connection reading it back. That is this project's
`tests/integration/` tier, which runs at `pre-push` (AGENTS.md, Testing
Strategy).

These tests assume `alembic upgrade head` has already been applied to the
database `DATABASE_URL` points at -- including this change's own
migration installing the runner's schema. That is the same assumption
`tests/integration/products/conftest.py` already makes, and creating the
schema here instead would be writing implementation inside a
test-authoring pass.

## What is invented here

- `commerce_ops.shared.infrastructure.driven.job_runner.app` -- the
  runner application object. design.md fixes the directory, no artifact
  fixes the name.
- `commerce_ops.shared.infrastructure.driven.job_history.last_successful_run`
  -- the last-success accessor tasks.md 2.10 requires, returning the time
  of a piece of work's most recent successful run, or `None` as the
  "distinct never-succeeded result" that task asks for. Neither its
  module, its function name, nor `None`-for-never is fixed by any
  artifact.

Both are single correction points: the assertions below are about what is
recorded and what can be read back, not about where the reader lives.

The history queries here go against the runner's physical tables. That is
not a shortcut around a supported API: design.md already accepts exactly
this coupling for the accessor itself ("reading the queue's tables with
the application's own SQLAlchemy session means raw SQL against the
runner's physical schema"), and asserting the recorded facts any other
way would mean asserting them through the very accessor one of these
tests exists to check.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driven.job_history import last_successful_run
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio

# How many worker passes a job that retries is given before the test
# gives up on it reaching a final status. A retried run is scheduled for
# "now" by a zero-wait strategy, but nothing guarantees one worker pass
# picks it up.
_MAX_WORKER_PASSES = 5


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's runner-schema migration), and point DATABASE_URL at "
            "it to run tests/integration/shared/."
        )
    return url


@pytest.fixture()
async def reader() -> AsyncIterator[AsyncEngine]:
    """A connection to the same database that is *not* the runner's own.

    Used for every read below, so that "the record survives the process
    that produced it" is observed across a real connection boundary
    rather than inside the writer's own session.
    """
    engine = create_async_engine(_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _shared_engine_disposed_between_tests() -> AsyncIterator[None]:
    """Test infrastructure, not a subject of any requirement.

    `last_successful_run` reads through the application's own session
    provider (tasks.md 2.10a: "not through the runner's own connector"),
    and that provider caches one engine -- and one asyncpg pool -- per
    process, which is exactly right for a worker that runs a single event
    loop for its whole life. `pytest.mark.anyio` gives every test function
    its own loop, so without this the second test in a run to reach the
    provider inherits a pool bound to the previous test's closed loop and
    fails with "got Future attached to a different loop" -- a defect in
    how these tests exercise a process-wide provider, not in the provider.

    Disposal runs on both sides of the test: before, so a pool left behind
    by an earlier file in the same session is not inherited; after, so
    this file leaves none behind either. `dispose_engine()` clears the
    factory cache in the same operation, so the next request builds a
    fresh engine on the loop that asks for it.
    """
    await dispose_engine()
    yield
    await dispose_engine()


# --------------------------------------------------------------------------
# Work defined for these tests only.
#
# Registered on the application's own runner rather than a throwaway one,
# so that what is exercised is this application's runner, its schema
# migration and its accessor -- not procrastinate in the abstract. No
# schedule is declared for them, so `test_job_runner_schedules.py`'s
# "exactly one piece of recurring work is scheduled" stays true.
# --------------------------------------------------------------------------

_FAILURES_BEFORE_SUCCESS: dict[str, int] = {}


@runner_app.task(name="tests.run_history.succeeds")
async def _succeeding_work(marker: str) -> str:
    return marker


@runner_app.task(name="tests.run_history.always_fails")
async def _failing_work(marker: str) -> None:
    raise RuntimeError(f"deliberate failure for {marker}")


@runner_app.task(
    name="tests.run_history.fails_then_succeeds",
    retry=1,
)
async def _flaky_work(marker: str) -> str:
    remaining = _FAILURES_BEFORE_SUCCESS.get(marker, 0)
    if remaining:
        _FAILURES_BEFORE_SUCCESS[marker] = remaining - 1
        raise RuntimeError(f"deliberate first-attempt failure for {marker}")
    return marker


async def _drain(passes: int = 1) -> None:
    """Runs the worker until the queue is empty, `passes` times."""
    for _ in range(passes):
        await runner_app.run_worker_async(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
            delete_jobs="never",
        )


async def _job_row(engine: AsyncEngine, job_id: int) -> dict[str, object]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT id, task_name, status, attempts "
                "FROM procrastinate_jobs WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )
        row = result.mappings().one_or_none()
    assert row is not None, (
        f"no run was recorded for job {job_id}; the run history has no "
        "record of work that ran"
    )
    return dict(row)


async def _job_events(engine: AsyncEngine, job_id: int) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT type, at FROM procrastinate_events "
                "WHERE job_id = :job_id ORDER BY at, id"
            ),
            {"job_id": job_id},
        )
        return [dict(row) for row in result.mappings().all()]


# --------------------------------------------------------------------------
# Requirement: Every Run's Outcome Is Recorded And Can Be Asked About
# Afterwards
# --------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ("succeeded", "failed"))
async def test_a_completed_run_is_recorded(outcome: str, reader: AsyncEngine) -> None:
    """Scenario: A completed run is recorded.

    WHEN a run completes, whether it succeeded or failed
    THEN the system SHALL record which work it was, when it started, when
    it ended, and its outcome.

    All four facts are asserted, because the requirement names all four
    and tasks.md 2.10 makes confirming they are all carried a precondition
    of the accessor being built at all.
    """
    marker = f"marker-{uuid.uuid4()}"
    work = _succeeding_work if outcome == "succeeded" else _failing_work

    async with runner_app.open_async():
        job_id = await work.defer_async(marker=marker)
        await _drain()

    row = await _job_row(reader, job_id)
    events = await _job_events(reader, job_id)
    event_types = [event["type"] for event in events]

    # SPECIFIED: which work it was.
    assert row["task_name"] == work.name
    # SPECIFIED: its outcome, and that the two outcomes are distinct.
    assert row["status"] == outcome, (
        f"expected the run to be recorded as {outcome}, got {row['status']}"
    )
    # SPECIFIED: when it started, and when it ended.
    assert "started" in event_types, (
        f"no start was recorded for the run; recorded events: {event_types}"
    )
    assert outcome in event_types, (
        f"no end was recorded for the run; recorded events: {event_types}"
    )
    started = next(event["at"] for event in events if event["type"] == "started")
    ended = next(event["at"] for event in events if event["type"] == outcome)
    assert started is not None and ended is not None, (
        f"the run's start or end was recorded without a time: {events}"
    )
    assert ended >= started  # type: ignore[operator]


async def test_a_runs_record_outlives_the_process(reader: AsyncEngine) -> None:
    """Scenario: A run's record outlives the process.

    WHEN the process that ran a piece of work has exited
    THEN that run's record SHALL still be available.

    The runner's own connection is closed before the record is read, and
    the read goes through an independent engine -- so what is observed is
    a row in Postgres, not a value the writer still holds in memory.
    """
    marker = f"marker-{uuid.uuid4()}"

    async with runner_app.open_async():
        job_id = await _succeeding_work.defer_async(marker=marker)
        await _drain()
    # The runner's connector is closed here; whatever it held is gone.

    row = await _job_row(reader, job_id)

    assert row["status"] == "succeeded"
    assert row["task_name"] == _succeeding_work.name


async def test_the_most_recent_successful_run_can_be_identified() -> None:
    """Scenario: The most recent successful run can be identified.

    WHEN the system is asked when a given piece of recurring work last
    succeeded
    THEN it SHALL report the time of that work's most recent successful
    run.

    DERIVED: that the reported time falls between the run's start and the
    moment of asking. The scenario says "the time of that work's most
    recent successful run" without fixing which timestamp of the run that
    is, so the assertion is bounded rather than exact.
    """
    marker = f"marker-{uuid.uuid4()}"

    async with runner_app.open_async():
        before = await last_successful_run(_succeeding_work.name)
        await _succeeding_work.defer_async(marker=marker)
        await _drain()
        after = await last_successful_run(_succeeding_work.name)

    assert after is not None, (
        "the system reported no successful run for work that just succeeded"
    )
    if before is not None:
        assert after > before, (
            "the reported last success did not advance past an earlier run, "
            "so it is not the *most recent* one"
        )


async def test_work_that_has_never_succeeded_is_reported_as_such() -> None:
    """Scenario: The most recent successful run can be identified.

    ... "or report that it has never succeeded".

    SPECIFIED: never-succeeded is reported distinctly. DERIVED: that the
    distinct result is `None` -- tasks.md 2.10 requires "a distinct
    never-succeeded result" without naming one, and `None` is the
    unambiguous Python spelling of it, as distinct from a sentinel time.
    """
    never_run = f"tests.run_history.never-{uuid.uuid4()}"

    async with runner_app.open_async():
        reported = await last_successful_run(never_run)

    assert reported is None, (
        f"work that has never run reported a last success: {reported!r}"
    )


async def test_a_failed_run_does_not_count_as_a_success(
    reader: AsyncEngine,
) -> None:
    """Scenario: The most recent successful run can be identified.

    DERIVED, from the same scenario read strictly: "the time of that
    work's most recent *successful* run". An accessor that reported the
    last run of any outcome would satisfy every assertion above while
    reporting an outage as a success -- which is precisely the question
    `report-overdue-scheduled-runs` will ask it.
    """
    marker = f"marker-{uuid.uuid4()}"

    async with runner_app.open_async():
        job_id = await _failing_work.defer_async(marker=marker)
        await _drain()
        reported = await last_successful_run(_failing_work.name)

    assert (await _job_row(reader, job_id))["status"] == "failed"
    assert reported is None, f"a failed run was reported as a success at {reported!r}"


# --------------------------------------------------------------------------
# Requirement: A Failed Run Is Retried With Increasing Delay
# --------------------------------------------------------------------------


async def test_a_retried_run_that_succeeds_is_recorded_as_succeeded(
    reader: AsyncEngine,
) -> None:
    """Scenario: A retried run that succeeds is recorded as succeeded.

    WHEN a run fails, is retried, and the retry succeeds
    THEN the run SHALL be recorded as succeeded.
    """
    marker = f"marker-{uuid.uuid4()}"
    _FAILURES_BEFORE_SUCCESS[marker] = 1

    async with runner_app.open_async():
        job_id = await _flaky_work.defer_async(marker=marker)
        await _drain(passes=_MAX_WORKER_PASSES)

    row = await _job_row(reader, job_id)
    event_types = [event["type"] for event in await _job_events(reader, job_id)]

    assert _FAILURES_BEFORE_SUCCESS[marker] == 0, (
        "the work never failed, so nothing was retried and this test "
        "establishes nothing about a retried run"
    )
    assert event_types.count("started") >= 2, (
        f"the run was not retried after its failure; events: {event_types}"
    )
    # SPECIFIED: the run is recorded as succeeded, not as failed-then-
    # separately-succeeded.
    assert row["status"] == "succeeded", (
        f"a run that succeeded on retry is recorded as {row['status']}"
    )


# --------------------------------------------------------------------------
# Requirement: Every Run's Outcome Is Recorded And Can Be Asked About
# Afterwards -- "A run spans its retries"
#
# Added after the requirement gained that paragraph: "A run spans its
# retries: a piece of work that fails and is retried is one run, not
# several. Its start is the first attempt's start, its end is the moment
# of the outcome that stopped it". The test above asserts the *outcome*
# half of a retried run; this asserts the start/end half, which is what
# tasks.md 5.7 asks for and what tasks.md 2.10 makes a precondition of
# building the accessor at all.
# --------------------------------------------------------------------------


async def _runs_recorded_for(
    engine: AsyncEngine, task_name: str, marker: str
) -> list[dict[str, object]]:
    """Every record the history holds for one deferral of one piece of
    work, identified by the marker that deferral carried -- so "one
    record, not one per attempt" is a count rather than an impression.
    """
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT id, status, attempts FROM procrastinate_jobs "
                "WHERE task_name = :task_name AND args->>'marker' = :marker "
                "ORDER BY id"
            ),
            {"task_name": task_name, "marker": marker},
        )
        return [dict(row) for row in result.mappings().all()]


async def test_a_retried_run_is_one_record_spanning_its_attempts(
    reader: AsyncEngine,
) -> None:
    """Requirement: "A run spans its retries: a piece of work that fails
    and is retried is one run, not several. Its start is the first
    attempt's start, its end is the moment of the outcome that stopped
    it, and its outcome is that final outcome."

    WHEN a run fails, is retried, and the retry succeeds
    THEN the history SHALL hold one record for it, whose start is the
    failed first attempt's start and whose end is the successful retry's
    outcome.

    Sibling of `test_a_retried_run_that_succeeds_is_recorded_as_succeeded`
    above, which asserts the outcome half of the same run. Written as a
    sibling rather than as extra assertions inside that test so the two
    halves fail separately: a history that records the right outcome
    against the wrong start is a different defect from one that records
    the wrong outcome, and `report-overdue-scheduled-runs` will read the
    start.
    """
    marker = f"marker-{uuid.uuid4()}"
    _FAILURES_BEFORE_SUCCESS[marker] = 1

    async with runner_app.open_async():
        job_id = await _flaky_work.defer_async(marker=marker)
        await _drain(passes=_MAX_WORKER_PASSES)

    events = await _job_events(reader, job_id)
    starts = [event["at"] for event in events if event["type"] == "started"]
    outcomes = [event for event in events if event["type"] in ("succeeded", "failed")]
    records = await _runs_recorded_for(reader, _flaky_work.name, marker)

    # Precondition, not the assertion under test: the work really did fail
    # once and then succeed. Without a retry there is no span to assert.
    assert _FAILURES_BEFORE_SUCCESS[marker] == 0, (
        "the work never failed, so nothing was retried and this test "
        "establishes nothing about a run spanning its retries"
    )
    assert len(starts) >= 2, (
        f"the run was not attempted more than once; events: "
        f"{[event['type'] for event in events]}"
    )

    # SPECIFIED: "one run, not several".
    assert len(records) == 1, (
        f"a run that was retried is recorded as {len(records)} records "
        f"rather than one: {records}"
    )

    # SPECIFIED: "its outcome is that final outcome" -- one outcome for the
    # whole run, and it is the one that stopped it.
    assert len(outcomes) == 1, (
        "the run carries more than one outcome, so a retried run is being "
        f"recorded as several: {[event['type'] for event in events]}"
    )
    assert outcomes[0]["type"] == "succeeded"

    # SPECIFIED: "Its start is the first attempt's start" -- the earliest
    # attempt's, not the attempt that happened to succeed. Asserted as a
    # strict inequality against the successful attempt's own start, so a
    # history that took its start from the last attempt fails here.
    run_start = min(starts)  # type: ignore[type-var]
    assert run_start == starts[0], (
        f"the run's attempts are not recorded in order: {starts}"
    )
    assert run_start < starts[-1], (  # type: ignore[operator]
        "the run's start is not the first attempt's start -- the first and "
        f"the successful attempt share a start time: {starts}"
    )

    # SPECIFIED: "its end is the moment of the outcome that stopped it" --
    # after the successful retry began, not at the failed attempt's end.
    run_end = outcomes[0]["at"]
    assert run_end >= starts[-1], (  # type: ignore[operator]
        f"the run's end ({run_end}) precedes the start of the attempt that "
        f"stopped it ({starts[-1]}), so it was taken from the failed "
        "attempt rather than from the outcome"
    )
    assert run_end > run_start, (  # type: ignore[operator]
        f"the run's end does not follow its start: {run_start} -> {run_end}"
    )
