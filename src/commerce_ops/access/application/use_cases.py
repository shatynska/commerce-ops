"""Resolving an established identity to what it may see.

Implements `access-scope`'s resolution requirements. Every path answers with
an `AccessScope` — never `None`, never an exception — because the callers
are read use cases that must be able to filter unconditionally, and because
a resolution that could fail would fail toward the asker at exactly the
moment access control matters most.
"""

from __future__ import annotations

import logging

from commerce_ops.access.application.ports import SkuResolver
from commerce_ops.access.domain.principals import PrincipalsDirectory
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId

_logger = logging.getLogger(__name__)


async def resolve_scope(
    directory: PrincipalsDirectory,
    resolve_sku: SkuResolver,
    *,
    identity: str,
) -> AccessScope:
    """What `identity` may see, according to `directory`.

    An identity the directory does not declare sees nothing: access fails
    closed, and a stranger is answered with the same kind of value everyone
    else gets rather than a distinct "unknown".
    """
    principal = directory.entry_for(identity)
    if principal is None:
        return AccessScope.nothing()

    if principal.all_products:
        return AccessScope.unrestricted()

    permitted: list[ProductId] = []
    for sku in principal.granted_skus:
        product_id = await resolve_sku(sku)
        if product_id is None:
            # A stale grant narrows what this principal sees and nothing
            # more: failing here would let one outdated line lock someone
            # out of every product they may legitimately see.
            _logger.warning(
                "principal '%s' is granted SKU '%s', which no product has; "
                "the grant confers nothing",
                identity,
                sku.value,
            )
            continue
        permitted.append(product_id)

    return AccessScope.permitting(permitted)
