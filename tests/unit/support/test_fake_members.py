"""`FakeMembers`' contract, stated directly.

Two things the lockstep proof cannot show for this fake. The first is that
nothing reaches the two spellings it drops -- a pairing over a name the shared
fake lacks is silent by construction, so the licence rests on task 11.1's
measurement. The second is `member()` on an identifier the roster does not hold,
which only six of the forty-three files carry at all.
"""

from __future__ import annotations

import pytest

from tests.support.fakes import FakeMembers
from tests.support.values import Member

pytestmark = pytest.mark.anyio

ALICE = Member("prs_01HQ8Z6M4A", "Alice Admin")
BOHDAN = Member("prs_01HQ8Z6M4B", "Bohdan Confirmer")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_an_empty_membership_lists_nobody() -> None:
    assert await FakeMembers().list_members() == ()


async def test_lists_the_members_it_was_given_in_order() -> None:
    """Order is part of the contract: the surfaces that render a membership
    read it straight out, and every local returned its roster unsorted."""
    assert await FakeMembers((ALICE, BOHDAN)).list_members() == (ALICE, BOHDAN)


async def test_resolves_a_member_by_identifier() -> None:
    assert await FakeMembers((ALICE, BOHDAN)).member(ALICE.id) is ALICE


async def test_answers_none_for_an_identifier_the_membership_does_not_hold() -> None:
    assert await FakeMembers((ALICE,)).member("prs_NOBODY") is None


async def test_presents_one_reader_shape_and_not_three() -> None:
    """The dropped spellings, asserted as dropped.

    `clickup_sync._members` and `activation_readiness._members_of` each accept
    three conventions and take the first that matches. This double supplies only
    the first, so a future edit that quietly restores `members` or `__call__`
    has to argue with a test rather than slipping past a green suite.
    """
    members = FakeMembers((ALICE,))

    assert not hasattr(members, "members")
    assert not callable(members)
