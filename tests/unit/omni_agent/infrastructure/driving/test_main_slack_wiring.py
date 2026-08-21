"""Import-time / wiring guards for the Slack driving adapter.

Originally derived from the `trigger-omni-agent-via-slack` change
(`openspec/changes/trigger-omni-agent-via-slack/`: specs/slack-trigger/spec.md,
design.md, tasks.md 5.1/6.1). As of `module-boundary-conventions`, the
adapter this file guards lives in
`src/commerce_ops/omni_agent/infrastructure/driving/slack.py` (moved out of
`shared`, which is no longer allowed to reach into `omni_agent`'s internals)
and mounts at `POST /omni_agent/slack/events`.

Provenance of what is asserted here is recorded in `test-manifest.md` at the
original change root. Summary:
- `test_main_imports_without_slack_secrets_in_environment` and
  `test_health_endpoint_still_serves_without_slack_secrets` are REGRESSION
  GUARDS, not scenario coverage. They must keep passing regardless of which
  module the adapter lives in. Their subject is the `deploy-pipeline` spec's
  "Pull Request Validation Gate" requirement, which runs `tests/unit` and
  `tests/agents` with no production-scoped secrets and "without any host
  connection" -- so eager construction of `SignatureVerifier`/`WebClient` at
  import time would break that gate.
- `test_slack_events_route_is_registered` confirms the router `main.py`
  includes actually mounts the events route, independent of which module
  contributes that router.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

# module-boundary-conventions: the route moved from POST /slack/events to
# POST /omni_agent/slack/events when the adapter relocated into omni_agent's
# own infrastructure/driving layer -- this is the URL Slack's Event
# Subscriptions Request URL must point at.
SLACK_EVENTS_PATH = "/omni_agent/slack/events"

# The environment variables the deploy pipeline delivers as `production`
# Environment secrets, and which the PR-validation gate therefore does NOT
# have. `OPENAI_API_KEY` is included because the same gate lacks it too and
# `handle_app_mention` reaches omni-agent, which needs it.
RUNTIME_SECRET_ENV_VARS = (
    "OMNI_AGENT_SLACK_SIGNING_SECRET",
    "OMNI_AGENT_SLACK_BOT_TOKEN",
    "OPENAI_API_KEY",
)


@pytest.fixture()
def no_slack_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removes every runtime secret this change introduces from the env."""
    for var in RUNTIME_SECRET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(no_slack_secrets: None) -> Iterator[TestClient]:
    # Context-managed so any lifespan/startup hook runs -- an adapter that
    # reached Slack at startup rather than at import would surface here.
    with TestClient(app) as test_client:
        yield test_client


def test_main_imports_without_slack_secrets_in_environment() -> None:
    """Regression guard, not a spec scenario.

    `commerce_ops.main` must import cleanly with OMNI_AGENT_SLACK_SIGNING_SECRET /
    OMNI_AGENT_SLACK_BOT_TOKEN / OPENAI_API_KEY absent, because the deploy-pipeline
    spec's "Pull Request Validation Gate" requirement runs the unit and
    agent tiers without access to production-scoped secrets and without any
    host connection.

    Run in a fresh interpreter on purpose: within this pytest process
    `commerce_ops.main` is already imported (see the module-level import
    above), so an in-process import would be a no-op cache hit and would
    assert nothing about import-time behaviour.
    """
    env = {k: v for k, v in os.environ.items() if k not in RUNTIME_SECRET_ENV_VARS}

    result = subprocess.run(
        [sys.executable, "-c", "import commerce_ops.main"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.main with Slack/OpenAI secrets absent failed; "
        "the Slack adapter's SignatureVerifier/WebClient must be constructed "
        "lazily behind a cached factory, never at module import time.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_health_endpoint_still_serves_without_slack_secrets(
    client: TestClient,
) -> None:
    """Regression guard: registering the Slack router must not couple
    `/health` to Slack configuration or reachability.

    Complements `tests/unit/test_health.py` (which is left untouched) by
    exercising the same endpoint with the Slack-related environment
    explicitly cleared.
    """
    response = client.get("/health")

    assert response.status_code == 200


def test_slack_events_route_is_registered(client: TestClient) -> None:
    """Wiring: the Slack router is included in `main.py`.

    Asserted behaviourally rather than by inspecting `app.routes`, because
    this FastAPI version keeps included routers as opaque `_IncludedRouter`
    entries rather than flattening them into inspectable `APIRoute` objects.

    The request below is unsigned, so a correct implementation rejects it --
    what matters here is only that something is mounted at the path and
    accepts POST, i.e. the response is neither 404 (no such route) nor 405
    (route exists but not for POST).
    """
    response = client.post(SLACK_EVENTS_PATH, json={})

    assert response.status_code != 404, f"no route mounted at POST {SLACK_EVENTS_PATH}"
    assert response.status_code != 405, (
        f"{SLACK_EVENTS_PATH} exists but does not accept POST"
    )
