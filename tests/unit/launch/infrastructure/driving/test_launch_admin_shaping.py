"""The launch-tracking pages' shaping, exercised without a template.

Derived from `add-launch-tracking-pages`' **task 7.4a**, not from a delta
scenario — `tasks.md` says so itself ("No delta requires it"). It exists
because `design.md`'s Goals claim data shaping is separable from markup,
and nothing derived from the specs can observe that claim: every other
test in this suite renders a page and reads the HTML back, so all of them
would still pass if shaping and rendering were fused again.

What this file asserts is therefore narrow and deliberate: that the read
model can be built and reasoned about with no Jinja environment, no
request and no HTML anywhere in the call. If that stops being true, these
tests stop compiling rather than stop passing.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from commerce_ops.launch.infrastructure.driving.launch_admin import (
    LaunchRow,
    _finished_key,
    _sort_key,
)

_DETAIL: Final = "/admin/launches/x"


def _row(
    product_id: str,
    *,
    launch_date: date | None = None,
    at_risk: bool = False,
    awaiting: bool = False,
) -> LaunchRow:
    return LaunchRow(
        product_id=product_id,
        label=product_id,
        resolved=True,
        current_gate="commit",
        launch_date=launch_date,
        at_risk=at_risk,
        awaiting_confirmation=awaiting,
        in_play=True,
        retired=False,
        detail_path=_DETAIL,
    )


def test_a_row_reports_its_attention_band_without_rendering() -> None:
    """At risk leads, then awaiting confirmation, then the rest — and a
    row in both bands reports the first, which is what makes it appear
    once rather than twice."""
    assert _row("a", at_risk=True).band == 0
    assert _row("b", awaiting=True).band == 1
    assert _row("c").band == 2
    assert _row("d", at_risk=True, awaiting=True).band == 0


def test_the_band_order_sorts_without_rendering() -> None:
    """The list's order is a property of the rows, not of the markup."""
    quiet = _row("quiet", launch_date=date(2027, 1, 1))
    waiting = _row("waiting", launch_date=date(2027, 6, 1), awaiting=True)
    risky = _row("risky", launch_date=date(2027, 9, 1), at_risk=True)

    ordered = sorted([quiet, waiting, risky], key=_sort_key)

    assert [row.product_id for row in ordered] == ["risky", "waiting", "quiet"]


def test_within_a_band_the_earliest_date_leads_and_undated_sorts_last() -> None:
    early = _row("early", launch_date=date(2027, 1, 1))
    late = _row("late", launch_date=date(2027, 8, 1))
    undated = _row("undated")

    ordered = sorted([undated, late, early], key=_sort_key)

    assert [row.product_id for row in ordered] == ["early", "late", "undated"]


def test_the_revealed_set_runs_the_other_way() -> None:
    """Most recent first, undated last — the reverse of the bands, which
    is the one place the two orders differ."""
    early = _row("early", launch_date=date(2027, 1, 1))
    late = _row("late", launch_date=date(2027, 8, 1))
    undated = _row("undated")

    ordered = sorted([early, undated, late], key=_finished_key)

    assert [row.product_id for row in ordered] == ["late", "early", "undated"]


def test_ties_break_on_the_product_identifier_in_both_orders() -> None:
    """The one identity field always available: a row may render with no
    SKU and no name, so nothing else is total."""
    same = date(2027, 5, 1)
    first = _row("aaa", launch_date=same)
    second = _row("bbb", launch_date=same)

    assert [r.product_id for r in sorted([second, first], key=_sort_key)] == [
        "aaa",
        "bbb",
    ]
    assert [r.product_id for r in sorted([second, first], key=_finished_key)] == [
        "aaa",
        "bbb",
    ]
