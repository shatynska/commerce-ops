"""The launch journal's facts, and the wording composed from them.

Implements `launch-journal` (`openspec/changes/add-launch-journal/`).

Two shapes live here, and the distinction between them is the whole of
the capability's "an entry stores structure, never rendered prose":

- `JournalOccurrence` is what an accepted command appends — the facts of
  one occurrence, a field per fact, never a sentence about them.
- `JournalEntry` is what a reader gets back, and its `what` and `cause`
  are **composed here, at read time**, from those facts. Improving a
  sentence therefore improves every entry of that kind already appended
  (design.md Decision 5); nothing about how an occurrence reads is
  frozen at the moment it is appended.

`occurred_at` is the moment the occurrence *names*, and is `None`
exactly for the occurrences that name none — a start, a gate opening, a
graduation, a date move, a refused advance. The store stamps those from
the database clock, because the application layer holds no clock
(design.md Decision 6). Every other kind carries the moment the work
happened: a `Provenance.when`, a `GateApproval.when`, a
`MetricAttestation.when`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from commerce_ops.shared.domain.identity import ProductId

KIND_LAUNCH_STARTED: Final = "launch-started"
KIND_STEP_OUTCOME_RECORDED: Final = "step-outcome-recorded"
KIND_METRIC_ATTESTED: Final = "metric-attested"
KIND_GATE_APPROVAL_RECORDED: Final = "gate-approval-recorded"
KIND_GATE_OPENED: Final = "gate-opened"
KIND_LAUNCH_GRADUATED: Final = "launch-graduated"
KIND_LAUNCH_DATE_MOVED: Final = "launch-date-moved"
KIND_ADVANCE_REFUSED: Final = "advance-refused"

JOURNAL_KINDS: Final[tuple[str, ...]] = (
    KIND_LAUNCH_STARTED,
    KIND_STEP_OUTCOME_RECORDED,
    KIND_METRIC_ATTESTED,
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
    """One entry as a reader gets it: what occurred, when, and what
    caused it — the wording composed from the stored facts.

    `label` and `category` are composed here too, the same way `what`
    and `cause` are: a short name for the kind, and one of four coarse
    groupings (`progression`, `judgment`, `blocked`, `admin`) a reader
    scans a table by. Neither is stored.

    `subject`, `source` and `actor` are the raw facts underlying `what`
    and `cause`, carried through unworded rather than folded into a
    sentence — a reader who wants the identifier or the recorder rather
    than the prose about them reads these directly. `None` where the
    occurrence carries none: `subject` for the four kinds with nothing to
    name, `source`/`actor` for the four kinds naming no one
    (`_COMMAND_CAUSE`'s own set, `launch-graduated`'s `actor`-without-
    `source` case included).
    """

    kind: str
    what: str
    when: datetime
    cause: str
    label: str
    category: str
    subject: str | None
    source: str | None
    actor: str | None


def _detail(occurrence: JournalOccurrence, key: str) -> object | None:
    return occurrence.details.get(key)


def _text(value: object | None) -> str:
    return "" if value is None else str(value)


def _subject(occurrence: JournalOccurrence) -> str:
    """How to name the thing an occurrence concerned: its captured label
    where it has one, its identifier otherwise.

    The label is read off the entry rather than re-resolved, which is
    what keeps an entry legible after the served playbook has moved on.
    """
    return occurrence.subject_label or occurrence.subject_id or "the launch"


def _what(occurrence: JournalOccurrence) -> str:
    kind = occurrence.kind
    if kind == KIND_LAUNCH_STARTED:
        version = _text(_detail(occurrence, "playbook_version"))
        return f"the launch was started against playbook version {version}"
    if kind == KIND_STEP_OUTCOME_RECORDED:
        outcome = _text(_detail(occurrence, "outcome"))
        reason = _detail(occurrence, "reason")
        recorded = f"'{_subject(occurrence)}' was recorded {outcome}"
        return f"{recorded} — {reason}" if reason else recorded
    if kind == KIND_METRIC_ATTESTED:
        gate = _text(_detail(occurrence, "gate_id"))
        return (
            f"the metric condition '{_subject(occurrence)}' was attested "
            f"on the {gate} gate"
        )
    if kind == KIND_GATE_APPROVAL_RECORDED:
        decision = _text(_detail(occurrence, "decision"))
        return f"a {decision} decision was recorded on the {_subject(occurrence)} gate"
    if kind == KIND_GATE_OPENED:
        standing = _text(_detail(occurrence, "standing_at"))
        opened = f"the {_subject(occurrence)} gate opened"
        return f"{opened}; the launch now stands at {standing}" if standing else opened
    if kind == KIND_LAUNCH_GRADUATED:
        posture = _text(_detail(occurrence, "posture"))
        return f"the launch graduated, steady-state posture '{posture}'"
    if kind == KIND_LAUNCH_DATE_MOVED:
        previous = _detail(occurrence, "previous")
        moved_to = _text(_detail(occurrence, "new"))
        if previous is None:
            return f"the launch date was set to {moved_to}"
        return f"the launch date was moved from {previous} to {moved_to}"
    if kind == KIND_ADVANCE_REFUSED:
        blocked_by = _detail(occurrence, "unsatisfied")
        conditions = blocked_by if isinstance(blocked_by, (list, tuple)) else ()
        named = ", ".join(str(item) for item in conditions)
        return (
            f"an advance past the {_subject(occurrence)} gate was refused, "
            f"waiting on: {named}"
        )
    return f"an occurrence of kind '{kind}' was recorded"


#: A short, fixed label per journal kind — what a table's kind column
#: shows in place of the raw kind string. One entry per `JOURNAL_KINDS`
#: member; `_label` matches exhaustively, raising on an unmapped kind
#: rather than falling through, mirroring the discipline `JOURNAL_KINDS`'
#: own check constraint applies at the schema level (design.md Risks).
_KIND_LABEL: Final[Mapping[str, str]] = {
    KIND_LAUNCH_STARTED: "Start",
    KIND_STEP_OUTCOME_RECORDED: "Outcome",
    KIND_METRIC_ATTESTED: "Attestation",
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
    if kind == KIND_METRIC_ATTESTED:
        return "judgment"
    if kind == KIND_STEP_OUTCOME_RECORDED:
        return "blocked" if _is_blocked_outcome(occurrence) else "progression"
    if kind in (KIND_LAUNCH_STARTED, KIND_GATE_OPENED, KIND_LAUNCH_GRADUATED):
        return "progression"
    raise ValueError(f"no category rule for journal kind '{kind}'")


#: How to name the command that produced an occurrence naming nobody.
#: Four of the eight kinds are in this position — the use case is simply
#: never told who asked (design.md Decision 4, "Which kinds carry an
#: actor").
_COMMAND_CAUSE: Final[Mapping[str, str]] = {
    KIND_LAUNCH_STARTED: "a recorded launch start",
    KIND_GATE_OPENED: "an advance past the gate",
    KIND_LAUNCH_DATE_MOVED: "a recorded launch date move",
    KIND_ADVANCE_REFUSED: "a refused advance past the gate",
}


def _cause(occurrence: JournalOccurrence) -> str:
    """What brought the occurrence about.

    The person and the source where the occurrence names one; the
    command that produced it where it names nobody. Never empty — a
    reader scanning a mixed list learns either who did this or which
    command did.
    """
    if occurrence.actor is not None:
        attributed = f"recorded by {occurrence.actor}"
        if occurrence.source is not None:
            attributed = f"{attributed} from {occurrence.source}"
        evidence = _detail(occurrence, "evidence")
        return f"{attributed}: {evidence}" if evidence else attributed
    return _COMMAND_CAUSE.get(occurrence.kind, f"a recorded {occurrence.kind}")


def compose(occurrence: JournalOccurrence) -> JournalEntry:
    """One stored occurrence, worded.

    A stamped `occurred_at` is guaranteed by the store, which fills the
    ones the application layer leaves `None`; an unstamped occurrence
    here would be a repository that did not do its job, so this asserts
    rather than inventing a moment of its own.
    """
    assert occurrence.occurred_at is not None, (
        f"a stored journal occurrence must carry the moment it names; the "
        f"store stamps the ones that name none (design.md Decision 6), and "
        f"this '{occurrence.kind}' occurrence arrived unstamped"
    )
    return JournalEntry(
        kind=occurrence.kind,
        what=_what(occurrence),
        when=occurrence.occurred_at,
        cause=_cause(occurrence),
        label=_label(occurrence),
        category=_category(occurrence),
        subject=occurrence.subject_label or occurrence.subject_id,
        source=occurrence.source,
        actor=occurrence.actor,
    )
