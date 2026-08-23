"""No externally reachable interface starts the daily briefing.

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/briefing/spec.md

Covers *The daily briefing runs on a schedule* / Scenario: The briefing
cannot be started from outside the deployment. Its sibling scenario (the
briefing runs when its schedule is due) is at the job level, in
`tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`.

## Reading "the system's externally reachable interfaces"

Unchanged from `tests/unit/test_no_external_cadence_trigger.py`, which
reads the same words for the retired daily listing: this application has
exactly one externally reachable surface -- the FastAPI application in
`commerce_ops.main`, which `docker-compose.yml`'s labels put behind a host
rule with no path restriction. Enumerating its OpenAPI paths is therefore
the enumeration the scenario asks for, and is read from the generated
document rather than from `app.routes` for the reason that file records
(included routers are opaque entries with no path of their own, so
filtering `app.routes` would make every assertion below vacuously true).

## Why a separate file from `test_no_external_cadence_trigger.py`

That file's own assertions are written against the retired listing's five
cadence paths and the word "monitoring". A route named for the *briefing*
-- `/briefing/run`, say -- would pass every one of them, so the scenario
this change adds needs an assertion of its own rather than the existing
file's coverage by coincidence.

Nothing here is invented. The vocabulary below is the briefing's own, and
the assertion is a negative one: no such path may exist, whatever it is
called.

Unlike most of this pass, the target exists today -- `commerce_ops.main`
is importable -- so these tests are expected to *pass* from the start,
including before the briefing exists at all. That is the correct outcome
for a requirement stating that something must never be built (the fourth
failure state in `ai-toolkit:testing` does not apply: nothing here could
be satisfied by an absent implementation being mistaken for a correct
one). What they guard against is a later change mounting a manual
"run the briefing now" endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

# The words an externally reachable briefing trigger would plausibly be
# named with. `digest` is included because the briefing takes the retired
# digest's place and a re-mounted trigger might keep the old noun.
BRIEFING_WORDS: Final = ("brief", "digest")

# Paths a manual trigger would most plausibly be mounted at, asserted by
# name as well as by word so that the check reads concretely.
UNMOUNTED_TRIGGER_PATHS: Final = (
    "/briefing",
    "/briefing/run",
    "/briefing/daily",
    "/monitoring/briefing",
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Cleared so that a route which merely *rejected* the request for want
    # of configuration would still be visible below as a mounted route,
    # rather than being mistaken for an absent one.
    for name in (
        "TRIGGER_SECRET",
        "DATABASE_URL",
        "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _mounted_paths() -> list[str]:
    paths = app.openapi().get("paths", {})
    assert paths, "the application exposes no paths at all, which cannot be right"
    return sorted(paths)


def test_no_externally_reachable_path_names_the_briefing() -> None:
    """Scenario: The briefing cannot be started from outside the
    deployment.

    WHEN the system's externally reachable interfaces are enumerated
    THEN none of them SHALL start the daily briefing.

    SPECIFIED: no such interface exists. Asserted by word rather than by a
    single transcribed path, so that mounting a trigger under any name
    built from the briefing's own vocabulary fails here.
    """
    paths = _mounted_paths()

    offending = [
        path for path in paths if any(word in path.lower() for word in BRIEFING_WORDS)
    ]

    assert offending == [], (
        "these externally reachable routes name the briefing, so the daily "
        f"briefing has an external trigger surface: {offending}"
    )


@pytest.mark.parametrize("path", UNMOUNTED_TRIGGER_PATHS)
def test_a_request_to_a_briefing_trigger_path_finds_nothing(
    path: str, client: TestClient
) -> None:
    """Scenario: The briefing cannot be started from outside the
    deployment -- the same fact from the caller's side.

    DERIVED: "nothing is there" is read as HTTP 404, the status a FastAPI
    application returns for an unmounted path, and the reading
    `test_no_external_cadence_trigger.py` already records for the retired
    cadence paths.
    """
    response = client.post(path)

    assert response.status_code == 404, (
        f"POST {path} returned {response.status_code}; something appears to "
        "be mounted there that could start the briefing"
    )


def test_the_application_still_serves_its_remaining_routes(
    client: TestClient,
) -> None:
    """DERIVED guard, not a scenario.

    Without it, an application whose routing was broken entirely would
    satisfy every assertion above.
    """
    response = client.get("/health")

    assert response.status_code == 200
