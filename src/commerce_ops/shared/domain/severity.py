"""The shared `Severity` vocabulary: how loudly a finding asks for attention.

Implements `shared-vocabulary`'s severity requirement. Three tiers, and
deliberately only three: below-threshold noise is not a severity but an
absence of one — something not worth reporting produces no attention item
at all, so there is nothing left for a fourth member to grade.

These are the reporting tiers the domain map's `SignificanceTier` scale
grades into. `briefing` speaks them today; `monitoring`'s percentage bands
grade into the same three, which is why they live here rather than in
either module.
"""

from __future__ import annotations

from enum import Enum


class Severity(Enum):
    MONITOR = "monitor"
    DIAGNOSE = "diagnose"
    CRITICAL = "critical"
