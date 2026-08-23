"""Tests for the shared identity value objects (`shared-vocabulary`).

Derived strictly from the ADDED requirements in
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/shared-vocabulary/spec.md`:

- Requirement: *Identity value objects validate at construction*
- Requirement: *Value objects are immutable and compare by value*
  (the identity-VO half; the stage-value half of that requirement is
  covered in `test_lifecycle_stage.py` alongside the rest of the stage
  vocabulary)

See `test-manifest.md` at the change root for the full scenario-to-test
accounting.

## The interface under test does not exist yet, and its shape is INVENTED

At the time this pass was written, `shared/domain` holds no vocabulary
modules (the change introduces them — tasks.md 1.1), so every test here is
expected to fail on an absent target (`ModuleNotFoundError`). Per
`ai-toolkit:testing`, that failure establishes only absence — the
assertions below never executed.

No artifact fixes module paths, class names, constructor shapes, or the
rejection signal. This file assumes, and the manifest records as
unresolved project questions:

- `commerce_ops.shared.domain.identity` as the module, exporting
  `ProductId`, `Sku`, `Asin`, `MarketplaceId` (the four VOs proposal.md
  and tasks.md 1.1 name).
- Each is constructed from a single positional string and exposes it as
  `.value`.
- Rejected construction raises `ValueError` (or a subclass) — the natural
  Python signal for construction-time validation; no artifact names an
  error type.

If the real implementation differs — a different module path, a
`.__str__`-only surface instead of `.value`, a custom exception type —
correcting the import, the accessor, or the `pytest.raises` target is a
fixture correction (failure state 3 in `ai-toolkit:testing`), not a change
to what each test asserts: that invalid values are rejected at
construction, valid ones are carried unchanged, and instances are
immutable and value-equal is what traces to the spec and must survive any
such correction unweakened.
"""

from __future__ import annotations

import pytest

from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku

# DERIVED example values: the spec fixes no sample SKU/ASIN/marketplace.
# "B0EXAMPLE1" is exactly ten alphanumeric characters, so it satisfies the
# ASIN rule; "ATVPDKIKX0DER" is the Amazon US marketplace id design.md's
# Decision 8 names as the backfill value.
VALID_ASIN = "B0EXAMPLE1"
VALID_MARKETPLACE = "ATVPDKIKX0DER"


# ---------------------------------------------------------------------------
# Requirement: Identity value objects validate at construction
# ---------------------------------------------------------------------------


def test_a_valid_sku_is_constructed_and_reports_its_value() -> None:
    """Scenario: A valid SKU is constructed.

    WHEN a SKU value object is constructed from a non-empty string with no
    surrounding whitespace
    THEN it is created and reports that string as its value.
    """
    sku = Sku("WIDGET-001")

    # SPECIFIED: it reports that string as its value.
    assert sku.value == "WIDGET-001"


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: ProductId(""), id="product-id"),
        pytest.param(lambda: Sku(""), id="sku"),
        pytest.param(lambda: Asin(""), id="asin"),
        pytest.param(lambda: MarketplaceId(""), id="marketplace-id"),
    ],
)
def test_an_empty_identity_value_is_rejected(make: object) -> None:
    """Scenario: An empty identity value is rejected.

    WHEN a product identifier, SKU, ASIN, or marketplace identifier is
    constructed from an empty value
    THEN construction fails with an error naming the offending value.

    The scenario's "naming the offending value" clause is asserted on the
    malformed-ASIN scenario below, where there is a non-empty value for
    the error to name; an empty string has no content to appear in a
    message, so here only the rejection itself is asserted (recorded in
    the manifest as a deliberately narrower reading for this case).
    """
    # SPECIFIED: construction fails. DERIVED: the mechanism is a raised
    # ValueError (see module docstring).
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: Sku(" WIDGET-001"), id="sku-leading"),
        pytest.param(lambda: Sku("WIDGET-001 "), id="sku-trailing"),
        pytest.param(lambda: Asin(f" {VALID_ASIN}"), id="asin-leading"),
        pytest.param(lambda: Asin(f"{VALID_ASIN} "), id="asin-trailing"),
        pytest.param(
            lambda: MarketplaceId(f" {VALID_MARKETPLACE}"),
            id="marketplace-leading",
        ),
        pytest.param(
            lambda: MarketplaceId(f"{VALID_MARKETPLACE} "),
            id="marketplace-trailing",
        ),
    ],
)
def test_a_padded_identity_value_is_rejected_not_trimmed(make: object) -> None:
    """Scenario: A padded identity value is rejected.

    WHEN a SKU, ASIN, or marketplace identifier is constructed from a
    string with leading or trailing whitespace
    THEN construction fails rather than silently trimming.

    Note the padded-ASIN params carry whitespace around an otherwise-valid
    ten-character ASIN, so a pass here cannot be explained by the
    length/alphanumeric rule alone — only by the whitespace rule the
    scenario states.
    """
    # SPECIFIED: construction fails (a silent trim would not raise).
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


@pytest.mark.parametrize(
    "bad_asin",
    [
        pytest.param("B0SHORT", id="too-short"),
        pytest.param("B0EXAMPLE12", id="eleven-chars"),
        pytest.param("B0EXAMPL-1", id="non-alphanumeric"),
    ],
)
def test_a_malformed_asin_is_rejected_with_the_value_named(bad_asin: str) -> None:
    """Scenario: A malformed ASIN is rejected.

    WHEN an ASIN is constructed from a value that is not exactly ten
    alphanumeric characters
    THEN construction fails with an error naming the value.
    """
    with pytest.raises(ValueError) as excinfo:
        Asin(bad_asin)

    # SPECIFIED: the error names the value.
    assert bad_asin in str(excinfo.value)


def test_a_valid_asin_is_constructed() -> None:
    """DERIVED, not a named scenario: the rejection tests above only
    establish what an ASIN refuses; that exactly ten alphanumerics are
    *accepted* traces to the requirement statement ("not exactly ten
    alphanumeric characters" is the rejection bound) but has no scenario
    of its own. Without this, an implementation rejecting everything
    would pass every ASIN test.
    """
    assert Asin(VALID_ASIN).value == VALID_ASIN


# ---------------------------------------------------------------------------
# Requirement: Value objects are immutable and compare by value
# ---------------------------------------------------------------------------


def test_two_skus_with_the_same_value_are_equal_and_hash_equal() -> None:
    """Scenario: Two value objects with the same value are equal.

    WHEN two SKU value objects are constructed from the same string
    THEN they compare equal and hash equal.
    """
    a = Sku("WIDGET-001")
    b = Sku("WIDGET-001")

    # SPECIFIED: equal and hash-equal.
    assert a == b
    assert hash(a) == hash(b)
    # SPECIFIED (requirement statement): usable as set members — two
    # equal instances collapse to one member.
    assert len({a, b}) == 1


def test_two_skus_with_different_values_are_not_equal() -> None:
    """DERIVED from the requirement statement's "exactly when their
    values are equal" — the named scenario covers only the equal half;
    without this, `__eq__` returning a constant `True` would pass it.
    """
    assert Sku("WIDGET-001") != Sku("WIDGET-002")


@pytest.mark.parametrize(
    "instance",
    [
        pytest.param(ProductId("pid-1"), id="product-id"),
        pytest.param(Sku("WIDGET-001"), id="sku"),
        pytest.param(Asin(VALID_ASIN), id="asin"),
        pytest.param(MarketplaceId(VALID_MARKETPLACE), id="marketplace-id"),
    ],
)
def test_mutation_of_a_constructed_value_object_fails(
    instance: ProductId | Sku | Asin | MarketplaceId,
) -> None:
    """Scenario: Mutation is not possible.

    WHEN code attempts to assign to a field of a constructed value object
    THEN the attempt fails.

    Parametrized over all four identity VOs because the requirement
    statement says *every* vocabulary value object is immutable.
    DERIVED mechanism: a frozen dataclass raises FrozenInstanceError
    (an AttributeError subclass); slots/NamedTuple raise AttributeError;
    other immutability schemes raise TypeError. Any of these is "the
    attempt fails"; the spec fixes no exception type.
    """
    with pytest.raises((AttributeError, TypeError)):
        instance.value = "SOMETHING-ELSE"  # type: ignore[misc]
