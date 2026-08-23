"""The launch side's cause order and severity grading — data, not code.

Implements the `briefing` capability's ranking clause: "The launch-side
cause order SHALL rank an at-risk launch date first, then a gate awaiting
confirmation, then overdue non-blocking steps."

This module is the whole of what `briefing` knows about launches, and it
is a table. Monitoring's eight-level order arrives in a later slice as a
sibling table read by the same `collapse` — which is what "the order is
data, the collapse is code" buys.

The grading follows the domain map's `SignificanceTier` reading: a launch
date at risk is a binary event, and binary events are always critical; a
gate awaiting confirmation has a human decision outstanding and
progression paused on it; an overdue step that blocks nothing is worth
watching, not diagnosing.
"""

from __future__ import annotations

from typing import Final

from commerce_ops.briefing.domain.attention import CauseOrder
from commerce_ops.shared.domain.severity import Severity

#: A blocking step's due period passed unresolved — the launch date slips.
LAUNCH_DATE_AT_RISK: Final = "launch-date-at-risk"

#: Everything the gate waits on is satisfied except the human decision.
GATE_AWAITING_CONFIRMATION: Final = "gate-awaiting-confirmation"

#: A step that blocks nothing is past its due period, unresolved.
OVERDUE_STEP: Final = "overdue-step"

LAUNCH_CAUSE_ORDER: Final = CauseOrder(
    (LAUNCH_DATE_AT_RISK, GATE_AWAITING_CONFIRMATION, OVERDUE_STEP)
)

LAUNCH_SEVERITIES: Final[dict[str, Severity]] = {
    LAUNCH_DATE_AT_RISK: Severity.CRITICAL,
    GATE_AWAITING_CONFIRMATION: Severity.DIAGNOSE,
    OVERDUE_STEP: Severity.MONITOR,
}
