"""Resolving an established identity to what it may see, over the roster.

Implements `access-scope`'s resolution requirements. Every path answers
with an `AccessScope` — never `None`, never an exception — because the
callers are read use cases that must be able to filter unconditionally,
and because a resolution that could fail would fail toward the asker at
exactly the moment access control matters most.

Product-level differentiation is deliberately absent since
`move-principals-to-roster`: an active roster member sees every product,
and what a person may see will be differentiated by *information kind* in
a later change, never by product.

Both resolutions read the roster per call rather than a cached copy:
`admin-session` promises that deactivating a person revokes their access
on their next request, and a cache would have to be invalidated across
two processes to keep that true. A roster is tens of rows.
"""

from __future__ import annotations

import logging
from typing import Any

from commerce_ops.access.application.roster import RosterStore, people_of
from commerce_ops.access.domain.principals import Person
from commerce_ops.shared.domain.access_scope import AccessScope

_logger = logging.getLogger(__name__)


async def _active_person(roster: RosterStore, identity: str) -> Person | None:
    """The active person carrying `identity`, or `None`.

    `None` covers all three fail-closed cases alike — unknown,
    deactivated, and a roster that could not be read — because no caller
    may distinguish them: an unreadable store must never widen access,
    and must never surface as an error toward the asker.
    """
    try:
        rows, _ = await roster.load()
    except Exception:
        _logger.exception(
            "the roster could not be read while resolving access for '%s'; "
            "resolving as no access",
            identity,
        )
        return None

    for person in people_of(rows):
        if person.slack_identity == identity and person.active:
            return person
    return None


async def resolve_scope(roster: Any, *, identity: str) -> AccessScope:
    """What `identity` may see, according to the roster.

    An active member sees every product. A deactivated member, an
    identity the roster does not carry, and a roster that cannot be read
    each see nothing: access fails closed, and every case is answered
    with the same kind of value rather than a distinct "unknown".
    """
    person = await _active_person(roster, identity)
    return AccessScope.unrestricted() if person is not None else AccessScope.nothing()


async def resolve_admin_capability(roster: Any, *, identity: str) -> bool:
    """Whether `identity` holds the admin surface's write authority.

    Fail-closed: an identity the roster does not carry, one carried only
    by a deactivated entry, an active entry without the admin flag, and a
    roster that cannot be read each answer `False`. Membership of any
    shape confers nothing by itself — an admin who is deactivated is not
    an admin, and an active member without the flag never was.
    """
    person = await _active_person(roster, identity)
    return person is not None and person.admin
