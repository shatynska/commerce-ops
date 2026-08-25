from __future__ import annotations

from commerce_ops.access.application.admin_session import (
    exchange_link_token,
    mint_admin_link,
    verify_admin_session,
)
from commerce_ops.access.application.ports import (
    AdminSessionStore,
    LinkTokenStore,
)
from commerce_ops.access.application.roster import (
    BOOTSTRAP_ADMIN_VARIABLE,
    PersonRecord,
    RosterStore,
    StaleRosterError,
    create_person,
    deactivate_person,
    reactivate_person,
    seed_bootstrap_admin,
    update_person,
)
from commerce_ops.access.application.use_cases import (
    resolve_admin_capability,
    resolve_scope,
)

# The directory and its rejection are part of the public surface: the
# composition root loads a directory and hands it to `resolve_scope`, and a
# malformed one must be catchable at startup without reaching into
# `access.domain`.
from commerce_ops.access.domain.principals import (
    InvalidRosterError,
    Person,
    Roster,
)

__all__ = [
    "BOOTSTRAP_ADMIN_VARIABLE",
    "AdminSessionStore",
    "InvalidRosterError",
    "LinkTokenStore",
    "Person",
    "PersonRecord",
    "Roster",
    "RosterStore",
    "StaleRosterError",
    "create_person",
    "deactivate_person",
    "exchange_link_token",
    "mint_admin_link",
    "reactivate_person",
    "resolve_admin_capability",
    "resolve_scope",
    "seed_bootstrap_admin",
    "update_person",
    "verify_admin_session",
]
