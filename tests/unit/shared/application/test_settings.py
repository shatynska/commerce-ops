"""Tests for the single runtime-configuration declaration.

Derived strictly from the `runtime-configuration` capability's delta spec:
`openspec/changes/revise-foundation-for-launch-mvp/specs/runtime-configuration/spec.md`

Every requirement in that spec is `ADDED` (this is a new capability), so
these tests are written from the scenarios alone, never against an
implementation -- none exists at the time of writing. `pydantic-settings`
is not yet a declared dependency (tasks.md 3.1) and
`commerce_ops.shared.application.settings` does not yet exist (tasks.md
4.1), so this module is expected to fail collection with
`ModuleNotFoundError` until that lands. That failure establishes only that
the target is absent -- nothing about whether the assertions below are
correct. See `test-manifest.md` at the change root for the full accounting,
including the interface names this file assumes and why.

ASSUMED INTERFACE (unresolved project question -- see test-manifest.md).
Neither the delta spec, design.md nor tasks.md pins the names below; they
are this file's assumption, and the implementation must either adopt them
or the manifest entry must be revisited:

- `Settings`                    -- the pydantic-settings model (tasks 4.1)
- `get_settings()`              -- the cached accessor (tasks 4.3)
- `STARTUP_CRITICAL_ENV_VARS`   -- the startup-critical marking (tasks 4.1)
- `ENV_VAR_EXEMPTIONS`          -- the exemption table (tasks 6.1), asserted
                                   in `test_settings_env_drift.py`
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from commerce_ops.shared.application.settings import (
    STARTUP_CRITICAL_ENV_VARS,
    Settings,
    get_settings,
)

# --------------------------------------------------------------------------
# The declared set, transcribed from tasks.md 4.1. `tasks.md` is a planning
# artifact of this change, so these are SPECIFIED values for the purposes of
# the delta spec's first requirement ("Every Variable The Runtime Requires Is
# Declared In One Place"), which itself names no variables.
# --------------------------------------------------------------------------

STARTUP_CRITICAL_AND_REQUIRED = frozenset({"DATABASE_URL"})

REQUIRED_NOT_STARTUP_CRITICAL = frozenset(
    {
        "OPENAI_API_KEY",
        "OMNI_AGENT_SLACK_SIGNING_SECRET",
        "OMNI_AGENT_SLACK_BOT_TOKEN",
        "PRODUCT_AGENT_SLACK_BOT_TOKEN",
        "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
    }
)

OPTIONAL = frozenset(
    {
        "PRODUCT_AGENT_SLACK_SIGNING_SECRET",
        "CLICKUP_API_TOKEN",
        # Added by configure-application-logging (tasks 2.4) -- this
        # transcribed set now spans more than one change.
        "LOG_LEVEL",
        # Added by add-clickup-completion-loop (tasks 2.1). Optional for the
        # same reason CLICKUP_API_TOKEN is: absent, the launch completion
        # loop degrades -- the webhook rejects every delivery, the pass fails
        # its own run -- while the application starts and serves unchanged.
        "CLICKUP_LAUNCH_FOLDER_ID",
        "CLICKUP_WEBHOOK_SECRET",
    }
)

REQUIRED = STARTUP_CRITICAL_AND_REQUIRED | REQUIRED_NOT_STARTUP_CRITICAL

ALL_DECLARED = REQUIRED | OPTIONAL

# tasks.md 4.1: deliberately NOT declared -- consumed by docker-compose.yml's
# own substitution and by the `postgres` service, never by the application
# process. The delta spec's first requirement excludes it in as many words
# ("A variable consumed only by the deployment's own machinery ... is outside
# this declaration").
DEPLOYMENT_ONLY_NOT_DECLARED = frozenset({"POSTGRES_PASSWORD"})

# A value whose scheme the application can connect with (design.md,
# "`DATABASE_URL` is typed, not merely present-checked").
VALID_DATABASE_URL = "postgresql+asyncpg://commerce_ops:pw@postgres:5432/commerce_ops"


# --------------------------------------------------------------------------
# Helpers: address the declaration by environment-variable name rather than
# by Python attribute name, so these tests do not silently pin a field-naming
# convention the artifacts never state. pydantic-settings' default is to
# match a field case-insensitively against the environment, so a field's
# environment name is its validation alias where it has one, and its
# upper-cased field name otherwise.
# --------------------------------------------------------------------------


def _env_name(field_name: str, field: Any) -> str:
    alias = (
        field.validation_alias if field.validation_alias is not None else field.alias
    )
    if alias is None:
        return field_name.upper()
    if isinstance(alias, str):
        return alias.upper()
    pytest.fail(
        f"field {field_name!r} declares a non-string validation alias ({alias!r}); "
        "this test resolves a declaration by environment-variable name and "
        "cannot interpret alias choices -- see test-manifest.md"
    )


def _declared_fields() -> dict[str, Any]:
    """Maps environment-variable name -> pydantic FieldInfo."""
    return {
        _env_name(name, field): field for name, field in Settings.model_fields.items()
    }


def _complete_environment() -> dict[str, str]:
    env = {name: f"value-for-{name.lower()}" for name in REQUIRED}
    env["DATABASE_URL"] = VALID_DATABASE_URL
    return env


def _value_for(settings: Settings, env_var: str) -> Any:
    """Reads the declared value by environment-variable name."""
    for field_name, field in Settings.model_fields.items():
        if _env_name(field_name, field) == env_var:
            return getattr(settings, field_name)
    pytest.fail(f"{env_var} is not declared by Settings")


@pytest.fixture()
def empty_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removes every declared variable, plus POSTGRES_PASSWORD, from the env."""
    for var in ALL_DECLARED | DEPLOYMENT_ONLY_NOT_DECLARED:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _uncached_settings() -> Any:
    """`get_settings` is cached (tasks 4.3); clear it around every test.

    Without this, a value read in one test leaks into the next, which would
    make the environment manipulation below assert nothing.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# Requirement: Every Variable The Runtime Requires Is Declared In One Place
# --------------------------------------------------------------------------


def test_every_required_runtime_variable_is_declared_in_one_definition() -> None:
    """Scenario: Every declared variable is discoverable from one definition.

    WHEN the set of environment variables the application's runtime requires
    is inspected
    THEN every such variable SHALL be declared in the single definition, with
    its type, whether it is required or optional, and whether it is
    startup-critical.

    The four assertions below are the four things the scenario's THEN names:
    the set itself, then type, then required/optional, then startup-critical
    (the latter three each get their own test below, so this one asserts the
    set and points at them).
    """
    # Specified (via tasks.md 4.1's transcription of the declared set).
    assert set(_declared_fields()) == set(ALL_DECLARED)


def test_deployment_only_variables_are_not_declared() -> None:
    """Same scenario, negative half.

    The requirement's prose excludes "a variable consumed only by the
    deployment's own machinery, and never by the application process". This
    pins `POSTGRES_PASSWORD` as outside the declaration, which tasks.md 4.1
    states in as many words, so that a later well-meaning addition of it is
    caught rather than accepted.
    """
    # Specified.
    assert set(_declared_fields()).isdisjoint(DEPLOYMENT_ONLY_NOT_DECLARED)


def test_every_declaration_carries_a_type() -> None:
    """Same scenario: "... with its type".

    Asserted as "the field carries an annotation" -- the only mechanically
    checkable reading of "carries its type" for the opaque credentials and
    ids. That `DATABASE_URL`'s type actually discriminates a value it cannot
    connect with is asserted separately, by the unparseable-value scenario in
    `tests/unit/test_preflight.py` (tasks 4.2a).
    """
    for env_var, field in _declared_fields().items():
        # Specified.
        assert field.annotation is not None, f"{env_var} is declared without a type"


def test_each_declaration_records_whether_it_is_required_or_optional() -> None:
    """Same scenario: "... whether it is required or optional".

    Required is asserted as "the field has no default", which is what makes
    absence a fault; optional as "the field has a default", which is what
    makes absence not a fault (see the optional-absence scenario below).
    """
    declared = _declared_fields()

    actually_required = {
        env_var for env_var, field in declared.items() if field.is_required()
    }

    # Specified (via tasks.md 4.1).
    assert actually_required == set(REQUIRED)
    assert set(declared) - actually_required == set(OPTIONAL)


def test_startup_critical_is_a_marking_on_top_of_required() -> None:
    """Same scenario: "... and whether it is startup-critical".

    tasks.md 4.1: "Startup-critical is a marking **on top of** required, not
    a third peer status -- `DATABASE_URL` is both." So the marked set is
    exactly {DATABASE_URL} and is a subset of the required set.
    """
    # Specified (via tasks.md 4.1).
    assert set(STARTUP_CRITICAL_ENV_VARS) == set(STARTUP_CRITICAL_AND_REQUIRED)
    # Specified: the marking sits on top of required, so it cannot name a
    # variable that is optional or undeclared.
    assert set(STARTUP_CRITICAL_ENV_VARS) <= set(REQUIRED)


# --------------------------------------------------------------------------
# Requirement: Configuration Faults Are Detected And Reported Together
# (the caller-facing half; the reporting half lives in test_preflight.py)
# --------------------------------------------------------------------------


def test_absent_optional_variable_is_reported_as_absent_to_a_caller(
    empty_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An optional variable's absence is not a fault.

    WHEN the configuration is checked and a variable declared optional is
    absent
    THEN it SHALL NOT be reported as faulting, and the value SHALL be
    reported as absent to any caller that asks for it.

    This test covers the second half -- the value reaching a caller as
    absent. The first half (not reported as faulting) is covered by
    `tests/unit/test_preflight.py::test_absent_optional_variable_is_not_reported_as_faulting`.
    """
    for name, value in _complete_environment().items():
        monkeypatch.setenv(name, value)

    settings = get_settings()

    for optional_var in sorted(OPTIONAL):
        # Specified: reported as absent. DERIVED: "absent" is read as `None`,
        # Python's ordinary encoding of an absent optional value -- the spec
        # pins no sentinel. Recorded in test-manifest.md.
        assert _value_for(settings, optional_var) is None, (
            f"{optional_var} is declared optional and is absent from the "
            "environment, so a caller must see it as absent"
        )


def test_an_unrecognized_variable_in_the_environment_is_not_a_fault(
    empty_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An unrecognized variable in the environment is not a fault.

    WHEN the configuration is checked and the environment or environment
    file carries a variable the definition does not declare
    THEN it SHALL be ignored rather than reported as a fault.

    Exercised here over the *process environment*; the *environment file*
    half is exercised at this same unit level by
    `tests/unit/test_preflight.py::test_unrecognized_keys_in_a_dotenv_file_are_not_faults`
    (tasks 8.8 -- a container never sees a dotenv file, so the precondition
    cannot be created above unit level).
    """
    for name, value in _complete_environment().items():
        monkeypatch.setenv(name, value)
    # The two keys a developer holding a copy of the rendered `.env` would
    # have that are not model fields (tasks 4.2), plus one arbitrary key.
    monkeypatch.setenv("IMAGE_TAG", "sha-deadbeef")
    monkeypatch.setenv("POSTGRES_PASSWORD", "not-a-model-field")
    monkeypatch.setenv("SOME_UNRELATED_VARIABLE", "ignored")

    # Specified: constructing the declaration must not raise on account of a
    # key it does not declare.
    settings = get_settings()

    assert _value_for(settings, "DATABASE_URL") is not None


# --------------------------------------------------------------------------
# Requirement: Checking Configuration Performs No Network Or Database Access
# --------------------------------------------------------------------------


def test_reading_configuration_opens_no_socket(
    empty_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Configuration is checked with no external service reachable.

    WHEN the configuration is checked in an environment where no external
    service is reachable
    THEN the check SHALL complete on the strength of the environment alone,
    and its outcome SHALL depend only on the declared variables' presence
    and parseability.

    "No external service reachable" is created by making socket creation and
    name resolution raise, which is stricter than unreachability: any attempt
    to contact Slack, the database or anything else fails loudly here instead
    of merely timing out. `DATABASE_URL` names a host that does not resolve
    from the test environment, so a check that connected would fail even
    without the guard.

    The whole-preflight counterpart is
    `tests/unit/test_preflight.py::test_preflight_completes_with_no_network_available`.
    """
    for name, value in _complete_environment().items():
        monkeypatch.setenv(name, value)

    def _no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "reading the configuration attempted network access; the "
            "requirement is that it reads only the process environment and "
            "an optional local environment file"
        )

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket, "getaddrinfo", _no_network)

    settings = get_settings()

    # Specified: the outcome depends only on the declared variables.
    assert _value_for(settings, "DATABASE_URL") is not None


# --------------------------------------------------------------------------
# Requirement: Importing And Starting The Application Do Not Require
# Configuration To Be Present (the settings module's own half; the
# application-wide half lives in test_startup_without_configuration.py)
# --------------------------------------------------------------------------


def test_importing_the_settings_module_with_an_empty_environment_succeeds(
    tmp_path: Path,
) -> None:
    """Scenario: Application imports with an empty environment.

    WHEN the application's modules are imported with every declared variable
    absent from the environment
    THEN the import SHALL succeed without raising.

    Narrowed here to the settings module itself, because it is the one module
    whose whole subject is configuration and therefore the one most likely to
    read it at import time -- which the requirement's second sentence forbids
    ("Configuration SHALL be read no earlier than the point at which it is
    checked or first used", tasks 4.3).

    Run in a fresh interpreter on purpose: the module is already imported in
    this pytest process (see the module-level import above), so an in-process
    import would be a cache hit and would assert nothing about import-time
    behaviour. Run from `tmp_path` so no repository-local `.env` is in scope.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import commerce_ops.shared.application.settings"],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Specified.
    assert result.returncode == 0, (
        "importing the settings module with an empty environment failed; the "
        "model must be constructed by the cached accessor on first call, "
        "never at import time.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# --------------------------------------------------------------------------
# Supplementary -- not itself a `#### Scenario:` block. Traces to tasks.md
# 4.3 and 4.4, which the delta spec does not restate. Recorded as DERIVED in
# test-manifest.md.
# --------------------------------------------------------------------------


def test_accessor_is_cached_across_calls(
    empty_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DERIVED (tasks 4.3): "a cached accessor"."""
    for name, value in _complete_environment().items():
        monkeypatch.setenv(name, value)

    assert get_settings() is get_settings()


def test_model_and_accessor_are_exported_from_the_layer_public_surface() -> None:
    """DERIVED (tasks 4.4): exported from `shared/application/__init__.py`'s
    `__all__`, which AGENTS.md names as a module's only public surface.
    """
    from commerce_ops.shared import application

    assert "Settings" in application.__all__
    assert "get_settings" in application.__all__
    assert application.Settings is Settings
    assert application.get_settings is get_settings
