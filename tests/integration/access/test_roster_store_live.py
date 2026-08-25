"""The Postgres roster store against a live database (`roster`).

The unit tier exercises every roster rule over a store double, so what is
left unobserved there — and covered here — is the adapter itself: that a
person round-trips through Postgres with their attribution intact, and
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
(including this change's roster tables); skips when `DATABASE_URL` is
unset, exactly as the launch tier's live tests do.
"""

from __future__ import annotations

import os
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
    create_person,
    deactivate_person,
    update_person,
)
from commerce_ops.access.application.roster import StaleRosterError
from commerce_ops.access.infrastructure.driven.models import RosterPerson
from commerce_ops.access.infrastructure.driven.roster_repository import (
    RosterRepository,
)

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"
ANOTHER_PRINCIPAL: Final = "the-other-admin"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's roster tables), and point DATABASE_URL at it."
        )
    return url


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_database_url())
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


class _SessionScopedRoster:
    """The store as the use cases hold it: a session per operation, which
    is what makes two interleaved writes genuinely concurrent here."""

    async def load(self) -> tuple[Any, int]:
        async with _session() as session:
            return await RosterRepository(session).load()

    async def save(self, records: Any, *, expected_version: int) -> None:
        async with _session() as session:
            await RosterRepository(session).save(
                records, expected_version=expected_version
            )


@pytest.fixture
async def roster() -> AsyncIterator[_SessionScopedRoster]:
    """An empty roster before and after, so these tests neither inherit
    nor leave behind a person. The version row is left alone: it only
    ever moves forward, and nothing asserts an absolute value."""
    async with _session() as session:
        await session.execute(delete(RosterPerson))
        await session.commit()
    yield _SessionScopedRoster()
    async with _session() as session:
        await session.execute(delete(RosterPerson))
        await session.commit()


def _identity() -> str:
    """A Slack identity unique to this run — the column is unique across
    every row, so a leftover from a crashed run must not collide."""
    return f"U{uuid.uuid4().hex[:10].upper()}"


async def test_a_person_round_trips_through_postgres(
    roster: _SessionScopedRoster,
) -> None:
    """A created person is readable back with identity data and
    attribution intact.

    The attribution half is the point: it is the audit that replaced the
    deleted directory file's git history, so a column that silently
    failed to persist would quietly cost the change its whole rationale.
    """
    identity = _identity()

    created = await create_person(
        roster=roster,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        clickup_user_id="clickup-1",
        admin=True,
    )

    rows, _ = await roster.load()
    (stored,) = [row for row in rows if row.person.slack_identity == identity]

    assert stored.person.identifier == created.person.identifier
    assert stored.person.display_name == "Alice Admin"
    assert stored.person.clickup_user_id == "clickup-1"
    assert stored.person.admin is True
    assert stored.person.active is True
    assert stored.created_by == PRINCIPAL
    assert stored.created_on is not None
    # Who conferred admin is stored apart from who last wrote the row.
    assert stored.admin_conferred_by == PRINCIPAL


async def test_an_update_persists_and_keeps_the_identifier(
    roster: _SessionScopedRoster,
) -> None:
    """An edit round-trips, and the generated identifier does not move —
    the property a step's assignees will depend on."""
    identity = _identity()
    created = await create_person(
        roster=roster,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )

    await update_person(
        roster=roster,
        principal=ANOTHER_PRINCIPAL,
        person_id=created.person.identifier,
        display_name="Alice Corrected",
    )

    rows, _ = await roster.load()
    (stored,) = [row for row in rows if row.person.slack_identity == identity]
    assert stored.person.display_name == "Alice Corrected"
    assert stored.person.identifier == created.person.identifier
    assert stored.updated_by == ANOTHER_PRINCIPAL


async def test_a_write_against_a_stale_version_is_refused(
    roster: _SessionScopedRoster,
) -> None:
    """Two writes computed against the same version: the second is
    refused rather than silently overwriting the first.

    This is what the set-version exists for, and it cannot be established
    against a double — the double is *told* which version to expect,
    while here the database decides. Without it, two admins deactivating
    at the same moment could each pass the last-admin floor against a
    roster the other had already changed.
    """
    identity = _identity()
    await create_person(
        roster=roster,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )

    # Both writers read the same version, as two concurrent requests do.
    rows_a, version = await roster.load()
    rows_b, version_b = await roster.load()
    assert version == version_b

    first = (*rows_a, _a_second_person())
    await roster.save(first, expected_version=version)

    # The second writer still holds the version the first one consumed.
    second = (*rows_b, _a_third_person())
    with pytest.raises(StaleRosterError):
        await roster.save(second, expected_version=version_b)

    # And the refused write left nothing behind.
    rows_after, _ = await roster.load()
    identities = {row.person.slack_identity for row in rows_after}
    assert _THIRD_IDENTITY not in identities


async def test_a_deactivation_persists_as_a_flag_not_a_deletion(
    roster: _SessionScopedRoster,
) -> None:
    """Deactivation keeps the row, its history, and its identifier."""
    identity = _identity()
    keeper = await create_person(
        roster=roster,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=identity,
        admin=True,
    )
    departing_identity = _identity()
    departing = await create_person(
        roster=roster,
        principal=PRINCIPAL,
        display_name="Dave Departed",
        slack_identity=departing_identity,
    )
    assert keeper.person.admin is True

    await deactivate_person(
        roster=roster,
        principal=ANOTHER_PRINCIPAL,
        person_id=departing.person.identifier,
    )

    rows, _ = await roster.load()
    (stored,) = [row for row in rows if row.person.slack_identity == departing_identity]
    assert stored.person.active is False
    assert stored.person.identifier == departing.person.identifier
    assert stored.deactivated_by == ANOTHER_PRINCIPAL
    assert stored.deactivated_on is not None
    # The row survives: deactivated, not deleted.
    assert stored.created_by == PRINCIPAL


_SECOND_IDENTITY: Final = "U0SECONDROW"
_THIRD_IDENTITY: Final = "U0THIRDROWX"


def _a_second_person() -> Any:
    from commerce_ops.access.application.roster import PersonRecord
    from commerce_ops.access.domain.principals import Person

    return PersonRecord(
        person=Person(
            identifier=str(uuid.uuid4()),
            display_name="Second Writer",
            slack_identity=_SECOND_IDENTITY,
        ),
        created_by=PRINCIPAL,
    )


def _a_third_person() -> Any:
    from commerce_ops.access.application.roster import PersonRecord
    from commerce_ops.access.domain.principals import Person

    return PersonRecord(
        person=Person(
            identifier=str(uuid.uuid4()),
            display_name="Third Writer",
            slack_identity=_THIRD_IDENTITY,
        ),
        created_by=PRINCIPAL,
    )
