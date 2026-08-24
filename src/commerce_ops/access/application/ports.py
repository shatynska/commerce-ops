"""Consumer-owned ports `access.application` depends on.

Satisfied by a callable the composition root closes over catalog's public
surface, the way briefing's readers already are. `access` never imports
another module's code: it is the catalog that knows what a SKU names, and
this port is the whole of what `access` needs to ask it.

The resolver is wired with the unrestricted scope by construction — it
answers what a SKU names, not what an asker may see — so deriving a scope
never depends on a scope having already been derived.
"""

from __future__ import annotations

from typing import Protocol

from commerce_ops.shared.domain.identity import ProductId, Sku


class SkuResolver(Protocol):
    """Resolves a granted SKU to the product it names.

    Absence is `None`, never an exception: a grant naming a SKU no product
    has is a stale line in a reviewed file, and it must cost the asker
    nothing but that one grant.
    """

    async def __call__(self, sku: Sku) -> ProductId | None: ...
