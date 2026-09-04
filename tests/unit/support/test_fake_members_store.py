"""`FakeMembersStore`'s contract, stated directly.

The lockstep proof compares this fake against each of the thirty-eight locals on
the calls those files execute. The stale write is the path none of them takes,
and it is the one behaviour this fake takes *stricter* than thirty of them, so
it is stated here rather than left to be discovered.
"""

from __future__ import annotations

import pytest

from tests.support.fakes import FakeMembersStore

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_an_empty_membership_loads_no_rows_at_the_opening_version() -> None:
    """13 is the version twenty-one of the thirty-eight declarations opened at;
    it is a literal, not a meaning, and the eight that pinned another keep a
    two-line adapter for it."""
    assert await FakeMembersStore().load() == ((), 13)


async def test_loads_back_the_rows_it_was_given_as_a_tuple() -> None:
    store = FakeMembersStore(rows=("first", "second"), version=5)

    assert await store.load() == (("first", "second"), 5)


async def test_a_save_replaces_the_rows_and_moves_the_version_on() -> None:
    store = FakeMembersStore(rows=("first",))

    await store.save(("second", "third"), expected_version=13)

    assert await store.load() == (("second", "third"), 14)


async def test_a_save_is_recorded_with_the_version_it_was_made_against() -> None:
    store = FakeMembersStore(rows=("first",))

    await store.save(("second",), expected_version=13)

    assert store.saves == [(("second",), 13)]


async def test_a_stale_write_is_refused_rather_than_accepted_quietly() -> None:
    """Stricter than thirty of the thirty-eight, deliberately."""
    store = FakeMembersStore(rows=("first",))
    await store.save(("second",), expected_version=13)

    with pytest.raises(AssertionError, match="conditional persistence violated"):
        await store.save(("third",), expected_version=13)


async def test_rows_are_stored_as_a_tuple_whatever_sequence_arrives() -> None:
    store = FakeMembersStore()

    await store.save(["first", "second"], expected_version=13)

    rows, _ = await store.load()
    assert rows == ("first", "second")
