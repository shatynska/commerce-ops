"""Write use cases of the `roles` capability.

The role collection lives behind the `RolesStore` port, and these seven
operations — plus the startup seed — are the only way it changes. Every write
is validated by constructing the **entire** `Roles` the write would produce and
reading it against the membership, so the same rulebook guards every path and a
rejected write reports every fault at once (`InvalidRolesError`) while
persisting nothing.

Two things differ from `members` beside it, both deliberate.

**Writes serialize on the membership's version row.** The member/role invariant
spans both collections — a member may not be deactivated while they are an
active role's default holder — so the two are one write-serialization boundary.
Two independent version cells would let a deactivation and a default move each
win their own race and together leave an active role holding a deactivated
default (`design.md` Decision 8). `StaleRolesError` is an alias of
`StaleMembersError` for the same reason: there is one race to lose.

**The slug is the identifier.** No identifier is generated. A step will store
the slug and a vendored file must be able to name it in advance, so it is
chosen once and never updatable — the inverse of a member's generated `uuid4`,
and for the inverse reason.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from commerce_ops.access.application.members import (
    SYSTEM_PRINCIPAL,
    MembersStore,
    StaleMembersError,
    members_of,
)
from commerce_ops.access.domain.members import Members
from commerce_ops.access.domain.roles import (
    InvalidRolesError,
    Role,
    Roles,
    RoleStatus,
    membership_faults,
    permits_transition,
)

_logger = logging.getLogger(__name__)

StaleRolesError = StaleMembersError
"""The role collection loses the *same* race the membership does.

Not a distinct exception: `design.md` Decision 8 puts both collections on one
version row, so there is one conditional persist and one way to lose it.
Exported under this name so a caller reading role code is not left wondering
whether a second race exists.
"""

_WRITE_ATTEMPTS = 3
"""How many times a write retries after losing the set-version race."""

_UPDATABLE = ("title",)
"""Exactly what `update_role` may change. The slug is immutable, holders move
only through the holder use cases, and status only through the transitions, so
every transition carries its own attribution."""


@dataclass(slots=True)
class HolderRecord:
    """One holder of a role, with when they were added and by whom.

    Attribution per holder rather than per role: a role's `updated_*` pair
    records its last write of any kind, so reading a holder's provenance off it
    would restate the role's last title correction as the moment every holder
    joined. Carried here so a holder added a month ago still says so after the
    role is retired, renamed, or given another holder.
    """

    member_id: str
    added_by: str | None = None
    added_on: datetime | None = None


@dataclass(slots=True)
class RoleRecord:
    """One stored role: the position plus its attribution trail.

    The attribution mirrors `MemberRecord`'s exactly, including the split
    between `updated_*` and the status-transition pair, so the admin can
    present the same audit for both collections.
    """

    role: Role
    created_by: str | None = None
    created_on: datetime | None = None
    updated_by: str | None = None
    updated_on: datetime | None = None
    retired_by: str | None = None
    retired_on: datetime | None = None
    unretired_by: str | None = None
    unretired_on: datetime | None = None
    holder_attribution: tuple[HolderRecord, ...] = ()
    """When each holder was added, and by whom. Carried beside the role rather
    than on it: `Role` is the domain value and knows nothing of attribution,
    exactly as `Member` does not."""

    @property
    def slug(self) -> str:
        return self.role.slug

    @property
    def title(self) -> str:
        return self.role.title

    @property
    def status(self) -> RoleStatus:
        return self.role.status

    @property
    def holders(self) -> tuple[str, ...]:
        return self.role.holders

    @property
    def default_holder(self) -> str | None:
        return self.role.default_holder


class RolesStore(Protocol):
    """The role collection's persistence port.

    Shaped after `MembersStore`: `load` returns every stored row — retired
    included, since slug uniqueness spans them — with the current set-version;
    `save` persists a full replacement set conditionally on that version,
    raising `StaleRolesError` when it has moved.
    """

    async def load(self) -> tuple[Sequence[Any], int]: ...

    async def save(self, rows: Sequence[Any], *, expected_version: int) -> None: ...


def _as_record(row: Any) -> RoleRecord:
    """A loaded row as a `RoleRecord`, whatever concrete type the store
    yielded — the attribute spellings are the port's contract."""
    if isinstance(row, RoleRecord):
        return row
    return RoleRecord(
        role=row.role,
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        retired_by=getattr(row, "retired_by", None),
        retired_on=getattr(row, "retired_on", None),
        unretired_by=getattr(row, "unretired_by", None),
        unretired_on=getattr(row, "unretired_on", None),
        holder_attribution=tuple(getattr(row, "holder_attribution", ()) or ()),
    )


def roles_of(rows: Sequence[Any]) -> tuple[Role, ...]:
    """The collection a set of stored rows carries, retired included."""
    return tuple(row.role for row in rows)


def _copy(row: Any) -> RoleRecord:
    """A fresh record for `row`, never the loaded object itself — so a write
    that loses the save race has mutated nothing."""
    record = _as_record(row)
    return replace(record) if record is row else record


def _find(rows: Sequence[Any], slug: str) -> int:
    for index, row in enumerate(rows):
        if row.role.slug == slug:
            return index
    raise ValueError(f"no stored role carries the slug '{slug}'")


async def _membership(members: MembersStore | None) -> Members:
    """The membership the candidate collection is read against.

    `None` is accepted so a caller with no membership to hand — a read, or a
    test double — is not obliged to invent one; the membership-dependent rules
    then simply find nothing to object to, and the intrinsic rules still apply.
    """
    if members is None:
        return Members()
    rows, _version = await members.load()
    return Members(members=members_of(rows))


def _validate(rows: Sequence[Any], membership: Members) -> None:
    """Construct the collection the write would produce and read it against the
    membership; `InvalidRolesError` propagates carrying every fault."""
    candidate = Roles(roles=roles_of(rows))
    faults = membership_faults(candidate, membership)
    if faults:
        raise InvalidRolesError(faults)


async def list_roles(*, roles: RolesStore) -> tuple[Role, ...]:
    """Every role the collection carries, retired included.

    The read half of this capability's public surface. Retired roles are
    answered too, because "is this role still active" is a question the caller
    has to be able to ask rather than have decided for it — the same reasoning
    `list_members` records for deactivated entries.
    """
    rows, _version = await roles.load()
    return roles_of(rows)


async def list_role_records(*, roles: RolesStore) -> tuple[RoleRecord, ...]:
    """Every stored role with its attribution, for the admin surface's audit."""
    rows, _version = await roles.load()
    return tuple(_as_record(row) for row in rows)


async def create_role(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
    title: str,
    status: RoleStatus | str = RoleStatus.DRAFT,
    default_holder: str | None = None,
) -> RoleRecord:
    """Create a role, attributed to `principal`.

    The initial status and — where that status is `active` — the default holder
    are taken in the *same* write. A role is never persisted in a state its own
    status forbids and then corrected: composing an active role as create-draft,
    add-holder, activate would satisfy the letter of the rules while recording
    an activation in the attribution trail that no admin performed.
    """
    wanted = RoleStatus(status)
    holders = (default_holder,) if default_holder is not None else ()

    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)

        # The faults `Role.__post_init__` cannot see, gathered BEFORE it is
        # constructed. Building the role first would raise on its intrinsic
        # faults and hide these, so a role submitted with a malformed slug that
        # is also already taken would report only the first half — and `roles`
        # requires a write "rejected reporting every fault at once".
        beyond: list[str] = []
        if any(row.role.slug == slug for row in rows):
            beyond.append(
                f"the slug '{slug}' is carried by more than one role — a slug "
                f"names exactly one position, retired roles included"
            )
        # A holder is an active member at the moment it is added, whatever the
        # role's status. `membership_faults` only reaches a deactivated default
        # on an ACTIVE role, so without this a draft role could be created
        # holding somebody who has left.
        if default_holder is not None:
            beyond.extend(_inactive_holder_faults(membership, default_holder, slug))

        now = datetime.now(UTC)
        try:
            proposed = Role(
                slug=slug,
                title=title,
                status=wanted,
                holders=tuple(h for h in holders if h is not None),
                default_holder=default_holder,
            )
        except InvalidRolesError as intrinsic:
            raise InvalidRolesError((*intrinsic.faults, *beyond)) from intrinsic
        if beyond:
            raise InvalidRolesError(tuple(beyond))

        record = RoleRecord(
            role=proposed,
            created_by=principal,
            created_on=now,
            holder_attribution=(
                (
                    HolderRecord(
                        member_id=default_holder, added_by=principal, added_on=now
                    ),
                )
                if default_holder is not None
                else ()
            ),
        )
        candidate = (*rows, record)
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(
        f"create_role lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def update_role(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
    **fields: Any,
) -> RoleRecord:
    """Correct a role's title. Nothing else is updatable.

    Renaming rewrites nothing: no stored reference to a role is by title, which
    is the whole reason the title is free to correct while the slug is not.
    """
    if "slug" in fields or "identifier" in fields:
        raise ValueError(
            f"a role's slug is not updatable: '{slug}' keeps the slug it was "
            f"created with, because a step stores the slug and a vendored file "
            f"names it; retire the role and create its successor instead"
        )
    if "status" in fields:
        raise ValueError(
            "status is not updatable: use retire_role or unretire_role, so the "
            "transition records who made it"
        )
    if "holders" in fields or "default_holder" in fields:
        raise ValueError(
            "holders are not updatable here: use add_role_holder, "
            "remove_role_holder or move_role_default, so each change records "
            "who made it"
        )
    unknown = sorted(set(fields) - set(_UPDATABLE))
    if unknown:
        raise ValueError(
            f"a role carries no updatable field named {', '.join(unknown)}"
        )

    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)
        index = _find(rows, slug)
        record = _copy(rows[index])
        record.role = replace(record.role, **fields)
        record.updated_by = principal
        record.updated_on = datetime.now(UTC)
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(
        f"update_role lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def _transition(
    *,
    roles: RolesStore,
    members: MembersStore | None,
    principal: str,
    slug: str,
    target: RoleStatus,
    verb: str,
) -> RoleRecord:
    """Move a role to `target`, refusing any transition the lifecycle forbids.

    The refusal is stated before the collection is validated so that an
    attempted return to `draft` explains itself as a forbidden transition,
    rather than as whatever coherence fault the resulting collection happens
    to carry.
    """
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)
        index = _find(rows, slug)
        record = _copy(rows[index])
        current = record.role.status

        if current is target:
            raise InvalidRolesError((f"role '{slug}' is already {target.value}",))
        if not permits_transition(current, target):
            raise InvalidRolesError(
                (
                    (
                        f"role '{slug}' cannot move from {current.value} to "
                        f"{target.value} — no role returns to draft, and "
                        f"{current.value} permits only "
                        f"{', '.join(sorted(t.value for t in _permitted(current)))}"
                    ),
                )
            )

        record.role = replace(record.role, status=target)
        now = datetime.now(UTC)
        if target is RoleStatus.RETIRED:
            record.retired_by, record.retired_on = principal, now
        elif current is RoleStatus.RETIRED:
            record.unretired_by, record.unretired_on = principal, now
        else:
            record.updated_by, record.updated_on = principal, now

        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(f"{verb} lost the set-version race {_WRITE_ATTEMPTS} times")


def _permitted(current: RoleStatus) -> frozenset[RoleStatus]:
    return frozenset(
        target for target in RoleStatus if permits_transition(current, target)
    )


async def retire_role(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
) -> RoleRecord:
    """Retire a role, from `active` or from `draft`.

    Retiring retains the role whole — slug, title, holders and attribution
    intact. `draft -> retired` is permitted because the collection offers no
    deletion: without it a position sketched and then abandoned could never be
    taken out of the working set.
    """
    return await _transition(
        roles=roles,
        members=members,
        principal=principal,
        slug=slug,
        target=RoleStatus.RETIRED,
        verb="retire_role",
    )


async def activate_role(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
) -> RoleRecord:
    """Move a role to `active`, from `draft` or from `retired`.

    Refused unless the role has a default holder who is an active member. The
    retired-side check is not redundant: a retired role keeps its holders
    unenforced, so its default may have been deactivated in the meantime.
    """
    return await _transition(
        roles=roles,
        members=members,
        principal=principal,
        slug=slug,
        target=RoleStatus.ACTIVE,
        verb="activate_role",
    )


unretire_role = activate_role
"""Un-retiring *is* activating: one transition, reached from the retired side.

Named twice because the admin surface offers it under the word that fits the
role's current status, and a caller should not have to know that the two are
the same write.
"""


async def add_role_holder(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
    member_id: str,
    make_default: bool = False,
) -> RoleRecord:
    """Add a member as a holder of a role.

    Holders may be added to a `draft` or `retired` role as freely as to an
    active one — un-retiring needs a default holder, so setting one up first
    has to be possible.
    """
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)
        index = _find(rows, slug)
        record = _copy(rows[index])

        if record.role.holds(member_id):
            raise InvalidRolesError(
                (
                    (
                        f"member '{member_id}' already holds role '{slug}' — a "
                        f"member holds a role at most once"
                    ),
                )
            )
        _refuse_inactive_holder(membership, member_id, slug)

        now = datetime.now(UTC)
        record.role = replace(
            record.role,
            holders=(*record.role.holders, member_id),
            default_holder=(member_id if make_default else record.role.default_holder),
        )
        record.holder_attribution = (
            *record.holder_attribution,
            HolderRecord(member_id=member_id, added_by=principal, added_on=now),
        )
        record.updated_by = principal
        record.updated_on = now
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(
        f"add_role_holder lost the set-version race {_WRITE_ATTEMPTS} times"
    )


def _inactive_holder_faults(
    membership: Members, member_id: str, slug: str
) -> tuple[str, ...]:
    """Why `member_id` may not hold `slug`, if anything.

    Returned rather than raised so a caller gathering every fault can add these
    to the rest; `_refuse_inactive_holder` raises them for the callers whose
    write has nothing else to report.

    An empty membership answers nothing: a caller that supplied no membership
    store has none to check against, and inventing a fault there would refuse
    every holder rather than none.
    """
    if not membership.members:
        return ()
    known = {member.identifier: member for member in membership.members}
    member = known.get(member_id)
    if member is None:
        return (
            (
                f"member '{member_id}' is not on the membership, so cannot "
                f"hold role '{slug}'"
            ),
        )
    if not member.active:
        return (
            (
                f"member '{member_id}' is deactivated, so cannot be added as a "
                f"holder of role '{slug}' — a holder is an active member at "
                f"the moment it is added"
            ),
        )
    return ()


def _refuse_inactive_holder(membership: Members, member_id: str, slug: str) -> None:
    faults = _inactive_holder_faults(membership, member_id, slug)
    if faults:
        raise InvalidRolesError(faults)


async def remove_role_holder(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
    member_id: str,
) -> RoleRecord:
    """Remove a holder from a role.

    Removing the default holder of an `active` role is refused whatever the
    rest of the holders are — where others remain the default must be moved
    first, and where none remain the role would be left without one. No holder
    is ever promoted in their place: a promotion the system chose would name a
    person nobody picked, in the one place where guessing is least acceptable.
    """
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)
        index = _find(rows, slug)
        record = _copy(rows[index])
        role = record.role

        if not role.holds(member_id):
            raise InvalidRolesError(
                (f"member '{member_id}' does not hold role '{slug}'",)
            )
        if role.status is RoleStatus.ACTIVE and role.is_default(member_id):
            others = tuple(h for h in role.holders if h != member_id)
            raise InvalidRolesError(
                (
                    f"member '{member_id}' is the default holder of the active "
                    f"role '{slug}': "
                    + (
                        "move the default to another holder first"
                        if others
                        else "an active role always has a default holder, so "
                        "retire the role or add another holder first"
                    ),
                )
            )

        remaining = tuple(h for h in role.holders if h != member_id)
        record.role = replace(
            role,
            holders=remaining,
            default_holder=(
                None if role.is_default(member_id) else role.default_holder
            ),
        )
        # The departed holder's attribution leaves with them.
        record.holder_attribution = tuple(
            held for held in record.holder_attribution if held.member_id != member_id
        )
        record.updated_by = principal
        record.updated_on = datetime.now(UTC)
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(
        f"remove_role_holder lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def move_role_default(
    *,
    roles: RolesStore,
    members: MembersStore | None = None,
    principal: str,
    slug: str,
    member_id: str,
) -> RoleRecord:
    """Move a role's default to another of its holders.

    The named member must already hold the role: the default is always one of
    the holders, so moving it is a choice among them rather than a way to add
    one.
    """
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roles.load()
        membership = await _membership(members)
        index = _find(rows, slug)
        record = _copy(rows[index])

        if not record.role.holds(member_id):
            raise InvalidRolesError(
                (
                    (
                        f"member '{member_id}' is not a holder of role "
                        f"'{slug}' — the default must be one of the role's "
                        f"holders, so add them as a holder first"
                    ),
                )
            )
        _refuse_inactive_holder(membership, member_id, slug)

        record.role = replace(record.role, default_holder=member_id)
        record.updated_by = principal
        record.updated_on = datetime.now(UTC)
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate, membership)
        try:
            await roles.save(candidate, expected_version=version)
        except StaleRolesError:
            continue
        return record
    raise StaleRolesError(
        f"move_role_default lost the set-version race {_WRITE_ATTEMPTS} times"
    )


SEEDED_ROLES: tuple[tuple[str, str, RoleStatus], ...] = (
    ("supply-chain", "Supply Chain Manager", RoleStatus.ACTIVE),
    ("ppc", "PPC Manager", RoleStatus.ACTIVE),
    ("brand", "Brand Manager", RoleStatus.ACTIVE),
    ("catalog", "Catalog Manager", RoleStatus.ACTIVE),
    ("controller", "Financial Controller", RoleStatus.ACTIVE),
    ("creative", "Creative Manager", RoleStatus.ACTIVE),
    ("customer-service", "Customer Service Manager", RoleStatus.ACTIVE),
    ("marketing", "Marketing Manager", RoleStatus.ACTIVE),
    ("operations", "Operations Manager", RoleStatus.DRAFT),
    ("managing-director", "Managing Director", RoleStatus.DRAFT),
    ("it", "IT Manager", RoleStatus.DRAFT),
)
"""The eleven roles the startup step seeds, with the status each is seeded in.

The eight `ACTIVE` are the ones `activate-the-seeded-step-set` assigns the
seeded step set to, so they must be assignable from the first boot. The three
`DRAFT` own no step; seeding them active would assert a position is filled when
it is not, and would pin the seeding administrator as the default holder of
eleven roles rather than eight.
"""


def _identifier_of(value: Any) -> str | None:
    """The member identifier `value` names, however it is handed over.

    The admin seeding answers a record; a caller with only an identifier hands
    that. Both reach this seed, so neither is made to convert first.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    nested = getattr(value, "member", None)
    if nested is not None and not isinstance(nested, str):
        resolved = _identifier_of(nested)
        if resolved is not None:
            return resolved
    for attribute in ("identifier", "member_id", "id"):
        found = getattr(value, attribute, None)
        if isinstance(found, str) and found:
            return found
    return None


_NEVER = datetime.max.replace(tzinfo=UTC)
"""Sorts last, so a row with no recorded creation time never wins the
earliest-created comparison over one that has a time."""


def resolve_seeding_administrator(
    rows: Sequence[Any], *, established: Any = None
) -> str | None:
    """Whose the seeded active roles' default holder is.

    `established` is the member the admin seeding created or promoted on this
    run, where it established one. Otherwise the **earliest-created** active
    admin, ties and absent creation times broken by identifier so the choice is
    deterministic across runs — not the first stored row, whose order is the
    store's business rather than a fact about the membership.

    The fallback always resolves in practice: `members` has the admin seeding
    alter nothing *only where* the membership already holds an active admin, so
    one exists to be chosen — and where it holds none, that step has already
    failed and this one does not run. `None` is answered only for a membership
    with no active admin at all, which the caller treats as the failure it is.
    """
    named = _identifier_of(established)
    if named is not None:
        return named
    admins = [row for row in rows if row.member.active and row.member.admin]
    if not admins:
        return None
    earliest = min(
        admins,
        key=lambda row: (
            getattr(row, "created_on", None) or _NEVER,
            row.member.identifier,
        ),
    )
    return str(earliest.member.identifier)


async def seed_roles(
    *,
    roles: RolesStore,
    members: MembersStore,
    seeding_administrator: Any = None,
) -> tuple[RoleRecord, ...]:
    """Ensure the eleven seeded roles exist, and answer the ones added.

    Runs in the step that seeds the first admin, after that admin exists and
    before the server starts: the roles' default holders are members, so the
    membership must be usable first, and a later step seeds the playbook that
    will come to reference these slugs.

    **Add-only.** A slug already in the collection is left exactly as it
    stands — whatever its title, status or holders — so an operator's edits
    survive every subsequent deployment. This is the trade `seed_playbook`
    already makes: a seed that overwrote would discard those edits at every
    deploy, and a mistake in the seeded set is corrected in the admin instead.

    `seeding_administrator` is the member the admin seeding created or promoted
    on this run, where it established one; a record or a bare identifier is
    accepted alike. Otherwise it is resolved from the stored membership — see
    `resolve_seeding_administrator`, which records why that fallback is total.

    Attributed to the same reserved system principal the admin seeding uses, so
    a seeded role is always distinguishable from one a human created. No
    membership entry is altered and nothing is conferred on the administrator:
    holding a role carries no authority, so `members`' guarantee that the
    bootstrap variable confers nothing is untouched.
    """
    rows, version = await roles.load()
    present = {row.role.slug for row in rows}
    missing = tuple(entry for entry in SEEDED_ROLES if entry[0] not in present)
    if not missing:
        return ()

    member_rows, _member_version = await members.load()
    membership = Members(members=members_of(member_rows))
    administrator = resolve_seeding_administrator(
        member_rows, established=seeding_administrator
    )
    if administrator is None and any(
        status is RoleStatus.ACTIVE for _slug, _title, status in missing
    ):
        raise InvalidRolesError(
            (
                (
                    "the role seed cannot resolve a seeding administrator: the "
                    "membership holds no active admin, so the roles seeded "
                    "active would have no default holder. The admin seeding "
                    "step runs before this one precisely so that it does"
                ),
            )
        )

    now = datetime.now(UTC)
    added: list[RoleRecord] = []
    for slug, title, status in missing:
        holders = (
            (administrator,)
            if status is RoleStatus.ACTIVE and administrator is not None
            else ()
        )
        added.append(
            RoleRecord(
                role=Role(
                    slug=slug,
                    title=title,
                    status=status,
                    holders=holders,
                    default_holder=holders[0] if holders else None,
                ),
                created_by=SYSTEM_PRINCIPAL,
                created_on=now,
                holder_attribution=tuple(
                    HolderRecord(
                        member_id=held, added_by=SYSTEM_PRINCIPAL, added_on=now
                    )
                    for held in holders
                ),
            )
        )

    candidate = (*rows, *added)
    _validate(candidate, membership)
    await roles.save(candidate, expected_version=version)
    _logger.info(
        "seeded %d role(s): %s",
        len(added),
        ", ".join(record.role.slug for record in added),
    )
    return tuple(added)
