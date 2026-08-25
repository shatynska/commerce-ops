"""The Postgres roster store: the `RosterStore` port over `roster_people`.

`load()` answers every stored row — deactivated included, since the
identity-uniqueness rule spans them — with the current set-version, and
`save()` persists a full replacement set conditionally on that version,
raising `StaleRosterError` when it has moved. The shape mirrors
`launch.infrastructure.driven.playbook_repository`, which serializes the
step set the same way: two capabilities with set-level invariants, one
idiom.

This adapter translates rows into the values the application's
constructors expect; it re-implements none of the coherence rules, which
live in `access.domain.principals` and run on every write.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.access.application.roster import PersonRecord, StaleRosterError
from commerce_ops.access.domain.principals import Person
from commerce_ops.access.infrastructure.driven.models import RosterPerson, RosterSet
from commerce_ops.shared.infrastructure.driven.database import session

_SET_ROW_ID = 1


def _record_from_row(row: RosterPerson) -> PersonRecord:
    return PersonRecord(
        person=Person(
            identifier=row.identifier,
            display_name=row.display_name,
            slack_identity=row.slack_identity,
            clickup_user_id=row.clickup_user_id,
            admin=row.admin,
            active=row.active,
        ),
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        deactivated_by=row.deactivated_by,
        deactivated_on=row.deactivated_on,
        reactivated_by=row.reactivated_by,
        reactivated_on=row.reactivated_on,
        admin_conferred_by=row.admin_conferred_by,
    )


def _row_from_record(record: Any) -> RosterPerson:
    person = record.person
    return RosterPerson(
        identifier=person.identifier,
        display_name=person.display_name,
        slack_identity=person.slack_identity,
        clickup_user_id=person.clickup_user_id,
        admin=person.admin,
        active=person.active,
        created_by=record.created_by,
        created_on=record.created_on,
        updated_by=record.updated_by,
        updated_on=record.updated_on,
        deactivated_by=record.deactivated_by,
        deactivated_on=record.deactivated_on,
        reactivated_by=record.reactivated_by,
        reactivated_on=record.reactivated_on,
        admin_conferred_by=getattr(record, "admin_conferred_by", None),
    )


class RosterRepository:
    """The roster as stored, behind the port the write use cases hold."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _version(self) -> int:
        version = await self._session.scalar(
            select(RosterSet.version).where(RosterSet.id == _SET_ROW_ID)
        )
        if version is None:
            # The singleton is created by the migration; its absence means
            # the migration has not run, which is a deployment fault rather
            # than an empty roster.
            raise RuntimeError("the roster has no version row — has the migration run?")
        return int(version)

    async def load(self) -> tuple[Sequence[PersonRecord], int]:
        version = await self._version()
        rows = await self._session.scalars(
            select(RosterPerson).order_by(RosterPerson.display_name)
        )
        return tuple(_record_from_row(row) for row in rows), version

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None:
        """Persist the full replacement set, conditionally on the version
        it was loaded at — the optimistic serialization every write rides."""
        bumped = await self._session.execute(
            update(RosterSet)
            .where(
                RosterSet.id == _SET_ROW_ID,
                RosterSet.version == expected_version,
            )
            .values(version=expected_version + 1)
            .returning(RosterSet.version)
        )
        if bumped.scalar() is None:
            await self._session.rollback()
            raise StaleRosterError(
                f"the roster moved past version {expected_version} while this "
                f"write was validating; reload and revalidate"
            )
        await self._session.execute(delete(RosterPerson))
        self._session.add_all(_row_from_record(record) for record in records)
        await self._session.commit()


class PostgresRoster:
    """The `RosterStore` port, opening its own session per operation.

    The composition-root collaborator, shaped like `PostgresLinkTokens`:
    the Slack adapter and the admin surface hold one of these rather than
    a session, so nothing above the adapter layer learns about sessions.
    """

    async def load(self) -> tuple[Sequence[PersonRecord], int]:
        async with session() as db:
            return await RosterRepository(db).load()

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None:
        async with session() as db:
            await RosterRepository(db).save(records, expected_version=expected_version)
