"""A recorded step outcome may carry the finding that produced it
(`launch-instance`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-instance/spec.md`

Covers, from its one ADDED requirement *A recording may carry the finding
that produced it*, six of its nine scenarios:

- A recording carries the finding that produced it (`tasks.md` 1.1)
- A recording made with no finding carries none (1.2)
- An absent finding is distinguishable from an empty value (1.3)
- A finding with no comment is carried as such (1.4)
- Evidence is unchanged by what is carried beside it (1.7)
- A later recording replaces the carried finding (1.6)

The requirement's other three scenarios are stated over something the
aggregate cannot observe and live elsewhere:

- *A carried finding reaches the launch report* —
  `tests/unit/launch/application/test_launch_report_carried_finding.py`
  (`tasks.md` 1.8).
- *An unreadable stored finding does not fail the read* and *A recording
  made before this capability reads as carrying nothing* —
  `tests/unit/launch/infrastructure/driven/test_launch_progress_finding_rows.py`
  (`tasks.md` 1.5 and 1.9). `tasks.md` groups 1.5 under the domain tier;
  it is written at the row mapping instead, because the domain carries
  no *stored* representation that can be unreadable and no *read* that
  could fail — `tasks.md` 2.8 assigns both to the repositories. The
  deviation and its reason are recorded in `test-manifest.md`.

See `test-manifest.md` at the change root for the full accounting of all
28 scenarios in this change.

## Level

Every scenario above is stated over *a recording* — what it carries, what
it does not, and what a later one replaces. The `Launch` aggregate with
no I/O is the smallest unit that can observe all of them, which is the
level `test_launch_run.py` already established for step-outcome
recording.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The finding's three parts are the **field** the value was written to,
  the **value**, and the **comment** (delta; `design.md`, *One `jsonb`
  column per store*; `tasks.md` 2.5, which spells the stored payload
  `{"field": ..., "value": ..., "comment": ...}`).
- "Carries nothing" is exactly one state, and an empty *value* lives
  inside a finding that exists (`tasks.md` 2.5, `design.md`).
- A value that is absent or null is not a present finding (delta).
- An absent comment is distinct from an empty-text comment (delta).
- A later recording replaces the carried finding, including with none
  (`tasks.md` 2.9).

INVENTED, each with its correction point named below and recorded in
`test-manifest.md`:

- **How a recording is given a finding.** No artifact fixes the keyword.
  `_record()` probes `record_step_outcome`'s signature for one of
  `_FINDING_KWARGS` and fails loudly rather than recording without one,
  which would make every assertion below vacuous.
- **How a carried finding is spelled in the domain.** `_carry()` uses a
  value type exported by `launch_run` under one of `_FINDING_TYPES` if
  one exists, and otherwise the mapping `tasks.md` 2.5 spells. `_read()`
  reads either shape back.
- **That an absent comment and a null comment are one state.** The delta
  distinguishes *absent* from *empty text* and says nothing about null;
  `Success.comment` is already `str | None = None`, so `None` is read
  here as the spelling of absent. What the tests assert is only that
  absent is not `""`.
- The fixture playbook, gates, step identifiers, product identifier and
  timestamps, carried unchanged from `test_launch_run.py`'s own
  documented assumptions.

Correcting any of those is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: what a recording carries, what it does not, and what a later
recording leaves behind.

## Expected first-run state

**Absent target.** No recording can carry a finding today: `StepProgress`
has `outcome` and `provenance` only, and `record_step_outcome` accepts no
finding (`tasks.md` 2.5 and 2.9 add both). Every test here is expected to
fail through `_record()`'s or `_finding_attr()`'s loud probe. Per
`ai-toolkit:testing` that establishes absence and nothing about whether
these assertions are any good.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped (against the seeded `commerce_ops_screen_test`
database, so the tier genuinely ran).
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain import launch_run
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InProgress,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fixtures import STEP_ID, product_id
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold

PRODUCT_ID: Final = product_id()
WHEN: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LATER: Final = datetime(2027, 1, 7, 9, 30, tzinfo=UTC)

#: The handler's produced text, which becomes the recording's evidence.
EVIDENCE: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration."
)
FIELD: Final = "sub_category"
VALUE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = "Rejected alternative: Home & Kitchen > Home Decor."

#: A comment that is *absent*, as distinct from one that is empty text.
_ABSENT: Final = object()
_UNSET: Final = object()


# ---------------------------------------------------------------------------
# Domain fixtures — carried from `test_launch_run.py`
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": "listing.subcategory_advisor",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        assignees=("prs_01HQ8Z6M4A",),
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        _step(STEP_ID),
        version="finding-v1",
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook, launch_date=None)
    return launch


def _provenance(evidence: str = EVIDENCE, when: datetime = WHEN) -> Provenance:
    return Provenance(
        source="automated",
        who="listing.subcategory_advisor",
        when=when,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# The carried finding, reached through this file's correction points
# ---------------------------------------------------------------------------

#: The keyword `record_step_outcome` is assumed to accept for a finding.
_FINDING_KWARGS: Final = ("finding", "carried_finding", "kept_finding")

#: A value type `launch_run` may export for the carried finding. Where it
#: exports none, the mapping `tasks.md` 2.5 spells is used instead.
_FINDING_TYPES: Final = (
    "CarriedFinding",
    "RecordedFinding",
    "KeptFinding",
    "Finding",
)

#: The attribute a `StepProgress` is assumed to expose it under.
_FINDING_ATTRS: Final = ("finding", "carried_finding", "kept_finding")


@dataclass(frozen=True)
class _Carried:
    """A carried finding as this file reads it back, whatever shape the
    implementation stores it in."""

    field: Any
    value: Any
    comment: Any


def _carry(field: str, value: Any, comment: Any = _ABSENT) -> Any:
    """The argument a recording is given to carry a finding.

    INVENTED shape; the single correction point for how a finding is
    spelled. Prefers a value type the domain exports, and otherwise the
    mapping `tasks.md` 2.5 names.
    """
    parts: dict[str, Any] = {"field": field, "value": value}
    if comment is not _ABSENT:
        parts["comment"] = comment
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            return found(**parts)
    return parts


def _finding_kwarg() -> str:
    accepted = set(inspect.signature(Launch.record_step_outcome).parameters)
    for name in _FINDING_KWARGS:
        if name in accepted:
            return name
    pytest.fail(
        "`Launch.record_step_outcome` accepts no keyword for a carried "
        f"finding among {list(_FINDING_KWARGS)}; its parameters are "
        f"{sorted(accepted)} — correct `_FINDING_KWARGS` to the "
        "implemented keyword"
    )


def _record(
    launch: Launch,
    playbook: LaunchPlaybook,
    *,
    step_id: str = STEP_ID,
    outcome: Any = Satisfied,
    provenance: Provenance | None = None,
    finding: Any = _UNSET,
) -> tuple[Any, ...]:
    """Record an outcome, optionally carrying a finding.

    `finding` left `_UNSET` records the way every caller does today —
    which is what the "carries none" scenarios need. Passing `None`
    explicitly is a *different* act, and the replace-with-none scenario
    below exercises both.
    """
    kwargs: dict[str, Any] = {
        "step_id": step_id,
        "outcome": outcome,
        "provenance": provenance if provenance is not None else _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg()] = finding
    return launch.record_step_outcome(playbook, **kwargs)


def _fields_of(progress: Any) -> set[str]:
    slots = getattr(type(progress), "__slots__", None)
    if slots:
        return set(slots)
    return {name for name in dir(progress) if not name.startswith("_")}


def _finding_attr(progress: Any) -> str:
    for name in _FINDING_ATTRS:
        if hasattr(progress, name):
            return name
    pytest.fail(
        "a recorded `StepProgress` exposes no carried finding under any of "
        f"{list(_FINDING_ATTRS)}; it carries {sorted(_fields_of(progress))} "
        "— correct `_FINDING_ATTRS` to the implemented attribute"
    )


def _part(raw: Any, key: str) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(key, _ABSENT)
    return getattr(raw, key, _ABSENT)


def _read(progress: Any) -> _Carried | None:
    """What the recording carries, or `None` where it carries nothing."""
    raw = getattr(progress, _finding_attr(progress))
    if raw is None:
        return None
    comment = _part(raw, "comment")
    return _Carried(
        field=_part(raw, "field"),
        value=_part(raw, "value"),
        comment=_ABSENT if comment is None else comment,
    )


def _progress(launch: Launch, step_id: str = STEP_ID) -> Any:
    found = launch.progress_for(step_id)
    assert found is not None, f"nothing was recorded for {step_id!r}"
    return found


# ---------------------------------------------------------------------------
# Scenario: A recording carries the finding that produced it (tasks.md 1.1)
# ---------------------------------------------------------------------------


def test_a_recording_carries_the_finding_that_produced_it() -> None:
    """WHEN an outcome is recorded together with a finding's field, value
    and comment THEN the recording carries all three, readable back
    alongside its outcome, evidence and provenance.
    """
    playbook = _playbook()
    launch = _launch(playbook)

    _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))

    progress = _progress(launch)
    carried = _read(progress)
    assert carried is not None, "the recording carries no finding"
    # SPECIFIED: all three parts are readable back.
    assert carried.field == FIELD
    assert carried.value == VALUE
    assert carried.comment == COMMENT
    # SPECIFIED: alongside its outcome, evidence and provenance — the
    # finding sits beside them, never in place of them.
    assert progress.outcome is Satisfied
    assert progress.provenance.evidence == EVIDENCE
    assert progress.provenance.source == "automated"
    assert progress.provenance.who == "listing.subcategory_advisor"
    assert progress.provenance.when == WHEN


# ---------------------------------------------------------------------------
# Scenario: A recording made with no finding carries none (tasks.md 1.2)
# ---------------------------------------------------------------------------


def test_a_recording_made_with_no_finding_carries_none() -> None:
    """WHEN an outcome is recorded with no finding THEN the recording
    carries no finding, and its outcome, evidence and provenance are
    exactly what they would be for any other recording.
    """
    playbook = _playbook()
    launch = _launch(playbook)

    _record(launch, playbook)

    progress = _progress(launch)
    assert _read(progress) is None
    assert progress.outcome is Satisfied
    assert progress.provenance.evidence == EVIDENCE
    assert progress.provenance.source == "automated"
    assert progress.provenance.who == "listing.subcategory_advisor"
    assert progress.provenance.when == WHEN


def test_the_outcome_and_provenance_match_a_recording_that_carries_one() -> None:
    """The same scenario's second clause, stated differentially.

    "Exactly what they would be for any other recording" is a comparison,
    so it is asserted as one: two launches recorded identically but for
    the finding, and every other fact equal.
    """
    bare_playbook = _playbook()
    bare = _launch(bare_playbook)
    carrying_playbook = _playbook()
    carrying = _launch(carrying_playbook)

    _record(bare, bare_playbook)
    _record(carrying, carrying_playbook, finding=_carry(FIELD, VALUE, COMMENT))

    left = _progress(bare)
    right = _progress(carrying)
    assert left.outcome is right.outcome
    assert left.provenance == right.provenance


# ---------------------------------------------------------------------------
# Scenario: An absent finding is distinguishable from an empty value
# (tasks.md 1.3 — the assertion the whole change turns on)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "empty", [[], "", (), {}], ids=["list", "text", "tuple", "map"]
)
def test_an_absent_finding_is_distinguishable_from_an_empty_value(empty: Any) -> None:
    """WHEN one recording carries no finding and another carries a finding
    whose value is empty THEN the two are distinguishable when read back,
    the first reporting that nothing was established and the second
    reporting that what was established was empty.

    An implementation that stores an empty value as "carries nothing", or
    reads "carries nothing" as an empty value, passes every other test in
    this file. `[]` and `""` are the two `tasks.md` 1.3 names; the tuple
    and mapping rows are INVENTED, on the same rule.
    """
    nothing_playbook = _playbook()
    nothing = _launch(nothing_playbook)
    empty_playbook = _playbook()
    established_empty = _launch(empty_playbook)

    _record(nothing, nothing_playbook)
    _record(established_empty, empty_playbook, finding=_carry(FIELD, empty, COMMENT))

    # SPECIFIED: nothing was established.
    assert _read(_progress(nothing)) is None

    # SPECIFIED: something was established and it was empty — a finding
    # that *exists*, whose value is the empty one written.
    carried = _read(_progress(established_empty))
    assert carried is not None, (
        f"a finding whose value is {empty!r} was read back as carrying "
        "nothing; an empty value lives inside a finding that exists"
    )
    assert carried.field == FIELD
    assert carried.value == empty


def test_a_finding_whose_value_is_null_is_not_a_present_finding() -> None:
    """The requirement's one-spelling clause: "a value that is absent, or
    null, SHALL NOT be stored or read as a present finding".

    Two acceptable implementations: reject the recording outright, or read
    it back as carrying nothing. Both satisfy the clause; what does not is
    reading it back as a *present* finding, which would give "empty" a
    second spelling and destroy the distinction the test above draws.
    """
    playbook = _playbook()
    launch = _launch(playbook)

    try:
        _record(launch, playbook, finding=_carry(FIELD, None, COMMENT))
    except (ValueError, TypeError, launch_run.LaunchError):
        return

    assert _read(_progress(launch)) is None, (
        "a finding whose value is null was read back as a present finding; "
        "the delta admits one spelling of empty and this is not it"
    )


def test_a_finding_whose_value_is_absent_is_not_a_present_finding() -> None:
    """The same clause for an *absent* value, which is a different payload
    from a null one wherever the store is a mapping."""
    playbook = _playbook()
    launch = _launch(playbook)

    try:
        _record(launch, playbook, finding={"field": FIELD, "comment": COMMENT})
    except (ValueError, TypeError, KeyError, launch_run.LaunchError):
        return

    assert _read(_progress(launch)) is None, (
        "a finding with no value at all was read back as a present finding"
    )


# ---------------------------------------------------------------------------
# Scenario: A finding with no comment is carried as such (tasks.md 1.4)
# ---------------------------------------------------------------------------


def test_a_finding_with_no_comment_is_carried_as_such() -> None:
    """WHEN an outcome is recorded with a finding whose comment is absent
    THEN the recording carries the field and the value, and reports the
    comment as absent rather than as empty text.
    """
    playbook = _playbook()
    launch = _launch(playbook)

    _record(launch, playbook, finding=_carry(FIELD, VALUE))

    carried = _read(_progress(launch))
    assert carried is not None
    assert carried.field == FIELD
    assert carried.value == VALUE
    assert carried.comment is _ABSENT, (
        f"an absent comment was read back as {carried.comment!r}; the delta "
        "requires it be distinct from empty text"
    )


def test_an_absent_comment_is_distinct_from_an_empty_one() -> None:
    """The clause's own comparison: absent and `""` are two states, and a
    representation collapsing them satisfies neither reading."""
    absent_playbook = _playbook()
    absent = _launch(absent_playbook)
    empty_playbook = _playbook()
    empty = _launch(empty_playbook)

    _record(absent, absent_playbook, finding=_carry(FIELD, VALUE))
    _record(empty, empty_playbook, finding=_carry(FIELD, VALUE, ""))

    without = _read(_progress(absent))
    with_empty = _read(_progress(empty))
    assert without is not None and with_empty is not None
    assert without.comment is _ABSENT
    assert with_empty.comment == ""


# ---------------------------------------------------------------------------
# Scenario: Evidence is unchanged by what is carried beside it (tasks.md 1.7)
# ---------------------------------------------------------------------------


def test_evidence_is_byte_identical_whether_or_not_a_finding_is_carried() -> None:
    """WHEN an outcome is recorded with a finding THEN its evidence is the
    same text it would have been had nothing been carried.

    Byte-identical, not merely equal-ish: the evidence is the verbatim
    text a member was shown, and a rendering change must never rewrite the
    record of what someone actually read.
    """
    bare_playbook = _playbook()
    bare = _launch(bare_playbook)
    carrying_playbook = _playbook()
    carrying = _launch(carrying_playbook)

    _record(bare, bare_playbook)
    _record(carrying, carrying_playbook, finding=_carry(FIELD, VALUE, COMMENT))

    stored = _progress(carrying).provenance.evidence
    assert stored == _progress(bare).provenance.evidence
    assert stored == EVIDENCE
    assert stored.encode("utf-8") == EVIDENCE.encode("utf-8")
    # DERIVED, from "carrying a finding SHALL NOT alter the evidence": the
    # comment is kept beside the evidence, so it must not be appended to
    # it — a plausible implementation that concatenates the two would pass
    # a laxer `EVIDENCE in stored`.
    assert COMMENT not in stored


# ---------------------------------------------------------------------------
# Scenario: A later recording replaces the carried finding (tasks.md 1.6)
# ---------------------------------------------------------------------------


def test_a_later_recording_replaces_the_carried_finding() -> None:
    """WHEN a step carrying a finding has a later outcome recorded against
    it THEN the carried finding is replaced along with the outcome and
    provenance.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    later_evidence = "Sports & Outdoors > Camping & Hiking > Cookware."
    later_value = "Sports & Outdoors > Camping & Hiking > Cookware"

    _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))
    _record(
        launch,
        playbook,
        outcome=InProgress,
        provenance=_provenance(evidence=later_evidence, when=LATER),
        finding=_carry(FIELD, later_value, "reconsidered"),
    )

    progress = _progress(launch)
    carried = _read(progress)
    assert carried is not None
    assert carried.value == later_value
    assert carried.comment == "reconsidered"
    assert progress.outcome is InProgress
    assert progress.provenance.evidence == later_evidence
    assert progress.provenance.when == LATER


def test_a_later_recording_replaces_a_carried_finding_with_none() -> None:
    """The same scenario's "including being replaced by none where the
    later recording carries nothing".

    The falsifying row `tasks.md` 1.6 names: an implementation that only
    ever *writes* a finding leaves the earlier one standing, so the launch
    goes on asserting a fact the new outcome never established.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    later_evidence = "The advisor could not reach a node this pass."

    _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))
    _record(
        launch,
        playbook,
        outcome=InProgress,
        provenance=_provenance(evidence=later_evidence, when=LATER),
    )

    progress = _progress(launch)
    assert _read(progress) is None, (
        "a later recording carrying nothing left the earlier finding "
        "standing; the launch now asserts a fact its current outcome "
        "never established"
    )
    assert progress.outcome is InProgress
    assert progress.provenance.evidence == later_evidence


def test_a_later_recording_carrying_an_explicit_none_replaces_it_too() -> None:
    """The same row, reached the other way: `None` passed explicitly.

    Recorded separately because the two calls differ in the implementation
    — one omits the keyword, one supplies it — and an implementation that
    only replaces on an omitted keyword would pass the test above.
    """
    playbook = _playbook()
    launch = _launch(playbook)

    _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))
    _record(
        launch,
        playbook,
        outcome=InProgress,
        provenance=_provenance(evidence="Nothing established.", when=LATER),
        finding=None,
    )

    assert _read(_progress(launch)) is None
