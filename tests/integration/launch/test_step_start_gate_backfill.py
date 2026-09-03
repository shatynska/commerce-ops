"""The stored step set after the start-gate backfill, read from Postgres
(`launch-playbook`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-playbook/spec.md`
— the ADDED requirement *The stored step set declares when its steps
start*, and the four scenarios of it that are stated about the **stored
set**:

- *A stored step starts at its own gate*
- *A stored step anchored before its gate starts earlier*
- *A final-gate step's default spans more than one gate*
- *A draft step declares a start gate too*

plus the requirement's clause *An authored value survives*, whose
scenario is stated over "a step whose `starts_at_gate` has been authored
before this obligation is met" and which `tasks.md` 8.1 turns into the
migration's own rule ("applied only where the column is null").

Its other scenarios are covered elsewhere: *An activated draft does not
become eligible everywhere* in
`tests/unit/launch/domain/test_step_start_release.py`, *An author may set
a step back to starting immediately* in
`tests/unit/launch/application/test_step_dependency_preconditions.py`, and
the two delivery-path scenarios in
`tests/unit/launch/test_playbook_reference_set_start_gates.py`. The
manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
accounts for every scenario in the change.

## Level

The real database after `alembic upgrade head`. Every scenario here is a
property of what the two revisions left in `playbook_steps`, and
`tasks.md` 10.2 names this tier as "the point of this one".

## Read, never written

Every assertion states a property of the stored set as the migrations
left it, so this file never writes. Assertions are scoped to the `lp.*`
namespace so `mg.*` residue from the authoring tests cannot leak in.

## INVENTED, with correction points

- The authored read (`_authored_steps`), probed on the playbook and then
  on the repository and failing loudly rather than defaulting — taken
  unchanged from `test_seeded_step_fields.py`, which records why.
- Nothing else: the seven anchor exceptions and the final-gate default
  are stated by identifier in `tasks.md` 8.2-8.5 and are transcribed
  here, not recomputed.

## Expected first-run state

Absent target: neither column nor revision exists, so every test here is
expected to fail on the field being absent. Skips where no database is
configured, through the tier's `database_url` gate — and in CI, where
`COMMERCE_OPS_REQUIRE_DATABASE` is set, fails instead.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29, against a configured database.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]
POSITIONS: Final = {gate: index for index, gate in enumerate(SPECIFIED_GATE_ORDER)}

SEEDED_PREFIX: Final = "lp."

#: SPECIFIED by `tasks.md` 8.5: a final-gate step defaults to `ignition`
#: — two gates back, because "gate progression advances a launch as far
#: as its state permits within one pass, so a single-gate window can be
#: crossed between two runs".
FINAL_GATE_DEFAULT: Final = "ignition"

#: SPECIFIED by `tasks.md` 8.2-8.4: the seven reviewed steps whose
#: calendar anchor falls before their own gate can be reached, each with
#: the earlier gate its anchor implies.
ANCHOR_EXCEPTIONS: Final[dict[str, str]] = {
    "lp.inventory.019": "order",
    "lp.inventory.008": "order",
    "lp.inventory.018": "order",
    "lp.ppc.001": "listable",
    "lp.ppc.002": "listable",
    "lp.ppc.004": "listable",
    "lp.ppc.003": "order",
}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate."""


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _served() -> LaunchPlaybook:
    async with _session() as session:
        result = await _resolve(
            PlaybookRepository(session).get("any-version-read-through")
        )
        assert isinstance(result, LaunchPlaybook)
        return result


_AUTHORED_ON_PLAYBOOK: Final = ("authored_steps", "all_steps")
_AUTHORED_ON_REPOSITORY: Final = (
    "authored_steps",
    "all_steps",
    "list_authored",
    "load",
)


async def _authored_steps() -> tuple[StepDefinition, ...]:
    """Every authored step definition, whatever its status.

    INVENTED read, taken unchanged from `test_seeded_step_fields.py`.
    Fails loudly rather than defaulting, so no assertion below can pass
    over an empty set.
    """
    playbook = await _served()
    for name in _AUTHORED_ON_PLAYBOOK:
        carried = getattr(playbook, name, None)
        if carried is not None:
            steps = await _resolve(carried() if callable(carried) else carried)
            return tuple(steps)
    async with _session() as session:
        repository = PlaybookRepository(session)
        for name in _AUTHORED_ON_REPOSITORY:
            reader = getattr(repository, name, None)
            if reader is None:
                continue
            answered = await _resolve(reader())
            rows = answered[0] if isinstance(answered, tuple) else answered
            steps = [
                row if isinstance(row, StepDefinition) else row.definition
                for row in rows
            ]
            if steps:
                return tuple(steps)
    pytest.fail(
        "no authored read was found on the playbook or the repository — "
        "correct this file's probe to the implemented read"
    )


async def _seeded() -> tuple[StepDefinition, ...]:
    steps = tuple(
        step
        for step in await _authored_steps()
        if step.identifier.startswith(SEEDED_PREFIX)
    )
    assert steps, (
        "the stored set carries no `lp.` steps, so nothing here is being "
        "asserted — has `alembic upgrade head` been applied?"
    )
    return steps


# ---------------------------------------------------------------------------
# ADDED Requirement: The stored step set declares when its steps start
# ---------------------------------------------------------------------------


async def test_every_stored_step_declares_a_start_gate() -> None:
    """Requirement statement: "Every step the system already stores SHALL
    declare a `starts_at_gate`."

    Stated once as the requirement's opening sentence rather than in a
    scenario, and asserted first because every scenario below presupposes
    it: a set in which some steps carry nothing would satisfy several of
    them vacuously.
    """
    missing = [step.identifier for step in await _seeded() if not step.starts_at_gate]

    assert not missing, (
        f"{len(missing)} stored steps declare no start gate (first few: "
        f"{missing[:5]}); a per-step field nobody fills in is a field that "
        "does not do its work"
    )


async def test_a_stored_step_starts_at_its_own_gate() -> None:
    """Scenario: A stored step starts at its own gate.

    WHEN the stored step set is read after this obligation is met
    THEN each step whose anchor does not precede its gate's reachability
    declares its own gate as its start gate.
    """
    wrong = {
        step.identifier: (step.starts_at_gate, step.gate)
        for step in await _seeded()
        if step.identifier not in ANCHOR_EXCEPTIONS
        and step.gate != FINAL_GATE
        and step.starts_at_gate != step.gate
    }

    assert not wrong, (
        "these stored steps do not take their own gate as their start gate "
        f"(identifier: declared, own gate): {dict(list(wrong.items())[:8])}"
    )


async def test_a_stored_step_anchored_before_its_gate_starts_earlier() -> None:
    """Scenario: A stored step anchored before its gate starts earlier.

    WHEN a stored step's timing anchor falls before its own gate can be
    reached
    THEN it declares the earlier gate its anchor implies, and not its own
    gate.

    The seven are named by identifier rather than re-derived from the
    anchors, because `tasks.md` 8.6 states them that way — "the same
    seven are `draft` in the vendored file and `active` in the stored
    set", so status cannot select them.
    """
    stored = {step.identifier: step for step in await _seeded()}

    for identifier, expected in ANCHOR_EXCEPTIONS.items():
        step = stored.get(identifier)
        assert step is not None, (
            f"{identifier!r} is not in the stored set, so the exception the "
            "backfill states for it cannot be observed"
        )
        assert step.starts_at_gate == expected, (
            f"{identifier!r} declares {step.starts_at_gate!r}; its anchor "
            f"implies {expected!r}"
        )
        # SPECIFIED: "and not its own gate" — the exception is a
        # departure, so a step whose own gate happened to equal the
        # earlier one would establish nothing.
        assert POSITIONS[expected] < POSITIONS[step.gate], (
            f"{identifier!r} starts at {expected!r}, which is not earlier "
            f"than its own gate {step.gate!r}"
        )


async def test_a_final_gate_steps_default_spans_more_than_one_gate() -> None:
    """Scenario: A final-gate step's default spans more than one gate.

    WHEN the stored step set is read after this obligation is met
    THEN each step belonging to the final gate declares a start gate at
    least two gates before it.

    SPECIFIED reason: the gate immediately before the final one "is a
    *single* gate's window ... and a step released only there would never
    be acted on at all". `tasks.md` 8.5 fixes the value as `ignition`,
    and the requirement adds that the default "SHALL be the **nearest**
    gate satisfying the margin, and not the earliest".
    """
    final_gate_steps = [step for step in await _seeded() if step.gate == FINAL_GATE]

    assert final_gate_steps, (
        "the stored set carries no final-gate step, so this scenario is not "
        "being reached"
    )
    for step in final_gate_steps:
        assert step.starts_at_gate, f"{step.identifier!r} declares no start gate"
        gap = POSITIONS[FINAL_GATE] - POSITIONS[str(step.starts_at_gate)]
        # SPECIFIED: at least two gates before it.
        assert gap >= 2, (
            f"{step.identifier!r} starts at {step.starts_at_gate!r}, "
            f"{gap} gate(s) before the final one; the margin is two"
        )
        # SPECIFIED: the nearest gate satisfying the margin, not the
        # earliest — "Widening further is not free".
        assert step.starts_at_gate == FINAL_GATE_DEFAULT, (
            f"{step.identifier!r} starts at {step.starts_at_gate!r} rather "
            f"than the nearest gate satisfying the margin, {FINAL_GATE_DEFAULT!r}"
        )


async def test_a_draft_step_declares_a_start_gate_too() -> None:
    """Scenario: A draft step declares a start gate too.

    WHEN the stored step set is read after this obligation is met
    THEN a step whose status is `draft` declares a start gate on the same
    rule as an `active` one.

    `design.md` names this "where this fails quietly if the backfill
    covers only what is served": 255 of the 352 stored steps are `draft`,
    and "a draft backfilled to nothing becomes, on the day it is
    activated, exactly the step this change was written to prevent".
    """
    drafts = [step for step in await _seeded() if step.status is StepStatus.DRAFT]

    assert drafts, (
        "the stored set carries no `draft` step, so this scenario is not "
        "being reached. Most of the stored set is expected to be drafts: the "
        "255 the vendored reference set adds are inserted by `seed_playbook`, "
        "which runs on container start rather than as a migration. A database "
        "that has had `alembic upgrade head` applied but has never run the "
        "preparation step carries only the 97 migrated `lp.` rows and no "
        "draft at all — which is the state this assertion is reporting, not a "
        "defect in the backfill"
    )
    missing = [step.identifier for step in drafts if not step.starts_at_gate]
    assert not missing, (
        f"{len(missing)} `draft` steps declare no start gate (first few: "
        f"{missing[:5]}); activation would then make each eligible in every "
        "launch at once"
    )

    # SPECIFIED: "on the same rule as an `active` one" — a draft is not
    # backfilled to some other value.
    wrong = {
        step.identifier: (step.starts_at_gate, step.gate)
        for step in drafts
        if step.identifier not in ANCHOR_EXCEPTIONS
        and step.gate != FINAL_GATE
        and step.starts_at_gate != step.gate
    }
    assert not wrong, (
        f"these drafts follow some other rule: {dict(list(wrong.items())[:8])}"
    )


async def test_no_stored_start_gate_names_the_final_gate() -> None:
    """Requirement statement: "A `starts_at_gate` naming the final gate
    SHALL be rejected, for every step including those belonging to that
    gate."

    A stored set violating this is one the loader refuses, which serves
    nothing — the failure `tasks.md` 8.5 records as the reason the
    final-gate default exists at all. Asserted here rather than left to
    `_served()` raising, so the reason a load failed is legible.
    """
    offending = [
        step.identifier for step in await _seeded() if step.starts_at_gate == FINAL_GATE
    ]

    assert not offending, f"these stored steps start at the final gate: {offending[:8]}"


async def test_no_stored_start_gate_is_later_than_its_own_gate() -> None:
    """Requirement statement (*A step cannot start after the gate it
    belongs to*): a playbook is rejected where any step declares a start
    gate later than its own.

    The load-time rule is covered at the domain tier in
    `tests/unit/launch/domain/test_step_start_coherence.py`; what this
    asserts is that the **backfilled data** satisfies it, which
    `design.md` names as the backfill's one bounded risk: "A wrong value
    delays work; it cannot deadlock, because the load rules refuse a
    start gate later than a step's own gate."
    """
    offending = {
        step.identifier: (step.starts_at_gate, step.gate)
        for step in await _seeded()
        if step.starts_at_gate
        and POSITIONS[str(step.starts_at_gate)] > POSITIONS[step.gate]
    }

    assert not offending, (
        "these stored steps start later than the gate they belong to "
        f"(identifier: start gate, own gate): {offending}"
    )


async def test_the_stored_set_still_serves() -> None:
    """Scenario: An authored value survives — read as the whole set still
    loading.

    The backfill writes "only where the column is null and keyed on step
    identifier, skipping a row it does not find" (`tasks.md` 8.1, 8.7),
    so an authored value is never overwritten. Nothing in the stored set
    is authored at the point this runs, so what is observable here is the
    consequence: the set the backfill produced is one the loader accepts
    and serves.

    DELIBERATELY UNTESTED at this tier: that a *specific* authored value
    survives the migration. Observing it would mean authoring a value,
    downgrading and re-upgrading, which writes to the shared database
    this file otherwise only reads. `tasks.md` 8.9's downgrade check and
    10.5's scratch-database walk-through are where that belongs, and both
    are stated as manual verification rather than as tests.
    """
    playbook = await _served()

    assert playbook.served_steps, (
        "the stored set serves nothing after the backfill; a start gate the "
        "load rules refuse would produce exactly this"
    )
    assert playbook.is_ready
