"""`FakeProductReader`'s contract, stated directly.

The equality proof compares this reader against each of the 24 callable
`_FakeCatalog` declarations on the calls those files execute. Three things it
cannot reach are stated here instead, because each is a *decision* rather than
a value:

* **What the reader may hold is deliberately unconstrained** (`design.md` --
  Decision 7). Several locals still declare their own frozen product type, and
  four production sites probe the *served* product by attribute name, so a
  reader annotated to `tests/support/values.py::CatalogProduct` would move
  `AGENTS.md`'s same-value invariant out of the visible call site and into the
  double. A reader that happened to be handed a `CatalogProduct` at all 24 sites
  would look identical under the proof.
* **`calls` is derived from `reads`, over the same list object** -- the
  arrangement `Member.identifier` and `FakeTask.custom_field_values` already
  use. 6 locals record into `reads` and 4 into `calls`; the proof sees each
  file's own spelling and never that the two are one list.
* **14 of the 24 record nothing at all.** For those the recorder is a superset,
  licensed by `design.md` -- *Context*, and never exercised by the proof.

`AGENTS.md`'s `clickup_user_id` precedent obliges each type to name the trap at
itself: the playbook store spells `reads` as an **`int`** with no `calls`, which
`tests/unit/support/test_fake_playbooks.py` pins from the other side.

This is the shared harness's own behaviour, so it lives under
`tests/unit/support/` -- the deliberate exception to the tier layout, per
`AGENTS.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from commerce_ops.shared.domain.identity import Sku
from tests.support.fakes import FakeProductReader
from tests.support.fixtures import PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.values import CatalogProduct

pytestmark = pytest.mark.anyio

#: Distinct identifiers, so a reader that answered by lookup rather than by
#: holding could not pass by accident.
FIRST_PRODUCT_ID = product_id()
SECOND_PRODUCT_ID = product_id()


@dataclass(frozen=True)
class _BespokeProduct:
    """A product type of this file's own, standing for the 2 declarations that
    do not import the shared `CatalogProduct` (`design.md` -- Decision 8)."""

    name: str
    sku: Sku
    headline: str


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_answers_the_product_it_was_handed() -> None:
    product = CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)

    reader = FakeProductReader(product)

    assert await reader(FIRST_PRODUCT_ID) is product


async def test_answers_an_object_of_whatever_type_it_was_handed() -> None:
    """The reader is not constrained to `CatalogProduct` (Decision 7).

    Stated as a test rather than left to the annotation, because a reader
    narrowed later would still satisfy every other assertion in this file.
    """
    product = _BespokeProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU, headline="Alpha")

    reader = FakeProductReader(product)

    answered = await reader(FIRST_PRODUCT_ID)
    assert answered is product
    assert answered.headline == "Alpha"


async def test_a_fresh_reader_has_recorded_nothing() -> None:
    reader = FakeProductReader(CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU))

    assert reader.reads == []
    assert reader.calls == []


async def test_records_each_product_it_was_asked_for_in_order() -> None:
    reader = FakeProductReader(CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU))

    await reader(FIRST_PRODUCT_ID)
    await reader(SECOND_PRODUCT_ID)

    assert reader.reads == [FIRST_PRODUCT_ID, SECOND_PRODUCT_ID]


async def test_calls_is_the_same_list_object_as_reads() -> None:
    """Not merely equal to it: the same object.

    6 locals read `reads` and 4 read `calls`, and both populations migrate onto
    this one type. Two lists carrying the same value would satisfy an equality
    assertion here and still let a future edit populate one and not the other.
    """
    reader = FakeProductReader(CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU))

    await reader(FIRST_PRODUCT_ID)

    assert reader.calls is reader.reads
    assert reader.calls == [FIRST_PRODUCT_ID]


async def test_reads_is_the_stored_spelling_and_calls_cannot_be_assigned() -> None:
    """`AGENTS.md`'s `Member.id` precedent: the assignable spelling must be the
    stored one, since a read-only property cannot receive an assignment.

    `tasks.md` 3.4 measured no call site assigning either name on a catalog
    reader, which is what licenses storing `reads` and deriving `calls`. If that
    measurement is re-taken and any site assigns `calls`, this test is the one
    that has to be reversed -- deliberately, and visibly.

    The refused assignment goes through `setattr` with the name in a variable,
    rather than `reader.calls = []`: the direct form is a `mypy` error once the
    property lands, and suppressing it with an ignore comment is an *unused*
    ignore until then, so neither spelling type-checks in both states.
    """
    reader = FakeProductReader(CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU))

    reader.reads = [FIRST_PRODUCT_ID]
    assert reader.calls == [FIRST_PRODUCT_ID]

    derived = "calls"
    with pytest.raises(AttributeError):
        setattr(reader, derived, [])
