from __future__ import annotations

from commerce_ops.access.application.admin_session import (
    exchange_link_token,
    mint_admin_link,
    verify_admin_session,
)
from commerce_ops.access.application.ports import (
    AdminSessionStore,
    LinkTokenStore,
    SkuResolver,
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
    InvalidPrincipalsError,
    PrincipalsDirectory,
)

__all__ = [
    "AdminSessionStore",
    "InvalidPrincipalsError",
    "LinkTokenStore",
    "PrincipalsDirectory",
    "SkuResolver",
    "exchange_link_token",
    "mint_admin_link",
    "resolve_admin_capability",
    "resolve_scope",
    "verify_admin_session",
]
