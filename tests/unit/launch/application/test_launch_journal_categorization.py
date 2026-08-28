"""Tests for the label and category composed onto each read journal
entry.

Derived from the delta spec:
openspec/changes/structure-the-launch-journal-table/specs/launch-journal/spec.md

Covers, of the MODIFIED requirement *One launch's journal is readable,
most recent first*, the six scenarios this change adds:

- *An entry reports a label naming its kind*
- *An entry reports a category*
- *A rejecting approval categorizes as blocked*
- *An approving approval categorizes as judgment*
- *A blocked or refused step outcome categorizes as blocked*
- *Every other step outcome categorizes as progression*

Plus one test that is not tied to a `#### Scenario:` block: that an
unmapped kind raises rather than silently omitting a label or category
(`tasks.md` 1.1, 1.3, 4.2; `design.md`'s first Risk/Trade-off, "A future
ninth journal kind lands without updating the label/category maps").
That test is DERIVED from those artifacts, not SPECIFIED by a scenario —
flagged as such below and reported as an unresolved-provenance note.

## What is not here, and why

The requirement's other five scenarios are unchanged by this delta and
already accounted for elsewhere, so they are not repeated in this file:

- *A launch's journal is read most recent first* and *Entries naming the
  same moment report the later append first* — ordering is the
  repository's own concern (`occurred_at DESC, sequence DESC`) and is
  deliberately exercised only at the integration tier
  (`tests/integration/launch/test_launch_journal_live.py`), per
  `test_launch_journal_read.py`'s own documented reasoning. Nothing about
  ordering changes here.
- *An entry reports what occurred, when, and what caused it* and *An
  occurrence naming nobody reports the command as its cause* — covered by
  `test_launch_journal_read.py::test_an_entry_reports_what_occurred_when_and_what_caused_it`
  and `::test_an_occurrence_naming_nobody_reports_the_command_as_its_cause`.
  Neither scenario's wording changed; `what`/`when`/`cause` are untouched
  by this change.
- The three empty-journal scenarios — covered by that same file's
  `test_an_out_of_scope_launch_reports_an_empty_journal`,
  `test_a_launch_with_nothing_recorded_reports_an_empty_journal` and
  `test_a_product_with_no_launch_record_reports_an_empty_journal`.
  Emptiness is untouched by this change.

## Level

The application layer, fast mocked unit tier, at the same seam
`test_launch_journal_read.py` uses: `read_launch_journal` over a fake
`LaunchJournal`, so the composed `label`/`category` are observed exactly
as a caller of the public use case would see them. `compose()` itself is
not imported here — it is not part of `commerce_ops.launch.application`'s
public surface (`AGENTS.md`: "a module's `application/__init__.py` is
its only public surface, enforced by `import-linter`").

## The interface under test does not exist yet

At review time `JournalEntry` is `JournalEntry(kind, what, when, cause)`
— it carries neither `label` nor `category`. Every test here is expected
to fail with an `AttributeError` on `.label` or `.category`. Per
`ai-toolkit:testing`, that establishes only absence, nothing about
whether these assertions are any good.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the four category values (`"progression"`,
`"judgment"`, `"blocked"`, `"admin"`) as plain strings, not CSS classes
(`design.md`, "Category is exposed as a plain string enum-like value");
the fork on `details["decision"]` (`"approving"` / `"rejecting"`) for
`gate-approval-recorded`; the fork on `details["outcome"]`
(`"Blocked"` / `"Refused"` versus the other four `StepOutcome` names) for
`step-outcome-recorded`; and that a `launch-started` occurrence
categorizes as progression regardless of its details (`design.md`'s
table).

INVENTED: constructing `JournalOccurrence` directly, rather than through
the domain's own commands (`record_step_outcome`, `approve_gate`, ...).
The label/category rule is a pure function of `(kind, details)` — stated
outright in `design.md`'s Decisions — so an occurrence built by hand
exercises exactly the same branch a domain-produced one would, without
the playbook/launch fixture weight `test_launch_journal_read.py` carries
for a different purpose (proving the facts a *command* records, not how
they are categorized). Correction point if a future kind's category ever
comes to depend on something beyond `details`. Also INVENTED: the literal
sentinel kind string used for the "unmapped kind" test
(`"a-future-ninth-kind"`) and that raising is observed through
`pytest.raises(Exception)` — the artifacts fix only that the maps must
raise, never the exception type.
"""

from __future__ import annotations

import uuid
from dataclasses import is_dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import JournalOccurrence, read_launch_journal
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
OCCURRED_AT: Final = datetime(2027, 7, 8, 16, 20, tzinfo=UTC)
STORE_STAMPED_AT: Final = datetime(2027, 7, 9, 10, 0, tzinfo=UTC)

#: SPECIFIED (design.md's Decisions): the four category values, exposed
#: as plain strings.
PROGRESSION: Final = "progression"
JUDGMENT: Final = "judgment"
BLOCKED: Final = "blocked"
ADMIN: Final = "admin"
ALL_CATEGORIES: Final = frozenset({PROGRESSION, JUDGMENT, BLOCKED, ADMIN})

#: The eight journal kinds (`JOURNAL_KINDS`), spelled literally rather
#: than imported — the constants (`KIND_STEP_OUTCOME_RECORDED`, ...) are
#: not exported from `commerce_ops.launch.application`, and
#: `test_launch_journal_read.py` already asserts against these same raw
#: strings (e.g. `entry.kind == "step-outcome-recorded"`).
KIND_STEP_OUTCOME_RECORDED: Final = "step-outcome-recorded"
KIND_GATE_APPROVAL_RECORDED: Final = "gate-approval-recorded"
KIND_LAUNCH_STARTED: Final = "launch-started"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class FakeJournal:
    """In-memory `LaunchJournal`, pared to what these tests need: append
    and read. No rollback behaviour is exercised here — the containment
    guarantees around a failed append belong to
    `launch-journal`'s other requirements, not to this one."""

    def __init__(self, stamp_at: datetime = STORE_STAMPED_AT) -> None:
        self.stored: list[Any] = []
        self._stamp_at = stamp_at

    async def append(self, entry: Any) -> None:
        stored = entry
        if (
            is_dataclass(entry)
            and not isinstance(entry, type)
            and getattr(entry, "occurred_at", None) is None
        ):
            stored = replace(entry, occurred_at=self._stamp_at)
        self.stored.append(stored)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(entry for entry in self.stored if entry.product_id == product_id)

    async def rollback(self) -> None:  # pragma: no cover - unused here
        pass


def _occurrence(kind: str, **overrides: Any) -> JournalOccurrence:
    attributes: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "kind": kind,
        "occurred_at": OCCURRED_AT,
        "details": {},
    }
    attributes.update(overrides)
    return JournalOccurrence(**attributes)


async def _read_one(occurrence: JournalOccurrence) -> Any:
    """Append one occurrence and read back the entry composed from it."""
    journal = FakeJournal()
    await journal.append(occurrence)
    (entry,) = await read_launch_journal(
        journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
    )
    return entry


async def _category_of(kind: str, **details: Any) -> str:
    entry = await _read_one(_occurrence(kind, details=details))
    return str(entry.category)


# ---------------------------------------------------------------------------
# An entry reports a label naming its kind
# ---------------------------------------------------------------------------


async def test_an_entry_reports_a_label_naming_its_kind() -> None:
    """Scenario: An entry reports a label naming its kind.

    WHEN any entry is read
    THEN it carries a short label naming its kind, drawn from the fixed
    set of labels rather than the raw kind string.

    The exact wording is not fixed by the artifacts (`design.md`
    considers and rejects fixing it to a mechanical transform of the
    kind) — only that it exists, is not the raw kind string, and is
    determined by kind alone (a fixed *set*, one per kind).
    """
    entry = await _read_one(
        _occurrence(KIND_STEP_OUTCOME_RECORDED, details={"outcome": "Satisfied"})
    )

    # SPECIFIED: a label is carried at all.
    assert entry.label, "the entry carries no label"
    # SPECIFIED: drawn from a fixed set rather than the raw kind string —
    # the raw kind string is exactly what a label exists to replace.
    assert entry.label != entry.kind, (
        f"the label {entry.label!r} is the raw kind string {entry.kind!r} "
        "verbatim; the requirement is a short label in its place"
    )

    # DERIVED: "fixed set, one per kind" means the label is a function of
    # kind alone — two occurrences of the same kind, differing only in
    # details irrelevant to labelling, read with the same label.
    other = await _read_one(
        _occurrence(
            KIND_STEP_OUTCOME_RECORDED,
            details={"outcome": "InProgress"},
            subject_id="a-different-step",
        )
    )
    assert other.label == entry.label, (
        f"two entries of the same kind carry different labels "
        f"({entry.label!r} vs {other.label!r}); a label is fixed per kind, "
        "not derived per entry"
    )


# ---------------------------------------------------------------------------
# An entry reports a category
# ---------------------------------------------------------------------------


async def test_an_entry_reports_a_category() -> None:
    """Scenario: An entry reports a category.

    WHEN any entry is read
    THEN it carries one of the four categories — progression, judgment,
    blocked, admin.
    """
    entry = await _read_one(_occurrence(KIND_LAUNCH_STARTED, details={}))

    assert entry.category in ALL_CATEGORIES, (
        f"the entry's category {entry.category!r} is not one of the four "
        f"fixed categories {sorted(ALL_CATEGORIES)}"
    )


# ---------------------------------------------------------------------------
# gate-approval-recorded: the rejecting/approving fork, exhaustively
# ---------------------------------------------------------------------------


async def test_a_rejecting_approval_categorizes_as_blocked() -> None:
    """Scenario: A rejecting approval categorizes as blocked.

    WHEN a `gate-approval-recorded` entry carrying a rejecting decision
    is read
    THEN it is categorized blocked, not judgment.
    """
    category = await _category_of(KIND_GATE_APPROVAL_RECORDED, decision="rejecting")

    assert category == BLOCKED, (
        f"a rejecting gate-approval-recorded entry categorizes as "
        f"{category!r}, not {BLOCKED!r}"
    )
    assert category != JUDGMENT


async def test_an_approving_approval_categorizes_as_judgment() -> None:
    """Scenario: An approving approval categorizes as judgment.

    WHEN a `gate-approval-recorded` entry carrying an approving decision
    is read
    THEN it is categorized judgment, not blocked.
    """
    category = await _category_of(KIND_GATE_APPROVAL_RECORDED, decision="approving")

    assert category == JUDGMENT, (
        f"an approving gate-approval-recorded entry categorizes as "
        f"{category!r}, not {JUDGMENT!r}"
    )
    assert category != BLOCKED


# ---------------------------------------------------------------------------
# step-outcome-recorded: the Blocked/Refused fork, exhaustively over all
# six StepOutcome names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["Blocked", "Refused"])
async def test_a_blocked_or_refused_step_outcome_categorizes_as_blocked(
    outcome: str,
) -> None:
    """Scenario: A blocked or refused step outcome categorizes as
    blocked.

    WHEN a `step-outcome-recorded` entry naming the outcome `Blocked`, or
    one naming the outcome `Refused`, is read
    THEN each is categorized blocked, not progression.
    """
    category = await _category_of(KIND_STEP_OUTCOME_RECORDED, outcome=outcome)

    assert category == BLOCKED, (
        f"a step-outcome-recorded entry naming {outcome!r} categorizes as "
        f"{category!r}, not {BLOCKED!r}"
    )
    assert category != PROGRESSION


@pytest.mark.parametrize(
    "outcome", ["NotStarted", "InProgress", "Satisfied", "NotApplicable"]
)
async def test_every_other_step_outcome_categorizes_as_progression(
    outcome: str,
) -> None:
    """Scenario: Every other step outcome categorizes as progression.

    WHEN a `step-outcome-recorded` entry naming the outcome `NotStarted`,
    `InProgress`, `Satisfied`, or `NotApplicable` is read
    THEN it is categorized progression, not blocked.
    """
    category = await _category_of(KIND_STEP_OUTCOME_RECORDED, outcome=outcome)

    assert category == PROGRESSION, (
        f"a step-outcome-recorded entry naming {outcome!r} categorizes as "
        f"{category!r}, not {PROGRESSION!r}"
    )
    assert category != BLOCKED


# ---------------------------------------------------------------------------
# The exhaustive-match discipline: DERIVED from tasks.md 1.1/1.3/4.2 and
# design.md's Risks/Trade-offs, not from a `#### Scenario:` block.
# ---------------------------------------------------------------------------


async def test_an_unmapped_kind_raises_rather_than_omitting_label_or_category() -> None:
    """DERIVED (not SPECIFIED): an unmapped kind raises.

    `tasks.md` 1.1 and 1.3 direct both the label map and the category
    rule to be "matched exhaustively (raise on an unmapped kind rather
    than falling through)" — the same discipline `JOURNAL_KINDS`' own
    check constraint already applies at the schema level. `design.md`'s
    first Risk names exactly this case: a future ninth kind landing
    without both maps being updated.

    Unreachable through any accepted command today (`JOURNAL_KINDS`
    closes the vocabulary at eight), which is why this occurrence is
    built by hand rather than through a launch: the day it becomes
    reachable is the day a ninth kind is added without updating the
    label/category maps, and a silently-omitted label or category is
    exactly the failure this discipline exists to prevent.
    """
    occurrence = _occurrence("a-future-ninth-kind", details={})
    journal = FakeJournal()
    await journal.append(occurrence)

    with pytest.raises(Exception):  # noqa: B017 - artifacts fix no exception type
        await read_launch_journal(
            journal, product_id=PRODUCT_ID, scope=AccessScope.unrestricted()
        )
