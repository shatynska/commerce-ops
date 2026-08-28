"""The launch list's last-completed column, exercised without a template.

Derived from `tidy-the-launch-pages-presentation`'s requirement *The list
names the completion recorded most recently*, added to that change after
its review at the admin's direction. These tests were written alongside
the implementation rather than derived from the delta ahead of it, which
the change's own tasks record; they are here so the reading the column
takes is pinned rather than left to be rediscovered from the code.

The reading that matters and is easy to get wrong: "last" is by RECORDING
time, not by the playbook's order, and only `Satisfied` counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from commerce_ops.launch.infrastructure.driving.launch_admin import (
    _last_completed,
    _rows_for,
)


class Satisfied:
    """Stands in for the domain outcome of the same name, which the
    shaping identifies by type name rather than by import."""


class Blocked:
    pass


class InProgress:
    pass


@dataclass(frozen=True)
class _Provenance:
    when: datetime | None


@dataclass(frozen=True)
class _Progress:
    outcome: Any
    provenance: _Provenance


@dataclass(frozen=True)
class _Entry:
    name: str
    progress: _Progress | None


@dataclass(frozen=True)
class _Report:
    steps: tuple[_Entry, ...]


EARLY: Final = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
MIDDLE: Final = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
LATE: Final = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


def _done(name: str, when: datetime | None) -> _Entry:
    return _Entry(name, _Progress(Satisfied, _Provenance(when)))


def test_the_latest_recorded_completion_is_named() -> None:
    """The column answers what most recently happened on this launch."""
    report = _Report(
        (_done("Create the listing shell", EARLY), _done("Raise the PO", LATE))
    )
    assert _last_completed(report) == ("Raise the PO", LATE)


def test_recording_time_beats_playbook_order() -> None:
    """A completion backfilled today leads, though a later step in the
    playbook was completed first. This is the chosen reading, and the one
    the two candidate readings disagree on -- so it is asserted rather
    than left to follow from the implementation."""
    report = _Report(
        (_done("An early step, recorded late", LATE), _done("A later step", MIDDLE))
    )
    assert _last_completed(report) == ("An early step, recorded late", LATE)


def test_only_satisfied_counts() -> None:
    """Every outcome is recorded with the same provenance, so taking the
    latest recording of any outcome would let a step recorded as blocked
    read as the launch's latest completion."""
    report = _Report(
        (
            _done("The one actually completed", EARLY),
            _Entry("Blocked later", _Progress(Blocked, _Provenance(LATE))),
            _Entry("In progress later", _Progress(InProgress, _Provenance(LATE))),
        )
    )
    assert _last_completed(report) == ("The one actually completed", EARLY)


def test_an_instance_outcome_is_read_like_a_type() -> None:
    """The shaping identifies an outcome by type name, and the domain
    records some outcomes as instances and some as the type itself."""
    report = _Report((_Entry("Done", _Progress(Satisfied(), _Provenance(LATE))),))
    assert _last_completed(report) == ("Done", LATE)


def test_a_launch_with_no_completion_names_none() -> None:
    """The ordinary case at the first gate, not a degenerate one."""
    unstarted = _Report((_Entry("Nothing recorded", None),))
    assert _last_completed(unstarted) == (None, None)
    assert _last_completed(_Report(())) == (None, None)


def test_a_completion_with_no_recorded_time_is_not_named() -> None:
    """Ordering by a time that is absent would order by chance."""
    report = _Report((_done("Undated completion", None),))
    assert _last_completed(report) == (None, None)


def test_a_tie_is_broken_by_the_reports_own_order() -> None:
    """Two completions recorded in the same instant order themselves by
    the report's order, which is the authored one -- never by chance."""
    report = _Report((_done("First authored", LATE), _done("Last authored", LATE)))
    assert _last_completed(report) == ("Last authored", LATE)


# ---------------------------------------------------------------------------
# The row actually carries it
#
# Everything above exercises the choosing in isolation. None of it would
# fail if the shaping computed the answer and dropped it on the floor --
# which is exactly what the first rendering of this column did, though by
# a different route: a preview built its rows directly and every launch
# read "Nothing completed yet". The gap was in the tests, so the test is
# here rather than the lesson being recorded in a comment.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProductId:
    value: str


@dataclass(frozen=True)
class _RowReport:
    product_id: _ProductId
    current_gate: str
    launch_date: Any
    at_risk: Any
    awaiting_confirmation: bool
    steps: tuple[_Entry, ...]


def _report(*steps: _Entry) -> _RowReport:
    return _RowReport(
        product_id=_ProductId("pid-1"),
        current_gate="commit",
        launch_date=None,
        at_risk=None,
        awaiting_confirmation=False,
        steps=steps,
    )


def test_a_shaped_row_carries_the_completion_it_names() -> None:
    """The choosing is reached from the shaping, and its answer survives
    onto the row -- not computed and discarded."""
    (row,) = _rows_for((_report(_done("Raise the PO", LATE)),), {})
    assert row.last_completed == "Raise the PO"
    assert row.last_completed_at == LATE


def test_a_shaped_row_with_no_completion_carries_none() -> None:
    """The absence reaches the row as an absence, so the page can state
    it rather than rendering an empty cell."""
    (row,) = _rows_for((_report(_Entry("Nothing recorded", None)),), {})
    assert row.last_completed is None
    assert row.last_completed_at is None
