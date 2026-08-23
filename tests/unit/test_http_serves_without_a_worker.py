"""HTTP is served whether or not a worker is running.

Derived strictly from `specs/scheduled-jobs/spec.md` in the OpenSpec
change `replace-cron-with-job-runner`:

- "A Worker Failure Does Not Prevent The Application From Serving" /
  Scenario: HTTP is served while no worker is running

See `test-manifest.md` at the change root for the full accounting.

## How "no process running scheduled work is available" is arranged

By running the HTTP application in a process where no worker exists at
all -- which is what every test process in this project already is. The
scenario's precondition is therefore the ambient condition here, and what
the tests establish is that the application serves under it.

The structural half of the requirement ("SHALL be separate from the
process serving HTTP requests") is asserted in a fresh interpreter: the
HTTP process must not so much as import the worker entry point, because
an entry point imported into the serving process is a worker that shares
its fate. The compose-level half -- that `worker` is a service of its own
rather than a second command in `app`'s container -- is asserted in
`tests/unit/test_compose_worker_service.py`.

Both tests here have a target that exists today -- `commerce_ops.main`
-- and both are expected to pass on their first run. That is the expected
result for a test written against code that already exists, not the
alarm it would be for one written against an absent target: what they
establish is that the property holds *now* and cannot be lost when the
worker entry point arrives. Recorded as such in the manifest.

The second test in particular passes today for a reason that will change
under it: `commerce_ops.worker` does not exist yet, so nothing can import
it. Once it does exist, the same assertion starts discriminating -- which
is exactly when it matters, since that is when someone could wire it into
`main`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from commerce_ops.main import app

WORKER_MODULE = "commerce_ops.worker"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # No worker, and no configuration a worker would have supplied: the
    # scenario's "no process running scheduled work is available", taken
    # at its strongest.
    for name in ("DATABASE_URL", "PRODUCT_AGENT_SLACK_BOT_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def test_http_is_served_while_no_worker_is_running(client: TestClient) -> None:
    """Scenario: HTTP is served while no worker is running.

    WHEN no process running scheduled work is available
    THEN the application SHALL continue to serve HTTP requests.

    Context-managed so the application's lifespan actually runs: an
    implementation that started or awaited a worker during startup would
    surface here rather than at deploy time.
    """
    response = client.get("/health")

    assert response.status_code == 200


def test_the_http_process_does_not_import_the_worker_entry_point() -> None:
    """Scenario: HTTP is served while no worker is running -- the
    structural half.

    SPECIFIED: "The process running scheduled work SHALL be separate from
    the process serving HTTP requests, such that the failure or absence of
    the former does not stop the latter from serving." A worker entry
    point imported by the serving process is not a separate process, and
    its import-time failure would take the HTTP application down with it.

    Run in a fresh interpreter because `commerce_ops.worker` is already
    imported inside this pytest process by other test files, so an
    in-process check would assert nothing.
    """
    script = (
        "import sys\n"
        "import commerce_ops.main\n"
        f"print({WORKER_MODULE!r} in sys.modules)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"DATABASE_URL", "TRIGGER_SECRET"}
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.main in a fresh interpreter failed\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout.strip().splitlines()[-1] == "False", (
        f"importing commerce_ops.main also imported {WORKER_MODULE}; the "
        "worker must be a separate process, not something the HTTP "
        "process carries"
    )
