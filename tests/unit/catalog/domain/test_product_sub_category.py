"""`Product.record_sub_category` — the sub-category finding, held as a
standalone fact on the aggregate (`product-catalog`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/product-catalog/spec.md`

Covers, from the two ADDED requirements:

- *A sub-category finding can be recorded against a product* — all three
  scenarios (recorded for a product with none, a later recording
  replaces the earlier one, recording does not require a particular
  stage).
- *A product reports its recorded sub-category, or its absence* — its one
  scenario (an unrecorded sub-category reports absence, not an empty
  string).

`tasks.md` 6.4 asks for unit tests of both `Product.record_sub_category`
and `catalog.application.record_sub_category`, "mirroring the existing
`record_asin` tests"; this file is the domain half. The application half
— the use case wiring a store around this method, mirroring
`record_asin`'s own shape — is in
`tests/unit/catalog/application/test_record_sub_category.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

`design.md` Decision 4 declares `record_sub_category` as a plain method on
`Product` with no I/O:

    def record_sub_category(self, sub_category: str) -> None:
        self.sub_category = sub_category

Construction and this one method are the smallest unit that can observe
all four scenarios above — no store, no session, matching the level
`test_product_lifecycle.py` already established for this aggregate's
other standalone facts.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 4: the method name and signature above, that
it is "a standalone fact, not part of the stage machine, overwritable, no
confirmer tracked", and mirrors `record_asin` "exactly".

INVENTED, recorded in `test-manifest.md`:

- That `Product` exposes a `sub_category` attribute readable directly
  (`product.sub_category`), mirroring how `test_product_lifecycle.py`
  reads `product.stage`/`product.stage_entered_at` directly rather than
  through a separate reader. `tasks.md` 3.1 fixes the field's presence on
  `Product` but not that it is exposed under this exact name; a different
  reader name is a fixture correction.
- That a freshly `register`ed product's `sub_category` reads `None` before
  anything is recorded — the requirement says "reports it as absent, ...
  never as an empty or default value" without fixing the sentinel;
  `None` is what `record_asin`'s own `asin` field already uses for
  "nothing recorded yet" (`tests/unit/catalog/domain/test_product_lifecycle.py`
  reads `.stage_confirmed_by is None` for an analogous "nothing yet"
  fact), so it is taken as the project's own convention rather than
  invented fresh here.

## Expected first-run state

`Product.record_sub_category` and the `sub_category` field do not exist
yet (`tasks.md` 3.1), so every test here is expected to fail: most on
`AttributeError` (no `record_sub_category` method, or no `sub_category`
attribute to read). Per `ai-toolkit:testing` that establishes absence
only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Retired

T_REGISTERED = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_RETIRED = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
CONFIRMER = "Helen"

NODE = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
LATER_NODE = "Home & Kitchen > Kitchen & Dining > Kitchen Utensils & Gadgets"


def _registered() -> Product:
    return Product.register(
        sku=Sku("WIDGET-SUBCAT-001"),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=T_REGISTERED,
    )


# ---------------------------------------------------------------------------
# Requirement: A sub-category finding can be recorded against a product
# ---------------------------------------------------------------------------


def test_a_sub_category_is_recorded_for_a_product_with_none() -> None:
    """Scenario: A sub-category is recorded for a product with none.

    WHEN a sub-category node is recorded for a product that has none
    recorded yet
    THEN reading the product back reports that node.
    """
    product = _registered()

    product.record_sub_category(NODE)

    # SPECIFIED: reading it back reports that node.
    assert product.sub_category == NODE


def test_a_later_recording_replaces_the_earlier_one() -> None:
    """Scenario: A later recording replaces the earlier one.

    WHEN a sub-category node is recorded for a product that already has
    one recorded
    THEN reading the product back reports the later node, not the earlier
    one.
    """
    product = _registered()
    product.record_sub_category(NODE)

    product.record_sub_category(LATER_NODE)

    # SPECIFIED: the later node, not the earlier one.
    assert product.sub_category == LATER_NODE
    assert product.sub_category != NODE


def test_recording_does_not_require_a_particular_stage() -> None:
    """Scenario: Recording does not require a particular stage.

    WHEN a sub-category node is recorded for a product in `Retired`
    THEN the recording succeeds exactly as it would for a product in any
    other stage.
    """
    product = _registered()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_RETIRED)
    assert product.stage == Retired()  # precondition

    product.record_sub_category(NODE)

    # SPECIFIED: the recording succeeds — reading it back reports the node.
    assert product.sub_category == NODE
    # DERIVED: the stage itself is untouched — this is not a stage
    # transition ("not part of the stage machine").
    assert product.stage == Retired()


# ---------------------------------------------------------------------------
# Requirement: A product reports its recorded sub-category, or its absence
# ---------------------------------------------------------------------------


def test_an_unrecorded_sub_category_reports_absence() -> None:
    """Scenario: An unrecorded sub-category reports absence.

    WHEN a registered product that has never had a sub-category recorded
    is read back
    THEN its sub-category is reported as absent, not as an empty string.
    """
    product = _registered()

    # SPECIFIED: absent, never an empty or default value.
    assert product.sub_category is None
    assert product.sub_category != ""
