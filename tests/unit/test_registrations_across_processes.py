"""Both composition roots hold the same registrations.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Each Piece Of Recurring Work Declares Its Schedule And Tolerance In One
  Place" / Scenario: Every process holds the same registration

See `test-manifest.md` at the change root for the full accounting.

## Why a subprocess, and why an in-process version would prove nothing

design.md is explicit, and tasks.md 1.4 repeats it: the registry is a
module-global in `shared`, so within one pytest process importing
`commerce_ops.worker` and importing `commerce_ops.main` read *the same
object*. An in-process comparison of "the registry after each root" is
therefore tautological -- it holds even when `main.py` never calls
`register_all()` at all, which is precisely the divergence the scenario
exists to detect. Each root is run in a fresh interpreter here and the
serialized identifier/tolerance pairs are compared, following the
subprocess pattern `tests/unit/test_startup_without_configuration.py`
already uses for process-global effects.

The environment handed to each subprocess is built from scratch rather
than pruned, and the working directory is `tmp_path`, for the same reason
that file gives: nothing on the developer's machine, and no
repository-local `.env`, may satisfy a configuration read at import. That
also makes the third test below a genuine check of tasks.md 1.4a -- that
`register_all()` and everything it pulls into `main.py`'s import graph
read no configuration at import time.

## What is invented

The dumping script's own shape, and nothing else.
`commerce_ops.registrations.register_all` is fixed by tasks.md 1.3;
`commerce_ops.worker` and `commerce_ops.main` are the two composition
roots the change names. The registry accessor is the same single
correction point recorded in
`tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py`
-- `REGISTRY_MODULE` / `REGISTRY_ACCESSOR` below.

That importing a root is what populates its registry is an assumption:
`worker.py` today registers job definitions by importing them at module
import, and `main.py` builds its `app` at import, so both roots are read
here by import alone. A `register_all()` deferred into `worker.main()`
would fail the first test below rather than the last -- the message says
so.

At the time this pass was written `commerce_ops.registrations` does not
exist, so every test here is expected to fail on an absent target until
tasks 1.3 and 1.3a land.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REGISTRY_MODULE = "commerce_ops.shared.infrastructure.driven.recurring_work"
REGISTRY_ACCESSOR = "registered_work"

WORKER_ROOT = "commerce_ops.worker"
HTTP_ROOT = "commerce_ops.main"
REPORT_ROOT = "commerce_ops.check_step_handlers"
DECLARED_ROOT = "commerce_ops.registrations"

# Every variable `runtime-configuration`'s empty-environment guarantee
# covers, transcribed from `tests/unit/test_startup_without_configuration.py`
# rather than imported, for the same reason that file transcribes it: this
# file's subject is the composition roots, not the settings declaration.
DECLARED_ENV_VARS = (
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "OMNI_AGENT_SLACK_SIGNING_SECRET",
    "OMNI_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_SLACK_BOT_TOKEN",
    "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
    "PRODUCT_AGENT_SLACK_SIGNING_SECRET",
    "CLICKUP_API_TOKEN",
    "LOG_LEVEL",
    "POSTGRES_PASSWORD",
    "IMAGE_TAG",
)

_DUMP_SCRIPT = """
import json
import datetime

import {root}  # noqa: F401  -- importing a composition root registers its work

from {registry_module} import {accessor}


def _entries(declared):
    if hasattr(declared, "values"):
        return [
            (key, entry) for key, entry in declared.items()
        ]
    return [(None, entry) for entry in declared]


def _identifier(key, entry):
    for attribute in ("identifier", "id", "task_name", "name"):
        value = getattr(entry, attribute, None)
        if value is not None:
            return str(value)
    return str(key)


def _tolerance_seconds(entry):
    for attribute in ("tolerance", "tolerance_seconds"):
        value = getattr(entry, attribute, None)
        if isinstance(value, datetime.timedelta):
            return value.total_seconds()
        if isinstance(value, (int, float)):
            return float(value)
    return None


pairs = sorted(
    (_identifier(key, entry), _tolerance_seconds(entry))
    for key, entry in _entries({accessor}())
)
print("REGISTRY-DUMP " + json.dumps(pairs))
"""


def _dump_registry(root: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = _DUMP_SCRIPT.format(
        root=root, registry_module=REGISTRY_MODULE, accessor=REGISTRY_ACCESSOR
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _registry_pairs(root: str, tmp_path: Path) -> list[list[object]]:
    result = _dump_registry(root, tmp_path)
    assert result.returncode == 0, (
        f"dumping the registry after importing {root} in a fresh "
        "interpreter failed. If it failed because the registry is empty or "
        "absent, note that this test reads each root by import alone: a "
        "register_all() deferred into a function the process calls later is "
        "not visible to a process that only imports the root.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    dumps = [
        line for line in result.stdout.splitlines() if line.startswith("REGISTRY-DUMP ")
    ]
    assert len(dumps) == 1, (
        f"expected exactly one registry dump from {root}, got {dumps!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    parsed: list[list[object]] = json.loads(dumps[0][len("REGISTRY-DUMP ") :])
    return parsed


def test_both_composition_roots_hold_the_same_registration(tmp_path: Path) -> None:
    """Scenario: Every process holds the same registration.

    WHEN the registrations visible to the process running scheduled work
    and to the process serving HTTP requests are compared
    THEN they SHALL contain the same pieces of work with the same
    tolerances
    AND neither SHALL be missing a piece of work the other holds.

    SPECIFIED. Compared as serialized identifier/tolerance pairs from two
    fresh interpreters, which is the only comparison that can fail -- see
    the module docstring.
    """
    worker_pairs = _registry_pairs(WORKER_ROOT, tmp_path)
    http_pairs = _registry_pairs(HTTP_ROOT, tmp_path)

    assert worker_pairs == http_pairs, (
        "the two composition roots hold different registrations.\n"
        f"{WORKER_ROOT}: {worker_pairs}\n"
        f"{HTTP_ROOT}: {http_pairs}\n"
        "One list, not two: tasks.md 1.3 puts every job-module import in "
        "registrations.register_all(), which both roots call."
    )


def test_each_root_registers_work_at_all(tmp_path: Path) -> None:
    """DERIVED guard on the test above, not itself a `#### Scenario:`.

    Two empty registries are equal. Without this, the scenario's assertion
    would pass in exactly the deployment it exists to prevent -- one where
    `register_all()` is never reached in either process, the freshness
    endpoint enumerates nothing, and the deployment reports healthy while
    nothing runs.
    """
    for root in (WORKER_ROOT, HTTP_ROOT):
        pairs = _registry_pairs(root, tmp_path)
        assert pairs, (
            f"importing {root} registered no recurring work at all, so the "
            "freshness endpoint would enumerate nothing and report healthy "
            "forever"
        )
        undeclared = [pair[0] for pair in pairs if pair[1] is None]
        assert undeclared == [], (
            f"{root} registered work with no readable tolerance: {undeclared}"
        )


def test_registering_reads_no_configuration_at_import(tmp_path: Path) -> None:
    """SPECIFIED by tasks.md 1.4a, guarding `runtime-configuration`'s
    "Importing And Starting The Application Do Not Require Configuration To
    Be Present" against this change's own additions.

    Not itself a `#### Scenario:` block of this change's delta spec: it is
    a published requirement of another capability that `register_all()`
    pulling the job modules -- and this change's route module -- into
    `main.py`'s import graph could break. Recorded here because the
    subprocess machinery is already present, and because a failure would
    otherwise surface as an unexplained failure of the two tests above.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import commerce_ops.registrations as r; r.register_all()",
        ],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.registrations and calling register_all() "
        "with every declared configuration variable absent "
        f"({', '.join(DECLARED_ENV_VARS)}) failed; configuration must be "
        "read no earlier than the point at which it is used.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# `introduce-automation-runtime` tasks.md 8.6a: the same guard, for handlers
# ---------------------------------------------------------------------------

_HANDLER_DUMP_SCRIPT = """
import json

import {root}  # noqa: F401  -- imported for the registration side effect

from commerce_ops.launch.application import HANDLERS

print("HANDLER-DUMP " + json.dumps(sorted(HANDLERS.names())))
"""


def _handler_names(root: str, tmp_path: Path) -> list[str]:
    """The step-handler names a fresh interpreter holds after importing
    `root` and nothing else."""
    script = _HANDLER_DUMP_SCRIPT.format(root=root)
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


def test_both_composition_roots_resolve_the_same_handler_names(
    tmp_path: Path,
) -> None:
    """`introduce-automation-runtime` tasks.md 8.6a.

    Step handlers register by being imported, exactly as jobs do, and
    carry the same asymmetric failure this file already guards for jobs —
    but a worse one, because the two processes ask *different* questions
    of the registry. `playbook-authoring` validates an activation against
    it in the process serving the admin surface; the automation pass needs
    the handler in the worker. A handler imported into only one is
    resolvable in one process and unknown in the other — a step the admin
    can activate and the worker cannot run, or the reverse: a deploy that
    passes every other check and then cannot complete its own migration.

    The startup report is no help with that asymmetry, and this docstring
    used to claim it was, saying such a handler left `check_step_handlers`
    "reporting it registered". It never did. Before
    `let-the-handler-report-see-handlers` the report held an empty
    registry and answered the same whatever any root imported; since that
    change it registers by the same `register_all()` the other two roots
    call, so it agrees with both and can no more see them diverge from
    each other than they can. That divergence is this test's job, and only
    this test's.
    """
    api = _handler_names("commerce_ops.main", tmp_path)
    worker = _handler_names("commerce_ops.worker", tmp_path)

    assert api == worker, (
        "the two composition roots resolve different step-handler names. "
        "The process serving the admin surface validates activation "
        "against this registry and the worker runs the pass against it, so "
        "a name in one and not the other makes a step activatable in a "
        "deployment that cannot resolve it, or resolvable in one that "
        f"refuses to activate it.\napi: {api}\nworker: {worker}"
    )


def test_each_root_registers_at_least_one_handler(tmp_path: Path) -> None:
    """Equality above is satisfied by two empty registries.

    The same reason this file already asserts each root registers work at
    all: an import that quietly stopped happening would leave both roots
    agreeing on nothing.
    """
    for root in ("commerce_ops.main", "commerce_ops.worker"):
        assert _handler_names(root, tmp_path), (
            f"{root} registers no step handler at all; an automated step "
            "would name a handler nothing in this deployment answers to"
        )


def test_the_reporting_process_holds_the_deployments_own_registrations(
    tmp_path: Path,
) -> None:
    """`let-the-handler-report-see-handlers` delta spec, `launch-playbook`,
    *A step carries the brief and the handler its automation needs* /
    Scenario: The reporting process holds the deployment's own
    registrations.

    Relocated here from the change's own test file by `tasks.md` 1.3,
    which asks for the reporting process as a **third root** beside the
    two composition roots above rather than as a case apart from them.
    The three other scenarios stay in
    `tests/unit/test_startup_handler_report_holds_the_registry.py`: they
    are about what the report says, and this one is about whether the
    process making it shares a registry with the processes it reports on
    — which is this file's subject.

    Equality against the declared set and against both composition roots,
    never non-emptiness. An empty registry answers identically for a
    deployment that registers a step's handler and one that does not, and
    a non-emptiness check is how that survived a test tier in the first
    place.
    """
    reporting = _handler_names(REPORT_ROOT, tmp_path)
    declared = _handler_names(DECLARED_ROOT, tmp_path)
    api = _handler_names(HTTP_ROOT, tmp_path)
    worker = _handler_names(WORKER_ROOT, tmp_path)

    assert reporting == declared, (
        f"the process that makes the startup report ({REPORT_ROOT}) does "
        "not hold every handler this deployment answers for. Importing a "
        "handler module is what registers it, so a process reporting on "
        "the registry has to be one that populates it.\n"
        f"{REPORT_ROOT}: {reporting}\n{DECLARED_ROOT}: {declared}"
    )
    assert reporting == api == worker, (
        f"{REPORT_ROOT} resolves different step-handler names than the "
        "processes it reports on. The start chain runs it to name the "
        "`active` automated steps this deployment cannot resolve, so a "
        "registry it does not share with them makes that report answer "
        "for some other deployment: identical output whether or not this "
        "one registers a step's handler, and so evidence about neither.\n"
        f"{REPORT_ROOT}: {reporting}\n{HTTP_ROOT}: {api}\n"
        f"{WORKER_ROOT}: {worker}"
    )
