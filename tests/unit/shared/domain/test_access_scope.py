"""Tests for the `AccessScope` value object (`shared-vocabulary`).

Derived strictly from the ADDED requirement *Access-scope vocabulary
expresses product visibility* in
`openspec/changes/introduce-access-scope/specs/shared-vocabulary/spec.md`
-- all three of its scenarios, plus the parts of the requirement statement
that carry no scenario of their own (the unrestricted scope is a distinct
construction rather than an enumeration of all products; the value follows
the vocabulary's existing immutability and value-equality rules).

See `test-manifest.md` at the change root for the full scenario-to-test
accounting.

## Why the value-object level

Every outcome the requirement states -- what a scope permits, that it is
immutable, that it compares by value -- is observable on the value alone,
with no store, no use case and no I/O. That is the smallest unit that can
observe it (`ai-toolkit:testing`'s level rule), and it is where
`test_identity_value_objects.py` and `test_lifecycle_stage.py` already put
the rest of this vocabulary.

## The interface under test does not exist yet, and its shape is INVENTED

`AccessScope` is introduced by this change (`tasks.md` 1.1), so every test
here is expected to fail on an absent target (`ModuleNotFoundError`). Per
`ai-toolkit:testing` that failure establishes only absence -- it says
nothing about whether the assertions below are any good.

Fixed by the artifacts, not invented: the type is named `AccessScope`, it
lives in `src/commerce_ops/shared/domain/`, it is either unrestricted or an
explicit (possibly empty) frozen set of `ProductId`s, and it answers a
`permits(product_id)` predicate (`proposal.md`, `design.md` Decisions 1-2,
`tasks.md` 1.1).

INVENTED, and recorded as unresolved project questions in the manifest:

- The module path `commerce_ops.shared.domain.access_scope`. The
  vocabulary's existing modules are one-per-concept (`identity`,
  `lifecycle_stage`, `discipline`, `severity`), so this follows that shape.
- How each of the two constructions is spelled. `_unrestricted()` and
  `_permitting()` below try the plausible spellings and fail loudly when
  none is present; they are the single correction point for this file.

Correcting the import or either constructor helper is a fixture correction
(failure state 3 in `ai-toolkit:testing`). What must survive unweakened is
what each test asserts: which products each of the three scope shapes
permits, that the unrestricted scope is not an enumeration, and that the
value is immutable and compares by value.
"""

from __future__ import annotations

import uuid

import pytest

from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _unrestricted() -> AccessScope:
    """The unrestricted scope."""
    return AccessScope.unrestricted()


def _permitting(*product_ids: ProductId) -> AccessScope:
    """An explicit-set scope over `product_ids`."""
    return AccessScope.permitting(product_ids)


def _permits(scope: AccessScope, product_id: ProductId) -> bool:
    """Reads the `permits` predicate, which `proposal.md` fixes by name."""
    assert hasattr(scope, "permits"), (
        "the access scope exposes no `permits` predicate, so it cannot "
        "report whether it permits a product identifier"
    )
    return bool(scope.permits(product_id))


# ---------------------------------------------------------------------------
# Scenario: The unrestricted scope permits every product
# ---------------------------------------------------------------------------


def test_the_unrestricted_scope_permits_every_product() -> None:
    """Scenario: The unrestricted scope permits every product.

    WHEN an unrestricted access scope is asked whether it permits any
    product identifier
    THEN it reports that it does.

    Three unrelated identifiers, and the third is minted *after* the scope
    was constructed -- the requirement statement's "the set of all products
    is unknowable to a value and changes after a scope is built" is only
    observable if the scope permits an identifier that did not exist when
    it was made.
    """
    first, second = _new_product_id(), _new_product_id()

    scope = _unrestricted()

    minted_later = _new_product_id()

    # SPECIFIED: it permits every product identifier.
    assert _permits(scope, first) is True
    assert _permits(scope, second) is True
    assert _permits(scope, minted_later) is True


def test_the_unrestricted_scope_is_not_an_enumeration_of_products() -> None:
    """SPECIFIED (requirement statement, no scenario of its own): "The
    unrestricted scope SHALL be a distinct construction, not a set
    enumerating all products".

    Distinctness is asserted as inequality with an explicit-set scope over
    the products that exist: an implementation that built "unrestricted" by
    enumerating the known products would compare equal to exactly that set.
    """
    known = (_new_product_id(), _new_product_id())

    assert _unrestricted() != _permitting(*known)


# ---------------------------------------------------------------------------
# Scenario: An explicit-set scope permits exactly its members
# ---------------------------------------------------------------------------


def test_an_explicit_set_scope_permits_exactly_its_members() -> None:
    """Scenario: An explicit-set scope permits exactly its members.

    WHEN an access scope is constructed from a set containing one product
    identifier and asked about that identifier and about a different one
    THEN it permits the member and does not permit the non-member.
    """
    member = _new_product_id()
    non_member = _new_product_id()

    scope = _permitting(member)

    # SPECIFIED: permits the member.
    assert _permits(scope, member) is True
    # SPECIFIED: does not permit the non-member. Without this half, a
    # `permits` returning a constant True would pass.
    assert _permits(scope, non_member) is False


def test_a_two_member_scope_permits_both_and_nothing_else() -> None:
    """DERIVED from the requirement statement's "permits exactly the
    members of its set": the named scenario fixes a single-member set, so
    an implementation permitting only the first member of any set would
    pass it. Two members, and one outsider.
    """
    first, second = _new_product_id(), _new_product_id()
    outsider = _new_product_id()

    scope = _permitting(first, second)

    assert _permits(scope, first) is True
    assert _permits(scope, second) is True
    assert _permits(scope, outsider) is False


# ---------------------------------------------------------------------------
# Scenario: The empty scope permits nothing
# ---------------------------------------------------------------------------


def test_the_empty_scope_permits_nothing() -> None:
    """Scenario: The empty scope permits nothing.

    WHEN an access scope is constructed from an empty set and asked whether
    it permits any product identifier
    THEN it reports that it does not.

    Two identifiers, so a `permits` that happened to answer False for one
    particular value is not what produces the pass. Reaching the assertions
    at all is the other half of the scenario: the empty set is
    *constructible*, not a rejected construction.
    """
    scope = _permitting()

    assert _permits(scope, _new_product_id()) is False
    assert _permits(scope, _new_product_id()) is False


# ---------------------------------------------------------------------------
# SPECIFIED (requirement statement): "The access scope follows the
# vocabulary's existing immutability and value-equality rules."
#
# Those rules are the `shared-vocabulary` requirement *Value objects are
# immutable and compare by value*, already covered for the identity VOs in
# `test_identity_value_objects.py`; these tests extend the same two
# assertions to this value, as the statement requires.
# ---------------------------------------------------------------------------


def test_two_scopes_over_the_same_products_are_equal_and_hash_equal() -> None:
    """SPECIFIED: value equality. Hash equality is asserted too, because
    the vocabulary's rule is stated in terms of set membership and this
    value is itself carried in sets and dict keys by its consumers.
    """
    first, second = _new_product_id(), _new_product_id()

    a = _permitting(first, second)
    b = _permitting(second, first)

    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_scopes_over_different_products_are_not_equal() -> None:
    """DERIVED, the other half of value equality: without it, an `__eq__`
    returning a constant True would satisfy the test above.
    """
    shared = _new_product_id()

    assert _permitting(shared) != _permitting(shared, _new_product_id())
    assert _permitting(shared) != _permitting()


def test_two_unrestricted_scopes_are_equal() -> None:
    """DERIVED: two separately constructed unrestricted scopes describe the
    same visibility, so value equality must hold for that construction as
    well as for the explicit-set one.
    """
    assert _unrestricted() == _unrestricted()


def test_mutation_of_a_constructed_scope_fails() -> None:
    """SPECIFIED: immutability, per the vocabulary's existing rule.

    DERIVED mechanism (the same reading `test_identity_value_objects.py`
    records): a frozen dataclass raises `FrozenInstanceError`, an
    `AttributeError` subclass; `__slots__` raises `AttributeError`; other
    immutability schemes raise `TypeError`. Any of those is "the attempt
    fails"; no artifact fixes an exception type.
    """
    scope = _permitting(_new_product_id())

    with pytest.raises((AttributeError, TypeError)):
        scope.permitted = frozenset()  # type: ignore[misc]
