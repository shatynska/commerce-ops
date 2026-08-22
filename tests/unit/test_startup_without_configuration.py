"""Import and startup must not require any configuration to be present.

Derived strictly from the `runtime-configuration` capability's delta spec:
`openspec/changes/revise-foundation-for-launch-mvp/specs/runtime-configuration/spec.md`,
requirement "Importing And Starting The Application Do Not Require
Configuration To Be Present".

WHAT A PASS MEANS HERE. Unlike every other file this change adds, these two
tests exercise a target that already exists: `commerce_ops.main`. The
behaviour they assert holds today, and the requirement's force is that
introducing a settings declaration must not break it -- which is precisely
the risk the change carries, since `pydantic-settings` raises on a missing
required field and the obvious place to put a configuration check is a
FastAPI lifespan hook. So these are regression guards written from a
scenario, and a pass on their first run is the expected, correct result,
not the "passed before any implementation existed" alarm that applies to the
other files.

RELATIONSHIP TO THE THREE FILES THIS CHANGE MUST NOT MODIFY. tasks 8.1-8.2
require `tests/unit/omni_agent/infrastructure/driving/test_main_slack_wiring.py`,
`tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py`
and `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py`
to keep passing unmodified. The first two assert this same shape over three
named variables each, as regression guards for a different requirement
(`deploy-pipeline`'s "Pull Request Validation Gate"). This file neither
edits nor duplicates them: it widens the precondition to *every* variable
the settings declaration declares, which is what this scenario states and
what those files, written before the declaration existed, cannot cover.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

# Every variable the declaration declares (tasks 4.1), plus the one
# deployment-only variable the change names explicitly. "Every declared
# variable absent" is the scenario's precondition, and it is transcribed
# rather than imported from the settings module so that this file -- whose
# subject is `commerce_ops.main`, not the declaration -- keeps working as a
# regression guard even while the settings module does not yet exist.
DECLARED_ENV_VARS = (
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "OMNI_AGENT_SLACK_SIGNING_SECRET",
    "OMNI_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
    "TRIGGER_SECRET",
    "PRODUCT_AGENT_SLACK_SIGNING_SECRET",
    "CLICKUP_API_TOKEN",
    # Added by configure-application-logging (tasks 2.5) -- this
    # transcribed set now spans more than one change.
    "LOG_LEVEL",
)

DEPLOYMENT_ONLY_ENV_VARS = ("POSTGRES_PASSWORD", "IMAGE_TAG")


@pytest.fixture()
def empty_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (*DECLARED_ENV_VARS, *DEPLOYMENT_ONLY_ENV_VARS):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def client(empty_configuration_environment: None) -> Iterator[TestClient]:
    # Context-managed so the application's lifespan runs -- the scenario says
    # "including any startup hook it declares", and a configuration check
    # placed in a lifespan hook is exactly what would fail here.
    with TestClient(app) as test_client:
        yield test_client


def test_application_modules_import_with_an_empty_environment(
    tmp_path: Path,
) -> None:
    """Scenario: Application imports with an empty environment.

    WHEN the application's modules are imported with every declared variable
    absent from the environment
    THEN the import SHALL succeed without raising.

    Run in a fresh interpreter, with an environment built from scratch rather
    than pruned, so that nothing set on the developer's machine can satisfy a
    read at import time; and from `tmp_path`, so no repository-local `.env`
    supplies one either. Within this pytest process `commerce_ops.main` is
    already imported (see the module-level import above), so an in-process
    import would be a cache hit asserting nothing.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import commerce_ops.main"],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Specified.
    assert result.returncode == 0, (
        "importing commerce_ops.main with every declared configuration "
        "variable absent failed; configuration must be read no earlier than "
        "the point at which it is checked or first used.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_http_application_starts_and_serves_with_an_empty_environment(
    client: TestClient,
) -> None:
    """Scenario: HTTP application object starts with an empty environment.

    WHEN the application's HTTP application object is started, including any
    startup hook it declares, with every declared variable absent from the
    environment
    THEN startup SHALL succeed, and endpoints that require no configuration
    SHALL serve normally.

    Startup succeeding is asserted by the `client` fixture's context manager
    completing at all -- a lifespan hook that raised would fail before the
    body of this test runs. `GET /health` is the endpoint that requires no
    configuration (`health-check`'s "Health check succeeds independent of
    database availability").
    """
    response = client.get("/health")

    # Specified: an endpoint requiring no configuration serves normally.
    assert response.status_code == 200
