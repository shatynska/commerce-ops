"""The first-known anchor: written once, never advanced, never erased.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Work Is Overdue Relative To Its Last Success Or To When It Was First
  Known" / Scenarios: A worker that never started still produces an anchor;
  A later observation does not advance the anchor; A success does not erase
  the first-known time

See `test-manifest.md` at the change root for the full accounting.

## Why this is integration tier

The requirement's words are "SHALL persist for as long as the work is
registered", the write "SHALL be idempotent", and the recorded time "SHALL
NOT be advanced by a later observation". Idempotence of an upsert and the
independence of two tables' lifecycles are properties of the schema and the
statement, not of a Python function -- an in-memory double asserts only
that the double was written the way the test wrote it. The smallest unit
that can observe them is a real Postgres with both of this change's
migrations applied, which is this project's `tests/integration/` tier
(`AGENTS.md`, Testing Strategy), run at `pre-push`.

These tests assume `uv run alembic upgrade head` has already been applied
to the database `DATABASE_URL` points at, including this change's
suppression and `known_work` migrations -- the same assumption
`tests/integration/shared/test_scheduled_run_history.py` already makes.
Creating the schema here would be writing implementation inside a
test-authoring pass.

## Reaching the repositories without naming them

Neither the anchor repository's module nor the suppression repository's is
fixed by any artifact. Both are reached the same way the rest of this pass
reaches things: through the namespace of the module that uses them -- the
freshness route (found by its path on `main.app`) for the anchor, the
overdue check (found by its placement in `shared/infrastructure/driving/`)
for suppression. So this file pins no name that
`tests/unit/shared/infrastructure/driving/` has not already pinned, and
adds no new invented surface of its own.

## Event loops

Each database interaction runs in its own `asyncio.run`, disposing the
process-wide engine on the way out. The session provider caches one engine
per process and an asyncpg pool is bound to the loop that created it, so a
second loop inheriting the first's pool fails with "got Future attached to
a different loop" -- a defect in how a test exercises a process-wide
provider, not in the provider. `test_scheduled_run_history.py` records the
same hazard.
"""

from __future__ import annotations

import asyncio
import datetime
import sys
import uuid
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

import commerce_ops.main as main_module
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

FRESHNESS_PATH = "/health/scheduled-runs"
OVERDUE_CHECK_PACKAGE = "commerce_ops.shared.infrastructure.driving"

register_all()


@pytest.fixture(autouse=True)
def _database_available(database_url: str) -> None:
    """Requesting `database_url` is this file's opt-in to the gate."""


def _run[T](work: Callable[[], Awaitable[T]]) -> T:
    """Runs one database interaction in its own loop, disposing after.

    Test infrastructure, not the subject of any requirement -- see the
    module docstring's "Event loops".
    """

    async def _wrapper() -> T:
        try:
            return await work()
        finally:
            await dispose_engine()

    return asyncio.run(_wrapper())


def _app_routes(app: Any) -> list[Any]:
    """Every route registered on the application, flattened.

    FastAPI 0.141 wraps each `include_router` in an `_IncludedRouter` that
    carries no `path` of its own, so a flat scan of `app.routes` finds only
    the built-in docs routes and would report a correctly registered router
    as missing. The underlying `APIRouter` is `original_router`.

    This is a fixture correction, not a weakening: what is asserted is still
    that exactly one route answers at the path, reached through the
    application object rather than by importing the module directly.
    """
    routes: list[Any] = []
    for entry in app.routes:
        original = getattr(entry, "original_router", None)
        if original is not None:
            routes.extend(original.routes)
        else:
            routes.append(entry)
    return routes


def _route_module() -> ModuleType:
    matching = [
        route
        for route in _app_routes(main_module.app)
        if getattr(route, "path", None) == FRESHNESS_PATH
    ]
    assert len(matching) == 1, (
        f"expected exactly one route at {FRESHNESS_PATH} on "
        "commerce_ops.main.app (tasks.md 5.2)"
    )
    # `endpoint` is an APIRoute attribute, absent from the `BaseRoute`
    # type the routes list is declared as -- read reflectively rather
    # than by narrowing to a FastAPI-internal class.
    endpoint = getattr(matching[0], "endpoint", None)
    assert endpoint is not None, (
        f"the route at {FRESHNESS_PATH} carries no endpoint function"
    )
    return sys.modules[endpoint.__module__]


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


def _collaborator(module: ModuleType, name: str) -> Any:
    if not hasattr(module, name):
        pytest.fail(
            f"{module.__name__} exposes no module-level name {name!r}. See "
            "tests/unit/shared/infrastructure/driving/test_overdue_check.py's "
            "SEAM CONTRACT docstring and test-manifest.md's unresolved "
            "project questions."
        )
    return getattr(module, name)


def _registered_identifiers() -> set[str]:
    """Every identifier the endpoint's own registry accessor reports."""
    declared = _collaborator(_route_module(), "registered_work")()
    if hasattr(declared, "keys"):
        return {str(key) for key in declared}
    identifiers = set()
    for entry in declared:
        for attribute in ("identifier", "id", "task_name", "name"):
            value = getattr(entry, attribute, None)
            if value is not None:
                identifiers.add(str(value))
                break
    return identifiers


def _anchors() -> dict[str, datetime.datetime]:
    route = _route_module()
    read = _collaborator(route, "first_known_times")
    return dict(_run(read))


def _anchor(identifiers: list[str]) -> None:
    route = _route_module()
    write = _collaborator(route, "record_first_known")
    _run(lambda: write(identifiers))


def _unique_identifier() -> str:
    """An identifier unique to this run.

    These tests run against a real, persistent Postgres with no truncate
    fixture, so each one names work nothing else has written a row for
    rather than assuming the table starts empty.
    """
    return f"tests.known-work.{uuid.uuid4()}"


# --------------------------------------------------------------------------
# Requirement: Work Is Overdue Relative To Its Last Success Or To When It
# Was First Known
# --------------------------------------------------------------------------


def test_a_worker_that_never_started_still_produces_an_anchor() -> None:
    """Scenario: A worker that never started still produces an anchor.

    WHEN the freshness interface has served a request and the process
    running scheduled work has never started
    THEN each registered piece of work SHALL have a recorded first-known
    time.

    SPECIFIED, and here against a real database rather than against a
    double: what this establishes over the unit-tier version is that the
    row is actually in Postgres, readable by a later request -- which is
    the whole of "the system SHALL record when it first knew of each piece
    of work". The precondition is ambient: no worker process exists here.

    The "SHALL become overdue once its tolerance has elapsed since that
    time" half is asserted in the unit tier, where the anchor can be aged
    without waiting out a real tolerance.
    """
    identifiers = _registered_identifiers()
    assert identifiers, "no recurring work is registered at all"

    with TestClient(main_module.app) as client:
        response = client.get(FRESHNESS_PATH)
    assert response.status_code in {200, 503}, (
        f"the endpoint neither reported healthy nor unhealthy: "
        f"{response.status_code} {response.text}"
    )

    recorded = _anchors()

    missing = identifiers - set(recorded)
    assert missing == set(), (
        f"serving one request left {sorted(missing)} without a recorded "
        "first-known time. A deployment whose worker never starts would "
        "then compute no overdueness for them and report healthy "
        "indefinitely -- the failure this capability exists to expose"
    )


def test_a_later_observation_does_not_advance_the_anchor() -> None:
    """Scenario: A later observation does not advance the anchor.

    WHEN a piece of work already has a recorded first-known time and is
    observed again
    THEN the recorded time SHALL be unchanged.

    SPECIFIED. An upsert that refreshed the timestamp would keep every
    never-succeeded piece of work permanently inside its tolerance -- and
    since the endpoint performs this write on *every* anonymous request,
    work that never runs would never become overdue at all.
    """
    identifier = _unique_identifier()

    _anchor([identifier])
    first = _anchors().get(identifier)
    assert first is not None, (
        f"recording a first-known time for {identifier} wrote no row"
    )

    _anchor([identifier])
    second = _anchors().get(identifier)

    assert second == first, (
        f"observing {identifier} a second time advanced its recorded "
        f"first-known time from {first} to {second}; the recorded time is "
        "the first one observed"
    )


def test_a_success_does_not_erase_the_first_known_time() -> None:
    """Scenario: A success does not erase the first-known time.

    WHEN a piece of recurring work succeeds
    THEN its recorded first-known time SHALL be unchanged.

    SPECIFIED. Exercised through the operations a success performs: the
    period of overdueness ends, so the suppression record is cleared
    (tasks.md 3.6, which says in the same breath "Do **not** clear the
    first-known row"). This is the assertion that the two records are in
    fact separate tables with independent lifecycles -- folded into one
    row, clearing suppression on recovery would take the anchor with it,
    and the work would then be treated as freshly known on the next check.
    """
    identifier = _unique_identifier()
    check = _check_module()
    record_delivered = _collaborator(check, "record_report_delivered")
    clear = _collaborator(check, "clear_report_suppression")
    suppressed = _collaborator(check, "suppressed_identifiers")

    _anchor([identifier])
    before = _anchors().get(identifier)
    assert before is not None, f"no first-known time was recorded for {identifier}"

    _run(lambda: record_delivered(identifier))
    assert identifier in _run(suppressed), (
        "recording a delivered report left the work unsuppressed, so the "
        "rest of this test would assert nothing"
    )

    # What happens when the work next succeeds.
    _run(lambda: clear(identifier))

    assert identifier not in _run(suppressed), (
        f"the suppression record for {identifier} survived the work "
        "succeeding, so recurrence could never be reported"
    )
    assert _anchors().get(identifier) == before, (
        f"the first-known time for {identifier} changed when its "
        f"suppression was cleared: {before} -> {_anchors().get(identifier)}. "
        "The anchor must persist for as long as the work is registered"
    )
