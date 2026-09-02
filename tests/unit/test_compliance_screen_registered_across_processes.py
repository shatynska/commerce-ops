"""Every process consulting the registry resolves the compliance screen
(`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from the ADDED requirement *The screen is reached only through the
step it is authored onto*, one scenario:

- The handler is resolvable in every process consulting the registry

`tasks.md` 1.14. See `test-manifest.md` at the change root for the full
accounting.

## Why this is a new file rather than an edit to the existing one

`tasks.md` 1.14 asks that the existing cross-process registration check —
`tests/unit/test_registrations_across_processes.py` — be *extended* so both
composition roots hold the new handler. This pass is additive only and does
not edit existing test files, so the same scenario is covered here instead,
by the same mechanism that file establishes: each root is read in a fresh
interpreter and the handler names it holds are compared. Whoever implements
the change may fold this file's assertion into that one; the scenario is
covered either way, and it is recorded in `test-manifest.md` as the one
place this pass departed from a task's literal wording.

What that file already asserts and this one does not repeat: that the two
composition roots and the reporting process resolve the *same* set of
handler names. That equality holds whether or not this screen is in the
set. What is asserted here is the other half — that the set contains this
screen — which is the failure adding a handler to only one root produces.

## Why a subprocess, and why an in-process version would prove nothing

The registry is a module-global in `launch.application`, so within one
pytest process importing `commerce_ops.worker` and importing
`commerce_ops.main` read the *same object*. An in-process comparison is
therefore tautological — it holds even where one root never imports the
handler at all, which is precisely the divergence the scenario exists to
detect. Each root is run in a fresh interpreter here, following the pattern
`tests/unit/test_registrations_across_processes.py` establishes.

The environment handed to each subprocess is built from scratch and the
working directory is `tmp_path`, for the reason that file gives: nothing on
the developer's machine, and no repository-local `.env`, may satisfy a
configuration read at import.

## Which processes count as "every process consulting the registry"

The three roots that file names, and for its reasons: the process serving
the admin surface validates an activation against the registry, the worker
runs the automation pass against it, and the startup handler report reads
it to name the `active` automated steps this deployment cannot resolve. A
handler in one and not another is resolvable in one process and unknown in
the other — a step the admin can activate and the worker cannot run, or a
report answering for some other deployment.

## What is fixed, and what is INVENTED

Fixed by the delta: that the name is registered "whether that process
serves the admin surface or runs the automation pass". Fixed by
`tasks.md` 2.2 and 2.12: the handler name, and that `registrations.py` — the
one list every composition root imports — is what carries it into all of
them. The three root module paths are transcribed from
`tests/unit/test_registrations_across_processes.py` rather than invented.

INVENTED: nothing beyond the dump script's own shape, which is that file's
`_HANDLER_DUMP_SCRIPT` in the same form.

## Expected first-run state

Observed, not predicted (`uv run pytest
tests/unit/test_compliance_screen_registered_across_processes.py` before
any implementation existed) — **4 failed, 1 passed**:

- `test_the_screen_is_registered_in_every_process` fails on all four
  roots, each reporting a registry holding `listing.subcategory_advisor`
  alone. That is failure state 1 per `ai-toolkit:testing`, not state 2:
  the assertions executed and discriminated, because this file imports no
  module that does not exist yet.
- `test_no_root_resolves_the_screen_that_another_one_lacks` **passes**,
  and that is expected rather than an alarm to be resolved by
  strengthening it. It asserts that the roots *agree*, which they do while
  all four lack the handler equally. Its subject is the asymmetry a
  half-finished `registrations.py` edit produces, and no such asymmetry
  can exist before the edit is begun — so it is recorded in
  `test-manifest.md` as a consistency guard that carries no evidence about
  the absence, and the test above is what covers the scenario until the
  handler is registered. Do not read its green as coverage.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HANDLER_NAME = "strategy.compliance_screen"

WORKER_ROOT = "commerce_ops.worker"
HTTP_ROOT = "commerce_ops.main"
REPORT_ROOT = "commerce_ops.check_step_handlers"
DECLARED_ROOT = "commerce_ops.registrations"

EVERY_ROOT = (HTTP_ROOT, WORKER_ROOT, REPORT_ROOT, DECLARED_ROOT)

DUMP_PREFIX = "HANDLER-DUMP "

_HANDLER_DUMP_SCRIPT = """
import json

import {root}  # noqa: F401  -- imported for the registration side effect

from commerce_ops.launch.application import HANDLERS

print("{prefix}" + json.dumps(sorted(HANDLERS.names())))
"""


def _handler_names(root: str, tmp_path: Path) -> list[str]:
    """The step-handler names a fresh interpreter holds after importing
    `root` and nothing else."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _HANDLER_DUMP_SCRIPT.format(root=root, prefix=DUMP_PREFIX),
        ],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"dumping the step-handler registry after importing {root} in a "
        "fresh interpreter failed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith(DUMP_PREFIX)
    ]
    assert len(dumps) == 1, (
        f"expected exactly one handler dump from {root}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parsed: list[str] = json.loads(dumps[0][len(DUMP_PREFIX) :])
    return parsed


@pytest.mark.parametrize("root", EVERY_ROOT)
def test_the_screen_is_registered_in_every_process(root: str, tmp_path: Path) -> None:
    """Scenario: The handler is resolvable in every process consulting the
    registry.

    WHEN a process consults the handler registry
    THEN this screen's name is registered in it, whether that process
    serves the admin surface or runs the automation pass.

    SPECIFIED, named rather than counted. A non-emptiness check would pass
    in a deployment that registers only the sibling handler, which is the
    failure adding a handler to one root exists to catch. The declared list
    is included as a fourth root because it is what carries the import into
    the other three: a failure there says the handler is not in
    `registrations.py` at all, and a failure in one of the other three says
    that root does not reach the declared list.
    """
    names = _handler_names(root, tmp_path)

    assert HANDLER_NAME in names, (
        f"{root} does not register {HANDLER_NAME!r}. Every handler is "
        "reached through `registrations.py`, so either that import is "
        "missing, or the module was added to the import list and not to "
        f"`HANDLER_MODULES`.\n{root} registers: {names}"
    )


def test_no_root_resolves_the_screen_that_another_one_lacks(tmp_path: Path) -> None:
    """The same scenario, asserted as the asymmetry it exists to prevent.

    SPECIFIED. The parametrised test above fails once per root, which says
    which roots lack the handler but reads as four independent failures. A
    handler in one root and not another is a single, specific fault — a
    step the admin can activate and the worker cannot run, or the reverse —
    and this states it as one.

    **This passes on the unmodified tree, by construction.** Four roots
    that all lack the handler agree about it, so the assertion holds
    vacuously until one root gains it. That is the shape of the fault it
    guards, not a defect in the assertion: strengthening it into an
    absence check would duplicate the test above and lose the asymmetry
    check entirely. Recorded in `test-manifest.md` so that its green is
    not read as coverage of the scenario before the handler exists.
    """
    holders = {
        root: HANDLER_NAME in _handler_names(root, tmp_path) for root in EVERY_ROOT
    }

    assert len(set(holders.values())) == 1, (
        "the roots disagree about whether this deployment answers for "
        f"{HANDLER_NAME!r}: {holders}. Activation is validated against the "
        "registry in the process serving the admin surface and the pass "
        "runs against it in the worker, so a name in one and not the other "
        "makes a step activatable in a deployment that cannot resolve it."
    )
