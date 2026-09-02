"""The Postgres members store against a live database (`members`).

The unit tier exercises every membership rule over a store double, so what is
left unobserved there — and covered here — is the adapter itself: that a
member round-trips through Postgres with their attribution intact, and
that the optimistic set-version actually serializes two concurrent
writes rather than merely being passed around.

The stale-version race is the reason this file exists. A double can only
*assert* that `save` was called with the version `load` returned; only a
real database can show that the second of two writes against the same
version is refused, which is what stops two admins from each deactivating
the other's last-admin protection at the same moment.

Recorded as `tasks.md` 5.8, from the test manifest's "deliberately
uncovered" list: the test-writing pass was barred from `tests/integration`
while another session held it.

Requires the compose file's `postgres` service and `alembic upgrade head`
(including this change's members tables). Gating is the tier's own: these
tests request the `database_url` fixture, so where nothing resolves they
skip locally and *fail* under `COMMERCE_OPS_REQUIRE_DATABASE`, rather
than carrying a private copy of the rule (`verify-the-integration-tier`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.access.application import (
    create_member,
    deactivate_member,
    update_member,
)
from commerce_ops.access.application.members import StaleMembersError
from commerce_ops.access.infrastructure.driven.members_repository import (
    MembersRepository,
)
from commerce_ops.access.infrastructure.driven.models import MemberRow

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"
ANOTHER_PRINCIPAL: Final = "the-other-admin"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def _session(url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


class _SessionScopedMembers:
    """The store as the use cases hold it: a session per operation, which
    is what makes two interleaved writes genuinely concurrent here."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def load(self) -> tuple[Any, int]:
        async with _session(self._url) as session:
            return await MembersRepository(session).load()

    async def save(self, records: Any, *, expected_version: int) -> None:
        async with _session(self._url) as session:
            await MembersRepository(session).save(
                records, expected_version=expected_version
            )


@pytest.fixture
async def members(database_url: str) -> AsyncIterator[_SessionScopedMembers]:
    """An empty membership before and after, so these tests neither inherit
    nor leave behind a member. The version row is left alone: it only
    ever moves forward, and nothing asserts an absolute value.

    Requesting `database_url` is how this file opts into the tier's
    gate: no database configured means skip here, fail in CI.
    """
    async with _session(database_url) as session:
        await session.execute(delete(MemberRow))
        await session.commit()
    yield _SessionScopedMembers(database_url)
    async with _session(database_url) as session:
        await session.execute(delete(MemberRow))
        await session.commit()


def _identity() -> str:
    """A Slack identity unique to this run — the column is unique across
    every row, so a leftover from a crashed run must not collide."""
    return f"U{uuid.uuid4().hex[:10].upper()}"


async def test_a_member_round_trips_through_postgres(
    members: _SessionScopedMembers,
) -> None:
    """A created member is readable back with identity data and
    attribution intact.

    The attribution half is the point: it is the audit that replaced the
    deleted directory file's git history, so a column that silently
    failed to persist would quietly cost the change its whole rationale.
    """
    identity = _identity()

    created = await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        clickup_user_id="clickup-1",
        admin=True,
    )

    rows, _ = await members.load()
    (stored,) = [row for row in rows if row.member.slack_identity == identity]

    assert stored.member.identifier == created.member.identifier
    assert stored.member.display_name == "Alice Admin"
    assert stored.member.clickup_user_id == "clickup-1"
    assert stored.member.admin is True
    assert stored.member.active is True
    assert stored.created_by == PRINCIPAL
    assert stored.created_on is not None
    # Who conferred admin is stored apart from who last wrote the row.
    assert stored.admin_conferred_by == PRINCIPAL


async def test_an_update_persists_and_keeps_the_identifier(
    members: _SessionScopedMembers,
) -> None:
    """An edit round-trips, and the generated identifier does not move —
    the property a step's assignees will depend on."""
    identity = _identity()
    created = await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )

    await update_member(
        members=members,
        principal=ANOTHER_PRINCIPAL,
        member_id=created.member.identifier,
        display_name="Alice Corrected",
    )

    rows, _ = await members.load()
    (stored,) = [row for row in rows if row.member.slack_identity == identity]
    assert stored.member.display_name == "Alice Corrected"
    assert stored.member.identifier == created.member.identifier
    assert stored.updated_by == ANOTHER_PRINCIPAL


async def test_a_write_against_a_stale_version_is_refused(
    members: _SessionScopedMembers,
) -> None:
    """Two writes computed against the same version: the second is
    refused rather than silently overwriting the first.

    This is what the set-version exists for, and it cannot be established
    against a double — the double is *told* which version to expect,
    while here the database decides. Without it, two admins deactivating
    at the same moment could each pass the last-admin floor against a
    members the other had already changed.
    """
    identity = _identity()
    await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )

    # Both writers read the same version, as two concurrent requests do.
    rows_a, version = await members.load()
    rows_b, version_b = await members.load()
    assert version == version_b

    first = (*rows_a, _a_second_member())
    await members.save(first, expected_version=version)

    # The second writer still holds the version the first one consumed.
    second = (*rows_b, _a_third_member())
    with pytest.raises(StaleMembersError):
        await members.save(second, expected_version=version_b)

    # And the refused write left nothing behind.
    rows_after, _ = await members.load()
    identities = {row.member.slack_identity for row in rows_after}
    assert _THIRD_IDENTITY not in identities


async def test_a_deactivation_persists_as_a_flag_not_a_deletion(
    members: _SessionScopedMembers,
) -> None:
    """Deactivation keeps the row, its history, and its identifier."""
    identity = _identity()
    keeper = await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )
    departing_identity = _identity()
    departing = await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Dave Departed",
        slack_identity=departing_identity,
    )
    assert keeper.member.admin is True

    await deactivate_member(
        members=members,
        principal=ANOTHER_PRINCIPAL,
        member_id=departing.member.identifier,
    )

    rows, _ = await members.load()
    (stored,) = [row for row in rows if row.member.slack_identity == departing_identity]
    assert stored.member.active is False
    assert stored.member.identifier == departing.member.identifier
    assert stored.deactivated_by == ANOTHER_PRINCIPAL
    assert stored.deactivated_on is not None
    # The row survives: deactivated, not deleted.
    assert stored.created_by == PRINCIPAL


_SECOND_IDENTITY: Final = "U0SECONDROW"
_THIRD_IDENTITY: Final = "U0THIRDROWX"


def _a_second_member() -> Any:
    from commerce_ops.access.application.members import MemberRecord
    from commerce_ops.access.domain.members import Member

    return MemberRecord(
        member=Member(
            identifier=str(uuid.uuid4()),
            display_name="Second Writer",
            slack_identity=_SECOND_IDENTITY,
        ),
        created_by=PRINCIPAL,
    )


def _a_third_member() -> Any:
    from commerce_ops.access.application.members import MemberRecord
    from commerce_ops.access.domain.members import Member

    return MemberRecord(
        member=Member(
            identifier=str(uuid.uuid4()),
            display_name="Third Writer",
            slack_identity=_THIRD_IDENTITY,
        ),
        created_by=PRINCIPAL,
    )
