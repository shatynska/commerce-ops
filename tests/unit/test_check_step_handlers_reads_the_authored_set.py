"""The startup handler report survives a playbook that is not ready.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-playbook/spec.md`

Covers the boundary the ADDED requirement *A playbook that cannot hold a
launch is not served* draws, applied to the one consumer that is not
serving a launch:

> The read that serves the authoring surface SHALL NOT be refused for that
> reason, so a set under construction stays visible and editable
> throughout.

and the obligation the live requirement *A step carries the brief and the
handler its automation needs* already carries:

> A deployment whose registry no longer answers for an `active` step's
> handler SHALL instead be reported at startup, where a deployment fault
> belongs.

Those two meet here. `design.md` is explicit that this consumer "should
never have been a `get()` caller": putting readiness on its read "would
suppress the startup report that `launch-playbook` requires, in exactly the
state this change makes reachable — an `active` `automated` step can exist
in a not-ready set, since activation checks the brief, the handler and the
registry but never the gate holdings."

## Level

The startup check as a module, in-process, over a substituted read. What is
under test is *which read it takes* and that the report still runs; nothing
below the module can observe the first, and the report's own content is
`report_unregistered_handlers`' and is covered in
`tests/unit/launch/application/test_step_activation.py`.

## What is fixed, and what is INVENTED

Fixed: that `check_step_handlers` moves to the authoring read
(`load()` + `authored_definitions`) and still reports at startup when the
playbook is not ready (`tasks.md` 4.7); that the module is
`commerce_ops.check_step_handlers`.

INVENTED, each with a correction point below:

- The module's entry point name — `_entry_point()` probes `_ENTRY_NAMES`.
- The read collaborator's name on the module — the fixture installs over
  `PlaybookRepository`, the spelling every other consumer uses, and fails
  loudly where the module exposes no such attribute.
- Which reader method the check calls. The double answers **both** `load()`
  and `get()`, recording each, and `get()` additionally raises — so a check
  still taking the serving read fails here with a message that says so
  rather than passing against an unpatched real one.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so every test here fails on an
absent target — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, ClassVar, Final

import pytest

from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    StepDefinition,
    StepKind,
    StepStatus,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step

CHECK_MODULE: Final = "commerce_ops.check_step_handlers"

UNHELD_GATE: Final = "graduated"

UNREGISTERED_HANDLER: Final = "price.a_handler_no_deploy_answers_for"
UNREGISTERED_STEP_ID: Final = "price.buy-box-check"

_ENTRY_NAMES: Final = ("main", "check", "run", "check_step_handlers")


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "timing_anchor": OffsetAnchor(days=0),
            "blocking": True,
            "kind": StepKind.AUTOMATED,
            "handler": "fixture.holding_check",
            **overrides,
        }
    )


def _unready_steps() -> tuple[StepDefinition, ...]:
    """A set leaving `graduated` unheld that nonetheless carries an
    `active` `automated` step whose handler is unregistered.

    That combination is exactly what `design.md` says is newly reachable:
    activation checks the brief, the handler and the registry, but never
    the gate holdings — so a set can be unready and still owe a startup
    report.
    """
    return (
        *(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                status=(StepStatus.DRAFT if gate == UNHELD_GATE else StepStatus.ACTIVE),
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
        _step(
            identifier=UNREGISTERED_STEP_ID,
            name="Check the Buy Box share",
            gate="live",
            blocking=False,
            status=StepStatus.ACTIVE,
            handler=UNREGISTERED_HANDLER,
        ),
    )


def _unready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=_unready_steps())


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": (UNHELD_GATE,)}),
        ((), {"playbook": playbook, "unheld_gates": (UNHELD_GATE,)}),
        (((UNHELD_GATE,), playbook), {}),
        ((playbook, (UNHELD_GATE,)), {}),
    )
    for args, kwargs in attempts:
        try:
            return error(*args, **kwargs)  # type: ignore[no-any-return]
        except TypeError:
            continue
    pytest.fail("could not construct PlaybookNotReadyError under any probed signature")


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _Record:
    def __init__(self, definition: StepDefinition, display_order: int = 10) -> None:
        self.definition = definition
        self.display_order = display_order


class _ReadRecorder:
    """A repository double that answers the authoring read and refuses the
    serving one.

    Both are offered deliberately: a check still calling `get()` gets the
    refusal this change introduces, and fails here with a message naming
    the reason — rather than passing because the attribute happened not to
    exist.
    """

    calls: ClassVar[list[str]] = []

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def load(self) -> tuple[tuple[_Record, ...], int]:
        _ReadRecorder.calls.append("load")
        return tuple(_Record(step) for step in _unready_steps()), 41

    async def get(self, version: str = "") -> LaunchPlaybook:
        _ReadRecorder.calls.append("get")
        raise _build_not_ready(_unready_playbook())


class _RecordingReport:
    """Stands in for `report_unregistered_handlers`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append({"args": args, "kwargs": kwargs})
        return (
            (
                f"{UNREGISTERED_STEP_ID} names handler {UNREGISTERED_HANDLER}, "
                "which this deployment does not register"
            ),
        )


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


@pytest.fixture()
def check_module() -> Any:
    try:
        return importlib.import_module(CHECK_MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{CHECK_MODULE} does not exist. Underlying error: {exc}")


@pytest.fixture(autouse=True)
def sessionless(check_module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_module, "session", _fake_session, raising=False)
    monkeypatch.setattr(check_module, "transaction", _fake_session, raising=False)


@pytest.fixture()
def reads(check_module: Any, monkeypatch: pytest.MonkeyPatch) -> type[_ReadRecorder]:
    assert hasattr(check_module, "PlaybookRepository"), (
        f"{CHECK_MODULE} exposes no `PlaybookRepository` to substitute, so "
        "this file cannot tell which read the startup check takes"
    )
    _ReadRecorder.calls = []
    monkeypatch.setattr(check_module, "PlaybookRepository", _ReadRecorder)
    return _ReadRecorder


@pytest.fixture()
def report(check_module: Any, monkeypatch: pytest.MonkeyPatch) -> _RecordingReport:
    fake = _RecordingReport()
    installed = [
        name
        for name in ("report_unregistered_handlers", "report_missing_handlers")
        if hasattr(check_module, name)
    ]
    assert installed, (
        f"{CHECK_MODULE} names no unregistered-handler report to substitute"
    )
    for name in installed:
        monkeypatch.setattr(check_module, name, fake)
    return fake


def _run_check(check_module: Any) -> Any:
    """Invoke the startup check the way the container start chain does.

    Synchronous on purpose: the entry point drives its own event loop
    (`asyncio.run`), so an async test here fails with "asyncio.run() cannot
    be called from a running event loop" — a defect in the test, not in the
    check. Where the entry point is instead a coroutine function, its
    coroutine is run here.
    """
    for name in _ENTRY_NAMES:
        entry = getattr(check_module, name, None)
        if callable(entry):
            result = entry()
            if inspect.isawaitable(result):
                result = asyncio.run(result)  # type: ignore[arg-type]
            return result
    pytest.fail(f"{CHECK_MODULE} exposes no entry point under any of {_ENTRY_NAMES}")


# ---------------------------------------------------------------------------
# The startup report against a not-ready playbook
# ---------------------------------------------------------------------------


def test_the_startup_check_reports_while_the_playbook_is_not_ready(
    check_module: Any, reads: type[_ReadRecorder], report: _RecordingReport
) -> None:
    """`launch-playbook`, *A step carries the brief and the handler its
    automation needs*: "A deployment whose registry no longer answers for
    an `active` step's handler SHALL instead be reported at startup."

    Held against the state this change makes reachable — a set that leaves
    a gate unheld. `design.md`: putting readiness on this read "would
    suppress the startup report that `launch-playbook` requires, in exactly
    the state this change makes reachable".
    """
    _run_check(check_module)

    assert report.calls, (
        "the startup handler report did not run while the playbook was not "
        "ready, so a deployment fault goes unreported in exactly the state "
        "this change introduces"
    )


def test_the_startup_check_takes_the_authoring_read_not_the_serving_one(
    check_module: Any, reads: type[_ReadRecorder], report: _RecordingReport
) -> None:
    """`tasks.md` 4.7 / `design.md`: "It moves to the authoring read, which
    is what it always wanted, and leaves the serving-read caller set at
    four."

    DERIVED from the artifacts rather than from a `#### Scenario:` — the
    spec fixes only that the authoring read is not refused, not which
    consumer takes it. Recorded as its own test because the previous one is
    satisfiable by a check that catches the refusal and reports anyway,
    which would leave the serving-read caller set at five and the
    design's boundary claim untrue.
    """
    _run_check(check_module)

    assert "get" not in reads.calls, (
        "the startup check still takes the serving read; it wants the "
        "authored set, and the serving read refuses a playbook that is not "
        f"ready. Reads taken: {reads.calls}"
    )
    assert "load" in reads.calls, (
        f"the startup check took no authoring read at all: {reads.calls}"
    )
