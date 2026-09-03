"""The role collection: which positions the company staffs, and who holds them.

Implements the coherence rules of the `roles` capability. Deterministic and
I/O-free, like `access.domain.members` beside it: persistence is the store
adapter's concern (`access.infrastructure.driven.roles_repository`), which
translates stored rows into the values these constructors expect and
re-implements none of the rules below.

Two kinds of rule live here and a third deliberately does not.

*Intrinsic* rules are properties of a role or of the whole collection — a slug's
shape, its uniqueness across every role including retired ones, the default
being one of the holders, an `active` role having a default at all. Those are
checked by construction.

*Membership-dependent* rules are not, because this module never sees the
membership: that a holder is an active member, and that an active role's default
is one. They are checked by `membership_faults`, which takes the `Members`
explicitly rather than reaching for it — the invariant spans two collections
(`design.md` Decision 1) and pretending otherwise inside a frozen dataclass
would hide where it is enforced.

A role's slug is its identifier. It is chosen once and never changes, which
inverts the membership's reasoning deliberately: a member's identifier is
generated precisely so it can never be re-pointed at a different human, while a
role's must be nameable in advance because a step will store it and a vendored
file must be able to write it down.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from commerce_ops.access.domain.members import Members

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
"""Lowercase letters and digits in hyphen-separated runs: no leading, trailing
or doubled hyphen, no uppercase, no surrounding whitespace. A slug is written
by hand into a vendored file and typed into an admin form, so it is kept to the
shape that survives both."""


class InvalidRolesError(ValueError):
    """A role collection (or a role within one) fails coherence.

    Carries every fault found in one validation, not just the first — the
    shape `InvalidMembersError` established, kept so that a rejected role
    write does not have to be corrected one fault at a time.
    """

    def __init__(self, faults: Sequence[str]) -> None:
        self.faults: tuple[str, ...] = tuple(faults)
        super().__init__("; ".join(self.faults))


class RoleStatus(StrEnum):
    """Where a role sits in its lifecycle.

    From a *step's* side `DRAFT` and `RETIRED` are identical: neither takes an
    assignment. They differ in exactly one obligation — only an `ACTIVE` role
    must have a default holder — which is what lets the collection record a
    position the company intends to staff but has not (`design.md` Decision 3).
    """

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


_TRANSITIONS: dict[RoleStatus, frozenset[RoleStatus]] = {
    RoleStatus.DRAFT: frozenset({RoleStatus.ACTIVE, RoleStatus.RETIRED}),
    RoleStatus.ACTIVE: frozenset({RoleStatus.RETIRED}),
    RoleStatus.RETIRED: frozenset({RoleStatus.ACTIVE}),
}
"""The four permitted transitions (`design.md` Decision 5).

Nothing returns to `DRAFT`: once a role has been in play, `RETIRED` is what
records that it no longer is, and a return to draft would erase the
distinction. `DRAFT -> RETIRED` is permitted because the collection offers no
deletion — without it, a position sketched and then abandoned would sit in the
draft group forever with no way to clear it.
"""


def permits_transition(current: RoleStatus, target: RoleStatus) -> bool:
    """Whether a role may move from `current` to `target`."""
    return target in _TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class Role:
    """One position: its identity, its lifecycle and who holds it.

    `holders` are member identifiers; `default_holder`, where set, is one of
    them. Holding a role confers no authority — permission remains the member's
    admin flag, which this collection does not touch.

    Attribution does not live here: who created, updated, retired or un-retired
    a role is recorded on the stored row (`access.application.roles.RoleRecord`),
    the split `MemberRecord` and `launch`'s `StepRecord` already use.
    """

    slug: str
    title: str
    status: RoleStatus = RoleStatus.DRAFT
    holders: tuple[str, ...] = ()
    default_holder: str | None = None

    def __post_init__(self) -> None:
        faults = self.faults()
        if faults:
            raise InvalidRolesError(faults)

    def faults(self) -> tuple[str, ...]:
        """Every intrinsic coherence fault this role carries, named against it.

        Exposed as well as raised so a whole-collection validation can gather
        each role's faults into one rejection rather than surfacing the first
        and hiding the rest.
        """
        found: list[str] = []
        who = self.slug or "<unidentified>"

        if not self.slug:
            found.append("a role carries an empty slug")
        elif not _SLUG.match(self.slug):
            found.append(
                f"role '{self.slug}' carries a malformed slug — a slug is "
                f"lowercase letters and digits in hyphen-separated runs, with "
                f"no leading, trailing or doubled hyphen and no surrounding "
                f"whitespace"
            )

        if not self.title or not self.title.strip():
            found.append(f"role '{who}' carries an empty title")

        found.extend(self._holder_faults(who))
        return tuple(found)

    def _holder_faults(self, who: str) -> list[str]:
        found: list[str] = []

        seen: set[str] = set()
        for holder in self.holders:
            if holder in seen:
                found.append(
                    f"role '{who}' names the member '{holder}' as a holder "
                    f"more than once"
                )
                break
            seen.add(holder)

        if self.default_holder is not None and self.default_holder not in self.holders:
            found.append(
                f"role '{who}' names a default holder '{self.default_holder}' "
                f"who is not one of its holders — the default is always one of "
                f"them"
            )

        if self.status is RoleStatus.ACTIVE and self.default_holder is None:
            found.append(
                f"role '{who}' is active with no default holder — an active "
                f"role always has one, so that a step assigned to it resolves "
                f"to somebody"
            )

        return found

    def holds(self, member_identifier: str) -> bool:
        return member_identifier in self.holders

    def is_default(self, member_identifier: str) -> bool:
        return self.default_holder == member_identifier


@dataclass(frozen=True, slots=True)
class Roles:
    """Every role, validated as a whole.

    The set-level rule is slug uniqueness, and it spans *every* role,
    retired ones included: a slug is what a step stores, so re-using one would
    silently re-point every step that names it.
    """

    roles: tuple[Role, ...] = ()

    def __post_init__(self) -> None:
        faults = [fault for role in self.roles for fault in role.faults()]
        faults.extend(self._duplicate_slug_faults())
        if faults:
            raise InvalidRolesError(faults)

    def _duplicate_slug_faults(self) -> list[str]:
        seen: set[str] = set()
        duplicated: list[str] = []
        for role in self.roles:
            if role.slug in seen and role.slug not in duplicated:
                duplicated.append(role.slug)
            seen.add(role.slug)
        return [
            f"the slug '{slug}' is carried by more than one role — a slug "
            f"names exactly one position, retired roles included"
            for slug in duplicated
        ]

    def role_for(self, slug: str) -> Role | None:
        """The role carrying `slug`, or `None` where none does."""
        for role in self.roles:
            if role.slug == slug:
                return role
        return None

    def active(self) -> tuple[Role, ...]:
        return tuple(role for role in self.roles if role.status is RoleStatus.ACTIVE)

    def active_defaults_of(self, member_identifier: str) -> tuple[Role, ...]:
        """Every `active` role `member_identifier` is the default holder of.

        Plural by design. A member deactivating while holding several should
        learn the whole list in one refusal rather than discovering it one
        attempt at a time, so the caller is handed every blocking role at once
        (`members`' added requirement).
        """
        return tuple(
            role for role in self.active() if role.is_default(member_identifier)
        )


def membership_faults(roles: Roles, members: Members) -> tuple[str, ...]:
    """Every fault `roles` carries when read against `members`.

    Separate from `Roles.__post_init__` because these rules are not properties
    of the role collection alone: a holder must be a member, and an active
    role's default must be an *active* one. Keeping them here — taking the
    membership explicitly — records that the invariant spans both collections
    rather than hiding a lookup inside a frozen dataclass.
    """
    known = {member.identifier: member for member in members.members}
    found: list[str] = []

    for role in roles.roles:
        for holder in role.holders:
            member = known.get(holder)
            if member is None:
                found.append(
                    f"role '{role.slug}' names a holder '{holder}' who is not "
                    f"on the membership"
                )
                continue
            if (
                role.status is RoleStatus.ACTIVE
                and role.is_default(holder)
                and not member.active
            ):
                found.append(
                    f"role '{role.slug}' is active with a deactivated default "
                    f"holder '{holder}' — an active role's default must be an "
                    f"active member, so the role resolves to somebody who can act"
                )

    return tuple(found)
