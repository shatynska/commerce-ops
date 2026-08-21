"""Tests for the `product-monitoring` capability's five trigger routes.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/add-product-agent-daily-digest/specs/product-monitoring/spec.md`:

- "Each Cadence Has Its Own Guarded Trigger Endpoint" / Scenario: A cadence
  endpoint rejects an unguarded request
- "Daily Cadence Lists Existing Product Names" / Scenario: Daily trigger
  lists product names
- "Daily Cadence Lists Existing Product Names" / Scenario: No products exist
- "Non-Daily Cadences Acknowledge Their Trigger Without Reporting" /
  Scenario: A non-daily cadence is triggered
- "Report Delivery Failure Is Decoupled From The Trigger" / Scenario: Slack
  post fails
- "Database Read Failure Is Surfaced, Not Treated Like A Delivery Failure" /
  Scenario: Database read fails

See `test-manifest.md` at this change's root for the full
specified/derived/deliberately-untested accounting.

## Everything about the routes' internals is INVENTED

No artifact fixes a module path for the five routes, a router variable
name, the names the router imports its collaborators under, or the shape
of the per-request session dependency. Only the five paths themselves are
SPECIFIED, in `design.md`'s Decisions ("Each cadence gets its own route ...
E.g. `POST /products/monitoring/daily`, `/weekly`, `/biweekly`, `/monthly`,
`/quarterly`"). This file assumes:

- Module: `commerce_ops.products.infrastructure.driving.monitoring`,
  exposing an `APIRouter` at module attribute `router`.
- That module imports its three collaborators *by name* into its own
  module namespace -- the same pattern
  `omni_agent/infrastructure/driving/slack.py` already uses for
  `answer_question`, and that
  `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`
  already relies on to substitute fakes:
  - `run_daily_digest` (from `commerce_ops.products.application`) -- the
    use case `daily` calls (Task 3.1/5.2).
  - `post_monitoring_message` (from
    `commerce_ops.products.infrastructure.driven.slack_notifier`) -- the
    notifier `daily` calls on a successful read (Task 4/5.2), taking one
    positional `message: str`.
  - `get_session` -- the per-request `AsyncSession` FastAPI dependency
    (Task 2.3), which `daily` alone depends on (Task 5.1) to construct a
    `ProductRepository` satisfying the `ProductNameReader` port passed into
    `run_daily_digest`.
- `daily`'s route body is therefore, in shape: resolve the session, build
  the repository, call `run_daily_digest`; on success, format the returned
  names into a message and call `post_monitoring_message`; on a raised
  failure from `run_daily_digest`, respond with a failing status and
  attempt `post_monitoring_message` with a failure message instead.
- The other four routes call *some* no-op placeholder (Task 3.2) that this
  file never names or patches, since none of the scenarios below turn on
  what that placeholder does internally -- only on the observable facts
  that the trigger is acknowledged and no Slack message results.

Patching `run_daily_digest` directly (rather than trying to substitute a
session/engine) is a deliberate level choice: `tasks.md` 8.3 already
assigns `ProductRepository.list_names()`'s own real-Postgres behavior to
`tests/integration/products/`, so these route-level tests substitute past
the repository entirely, the same way the existing Slack adapter tests
substitute `answer_question` rather than the LangGraph graph it wraps.
`get_session` is still overridden (via `app.dependency_overrides`, not by
monkeypatching) purely so route resolution does not require a real
`DATABASE_URL` in this unit-tier process -- the yielded session is never
actually used, since `run_daily_digest` is faked out before it would be.

If any of the above differs from the real implementation -- a different
module path, different imported names, a different session-dependency
shape, or a different message-formatting/failure-response mechanism --
correcting the imports, the `app.dependency_overrides` target, or the
`_build_app` helper is a fixture correction; the postconditions asserted
(status code, what was or wasn't posted, whether the guard was honored)
are what trace to the spec and must survive any such correction unweakened.

At the time this pass was written, none of the above exists, so every test
in this file is expected to fail on an absent target (`ModuleNotFoundError`
or `ImportError`) until Tasks 1-5 land.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.products.infrastructure.driving import monitoring

TRIGGER_SECRET = "test-trigger-secret-not-a-real-credential"

CADENCE_PATHS: Final[dict[str, str]] = {
    "daily": "/products/monitoring/daily",
    "weekly": "/products/monitoring/weekly",
    "biweekly": "/products/monitoring/biweekly",
    "monthly": "/products/monitoring/monthly",
    "quarterly": "/products/monitoring/quarterly",
}
NON_DAILY_CADENCES: Final[tuple[str, ...]] = (
    "weekly",
    "biweekly",
    "monthly",
    "quarterly",
)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingNotifier:
    """Stands in for `post_monitoring_message`, recording each call.

    Can be scripted to raise instead, for the "Slack post fails" scenario.
    """

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.posted: list[str] = []
        self._failure = failure

    def __call__(self, message: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.posted.append(message)


class _ScriptedDailyDigest:
    """Stands in for `run_daily_digest`: scripted names or a scripted
    failure, never both. Records what it was called with."""

    def __init__(
        self, *, names: tuple[str, ...] | None = None, failure: Exception | None = None
    ) -> None:
        self._names = names
        self._failure = failure
        self.calls: list[Any] = []

    async def __call__(self, reader: Any) -> tuple[str, ...]:
        self.calls.append(reader)
        if self._failure is not None:
            raise self._failure
        assert self._names is not None
        return self._names


async def _fake_session() -> AsyncIterator[None]:
    """Overrides `get_session` so route resolution never needs a real
    `DATABASE_URL` or a real Postgres connection in this unit-tier file.

    Yields `None` deliberately: the object is only ever passed into
    `ProductRepository(session)`'s constructor by the route (never used for
    an actual query here), because `run_daily_digest` itself is patched out
    before any query would run.
    """
    yield None


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def trigger_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ambient environment the shared internal-trigger guard reads its
    configured secret from. Set (not overridden away) deliberately, so
    these tests exercise the *real* guard wired onto each route -- the
    thing "Each Cadence Has Its Own Guarded Trigger Endpoint" is actually
    about -- rather than a stand-in for it.
    """
    monkeypatch.setenv("TRIGGER_SECRET", TRIGGER_SECRET)


@pytest.fixture()
def notifier(monkeypatch: pytest.MonkeyPatch) -> Iterator[_RecordingNotifier]:
    fake = _RecordingNotifier()
    monkeypatch.setattr(monitoring, "post_monitoring_message", fake)
    yield fake


@pytest.fixture()
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(monitoring.router)
    fastapi_app.dependency_overrides[monitoring.get_session] = _fake_session
    return fastapi_app


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _trigger_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TRIGGER_SECRET}"}


def install_daily_digest(
    monkeypatch: pytest.MonkeyPatch, fake: _ScriptedDailyDigest
) -> _ScriptedDailyDigest:
    monkeypatch.setattr(monitoring, "run_daily_digest", fake)
    return fake


# --------------------------------------------------------------------------
# Requirement: Each Cadence Has Its Own Guarded Trigger Endpoint
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cadence", list(CADENCE_PATHS), ids=list(CADENCE_PATHS))
def test_unguarded_request_is_rejected_and_performs_no_reporting_action(
    cadence: str,
    client: TestClient,
    notifier: _RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A cadence endpoint rejects an unguarded request.

    WHEN a request to any cadence's endpoint does not satisfy the
    internal-trigger guard
    THEN the system SHALL reject the request and SHALL NOT perform that
    cadence's reporting action.

    No `Authorization` header is sent -- `TRIGGER_SECRET` is configured
    (via the autouse `trigger_env` fixture), so this fails the guard
    specifically for lacking a matching secret, not for the secret being
    unconfigured (that case belongs to `internal-trigger`'s own spec,
    covered in `test_internal_trigger_guard.py`).
    """
    daily_fake = install_daily_digest(monkeypatch, _ScriptedDailyDigest(names=()))

    response = client.post(CADENCE_PATHS[cadence])

    # SPECIFIED: the request is rejected. Derived: consistent with
    # `internal-trigger`'s own 401, since this is that same guard.
    assert response.status_code == 401
    # SPECIFIED: no reporting action was performed.
    assert notifier.posted == []
    assert daily_fake.calls == []


# --------------------------------------------------------------------------
# Requirement: Daily Cadence Lists Existing Product Names
# --------------------------------------------------------------------------


def test_daily_trigger_lists_product_names(
    client: TestClient,
    notifier: _RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Daily trigger lists product names.

    WHEN the daily endpoint is invoked and at least one product exists
    THEN the system SHALL post a Slack message listing the name of every
    existing product.
    """
    install_daily_digest(
        monkeypatch, _ScriptedDailyDigest(names=("Widget A", "Widget B"))
    )

    response = client.post(CADENCE_PATHS["daily"], headers=_trigger_headers())

    assert 200 <= response.status_code < 300
    # SPECIFIED: a Slack message listing every existing product's name.
    assert len(notifier.posted) == 1
    message = notifier.posted[0]
    assert "Widget A" in message
    assert "Widget B" in message


def test_no_products_exist_posts_a_message_rather_than_nothing(
    client: TestClient,
    notifier: _RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No products exist.

    WHEN the daily endpoint is invoked and no product exists
    THEN the system SHALL post a message indicating no products exist,
    rather than posting nothing.

    DELIBERATELY UNTESTED: the exact wording of the "no products exist"
    message. Neither the spec nor design.md pins any phrasing, and
    asserting particular words here would impose a contract nobody agreed
    to -- the same reasoning
    `test_omni_agent_invocation_failure_posts_a_message_to_the_channel`
    already applies to its own failure message in
    `test_slack_events_endpoint.py`. What is asserted is that a message
    reaches the channel at all.
    """
    install_daily_digest(monkeypatch, _ScriptedDailyDigest(names=()))

    response = client.post(CADENCE_PATHS["daily"], headers=_trigger_headers())

    assert 200 <= response.status_code < 300
    # SPECIFIED: a message is posted, rather than nothing.
    assert len(notifier.posted) == 1
    assert notifier.posted[0], "the posted message was empty"


# --------------------------------------------------------------------------
# Requirement: Non-Daily Cadences Acknowledge Their Trigger Without Reporting
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cadence", NON_DAILY_CADENCES)
def test_non_daily_cadence_is_acknowledged_without_posting(
    cadence: str, client: TestClient, notifier: _RecordingNotifier
) -> None:
    """Scenario: A non-daily cadence is triggered.

    WHEN the weekly, biweekly, monthly, or quarterly endpoint is invoked
    and satisfies the internal-trigger guard
    THEN the system SHALL respond indicating the trigger was received and
    SHALL NOT post any Slack message.
    """
    response = client.post(CADENCE_PATHS[cadence], headers=_trigger_headers())

    # DERIVED: "indicating the trigger was received" is read as a 2xx
    # response, matching the equivalent reading used throughout
    # `test_slack_events_endpoint.py` for an analogous "acknowledged"
    # response with no status code pinned by any artifact.
    assert 200 <= response.status_code < 300
    # SPECIFIED: no Slack message is posted.
    assert notifier.posted == []


# --------------------------------------------------------------------------
# Requirement: Report Delivery Failure Is Decoupled From The Trigger
# --------------------------------------------------------------------------


def test_slack_post_failure_still_yields_an_accepted_trigger_response(
    client: TestClient,
    notifier: _RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: Slack post fails.

    WHEN a cadence's report has been assembled and posting it to Slack
    fails
    THEN the system SHALL log the failure
    AND the triggering request SHALL still receive a response indicating
    the trigger was accepted.
    """
    install_daily_digest(monkeypatch, _ScriptedDailyDigest(names=("Widget A",)))
    monkeypatch.setattr(
        monitoring,
        "post_monitoring_message",
        _RecordingNotifier(failure=RuntimeError("simulated Slack API failure")),
    )

    with caplog.at_level(logging.WARNING):
        response = client.post(CADENCE_PATHS["daily"], headers=_trigger_headers())

    # SPECIFIED: the triggering request still receives a response
    # indicating the trigger was accepted -- unaffected by the delivery
    # failure, and distinct from the database-read-failure response below.
    assert 200 <= response.status_code < 300
    # SPECIFIED: the failure is logged. DERIVED: "logged" is read as at
    # least one log record at WARNING level or above, since neither the
    # spec nor design.md pins a logger name or message.
    assert any(record.levelno >= logging.WARNING for record in caplog.records), (
        "expected the Slack post failure to be logged at WARNING level or "
        f"above; captured records: {[r.getMessage() for r in caplog.records]}"
    )


# --------------------------------------------------------------------------
# Requirement: Database Read Failure Is Surfaced, Not Treated Like A
# Delivery Failure
# --------------------------------------------------------------------------


def test_database_read_failure_yields_a_failing_status_and_an_attempted_post(
    client: TestClient,
    notifier: _RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Database read fails.

    WHEN the daily endpoint is invoked and reading products from the
    database fails
    THEN the system SHALL respond with a failing status
    AND SHALL attempt to post a message to the configured channel
    indicating the database could not be read.
    """
    install_daily_digest(
        monkeypatch,
        _ScriptedDailyDigest(failure=RuntimeError("simulated database-read failure")),
    )

    response = client.post(CADENCE_PATHS["daily"], headers=_trigger_headers())

    # SPECIFIED: a failing status, distinct from the accepted-trigger
    # response used when only delivery fails. DERIVED: "failing" is read as
    # a server error (5xx), since the endpoint's own job -- reading the
    # database -- never completed; neither the spec nor design.md pins an
    # exact code.
    assert response.status_code >= 500, (
        f"expected a failing (5xx) status for a database-read failure, got "
        f"{response.status_code}"
    )
    # SPECIFIED: an attempt was made to post a message indicating the
    # database could not be read. DELIBERATELY UNTESTED: the message's
    # exact wording, same reasoning as the "no products exist" scenario
    # above.
    assert len(notifier.posted) == 1
    assert notifier.posted[0], "the attempted failure message was empty"
