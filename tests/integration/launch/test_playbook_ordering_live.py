"""Within-gate authored order reaching the live served playbook, against
real Postgres.

Derived strictly from the delta specs of `add-playbook-admin-ui`:
`.../specs/launch-playbook/spec.md` (MODIFIED *Gate sequence orders the
launch* — scenario *Steps at a gate are served in their authored
order*) and `.../specs/playbook-authoring/spec.md` (the serving halves
that `tests/unit/launch/application/test_playbook_reorder.py` cannot
observe through a fake store: the real adapter's ordered read after a
reorder, an append-on-create, and an append-on-un-retire).

Conventions, invented shapes (`PlaybookRepository`, `_store`, the
use-case call shapes) and the test-database lifecycle are the ones
`test_playbook_authoring_live.py` in this directory records; the
`reorder_step` call shape is the one `test_playbook_reorder.py`
records (`steps=`, `principal=`, `step_id=`, `target_index=` 0-based).
Writes are confined to `mg.*` steps these tests create in the
`ignition` gate; each test retires its residue. A reorder renumbers the
gate's slots but preserves every other step's relative order, so the
seeded rows' order is left as found.

DELIBERATELY UNTESTED here, recorded in the manifest: the migration's
backfill ("the step set as it stands ... SHALL keep the order it was
being served in") is a property of the migration *moment* — on any
database whose steps have since been reordered, asserting
identifier-order would be wrong, so a standing test cannot pin it.

**Expected first-run state.** Absent target: `reorder_step` is not
exported yet, so the file fails at import. The create/un-retire tests
would otherwise run against the existing adapter, whose serve order and
slot assignment do not exist yet.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed. The
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
    reorder_step,
    retire_step,
    unretire_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
)
from commerce_ops.launch.infrastructure.driven import playbook_repository
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"
GATE: Final = "ignition"
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
            "change's `display_order` migration), and point DATABASE_URL "
            "at it."
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
    factory = (
        getattr(playbook_repository, "PlaybookStepStore", None)
        or playbook_repository.PlaybookRepository
    )
    return factory(session)


async def _served() -> LaunchPlaybook:
    async with _session() as session:
        served = await _maybe_await(
            playbook_repository.PlaybookRepository(session).get("any-version")
        )
        assert isinstance(served, LaunchPlaybook)
        return served


async def _gate_order() -> list[str]:
    """The identifiers of the gate's steps, in served order."""
    return [step.identifier for step in (await _served()).steps_for_gate(GATE)]


def _authorable_fields(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "gate": GATE,
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
    before = {step.identifier for step in (await _served()).steps}
    async with _session() as session:
        await _maybe_await(
            create_step(
                steps=_store(session),
                principal=PRINCIPAL,
                **_authorable_fields(description),
            )
        )
    created = [
        step.identifier
        for step in (await _served()).steps
        if step.identifier not in before and step.description == description
    ]
    assert len(created) == 1
    return created[0]


async def _reorder(step_id: str, target_index: int) -> None:
    async with _session() as session:
        await _maybe_await(
            reorder_step(
                steps=_store(session),
                principal=PRINCIPAL,
                step_id=step_id,
                target_index=target_index,
            )
        )


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
# launch-playbook (MODIFIED): Steps at a gate are served in their
# authored order
# ---------------------------------------------------------------------------


async def test_two_reads_with_no_intervening_write_serve_the_same_order() -> None:
    """Scenario: Steps at a gate are served in their authored order —
    the stability clause.

    WHEN a gate's steps are read from the served playbook twice with no
    intervening write
    THEN both reads arrive in the same order, for every gate.

    That the order is the *authored* one (not an accident of row order)
    is asserted by the reorder test below, which authors an order and
    reads it back.
    """
    first = await _served()
    second = await _served()

    for gate in (gate.identifier for gate in first.gates):
        assert [step.identifier for step in first.steps_for_gate(gate)] == [
            step.identifier for step in second.steps_for_gate(gate)
        ], f"gate {gate} served two different orders across two reads"


async def test_a_reorder_is_served_on_the_next_read() -> None:
    """Scenarios: A moved step is served in its new slot (the serving
    half) / Steps at a gate are served in their authored order (the
    authored-order clause).

    WHEN a step is moved to its gate's first position
    THEN the next read serves that gate's steps with the moved step
    first, the rest in their previous relative order.
    """
    first_created = await _create(_unique_description("Ordered work A"))
    second_created = await _create(_unique_description("Ordered work B"))
    try:
        before = await _gate_order()
        # Both created steps were appended, in creation order.
        assert before[-2:] == [first_created, second_created]

        await _reorder(second_created, 0)

        after = await _gate_order()
        # SPECIFIED: moved step first; everyone else in their previous
        # relative order.
        assert after[0] == second_created
        assert after[1:] == [s for s in before if s != second_created]
    finally:
        await _retire(first_created)
        await _retire(second_created)


# ---------------------------------------------------------------------------
# playbook-authoring: Every live step holds a slot in its gate's order
# (the serving halves)
# ---------------------------------------------------------------------------


async def test_a_created_step_is_served_last_in_its_gate() -> None:
    """Scenario: A created step appends to its gate — the serving half.

    WHEN a step is created for a gate that already has live steps
    THEN the next read serves it as that gate's last step.
    """
    identifier = await _create(_unique_description("Appended work"))
    try:
        assert (await _gate_order())[-1] == identifier
    finally:
        await _retire(identifier)


async def test_an_unretired_step_is_served_last_whatever_slot_it_held() -> None:
    """Scenarios: An un-retired step rejoins at the end / Retirement
    closes the gap — the serving halves.

    WHEN a step holding the gate's first slot is retired and later
    un-retired
    THEN while retired, the remaining steps keep their relative order,
    and on rejoining it is served as the gate's last step.
    """
    identifier = await _create(_unique_description("Roundtrip work"))
    try:
        await _reorder(identifier, 0)
        assert (await _gate_order())[0] == identifier
        others_before = (await _gate_order())[1:]

        await _retire(identifier)
        # SPECIFIED: the gap closes; survivors keep their relative order.
        assert await _gate_order() == others_before

        await _unretire(identifier)
        # SPECIFIED: rejoins last, not in its remembered first slot.
        assert await _gate_order() == [*others_before, identifier]
    finally:
        await _retire(identifier)
