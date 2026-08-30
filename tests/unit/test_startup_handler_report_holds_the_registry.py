"""The startup handler report reads the registry this deployment holds.

Derived strictly from the delta spec of the OpenSpec change
`let-the-handler-report-see-handlers`:
`openspec/changes/let-the-handler-report-see-handlers/specs/launch-playbook/spec.md`

Covers three of the four scenarios that change adds to the MODIFIED
requirement *A step carries the brief and the handler its automation
needs*:

- A registered handler draws no fault at startup
- An unregistered handler is named at startup
- The faults the report names do not stop the deployment

The fourth, *The reporting process holds the deployment's own
registrations*, lives in `tests/unit/test_registrations_across_processes.py`
where `tasks.md` 1.3 places it: it asserts the reporting process shares a
registry with the two composition roots, which is that file's subject.
The three here are about what the report then says.

and the normative paragraph they hang from:

> That startup report SHALL be produced by a process in which every
> handler this deployment answers for is registered. A report produced
> against a registry holding none of them SHALL NOT satisfy this
> requirement: such a report answers identically for a deployment that
> registers a step's handler and one that does not, and so establishes
> nothing about either.

See `test-manifest.md` at that change's root for the full accounting.

## Level, and why a fresh interpreter is the only level that works

Every **WHEN** here says the process is "started the way the deployment
starts it". That is a statement about where the registry came from, not
about what a supplied registry produces, and it is the whole point of the
scenarios: two tests already exercise the startup clause in-process
(`tests/unit/launch/application/test_step_activation.py:636` and
`tests/unit/test_check_step_handlers_reads_the_authored_set.py:329`) and
both hand the registry in, so both pass against a process that registers
nothing.

An in-process test here would be worse than useless. `HANDLERS` is a
module global and several files under `tests/unit` import
`commerce_ops.registrations` at module scope, so pytest collection alone
populates the registry for the whole run -- verified while writing this
file: the registry is empty after importing
`commerce_ops.check_step_handlers` alone, and holds
`listing.subcategory_advisor` after importing `commerce_ops.registrations`.
A test run as a single file would therefore be red and the same test run
in the full tree green, whatever `check_step_handlers.py` does. So each
test below drives a fresh interpreter, following the subprocess pattern
`tests/unit/test_registrations_across_processes.py` establishes
(`_handler_names`, `:263`), transcribed here rather than imported for the
same reason that file transcribes its own environment list: this file's
subject is the reporting process, not that file's.

The step set is substituted inside the driver script, so no database is
needed. Only the *read* is substituted -- never the registry, which is
whatever importing the reporting module left behind.

## What is fixed, and what is INVENTED

Fixed by the delta: that a startup report exists, that it names `active`
`automated` steps whose handler is unregistered, that it does not stop the
deployment, and that the process making it holds this deployment's
registrations.

Fixed by the repository, and read from it rather than assumed:
`commerce_ops.check_step_handlers` is the reporting process
(`Dockerfile:86`); its `main` entry point, its `PlaybookRepository`,
`session`, `HANDLERS` and `report_unregistered_handlers` attributes, and
the `(records, version)` shape its read returns, are all transcribed from
`tests/unit/test_check_step_handlers_reads_the_authored_set.py`, which
substitutes exactly the same collaborators and passes today.

INVENTED, each recorded in the manifest:

- The driver script's own shape, and the `COMMERCE_OPS_TEST_STEP_SET`
  variable it reads its step set from. That name is deliberately not an
  application variable: nothing in `shared/application/settings.py`
  declares it and nothing in `src/` reads it.
- Wrapping `report_unregistered_handlers` to record what it returned. The
  real function still runs, against whatever registry the module itself
  passes it -- the wrapper observes the report, it does not supply the
  registry. Capturing the `ERROR` log lines instead was considered and
  rejected: it would pin the report's wording, which no scenario states.
- Which handler name stands for "a handler this deployment's code
  registers". Read at run time from a fresh interpreter that imports
  `commerce_ops.registrations`, rather than hard-coded, so that adding or
  renaming a handler cannot silently turn these tests green.

Deliberately **not** asserted: that registration happens by importing
`commerce_ops.registrations`. design.md is explicit that the added text
"deliberately does not say *how* registration happens", so whether that
module reached `sys.modules` is recorded in the failure message as a
diagnostic and asserted nowhere.

## Expected first-run state

Written before the change was implemented, against a tree where
`check_step_handlers` imports no handler module. Expected on that tree:

- `test_a_registered_handler_draws_no_fault_at_startup` -- RED: with an
  empty registry every `active` `automated` step is reported unresolvable,
  including the one this deployment registers.
- `test_an_unregistered_handler_is_named_at_startup` -- RED on its second
  assertion only: the step is named (an empty registry names everything),
  but so is the step whose handler is registered, which is the
  answers-identically failure the new paragraph forbids.
- `test_the_faults_the_report_names_do_not_stop_the_deployment` -- GREEN,
  by design. It pins behaviour this change must preserve.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` -- 1114 passed, 0 failed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

# The process the container start chain runs between `seed_playbook` and
# `uvicorn` (`Dockerfile:86`).
REPORTING_ROOT: Final = "commerce_ops.check_step_handlers"

# The two composition roots `tests/unit/test_registrations_across_processes.py`
# already compares. The delta requires the reporting process to hold "the
# same handlers as every other process of this deployment that consults the
# registry", and these are those processes.
HTTP_ROOT: Final = "commerce_ops.main"
WORKER_ROOT: Final = "commerce_ops.worker"

# The one module that states which handlers this deployment answers for.
DECLARED_ROOT: Final = "commerce_ops.registrations"

STEP_SET_VARIABLE: Final = "COMMERCE_OPS_TEST_STEP_SET"

UNREGISTERED_HANDLER: Final = "price.a_handler_no_deploy_answers_for"
UNREGISTERED_STEP: Final = "price.buy-box-check"
REGISTERED_STEP: Final = "listing.subcategory-suggested"

_SUBPROCESS_TIMEOUT: Final = 180


# ---------------------------------------------------------------------------
# Reading a fresh interpreter's handler registry
# ---------------------------------------------------------------------------

_HANDLER_DUMP_SCRIPT: Final = """
import json

import {root}  # noqa: F401  -- imported for the registration side effect

from commerce_ops.launch.application import HANDLERS

print("HANDLER-DUMP " + json.dumps(sorted(HANDLERS.names())))
"""


def _run(
    script: str, workdir: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `script` in a fresh interpreter with an empty environment.

    Built from scratch rather than pruned, and run from a temporary
    directory, for the reason `test_registrations_across_processes.py`
    gives: nothing on the developer's machine and no repository-local
    `.env` may satisfy a configuration read at import.
    """
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=str(workdir),
        check=False,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )


def _handler_names(root: str, workdir: Path) -> list[str]:
    """The step-handler names a fresh interpreter holds after importing
    `root` and nothing else."""
    result = _run(_HANDLER_DUMP_SCRIPT.format(root=root), workdir)
    assert result.returncode == 0, (
        f"dumping the step-handler registry after importing {root} in a "
        "fresh interpreter failed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith("HANDLER-DUMP ")
    ]
    assert len(dumps) == 1, (
        f"expected exactly one handler dump from {root}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parsed: list[str] = json.loads(dumps[0][len("HANDLER-DUMP ") :])
    return parsed


# ---------------------------------------------------------------------------
# Driving the reporting process over a substituted step set
# ---------------------------------------------------------------------------

_REPORT_DRIVER_SCRIPT: Final = '''
"""Start the reporting process the way the deployment starts it.

Only the playbook read and the database session are substituted. The
registry is never supplied: it is whatever importing the reporting module
left in place, which is the property under test.
"""

import json
import os
import sys
from contextlib import asynccontextmanager

import commerce_ops.check_step_handlers as reporting_process

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

STEP_SET = json.loads(os.environ["COMMERCE_OPS_TEST_STEP_SET"])


def _definition(entry):
    return StepDefinition(
        identifier=entry["identifier"],
        name=entry["name"],
        gate=entry["gate"],
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=0),
        blocking=False,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        handler=entry["handler"],
        provenance=None,
    )


class _Record:
    def __init__(self, definition):
        self.definition = definition
        self.display_order = 10


class _SubstitutedRead:
    """The authoring read, answering the substituted step set.

    Shape transcribed from
    `tests/unit/test_check_step_handlers_reads_the_authored_set.py`.
    """

    def __init__(self, *args, **kwargs):
        pass

    async def load(self):
        return tuple(_Record(_definition(e)) for e in STEP_SET), 41


@asynccontextmanager
async def _no_session():
    yield None


OBSERVED = {
    "report_ran": False,
    "faults": [],
    "registry": None,
    "exit": None,
    "error": None,
    "registrations_imported": None,
}

_real_report = reporting_process.report_unregistered_handlers


def _recording_report(*args, **kwargs):
    faults = _real_report(*args, **kwargs)
    OBSERVED["report_ran"] = True
    OBSERVED["faults"] = [str(fault) for fault in faults]
    OBSERVED["registry"] = sorted(reporting_process.HANDLERS.names())
    return faults


reporting_process.PlaybookRepository = _SubstitutedRead
reporting_process.session = _no_session
reporting_process.report_unregistered_handlers = _recording_report

try:
    reporting_process.main()
except SystemExit as raised:
    OBSERVED["exit"] = 0 if raised.code is None else raised.code
except BaseException as raised:
    OBSERVED["error"] = type(raised).__name__ + ": " + str(raised)

OBSERVED["registrations_imported"] = "commerce_ops.registrations" in sys.modules

print("STARTUP-REPORT " + json.dumps(OBSERVED))
'''


def _step_entry(identifier: str, handler: str, gate: str) -> dict[str, str]:
    return {
        "identifier": identifier,
        "name": f"Work the step {identifier} asks for",
        "gate": gate,
        "handler": handler,
    }


def _start_the_reporting_process(
    steps: list[dict[str, str]], workdir: Path
) -> dict[str, Any]:
    """Start the reporting process over `steps` and return what it did."""
    result = _run(
        _REPORT_DRIVER_SCRIPT,
        workdir,
        extra_env={STEP_SET_VARIABLE: json.dumps(steps)},
    )
    assert result.returncode == 0, (
        "the driver that starts the reporting process in a fresh "
        "interpreter failed before it could report what happened. This is a "
        "failure of the driver, not a verdict on the process.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("STARTUP-REPORT ")
    ]
    assert len(dumps) == 1, (
        f"expected exactly one startup-report dump, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    observed: dict[str, Any] = json.loads(dumps[0][len("STARTUP-REPORT ") :])
    assert observed["error"] is None, (
        "the reporting process raised rather than reporting: "
        f"{observed['error']}\nstderr:\n{result.stderr}"
    )
    assert observed["report_ran"], (
        "the reporting process never reached the unregistered-handler "
        "report, so nothing below establishes anything about it.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return observed


def _named(observed: dict[str, Any], text: str) -> bool:
    return any(text in fault for fault in observed["faults"])


def _diagnostics(observed: dict[str, Any]) -> str:
    return (
        f"\nfaults: {observed['faults']}"
        f"\nregistry the reporting process consulted: {observed['registry']}"
        f"\ncommerce_ops.registrations imported by that process: "
        f"{observed['registrations_imported']} (recorded as a diagnostic; the "
        "delta fixes no mechanism for registration and nothing here asserts "
        "on it)"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("startup-handler-report")


@pytest.fixture(scope="module")
def registered_handler(workdir: Path) -> str:
    """A handler name this deployment's code registers.

    Read from the deployment's own declaration rather than hard-coded, so
    that a handler renamed out from under these tests fails them instead
    of quietly making them vacuous.
    """
    declared = _handler_names(DECLARED_ROOT, workdir)
    if not declared:
        pytest.fail(
            f"importing {DECLARED_ROOT} registers no step handler at all, so "
            "no step set below can hold a handler 'this deployment's code "
            "registers' and the scenarios cannot be exercised"
        )
    return declared[0]


# ---------------------------------------------------------------------------
# Scenario: A registered handler draws no fault at startup
# ---------------------------------------------------------------------------


def test_a_registered_handler_draws_no_fault_at_startup(
    workdir: Path, registered_handler: str
) -> None:
    """Scenario: A registered handler draws no fault at startup.

    WHEN the process that makes the startup report is started the way the
    deployment starts it, over a step set holding an `active` `automated`
    step whose handler this deployment's code registers
    THEN no fault is reported for that step.

    SPECIFIED. The step set holds exactly one step and its handler is one
    this deployment registers, so any fault at all is a fault for that
    step.
    """
    steps = [_step_entry(REGISTERED_STEP, registered_handler, "listable")]

    observed = _start_the_reporting_process(steps, workdir)

    assert observed["faults"] == [], (
        f"the startup report named a step whose handler ({registered_handler}) "
        "this deployment registers. A report that cries fault at a healthy "
        "deployment is worse than no report: the next real fault reads as "
        "more of the same." + _diagnostics(observed)
    )


# ---------------------------------------------------------------------------
# Scenario: An unregistered handler is named at startup
# ---------------------------------------------------------------------------


def test_an_unregistered_handler_is_named_at_startup(
    workdir: Path, registered_handler: str
) -> None:
    """Scenario: An unregistered handler is named at startup.

    WHEN the process that makes the startup report is started the way the
    deployment starts it, over a step set holding an `active` `automated`
    step whose handler this deployment's code does not register
    THEN the report names that step and the handler it could not resolve.

    The first assertion is SPECIFIED by that **THEN**.

    The second is SPECIFIED too, by the paragraph the same delta adds: "A
    report produced against a registry holding none of them SHALL NOT
    satisfy this requirement: such a report answers identically for a
    deployment that registers a step's handler and one that does not, and
    so establishes nothing about either." A step set holding both kinds
    of step is what makes the two answers distinguishable, so the naming
    assertion above means something.
    """
    steps = [
        _step_entry(REGISTERED_STEP, registered_handler, "listable"),
        _step_entry(UNREGISTERED_STEP, UNREGISTERED_HANDLER, "live"),
    ]

    observed = _start_the_reporting_process(steps, workdir)

    assert _named(observed, UNREGISTERED_STEP), (
        "the startup report did not name the `active` `automated` step "
        f"whose handler this deployment does not register ({UNREGISTERED_STEP})"
        + _diagnostics(observed)
    )
    assert _named(observed, UNREGISTERED_HANDLER), (
        "the startup report named the step but not the handler it could not "
        f"resolve ({UNREGISTERED_HANDLER})" + _diagnostics(observed)
    )
    assert not _named(observed, REGISTERED_STEP), (
        "the startup report named the step whose handler this deployment "
        "does register alongside the one it does not, so it answers "
        "identically for both and establishes nothing about either."
        + _diagnostics(observed)
    )


# ---------------------------------------------------------------------------
# Scenario: The faults the report names do not stop the deployment
# ---------------------------------------------------------------------------


def test_the_faults_the_report_names_do_not_stop_the_deployment(
    workdir: Path, registered_handler: str
) -> None:
    """Scenario: The faults the report names do not stop the deployment.

    WHEN the startup report names one or more `active` `automated` steps
    whose handlers are unregistered
    THEN the deployment continues to start, and every step whose handler
    is registered is unaffected.

    SPECIFIED, first clause. The reporting process runs inside a `&&`
    chain ahead of `exec uvicorn` (`Dockerfile:86`), so "continues to
    start" is observable as this process's own exit status: zero, or no
    exit at all.

    The second clause -- that a registered handler is unaffected by the
    faults named beside it -- is carried by
    `test_a_registered_handler_draws_no_fault_at_startup` and by the third
    assertion of `test_an_unregistered_handler_is_named_at_startup`, and
    is not re-asserted here.

    This test is expected to be green both before and after the change:
    the report is advisory today and this change must keep it advisory.
    Its value is regression protection, not a red-then-green transition.
    """
    steps = [
        _step_entry(REGISTERED_STEP, registered_handler, "listable"),
        _step_entry(UNREGISTERED_STEP, UNREGISTERED_HANDLER, "live"),
    ]

    observed = _start_the_reporting_process(steps, workdir)

    assert observed["faults"], (
        "the report named no fault at all, so this test would pass without "
        "the deployment ever having been asked to continue past one."
        + _diagnostics(observed)
    )
    assert observed["exit"] in (None, 0), (
        "the startup report stopped the deployment on account of the faults "
        f"it named (exit status {observed['exit']!r}). One unresolvable step "
        "leaves every other part of a launch working; refusing to start "
        "turns it into a full outage." + _diagnostics(observed)
    )
