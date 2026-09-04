"""`StubDate`'s contract, stated directly.

**These are the primary check for this double, not a supplement.** No instance
is constructed by the call sites -- they substitute the class -- and `today` is
a classmethod, so the lockstep proof of `share-the-stateful-fakes` has nothing
to intercept and does not run for it (design.md Decision 2). What stands in its
place is this module, the `date` base class, and the class-object `_conforms`
assignment in `tests/support/protocols.py`.
"""

from __future__ import annotations

from datetime import date

from tests.support.fakes import StubDate

RENDERED_ON = date(2027, 4, 1)


class _FixedDate(StubDate):
    _today = RENDERED_ON


def test_today_answers_the_day_the_subclass_pins() -> None:
    assert _FixedDate.today() == RENDERED_ON


def test_is_a_date_and_goes_on_behaving_like_one() -> None:
    """The base class is the substance: production keeps constructing and
    comparing dates through the class it was handed."""
    assert issubclass(_FixedDate, date)
    assert _FixedDate(2027, 3, 2) == date(2027, 3, 2)
    assert _FixedDate(2027, 3, 2) < RENDERED_ON
    assert _FixedDate(2027, 3, 2).isoformat() == "2027-03-02"


def test_a_further_subclass_pins_its_own_day() -> None:
    """One file builds a subclass on the fly to move the day within a test:
    `type("_FixedDate", (_StubDate,), {"_today": day})`."""
    other = date(2028, 1, 9)
    moved: type[StubDate] = type("_MovedDate", (_FixedDate,), {"_today": other})

    assert moved.today() == other
    assert _FixedDate.today() == RENDERED_ON
