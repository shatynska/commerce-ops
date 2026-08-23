"""No externally reachable interface starts a piece of recurring work.

Derived strictly from the delta specs of the OpenSpec change
`replace-cron-with-job-runner`:

- `specs/scheduled-jobs/spec.md`, "Scheduled Work Is Not Reachable From
  Outside The Deployment" / Scenario: No external interface starts
  scheduled work
- `specs/product-monitoring/spec.md`, ADDED "The Daily Cadence Runs On A
  Schedule" / Scenario: The daily cadence cannot be started from outside
  the deployment

See `test-manifest.md` at the change root for the full accounting.

## Reading "the system's externally reachable interfaces"

This application has exactly one externally reachable surface: the
FastAPI application in `commerce_ops.main`, routed to by Traefik on the
host (README's Architecture section; `docker-compose.yml`'s labels put
the whole of port 8000 behind `Host(fuperia.shatynska.com)` with no path
restriction, which is what makes enumerating its routes the same thing as
enumerating what the internet can reach). Enumerating `app.routes` is
therefore the enumeration the scenario asks for.

Nothing is invented here: the five cadence paths below are transcribed
from `docker-compose.yml`'s retired crontab and from the
`product-monitoring` requirement this change removes, and they are the
paths that must no longer exist.

Unlike the rest of this pass, these tests have a target that exists
today: `commerce_ops.main` currently mounts all five cadence routes, so
these are expected to fail *on a wrong value* until task 4.1 removes
them -- not on an absent target.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

RETIRED_CADENCE_PATHS = (
    "/products/monitoring/daily",
    "/products/monitoring/weekly",
    "/products/monitoring/biweekly",
    "/products/monitoring/monthly",
    "/products/monitoring/quarterly",
)

CADENCE_NAMES = ("daily", "weekly", "biweekly", "monthly", "quarterly")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Cleared so that a route which merely *rejected* the request for want
    # of a secret would still be visible below as a mounted route, rather
    # than being mistaken for an absent one.
    for name in ("TRIGGER_SECRET", "DATABASE_URL", "PRODUCT_AGENT_SLACK_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _mounted_paths() -> list[str]:
    """Every path this application exposes over HTTP.

    Read from the generated OpenAPI document rather than from
    `app.routes`: this FastAPI version keeps included routers as opaque
    `_IncludedRouter` entries with no `path` of their own (the same fact
    `test_main_slack_wiring.py` records), so filtering `app.routes` for
    `APIRoute` yields an empty list and would make every assertion below
    vacuously true. Verified against the installed FastAPI during this
    pass: `app.routes` exposes only the docs routes plus three
    `_IncludedRouter` entries, while the OpenAPI document lists all seven
    real paths.
    """
    paths = app.openapi().get("paths", {})
    assert paths, "the application exposes no paths at all, which cannot be right"
    return sorted(paths)


def test_no_route_exists_for_starting_a_cadence() -> None:
    """Scenario: No external interface starts scheduled work; Scenario:
    The daily cadence cannot be started from outside the deployment.

    WHEN the system's externally reachable interfaces are enumerated
    THEN none of them SHALL exist for the purpose of starting a piece of
    recurring work / SHALL start the daily cadence.

    SPECIFIED: no such interface exists. Asserted by name against the
    paths that exist today, and by cadence word against any replacement,
    so that moving the endpoint rather than removing it also fails.
    """
    paths = _mounted_paths()

    for retired in RETIRED_CADENCE_PATHS:
        assert retired not in paths, (
            f"{retired} is still mounted; scheduled work must not be "
            "startable from outside the deployment"
        )
    offending = [
        path
        for path in paths
        if "monitoring" in path or any(name in path for name in CADENCE_NAMES)
    ]
    assert offending == [], (
        "these externally reachable routes name a monitoring cadence, so "
        f"scheduled work still has an external trigger surface: {offending}"
    )


@pytest.mark.parametrize("path", RETIRED_CADENCE_PATHS)
def test_a_request_to_a_retired_cadence_path_finds_nothing(
    path: str, client: TestClient
) -> None:
    """Scenario: No external interface starts scheduled work.

    The same fact from the caller's side rather than the route table's:
    the request that used to start a cadence now reaches no handler at
    all.

    SPECIFIED: nothing is there to start the work. DERIVED: "nothing is
    there" is read as HTTP 404 -- the status a FastAPI application
    returns for an unmounted path, and the same reading
    `test_main_monitoring_wiring.py` used in the opposite direction when
    these routes were added.
    """
    response = client.post(path)

    assert response.status_code == 404, (
        f"POST {path} returned {response.status_code}; a cadence trigger "
        "endpoint appears to still be mounted there"
    )


def test_the_application_still_serves_its_remaining_routes(
    client: TestClient,
) -> None:
    """DERIVED guard, not a scenario.

    Removing the cadence routes must remove *those* routes and nothing
    else. Without this, an implementation that dropped the whole
    application's routing would satisfy every assertion above.
    """
    response = client.get("/health")

    assert response.status_code == 200
