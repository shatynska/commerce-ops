from __future__ import annotations

from commerce_ops.access.application.admin_session import (
    exchange_link_token,
    mint_admin_link,
    verify_admin_session,
)
from commerce_ops.access.application.members import (
    BOOTSTRAP_ADMIN_VARIABLE,
    MemberRecord,
    MembersStore,
    StaleMembersError,
    create_member,
    deactivate_member,
    list_members,
    reactivate_member,
    seed_bootstrap_admin,
    update_member,
)
from commerce_ops.access.application.ports import (
    AdminSessionStore,
    LinkTokenStore,
)
from commerce_ops.access.application.roles import (
    SEEDED_ROLES,
    RoleRecord,
    RolesStore,
    StaleRolesError,
    activate_role,
    add_role_holder,
    create_role,
    list_role_records,
    list_roles,
    move_role_default,
    remove_role_holder,
    resolve_seeding_administrator,
    retire_role,
    seed_roles,
    unretire_role,
    update_role,
)
from commerce_ops.access.application.use_cases import (
    resolve_admin_capability,
    resolve_scope,
)

# The directory and its rejection are part of the public surface: the
# composition root loads a directory and hands it to `resolve_scope`, and a
# malformed one must be catchable at startup without reaching into
# `access.domain`.
from commerce_ops.access.domain.members import (
    InvalidMembersError,
    Member,
    Members,
)
from commerce_ops.access.domain.roles import (
    InvalidRolesError,
    Role,
    Roles,
    RoleStatus,
)

__all__ = [
    "BOOTSTRAP_ADMIN_VARIABLE",
    "SEEDED_ROLES",
    "AdminSessionStore",
    "InvalidMembersError",
    "InvalidRolesError",
    "LinkTokenStore",
    "Member",
    "MemberRecord",
    "Members",
    "MembersStore",
    "Role",
    "RoleRecord",
    "RoleStatus",
    "Roles",
    "RolesStore",
    "StaleMembersError",
    "StaleRolesError",
    "activate_role",
    "add_role_holder",
    "create_member",
    "create_role",
    "deactivate_member",
    "exchange_link_token",
    "list_members",
    "list_role_records",
    "list_roles",
    "mint_admin_link",
    "move_role_default",
    "reactivate_member",
    "remove_role_holder",
    "resolve_admin_capability",
    "resolve_scope",
    "resolve_seeding_administrator",
    "retire_role",
    "seed_bootstrap_admin",
    "seed_roles",
    "unretire_role",
    "update_member",
    "update_role",
    "verify_admin_session",
]
