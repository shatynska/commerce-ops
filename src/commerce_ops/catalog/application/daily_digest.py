"""The `daily` product-monitoring cadence's use case.

Implements `product-monitoring`'s "Daily Cadence Lists Existing Product
Names" requirement. Moved here from the launch module (then `products.application`) with the table
split: "which products exist" is catalog's question (design.md Decision 9
as amended). A database-read failure is let through, not swallowed here —
see `add-product-agent-daily-digest`'s design.md, Decisions, on why a read
failure must be distinguishable from a delivery failure.
"""

from __future__ import annotations

from collections.abc import Sequence

from commerce_ops.catalog.application.ports import ProductNameReader


async def run_daily_digest(reader: ProductNameReader) -> Sequence[str]:
    return await reader.list_names()
