"""Registering a step handler loads nothing the handler needs to run.

Derived strictly from the delta spec of the OpenSpec change
`keep-handler-imports-cheap`
(`openspec/changes/keep-handler-imports-cheap/specs/launch-step-automation/spec.md`):

- "Registering a handler does not load what the handler needs to run"
  — *Registering a handler loads no model client*, *A process that never
  invokes a handler still pays only for the registration*.

The requirement's remaining scenario, *A handler still resolves a step*,
is deliberately **not** covered here.
`tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py`
already drives the advisor over a stubbed model and specifies the
outcome and result text it produces; that scenario asks whether deferring
a resource changed them, and the answer is that same file passing
unmodified (tasks.md 5.2). A copy of those cases in this file would
assert the same thing twice and drift from the original.

See `test-manifest.md` at the change root for the full accounting.

## Expected to fail on the unmodified tree

The module paths below are as they were when the baseline was taken, and
are left that way on purpose: `group-step-handlers` has since moved the
advisor to `commerce_ops.step_handlers.listing.subcategory_advisor`, and
rewriting an observation to a path that did not exist when it was made
would turn a record into a claim. Nothing here is executable — the
assertions read `HANDLER_MODULES` at runtime (see below), so no module
path is hard-coded in this file.

tasks.md 2.4: "a guard that is green before the change guards nothing."
Observed when this pass was written, against the tree before task 3
lands (`uv run pytest tests/unit/test_handler_registration_is_cheap.py`
-> **2 failed, 1 passed**):

- `test_registering_every_handler_loads_no_model_client` fails — a fresh
  interpreter that imported `commerce_ops.registrations` and invoked
  nothing holds 2,645 modules, `langgraph` and `openai` among them.
- `test_loading_a_handler_module_alone_loads_no_model_client` fails —
  `commerce_ops.subcategory_advisor.application.handler` alone is 2,023
  modules, `langgraph` and `openai` among them.
- `test_every_handler_module_registers_its_name` passes already, and is
  expected to keep passing: it is the half that must survive the
  deferral, not the half the deferral fixes.

proposal.md records the cause — `subcategory_advisor/application/graph.py`
imports `langchain_core`, `langchain_openai` and `langgraph.graph` at
module level for names used only inside function bodies. Both failures
are the strongest state available: the assertions executed and
discriminated between the property holding and not, rather than failing
on an absent target. Do not repair either by weakening it; they go green
when task 3 moves those imports.

## Why a subprocess, and why an in-process version would prove nothing

`sys.modules` is process-global. Within one pytest interpreter another
test — `tests/agents/` most obviously — may already have imported
LangGraph, so an in-process assertion that `langgraph` is absent measures
test ordering rather than what registration costs. Each probe below
therefore runs in a fresh interpreter, following the subprocess pattern
`tests/unit/test_registrations_across_processes.py` already establishes
for process-global registration effects, and reading the same
`commerce_ops.launch.application.HANDLERS` accessor that file's handler
dump reads. The environment is built from scratch and the working
directory is `tmp_path` for the reason that file gives: nothing on the
developer's machine, and no repository-local `.env`, may satisfy a
configuration read at import.

## Why `commerce_ops.registrations`, and not a handler module by name

design.md, Decision 2: the property is violated by whoever writes the
*next* handler, in a file a single-module test does not name. So the
registry-wide probe imports the one list every composition root reaches
the registry through, and the per-module probe below takes its modules
from `HANDLER_MODULES` rather than from a literal in this file. No
handler is named here, and a handler added later is covered on the day it
joins the list.

## Specified, derived, invented

SPECIFIED by the delta spec: that a name resolves after registration and
that the process then holds none of the resources the handler uses to
resolve a step.

Specified by the change's own artifacts rather than by the delta spec's
prose: that "the resources the handler uses" is read here as the
top-level packages `langgraph` and `openai` being absent from
`sys.modules`. proposal.md ("leaves `langgraph` and `openai` out of
`sys.modules`") and tasks.md 2.1 both fix that pair. The requirement is
deliberately broader — "a language model client, a graph, an HTTP
session, or anything else" — and this test asserts the named pair only;
`langchain_core` and `langchain_openai` are left uncovered on purpose,
recorded in `test-manifest.md`.

DERIVED: that every module in `HANDLER_MODULES` must expose a *string*
`HANDLER_NAME` and that it must appear in `HANDLERS` afterwards. The
name-per-module convention is established by practice (`handler.py`), not
by a requirement; tasks.md 2.2 asks that a module exposing no such name
fail loudly rather than be skipped, because a silent skip would hide a
handler that registered nothing. `HANDLER_MODULES` holding modules rather
than names, and being importable from `commerce_ops.registrations`, is
likewise fixed by tasks.md 2.2 — `_registry_probe` below is the single
correction point if that shape differs.

Not asserted: any module count or import duration. The ~1,110 / ~2,610
figures in tasks.md 1.2 are measurements for the pull request, not
thresholds — a count assertion would fail on an unrelated dependency
bump and say nothing about this property. The probe reports its count in
failure messages as context only.
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

# The libraries the change names. A top-level package is treated as loaded
# when it, or any submodule of it, is in `sys.modules`.
HEAVY_LIBRARIES = ("langgraph", "openai")

REGISTRATIONS_MODULE = "commerce_ops.registrations"
HANDLER_MODULES_ATTRIBUTE = "HANDLER_MODULES"
HANDLER_NAME_ATTRIBUTE = "HANDLER_NAME"

PROBE_PREFIX = "HANDLER-IMPORT-PROBE "

# No literal braces anywhere in the probe scripts: they are `str.format`
# templates, and doubling braces to keep a dict literal happy reads worse
# than calling `dict()`.
_REGISTRY_PROBE_SCRIPT = """
import json
import sys

import commerce_ops.registrations as registrations

from commerce_ops.launch.application import HANDLERS

records = []
for entry in getattr(registrations, "{modules_attribute}"):
    module_name = getattr(entry, "__name__", None)
    handler_name = getattr(entry, "{name_attribute}", None)
    records.append(
        dict(
            module=module_name if module_name is not None else repr(entry),
            is_module=module_name is not None,
            handler_name=handler_name if isinstance(handler_name, str) else None,
        )
    )

loaded = sorted(set(name.partition(".")[0] for name in list(sys.modules)))

print(
    "{prefix}"
    + json.dumps(
        dict(
            handler_modules=records,
            registered=sorted(HANDLERS.names()),
            loaded_roots=loaded,
            module_count=len(sys.modules),
        )
    )
)
"""

_SINGLE_MODULE_PROBE_SCRIPT = """
import json
import sys

import {module}

from commerce_ops.launch.application import HANDLERS

handler_name = getattr(sys.modules["{module}"], "{name_attribute}", None)

loaded = sorted(set(name.partition(".")[0] for name in list(sys.modules)))

print(
    "{prefix}"
    + json.dumps(
        dict(
            module="{module}",
            handler_name=handler_name if isinstance(handler_name, str) else None,
            registered=sorted(HANDLERS.names()),
            loaded_roots=loaded,
            module_count=len(sys.modules),
        )
    )
)
"""


@dataclass(frozen=True)
class HandlerModuleRecord:
    """One entry of `HANDLER_MODULES`, as a fresh interpreter saw it."""

    module: str
    is_module: bool
    handler_name: str | None


@dataclass(frozen=True)
class RegistryProbe:
    """What a fresh interpreter holds after importing the one list."""

    handler_modules: tuple[HandlerModuleRecord, ...]
    registered: tuple[str, ...]
    loaded_roots: tuple[str, ...]
    module_count: int


@dataclass(frozen=True)
class ModuleProbe:
    """What a fresh interpreter holds after importing one handler module."""

    module: str
    handler_name: str | None
    registered: tuple[str, ...]
    loaded_roots: tuple[str, ...]
    module_count: int


def _run_probe(script: str, tmp_path: Path, subject: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"probing a fresh interpreter that had imported {subject} failed. "
        f"If it failed on `{HANDLER_MODULES_ATTRIBUTE}`, that name and its "
        f"shape — modules, not names — are this file's one correction "
        f"point: tasks.md 2.2 fixes it at `{REGISTRATIONS_MODULE}`.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith(PROBE_PREFIX)
    ]
    assert len(dumps) == 1, (
        f"expected exactly one probe line from {subject}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parsed: dict[str, Any] = json.loads(dumps[0][len(PROBE_PREFIX) :])
    return parsed


def _registry_probe(tmp_path: Path) -> RegistryProbe:
    """Import `commerce_ops.registrations` — and nothing else — freshly."""
    payload = _run_probe(
        _REGISTRY_PROBE_SCRIPT.format(
            modules_attribute=HANDLER_MODULES_ATTRIBUTE,
            name_attribute=HANDLER_NAME_ATTRIBUTE,
            prefix=PROBE_PREFIX,
        ),
        tmp_path,
        REGISTRATIONS_MODULE,
    )
    return RegistryProbe(
        handler_modules=tuple(
            HandlerModuleRecord(
                module=str(record["module"]),
                is_module=bool(record["is_module"]),
                handler_name=record["handler_name"],
            )
            for record in payload["handler_modules"]
        ),
        registered=tuple(payload["registered"]),
        loaded_roots=tuple(payload["loaded_roots"]),
        module_count=int(payload["module_count"]),
    )


def _module_probe(module: str, tmp_path: Path) -> ModuleProbe:
    """Import one handler module — and nothing else — freshly."""
    payload = _run_probe(
        _SINGLE_MODULE_PROBE_SCRIPT.format(
            module=module,
            name_attribute=HANDLER_NAME_ATTRIBUTE,
            prefix=PROBE_PREFIX,
        ),
        tmp_path,
        module,
    )
    return ModuleProbe(
        module=str(payload["module"]),
        handler_name=payload["handler_name"],
        registered=tuple(payload["registered"]),
        loaded_roots=tuple(payload["loaded_roots"]),
        module_count=int(payload["module_count"]),
    )


def _heavy_loaded(loaded_roots: tuple[str, ...]) -> list[str]:
    return [library for library in HEAVY_LIBRARIES if library in loaded_roots]


@pytest.fixture(scope="module")
def registry_probe(tmp_path_factory: pytest.TempPathFactory) -> RegistryProbe:
    """One fresh-interpreter probe, shared read-only by the tests below.

    Module-scoped because the subprocess is the expensive part and the
    result is frozen — nothing here may mutate it into a different
    observation for the next test.
    """
    return _registry_probe(tmp_path_factory.mktemp("registry-probe"))


def test_registering_every_handler_loads_no_model_client(
    registry_probe: RegistryProbe,
) -> None:
    """Scenario: A process that never invokes a handler still pays only
    for the registration.

    WHEN a process registers every handler this deployment answers for in
    order to read the registry, and invokes none of them
    THEN it loads no handler's working resources.

    SPECIFIED, with the reading of "working resources" fixed by
    proposal.md and tasks.md 2.1 as `langgraph` and `openai`. The process
    imports `commerce_ops.registrations` — the one list every composition
    root reaches the registry through — and invokes nothing.
    """
    loaded = _heavy_loaded(registry_probe.loaded_roots)

    assert loaded == [], (
        f"importing {REGISTRATIONS_MODULE} in a fresh interpreter loaded "
        f"{', '.join(loaded)} without invoking any handler. Registering a "
        "handler must make its name resolvable and load nothing the "
        "handler needs in order to run: every process that consults the "
        "registry — including ones that never invoke a handler, such as "
        "the startup handler report — pays this cost, multiplied by every "
        "handler the deployment answers for.\n"
        f"registered handlers: {list(registry_probe.registered)}\n"
        f"handler modules: "
        f"{[record.module for record in registry_probe.handler_modules]}\n"
        f"modules held: {registry_probe.module_count} (context, not a "
        "threshold)\n"
        "A handler's dependencies are obtained when it runs, not when it "
        "is registered."
    )


def test_every_handler_module_registers_its_name(
    registry_probe: RegistryProbe,
) -> None:
    """Scenario: Registering a handler loads no model client — the half
    that says "its name resolves".

    Partly SPECIFIED, partly DERIVED. Specified: after loading, the
    handler's name resolves in the registry. Derived from tasks.md 2.2:
    that the name is a module-level `HANDLER_NAME`, and that a module
    exposing none fails loudly rather than being skipped.

    Without this, the absence assertions above would pass against a
    `registrations.py` that imported nothing at all — which is the one
    way to load no model client that also registers no handler.
    """
    assert registry_probe.handler_modules, (
        f"{REGISTRATIONS_MODULE}.{HANDLER_MODULES_ATTRIBUTE} is empty, so "
        "the absence assertion in this file would hold in a deployment "
        "that registers no handler at all and can resolve no automated "
        "step"
    )

    not_modules = [
        record.module
        for record in registry_probe.handler_modules
        if not record.is_module
    ]
    assert not_modules == [], (
        f"{HANDLER_MODULES_ATTRIBUTE} holds entries that are not modules: "
        f"{not_modules}. tasks.md 2.2 fixes it as tuple[ModuleType, ...]; "
        "if that changed, this file's probe is the correction point."
    )

    nameless = [
        record.module
        for record in registry_probe.handler_modules
        if record.handler_name is None
    ]
    assert nameless == [], (
        f"these handler modules expose no string {HANDLER_NAME_ATTRIBUTE}: "
        f"{nameless}. Failing rather than skipping is deliberate "
        "(tasks.md 2.2): a skipped module is indistinguishable from one "
        "that registered nothing, which is exactly the regression the "
        "rest of this file cannot see."
    )

    unregistered = [
        record.handler_name
        for record in registry_probe.handler_modules
        if record.handler_name not in registry_probe.registered
    ]
    assert unregistered == [], (
        "importing the one list left these handler names unresolvable in "
        f"the registry: {unregistered}. Registration is an import side "
        "effect, so a name that does not appear means the module was "
        "loaded and registered nothing.\n"
        f"registered: {list(registry_probe.registered)}"
    )


def test_loading_a_handler_module_alone_loads_no_model_client(
    registry_probe: RegistryProbe, tmp_path: Path
) -> None:
    """Scenario: Registering a handler loads no model client.

    WHEN a step handler's module is loaded such that its name becomes
    resolvable in the registry
    THEN its name resolves, and the process holds no resource the handler
    uses to resolve a step.

    SPECIFIED, with the same reading of "resource" as the first test.
    Stated per handler module rather than over the whole list, because
    that is how the scenario is stated and because it attributes the cost:
    with twenty handlers registered, the registry-wide test says a model
    client was loaded and this one says which module loaded it. The
    modules come from `HANDLER_MODULES`, not from a literal here, so a
    handler added later is covered without editing this file.
    """
    offenders: list[str] = []
    unresolved: list[str] = []
    for record in registry_probe.handler_modules:
        if not record.is_module:
            continue
        probe = _module_probe(record.module, tmp_path)
        loaded = _heavy_loaded(probe.loaded_roots)
        if loaded:
            offenders.append(
                f"{probe.module} loaded {', '.join(loaded)} "
                f"({probe.module_count} modules)"
            )
        if probe.handler_name is None or probe.handler_name not in probe.registered:
            unresolved.append(
                f"{probe.module} registered {probe.handler_name!r}, "
                f"registry holds {list(probe.registered)}"
            )

    assert offenders == [], (
        "loading these handler modules registered their names and also "
        "loaded what they need in order to run:\n" + "\n".join(offenders) + "\n"
        "Obtain the resource inside the function that uses it, so that "
        "registration costs the registration and nothing else."
    )
    assert unresolved == [], (
        "loading these handler modules did not make their names "
        "resolvable:\n" + "\n".join(unresolved)
    )
