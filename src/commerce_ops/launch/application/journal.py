"""The launch journal's facts, read back as facts — never as prose.

Implements `launch-journal` (`openspec/changes/add-launch-journal/`,
later revised by `structure-the-launch-journal-table` and
`raw-out-the-journal-columns`).

Two shapes live here:

- `JournalOccurrence` is what an accepted command appends — the facts of
  one occurrence, a field per fact, never a sentence about them.
- `JournalEntry` is what a reader gets back: the same facts, still
  unworded, plus a short `label` and a `category` composed from them at
  read time (design.md Decision 5 of `structure-the-launch-journal-table`
  — improving a label or a category rule improves every entry of that
  kind already appended). Earlier revisions of this module also composed
  a `what` sentence and a `cause` sentence; `raw-out-the-journal-columns`
  removed both; a reader wanting the shape of an occurrence one kind at a
  time reads `kind`, `subject` and the per-kind fact fields below
  directly; no field here is ever a sentence about another.

`occurred_at` is the moment the occurrence *names*, and is `None`
exactly for the occurrences that name none — a start, a gate opening, a
graduation, a date move, a refused advance. The store stamps those from
the database clock, because the application layer holds no clock
(design.md Decision 6). Every other kind carries the moment the work
happened: a `Provenance.when` or a `GateApproval.when`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from commerce_ops.shared.domain.identity import ProductId

KIND_LAUNCH_STARTED: Final = "launch-started"
KIND_STEP_OUTCOME_RECORDED: Final = "step-outcome-recorded"
KIND_GATE_APPROVAL_RECORDED: Final = "gate-approval-recorded"
KIND_GATE_OPENED: Final = "gate-opened"
KIND_LAUNCH_GRADUATED: Final = "launch-graduated"
KIND_LAUNCH_DATE_MOVED: Final = "launch-date-moved"
KIND_ADVANCE_REFUSED: Final = "advance-refused"

JOURNAL_KINDS: Final[tuple[str, ...]] = (
    KIND_LAUNCH_STARTED,
    KIND_STEP_OUTCOME_RECORDED,
    KIND_GATE_APPROVAL_RECORDED,
    KIND_GATE_OPENED,
    KIND_LAUNCH_GRADUATED,
    KIND_LAUNCH_DATE_MOVED,
    KIND_ADVANCE_REFUSED,
)
"""The occurrence vocabulary — one kind per accepted command, plus the
refusal. Mirrored as a check constraint on the table
(`models.LAUNCH_JOURNAL_KINDS`), so a ninth kind is a migration."""


@dataclass(frozen=True, slots=True)
class JournalOccurrence:
    """One occurrence, as facts. Never a sentence about it.

    The field set is exactly the table's fact columns; a `sentence`,
    `message` or `rendered` field is precisely what this shape forbids.
    `details` holds what distinguishes one occurrence of a kind from
    another — an outcome and its reason, a decision and its posture, two
    dates, the conditions that blocked an advance.
    """

    product_id: ProductId
    kind: str
    occurred_at: datetime | None = None
    actor: str | None = None
    source: str | None = None
    subject_id: str | None = None
    subject_label: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One entry as a reader gets it — every fact the occurrence carried,
    unworded, plus a composed `label` and `category` (below).

    `subject` is the occurrence's captured label where it has one, its
    identifier otherwise; `None` for the three kinds with nothing to
    name (`launch-started`, `launch-date-moved`) — see the field-by-field
    table below for which kind populates which field.

    Every other field beyond `kind`/`when`/`subject`/`source`/`actor`/
    `label`/`category` is a raw fact read straight out of the stored
    occurrence's `details`, present only for the kind(s) that populate
    it, `None` (or, for `unsatisfied`, an empty tuple) everywhere else:

    | Field               | Populated by                              |
    |---------------------|--------------------------------------------|
    | `playbook_version`  | `launch-started`                            |
    | `outcome`, `reason`  | `step-outcome-recorded`                     |
    | `evidence`          | `step-outcome-recorded`                     |
    | `decision`          | `gate-approval-recorded`                    |
    | `posture`           | `gate-approval-recorded` (graduating), `launch-graduated` |
    | `standing_at`       | `gate-opened`                               |
    | `previous_date`, `new_date` | `launch-date-moved`                 |
    | `unsatisfied`       | `advance-refused`                           |
    """

    kind: str
    when: datetime
    label: str
    category: str
    subject: str | None
    source: str | None
    actor: str | None
    playbook_version: str | None
    outcome: str | None
    reason: str | None
    evidence: str | None
    decision: str | None
    posture: str | None
    standing_at: str | None
    previous_date: str | None
    new_date: str | None
    unsatisfied: tuple[str, ...]


def _detail(occurrence: JournalOccurrence, key: str) -> object | None:
    return occurrence.details.get(key)


def _detail_str(occurrence: JournalOccurrence, key: str) -> str | None:
    value = _detail(occurrence, key)
    return None if value is None else str(value)


def _unsatisfied(occurrence: JournalOccurrence) -> tuple[str, ...]:
    value = _detail(occurrence, "unsatisfied")
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


#: A short, fixed label per journal kind — what a table's kind column
#: shows in place of the raw kind string. One entry per `JOURNAL_KINDS`
#: member; `_label` matches exhaustively, raising on an unmapped kind
#: rather than falling through, mirroring the discipline `JOURNAL_KINDS`'
#: own check constraint applies at the schema level (design.md Risks).
_KIND_LABEL: Final[Mapping[str, str]] = {
    KIND_LAUNCH_STARTED: "Start",
    KIND_STEP_OUTCOME_RECORDED: "Outcome",
    KIND_GATE_APPROVAL_RECORDED: "Approval",
    KIND_GATE_OPENED: "Gate Opened",
    KIND_LAUNCH_GRADUATED: "Graduation",
    KIND_LAUNCH_DATE_MOVED: "Date Moved",
    KIND_ADVANCE_REFUSED: "Refusal",
}


def _label(occurrence: JournalOccurrence) -> str:
    try:
        return _KIND_LABEL[occurrence.kind]
    except KeyError:
        raise ValueError(
            f"no label mapped for journal kind '{occurrence.kind}'"
        ) from None


def _is_rejecting(occurrence: JournalOccurrence) -> bool:
    """Whether a `gate-approval-recorded` occurrence carries a rejecting
    decision, as opposed to an approving one."""
    return _detail(occurrence, "decision") == "rejecting"


def _is_blocked_outcome(occurrence: JournalOccurrence) -> bool:
    """Whether a `step-outcome-recorded` occurrence names an outcome that
    reads as trouble — `Blocked` or `Refused` — as opposed to one of the
    domain's other four `StepOutcome` names."""
    return _detail(occurrence, "outcome") in ("Blocked", "Refused")


def _category(occurrence: JournalOccurrence) -> str:
    """One of four coarse groupings a reader scans a table by.

    A pure function of `kind`, except for the two kinds that can carry a
    negative outcome: `gate-approval-recorded` (blocked where rejecting)
    and `step-outcome-recorded` (blocked where `Blocked`/`Refused`) —
    design.md Decisions, "the whole point is to let a reader spot
    trouble without reading every sentence." Matched exhaustively, same
    discipline as `_label`.
    """
    kind = occurrence.kind
    if kind == KIND_LAUNCH_DATE_MOVED:
        return "admin"
    if kind == KIND_ADVANCE_REFUSED:
        return "blocked"
    if kind == KIND_GATE_APPROVAL_RECORDED:
        return "blocked" if _is_rejecting(occurrence) else "judgment"
    if kind == KIND_STEP_OUTCOME_RECORDED:
        return "blocked" if _is_blocked_outcome(occurrence) else "progression"
    if kind in (KIND_LAUNCH_STARTED, KIND_GATE_OPENED, KIND_LAUNCH_GRADUATED):
        return "progression"
    raise ValueError(f"no category rule for journal kind '{kind}'")


def compose(occurrence: JournalOccurrence) -> JournalEntry:
    """One stored occurrence, read back as an entry.

    Composes only `label` and `category` — every other field is the
    occurrence's own fact, carried across unchanged. A stamped
    `occurred_at` is guaranteed by the store, which fills the ones the
    application layer leaves `None`; an unstamped occurrence here would
    be a repository that did not do its job, so this asserts rather than
    inventing a moment of its own.
    """
    assert occurrence.occurred_at is not None, (
        f"a stored journal occurrence must carry the moment it names; the "
        f"store stamps the ones that name none (design.md Decision 6), and "
        f"this '{occurrence.kind}' occurrence arrived unstamped"
    )
    return JournalEntry(
        kind=occurrence.kind,
        when=occurrence.occurred_at,
        label=_label(occurrence),
        category=_category(occurrence),
        subject=occurrence.subject_label or occurrence.subject_id,
        source=occurrence.source,
        actor=occurrence.actor,
        playbook_version=_detail_str(occurrence, "playbook_version"),
        outcome=_detail_str(occurrence, "outcome"),
        reason=_detail_str(occurrence, "reason"),
        evidence=_detail_str(occurrence, "evidence"),
        decision=_detail_str(occurrence, "decision"),
        posture=_detail_str(occurrence, "posture"),
        standing_at=_detail_str(occurrence, "standing_at"),
        previous_date=_detail_str(occurrence, "previous"),
        new_date=_detail_str(occurrence, "new"),
        unsatisfied=_unsatisfied(occurrence),
    )
