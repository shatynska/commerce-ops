"""The pass stands down over a stored step set that has not become ready.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers one scenario, from the ADDED requirement *The pass stands down
while the playbook cannot hold a launch*:

    #### Scenario: An unready playbook stands the pass down without
    failing it
    - **WHEN** the pass runs while a gate holds no active blocking step
    - **THEN** no launch is advanced and no ask is posted
    - **AND** the run is recorded as succeeded, with the stand-down and
      the unheld gates logged

The same scenario is also driven at the unit tier, against a substituted
playbook read, in
`tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`.
Both are wanted, and `tasks.md` 7.9 says why this one exists: the state
cannot be produced on a working deployment by hand, because
`playbook-authoring`'s ratchet refuses any write that would make a *ready*
set unready. Verifying the stand-down against a real serving read is
therefore this tier's job, not a manual check's.

See `test-manifest.md` at the change root for the full accounting.

## Level

The pass body over the real `PlaybookRepository`, against Postgres. What
is under test is that the *serving read* refuses and the pass treats that
refusal as a stand-down — and a substituted playbook read cannot establish
the first half. Everything the pass would do *after* readiness is
substituted, since none of it is the subject here and all of it would
otherwise reach Slack.

## This module writes to the step set, and restores it

Transcribed from `tests/integration/launch/test_playbook_readiness_live.py`,
which established the pattern and the reason: no accepted write produces
an unheld gate from a set that is already ready, so the state is reachable
only by writing the set directly. Each test demotes one gate's blocking
steps, asserts, and restores the exact records it snapshotted in a
`finally`; and the module refuses to run at all against a database whose
name does not mark it as a test database.

Where no isolated test database is configured, this module skips. That
skip is recorded in `test-manifest.md` as a conditional coverage gap, not
as coverage.

## What is fixed, and what is INVENTED

Fixed: that readiness is read through `PlaybookRepository.get()`, which
raises `PlaybookNotReadyError` (`launch-playbook`, unchanged by this
change); that the pass determines readiness once, above the walk, and
records a stand-down as a succeeded run with the unheld gates logged
(`tasks.md` 4.2).

INVENTED: the pass module's entry point and collaborator names,
transcribed from
`tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`,
which is the single correction point for all of them.

## Expected first-run state

`gate_progression_job.py` does not exist (`tasks.md` 4.1), so this test is
expected to fail on an absent target where a database is configured, and
to skip where one is not.

Baseline recorded before this test was written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/integration` — 3
passed, 112 skipped (no `DATABASE_URL` is configured here, so this tier
did not in fact run).
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.launch.infrastructure.driven import playbook_repository

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_progression_job"

#: The gate this module demotes. `graduated` is last in the sequence, so a
#: launch that somehow read a stale set is furthest from being affected —
#: the choice `test_playbook_readiness_live.py` records.
TARGET_GATE: Final = "graduated"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate."""


@pytest.fixture(autouse=True)
def _requires_an_isolated_database() -> None:
    url = os.environ.get("DATABASE_URL", "")
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database.endswith("_test"):
        pytest.skip(
            "this module rewrites the stored step set and restores it, so it "
            "runs only against an isolated test database. Create "
            "`commerce_ops_test`, run `alembic upgrade head` against it, and "
            "name it as DATABASE_URL in `.env.test`. Resolved database was "
            f"{database!r}."
        )


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        value = await value
    return value


def _store(session: AsyncSession) -> Any:
    """The write store — transcribed from
    `test_playbook_readiness_live.py`, which is the correction point."""
    factory = (
        getattr(playbook_repository, "PlaybookStepStore", None)
        or playbook_repository.PlaybookRepository
    )
    return factory(session)


async def _load() -> tuple[Any, int]:
    async with _session() as session:
        return await _maybe_await(_store(session).load())  # type: ignore[no-any-return]


async def _save(records: Any, expected_version: int) -> None:
    async with _session() as session:
        await _maybe_await(
            _store(session).save(records, expected_version=expected_version)
        )


def _restatused(records: Any, gate: str, status: Any) -> tuple[Any, ...]:
    changed = []
    for record in records:
        definition = record.definition
        if definition.gate == gate and definition.blocking:
            record.definition = dataclasses.replace(definition, status=status)
        changed.append(record)
    return tuple(changed)


@asynccontextmanager
async def _unready_step_set(gate: str = TARGET_GATE) -> AsyncIterator[tuple[str, ...]]:
    """Demote `gate`'s blocking steps for the duration of the block, then
    restore the exact records that were there.

    The snapshot is loaded in its own session, separately from the records
    that are mutated, so restoring cannot write the demotion back — the
    separation `test_playbook_readiness_live.py` records as load-bearing.
    """
    from commerce_ops.launch.domain.launch_playbook import StepStatus

    original, _ = await _load()
    original = tuple(original)
    fresh, version = await _load()
    await _save(_restatused(list(fresh), gate, StepStatus.DRAFT), version)
    try:
        yield (gate,)
    finally:
        _, current = await _load()
        await _save(original, current)


# ---------------------------------------------------------------------------
# Reaching the pass — transcribed from test_gate_progression_pass.py
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_gate_progression_pass",
    "run_gate_progression",
    "advance_launch_gates",
    "progress_gates",
    "run_pass",
)
_PROGRESS_NAMES: Final = ("progress_launch", "progress", "advance_launch")
_ASK_NAMES: Final = (
    "post_gate_ask",
    "deliver_gate_ask",
    "ask_for_confirmation",
    "request_confirmation",
    "post_ask",
    "deliver",
)


def _module() -> ModuleType:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` 4.1 creates "
            "it. This is the absent-target state, not a defect in this file."
        )


def _entry(module: ModuleType) -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {module.__name__} under any of "
        f"{_ENTRY_NAMES} — correct this file's probe to the implemented name"
    )


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return None


def _substitute(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    names: tuple[str, ...],
    value: Any,
) -> list[str]:
    placed = []
    for name in names:
        if not hasattr(module, name):
            continue
        monkeypatch.setattr(module, name, value)
        placed.append(name)
    return placed


# ---------------------------------------------------------------------------
# Requirement: The pass stands down while the playbook cannot hold a launch
# ---------------------------------------------------------------------------


async def test_an_unready_stored_step_set_stands_the_pass_down(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: An unready playbook stands the pass down without failing it.

    WHEN the pass runs while a gate holds no active blocking step
    THEN no launch is advanced and no ask is posted
    AND the run is recorded as succeeded, with the stand-down and the
    unheld gates logged.

    Driven against the real serving read, over a stored step set demoted
    for the duration of this test. Everything the pass does *after*
    readiness is substituted, so that "no launch is advanced" and "no ask
    is posted" are observable without reaching Slack — and so that a pass
    which did not stand down would be caught by those substitutes having
    been called, rather than by a side effect nobody watches.
    """
    module = _module()
    # ADDED: the pass reaches its database through the *global* `session()`,
    # which builds one engine and binds it to whichever event loop first
    # touches it. Driven from this tier that engine outlives the module and
    # breaks a later test with "attached to a different loop" — the hazard
    # `docs/deferred-work.md` records, and `test_clickup_sync_job_containment_live.py`
    # avoids the same way. This module already opens and disposes its own
    # engine per call, so the pass is pointed at that instead.
    for seam in ("session", "transaction"):
        if hasattr(module, seam):
            monkeypatch.setattr(module, seam, _session)

    progress = _Recorder()
    ask = _Recorder()
    placed_progress = _substitute(module, monkeypatch, _PROGRESS_NAMES, progress)
    placed_ask = _substitute(module, monkeypatch, _ASK_NAMES, ask)
    parameters = set(inspect.signature(_entry(module)).parameters)
    assert placed_progress or (parameters & set(_PROGRESS_NAMES)), (
        "the pass exposes no cascade collaborator under any of "
        f"{_PROGRESS_NAMES}; correct this file's probe. Its parameters are "
        f"{sorted(parameters)}"
    )
    assert placed_ask or (parameters & set(_ASK_NAMES)), (
        f"the pass exposes no ask collaborator under any of {_ASK_NAMES}; "
        f"correct this file's probe. Its parameters are {sorted(parameters)}"
    )

    async with _unready_step_set() as unheld:
        entry = _entry(module)
        pool: dict[str, Any] = {
            "progress_launch": progress,
            "progress": progress,
            "post_gate_ask": ask,
            "deliver": ask,
        }
        with caplog.at_level(logging.DEBUG):
            # SPECIFIED: the run is recorded as succeeded — returning
            # normally is the assertion.
            await entry(**{k: v for k, v in pool.items() if k in parameters})

    # SPECIFIED: no launch is advanced.
    assert progress.calls == [], (
        f"a launch was advanced against an unready served step set: {progress.calls!r}"
    )
    # SPECIFIED: no ask is posted.
    assert ask.calls == [], (
        f"an ask was posted against an unready served step set: {ask.calls!r}"
    )
    # SPECIFIED: the stand-down and the unheld gates are logged.
    logged = " ".join(record.getMessage() for record in caplog.records)
    for gate in unheld:
        assert gate in logged, (
            f"the stand-down did not log the unheld gate {gate!r}; what was "
            f"logged was: {logged!r}"
        )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED here, recorded rather than omitted
#
# - *A ready playbook is served normally*, the requirement's other
#   scenario. It needs no real database to be observed and is at the unit
#   tier; driving it here would only re-assert the seeded set's readiness,
#   which `test_playbook_readiness_live.py` already owns.
# - Whether the run is recorded as succeeded in `scheduled-jobs`' own
#   store. That is another capability's record; the reading this
#   repository uses for "recorded as succeeded" is that the job body
#   returns, which is what is asserted above.
# ---------------------------------------------------------------------------
