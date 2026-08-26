"""Which read refuses a playbook that cannot hold a launch, against Postgres.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-playbook/spec.md`

Covers, from the ADDED requirement *A playbook that cannot hold a launch is
not served*:

- *A launch cannot be advanced by an unready playbook*
- *Authoring reads an unready playbook freely*
- *Readiness follows the set without ceremony*

And, from the MODIFIED requirement *An incoherent playbook is rejected
against each step's status*, the half of *A gate with no active blocking
step is rejected* that this level owns: "the rejection happens when that
playbook is asked for in order to hold a launch, naming the gate". Its
other half — "and not when it is loaded" — is asserted at the domain level
in `tests/unit/launch/domain/test_playbook_readiness.py`.

## Level

The repository, and nothing smaller. What these three scenarios fix is
**which read** refuses and which does not — `get()` against `load()`
(`design.md`, "The enforcement point is the serving read, not a
convention"). A double for either read would be asserting the double.

## This module writes to the step set, and restores it

There is no other way to reach a stored set that leaves a gate unheld: no
accepted write produces one from a set that is already ready — that is the
ratchet this change introduces — so the state is reachable only by writing
the set directly, which `proposal.md` names as the constraint the seed
change carries.

So each test here demotes one gate's blocking steps through the write
store, asserts, and restores the exact records it snapshotted, in a
`finally`. The module-scoped `restored_step_set` fixture snapshots and
restores again around the whole module, and the last test in the file
re-reads through `get()` so a failure to restore is loud rather than
inherited by the next file.

**It runs only against a database whose name marks it as a test database.**
`tasks.md` 6.2 directs the integration tier at an isolated
`commerce_ops_test` named in `.env.test`; without one, this module would be
rewriting the developer's working step set, and a mid-test failure would
leave it unready — which is exactly the state that stops launches from
starting. Where no such database is configured the module skips with a
message saying what to create. That skip is recorded in
`test-manifest.md` as a conditional coverage gap, not as coverage.

## What is fixed, and what is INVENTED

Fixed: `PlaybookRepository.get()` raises `PlaybookNotReadyError` when the
constructed playbook is not ready; `load()` is untouched (`tasks.md` 3.1).

INVENTED, and transcribed from
`tests/integration/launch/test_playbook_authoring_live.py` rather than
re-derived: the session helper, the write store's resolution, and the two
read call shapes. `PlaybookNotReadyError`'s attributes are probed.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so every test here fails on an
absent target — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed (against the
`DATABASE_URL` this checkout resolves, which is **not** an isolated test
database — see the skip above).
"""

from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
    InvalidPlaybookError,
    LaunchPlaybook,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driven import playbook_repository

pytestmark = pytest.mark.anyio

SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

# The gate this module demotes. `graduated` is the last in the sequence, so
# a launch that somehow read a stale set is furthest from being affected.
TARGET_GATE: Final = "graduated"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate — the convention
    `test_playbook_authoring_live.py` records."""


@pytest.fixture(autouse=True)
def _requires_an_isolated_database() -> None:
    """Refuse to rewrite a step set that is not a test database's.

    See the module docstring. The check is on the database *name* rather
    than on a bespoke flag, so it explains itself and matches what
    `tasks.md` 6.2 asks the implementer to create.
    """
    url = os.environ.get("DATABASE_URL", "")
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database.endswith("_test"):
        pytest.skip(
            "this module rewrites the stored step set and restores it, so it "
            "runs only against an isolated test database. Create "
            "`commerce_ops_test`, run `alembic upgrade head` against it, and "
            "name it as DATABASE_URL in `.env.test` (`tasks.md` 6.2). "
            f"Resolved database was {database!r}."
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
    """The write store — the single correction point, transcribed from
    `test_playbook_authoring_live.py`."""
    factory = (
        getattr(playbook_repository, "PlaybookStepStore", None)
        or playbook_repository.PlaybookRepository
    )
    return factory(session)


# ---------------------------------------------------------------------------
# The two reads
# ---------------------------------------------------------------------------


async def _get() -> LaunchPlaybook:
    """The serving read."""
    async with _session() as session:
        served = await _maybe_await(
            playbook_repository.PlaybookRepository(session).get(
                "any-version-read-through"
            )
        )
        assert isinstance(served, LaunchPlaybook)
        return served


async def _load() -> tuple[Any, int]:
    """The authoring read."""
    async with _session() as session:
        loaded = await _maybe_await(_store(session).load())
        return loaded  # type: ignore[no-any-return]


async def _save(records: Any, expected_version: int) -> None:
    async with _session() as session:
        await _maybe_await(
            _store(session).save(records, expected_version=expected_version)
        )


def _not_ready_error() -> type[Exception]:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    return error  # type: ignore[no-any-return]


def _named_gates(error: Exception) -> str:
    """Everything the refusal says, for a substring assertion.

    The message and the carried attributes alike — the requirement fixes
    that the refusal "names the gates", not through which of the two.
    """
    return str(error) + repr(getattr(error, "__dict__", {}))


# ---------------------------------------------------------------------------
# Reaching an unready stored set, and getting back
# ---------------------------------------------------------------------------


def _restatused(records: Any, gate: str, status: StepStatus) -> tuple[Any, ...]:
    """The same records with every blocking step on `gate` carrying
    `status`.

    Mutates the records it is handed, so every caller passes a set loaded
    afresh — `_load()` opens its own session and returns its own objects,
    so a snapshot taken by a separate `_load()` is untouched by this. That
    separation is load-bearing: restoring from a snapshot that shared these
    objects would write the demotion back.
    """
    changed = []
    for record in records:
        definition = record.definition
        if definition.gate == gate and definition.blocking:
            record.definition = _with_status(definition, status)
        changed.append(record)
    return tuple(changed)


def _with_status(definition: Any, status: StepStatus) -> Any:
    """A copy of `definition` carrying `status`.

    `StepDefinition` is a frozen dataclass everywhere the unit tier
    constructs one, so `dataclasses.replace` is the copy; the fallback
    exists only so a different shape fails with a readable message.
    """
    import dataclasses

    try:
        return dataclasses.replace(definition, status=status)
    except TypeError as exc:  # pragma: no cover - shape guard
        pytest.fail(
            f"could not produce a copy of {definition!r} carrying "
            f"status={status!r}: {exc}"
        )


@pytest.fixture(scope="module", autouse=True)
def restored_step_set(anyio_backend: str) -> Iterator[None]:
    """Snapshot the stored step set around the whole module and put it
    back, whatever happens inside."""
    import anyio

    snapshot: dict[str, Any] = {}

    async def _snapshot() -> None:
        records, version = await _load()
        snapshot["records"] = tuple(records)
        snapshot["version"] = version

    async def _restore() -> None:
        _, version = await _load()
        await _save(snapshot["records"], version)

    try:
        anyio.run(_snapshot)
    except Exception:  # noqa: BLE001 -- see below
        # Deliberately broad: this is the module-level safety net, not a
        # test. Anything that stops the snapshot being taken — an absent
        # step set, an unreachable database, a store whose shape differs —
        # must leave the module running its own per-test restores rather
        # than erroring in a fixture, where the failure would read as a
        # collection error rather than as the target being absent.
        yield
        return

    try:
        yield
    finally:
        anyio.run(_restore)


@asynccontextmanager
async def _unready_step_set(gate: str = TARGET_GATE) -> AsyncIterator[tuple[str, ...]]:
    """Demote `gate`'s blocking steps for the duration of the block, then
    restore the exact records that were there."""
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
# Requirement (ADDED): A playbook that cannot hold a launch is not served
# ---------------------------------------------------------------------------


async def test_a_launch_cannot_be_advanced_by_an_unready_playbook() -> None:
    """Scenario: A launch cannot be advanced by an unready playbook.

    WHEN a consumer asks for the playbook on a launch's behalf — to advance
    one, project one, or report on one — and one or more gates hold no
    active blocking step
    THEN the request is refused, and the refusal names those gates.

    Also the half of *A gate with no active blocking step is rejected* this
    level owns: "the rejection happens when that playbook is asked for in
    order to hold a launch, naming the gate".

    `get()` is that read — `design.md` calls it "a read taken on a launch's
    behalf: advancing one, projecting one, or reporting on one", and the
    four remaining callers all take it.
    """
    not_ready = _not_ready_error()

    async with _unready_step_set() as unheld:
        with pytest.raises(not_ready) as caught:
            await _get()

    # SPECIFIED: the refusal names those gates.
    named = _named_gates(caught.value)
    for gate in unheld:
        assert gate in named, (
            f"the refusal does not name the unheld gate {gate!r}: {named!r}"
        )
    # SPECIFIED (*Not ready is distinguishable from incoherent*): not the
    # condition an incoherent set reports.
    assert not isinstance(caught.value, InvalidPlaybookError)


async def test_authoring_reads_an_unready_playbook_freely() -> None:
    """Scenario: Authoring reads an unready playbook freely.

    WHEN the authoring surface reads a step set that leaves gates unheld
    THEN the read succeeds and every authored step is listed, whatever its
    status.

    The same stored state as the test above, read the other way — which is
    what makes the pair a statement about *which read* enforces readiness
    rather than about the set.
    """
    async with _unready_step_set():
        # No `pytest.raises`: not raising is the assertion.
        records, _ = await _load()

        listed = {record.definition.identifier for record in records}
        statuses = {record.definition.status for record in records}

    assert listed, "the authoring read returned no steps at all"
    # SPECIFIED: every authored step, whatever its status — the demoted
    # blockers are drafts now, and must still be listed.
    assert StepStatus.DRAFT in statuses, (
        "the authoring read did not list the demoted steps, so a set under "
        "construction is not visible to whoever is building it"
    )


async def test_readiness_follows_the_set_without_ceremony() -> None:
    """Scenario: Readiness follows the set without ceremony.

    WHEN the last gate holding no active blocking step gains one through an
    ordinary authoring write
    THEN the next serving read succeeds, with no further action.

    "With no further action" is what the assertion is really about: nothing
    is republished, no version is bumped by hand, no cache is invalidated.
    The write here is the ordinary status change back to `active`, and the
    very next `get()` is expected to succeed.
    """
    not_ready = _not_ready_error()
    snapshot, _ = await _load()
    snapshot = tuple(snapshot)

    try:
        fresh, version = await _load()
        await _save(_restatused(list(fresh), TARGET_GATE, StepStatus.DRAFT), version)

        with pytest.raises(not_ready):
            await _get()

        # The ordinary authoring write that puts the blocker back. Written
        # through the store rather than the use case because the use case's
        # own acceptance of this write is the ratchet's, covered at the
        # unit tier; what is under test here is the read that follows.
        current, current_version = await _load()
        await _save(
            _restatused(list(current), TARGET_GATE, StepStatus.ACTIVE),
            current_version,
        )

        # SPECIFIED: the next serving read succeeds, with no further action
        # — no republish, no manual version bump, no cache to invalidate.
        served = await _get()
        assert isinstance(served, LaunchPlaybook)
    finally:
        _, version_now = await _load()
        await _save(snapshot, version_now)


async def test_the_step_set_is_left_exactly_as_it_was_found() -> None:
    """Guard, not a scenario.

    Every test above rewrites the stored step set and restores it. This
    asserts the restoration held, so a failure to restore is reported here
    — loudly, in this file — rather than inherited by the next file in the
    tier as an unexplained refusal.

    Ordering matters: pytest runs a module's tests in definition order, so
    this runs after the three above.
    """
    served = await _get()

    unheld = [
        gate
        for gate in SPECIFIED_GATE_ORDER
        if not any(
            step.blocking and step.status is StepStatus.ACTIVE
            for step in served.steps_for_gate(gate)
        )
    ]
    assert unheld == [], (
        "the stored step set was left unready by this module; restore it "
        f"before running anything else. Gates left unheld: {unheld}"
    )
