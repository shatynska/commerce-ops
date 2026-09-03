"""The fixed domain values the suite arranges around.

Every name here is a **literal that does not vary** — one value spelled in many
files. A name whose value differs between files is not here, and a name that is
*generated* is a factory rather than a constant, for the reason `product_id`
gives below.

Migration matches on the value, never on the identifier: `LAUNCH_DATE`,
`STEP_ID` and their neighbours each carry several values across the suite, and
a file whose value differs from the one here keeps its own declaration. It
differs on purpose until shown otherwise.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Final

from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

#: The launch date the suite plans against.
LAUNCH_DATE: Final = date(2027, 3, 2)

#: The admin whose session the surface tests verify as.
PRINCIPAL: Final = "helen"

#: Two members, by generated identifier and display name.
ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_NAME: Final = "Bohdan Colleague"

#: Amazon US, the only marketplace the suite exercises.
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

#: The product most tests launch.
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

#: A step, and the handler registered against it.
STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"


def product_id() -> ProductId:
    """A fresh product identifier.

    **A factory, not a constant, and the distinction is load-bearing.** Sixty-
    eight files evaluate `ProductId(str(uuid.uuid4()))` at module level, which
    gives each module its own identifier — 68 distinct values. Hoisting that to
    a module-level constant here would give every one of them the *same* value,
    shared by every test in the session, so a test writing a product to a shared
    store would collide with every other, or worse, pass on a fixture a
    neighbour left behind.

    A migrated file therefore keeps its module-level binding and only the
    construction moves::

        PRODUCT_ID: Final = product_id()
    """
    return ProductId(str(uuid.uuid4()))


def any_discipline() -> Discipline:
    """Some discipline, where the test does not care which.

    Computed rather than pinned, because that is what the 24 files declaring
    `A_DISCIPLINE` as `next(iter(Discipline))` and the 13 declaring it as
    `DISCIPLINES[0]` actually do. A pinned literal would agree with them only
    while the enum's declaration order holds, and would silently stop agreeing
    the day a discipline is added at the front.
    """
    return next(iter(Discipline))
