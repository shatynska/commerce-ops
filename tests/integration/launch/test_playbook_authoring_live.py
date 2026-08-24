"""Authored writes reaching the live served playbook, against real Postgres.

Derived strictly from the delta specs:
`openspec/changes/move-playbook-steps-to-postgres/specs/playbook-authoring/spec.md`
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-playbook/spec.md`

Covers the serving halves that
`tests/unit/launch/application/test_playbook_authoring.py` cannot observe
through a fake store:

- *A created step joins the served set* — "the next read of the playbook
  serves it".
- *An edit is served on the next read*.
- *A retired step leaves the served set* / *An un-retired step rejoins
  the served set* — the adapter excluding and re-including the step.
- *An authored change changes the served version identifier* (MODIFIED
  requirement *Playbooks are versioned*).
- *An authored change reaches a launch already in flight* — together with
  the audit-stamp half of *A launch records the version it started
  under*: a read made with a stale version stamp still serves the
  current step set, because no read path selects among stored
  definitions by version.

## Invented shapes (single correction points, recorded in the manifest)

- The read adapter: `PlaybookRepository(session)` with the port's
  `get(version) -> LaunchPlaybook`, as `test_playbook_seed.py` in this
  directory records — `_served()` / `_get()` below are the correction
  points.
- The write store the use cases take as `steps=`: no artifact names it.
  `_store()` below resolves it from the same
  `launch/infrastructure/driven/playbook_repository` module, accepting
  either a dedicated `PlaybookStepStore` or the repository class itself
  doubling as the store.
- The use-case call shapes: as
  `tests/unit/launch/application/test_playbook_authoring.py` records
  (`create_step(steps=, principal=, <authorable fields>)`, etc.), each
  committing its own work — the precedent
  `test_launch_repository.py` records for repository methods.

## Test-database lifecycle

Same convention as the rest of this directory: `alembic upgrade head`
assumed applied (schema + seed), a skip when `DATABASE_URL` is unset, no
truncate fixture. Writes are confined to steps these tests create in the
`mg.*` namespace, with unique descriptions per run; seeded `lp.*` rows
are never updated or retired, preserving `test_playbook_seed.py`'s
"before any authored edit" premise. Created steps are non-blocking, so
retiring them can never unhold a gate; each test leaves its step retired
where the flow allows, and any `mg.*` residue a failure leaves behind is
harmless to every other test here and in `test_playbook_seed.py`.

**Expected first-run state.** Absent target (`ModuleNotFoundError` /
`ImportError`): neither the adapter module nor the exported use cases
exist yet. Per `ai-toolkit:testing` that failure establishes only
absence.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

import inspect
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.launch.application import (
    create_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
)
from commerce_ops.launch.infrastructure.driven import playbook_repository
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"

A_DISCIPLINE: Final = next(iter(Discipline))


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's step tables and seed), and point DATABASE_URL at it."
        )
    return url


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_database_url())
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
    """The write store — a single correction point (see the docstring)."""
    factory = (
        getattr(playbook_repository, "PlaybookStepStore", None)
        or playbook_repository.PlaybookRepository
    )
    return factory(session)


async def _get(version: str) -> LaunchPlaybook:
    """A port read passing an explicit version value."""
    async with _session() as session:
        served = await _maybe_await(
            playbook_repository.PlaybookRepository(session).get(version)
        )
        assert isinstance(served, LaunchPlaybook)
        return served


async def _served() -> LaunchPlaybook:
    """A fresh read of the live served playbook."""
    return await _get("any-version-read-through")


def _step_named(playbook: LaunchPlaybook, identifier: str) -> StepDefinition | None:
    for step in playbook.steps:
        if step.identifier == identifier:
            return step
    return None


def _authorable_fields(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "gate": "ignition",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-3),
        "binding": Binding.FRAMEWORK,
        "blocking": False,
        "execution": ExecutionMode.HUMAN_ATTESTED,
        "hazard": Hazard.NONE,
        "rule_policy": None,
    }


def _unique_description(label: str) -> str:
    return f"{label} ({uuid.uuid4().hex[:12]})"


async def _create(description: str) -> str:
    """Create a step and return its identifier, located by description."""
    before = {step.identifier for step in (await _served()).steps}
    async with _session() as session:
        await _maybe_await(
            create_step(
                steps=_store(session),
                principal=PRINCIPAL,
                **_authorable_fields(description),
            )
        )
    after = await _served()
    created = [
        step
        for step in after.steps
        if step.identifier not in before and step.description == description
    ]
    assert len(created) == 1, (
        f"expected exactly the one created step for {description!r}, "
        f"found {[step.identifier for step in created]}"
    )
    return created[0].identifier


async def _retire(step_id: str) -> None:
    async with _session() as session:
        await _maybe_await(
            retire_step(steps=_store(session), principal=PRINCIPAL, step_id=step_id)
        )


async def _unretire(step_id: str) -> None:
    async with _session() as session:
        await _maybe_await(
            unretire_step(steps=_store(session), principal=PRINCIPAL, step_id=step_id)
        )


# ---------------------------------------------------------------------------
# Requirement: A step can be created — the serving half
# ---------------------------------------------------------------------------


async def test_a_created_step_joins_the_served_set() -> None:
    """Scenario: A created step joins the served set.

    WHEN a step is created with valid authorable fields
    THEN the next read of the playbook serves it, carrying a generated
    identifier whose second segment is its discipline.

    The authorship-provenance half is asserted at the unit tier, where
    the stored attribution is observable.
    """
    description = _unique_description("Refresh the hero image ahead of ignition")

    identifier = await _create(description)

    # SPECIFIED: generated, namespaced, discipline-bearing identifier.
    assert not identifier.startswith("lp.")
    assert identifier.split(".")[1] == A_DISCIPLINE.value
    served = _step_named(await _served(), identifier)
    assert served is not None
    assert served.description == description

    await _retire(identifier)  # residue control, not an assertion


# ---------------------------------------------------------------------------
# Requirement: A step can be updated — the serving half
# ---------------------------------------------------------------------------


async def test_an_edit_is_served_on_the_next_read() -> None:
    """Scenario: An edit is served on the next read.

    WHEN a step's description is updated
    THEN the next read of the playbook serves the step with the new
    description under its unchanged identifier.
    """
    original = _unique_description("Stage the launch teaser")
    reworded = _unique_description("Stage the launch teaser, reworded")
    identifier = await _create(original)

    async with _session() as session:
        await _maybe_await(
            update_step(
                steps=_store(session),
                principal=PRINCIPAL,
                step_id=identifier,
                description=reworded,
            )
        )

    served = _step_named(await _served(), identifier)
    assert served is not None
    # SPECIFIED: new description, unchanged identifier.
    assert served.description == reworded

    await _retire(identifier)


# ---------------------------------------------------------------------------
# Requirement: A step can be retired and un-retired — the serving halves
# ---------------------------------------------------------------------------


async def test_a_retired_step_leaves_and_rejoins_the_served_set() -> None:
    """Scenarios: A retired step leaves the served set / An un-retired
    step rejoins the served set.

    WHEN a step is retired
    THEN the next read of the playbook does not serve it.
    WHEN it is un-retired
    THEN the next read serves it again under its original identifier.

    The attribution halves (who retired/un-retired, when) are asserted at
    the unit tier against the stored record.
    """
    identifier = await _create(_unique_description("Short-lived checklist item"))

    await _retire(identifier)
    assert _step_named(await _served(), identifier) is None

    await _unretire(identifier)
    restored = _step_named(await _served(), identifier)
    assert restored is not None
    assert restored.identifier == identifier

    await _retire(identifier)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Playbooks are versioned
# ---------------------------------------------------------------------------


async def test_an_authored_change_changes_the_served_version_identifier() -> None:
    """Scenario: An authored change changes the served version identifier.

    WHEN the playbook is read, the step set is then changed by an
    accepted write, and the playbook is read again
    THEN the two reads report different version identifiers.
    """
    before = (await _served()).version

    identifier = await _create(_unique_description("Version-moving step"))
    after = (await _served()).version

    assert after != before

    await _retire(identifier)
    # A retire is an accepted write too; the version moves again.
    assert (await _served()).version != after


async def test_a_stale_version_stamp_does_not_freeze_the_read() -> None:
    """Scenario: An authored change reaches a launch already in flight —
    with the audit-stamp half of *A launch records the version it
    started under* ("no subsequent read of the playbook branches on it").

    WHEN the step set is changed after a launch has started, and the
    playbook is next read on that launch's behalf — here, a read passing
    the stale version identifier the launch recorded
    THEN the read serves the current step set, including the change.
    """
    stamp = (await _served()).version  # what an in-flight launch recorded

    identifier = await _create(_unique_description("Mid-launch authored step"))

    read_for_launch = await _get(stamp)
    # SPECIFIED: the read serves the current set, the change included —
    # the stamp selects nothing.
    assert _step_named(read_for_launch, identifier) is not None
    assert read_for_launch.version != stamp

    await _retire(identifier)
