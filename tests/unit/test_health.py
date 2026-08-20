"""Tests for the `GET /health` liveness endpoint.

Derived from the `health-check` capability's delta spec:
openspec/changes/deploy-health-endpoint/specs/health-check/spec.md

Both requirements in that spec are `ADDED` (this is the first product-facing
spec in this repository), so these tests are written directly from the
scenarios below, not against any pre-existing implementation.

At the time these tests were written, `src/commerce_ops/` does not exist yet
and FastAPI is not a declared dependency (see tasks.md section 1) — so these
tests are expected to fail on an absent target (`ModuleNotFoundError`) until
that scaffolding lands. That failure establishes only that the target is
absent, nothing about whether the assertions below are correct; see
`test-manifest.md` at the change root for the full accounting.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # Used as a context manager so any startup-time behavior (e.g. an
    # application lifespan hook) runs, matching the scenarios' "while the
    # application is running" precondition.
    with TestClient(app) as test_client:
        yield test_client


def _assert_healthy_response(body: dict[str, Any]) -> None:
    """Asserts the response body "indicates the service is healthy".

    DERIVED / unresolved project question: the delta spec requires "a JSON
    body indicating the service is healthy" (Requirement: Liveness Endpoint
    Available) but does not pin an exact schema, and neither tasks.md nor
    design.md name one either. This assumes the common `{"status": "ok"}`
    convention as a placeholder contract; see test-manifest.md, which
    records this as an unresolved project question that implementation (or
    a design update) should settle explicitly rather than this test
    silently deciding it.
    """
    assert body.get("status") == "ok"


def test_health_returns_success_when_running(client: TestClient) -> None:
    """Scenario: Health check returns success when the service is running.

    WHEN a client sends GET /health while the application is running
    THEN the response SHALL have HTTP status 200 and a JSON body
    indicating the service is healthy.
    """
    response = client.get("/health")

    # Specified: status 200.
    assert response.status_code == 200
    # Derived: "a JSON body" is interpreted as a JSON-typed response.
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert isinstance(body, dict)
    # Derived (see _assert_healthy_response docstring).
    _assert_healthy_response(body)


def test_health_succeeds_with_no_database_configured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Scenario: Health check succeeds independent of database availability.

    WHEN GET /health is requested and no database connection exists or is
    configured
    THEN the endpoint SHALL still return the successful response described
    above.
    """
    # Specified precondition: no database connection exists or is
    # configured. There is no settings/config module in this repository
    # yet, so this removes the conventional env-var names a future
    # Postgres configuration would plausibly use, to make the "not
    # configured" precondition explicit rather than incidental.
    for var in (
        "DATABASE_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(var, raising=False)

    response = client.get("/health")

    # Specified: still returns the successful response from the first
    # scenario (status 200 + JSON body indicating healthy).
    assert response.status_code == 200
    _assert_healthy_response(response.json())
