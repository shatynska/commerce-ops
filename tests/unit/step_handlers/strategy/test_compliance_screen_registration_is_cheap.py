"""Importing the compliance screen registers a name and loads nothing else
(`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from the ADDED requirement *The screen is reached only through the
step it is authored onto*, one scenario:

- Registration loads nothing the run needs

`tasks.md` 1.13. Its two sibling scenarios are elsewhere: *The handler is
resolvable in every process consulting the registry* in
`tests/unit/test_compliance_screen_registered_across_processes.py`, and
*The screen does not test which step invoked it* in
`tests/agents/step_handlers/strategy/test_compliance_screen_failure_and_context.py`.
See `test-manifest.md` at the change root for the full accounting.

## Why a subprocess, and why an in-process version would prove nothing

`sys.modules` is process-global. Within one pytest interpreter another test
— `tests/agents/` most obviously — has already imported LangGraph by the
time this runs, so an in-process assertion that `langgraph` is absent
measures test ordering rather than what registration costs. The probe below
therefore runs in a fresh interpreter, following the pattern
`tests/unit/test_handler_registration_is_cheap.py` and
`tests/unit/test_registrations_across_processes.py` already establish for
process-global effects. `tasks.md` 1.13 asks for exactly this: "Assert
against `sys.modules` in a fresh interpreter, not by inspection."

The environment is built from scratch rather than pruned, and the working
directory is `tmp_path`: nothing on the developer's machine, and no
repository-local `.env`, may satisfy a configuration read at import. That
is what makes "no credential is read" an observation rather than a claim —
the import runs with no credential available at all, so a module reading
one at import time fails the probe outright.

## Why this file exists beside the registry-wide guard

`tests/unit/test_handler_registration_is_cheap.py` already asserts this
property over every module in `HANDLER_MODULES`, so this screen is covered
there from the moment `registrations.py` names it. This file is not a
duplicate of that: it names **this** module directly, so the property is
established for the screen whether or not the registrations edit has
landed, and it covers `langchain_openai` — the graph library this screen
imports inside its own graph-building functions — which the registry-wide
guard's `langgraph`/`openai` pair does not name.

## What is fixed, and what is INVENTED

Fixed by the delta: that importing the module makes the name resolvable,
and that doing so constructs no model, reads no credential and imports no
graph library.

Fixed by `tasks.md` 2.2: the module path and that it exposes
`HANDLER_NAME`. Fixed by `tasks.md` 2.7: that `langgraph` and
`langchain_openai` are imported inside the functions that build a graph and
that the production graph is `lru_cache`d.

INVENTED, recorded in `test-manifest.md`: that "a graph library" is read as
the top-level packages `langgraph`, `langchain_openai` and `openai` being
absent from `sys.modules`, and that "no model is constructed" is read as
the same absence. The delta's wording is broader; a module count is not
asserted at all, since it would fail on an unrelated dependency bump and
say nothing about this property.

## Expected first-run state

`commerce_ops.step_handlers.strategy.compliance_screen` does not exist, so
the probe's subprocess exits non-zero on `ModuleNotFoundError` and both
tests fail on an absent target — failure state 2 per `ai-toolkit:testing`.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

MODULE = "commerce_ops.step_handlers.strategy.compliance_screen"
EXPECTED_HANDLER_NAME = "strategy.compliance_screen"

#: The libraries this screen needs in order to run, and must not load in
#: order to be registered. `openai` is the client `langchain_openai`
#: constructs; naming it as well as the wrapper is what catches a model
#: built at import rather than on first use.
GRAPH_LIBRARIES = ("langgraph", "langchain_openai", "openai")

PROBE_PREFIX = "COMPLIANCE-SCREEN-PROBE "

# No literal braces in the probe script: it is a `str.format` template.
_PROBE_SCRIPT = """
import json
import sys

import {module}

from commerce_ops.launch.application import HANDLERS

handler_name = getattr(sys.modules["{module}"], "HANDLER_NAME", None)

loaded = sorted(set(name.partition(".")[0] for name in list(sys.modules)))

print(
    "{prefix}"
    + json.dumps(
        dict(
            handler_name=handler_name if isinstance(handler_name, str) else None,
            registered=sorted(HANDLERS.names()),
            loaded_roots=loaded,
            module_count=len(sys.modules),
        )
    )
)
"""


@dataclass(frozen=True)
class ModuleProbe:
    """What a fresh interpreter holds after importing the screen alone."""

    handler_name: str | None
    registered: tuple[str, ...]
    loaded_roots: tuple[str, ...]
    module_count: int


def _probe(tmp_path: Path) -> ModuleProbe:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE_SCRIPT.format(module=MODULE, prefix=PROBE_PREFIX),
        ],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"importing {MODULE} in a fresh interpreter with no configuration "
        "present failed. Registration must make the handler's name "
        "resolvable and read nothing — a credential read at import would "
        "fail exactly here.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith(PROBE_PREFIX)
    ]
    assert len(dumps) == 1, (
        f"expected exactly one probe line from {MODULE}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload: dict[str, Any] = json.loads(dumps[0][len(PROBE_PREFIX) :])
    return ModuleProbe(
        handler_name=payload["handler_name"],
        registered=tuple(payload["registered"]),
        loaded_roots=tuple(payload["loaded_roots"]),
        module_count=int(payload["module_count"]),
    )


@pytest.fixture(scope="module")
def probe(tmp_path_factory: pytest.TempPathFactory) -> ModuleProbe:
    """One fresh-interpreter probe, shared read-only by the tests below.

    Module-scoped because the subprocess is the expensive part and the
    result is frozen — nothing here may mutate it into a different
    observation for the next test.
    """
    return _probe(tmp_path_factory.mktemp("compliance-screen-probe"))


def test_importing_the_screen_makes_its_name_resolvable(probe: ModuleProbe) -> None:
    """Scenario: Registration loads nothing the run needs — the half that
    says the name becomes resolvable.

    SPECIFIED: the scenario's WHEN is "the module holding this screen is
    imported **so that its name becomes resolvable**", so the absence
    assertions below are only meaningful alongside this one. Without it
    they would hold in a deployment that registers nothing at all, which is
    the one way to load no model client that also resolves no step.

    The name itself is fixed by `tasks.md` 2.2 and by the requirement that
    a handler's first name segment be the discipline it is written for.
    """
    assert probe.handler_name == EXPECTED_HANDLER_NAME, (
        f"{MODULE} exposes HANDLER_NAME={probe.handler_name!r}; the "
        f"requirement fixes the first segment as the discipline the screen "
        f"is written for, and `tasks.md` 2.2 fixes the whole as "
        f"{EXPECTED_HANDLER_NAME!r}"
    )
    assert EXPECTED_HANDLER_NAME in probe.registered, (
        f"importing {MODULE} left {EXPECTED_HANDLER_NAME!r} unresolvable in "
        "the registry. Registration is an import side effect, so a name "
        "that does not appear means the module was loaded and registered "
        f"nothing.\nregistered: {list(probe.registered)}"
    )


def test_registration_constructs_no_model_and_imports_no_graph_library(
    probe: ModuleProbe,
) -> None:
    """Scenario: Registration loads nothing the run needs.

    WHEN the module holding this screen is imported so that its name
    becomes resolvable
    THEN no model is constructed, no credential is read, and no graph
    library is imported.

    SPECIFIED, with "graph library" and "model constructed" read as the
    three top-level packages below being absent from `sys.modules`. "No
    credential is read" is established by the probe's environment: the
    subprocess holds nothing but `PATH` and runs in an empty directory, so
    an import-time read would have failed the probe before any assertion
    here ran.

    Every process consulting the registry pays this cost — the startup
    handler report among them, which never invokes a handler at all —
    multiplied by every handler the deployment answers for.
    """
    loaded = [library for library in GRAPH_LIBRARIES if library in probe.loaded_roots]

    assert loaded == [], (
        f"importing {MODULE} in a fresh interpreter loaded "
        f"{', '.join(loaded)} without invoking the handler. `langgraph` and "
        "`langchain_openai` belong inside the functions that build a graph, "
        "and the production graph is built on first use rather than at "
        "import, so that registration costs the registration and nothing "
        f"else.\nmodules held: {probe.module_count} (context, not a "
        "threshold)"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Any module count or import duration. The counts in the sibling
#   handler's own change are measurements for a pull request, not
#   thresholds; a count assertion would fail on an unrelated dependency
#   bump and say nothing about this property. The probe reports its count
#   in failure messages as context only.
# - That the correspondence between the `strategy/` directory and the
#   `strategy.` name prefix is enforced. The requirement states outright
#   that it is "a convention of where handlers are grouped, not a rule the
#   registry enforces", so there is nothing to assert.
# ---------------------------------------------------------------------------
