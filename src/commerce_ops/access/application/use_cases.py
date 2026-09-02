"""Resolving an established identity to what it may see, over the membership.

Implements `access-scope`'s resolution requirements. Every path answers
with an `AccessScope` — never `None`, never an exception — because the
callers are read use cases that must be able to filter unconditionally,
and because a resolution that could fail would fail toward the asker at
exactly the moment access control matters most.

Product-level differentiation is deliberately absent since
`move-principals-to-roster`: an active member sees every product,
and what a member may see will be differentiated by *information kind* in
a later change, never by product.

Both resolutions read the membership per call rather than a cached copy:
`admin-session` promises that deactivating a member revokes their access
on their next request, and a cache would have to be invalidated across
two processes to keep that true. A membership is tens of rows.
"""

from __future__ import annotations

import logging
from typing import Any

from commerce_ops.access.application.members import MembersStore, members_of
from commerce_ops.access.domain.members import Member
from commerce_ops.shared.domain.access_scope import AccessScope

_logger = logging.getLogger(__name__)


async def _active_member(members: MembersStore, identity: str) -> Member | None:
    """The active member carrying `identity`, or `None`.

    `None` covers all three fail-closed cases alike — unknown,
    deactivated, and a membership that could not be read — because no caller
    may distinguish them: an unreadable store must never widen access,
    and must never surface as an error toward the asker.
    """
    try:
        rows, _ = await members.load()
    except Exception:
        _logger.exception(
            "the membership could not be read while resolving access for '%s'; "
            "resolving as no access",
            identity,
        )
        return None

    for member in members_of(rows):
        if member.slack_identity == identity and member.active:
            return member
    return None


async def resolve_scope(members: Any, *, identity: str) -> AccessScope:
    """What `identity` may see, according to the membership.

    An active member sees every product. A deactivated member, an
    identity the membership does not carry, and a membership that cannot be read
    each see nothing: access fails closed, and every case is answered
    with the same kind of value rather than a distinct "unknown".
    """
    member = await _active_member(members, identity)
    return AccessScope.unrestricted() if member is not None else AccessScope.nothing()


async def resolve_admin_capability(members: Any, *, identity: str) -> bool:
    """Whether `identity` holds the admin surface's write authority.

    Fail-closed: an identity the membership does not carry, one carried only
    by a deactivated entry, an active entry without the admin flag, and a
    members that cannot be read each answer `False`. Membership of any
    shape confers nothing by itself — an admin who is deactivated is not
    an admin, and an active member without the flag never was.
    """
    member = await _active_member(members, identity)
    return member is not None and member.admin
