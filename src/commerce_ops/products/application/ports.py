"""Consumer-owned ports `products.application` depends on.

`.importlinter`'s `module-layers` contract forbids `products.application`
from importing `products.infrastructure` directly. `ProductRepository`
(infrastructure) satisfies `ProductNameReader` structurally -- its
`list_names()` method already matches this Protocol's shape -- so it can be
passed in without either layer importing the other by name. See
`add-product-agent-daily-digest`'s design.md, Decisions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ProductNameReader(Protocol):
    async def list_names(self) -> Sequence[str]: ...
