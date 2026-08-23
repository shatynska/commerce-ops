"""Tests for timing-anchor resolution in the `launch-playbook` capability.

Derived from the delta spec:
openspec/changes/add-launch-playbook/specs/launch-playbook/spec.md
— Requirement: *Timing anchors resolve against the launch date*.

Every requirement in that spec is `ADDED`; no prior `launch-playbook` spec
exists. These tests were therefore written from the scenarios alone, before
any implementation, and were never run against implementation code.

At the time of writing `src/commerce_ops/launch/domain/` is empty
scaffolding, so every test in this file is expected to fail on an absent
target (`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only that the target is absent — it establishes nothing about
whether the assertions below are correct, because they never executed.

Names imported from the domain are DERIVED: neither the spec, `design.md`
nor `tasks.md` fixes module paths, class names or field names. See
`openspec/changes/add-launch-playbook/test-manifest.md`, which records the
assumed API surface as an unresolved project question.
"""

from __future__ import annotations

from datetime import date

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Cadence,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    WindowAnchor,
)

# DERIVED: the spec fixes no particular launch date. This one is chosen so
# that the offsets under test cross month boundaries in both directions,
# which a naive day-of-month implementation would get wrong. Expected dates
# below are written as literals rather than recomputed with `timedelta`, so
# the test does not reuse the arithmetic it is checking.
LAUNCH_DATE = date(2026, 3, 2)


def test_offset_anchor_resolves_to_a_single_day() -> None:
    """Scenario: An offset anchor resolves to a single day.

    WHEN an anchor of -7 days is resolved against a launch date
    THEN the resulting range starts and ends on the day seven days before
    the launch date.
    """
    resolved = OffsetAnchor(days=-7).resolve(LAUNCH_DATE)

    # SPECIFIED: starts and ends on the day seven days before launch.
    assert resolved is not None
    assert resolved.start == date(2026, 2, 23)
    assert resolved.end == date(2026, 2, 23)


def test_offset_zero_resolves_to_the_launch_date_itself() -> None:
    """Scenario: The launch day itself is offset zero.

    WHEN an anchor of offset 0 is resolved against a launch date
    THEN the resulting range starts and ends on the launch date itself.

    This pins the zero-based convention the spec states outright ("the
    launch day itself is offset 0"), which `design.md` flags as the single
    most expensive thing to get wrong: a uniform one-day drift across every
    post-launch anchor is invisible in the data file.
    """
    resolved = OffsetAnchor(days=0).resolve(LAUNCH_DATE)

    # SPECIFIED: offset zero is the marketing launch date.
    assert resolved is not None
    assert resolved.start == LAUNCH_DATE
    assert resolved.end == LAUNCH_DATE


def test_offset_one_is_the_day_after_launch() -> None:
    """Scenario: The launch day itself is offset zero (second assertion).

    The spec states in the same requirement that "the day after it is
    offset 1". Covered here rather than folded into the test above so that
    a failure distinguishes a wrong origin from a wrong direction.
    """
    resolved = OffsetAnchor(days=1).resolve(LAUNCH_DATE)

    # SPECIFIED: offsets after the launch date are positive.
    assert resolved is not None
    assert resolved.start == date(2026, 3, 3)
    assert resolved.end == date(2026, 3, 3)


def test_window_anchor_resolves_to_a_bounded_span() -> None:
    """Scenario: A window anchor resolves to a bounded span.

    WHEN an anchor spanning offsets 28 through 55 is resolved against a
    launch date
    THEN the resulting range starts 28 days after and ends 55 days after
    the launch date.
    """
    resolved = WindowAnchor(start=28, end=55).resolve(LAUNCH_DATE)

    # SPECIFIED: both bounds are inclusive positions relative to launch.
    assert resolved is not None
    assert resolved.start == date(2026, 3, 30)
    assert resolved.end == date(2026, 4, 26)


def test_open_ended_anchor_resolves_to_a_start_with_no_end() -> None:
    """Scenario: An open-ended anchor resolves to a start with no end.

    WHEN an anchor beginning at offset 59 with no end is resolved against a
    launch date
    THEN the resulting range starts 59 days after the launch date
    AND the range reports no end date.
    """
    resolved = OpenEndedAnchor(start=59).resolve(LAUNCH_DATE)

    # SPECIFIED: a start 59 days after launch, and no end at all.
    assert resolved is not None
    assert resolved.start == date(2026, 4, 30)
    assert resolved.end is None


def test_recurring_anchor_produces_no_range_and_reports_its_cadence() -> None:
    """Scenario: A recurring anchor has no due date.

    WHEN a recurring anchor is resolved against a launch date
    THEN no date range is produced, and the anchor reports its cadence
    instead.
    """
    anchor = RecurringAnchor(cadence=Cadence.WEEKLY)

    # SPECIFIED: no date range is produced.
    assert anchor.resolve(LAUNCH_DATE) is None
    # SPECIFIED: the anchor reports its cadence instead.
    assert anchor.cadence is Cadence.WEEKLY


def test_window_with_a_reversed_span_is_rejected() -> None:
    """Scenario: A window with a reversed span is rejected.

    WHEN a window anchor is defined whose end offset precedes its start
    offset
    THEN it is rejected as invalid.

    DERIVED: the spec says "rejected as invalid" without naming an
    exception type, and `tasks.md` 2.4 places the rejection at
    construction. `ValueError` is asserted because `pytest.raises` accepts
    any subclass, so a domain-specific error deriving from `ValueError`
    satisfies this without the test needing to know its name.
    """
    with pytest.raises(ValueError):
        WindowAnchor(start=55, end=28)


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - Whether a window whose start equals its end is accepted. The spec calls
#   a window "a span between two such offsets" and rejects only a reversed
#   one; a degenerate single-day window is neither required nor forbidden.
# - Which concrete type `resolve()` returns. The scenarios describe it only
#   as "the resulting range" with a start and an optional end, so these
#   tests assert on those two attributes and import no range type.
# - Whether an open-ended anchor may carry a negative start, and whether a
#   recurring anchor carries any offset at all. Neither is stated.
