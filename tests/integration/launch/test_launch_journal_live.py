"""Tests for the launch journal against a real Postgres.

Derived from the delta spec:
openspec/changes/add-launch-journal/specs/launch-journal/spec.md

Covers the scenarios that cannot be observed above the database:

- *One launch's journal is readable, most recent first* — its two
  ordering scenarios, *A launch's journal is read most recent first* and
  *Entries naming the same moment report the later append first*.
  Ordering is the repository's (`tasks.md` 6.2: `occurred_at DESC,
  sequence DESC`) and the append sequence that breaks a tie exists only
  in the database, so a fake could only ever test itself.
- *A launch's journal is retained for the life of the launch record* —
  *Removing the launch record removes its journal*, which is the
  `ON DELETE CASCADE` of `design.md` Decision 4 and nothing else.
- *An entry stores structure, never rendered prose* — both scenarios, in
  their literal stored-row form. `tasks.md` 1.2 asks for exactly this:
  *assert on what the repository wrote, and compose through the read*.
  The unit file `tests/unit/launch/application/test_launch_journal_read.py`
  makes the same assertion one layer up, against what the use case hands
  the port; this one reads the row back with SQL, so a repository that
  rendered a sentence on the way in is caught even though the use case
  did not.

Every other scenario of the delta spec is driven in the three unit files
under `tests/unit/launch/application/` — see this change's
`test-manifest.md` for the full accounting.

## Test-database lifecycle

The convention this directory already keeps: a freshly registered catalog
product per test (so no truncate fixture is needed), and
`alembic upgrade head` — including this change's new revision — assumed
applied. The tier skips where no database is configured
(`tests/integration/conftest.py`).

## The interface under test does not exist yet, and its shape is INVENTED

At the time of writing neither the table, the repository nor the read
exist, so every test here is expected to fail on an absent target — an
`ImportError`, or a `UndefinedTable` for `launch_journal_entries` where
the migration has not been applied. Per `ai-toolkit:testing`, that
establishes only absence.

**These tests have never been executed.** No database was reachable where
they were written, so their failure mode is unestablished: a fixture
fault here would be indistinguishable from the absent target until the
tier is first run with a database. `tasks.md` 1.3 is not discharged for
this file.

Fixed by this change's artifacts: the table name
`launch_journal_entries` and its columns (`design.md` Decision 4,
`tasks.md` 2.1); the ordering (`tasks.md` 6.2); the cascade (Decision 4);
`read_launch_journal(journal, *, product_id, scope)` (`tasks.md` 7.1);
and the read model's `kind` / `what` / `when` / `cause` (Decision 5).

INVENTED, with correction points: the repository's module and class name,
`commerce_ops.launch.infrastructure.driven.launch_journal_repository`
exporting `LaunchJournalRepository(session)`, on `LaunchRepository`'s
precedent (`tasks.md` 6.1 fixes the directory, not the name) — correction
point is the import; and the port being async — correction point is the
`await`s.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.application import (
    read_launch_journal,
    record_step_outcome,
    start_launch,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Provenance
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

LAUNCH_DATE: Final = date(2028, 3, 1)

FIRST_AT: Final = datetime(2028, 1, 10, 9, 0, tzinfo=UTC)
SECOND_AT: Final = datetime(2028, 1, 11, 9, 0, tzinfo=UTC)
THIRD_AT: Final = datetime(2028, 1, 12, 9, 0, tzinfo=UTC)
SAME_MOMENT: Final = datetime(2028, 1, 13, 9, 0, tzinfo=UTC)

RECORDER: Final = "Dana"
SOURCE: Final = "clickup"

STEP_A: Final = "listing.title-conforms"
STEP_A_NAME: Final = "Write the listing title to the conformance rules"
STEP_B: Final = "listing.images-approved"
STEP_B_NAME: Final = "Get the hero image approved by brand"
STEP_C: Final = "listing.copy-drafted"
STEP_C_NAME: Final = "Draft the bullet copy"

#: SPECIFIED (design.md Decision 4's table, tasks.md 2.1). The columns a
#: row may carry; the assertion that no other column exists is what makes
#: "no composed sentence is among them" checkable against the row.
FACT_COLUMNS: Final = frozenset(
    {
        "sequence",
        "product_id",
        "occurred_at",
        "kind",
        "actor",
        "source",
        "subject_id",
        "subject_label",
        "details",
    }
)

JOURNAL_TABLE: Final = "launch_journal_entries"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _normalised(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _unique_sku() -> Sku:
    return Sku(f"LJ-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_A,
        "name": STEP_A_NAME,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "automation_brief": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        automation_brief="Held until the automated check reports green.",
        handler="fixture.holding_check",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=(
                GateOpening.REQUIRES_CONFIRMATION
                if identifier in CONFIRMATION_GATES
                else GateOpening.AUTOMATIC
            ),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
        _step(),
        _step(identifier=STEP_B, name=STEP_B_NAME),
        _step(identifier=STEP_C, name=STEP_C_NAME),
    )
    return LaunchPlaybook(version="journal-live-v1", gates=gates, steps=steps)


class FakePlaybooks:
    """The playbook port. In-process on purpose: the journal is what these
    tests put in Postgres, not the playbook."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


def _provenance(when: datetime) -> Provenance:
    return Provenance(
        source=SOURCE,
        who=RECORDER,
        when=when,
        evidence="ClickUp task closed with its checklist complete",
    )


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def registered_product_id(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[ProductId]]:
    async def _register() -> ProductId:
        async with sessions() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Launch Journal Test Widget",
            )
        return product.id

    return _register


async def _start_and_record(
    sessions: async_sessionmaker[AsyncSession],
    product_id: ProductId,
    recordings: tuple[tuple[str, datetime], ...],
) -> None:
    """Start a launch and record each `(step_id, when)` in turn, each
    through its own session — the way the composing adapters do."""
    playbook = _playbook()
    async with sessions() as session:
        await start_launch(
            LaunchRepository(session),
            playbook,
            product_id=product_id,
            launch_date=LAUNCH_DATE,
            journal=LaunchJournalRepository(session),
        )
    for step_id, when in recordings:
        async with sessions() as session:
            await record_step_outcome(
                LaunchRepository(session),
                FakePlaybooks(playbook),
                product_id=product_id,
                step_id=step_id,
                outcome=Satisfied,
                provenance=_provenance(when),
                journal=LaunchJournalRepository(session),
            )


async def _rows(
    sessions: async_sessionmaker[AsyncSession], product_id: ProductId
) -> list[dict[str, Any]]:
    async with sessions() as session:
        result = await session.execute(
            text(
                f"SELECT * FROM {JOURNAL_TABLE} "
                f"WHERE product_id = CAST(:pid AS uuid) ORDER BY sequence"
            ),
            {"pid": product_id.value},
        )
        return [dict(row) for row in result.mappings()]


# ---------------------------------------------------------------------------
# R7: ordering
# ---------------------------------------------------------------------------


async def test_a_launchs_journal_is_read_most_recent_first(
    sessions: async_sessionmaker[AsyncSession],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A launch's journal is read most recent first.

    WHEN a launch whose journal holds three entries naming three
    different moments is read
    THEN the three entries are reported most recent first.
    """
    product_id = await registered_product_id()
    await _start_and_record(
        sessions,
        product_id,
        ((STEP_A, FIRST_AT), (STEP_B, SECOND_AT), (STEP_C, THIRD_AT)),
    )

    async with sessions() as session:
        reported = await read_launch_journal(
            LaunchJournalRepository(session),
            product_id=product_id,
            scope=AccessScope.unrestricted(),
        )

    # The launch-started entry is stamped by the store at append time, so
    # it sits above these three; the three step recordings are the
    # scenario's subject.
    recordings = [
        entry for entry in reported if entry.when in (FIRST_AT, SECOND_AT, THIRD_AT)
    ]
    assert len(recordings) == 3, (
        f"expected the three step recordings among {len(reported)} entries; "
        f"their moments were {[entry.when for entry in reported]!r}"
    )
    # SPECIFIED: most recent first, ordered by the moment each entry names.
    assert [entry.when for entry in recordings] == [THIRD_AT, SECOND_AT, FIRST_AT]
    # SPECIFIED, and the whole reported sequence is ordered too — not only
    # the subset this scenario names.
    moments = [entry.when for entry in reported]
    assert moments == sorted(moments, reverse=True)


async def test_entries_naming_the_same_moment_report_the_later_append_first(
    sessions: async_sessionmaker[AsyncSession],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Entries naming the same moment report the later append
    first.

    WHEN two entries naming the same moment are read
    THEN the one appended later is reported first.

    A batch reconciliation recording several steps under one timestamp is
    the ordinary case, not the edge (`design.md` Decision 4), which is why
    "most recent first" has to be total.
    """
    product_id = await registered_product_id()
    await _start_and_record(
        sessions,
        product_id,
        ((STEP_A, SAME_MOMENT), (STEP_B, SAME_MOMENT)),
    )

    stored = await _rows(sessions, product_id)
    tied = [row for row in stored if row["occurred_at"] == SAME_MOMENT]
    assert len(tied) == 2, (
        f"fixture premise: two rows naming the same moment; found "
        f"{len(tied)} among {[row['occurred_at'] for row in stored]!r}"
    )
    # The premise: they really were appended in this order.
    assert [row["subject_id"] for row in tied] == [STEP_A, STEP_B]

    async with sessions() as session:
        reported = await read_launch_journal(
            LaunchJournalRepository(session),
            product_id=product_id,
            scope=AccessScope.unrestricted(),
        )

    at_the_same_moment = [entry for entry in reported if entry.when == SAME_MOMENT]
    assert len(at_the_same_moment) == 2
    # SPECIFIED: the later of two simultaneous entries is reported first.
    first, second = at_the_same_moment
    assert _normalised(STEP_B_NAME) in _normalised(first.what), (
        f"the later-appended entry must be reported first; the first "
        f"reported was {first.what!r}"
    )
    assert _normalised(STEP_A_NAME) in _normalised(second.what)


# ---------------------------------------------------------------------------
# R4: an entry stores structure, never rendered prose — as stored
# ---------------------------------------------------------------------------


async def test_an_entry_is_stored_as_facts_in_the_row(
    sessions: async_sessionmaker[AsyncSession],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: An entry is stored as facts.

    WHEN an entry is appended and inspected as stored
    THEN its kind, the moment it names, the identifiers and labels it
    concerned and its distinguishing values are each carried separately,
    and no composed sentence is among them.
    """
    product_id = await registered_product_id()
    await _start_and_record(sessions, product_id, ((STEP_A, FIRST_AT),))

    stored = await _rows(sessions, product_id)
    recording = [row for row in stored if row["kind"] == "step-outcome-recorded"]
    assert len(recording) == 1
    row = recording[0]

    # SPECIFIED: each carried separately.
    assert row["occurred_at"] == FIRST_AT
    assert row["subject_id"] == STEP_A
    assert row["subject_label"] == STEP_A_NAME
    assert row["actor"] == RECORDER
    assert row["source"] == SOURCE
    assert isinstance(row["details"], dict)

    # SPECIFIED: no composed sentence is among them. A column outside the
    # fact set is where one would live.
    assert set(row) <= FACT_COLUMNS, (
        f"the row carries columns outside the fact set: "
        f"{sorted(set(row) - FACT_COLUMNS)}"
    )


async def test_improved_wording_reaches_entries_already_appended(
    sessions: async_sessionmaker[AsyncSession],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Improved wording reaches entries already appended.

    WHEN the wording composed for a kind of occurrence changes, and a
    launch's journal holding an entry of that kind from before the change
    is read
    THEN that entry reads with the new wording.

    Read as `tasks.md` 1.2 directs — a test about *where* composition
    happens, not about a particular sentence. It holds exactly when the
    stored row holds no sentence and the read composes one from the row's
    facts: the composer is then the only source of wording, so improving
    it improves every row already written.
    """
    product_id = await registered_product_id()
    await _start_and_record(sessions, product_id, ((STEP_A, FIRST_AT),))

    async with sessions() as session:
        reported = await read_launch_journal(
            LaunchJournalRepository(session),
            product_id=product_id,
            scope=AccessScope.unrestricted(),
        )
    composed = next(
        entry for entry in reported if entry.kind == "step-outcome-recorded"
    )

    stored = await _rows(sessions, product_id)
    row = next(row for row in stored if row["kind"] == "step-outcome-recorded")
    values = [str(value) for value in row.values() if value is not None]
    values.extend(str(value) for value in row["details"].values())

    # SPECIFIED: nothing in the row is the sentence the read composed.
    assert composed.what
    for value in values:
        assert composed.what not in value, (
            f"the stored value {value!r} carries the composed wording "
            f"{composed.what!r}; wording must be composed at read time"
        )
    # SPECIFIED, the other half: the wording is composed from the row's
    # own facts, so a later composer can phrase this same row differently.
    assert _normalised(STEP_A_NAME) in _normalised(composed.what)


# ---------------------------------------------------------------------------
# R8: retention
# ---------------------------------------------------------------------------


async def test_removing_the_launch_record_removes_its_journal(
    sessions: async_sessionmaker[AsyncSession],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Removing the launch record removes its journal.

    WHEN a launch record is removed
    THEN its journal entries are removed with it, and no entry is left
    referencing a launch that no longer exists.
    """
    product_id = await registered_product_id()
    survivor_id = await registered_product_id()
    await _start_and_record(
        sessions, product_id, ((STEP_A, FIRST_AT), (STEP_B, SECOND_AT))
    )
    await _start_and_record(sessions, survivor_id, ((STEP_A, FIRST_AT),))

    # The premise: there is a journal to remove.
    assert len(await _rows(sessions, product_id)) >= 2

    async with sessions() as session:
        await session.execute(
            text("DELETE FROM launch_positions WHERE product_id = CAST(:pid AS uuid)"),
            {"pid": product_id.value},
        )
        await session.commit()

    # SPECIFIED: the journal entries are removed with the launch record —
    # the retention rule's other half, and the `ON DELETE CASCADE` of
    # design.md Decision 4.
    assert await _rows(sessions, product_id) == []
    # SPECIFIED by implication: another launch's journal is untouched —
    # the cascade is keyed by launch, not a table-wide sweep.
    assert await _rows(sessions, survivor_id) != []

    async with sessions() as session:
        orphans = await session.execute(
            text(
                f"SELECT count(*) FROM {JOURNAL_TABLE} entry "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM launch_positions position "
                "  WHERE position.product_id = entry.product_id"
                ")"
            )
        )
    # SPECIFIED: no entry is left referencing a launch that no longer
    # exists — asserted over the whole table, not only this launch.
    assert orphans.scalar_one() == 0
