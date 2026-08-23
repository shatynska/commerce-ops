"""An unreachable database is answered, not waited on.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Run Freshness Is Reportable Over HTTP" / Scenario: Recorded state that
  cannot be read is not reported as healthy -- the unreachable-database
  mechanism.

The absent-setting and malformed-setting mechanisms of the same scenario
are in `tests/unit/shared/infrastructure/driving/
test_scheduled_runs_freshness_unreadable.py`: they raise immediately at the
point of use and reach no network at all, so they belong in the fast tier.
tasks.md 6.22 requires both to be covered, "which fail differently". See
`test-manifest.md` at the change root for the full accounting.

## Why this file is in the integration tier, and why it is never skipped

It opens real TCP connections, so it is not I/O-free and `AGENTS.md` puts
it at `pre-push`. But it needs no *configured* Postgres: each test supplies
its own unreachable address, so unlike its neighbours it does not skip when
`DATABASE_URL` is unset. That is deliberate -- the scenario it covers is
about a database that is not there, and a test that skipped without one
would skip exactly when it could run.

## The two unreachable shapes, and why both are here

- **Refused**: nothing is listening. The connection fails at once, and an
  implementation that catches connection errors passes.
- **Unanswered**: the address absorbs packets and never replies
  (`192.0.2.1`, reserved by RFC 5737 for documentation and routed nowhere).
  This is the shape tasks.md 5.8a exists for: without a short timeout the
  request hangs rather than answering 503 -- on the one endpoint whose
  whole purpose is to be polled by something that will conclude nothing
  from a request that never returns.

The second request is issued on a worker thread and waited on with a hard
ceiling, so an implementation with no timeout fails this test instead of
hanging the suite.
"""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import commerce_ops.main as main_module
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven import database

FRESHNESS_PATH = "/health/scheduled-runs"

# Nothing listens on port 1 of the loopback interface: the connection is
# refused immediately.
REFUSING_URL = "postgresql+asyncpg://commerce:ops@127.0.0.1:1/commerce_ops"

# RFC 5737 reserves 192.0.2.0/24 for documentation; it is routed nowhere,
# so a connection attempt is absorbed rather than refused.
UNANSWERING_URL = "postgresql+asyncpg://commerce:ops@192.0.2.1:5432/commerce_ops"

# What "within a bounded time" is taken to mean here. No artifact fixes a
# figure -- design.md says only "a short timeout" and "promptly" -- so this
# is generous by an order of magnitude over anything an implementation
# would choose. What it asserts is the difference between answering and
# hanging, not a latency budget. DERIVED, recorded in test-manifest.md.
BOUNDED_SECONDS = 20.0

# The ceiling on waiting for the request at all, after which the request is
# abandoned and the test fails rather than the suite hanging.
ABANDON_AFTER_SECONDS = 120.0

register_all()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # `raise_server_exceptions=False`: a handler that fails instead of
    # answering must be observed as a status code, since the scenario is
    # stated in terms of what the response indicates.
    with TestClient(main_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_engine_left_over() -> Iterator[None]:
    """Test infrastructure, not the subject of any requirement.

    The session provider caches one engine per process. These tests point
    `DATABASE_URL` at an address nothing answers, which only takes effect
    while no engine built from a working one is already cached.
    """
    database._get_engine_and_session_factory.cache_clear()
    yield
    database._get_engine_and_session_factory.cache_clear()


def _request_with_a_ceiling(client: TestClient) -> tuple[Any, float]:
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, FRESHNESS_PATH)
        try:
            response = future.result(timeout=ABANDON_AFTER_SECONDS)
        except concurrent.futures.TimeoutError:
            pytest.fail(
                "the freshness endpoint had still not answered after "
                f"{ABANDON_AFTER_SECONDS:.0f}s with the database "
                "unreachable. It must respond within a bounded time rather "
                "than waiting indefinitely on unreadable state -- the "
                "external checker polling it concludes nothing from a "
                "request that never returns (tasks.md 5.8a)"
            )
    return response, time.monotonic() - started


def _assert_unhealthy_and_empty(response: Any, elapsed: float, how: str) -> None:
    assert response.status_code == 503, (
        f"with the database {how} the endpoint answered "
        f"{response.status_code}, not 503: {response.text!r}"
    )
    body = response.json()
    assert body.get("status") == "unhealthy", (
        f"the body does not report an unhealthy state ({how}): {body!r}"
    )
    assert body.get("work") == [], (
        "the response reports work while the state it would have been "
        f"computed from is unreadable ({how}); the empty array is what "
        f"tells a human which case this is: {body!r}"
    )
    assert elapsed < BOUNDED_SECONDS, (
        f"the endpoint took {elapsed:.1f}s to answer with the database "
        f"{how}; the read and the anchor upsert are given a short timeout, "
        "and expiry is itself the unreadable case"
    )


def test_a_refused_database_connection_is_not_reported_as_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Recorded state that cannot be read is not reported as
    healthy -- an unreachable database that refuses the connection.

    WHEN the freshness endpoint is requested and the recorded state cannot
    be read
    THEN the system SHALL indicate an unhealthy state in a way an automated
    checker can act on without parsing prose
    AND SHALL NOT report any piece of work as being within its tolerance
    AND SHALL respond within a bounded time.

    SPECIFIED. Indistinguishable to a monitor from overdue work, which is
    correct -- both mean the deployment cannot demonstrate that its
    scheduled work is happening -- while the empty array tells a human
    which of the two they are looking at.
    """
    monkeypatch.setenv("DATABASE_URL", REFUSING_URL)

    response, elapsed = _request_with_a_ceiling(client)

    _assert_unhealthy_and_empty(response, elapsed, how="refusing connections")


def test_a_database_that_never_answers_is_not_waited_on_indefinitely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Recorded state that cannot be read is not reported as
    healthy -- the "SHALL respond within a bounded time rather than waiting
    indefinitely" clause.

    SPECIFIED as to the clause; DERIVED as to the bound, which no artifact
    fixes -- see `BOUNDED_SECONDS`. A database that accepts nothing and
    refuses nothing is the shape that discriminates: an implementation
    handling only refused connections answers the test above and hangs
    here.
    """
    monkeypatch.setenv("DATABASE_URL", UNANSWERING_URL)

    response, elapsed = _request_with_a_ceiling(client)

    _assert_unhealthy_and_empty(response, elapsed, how="never answering")
