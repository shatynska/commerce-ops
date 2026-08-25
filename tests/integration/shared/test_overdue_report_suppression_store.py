"""The suppression record outlives the process that wrote it.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "A Continuing Outage Is Reported Once, Not Repeatedly" / Scenario: A
  restart does not resume reporting -- its durable half. "The record SHALL
  be persisted, so that restarting the process running scheduled work does
  not cause the reports to resume."

The behavioural half -- that a check which has itself reported nothing
still posts nothing when the record is present, which is what a freshly
restarted worker is -- is asserted in
`tests/unit/shared/infrastructure/driving/test_overdue_check.py`. See
`test-manifest.md` at the change root for the full accounting.

## Why this is integration tier

In-memory suppression satisfies every other scenario in that requirement
and fails only this one, and it fails it at exactly the moment the
requirement was written for: a crash-looping worker is when the outage is
ongoing, so an in-memory record produces a message per restart -- the flood
the requirement exists to prevent, arriving by the worst route. Surviving a
process is not observable against a double at any level; the smallest unit
that can observe it is a real Postgres row read back through a connection
that is not the one that wrote it.

Assumes `uv run alembic upgrade head` has been applied, including this
change's suppression migration.

## Reaching the repository without naming it

Through the overdue check's own namespace -- the check is found by the
placement tasks.md 4.1 fixes -- so this file pins no name
`tests/unit/shared/infrastructure/driving/test_overdue_check.py` has not
already pinned. Neither the suppression table's name nor its columns are
touched here.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any

import pytest

from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

OVERDUE_CHECK_PACKAGE = "commerce_ops.shared.infrastructure.driving"

register_all()


@pytest.fixture(autouse=True)
def _database_available(database_url: str) -> None:
    """Requesting `database_url` is this file's opt-in to the gate."""


def _run[T](work: Callable[[], Awaitable[T]]) -> T:
    """One database interaction, in its own loop and its own engine.

    Disposing on the way out is what makes the read below a genuine
    second connection rather than the writer's own session -- and it is
    also the hazard `test_scheduled_run_history.py` records, an asyncpg
    pool being bound to the loop that created it.
    """

    async def _wrapper() -> T:
        try:
            return await work()
        finally:
            await dispose_engine()

    return asyncio.run(_wrapper())


def _check_module() -> ModuleType:
    matching = [
        entry
        for entry in runner_app.periodic_registry.periodic_tasks.values()
        if entry.task.func.__module__.startswith(OVERDUE_CHECK_PACKAGE)
    ]
    assert len(matching) == 1, (
        f"expected exactly one scheduled job under {OVERDUE_CHECK_PACKAGE!r} "
        "(tasks.md 4.1)"
    )
    return sys.modules[matching[0].task.func.__module__]


def _collaborator(name: str) -> Any:
    module = _check_module()
    if not hasattr(module, name):
        pytest.fail(
            f"{module.__name__} exposes no module-level name {name!r}. See "
            "tests/unit/shared/infrastructure/driving/test_overdue_check.py's "
            "SEAM CONTRACT docstring and test-manifest.md's unresolved "
            "project questions."
        )
    return getattr(module, name)


def test_a_delivered_report_stays_suppressed_across_a_restart() -> None:
    """Scenario: A restart does not resume reporting.

    WHEN a piece of recurring work has been reported as overdue, the
    process running scheduled work restarts, and the work is still overdue
    THEN the system SHALL NOT post a further message for that same period
    of overdueness.

    SPECIFIED, at the mechanism the requirement names: the record is
    persisted. Written through one connection and read back through
    another, after the first has been disposed -- which is as close to a
    restart as one process gets, and is the difference between a row in
    Postgres and a set in memory.

    The identifier is unique to this run: these tests share a persistent
    database with no truncate fixture, so nothing here assumes the table
    starts empty.
    """
    identifier = f"tests.suppression.{uuid.uuid4()}"
    record = _collaborator("record_report_delivered")
    suppressed = _collaborator("suppressed_identifiers")
    clear = _collaborator("clear_report_suppression")

    assert identifier not in _run(suppressed), (
        f"{identifier} was already suppressed before anything wrote it"
    )

    _run(lambda: record(identifier))

    try:
        # A second process, as far as the session provider is concerned:
        # the engine and its pool were disposed with the write above.
        assert identifier in _run(suppressed), (
            f"the suppression record for {identifier} did not survive the "
            "connection that wrote it, so a restarted worker would report "
            "the same period of overdueness again -- and a crash-looping "
            "worker would report it on every restart"
        )
    finally:
        _run(lambda: clear(identifier))

    assert identifier not in _run(suppressed), (
        "clearing the suppression record left it in place, so this test "
        "leaves state behind and recurrence could never be reported"
    )
