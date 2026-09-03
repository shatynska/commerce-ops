"""The deployment registers a finding sink for `lp.strategy.006`.

Derived from `tasks.md` 1.19 and 5.3 of the change
`screen-for-hazard-categories`, and from `compliance-screen`'s ADDED
requirement *The screen reports what it established as a typed finding* —
whose whole point is defeated by a handler that reports one where no sink
accepts it. The previous change's own requirement said so in as many
words when it declined to report a finding: "reporting a finding no sink
accepts would record nothing while implying something was recorded."

**No `#### Scenario:` in this change's deltas states this.** The sink
registration is composition-root wiring, which none of the four
capabilities specifies; it is covered here because `tasks.md` 1.19 asks
for it and because the finding path is inert without it. Classified
DERIVED throughout, and recorded as such in `test-manifest.md`.

## A departure from `tasks.md` 1.19, reported rather than made silently

`tasks.md` 1.19 asks that "both composition roots hold the second sink",
by extending `tests/unit/test_registrations_across_processes.py`. Two
things stand in the way, and neither is this pass's to settle:

1. **That file is not edited.** This pass adds tests and never subtracts
   or rewrites, so the check is written here instead.
2. **Sinks are not a two-root registration.** Step *handlers* and
   recurring *work* are registered in every process — the existing file
   checks exactly those two, and for a stated reason: the admin surface
   validates an activation against the handler registry while the worker
   runs the pass against it. A finding sink is read only by the automation
   pass, which runs in the worker. Asserting that
   `commerce_ops.main` holds it would assert a symmetry no artifact
   states and that the existing `lp.listing.007` sink does not have
   either.

So what is asserted here is what the artifacts actually fix: the
**worker** root holds a sink for `lp.strategy.006`, carrying the field
and wording `tasks.md` 5.3 names, beside the one that already exists. The
discrepancy with 1.19's wording is reported to the dispatcher and
recorded in `test-manifest.md` as an unresolved question rather than
resolved by writing an assertion against a symmetry nobody specified.

## Level

A **fresh interpreter** per root, as
`tests/unit/test_registrations_across_processes.py` does and for the same
reason it gives: the registries are module globals, so an in-process
comparison after importing a root is tautological. The subprocess is
handed a bare environment and `tmp_path` as its working directory, so
nothing on the developer's machine and no repository-local `.env`
satisfies a configuration read at import.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 5.3: the step identifier `lp.strategy.006`, the field
`hazard_categories`, and the wording `Hazard categories`.

INVENTED, recorded in `test-manifest.md`: the dump script's own shape;
that the sink mapping is reachable as `automation_pass.recorders` **or**
as a module-level mapping on the worker whose values carry a `field`
(both are searched, so either wiring is found); and the attribute names a
sink's field and wording are read under.

## Expected first-run state

`tasks.md` 5.3 has not landed, so this is expected to fail with the
`lp.strategy.006` key absent from the dumped registration — failure state
1 in `ai-toolkit:testing`'s terms, since the code runs and produces a
registration missing the entry. The companion assertion that
`lp.listing.007` is still registered is expected to **pass** on first run
and is what keeps a later regression legible.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

WORKER_ROOT: Final = "commerce_ops.worker"

SCREEN_STEP_ID: Final = "lp.strategy.006"
ADVISOR_STEP_ID: Final = "lp.listing.007"
HAZARD_FIELD: Final = "hazard_categories"
HAZARD_WORDING: Final = "Hazard categories"

_DUMP_SCRIPT: Final = """
import json

import {root}  # noqa: F401  -- importing a composition root wires its sinks

from commerce_ops.launch.infrastructure.driving import automation_pass


def _fields(entry):
    for attribute in ("field", "field_name", "name"):
        value = getattr(entry, attribute, None)
        if isinstance(value, str):
            return value
    return None


def _wording(entry):
    for attribute in ("reads_as", "wording", "reads", "label"):
        value = getattr(entry, attribute, None)
        if isinstance(value, str):
            return value
    return None


def _looks_like_a_sink_mapping(value):
    if not hasattr(value, "items"):
        return False
    values = list(value.values())
    return bool(values) and all(_fields(entry) is not None for entry in values)


candidates = [getattr(automation_pass, "recorders", None)]
candidates.extend(
    value for value in vars({root}).values() if _looks_like_a_sink_mapping(value)
)

found = {{}}
for mapping in candidates:
    if not _looks_like_a_sink_mapping(mapping):
        continue
    for key, entry in mapping.items():
        found[str(key)] = [_fields(entry), _wording(entry)]

print("SINK-DUMP " + json.dumps(found, sort_keys=True))
"""


def _dump_sinks(root: str, tmp_path: Path) -> dict[str, list[Any]]:
    """The finding sinks a fresh interpreter holds after importing `root`."""
    result = subprocess.run(
        [sys.executable, "-c", _DUMP_SCRIPT.format(root=root)],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"dumping the finding sinks after importing {root} in a fresh "
        "interpreter failed. Note that this test reads the root by import "
        "alone: a registration deferred into a function the process calls "
        "later is not visible to a process that only imports it.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith("SINK-DUMP ")
    ]
    assert len(dumps) == 1, (
        f"expected exactly one sink dump from {root}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parsed: dict[str, list[Any]] = json.loads(dumps[0][len("SINK-DUMP ") :])
    return parsed


@pytest.fixture(scope="module")
def worker_sinks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[Any]]:
    return _dump_sinks(WORKER_ROOT, tmp_path_factory.mktemp("sinks"))


def test_the_worker_registers_a_sink_for_the_compliance_screen(
    worker_sinks: dict[str, list[Any]],
) -> None:
    """DERIVED from `tasks.md` 5.3.

    Without this registration the screen's finding is reported and
    dropped: the pass looks a sink up by step identifier and writes
    nothing where none is found. Every other test in this change would
    still pass — the handler reports its finding, the catalog use case
    records what it is given — and no product would ever carry a hazard
    category in production.
    """
    assert SCREEN_STEP_ID in worker_sinks, (
        f"the worker registers no finding sink for {SCREEN_STEP_ID!r}, so "
        "the screen's finding is reported and then dropped. Registered "
        f"sinks: {sorted(worker_sinks)}"
    )


def test_the_screens_sink_names_the_field_and_its_wording(
    worker_sinks: dict[str, list[Any]],
) -> None:
    """DERIVED from `tasks.md` 5.3, which fixes both values.

    The field is what the value is written to and the wording is what the
    launch detail page renders — `launch-admin` requires the wording be
    "supplied alongside the sink registration … so that naming a sink and
    naming how it reads are one act". A sink registered without one
    renders `hazard_categories` at an admin.
    """
    assert SCREEN_STEP_ID in worker_sinks, (
        f"no sink is registered for {SCREEN_STEP_ID!r}"
    )
    field_name, wording = worker_sinks[SCREEN_STEP_ID]

    assert field_name == HAZARD_FIELD, (
        f"the sink for {SCREEN_STEP_ID!r} writes to {field_name!r} rather "
        f"than {HAZARD_FIELD!r}"
    )
    assert wording == HAZARD_WORDING, (
        f"the sink for {SCREEN_STEP_ID!r} reads as {wording!r} rather than "
        f"{HAZARD_WORDING!r}; without it the page renders the storage "
        "identifier at an admin"
    )


def test_the_existing_sink_is_still_registered_beside_it(
    worker_sinks: dict[str, list[Any]],
) -> None:
    """The second sink is added *beside* the first, not in place of it.

    Expected to pass on first run, and stated separately so that a
    registration rewritten rather than extended is legible by name rather
    than as an unrelated advisor test failing somewhere else.
    """
    assert ADVISOR_STEP_ID in worker_sinks, (
        f"the sink for {ADVISOR_STEP_ID!r} is no longer registered; the "
        f"second sink replaced the first. Registered: {sorted(worker_sinks)}"
    )
