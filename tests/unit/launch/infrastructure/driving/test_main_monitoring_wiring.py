"""Import-time / wiring guards for the `product-monitoring` driving routes.

Mirrors
`tests/unit/omni_agent/infrastructure/driving/test_main_slack_wiring.py`'s
own two regression guards, per `tasks.md` 8.6 of this change
("Regression guard mirroring `test_main_slack_wiring.py`: importing `main`
and hitting `/health` succeeds without
`PRODUCT_AGENT_SLACK_BOT_TOKEN`/`DATABASE_URL` in the environment").
`TRIGGER_SECRET` was named there too, until replace-cron-with-job-runner
removed the variable along with the cadence routes this file also guarded.

These are REGRESSION GUARDS, not scenario coverage -- no
`#### Scenario:` block in either of this change's delta specs asks for
this. Their subject is the `deploy-pipeline` spec's "Pull Request
Validation Gate" requirement, which runs `tests/unit` and `tests/agents`
with no production-scoped secrets and "without any host connection" (see
`test_main_slack_wiring.py`'s own module docstring for the fuller
citation). `DATABASE_URL`'s absence specifically guards Task 2.3's engine
staying lazily constructed rather than built at import time -- an
implementation that read `DATABASE_URL` eagerly at import (e.g. to build
the `create_async_engine`/`async_sessionmaker` pair) would fail the first
test below.

## What's INVENTED here

The five cadence paths are SPECIFIED (`design.md`'s Decisions). Whether
`main.py` actually mounts `commerce_ops.launch.infrastructure.driving.monitoring`'s
router (Task 5.6) is not itself observable from outside except behaviorally
-- `test_route_is_registered` below follows
`test_slack_events_route_is_registered`'s own precedent exactly: a request
that would 404 if nothing were mounted at the path, or 405 if the path
existed but didn't accept POST, tells us the router is wired in, without
needing to inspect `app.routes` (this FastAPI version keeps included
routers as opaque `_IncludedRouter` entries, per that test's own comment).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

# The env vars `tasks.md` 8.6 named. `TRIGGER_SECRET` was the third until
# replace-cron-with-job-runner removed the variable along with its guard.
RUNTIME_ENV_VARS = (
    "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    "DATABASE_URL",
)


@pytest.fixture()
def no_monitoring_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in RUNTIME_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(no_monitoring_secrets: None) -> Iterator[TestClient]:
    # Context-managed so any lifespan/startup hook runs -- an
    # implementation that eagerly connected to Postgres at startup rather
    # than lazily per-request would surface here.
    with TestClient(app) as test_client:
        yield test_client


def test_main_imports_without_trigger_slack_or_database_secrets_in_environment() -> (
    None
):
    """Regression guard, not a spec scenario.

    `commerce_ops.main` must import cleanly with
    `PRODUCT_AGENT_SLACK_BOT_TOKEN` / `DATABASE_URL` absent, because the
    `deploy-pipeline` spec's "Pull Request Validation Gate" requirement runs
    the unit and agent tiers without access to production-scoped secrets
    and without any host connection.

    Run in a fresh interpreter on purpose, matching
    `test_main_slack_wiring.py`'s own reasoning: within this pytest process
    `commerce_ops.main` is already imported, so an in-process import would
    be a no-op cache hit and would assert nothing about import-time
    behaviour.
    """
    env = {k: v for k, v in os.environ.items() if k not in RUNTIME_ENV_VARS}

    result = subprocess.run(
        [sys.executable, "-c", "import commerce_ops.main"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.main with "
        "PRODUCT_AGENT_SLACK_BOT_TOKEN / DATABASE_URL absent failed; the "
        "monitoring routes' session/Slack-client construction must be "
        "lazy, never performed at module import time.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_health_endpoint_still_serves_without_monitoring_secrets(
    client: TestClient,
) -> None:
    """Regression guard: registering the monitoring routers must not couple
    `/health` to trigger/Slack/database configuration or reachability.

    Complements `tests/unit/test_health.py` (left untouched) by exercising
    the same endpoint with this change's environment explicitly cleared.
    """
    response = client.get("/health")

    assert response.status_code == 200
