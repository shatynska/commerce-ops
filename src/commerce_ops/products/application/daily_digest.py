"""The `daily` product-monitoring cadence's use case.

Implements `product-monitoring`'s "Daily Cadence Lists Existing Product
Names" requirement. A database-read failure is let through, not swallowed
here -- see `add-product-agent-daily-digest`'s design.md, Decisions, on
why a read failure must be distinguishable from a delivery failure.
"""

from __future__ import annotations

from collections.abc import Sequence

from commerce_ops.products.application.ports import ProductNameReader


async def run_daily_digest(reader: ProductNameReader) -> Sequence[str]:
    return await reader.list_names()
