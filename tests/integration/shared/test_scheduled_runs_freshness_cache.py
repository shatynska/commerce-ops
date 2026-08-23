"""A cache hit still anchors work that has no first-known time.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Run Freshness Is Reportable Over HTTP" / Scenario: A repeated request
  still anchors work that has no first-known time -- specifically its
  second clause, "SHALL record a time for any registered piece of work that
  has none at that moment".

See `test-manifest.md` at the change root for the full accounting.

## Why this test exists separately from the unit-tier one

tasks.md 6.24 names the trap directly: after the first request nothing
lacks an anchor, so a test that simply issues two requests can only assert
that the upsert *ran* -- never that it wrote a row for work that had none.
Setting it up any other way makes the test vacuous. The only non-vacuous
arrangement is to remove the anchors between the two requests, and rows
only exist to be removed against a real database. That is why this half of
the scenario is in the `pre-push` tier while its first clause is asserted
in `tests/unit/shared/infrastructure/driving/
test_scheduled_runs_freshness_unreadable.py`.

`known_work` is the table name proposal.md and tasks.md 3.2 fix. Its
columns are not fixed by any artifact, so nothing here names one: the rows
are removed wholesale and the effect is read back through the same
accessor the endpoint uses.

**This test deletes every row of `known_work`.** That is destructive to
whatever the local database held, and deliberate -- the table holds only
first-known anchors, which the very next request re-creates. It is
recorded here rather than left for a reader to discover.

## Event loops

Each database interaction outside the HTTP client runs in its own loop
against its own engine; the process-wide provider's engine belongs to the
`TestClient`'s portal loop while the client is open. See
`test_known_work_anchor.py`'s "Event loops" for the hazard this avoids.
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import commerce_ops.main as main_module
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.database import dispose_engine

FRESHNESS_PATH = "/health/scheduled-runs"
KNOWN_WORK_TABLE = "known_work"

register_all()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's known_work migration), and point DATABASE_URL at it "
            "to run tests/integration/shared/."
        )
    return url


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


def _collaborator(name: str) -> Any:
    module = _route_module()
    if not hasattr(module, name):
        pytest.fail(
            f"{module.__name__} exposes no module-level name {name!r}. See "
            "tests/unit/shared/infrastructure/driving/"
            "test_scheduled_runs_freshness.py's docstring."
        )
    return getattr(module, name)


def _registered_identifiers() -> set[str]:
    declared = _collaborator("registered_work")()
    if hasattr(declared, "keys"):
        return {str(key) for key in declared}
    identifiers: set[str] = set()
    for entry in declared:
        for attribute in ("identifier", "id", "task_name", "name"):
            value = getattr(entry, attribute, None)
            if value is not None:
                identifiers.add(str(value))
                break
    return identifiers


def _remove_every_anchor(url: str) -> None:
    """Removes every `known_work` row, through an engine of its own."""

    async def _work() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f"DELETE FROM {KNOWN_WORK_TABLE}"))
        finally:
            await engine.dispose()

    asyncio.run(_work())


def _anchored_identifiers() -> set[str]:
    read = _collaborator("first_known_times")

    async def _work() -> set[str]:
        try:
            return {str(key) for key in await read()}
        finally:
            await dispose_engine()

    return asyncio.run(_work())


def test_a_repeated_request_anchors_work_that_has_none_at_that_moment() -> None:
    """Scenario: A repeated request still anchors work that has no
    first-known time.

    WHEN the freshness endpoint is requested, and requested again soon
    enough that it need not re-evaluate
    THEN the system SHALL perform the first-known recording for every
    registered piece of recurring work on the repeated request regardless,
    rather than serving a previously computed answer without having done so
    AND SHALL record a time for any registered piece of work that has none
    at that moment.

    SPECIFIED. The anchors are removed between the two requests, which is
    the only arrangement in which the second clause can fail: an
    implementation that memoised the upsert away, or that returned the
    cached response before reaching it, leaves the table empty here. And an
    empty table is not a cosmetic defect -- it is a deployment whose work
    can never be found overdue, because nothing anchors the work that has
    never run.

    Both requests are issued through one open client, milliseconds apart,
    so the second falls inside the brief cache window tasks.md 5.7
    establishes. If no cache exists at all the assertion still holds; it is
    the cache's existence that is asserted in the unit tier, by counting
    reads.
    """
    url = _database_url()
    identifiers = _registered_identifiers()
    assert identifiers, "no recurring work is registered at all"

    with TestClient(main_module.app) as client:
        first = client.get(FRESHNESS_PATH)
        assert first.status_code in {200, 503}, (
            f"the first request did not answer: {first.status_code} {first.text}"
        )

        _remove_every_anchor(url)

        second = client.get(FRESHNESS_PATH)
        assert second.status_code in {200, 503}, (
            f"the repeated request did not answer: {second.status_code} {second.text}"
        )

    anchored = _anchored_identifiers()

    missing = identifiers - anchored
    assert missing == set(), (
        f"after their anchors were removed, a repeated request inside the "
        f"cache window left {sorted(missing)} with no first-known time. The "
        "cache short-circuits the evaluation, never the anchor upsert -- "
        "that upsert is the only database access a cache-hit request makes"
    )
