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
