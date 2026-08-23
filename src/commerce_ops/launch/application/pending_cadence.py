"""The placeholder use case for cadences with no reporting logic yet.

Covers the weekly, biweekly, monthly, and quarterly `product-monitoring`
cadences: each has a guarded, triggerable endpoint (see
`add-product-agent-daily-digest`'s tasks.md 5.1), but its content is
planned separately and is not implemented by this change. This performs no
reporting action and logs the trigger as an intentional no-op, so it reads
in logs as "not built yet," not as a silent failure.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def run_pending_cadence_report(cadence: str) -> None:
    _logger.info(
        "product-monitoring cadence '%s' triggered; reporting logic is not "
        "implemented yet (intentional no-op)",
        cadence,
    )
