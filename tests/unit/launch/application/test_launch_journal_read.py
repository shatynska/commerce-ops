"""Tests for reading one launch's journal, and for entries storing facts
rather than rendered prose.

Derived from the delta spec:
openspec/changes/add-launch-journal/specs/launch-journal/spec.md, later
revised twice — `structure-the-launch-journal-table` added `label` and
`category`, and `raw-out-the-journal-columns` removed the `what`/`cause`
sentences this file originally tested, replacing them with per-kind raw
fact fields (`outcome`, `reason`, `decision`, ...) read straight off the
occurrence. The two scenarios below now named *An entry reports its
distinguishing facts as their own fields* and *A kind's distinguishing
facts are absent from an entry of another kind* are that revision's
replacements for this file's original *An entry reports what occurred,
when, and what caused it* / *An occurrence naming nobody reports the
command as its cause* — same two positions in the requirement, rewritten
because the fields they asserted on no longer exist.

Covers, of that spec's ADDED requirements:

- *An entry stores structure, never rendered prose* — both scenarios,
  now exercised against `label`/`category` (the only fields still
  composed at read time) rather than against the removed `what`.
- *One launch's journal is readable, most recent first* — five of its
  seven scenarios: the two above, *An out-of-scope launch reports an
  empty journal*, *A launch with nothing recorded reports an empty
  journal*, and *A product with no launch record reports an empty
  journal*.

The two ordering scenarios of that requirement — *A launch's journal is
read most recent first* and *Entries naming the same moment report the
later append first* — are **not** here. Ordering is the repository's
(`tasks.md` 6.2: `occurred_at DESC, sequence DESC`), and the append
sequence that breaks a tie exists only in the database. A fake that
sorted them here would be testing the fake; one that did not would demand
the use case re-sort, which no artifact asks of it. Both are driven in
`tests/integration/launch/test_launch_journal_live.py`.

## Where composition happens is the point of the prose scenarios

`tasks.md` 1.2: *"Improved wording reaches entries already appended" is a
test about where composition happens, not about a particular sentence. It
passes only if the stored row holds no sentence — assert on what the
repository wrote, and compose through the read.*

So neither prose test asserts a sentence. They assert that the entry
handed to the port carries only fact fields, that the composed `what`
appears among none of them, and that the composition nonetheless draws on
those facts. Where no sentence is stored, improving the composer
necessarily improves every entry already appended — which is the
requirement, and the only half of it a test can observe without a second
version of the composer.

The same assertion is made against a real stored row in the integration
file named above; this is the fast half of it.

## Level

The application layer, fast mocked unit tier: `read_launch_journal` is an
application use case (`tasks.md` 7.1) and the composer lives beside it
(`design.md` Decision 5), so nothing lower can observe a composed entry.

## The interface under test does not exist yet, and its shape is INVENTED

Every test here is expected to fail on an absent target — an `ImportError`
for `read_launch_journal`. Per `ai-toolkit:testing`, that establishes only
absence.

Fixed by this change's artifacts: `read_launch_journal(journal, *,
product_id, scope)` (`tasks.md` 7.1); the read model
`JournalEntry(kind, what, when, cause)` (`design.md` Decision 5, whose
field names are the ones `add-launch-tracking-pages` stubbed); that
`cause` is the member and source where the occurrence names one and the
command where it names nobody (delta spec R7); that the three empty cases
are indistinguishable (`tasks.md` 7.2); and that entries naming no moment
are stamped by the store (`design.md` Decision 6), which is why
`FakeJournal` stamps them.

INVENTED, with correction points: the port being async (`FakeJournal`);
and that the read model is imported from `commerce_ops.launch.application`
(`tasks.md` 3.4 exports it, without fixing the module) — nothing here
imports it by name, so only the use case's import matters.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    move_launch_date,
    read_launch_journal,
    record_step_outcome,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
OTHER_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
UNLAUNCHED_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

RECORDED_AT: Final = datetime(2027, 7, 8, 16, 20, tzinfo=UTC)
STORE_STAMPED_AT: Final = datetime(2027, 7, 9, 10, 0, tzinfo=UTC)

RECORDER: Final = "Dana"
SOURCE: Final = "clickup"

LAUNCH_DATE: Final = date(2027, 12, 1)
MOVED_DATE: Final = date(2028, 1, 20)

TRACKED_STEP: Final = "listing.title-conforms"
TRACKED_STEP_NAME: Final = "Write the listing title to the conformance rules"

#: SPECIFIED (design.md Decision 4's table, tasks.md 3.1): what an entry
#: may carry. A field outside this set is a composed sentence or another
#: rendering, which R4 forbids storing.
FACT_FIELDS: Final = frozenset(
    {
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


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _normalised(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _flatten(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [text for held in value.values() for text in _flatten(held)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [text for held in value for text in _flatten(held)]
    return [str(value)]


def _stored_values(entry: object) -> list[str]:
    """Every value the entry stores, flattened — what a reader of the row
    would find there."""
    values: list[str] = []
    for name in ("kind", "actor", "source", "subject_id", "subject_label"):
        held = getattr(entry, name, None)
        if held is not None:
            values.append(str(held))
    values.extend(_flatten(getattr(entry, "details", None)))
    return values


def _is_product(value: object, product_id: ProductId) -> bool:
    return value == product_id or value == product_id.value


# ---------------------------------------------------------------------------
# Collaborators
# ---------------------------------------------------------------------------


class FakeJournal:
    """In-memory `LaunchJournal`.

    Two behaviours of the real repository are modelled because the read
    depends on them: an entry naming no moment is stamped by the store
    (`design.md` Decision 6), and `read` reports most recent first, the
    later append winning a tie (`tasks.md` 6.2). Neither is *tested* here
    — the ordering scenarios are in the integration file — but the read
    would otherwise be handed a shape the real port never produces.
    """

    def __init__(self, stamp_at: datetime = STORE_STAMPED_AT) -> None:
        self.appended: list[Any] = []
        self.stored: list[Any] = []
        self.rollbacks = 0
        self._stamp_at = stamp_at

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)
        stored = entry
        if (
            is_dataclass(entry)
            and not isinstance(entry, type)
            and getattr(entry, "occurred_at", None) is None
        ):
            stored = replace(entry, occurred_at=self._stamp_at)
        self.stored.append(stored)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        matching = [
            (getattr(entry, "occurred_at", None), sequence, entry)
            for sequence, entry in enumerate(self.stored)
            if _is_product(getattr(entry, "product_id", None), product_id)
        ]
        matching.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return tuple(entry for _, _, entry in matching)

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())


class FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self.playbook


# ---------------------------------------------------------------------------
# Playbook and launch fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{"identifier": TRACKED_STEP, "name": TRACKED_STEP_NAME, **overrides}
    )


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
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
    steps = (*(_hold(gate) for gate in SPECIFIED_GATE_ORDER), _step())
    return LaunchPlaybook(version="journal-v1", gates=gates, steps=steps)


def _started(playbook: LaunchPlaybook, product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": SOURCE,
        "who": RECORDER,
        "when": RECORDED_AT,
        "evidence": "ClickUp task closed with its checklist complete",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


async def _record_one_step_outcome(
    journal: FakeJournal, product_id: ProductId = PRODUCT_ID
) -> None:
    playbook = _playbook()
    await record_step_outcome(
        FakeLaunchStore(_started(playbook, product_id)),
        FakePlaybooks(playbook),
        product_id=product_id,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )


# ---------------------------------------------------------------------------
# R4: An entry stores structure, never rendered prose
# ---------------------------------------------------------------------------


async def test_an_entry_is_stored_as_facts() -> None:
    """Scenario: An entry is stored as facts.

    WHEN an entry is appended and inspected as stored
    THEN its kind, the moment it names, the identifiers and labels it
    concerned and its distinguishing values are each carried separately,
    and no composed sentence is among them.
    """
    journal = FakeJournal()
    await _record_one_step_outcome(journal)

    (entry,) = journal.appended
    # SPECIFIED: each carried separately — a field per fact, not one
    # blob and not one sentence.
    assert entry.kind == "step-outcome-recorded"
    assert entry.occurred_at == RECORDED_AT
    assert entry.subject_id == TRACKED_STEP
    assert entry.subject_label == TRACKED_STEP_NAME
    assert entry.actor == RECORDER
    assert entry.source == SOURCE
    assert isinstance(entry.details, Mapping)

    # SPECIFIED: no composed sentence is among them. The entry may carry
    # only fact fields; a `sentence`, `message` or `rendered` field is
    # exactly what this forbids.
    assert is_dataclass(entry), (
        "the appended entry must be a dataclass of facts (tasks.md 3.1); "
        f"it is {type(entry)!r}"
    )
    carried = {field.name for field in fields(entry)}
    assert carried <= FACT_FIELDS, (
        f"the entry carries fields outside the fact set: "
        f"{sorted(carried - FACT_FIELDS)}"
    )

    # SPECIFIED: and the composed label/category are not among the stored
    # values — they are produced at read time from them
    # (`raw-out-the-journal-columns`: every other field on `JournalEntry`
    # is now a raw pass-through of a stored fact, not a composition, so
    # `label`/`category` are the only fields left for this scenario to
    # exercise).
    (read,) = await read_launch_journal(
        journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )
    assert read.label
    assert read.label not in _stored_values(entry), (
        f"the composed label {read.label!r} was found among the stored "
        f"values {_stored_values(entry)!r} — the entry stores prose"
    )
    assert read.category
    assert read.category not in _stored_values(entry), (
        f"the composed category {read.category!r} was found among the "
        f"stored values {_stored_values(entry)!r} — the entry stores prose"
    )


async def test_improved_wording_reaches_entries_already_appended() -> None:
    """Scenario: Improved wording reaches entries already appended.

    WHEN the label or category rule composed for a kind of occurrence
    changes, and a launch's journal holding an entry of that kind from
    before the change is read
    THEN that entry reads with the new label or category.

    Read as `tasks.md` 1.2 directs: this is a test about *where*
    composition happens. It holds exactly when the stored entry carries
    no sentence and the read composes the label/category from the facts
    — because then the composer is the only source of that wording, and
    changing it changes every entry already appended. A test naming a
    particular label or category would instead freeze the wording this
    requirement exists to let improve; the second assertion below checks
    that the category draws on the entry's own outcome fact rather than
    checking its exact value against a fixed expectation.
    """
    journal = FakeJournal()
    await _record_one_step_outcome(journal)
    (entry,) = journal.appended

    (read,) = await read_launch_journal(
        journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )

    # SPECIFIED: nothing stored is a sentence about the occurrence — no
    # stored value is, or contains, the label or category the read
    # composed.
    for value in _stored_values(entry):
        assert read.label not in value, (
            f"the stored value {value!r} carries the composed label "
            f"{read.label!r}; the label must be composed at read time only"
        )
        assert read.category not in value, (
            f"the stored value {value!r} carries the composed category "
            f"{read.category!r}; the category must be composed at read "
            f"time only"
        )

    # SPECIFIED, the other half: the category is nonetheless composed
    # from what the entry carries — a `Satisfied` outcome (the fixture's
    # premise) composes `progression`; `test_launch_journal_categorization.py`
    # exercises the same rule composing `blocked` for `Blocked`/`Refused`,
    # so a better category rule has the fact it needs to categorize this
    # entry differently.
    assert entry.details.get("outcome") == "Satisfied", (
        "fixture premise: this test records a Satisfied outcome"
    )
    assert read.category == "progression", (
        f"the composed category {read.category!r} does not draw on the "
        f"entry's own outcome fact ({entry.details.get('outcome')!r})"
    )


# ---------------------------------------------------------------------------
# R7: One launch's journal is readable, most recent first
# ---------------------------------------------------------------------------


async def test_an_entry_reports_its_distinguishing_facts_as_their_own_fields() -> None:
    """Scenario: An entry reports its distinguishing facts as their own
    fields.

    WHEN a launch whose journal holds a step outcome recorded by a named
    member from a named source is read
    THEN that entry carries the moment it occurred as `when`, that member
    as `actor`, that source as `source`, and the recorded outcome and its
    reason as `outcome` and `reason`, each in its own field.
    """
    journal = FakeJournal()
    await _record_one_step_outcome(journal)

    (read,) = await read_launch_journal(
        journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )

    assert read.kind == "step-outcome-recorded"
    assert read.subject == TRACKED_STEP_NAME
    # SPECIFIED: when it occurred — the moment the occurrence named, not
    # the moment of the append (design.md Decision 6).
    assert read.when == RECORDED_AT
    # SPECIFIED: the member and the source, each in its own field.
    assert read.actor == RECORDER
    assert read.source == SOURCE
    # SPECIFIED: the recorded outcome and its reason, each in its own
    # field, not folded into a sentence with the subject or with each
    # other.
    assert read.outcome == "Satisfied"


async def test_a_kinds_distinguishing_facts_are_absent_from_an_entry_of_another_kind() -> (
    None
):
    """Scenario: A kind's distinguishing facts are absent from an entry
    of another kind.

    WHEN an entry of a kind that carries no `outcome`, `reason`,
    `decision`, `gate_id`, `standing_at`, `posture`, `playbook_version`,
    `previous_date` or `new_date` is read
    THEN each of those fields is `None` on that entry, rather than an
    empty string or a placeholder.

    A moved launch date is one of the four kinds that names nobody
    (design.md Decision 4: `move_launch_date` is never told who asked)
    and carries none of the other kinds' distinguishing facts either.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await move_launch_date(
        FakeLaunchStore(_started(playbook, PRODUCT_ID)),
        product_id=PRODUCT_ID,
        new_date=MOVED_DATE,
        journal=journal,
    )

    # The premise: the occurrence names nobody.
    (stored,) = journal.appended
    assert stored.actor is None, (
        "fixture premise: a moved launch date names no member "
        f"(design.md Decision 4); the entry carries actor={stored.actor!r}"
    )

    (read,) = await read_launch_journal(
        journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )

    # SPECIFIED: the previous and new dates ARE this kind's own facts...
    assert read.new_date == MOVED_DATE.isoformat()
    # ...but every other kind's distinguishing fact is absent, not a
    # placeholder.
    assert read.outcome is None
    assert read.reason is None
    assert read.decision is None
    # `gate_id` left the entry shape with `metric-attested`, its only
    # populator (`replace-metric-conditions-with-steps`), so there is no
    # longer a field here to assert absent.
    assert read.standing_at is None
    assert read.posture is None
    assert read.playbook_version is None
    assert read.unsatisfied == ()


async def test_an_out_of_scope_launch_reports_an_empty_journal() -> None:
    """Scenario: An out-of-scope launch reports an empty journal.

    WHEN a launch's journal is read on the behalf of a caller whose scope
    does not permit that product
    THEN an empty journal is reported, exactly as for a launch with
    nothing recorded.
    """
    journal = FakeJournal()
    await _record_one_step_outcome(journal)

    # The premise: this launch really does have a journal to hide.
    assert len(journal.appended) == 1

    refused = await read_launch_journal(
        journal,
        product_id=PRODUCT_ID,
        scope=AccessScope.permitting([OTHER_PRODUCT_ID]),
    )

    # SPECIFIED: an empty journal — never an error, and never a
    # distinguishable refusal, so a read cannot confirm the existence of
    # a launch the caller may not see.
    assert refused == ()
    empty_but_permitted = await read_launch_journal(
        FakeJournal(),
        product_id=PRODUCT_ID,
        scope=AccessScope.unrestricted(),
    )
    assert refused == empty_but_permitted


async def test_a_launch_with_nothing_recorded_reports_an_empty_journal() -> None:
    """Scenario: A launch with nothing recorded reports an empty journal.

    WHEN the journal of a launch that has nothing recorded is read — the
    state every launch predating the journal is in
    THEN an empty journal is reported, rather than an error.
    """
    reported = await read_launch_journal(
        FakeJournal(), product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )

    # SPECIFIED: empty, not an error. Every launch that predates the
    # migration is in this state for ever (design.md — Migration Plan).
    assert reported == ()


async def test_a_product_with_no_launch_record_reports_an_empty_journal() -> None:
    """Scenario: A product with no launch record reports an empty journal.

    WHEN the journal is read for a product identifier that has no launch
    record at all
    THEN an empty journal is reported, indistinguishable from that of a
    permitted launch with nothing recorded, rather than an error.
    """
    journal = FakeJournal()
    # A journal that holds entries — for a different launch. The product
    # asked about has no launch record at all.
    await _record_one_step_outcome(journal, product_id=OTHER_PRODUCT_ID)

    unlaunched = await read_launch_journal(
        journal,
        product_id=UNLAUNCHED_PRODUCT_ID,
        scope=AccessScope.unrestricted(),
    )
    nothing_recorded = await read_launch_journal(
        FakeJournal(),
        product_id=PRODUCT_ID,
        scope=AccessScope.unrestricted(),
    )

    # SPECIFIED: empty rather than an error, and indistinguishable from a
    # permitted launch with nothing recorded.
    assert unlaunched == ()
    assert unlaunched == nothing_recorded
