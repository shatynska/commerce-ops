"""Tests for `ProductRepository`, the `launch-instance` capability's store.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/add-products-store/specs/launch-instance/spec.md`. Every
`#### Scenario:` in that delta is accounted for below; see
`openspec/changes/add-products-store/test-manifest.md` for the full
scenario-to-test mapping and the specified/derived/deliberately-untested
classification of each assertion.

## The interface under test does not exist yet, and its shape is INVENTED

At the time this pass was written this project has no DB driver, no ORM
model, and no repository anywhere (`add-products-store` is its first
persistence layer) -- so every test in this file is expected to fail with
`ModuleNotFoundError` until the implementation lands. Per
`ai-toolkit:testing`'s failure-state taxonomy, that failure establishes only
absence, nothing about whether the scenarios below are well-formed.

`tasks.md` 3.1 fixes only the shape of the *operations* the repository must
support ("create, get by id, get by SKU, update current gate"), not method
names, a constructor, or how rejection is signaled. This file assumes, and
`conftest.py`'s module docstring records as an INVENTED/DERIVED fixture
assumption:

- `ProductRepository(session: AsyncSession)`, with `create`, `get_by_id`,
  `get_by_sku`, and `update_current_gate` as async methods, each committing
  its own work.
- `create()` returns an object exposing `.id`, `.sku`, `.asin`, `.name`,
  `.playbook_version`, `.current_gate`, and `.launch_date` attributes.
  `get_by_id` / `get_by_sku` return that same shape, or `None` if nothing
  matches.
- A single `ProductRepositoryError` (imported from the same module) is
  raised for every rejection the delta spec describes: a duplicate SKU, an
  unrecognized gate, or an update targeting a nonexistent product. The spec
  never distinguishes these by signaling mechanism, and this project's
  domain layer already has precedent for a single named exception per
  rejected-operation family (`launch_playbook.InvalidPlaybookError`) rather
  than a hierarchy per cause -- so one exception type is used here rather
  than three invented subtypes for causes the spec treats identically
  ("the operation is rejected").

If the real implementation differs in any of the above -- a different
module path, different method names, a different return shape, a different
signaling mechanism (e.g. `None` instead of a raised exception) -- correcting
the import, the constructor call, or the `pytest.raises` target is a
**fixture correction** (failure state 3 in `ai-toolkit:testing`), not a
change to what each test asserts: the state postconditions each test checks
(what was persisted, what was *not* persisted, what a re-read reports) are
what trace to the spec, and those are the assertions that must survive any
such correction unweakened.

## Test-database lifecycle

Each test generates its own unique SKU (`conftest.unique_sku`) rather than
assuming an empty database or adding a truncate/rollback fixture -- no
artifact records a convention for this database's per-test lifecycle. See
`test-manifest.md`'s unresolved project questions.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Final

import pytest
from commerce_ops.products.infrastructure.driven.product_repository import (  # type: ignore[import-untyped]
    ProductRepository,
    ProductRepositoryError,
)

from .conftest import unique_sku

pytestmark = pytest.mark.anyio

# SPECIFIED: the eight gate ids `launch-playbook` defines, exactly as the
# `launch-instance` delta spec enumerates them (not imported from the
# `launch-playbook` domain module -- design.md's Decisions section is
# explicit that this capability does not depend on that module's gate
# enum for this constrained column list).
EIGHT_GATE_IDS: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

NOT_A_GATE: Final = "not-a-real-gate"


# ---------------------------------------------------------------------------
# Requirement: A product is persisted with its catalog identity
# ---------------------------------------------------------------------------


async def test_creating_with_only_required_fields_persists_absent_optionals(
    repository: ProductRepository,
) -> None:
    """Scenario: A product is created with only the required fields.

    WHEN a product is created with a SKU, a name, and a playbook version,
    and no ASIN or launch date
    THEN the product is persisted with those fields set and ASIN and launch
    date reported as absent.
    """
    sku = unique_sku()

    product = await repository.create(sku=sku, name="Widget", playbook_version="v1")

    # SPECIFIED: the given fields are persisted as given.
    assert product.sku == sku
    assert product.name == "Widget"
    assert product.playbook_version == "v1"
    # SPECIFIED: ASIN and launch date are reported as absent.
    assert product.asin is None
    assert product.launch_date is None
    # SPECIFIED (requirement statement): a unique identifier is persisted.
    assert product.id is not None


async def test_creating_with_every_field_persists_all_five_values(
    repository: ProductRepository,
) -> None:
    """Scenario: A product is created with every field.

    WHEN a product is created with a SKU, a name, a playbook version, an
    ASIN, and a launch date
    THEN the product is persisted with all five values present.
    """
    sku = unique_sku()

    product = await repository.create(
        sku=sku,
        name="Widget",
        playbook_version="v1",
        asin="B0EXAMPLE1",
        launch_date=date(2027, 3, 1),
    )

    # SPECIFIED: all five values are present.
    assert product.sku == sku
    assert product.name == "Widget"
    assert product.playbook_version == "v1"
    assert product.asin == "B0EXAMPLE1"
    assert product.launch_date == date(2027, 3, 1)


async def test_creating_with_a_duplicate_sku_is_rejected(
    repository: ProductRepository,
) -> None:
    """Scenario: A duplicate SKU is rejected.

    WHEN a product is created with a SKU that already belongs to an
    existing product
    THEN the creation is rejected and no new record is persisted.
    """
    sku = unique_sku()
    original = await repository.create(sku=sku, name="Widget", playbook_version="v1")

    # DERIVED (rejection mechanism): see module docstring -- a
    # `ProductRepositoryError` is the invented signal for every rejection
    # this delta spec describes. Scoped to only the call under test, per
    # `python`'s `references/testing.md` (a wider block risks passing for
    # an unrelated raise).
    with pytest.raises(ProductRepositoryError):
        await repository.create(
            sku=sku, name="A Different Widget", playbook_version="v1"
        )

    # SPECIFIED: no new record was persisted -- the SKU still resolves to
    # the original product, not a second one.
    reread = await repository.get_by_sku(sku)
    assert reread is not None
    assert reread.id == original.id
    assert reread.name == "Widget"


# ---------------------------------------------------------------------------
# Requirement: A product's current gate is restricted to the launch-playbook
# gate sequence
# ---------------------------------------------------------------------------


async def test_a_new_product_defaults_to_the_first_gate(
    repository: ProductRepository,
) -> None:
    """Scenario: A new product defaults to the first gate.

    WHEN a product is created without specifying a current gate
    THEN its current gate is reported as `commit`.
    """
    product = await repository.create(
        sku=unique_sku(), name="Widget", playbook_version="v1"
    )

    # SPECIFIED: defaults to `commit`, the first gate in the sequence.
    assert product.current_gate == "commit"


async def test_creating_with_an_unrecognized_gate_is_rejected(
    repository: ProductRepository,
) -> None:
    """Scenario: An unrecognized gate is rejected (create half).

    WHEN a product is created ... with a current gate that is not one of
    the eight `launch-playbook` gate ids
    THEN the operation is rejected and the product's stored gate is
    unchanged.

    DERIVED: for the create path there is no prior "stored gate" to remain
    unchanged, so the create-side counterpart asserted here is that
    rejection means no product is persisted at all -- the closest reading
    of "unchanged" available before any record exists. The update path,
    where a stored gate literally stays unchanged, is asserted separately
    below.
    """
    sku = unique_sku()

    with pytest.raises(ProductRepositoryError):
        await repository.create(
            sku=sku,
            name="Widget",
            playbook_version="v1",
            current_gate=NOT_A_GATE,
        )

    # DERIVED (see above): nothing was persisted under the attempted SKU.
    assert await repository.get_by_sku(sku) is None


async def test_updating_to_an_unrecognized_gate_is_rejected(
    repository: ProductRepository,
) -> None:
    """Scenario: An unrecognized gate is rejected (update half).

    WHEN a product is ... updated with a current gate that is not one of
    the eight `launch-playbook` gate ids
    THEN the operation is rejected and the product's stored gate is
    unchanged.
    """
    product = await repository.create(
        sku=unique_sku(), name="Widget", playbook_version="v1"
    )
    assert product.current_gate == "commit"  # precondition

    with pytest.raises(ProductRepositoryError):
        await repository.update_current_gate(product.id, NOT_A_GATE)

    # SPECIFIED: the product's stored gate is unchanged.
    reread = await repository.get_by_id(product.id)
    assert reread is not None
    assert reread.current_gate == "commit"


@pytest.mark.parametrize("gate_id", EIGHT_GATE_IDS)
async def test_creating_with_each_of_the_eight_gate_ids_is_accepted(
    gate_id: str, repository: ProductRepository
) -> None:
    """DERIVED, not a named scenario.

    The requirement states a product's current gate SHALL be one of the
    eight `launch-playbook` gate ids. The two named scenarios cover only
    the default (`commit`, on omission) and a rejected, unrecognized
    value -- neither exercises an explicitly-given *recognized* gate at
    creation. Parametrized over all eight so the requirement's stated
    bound is checked in full, following this project's own precedent for
    testing a spec's fixed-vocabulary requirement exhaustively rather than
    with one representative sample
    (`tests/unit/products/infrastructure/test_playbook_loader.py`'s
    `CONFIRMATION_GATES` / `AUTOMATIC_GATES` parametrization).
    """
    product = await repository.create(
        sku=unique_sku(),
        name="Widget",
        playbook_version="v1",
        current_gate=gate_id,
    )

    # DERIVED: an explicitly recognized gate is accepted as given.
    assert product.current_gate == gate_id


# ---------------------------------------------------------------------------
# Requirement: A product can be read back by identifier or by SKU
# ---------------------------------------------------------------------------


async def test_a_product_is_retrieved_by_its_identifier(
    repository: ProductRepository,
    new_repository: Callable[[], AbstractAsyncContextManager[ProductRepository]],
) -> None:
    """Scenario: A product is retrieved by its identifier.

    WHEN a product is read using the identifier it was persisted with
    THEN the same product is returned with every field it was persisted
    with.
    """
    created = await repository.create(
        sku=unique_sku(),
        name="Widget",
        playbook_version="v1",
        asin="B0EXAMPLE2",
        launch_date=date(2027, 6, 15),
    )

    # Read through an independent repository/session, so this proves the
    # write reached Postgres rather than merely a session identity map.
    async with new_repository() as other:
        reread = await other.get_by_id(created.id)

    assert reread is not None
    # SPECIFIED: the same product, every field it was persisted with.
    assert reread.id == created.id
    assert reread.sku == created.sku
    assert reread.name == created.name
    assert reread.playbook_version == created.playbook_version
    assert reread.asin == created.asin
    assert reread.launch_date == created.launch_date
    assert reread.current_gate == created.current_gate


async def test_a_product_is_retrieved_by_its_sku(
    repository: ProductRepository,
    new_repository: Callable[[], AbstractAsyncContextManager[ProductRepository]],
) -> None:
    """Scenario: A product is retrieved by its SKU.

    WHEN a product is read using the SKU it was persisted with
    THEN the same product is returned.
    """
    created = await repository.create(
        sku=unique_sku(), name="Widget", playbook_version="v1"
    )

    async with new_repository() as other:
        reread = await other.get_by_sku(created.sku)

    # SPECIFIED: the same product is returned.
    assert reread is not None
    assert reread.id == created.id
    assert reread.sku == created.sku


@pytest.mark.parametrize(
    "lookup",
    [
        pytest.param("get_by_id", id="by-unknown-identifier"),
        pytest.param("get_by_sku", id="by-unknown-sku"),
    ],
)
async def test_reading_an_unknown_product_reports_absence(
    lookup: str, repository: ProductRepository
) -> None:
    """Scenario: Reading an unknown product reports absence.

    WHEN a product is read using an identifier or a SKU that no persisted
    product has
    THEN the system reports that no product was found, rather than an
    error.
    """
    unknown_key: object = uuid.uuid4() if lookup == "get_by_id" else unique_sku()

    method = getattr(repository, lookup)
    result = await method(unknown_key)

    # SPECIFIED: absence is reported (`None`), not an error raised.
    assert result is None


# ---------------------------------------------------------------------------
# Requirement: A product's current gate can be updated
# ---------------------------------------------------------------------------


async def test_updating_current_gate_to_a_valid_gate_persists_the_change(
    repository: ProductRepository,
    new_repository: Callable[[], AbstractAsyncContextManager[ProductRepository]],
) -> None:
    """Scenario: A product's current gate is updated to a valid gate.

    WHEN an existing product's current gate is updated to `order`
    THEN reading the product back reports `order` as its current gate.
    """
    product = await repository.create(
        sku=unique_sku(), name="Widget", playbook_version="v1"
    )
    assert product.current_gate == "commit"  # precondition

    await repository.update_current_gate(product.id, "order")

    # Independent repository/session, per the identifier-lookup test above.
    async with new_repository() as other:
        reread = await other.get_by_id(product.id)

    # SPECIFIED: reading the product back reports `order`.
    assert reread is not None
    assert reread.current_gate == "order"


async def test_updating_a_nonexistent_product_is_rejected(
    repository: ProductRepository,
) -> None:
    """Scenario: Updating a nonexistent product is rejected.

    WHEN a current-gate update targets an identifier that no persisted
    product has
    THEN the update is rejected.
    """
    unknown_id = uuid.uuid4()

    # DERIVED (rejection mechanism): see module docstring.
    with pytest.raises(ProductRepositoryError):
        await repository.update_current_gate(unknown_id, "order")


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - `created_at` / `updated_at`. `design.md`'s column table adds them, but
#   the delta spec's Requirement ("A product is persisted with its catalog
#   identity") names only identifier, SKU, ASIN, name, playbook version,
#   launch date, and current gate as what SHALL be persisted -- these two
#   columns are an implementation detail design.md records, not something
#   the spec's scenarios assert on.
# - The exact type/hierarchy of `ProductRepositoryError` beyond "some
#   exception is raised". See the module docstring's INVENTED section.
# - Gate-transition validation (e.g. moving from `commit` straight to
#   `graduated`). design.md's Non-Goals is explicit this is out of scope:
#   "this change only stores and updates *which* gate a product is
#   currently at; enforcing the launch-playbook's rules about how it got
#   there is future work."
