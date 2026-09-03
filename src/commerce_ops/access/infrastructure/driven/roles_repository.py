"""The Postgres roles store: the `RolesStore` port over `roles`/`role_holders`.

`load()` answers every stored role — retired included, since slug uniqueness
spans them — with the current set-version, and `save()` persists a full
replacement set conditionally on that version. The shape mirrors
`members_repository` beside it, deliberately: two collections with set-level
invariants, one idiom.

**The version is the membership's.** Not a second cell of its own: the
member/role invariant spans both collections, so they are one
write-serialization boundary (`design.md` Decision 8). Two versions would let a
member deactivation and a role's default move each win their own race and
together leave an active role holding a deactivated default. `StaleRolesError`
is `StaleMembersError` for the same reason — there is one race to lose.

This adapter translates rows into the values the application's constructors
expect; it re-implements none of the coherence rules, which live in
`access.domain.roles` and run on every write.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.access.application.roles import (
    HolderRecord,
    RoleRecord,
    StaleRolesError,
)
from commerce_ops.access.domain.roles import Role, RoleStatus
from commerce_ops.access.infrastructure.driven.models import (
    MembersSet,
    RoleHolderRow,
    RoleRow,
)
from commerce_ops.shared.infrastructure.driven.database import session

_SET_ROW_ID = 1


def _record_from_rows(row: RoleRow, holders: Sequence[RoleHolderRow]) -> RoleRecord:
    ordered = sorted(holders, key=lambda held: held.member_id)
    default = next((held.member_id for held in ordered if held.is_default), None)
    return RoleRecord(
        role=Role(
            slug=row.slug,
            title=row.title,
            status=RoleStatus(row.status),
            holders=tuple(held.member_id for held in ordered),
            default_holder=default,
        ),
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        retired_by=row.retired_by,
        retired_on=row.retired_on,
        unretired_by=row.unretired_by,
        unretired_on=row.unretired_on,
        holder_attribution=tuple(
            HolderRecord(
                member_id=held.member_id,
                added_by=held.added_by,
                added_on=held.added_on,
            )
            for held in ordered
        ),
    )


def _rows_from_record(record: Any) -> tuple[RoleRow, list[RoleHolderRow]]:
    role = record.role
    row = RoleRow(
        slug=role.slug,
        title=role.title,
        status=RoleStatus(role.status).value,
        created_by=record.created_by,
        created_on=record.created_on,
        updated_by=record.updated_by,
        updated_on=record.updated_on,
        retired_by=getattr(record, "retired_by", None),
        retired_on=getattr(record, "retired_on", None),
        unretired_by=getattr(record, "unretired_by", None),
        unretired_on=getattr(record, "unretired_on", None),
    )
    # Each holder's own attribution, not the role's last write. `save` is a
    # full replacement, so taking these off `record.updated_*` would restate
    # every holder as added by whoever last touched the role, rewriting the
    # audit on every unrelated write.
    attributed = {held.member_id: held for held in record.holder_attribution}
    holders = [
        RoleHolderRow(
            role_slug=role.slug,
            member_id=member_id,
            is_default=(member_id == role.default_holder),
            added_by=(
                attributed[member_id].added_by
                if member_id in attributed
                else record.created_by
            ),
            added_on=(
                attributed[member_id].added_on
                if member_id in attributed
                else record.created_on
            ),
        )
        for member_id in role.holders
    ]
    return row, holders


class RolesRepository:
    """The role collection as stored, behind the port the use cases hold."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _version(self) -> int:
        version = await self._session.scalar(
            select(MembersSet.version).where(MembersSet.id == _SET_ROW_ID)
        )
        if version is None:
            raise RuntimeError(
                "the access module has no version row — has the migration run?"
            )
        return int(version)

    async def load(self) -> tuple[Sequence[RoleRecord], int]:
        version = await self._version()
        rows = list(await self._session.scalars(select(RoleRow).order_by(RoleRow.slug)))
        held = list(await self._session.scalars(select(RoleHolderRow)))
        by_slug: dict[str, list[RoleHolderRow]] = {}
        for holder in held:
            by_slug.setdefault(holder.role_slug, []).append(holder)
        return (
            tuple(_record_from_rows(row, by_slug.get(row.slug, [])) for row in rows),
            version,
        )

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None:
        """Persist the full replacement set, conditionally on the version it was
        loaded at — the same optimistic serialization every membership write
        rides, on the same row."""
        bumped = await self._session.execute(
            update(MembersSet)
            .where(
                MembersSet.id == _SET_ROW_ID,
                MembersSet.version == expected_version,
            )
            .values(version=expected_version + 1)
            .returning(MembersSet.version)
        )
        if bumped.scalar() is None:
            await self._session.rollback()
            raise StaleRolesError(
                f"the access module moved past version {expected_version} while "
                f"this write was validating; reload and revalidate"
            )
        # Deleted holders first: they carry the foreign key into `roles`, so
        # the referencing rows have to go before the rows they reference.
        await self._session.execute(delete(RoleHolderRow))
        await self._session.execute(delete(RoleRow))

        # Inserted in the opposite order, and flushed between: the roles must
        # exist before a holder can reference one. Ordering the two `add`
        # groups is not enough on its own — the unit of work decides insert
        # order for itself, and with no `relationship()` declared between these
        # mappers it sorted holders ahead of roles and the foreign key
        # rejected them. The flush makes the dependency explicit rather than
        # inferred.
        prepared = [_rows_from_record(record) for record in records]
        self._session.add_all(row for row, _holders in prepared)
        await self._session.flush()
        for _row, holders in prepared:
            self._session.add_all(holders)
        await self._session.commit()


class PostgresRoles:
    """The `RolesStore` port, opening its own session per operation.

    The composition-root collaborator, shaped like `PostgresMembers`: the admin
    surfaces hold one of these rather than a session, so nothing above the
    adapter layer learns about sessions.
    """

    async def load(self) -> tuple[Sequence[RoleRecord], int]:
        async with session() as opened:
            return await RolesRepository(opened).load()

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None:
        async with session() as opened:
            await RolesRepository(opened).save(
                records, expected_version=expected_version
            )
