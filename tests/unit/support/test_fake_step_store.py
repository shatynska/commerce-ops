"""`FakeStepStore`'s contract, stated directly.

The lockstep proof compares this fake against each of the thirty-seven locals on
the calls those files execute. What it cannot reach is the path no file takes --
the stale write, in particular, which is the one behaviour this fake takes
*stricter* than eighteen of the declarations it replaces. That strengthening is
the reason the assertion is stated here rather than left to be discovered.
"""

from __future__ import annotations

import pytest

from tests.support.fakes import FakeStepStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_an_empty_store_loads_no_rows_at_the_opening_version() -> None:
    """41 is the version every one of the thirty-seven declarations opened at,
    bar two that pinned their own; it is a literal, not a meaning."""
    empty: FakeStepStore[str] = FakeStepStore()

    assert await empty.load() == ((), 41)


async def test_loads_back_the_rows_it_was_given_as_a_tuple() -> None:
    store = FakeStepStore(records=("first", "second"), version=7)

    assert await store.load() == (("first", "second"), 7)


async def test_a_save_replaces_the_rows_and_moves_the_version_on() -> None:
    store = FakeStepStore(records=("first",))

    await store.save(("second", "third"), expected_version=41)

    assert await store.load() == (("second", "third"), 42)


async def test_a_save_is_recorded_with_the_version_it_was_made_against() -> None:
    """`saves` is a superset over eleven of the locals: no production reader
    probes it, so a file that never reads it cannot tell it is there."""
    store = FakeStepStore(records=("first",))

    await store.save(("second",), expected_version=41)

    assert store.saves == [(("second",), 41)]


async def test_a_stale_write_is_refused_rather_than_accepted_quietly() -> None:
    """The one behaviour taken stricter than eighteen of the locals.

    A fake that accepts an `expected_version` from an earlier read hides the
    optimistic-concurrency defect the real store exists to catch.
    """
    store = FakeStepStore(records=("first",))
    await store.save(("second",), expected_version=41)

    with pytest.raises(AssertionError, match="conditional persistence violated"):
        await store.save(("third",), expected_version=41)


async def test_rows_are_stored_as_a_tuple_whatever_sequence_arrives() -> None:
    store: FakeStepStore[str] = FakeStepStore()

    await store.save(["first", "second"], expected_version=41)

    rows, _ = await store.load()
    assert rows == ("first", "second")


async def test_is_generic_in_its_row_type() -> None:
    """Each file binds the parameter its own local declaration bound.

    Seven of the thirty-seven read a row back through a helper declaring the
    concrete return type; a store fixed at `tuple[Any, ...]` would make those
    helpers return `Any` from a function declared otherwise, which
    `mypy --strict` refuses. The settle line carries the parameter instead.
    """
    store: FakeStepStore[str] = FakeStepStore(records=("first",))

    rows, _ = await store.load()

    assert rows == ("first",)
