"""The six metric steps, after migrate-then-prepare, read back from
Postgres.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-playbook/spec.md`,
and from `tasks.md` 7.3, which asks for exactly this at this tier:

    On an **empty** database, run migrate-then-prepare and confirm: both
    schema migrations apply, the step set loads coherently at 358 steps,
    and each of the six carries its metric identifier — the identifier,
    not just the row, since a null one changes no behaviour until the
    monitoring join is attempted and would go unnoticed.

Covers the storage half of the ADDED requirement *The seeded step set
carries every reference row*: that the six rows and, crucially, their
`metric_id` values survive the column migration, the preparation step's
insert and the repository's read. The vendored file's own half — that the
six are in it, blocking, draft, and named by the naming rule — is at the
unit tier in
`tests/unit/launch/test_playbook_reference_set_metric_steps.py`; a file
correct on disk whose column is never written would pass there and fail
here, which is the point of having both.

## What "on an empty database" means for a test

The migration and the preparation step are operator actions, not
something a test performs: `AGENTS.md` has the tier's database created
and migrated by hand, and `design.md` — Decision 6 puts the six rows in
the preparation step rather than in a migration precisely because a
migration runs once per environment. So what this file asserts is the
**resulting state** of a database that has been migrated and prepared,
and it says so loudly when the state it finds is a migrate-only one.

`tasks.md` 6.5 records that a migrate-only database carries the
migration-era seed's 107 steps rather than the served set, so
`AGENTS.md`'s "create and migrate `commerce_ops_test` once by hand"
leaves a database the preparation step must still be run against. That
gap predates this change; this file names it in its failure message
rather than skipping past it, so a run against an unprepared database
reports a setup gap instead of a phantom defect.

## Level

The integration tier: the assertion is that a value survives a column, a
migration and an adapter read, which nothing below the database can
observe. It follows the read shape
`tests/integration/launch/test_seeded_step_fields.py` records.

## Read, never written

This file only reads. Assertions filter to the `lp.*` namespace so `mg.*`
residue from the authoring tests in this directory cannot leak in.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the six identifiers (`tasks.md` 3.1); 358 as the
seeded count (`tasks.md` 3.4); `metric_id` as the field (`tasks.md` 2.1);
that the column is nullable and added by its own migration
(`tasks.md` 2.2).

INVENTED: `PlaybookRepository(session).get(version)` for the served
playbook and the authored read `_authored_steps()` probes for — both as
`tests/integration/launch/test_seeded_step_fields.py`'s docstring records
them, and reproduced here because that file must not be edited by this
pass.

## Expected first-run state

Absent target: `metric_id` does not exist on `StepDefinition`, the column
migration is unwritten and the six rows are not in the vendored file.
Skips where no database is configured, through the tier's `database_url`
gate — which is the state of this machine, so these assertions have never
been executed against a database and this file's own claim is only that
it will run there.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed. This tier skipped throughout: no
`DATABASE_URL` is configured here.
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
    framework_gates,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)

pytestmark = pytest.mark.anyio

#: SPECIFIED (`tasks.md` 3.1): the six rows this change seeds.
SEEDED_METRIC_STEPS: Final = (
    "lp.inventory.040",
    "lp.inventory.041",
    "lp.strategy.025",
    "lp.strategy.033",
    "lp.ppc.048",
    "lp.finance.036",
)

METRIC_BEARING_STEPS: Final = tuple(
    identifier for identifier in SEEDED_METRIC_STEPS if identifier != "lp.ppc.048"
)
"""Of the six, those whose words state a threshold on one named quantity.

`lp.ppc.048` conditions its gate on four qualitative criteria naming no
single quantity, so it is seeded blocking and declares no identifier
(`design.md` — Decision 8). Written before that decision, the two
assertions below required all six to carry one.
"""

#: SPECIFIED (`tasks.md` 3.4, 7.3): the prepared set's size.
SEEDED_COUNT: Final = 358

#: `tasks.md` 6.5: what a migrate-only database carries instead, named so
#: a failure here reads as a setup gap rather than as a defect.
MIGRATION_ERA_COUNT: Final = 107


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
    """Every authored step definition, whatever its status — the six are
    seeded `draft`, so the served read would not answer them.

    INVENTED read; the single correction point for how the authored set
    is reached.
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


async def _seeded() -> dict[str, StepDefinition]:
    """The `lp.*` rows alone, keyed by identifier, with the setup gap
    named where the database has been migrated but not prepared."""
    steps = await _authored_steps()
    seeded = {
        step.identifier: step for step in steps if step.identifier.startswith("lp.")
    }
    assert len(seeded) != MIGRATION_ERA_COUNT, (
        f"the database carries exactly {MIGRATION_ERA_COUNT} `lp.*` steps, "
        "which is the migration-era seed — it has been migrated but the "
        "preparation step has not been run against it (`tasks.md` 6.5). Run "
        "the preparation step before this tier, rather than reading this as "
        "a defect in the seed."
    )
    assert seeded, "no seeded (lp.*) steps were read back"
    return seeded


# ---------------------------------------------------------------------------
# Requirement (ADDED): The seeded step set carries every reference row
# ---------------------------------------------------------------------------


async def test_the_prepared_step_set_loads_coherently_at_358_steps() -> None:
    """`tasks.md` 7.3: "the step set loads coherently at 358 steps".

    Coherence is asserted by constructing a `LaunchPlaybook` over the
    framework's gates and the whole authored set — the same rulebook every
    load and every write applies, which rejects rather than returning a
    partially valid playbook.
    """
    seeded = await _seeded()

    # SPECIFIED: 358, the reference document's ID-bearing row count.
    assert len(seeded) == SEEDED_COUNT, (
        f"the prepared set carries {len(seeded)} `lp.*` steps, not "
        f"{SEEDED_COUNT}; the six restatement rows are what this change adds"
    )
    # SPECIFIED: it loads coherently.
    playbook = LaunchPlaybook(
        version="prepared-set-check",
        gates=framework_gates(),
        steps=tuple(seeded.values()),
    )
    assert len(playbook.authored_steps) == SEEDED_COUNT


async def test_each_of_the_six_carries_its_metric_identifier() -> None:
    """`tasks.md` 7.3: "each of the six carries its metric identifier —
    the identifier, not just the row, since a null one changes no
    behaviour until the monitoring join is attempted and would go
    unnoticed".

    That sentence is why this asserts the value and not merely the row's
    presence: the column is nullable, nothing reads it yet, and a
    preparation step that inserted the six rows while dropping the field
    would leave the launch↔monitoring join silently unavailable — the one
    thing this change carries forward from the removed condition.

    **Which identifier each row carries is not asserted.** `tasks.md` 1.2
    transcribes them out of `_AUTHORED_METRIC_CONDITIONS` during
    implementation; no artifact of this change states the mapping, so a
    test fixing it would invent the answer rather than check it.
    """
    seeded = await _seeded()

    for identifier in SEEDED_METRIC_STEPS:
        assert identifier in seeded, (
            f"{identifier} is not in the prepared set; `tasks.md` 3.1 seeds "
            "all six and 3.2 has the preparation step deliver them"
        )

    for identifier in METRIC_BEARING_STEPS:
        step = seeded[identifier]
        # SPECIFIED: the identifier survived the column, the insert and
        # the read.
        assert step.metric_id is not None, (
            f"{identifier} came back from the database with no metric "
            "identifier; the row survived and the field did not"
        )
        assert str(getattr(step.metric_id, "value", step.metric_id)).strip(), (
            f"{identifier}'s metric identifier read back empty"
        )
        # SPECIFIED (`tasks.md` 3.1): blocking, and seeded `draft` like
        # every other row (`design.md` — Decision 3).
        assert step.blocking is True, identifier


async def test_no_other_prepared_step_gained_a_metric_identifier() -> None:
    """Scenario: A row merely mentioning a number is an ordinary step —
    the storage half.

    The resulting set is the six and no other, read back from the
    database rather than from the file: a preparation step that wrote the
    column from the wrong source, or a repository mapping that filled it
    by default, would leave the file correct and the stored set wrong.
    """
    seeded = await _seeded()

    declaring = {
        identifier
        for identifier, step in seeded.items()
        if getattr(step, "metric_id", None) is not None
    }

    assert declaring == set(METRIC_BEARING_STEPS), (
        f"unexpected: {sorted(declaring - set(METRIC_BEARING_STEPS))}; "
        f"missing: {sorted(set(METRIC_BEARING_STEPS) - declaring)}"
    )
    # SPECIFIED (delta): a gate-conditioning row naming no single quantity
    # blocks *without* an identifier — asserted, not merely tolerated by
    # the set comparison above.
    assert seeded["lp.ppc.048"].metric_id is None
