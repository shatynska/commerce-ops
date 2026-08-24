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

from datetime import datetime
from typing import Protocol

from commerce_ops.shared.domain.identity import ProductId, Sku


class LinkTokenStore(Protocol):
    """Persistence for the single-use admin link tokens (`admin-session`).

    Stores only hashes — the raw token rides the minted link and is never
    at rest. `claim` atomically spends: it answers the bound principal for
    an unspent, unexpired hash and marks it spent in the same operation,
    so a token can never exchange twice; every other case — spent,
    expired, never minted — answers `None`, indistinguishably.
    """

    async def save(
        self, *, token_hash: str, principal: str, expires_at: datetime
    ) -> None: ...

    async def claim(self, token_hash: str, *, now: datetime) -> str | None: ...


class AdminSessionStore(Protocol):
    """Persistence for the browser sessions the token exchange establishes.

    Stores only hashes, like the token store. `find` answers the bound
    principal for an unexpired session hash and `None` for everything
    else — expired and never-established alike.
    """

    async def save(
        self, *, session_hash: str, principal: str, expires_at: datetime
    ) -> None: ...

    async def find(self, session_hash: str, *, now: datetime) -> str | None: ...


class SkuResolver(Protocol):
    """Resolves a granted SKU to the product it names.

    Absence is `None`, never an exception: a grant naming a SKU no product
    has is a stale line in a reviewed file, and it must cost the asker
    nothing but that one grant.
    """

    async def __call__(self, sku: Sku) -> ProductId | None: ...
