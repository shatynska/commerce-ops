from __future__ import annotations

from commerce_ops.briefing.application.ports import (
    BriefingNotifier,
    CatalogProduct,
    LaunchReports,
    ProductReader,
)
from commerce_ops.briefing.application.use_cases import (
    assemble_daily_briefing,
    render_briefing,
    run_daily_briefing,
)

# The aggregate and its item are part of the public surface: a caller that
# receives a `Briefing` must be able to ask whether it is clean, and read
# the items it carries, without reaching into `briefing.domain`.
from commerce_ops.briefing.domain.attention import (
    AttentionItem,
    BriefingError,
    Evidence,
)
from commerce_ops.briefing.domain.briefing import Briefing

__all__ = [
    "AttentionItem",
    "Briefing",
    "BriefingError",
    "BriefingNotifier",
    "CatalogProduct",
    "Evidence",
    "LaunchReports",
    "ProductReader",
    "assemble_daily_briefing",
    "render_briefing",
    "run_daily_briefing",
]
