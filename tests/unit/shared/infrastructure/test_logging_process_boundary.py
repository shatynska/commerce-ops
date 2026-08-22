"""Fresh-interpreter tests for `commerce_ops.shared.infrastructure.logging`.

Derived strictly from the `application-logging` capability's delta spec:
`openspec/changes/configure-application-logging/specs/application-logging/spec.md`.

`src/commerce_ops/shared/infrastructure/logging.py` does not exist yet
(tasks.md 1.1), and neither `main.py` nor `preflight.py` calls it yet
(tasks.md 3.1/3.2), so every test in this file is expected to fail --
either the subprocess exits non-zero on an import error, or a captured
stream lacks a marker that a call to `configure_logging()` would have
produced -- until the change lands. That failure establishes only that the
target is absent. See `test-manifest.md` at the change root.

WHY A FRESH INTERPRETER, PER TEST HERE (per the dispatch's explicit
constraint, matching the pattern `test_main_slack_wiring.py` and
`test_preflight.py` already use for process-global effects):

- The empty-environment and non-HTTP-entrypoint scenarios below share
  process-global/import-order sensitivity with the guards those two files
  already establish -- see `test_startup_without_configuration.py`'s own
  precedent for the same reasoning applied to `commerce_ops.main`.
- The `dictConfig` regression tests are the sharper reason. Design.md,
  Context fact 3: `logging.config.dictConfig`'s non-incremental path calls
  `_clearExistingHandlers()`, which runs `logging.shutdown()` over every
  handler currently registered in the process -- including whatever
  handlers pytest's own logging plugin has installed for the current test
  item -- and leaves `uvicorn`/`uvicorn.access` configured with
  `propagate: false` for the remainder of the session. Run in-process, this
  does not fail the test that triggers it; it corrupts a *different* test's
  captured output later in the same session, surfacing as an unrelated
  failure attributed to the wrong place. A subprocess contains the damage
  to a throwaway interpreter.

Confirmed empirically against the installed `uvicorn` (0.52.4, matching
design.md's own citation) before writing the assertions below: `dictConfig`
over `uvicorn.config.LOGGING_CONFIG` leaves `logging.getLogger().handlers`
untouched (root is not named in that config) and a `StreamHandler` already
attached to root continues to receive records afterward -- the mechanism
design.md's fact 3 describes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

# Env vars a complete configuration needs, transcribed from
# tests/unit/test_preflight.py's own `_complete_environment()` rather than
# imported from it -- that file's own precedent (see its module docstring)
# is that a process-boundary test must keep working even where the module it
# borrows the shape from cannot itself be imported, and a shared import
# would couple two files asserting different things.
_REQUIRED_NOT_STARTUP_CRITICAL = (
    "OPENAI_API_KEY",
    "OMNI_AGENT_SLACK_SIGNING_SECRET",
    "OMNI_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
    "TRIGGER_SECRET",
)
_VALID_DATABASE_URL = "postgresql+asyncpg://commerce_ops:pw@postgres:5432/commerce_ops"


def _complete_environment() -> dict[str, str]:
    env = {name: f"value-for-{name.lower()}" for name in _REQUIRED_NOT_STARTUP_CRITICAL}
    env["DATABASE_URL"] = _VALID_DATABASE_URL
    return env


def _run(
    script: str, environment: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        env={"PATH": os.environ.get("PATH", ""), **environment},
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


# --------------------------------------------------------------------------
# Requirement: Configuring Logging Requires No Configuration To Be Present
# --------------------------------------------------------------------------


def test_logging_is_configured_with_an_empty_environment(tmp_path: Path) -> None:
    """Scenario: Logging is configured with an empty environment.

    WHEN logging is configured with every environment variable absent
    THEN configuring SHALL succeed without raising, at the default
    threshold.

    Run with an environment built from scratch (only `PATH`) rather than a
    pruned copy of the developer's own environment, and from `tmp_path`, so
    nothing set on the machine or a stray `.env` can supply `LOG_LEVEL` (or
    anything else) and mask the empty-environment precondition.
    """
    script = (
        "from commerce_ops.shared.infrastructure.logging import configure_logging\n"
        "configure_logging()\n"
    )
    result = _run(script, {}, tmp_path)

    # Specified: succeeds without raising.
    assert result.returncode == 0, (
        f"configure_logging() must succeed with the environment empty.\n{_output(result)}"
    )


# --------------------------------------------------------------------------
# Requirement: Logging Is Configured From Every Entrypoint
# --------------------------------------------------------------------------


def test_a_non_http_entrypoint_emits_records(tmp_path: Path) -> None:
    """Scenario: A non-HTTP entrypoint emits records.

    WHEN the application starts through an entrypoint that does not run the
    HTTP server, and a record at or above the configured threshold is
    emitted after that entrypoint has run
    THEN that record SHALL reach the process's standard error stream.

    `commerce_ops.preflight` is the entrypoint that does not run the HTTP
    server (design.md, Context: "Entrypoints that exist today"). `check()`
    is called directly (not via `python -m commerce_ops.preflight`, which
    would exit the process before this script could emit its own probe
    record) with a complete, valid environment so the entrypoint's own
    fault-reporting behaviour -- a different capability's concern -- cannot
    interfere with what this scenario asserts. Without task 3.2's call
    inside `check()`, this is exactly the test that stays red after
    task 3.2 is reverted.
    """
    marker = f"probe-{uuid.uuid4().hex}"
    script = (
        "import logging\n"
        "from commerce_ops.preflight import check\n"
        "check()\n"
        f"logging.getLogger('commerce_ops.entrypoint_probe').info({marker!r})\n"
    )
    result = _run(script, _complete_environment(), tmp_path)

    assert result.returncode == 0, (
        f"the preflight entrypoint must run cleanly with a complete "
        f"environment.\n{_output(result)}"
    )
    # Specified.
    assert marker in result.stderr, (
        f"a record emitted after the non-HTTP entrypoint ran did not reach "
        f"stderr.\n{_output(result)}"
    )


# --------------------------------------------------------------------------
# Requirement: The Hosting Server's Own Logging Is Left Intact
# --------------------------------------------------------------------------

_DICTCONFIG_ORDER_A = """
import logging
import logging.config
import uvicorn.config

from commerce_ops.shared.infrastructure.logging import configure_logging

# Production order: the hosting server configures its own logging first,
# then the application configures its own (design.md, Risks/Trade-offs:
# "the production order under the uvicorn CLI is uvicorn-configures-then-
# app-imports").
logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
configure_logging()

logging.getLogger({app_logger_name!r}).info({app_marker!r})
logging.getLogger('uvicorn.access').info(
    '%s - "%s %s HTTP/%s" %d',
    '127.0.0.1:0', 'GET', {access_path!r}, '1.1', 200,
)
"""

_DICTCONFIG_ORDER_B = """
import logging
import logging.config
import uvicorn.config

from commerce_ops.shared.infrastructure.logging import configure_logging

# Reverse order: the application configures its own logging first, then the
# hosting server applies its own configuration afterward -- exactly the
# WHEN clause of "The application's records survive the server configuring
# its own logging".
configure_logging()
logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)

logging.getLogger({app_logger_name!r}).info({app_marker!r})
logging.getLogger('uvicorn.access').info(
    '%s - "%s %s HTTP/%s" %d',
    '127.0.0.1:0', 'GET', {access_path!r}, '1.1', 200,
)
"""


def _assert_dictconfig_regression(
    result: subprocess.CompletedProcess[str], app_marker: str, access_marker: str
) -> None:
    # Specified (Scenario: The application's records survive the server
    # configuring its own logging / A record at the configured threshold is
    # emitted): the application's record reaches stderr regardless of order.
    assert app_marker in result.stderr, (
        f"the application's record did not reach stderr.\n{_output(result)}"
    )
    # Specified (Scenario: Server request logs continue to be emitted
    # exactly once): the server's own record is emitted exactly once, on
    # its own (stdout) stream -- uvicorn's `access` handler writes to
    # stdout, not stderr (design.md, Context).
    assert result.stdout.count(access_marker) == 1, (
        "the hosting server's request record must be emitted exactly once "
        f"on stdout.\n{_output(result)}"
    )
    # Specified (same scenario, "left intact" / "not caused to be emitted
    # more than once"): the server's record must not additionally leak onto
    # the application's own stream.
    assert access_marker not in result.stderr, (
        f"the hosting server's request record leaked onto stderr.\n{_output(result)}"
    )


def test_uvicorn_dictconfig_then_configure_logging(tmp_path: Path) -> None:
    """Scenario: Server request logs continue to be emitted exactly once
    (production order) -- also exercises design.md fact 3 (Context: "A root
    handler attached before uvicorn starts survives uvicorn's `dictConfig`
    call"), since this order attaches nothing before `dictConfig` runs at
    all; `configure_logging()`'s own handler is installed only afterward,
    so this order additionally confirms attaching after leaves nothing to
    survive in the first place.

    WHEN the application's logging is configured and the hosting HTTP
    server emits a request record
    THEN that record SHALL be emitted exactly once.
    """
    app_logger_name = f"commerce_ops.dictconfig_probe_{uuid.uuid4().hex}"
    app_marker = f"app-probe-{uuid.uuid4().hex}"
    access_marker = f"/access-probe-{uuid.uuid4().hex}"
    script = _DICTCONFIG_ORDER_A.format(
        app_logger_name=app_logger_name,
        app_marker=app_marker,
        access_path=access_marker,
    )

    result = _run(script, {}, tmp_path)

    assert result.returncode == 0, f"the script raised.\n{_output(result)}"
    _assert_dictconfig_regression(result, app_marker, access_marker)


def test_configure_logging_then_uvicorn_dictconfig(tmp_path: Path) -> None:
    """Scenario: The application's records survive the server configuring
    its own logging (reverse order) -- also exercises Scenario: Server
    request logs continue to be emitted exactly once, in the order design.md
    fact 3 is specifically about: a handler already attached to root before
    `dictConfig` runs.

    WHEN the hosting HTTP server applies its own logging configuration after
    the application has configured logging
    THEN a subsequently emitted application record SHALL still reach the
    process's standard error stream.
    """
    app_logger_name = f"commerce_ops.dictconfig_probe_{uuid.uuid4().hex}"
    app_marker = f"app-probe-{uuid.uuid4().hex}"
    access_marker = f"/access-probe-{uuid.uuid4().hex}"
    script = _DICTCONFIG_ORDER_B.format(
        app_logger_name=app_logger_name,
        app_marker=app_marker,
        access_path=access_marker,
    )

    result = _run(script, {}, tmp_path)

    assert result.returncode == 0, f"the script raised.\n{_output(result)}"
    _assert_dictconfig_regression(result, app_marker, access_marker)
