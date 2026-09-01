"""The shared `Discipline` vocabulary: which discipline owns a piece of work.

Implements `shared-vocabulary`'s discipline requirement. A closed set of
twelve, one per ownership boundary the launch playbook divides along.
Deliberately a weak closure: a future context adding a discipline (say
monitoring's `sales` or `health`) costs one member, not a structural
change — and until such a member exists, the set is exactly these twelve.
"""

from __future__ import annotations

from enum import Enum


class Discipline(Enum):
    STRATEGY = "strategy"
    FINANCE = "finance"
    SETUP = "setup"
    INVENTORY = "inventory"
    CREATIVE = "creative"
    LISTING = "listing"
    RANK = "rank"
    PRICE = "price"
    PPC = "ppc"
    CUSTOMER = "customer"
    EXTERNAL = "external"
    TRAFFIC = "traffic"

    def __str__(self) -> str:
        """The value, not `Enum`'s `Discipline.LISTING` default.

        `shared-vocabulary` requires a single-valued vocabulary object to
        render as its value, and an enum carries exactly one. Without this,
        every site interpolating a discipline says `Discipline.LISTING`
        where it means `listing` — `launch_playbook.py`'s own rejection
        message did.
        """
        return self.value
