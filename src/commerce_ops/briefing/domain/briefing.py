"""The briefing aggregate: what one audience is told, on one day.

Implements the `briefing` capability's *A clean briefing is not sent*.

Assembled, never persisted — this slice's briefing is a digest of what is
open right now, so it carries no memory between days and needs no store
(design.md, Decision 4). If routing or history later wants one, the
aggregate is where it attaches.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from commerce_ops.briefing.domain.attention import AttentionItem, BriefingError


@dataclass(frozen=True, slots=True)
class Briefing:
    """One period's attention items for one audience.

    Knows whether it is clean, and refuses to be rendered for delivery
    when it is: silence is this aggregate's own rule, not a condition the
    scheduled job is trusted to remember.
    """

    period: date
    audience: str
    items: tuple[AttentionItem, ...]

    @property
    def is_clean(self) -> bool:
        return not self.items

    def for_delivery(self) -> Sequence[AttentionItem]:
        """The items to deliver — never callable on a clean briefing.

        A clean day is not an empty message: it is no message at all, so
        asking a clean briefing what to send is a caller error rather
        than a case with an empty answer.
        """
        if self.is_clean:
            raise BriefingError(
                f"the briefing for {self.period.isoformat()} is clean and is "
                "not delivered; a clean briefing sends nothing at all"
            )
        return self.items
