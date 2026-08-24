"""Tests for the configuration preflight check.

Derived strictly from the `runtime-configuration` capability's delta spec:
`openspec/changes/revise-foundation-for-launch-mvp/specs/runtime-configuration/spec.md`

The preflight is the surface on which "the configuration is checked" is
observable: it produces the report (stderr) and the outcome (exit status)
that the delta spec's "Configuration Faults Are Detected And Reported
Together" and "Only A Startup-Critical Fault Prevents Startup" requirements
describe. It is exercised here exactly as the container invokes it -- as a
process, with a constructed environment -- because the exit status is half
of what those requirements state and is not observable any other way.

`src/commerce_ops/preflight.py` does not exist yet (tasks 5.1), so every
test here is expected to fail on an absent target until it lands. That
failure establishes only that the target is absent. See `test-manifest.md`
at the change root.

THE TRAP THESE TESTS EXIST TO PIN. `pydantic` raises rather than returning a
report, so a preflight that lets `ValidationError` escape exits non-zero on
*any* fault -- silently converting the capability-scoped degradation the
"Only A Startup-Critical Fault Prevents Startup" requirement mandates into a
full outage (design.md: "a missing `PRODUCT_AGENT_MONITORING_CHANNEL_ID`
would take `/health`, Slack and every cadence endpoint with it"). The exit
status is therefore asserted on both the startup-critical and the
non-critical path.

ASSUMED INTERFACE (unresolved project questions -- see test-manifest.md):

1. The preflight is invoked as `python -m commerce_ops.preflight`. tasks 5.2
   says only that it goes into the Dockerfile's `CMD` chain ahead of
   `alembic upgrade head`; the invocation form is not pinned anywhere.
2. The report names faulting variables and *only* faulting variables. The
   spec requires "report every faulting variable by name"; it does not say
   the report must be silent about non-faulting ones, but the
   optional-absence and capability-scoped scenarios both turn on
   distinguishing "named as faulting" from "not named", which an inventory
   listing every declared variable would destroy.
   `test_a_complete_configuration_reports_no_fault` pins this contract once
   so the "not named" assertions elsewhere in this file are meaningful.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

# The declared set, transcribed from tasks.md 4.1. Deliberately duplicated
# from tests/unit/shared/application/test_settings.py rather than imported
# from it: this module must be able to run as a process-level check even
# where the settings module itself cannot be imported, and a shared import
# would couple two files that assert different things.
STARTUP_CRITICAL_ENV_VAR = "DATABASE_URL"

REQUIRED_NOT_STARTUP_CRITICAL = (
    "OPENAI_API_KEY",
    "OMNI_AGENT_SLACK_SIGNING_SECRET",
    "OMNI_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
    # Moved here from OPTIONAL_ENV_VARS by start-launch-from-slack
    # (tasks 1.1), the launch-entry surface being its first consumer.
    "PRODUCT_AGENT_SLACK_SIGNING_SECRET",
)

OPTIONAL_ENV_VARS = (
    "CLICKUP_API_TOKEN",
    # Added by configure-application-logging (tasks 2.5) -- this
    # transcribed set now spans more than one change.
    "LOG_LEVEL",
)

ALL_DECLARED = (
    STARTUP_CRITICAL_ENV_VAR,
    *REQUIRED_NOT_STARTUP_CRITICAL,
    *OPTIONAL_ENV_VARS,
)

VALID_DATABASE_URL = "postgresql+asyncpg://commerce_ops:pw@postgres:5432/commerce_ops"

# design.md, "`DATABASE_URL` is typed": the application connects with
# `postgresql+asyncpg`; a value carrying a scheme SQLAlchemy's async engine
# cannot use is what "unparseable as its declared type" refers to.
UNPARSEABLE_DATABASE_URL = "mysql://commerce_ops:pw@mysql:3306/commerce_ops"


def _complete_environment() -> dict[str, str]:
    """Every required variable set to a usable value; optionals absent.

    Optionals are left absent deliberately -- design.md records both as
    registered `production` secrets that the deploy does not yet render, so
    this is the configuration the first deploy after this change actually
    delivers.
    """
    env = {name: f"value-for-{name.lower()}" for name in REQUIRED_NOT_STARTUP_CRITICAL}
    env[STARTUP_CRITICAL_ENV_VAR] = VALID_DATABASE_URL
    return env


def _run_preflight(
    environment: Mapping[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Runs the preflight as a process with `environment` and nothing else.

    The environment is built from scratch rather than by copying and pruning
    `os.environ`, so a `DATABASE_URL` (or any other declared variable) that
    happens to be set on the developer's machine cannot leak in and make an
    absence test assert nothing. `cwd` is a tmp directory so that no
    repository-local environment file is in scope unless a test puts one
    there.
    """
    return subprocess.run(
        [sys.executable, "-m", "commerce_ops.preflight"],
        env={"PATH": os.environ.get("PATH", ""), **environment},
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def _assert_reported(result: subprocess.CompletedProcess[str], *variables: str) -> None:
    """Asserts each variable is named in the report on stderr (tasks 5.1)."""
    for variable in variables:
        assert variable in result.stderr, (
            f"{variable} is faulting but the report does not name it.\n"
            f"{_output(result)}"
        )


def _assert_not_reported(
    result: subprocess.CompletedProcess[str], *variables: str
) -> None:
    """Asserts each variable appears nowhere in the preflight's output."""
    combined = result.stdout + result.stderr
    for variable in variables:
        assert variable not in combined, (
            f"{variable} is not faulting but the report names it.\n{_output(result)}"
        )


# --------------------------------------------------------------------------
# Baseline: a complete configuration. Not itself a `runtime-configuration`
# scenario -- it is what makes the "not reported" assertions below readable
# (see ASSUMED INTERFACE 2 in the module docstring), and it is the state
# design.md's Migration Plan expects of the first deploy after this change:
# "should start cleanly and report nothing".
# --------------------------------------------------------------------------


def test_a_complete_configuration_reports_no_fault(tmp_path: Path) -> None:
    """DERIVED (design.md, Migration Plan) plus the report contract this file
    assumes: with nothing faulting, the preflight exits zero and names no
    declared variable at all.
    """
    result = _run_preflight(_complete_environment(), tmp_path)

    assert result.returncode == 0, (
        f"a complete configuration must not fail the check.\n{_output(result)}"
    )
    _assert_not_reported(result, *ALL_DECLARED)


# --------------------------------------------------------------------------
# Requirement: Configuration Faults Are Detected And Reported Together
# --------------------------------------------------------------------------


def test_every_absent_required_variable_is_named_not_only_the_first(
    tmp_path: Path,
) -> None:
    """Scenario: Several required variables are faulty at once.

    WHEN the configuration is checked and more than one required variable is
    absent
    THEN the report SHALL name every absent variable, not only one of them.

    Three are removed rather than two, so that a report which stopped at the
    first, or at the first two, both fail. The variables removed are all
    non-startup-critical, so the process' exit status is not what is under
    test here -- only the report's completeness is.
    """
    absent = (
        "OMNI_AGENT_SLACK_BOT_TOKEN",
        "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
        # Substituted for TRIGGER_SECRET when replace-cron-with-job-runner
        # removed that variable. Striking it would have quietly reduced this
        # case to two absent variables and weakened the guard the docstring
        # above describes; the count is the point, so another required,
        # non-startup-critical variable takes its place.
        "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    )
    environment = {
        name: value
        for name, value in _complete_environment().items()
        if name not in absent
    }

    result = _run_preflight(environment, tmp_path)

    # Specified: every absent variable is named, not only one.
    _assert_reported(result, *absent)


def test_a_value_that_cannot_be_parsed_as_its_type_is_reported(
    tmp_path: Path,
) -> None:
    """Scenario: A variable cannot be parsed as its declared type.

    WHEN the configuration is checked and a variable's value cannot be parsed
    as the type it is declared with -- such as a database URL whose scheme is
    not one the application can connect with
    THEN that variable SHALL be reported as faulting.

    The scenario names a database URL's scheme as its own example, and
    `DATABASE_URL` is the one declared variable carrying a type at all
    (tasks 4.2a); every other declared variable is an opaque credential or
    id for which presence is all that is meaningful.
    """
    environment = _complete_environment()
    environment[STARTUP_CRITICAL_ENV_VAR] = UNPARSEABLE_DATABASE_URL

    result = _run_preflight(environment, tmp_path)

    # Specified: reported as faulting.
    _assert_reported(result, STARTUP_CRITICAL_ENV_VAR)


def test_a_present_but_empty_required_variable_is_reported(tmp_path: Path) -> None:
    """Scenario: A variable is present but empty.

    WHEN the configuration is checked and a declared non-optional variable is
    present but its value is empty
    THEN that variable SHALL be reported as faulting, the same as if it were
    absent.

    Exercised on a non-startup-critical variable so that "reported as
    faulting" is asserted independently of any effect on the exit status;
    the startup-critical empty case is asserted by
    `test_a_faulty_startup_critical_variable_fails_the_check` below.
    """
    environment = _complete_environment()
    environment["PRODUCT_AGENT_SLACK_BOT_TOKEN"] = ""

    result = _run_preflight(environment, tmp_path)

    # Specified: an empty value faults the same as an absent one.
    _assert_reported(result, "PRODUCT_AGENT_SLACK_BOT_TOKEN")


def test_absent_optional_variable_is_not_reported_as_faulting(
    tmp_path: Path,
) -> None:
    """Scenario: An optional variable's absence is not a fault.

    WHEN the configuration is checked and a variable declared optional is
    absent
    THEN it SHALL NOT be reported as faulting [...]

    The second half of this scenario -- "the value SHALL be reported as
    absent to any caller that asks for it" -- is covered at the declaration
    level by
    `tests/unit/shared/application/test_settings.py::test_absent_optional_variable_is_reported_as_absent_to_a_caller`.

    Both optional variables are absent from `_complete_environment()`, which
    is the state design.md records as today's deployment reality.
    """
    result = _run_preflight(_complete_environment(), tmp_path)

    # Specified: not reported as faulting.
    _assert_not_reported(result, *OPTIONAL_ENV_VARS)
    # Specified, by implication of "not a fault": an absent optional cannot
    # be what fails the check.
    assert result.returncode == 0, (
        "an absent optional variable must not fail the configuration check.\n"
        f"{_output(result)}"
    )


def test_unrecognized_keys_in_the_process_environment_are_not_faults(
    tmp_path: Path,
) -> None:
    """Scenario: An unrecognized variable in the environment is not a fault.

    WHEN the configuration is checked and the environment or environment file
    carries a variable the definition does not declare
    THEN it SHALL be ignored rather than reported as a fault, since the
    deployment delivers variables the application does not consume.

    The `environment` half. `POSTGRES_PASSWORD` and `IMAGE_TAG` are the two
    real cases (tasks 4.2): the deploy renders both and the model declares
    neither.
    """
    environment = _complete_environment()
    environment["IMAGE_TAG"] = "sha-deadbeef"
    environment["POSTGRES_PASSWORD"] = "not-a-model-field"
    environment["SOME_UNRELATED_VARIABLE"] = "ignored"

    result = _run_preflight(environment, tmp_path)

    # Specified: ignored, not reported as a fault.
    assert result.returncode == 0, (
        "an undeclared variable in the environment must be ignored, not "
        f"treated as a fault.\n{_output(result)}"
    )
    _assert_not_reported(result, *ALL_DECLARED)


def test_unrecognized_keys_in_a_dotenv_file_are_not_faults(tmp_path: Path) -> None:
    """Scenario: An unrecognized variable in the environment is not a fault.

    The *environment file* half, and the whole of tasks 8.8: `extra="ignore"`
    is verifiable only at unit level over a dotenv fixture, because the image
    copies no `.env` and Compose mounts none, so a container never sees a
    dotenv file at all and the precondition cannot be created above this
    level.

    The fixture is a developer's copy of the rendered `.env`: every required
    variable, plus `IMAGE_TAG` and `POSTGRES_PASSWORD`, neither of which is a
    model field. Under pydantic-settings' strict default both would be
    reported as phantom faults (tasks 4.2, design.md Trade-offs).
    """
    lines = [f"{name}={value}" for name, value in _complete_environment().items()]
    lines.append("IMAGE_TAG=sha-deadbeef")
    lines.append("POSTGRES_PASSWORD=rendered-by-the-deploy")
    (tmp_path / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Nothing in the process environment: everything comes from the file, so
    # a preflight that did not read it would report every required variable
    # absent and this test would fail loudly rather than vacuously pass.
    result = _run_preflight({}, tmp_path)

    # Specified: the undeclared keys are ignored, not faults.
    assert result.returncode == 0, (
        "a dotenv file carrying IMAGE_TAG and POSTGRES_PASSWORD must not "
        f"produce faults for them.\n{_output(result)}"
    )
    _assert_not_reported(result, *ALL_DECLARED)


# --------------------------------------------------------------------------
# Requirement: Only A Startup-Critical Fault Prevents Startup
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fault", "value"),
    [
        ("absent", None),
        ("empty", ""),
        ("unparseable", UNPARSEABLE_DATABASE_URL),
    ],
)
def test_a_faulty_startup_critical_variable_fails_the_check(
    fault: str, value: str | None, tmp_path: Path
) -> None:
    """Scenario: A startup-critical variable is faulty.

    WHEN the configuration is checked and a variable marked startup-critical
    is absent, empty, or unparseable
    THEN the check SHALL fail.

    All three forms the WHEN clause names are exercised; `DATABASE_URL` is
    the only startup-critical variable (tasks 4.1).
    """
    environment = _complete_environment()
    if value is None:
        del environment[STARTUP_CRITICAL_ENV_VAR]
    else:
        environment[STARTUP_CRITICAL_ENV_VAR] = value

    result = _run_preflight(environment, tmp_path)

    # Specified: the check fails.
    assert result.returncode != 0, (
        f"a {fault} startup-critical {STARTUP_CRITICAL_ENV_VAR} must fail the "
        f"check.\n{_output(result)}"
    )
    # Specified (tasks 5.1, and deploy-pipeline's "reporting every faulting
    # variable"): the failure names what faulted.
    _assert_reported(result, STARTUP_CRITICAL_ENV_VAR)


@pytest.mark.parametrize(
    ("fault", "value"),
    [
        ("absent", None),
        ("empty", ""),
    ],
)
def test_a_faulty_capability_scoped_variable_is_reported_without_failing(
    fault: str, value: str | None, tmp_path: Path
) -> None:
    """Scenario: A capability-scoped variable is faulty.

    WHEN the configuration is checked and a required variable that is not
    marked startup-critical is absent, empty, or unparseable
    THEN the check SHALL report it as faulting
    AND the check SHALL NOT fail on account of it.

    This is the trap the module docstring names: pydantic raises rather than
    returning a report, so a preflight that lets `ValidationError` escape
    exits non-zero here and turns a one-capability misconfiguration into a
    full outage.

    The WHEN clause's third form, "unparseable", is NOT exercised and is
    recorded as deliberately untested: every declared variable other than
    `DATABASE_URL` is an opaque credential or id carrying no type that a
    value could fail to parse as (design.md, "`DATABASE_URL` is typed"), so
    the form has no referent among capability-scoped variables.
    """
    faulty = "PRODUCT_AGENT_MONITORING_CHANNEL_ID"
    environment = _complete_environment()
    if value is None:
        del environment[faulty]
    else:
        environment[faulty] = value

    result = _run_preflight(environment, tmp_path)

    # Specified: reported as faulting.
    _assert_reported(result, faulty)
    # Specified: the check does NOT fail on account of it.
    assert result.returncode == 0, (
        f"a {fault} capability-scoped {faulty} must be reported without "
        "failing the check -- a fault scoped to one capability must degrade "
        f"that capability, not the whole application.\n{_output(result)}"
    )


def test_a_capability_scoped_fault_does_not_suppress_the_startup_critical_one(
    tmp_path: Path,
) -> None:
    """DERIVED, not itself a scenario.

    Covers the interaction the two requirements leave implicit: with faults
    of both kinds present at once, the check must both fail (the
    startup-critical one decides the outcome) and name both (the
    report-together requirement decides the report). A preflight that
    short-circuits on the first fault it finds passes each requirement's own
    scenario in isolation and fails here.
    """
    faulty_capability_scoped = "PRODUCT_AGENT_SLACK_BOT_TOKEN"
    environment = _complete_environment()
    del environment[STARTUP_CRITICAL_ENV_VAR]
    del environment[faulty_capability_scoped]

    result = _run_preflight(environment, tmp_path)

    assert result.returncode != 0, (
        f"a faulty startup-critical variable must fail the check even when a "
        f"capability-scoped variable is faulty too.\n{_output(result)}"
    )
    _assert_reported(result, STARTUP_CRITICAL_ENV_VAR, faulty_capability_scoped)


# --------------------------------------------------------------------------
# Requirement: Checking Configuration Performs No Network Or Database Access
# --------------------------------------------------------------------------


# The preflight is imported BEFORE the socket blockers are installed, and
# only its `check()` runs under them.
#
# Installing them first does not work, and not for a reason that says
# anything about the implementation: `socket.socket` is a class, and
# `ssl.py` does `class SSLSocket(socket):` at module scope. Rebinding it to
# a function makes that class statement raise `TypeError` the first time
# anything imports `ssl` -- which `pydantic_settings` does transitively, via
# `asyncio`. Every correct implementation of this change imports
# `pydantic_settings` (tasks 4.1), so blocking first fails regardless of
# what the preflight does, and the test would assert nothing.
#
# Importing is not network access, so nothing this scenario cares about is
# lost: `check()` still runs with socket creation and name resolution
# raising, so a check that contacted Slack or the database fails loudly.
_NO_NETWORK_BOOTSTRAP = """
import socket
import sys

from commerce_ops.preflight import check


def _blocked(*args, **kwargs):
    raise AssertionError(
        "the configuration check attempted network access; it must read only "
        "the process environment and, where present, a local environment file"
    )


socket.socket = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

sys.exit(check())
"""


def test_preflight_completes_with_no_network_available(tmp_path: Path) -> None:
    """Scenario: Configuration is checked with no external service reachable.

    WHEN the configuration is checked in an environment where no external
    service is reachable
    THEN the check SHALL complete on the strength of the environment alone,
    and its outcome SHALL depend only on the declared variables' presence and
    parseability.

    "No external service reachable" is created by making socket creation and
    name resolution raise inside the preflight's own process -- stricter than
    unreachability, so a check that contacted Slack or the database fails
    loudly here rather than merely timing out. `DATABASE_URL` points at the
    Compose hostname `postgres`, which does not resolve here either.

    The declaration-level counterpart is
    `tests/unit/shared/application/test_settings.py::test_reading_configuration_opens_no_socket`.
    """
    result = subprocess.run(
        [sys.executable, "-c", _NO_NETWORK_BOOTSTRAP],
        env={"PATH": os.environ.get("PATH", ""), **_complete_environment()},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Specified: the check completes, and its outcome depends only on the
    # declared variables -- which are all present and parseable here, so it
    # succeeds.
    assert result.returncode == 0, (
        "the configuration check did not complete with no network "
        f"available.\n{_output(result)}"
    )
    _assert_not_reported(result, *ALL_DECLARED)
