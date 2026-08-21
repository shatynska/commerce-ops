"""Tests for `ProductRepository.list_names()`, against a real Postgres
connection.

Per `tasks.md` 8.3 of `add-product-agent-daily-digest`: "Unit test for
`ProductRepository.list_names()` (Task 2.1) -- covered under
`tests/integration/products/` per this repo's testing-tier convention,
since it exercises real Postgres." This is a **new** file, not an edit to
the existing `test_product_repository.py` (an existing test file this pass
never edits, deletes, or weakens) -- both files share
`tests/integration/products/conftest.py`'s fixtures.

## What this file does and does not account for

No `#### Scenario:` block in either of this change's delta specs names
`ProductRepository.list_names()` directly -- the delta specs state the
"lists every existing product" / "no products exist" behavior entirely at
the daily *endpoint's* level, which
`tests/unit/products/infrastructure/driving/test_monitoring_routes.py`
covers (against a faked `ProductNameReader`, per that file's own Level
reasoning). This file is DERIVED supplementary coverage for the concrete
repository method those route-level tests fake around, per `tasks.md` 8.3's
own explicit ask -- not a second accounting of either named scenario.

**No "no products exist" case is tested here.** This directory's existing
convention (see `conftest.py`'s and `test_product_repository.py`'s own
module docstrings) provides no truncate/rollback fixture -- each test
assumes rows may already exist from earlier runs, which is exactly why
`unique_sku()` exists. That same absence of isolation makes "the database
currently has zero products" unobservable here without adding new
fixture machinery (a truncation fixture), which is a fixture-infrastructure
decision beyond what this pass's fixture-correction latitude covers, not
merely a name/shape correction. Recorded as deliberately untested at this
level; the "no products exist" scenario itself remains covered at the
route level.

## The method's return shape is INVENTED

`design.md`'s Decisions fixes only that the port returns
`Sequence[str]` ("plain names, not the ORM `Product` row"). This file
assumes `ProductRepository.list_names()` itself already returns that same
`Sequence[str]` of names (rather than, say, full `Product` rows that a
separate mapping step in `products.application` would reduce to names) --
the natural reading of Task 2.1 ("Add `list_names()` to
`ProductRepository` ... returning every product's name"). If the real
method returns something else, adjusting how each test extracts a name
from the result is a fixture correction; that each created product's name
appears in what `list_names()` returns is what traces to the spec and
tasks.md, and must survive any such correction unweakened.

At the time this pass was written, `ProductRepository` has no `list_names`
method, so every test here is expected to fail (`AttributeError`) until
Task 2.1 lands.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest

from commerce_ops.products.infrastructure.driven.product_repository import (
    ProductRepository,
)

from .conftest import unique_sku

pytestmark = pytest.mark.anyio


def _unique_name() -> str:
    """A product name unique to this test run, mirroring `unique_sku()`'s
    own reasoning: no truncate/rollback fixture exists in this directory,
    so a name that could collide with a leftover row from an earlier run
    would make containment assertions unreliable.
    """
    return f"Digest Test Widget {unique_sku()}"


async def test_list_names_includes_every_created_products_name(
    repository: ProductRepository,
) -> None:
    """DERIVED from `tasks.md` 8.3/2.1 and `product-monitoring`'s "Daily
    trigger lists product names" scenario, at the repository level.

    WHEN at least one product has been persisted
    THEN `list_names()` reports its name among the names it returns.

    Containment, not equality, against the full result: this database is
    not truncated between test runs, so other products may already exist.
    Two products are created (not one) so this also confirms the method
    is not accidentally limited to a single row.
    """
    first_name = _unique_name()
    second_name = _unique_name()
    await repository.create(sku=unique_sku(), name=first_name, playbook_version="v1")
    await repository.create(sku=unique_sku(), name=second_name, playbook_version="v1")

    names = await repository.list_names()

    assert first_name in names
    assert second_name in names


async def test_list_names_reflects_products_written_by_another_session(
    repository: ProductRepository,
    new_repository: Callable[[], AbstractAsyncContextManager[ProductRepository]],
) -> None:
    """DERIVED: proves the listing reaches Postgres itself, not merely a
    session-local identity map -- the same concern
    `test_a_product_is_retrieved_by_its_identifier` addresses for
    `get_by_id`, applied to `list_names()`.
    """
    name = _unique_name()
    await repository.create(sku=unique_sku(), name=name, playbook_version="v1")

    async with new_repository() as other:
        names = await other.list_names()

    assert name in names
