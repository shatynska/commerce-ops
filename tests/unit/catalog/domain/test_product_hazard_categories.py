"""`Product.record_hazard_categories` — a compliance screening's result,
held on the aggregate in three states (`product-catalog`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/product-catalog/spec.md`

Covers, at the domain level, from three ADDED requirements:

*A hazard-category finding can be recorded against a product*
- Hazard categories are recorded for a product with none
- An empty set is recorded as an empty set
- A later recording replaces the earlier one wholesale
- An empty set replaces a recorded set
- Recording does not require a particular stage
- What was screened against is not recorded with the result

*A product reports its hazard categories in three states, never two*
- A never-screened product reports the question as open
- A cleared product reports an answered question
- A flagged product reports its categories
- A product predating the field reports the question as open

*A recorded hazard-category set is what a screening established, not what
a member ratified*
- A later screening replaces a disputed value (the recording half; the
  decision half is in
  `tests/unit/launch/application/test_rejected_hazard_finding_stands.py`)

`tasks.md` 1.1-1.4. The use-case half of the same scenarios is in
`tests/unit/catalog/application/test_record_hazard_categories.py`, and the
storage half in
`tests/integration/catalog/test_product_hazard_categories.py`. See
`test-manifest.md` at the change root for the full accounting.

## Level

Construction plus this one method — the smallest unit that can observe
every scenario above, since none of them needs a store, a session or a
launch. This is the level `test_product_sub_category.py` established for
this aggregate's other standalone fact, and this file is deliberately its
mirror.

## What is fixed, and what is INVENTED

Fixed by the delta: that recording is independent of lifecycle stage and
needs no confirmer; that a later recording replaces the earlier set
entirely; that an empty set is a *recording* rather than a way of
clearing the field; and that the three states are pairwise
distinguishable, an empty recorded set never reading as never-recorded.

Fixed by `tasks.md` 3.1: the method name `record_hazard_categories` and
the field name `hazard_categories`, "shaped exactly like
`record_sub_category`", stored "as an immutable sequence so a caller
cannot mutate what the aggregate holds".

INVENTED, recorded in `test-manifest.md`:

- **That `None` is the never-recorded reading and an empty sequence the
  recorded-and-empty one.** The delta fixes that the two must be
  distinguishable and fixes no sentinel; `design.md` Decision 1 fixes
  `NULL` and `{}` in *storage*, and `None` is what `asin` and
  `sub_category` already use on this aggregate for "nothing recorded
  yet". Every scenario about the three-state distinction is therefore
  asserted **pairwise first** — `_reading()` compares the three readings
  against one another and pins no literal — with the sentinel asserted
  separately, so a different sentinel is a fixture correction here and
  the distinction itself is not.
- That the recorded set is read back under the attribute
  `product.hazard_categories`, mirroring how `sub_category` is read.
- The comparison helper `_members()`: the delta says a *set* is recorded
  and `tasks.md` 3.1 says an immutable sequence holds it, so members are
  compared as a sequence of members rather than by pinning `tuple` or
  `list`.

## Expected first-run state

Neither `Product.record_hazard_categories` nor the `hazard_categories`
field exists yet (`tasks.md` 3.1), so every test here is expected to fail
on an absent target — `AttributeError`. Per `ai-toolkit:testing` that is
failure state 2 and establishes absence only; none of the assertions
below will have run.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching, Retired

T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_MOVED: Final = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
CONFIRMER: Final = "Helen"

FLAGGED: Final = ("supplements",)
LATER_FLAGGED: Final = ("medical devices", "lighters")
EMPTY: Final[tuple[str, ...]] = ()

#: The categories a screening screens *against* — the step's authored
#: description. Recorded nowhere, per the sixth scenario, and used here
#: only as the string that must not turn up on the product.
SCREENED_AGAINST: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)


def _registered(sku: str = "WIDGET-HAZ-001") -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=T_REGISTERED,
    )


def _reading(product: Product) -> Any:
    """What the product reports for its hazard categories.

    Read through one accessor so that the pairwise comparisons below are
    comparisons of *readings*, not of literals — the shape `tasks.md` 1.3
    asks for, which discriminates against an implementation reporting two
    of the three states identically to a caller while differing
    internally.
    """
    return product.hazard_categories


def _members(product: Product) -> list[str]:
    """The recorded members, as members.

    The delta records a *set* and `tasks.md` 3.1 holds it as an immutable
    sequence, so nothing here pins `tuple` over `list`; a reading that is
    neither fails loudly rather than comparing false.
    """
    reading = _reading(product)
    assert reading is not None, (
        "the product reports its hazard categories as never recorded where "
        "a recording was made"
    )
    assert not isinstance(reading, str), (
        f"the product reports its hazard categories as the string "
        f"{reading!r}; a set of categories is not one of them"
    )
    return list(reading)


# ---------------------------------------------------------------------------
# Requirement: A hazard-category finding can be recorded against a product
# ---------------------------------------------------------------------------


def test_hazard_categories_are_recorded_for_a_product_with_none() -> None:
    """Scenario: Hazard categories are recorded for a product with none.

    WHEN a non-empty set of hazard categories is recorded for a product
    that has none recorded yet
    THEN reading the product back reports exactly that set.

    SPECIFIED: "exactly that set" — the members, and no others.
    """
    product = _registered()

    product.record_hazard_categories(FLAGGED)

    assert _members(product) == list(FLAGGED)


def test_an_empty_set_is_recorded_as_an_empty_set() -> None:
    """Scenario: An empty set is recorded as an empty set.

    WHEN an empty set of hazard categories is recorded for a product that
    has none recorded yet
    THEN reading the product back reports an empty set, and does not
    report the categories as never recorded.

    SPECIFIED: **both** halves. The second is the one an implementation
    storing `None` for an empty input passes the first half of — and it is
    the state this whole change exists to create.
    """
    product = _registered()
    never_recorded = _reading(_registered("WIDGET-HAZ-001-B"))

    product.record_hazard_categories(EMPTY)

    assert _members(product) == []
    assert _reading(product) != never_recorded, (
        "an empty set recorded against a product reads back the same as a "
        "product nothing has ever screened; those are opposite facts"
    )


def test_a_later_recording_replaces_the_earlier_one_wholesale() -> None:
    """Scenario: A later recording replaces the earlier one wholesale.

    WHEN a set of hazard categories is recorded for a product that already
    has a different set recorded
    THEN reading the product back reports the later set alone, with no
    member of the earlier set surviving.

    SPECIFIED: both the later set being reported *and* no earlier member
    surviving — the second is what excludes a merge, which the delta names
    ("never merge with it").
    """
    product = _registered()
    product.record_hazard_categories(FLAGGED)

    product.record_hazard_categories(LATER_FLAGGED)

    assert _members(product) == list(LATER_FLAGGED)
    for earlier in FLAGGED:
        assert earlier not in _members(product), (
            f"{earlier!r} survived a wholesale replacement, so the later "
            "recording merged with the earlier one instead of replacing it"
        )


def test_an_empty_set_replaces_a_recorded_set() -> None:
    """Scenario: An empty set replaces a recorded set.

    WHEN an empty set of hazard categories is recorded for a product whose
    recorded set is non-empty
    THEN reading the product back reports an empty set.

    SPECIFIED, and this is the row that fails an implementation treating
    an empty input as "nothing to record": a screening that found the
    product clear replaces a flag an earlier screening recorded.
    """
    product = _registered()
    product.record_hazard_categories(FLAGGED)

    product.record_hazard_categories(EMPTY)

    assert _members(product) == []
    assert _reading(product) != _reading(_registered("WIDGET-HAZ-001-C")), (
        "an empty set recorded over a flag left the product reading as "
        "never screened rather than as screened and clear"
    )


def test_recording_does_not_require_a_particular_stage() -> None:
    """Scenario: Recording does not require a particular stage.

    WHEN hazard categories are recorded for a product in `Retired`
    THEN the recording succeeds exactly as it would for a product in any
    other stage.

    SPECIFIED: the recording succeeds. DERIVED: that the stage itself is
    untouched — the delta says the recording "is not a stage transition".
    """
    product = _registered()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_MOVED)
    assert product.stage == Retired()  # precondition

    product.record_hazard_categories(FLAGGED)

    assert _members(product) == list(FLAGGED)
    assert product.stage == Retired()


@pytest.mark.parametrize(
    "categories", [FLAGGED, EMPTY, LATER_FLAGGED], ids=["flagged", "empty", "several"]
)
def test_what_was_screened_against_is_not_recorded_with_the_result(
    categories: tuple[str, ...],
) -> None:
    """Scenario: What was screened against is not recorded with the result.

    WHEN a set of hazard categories is recorded for a product
    THEN reading the product back reports the recorded set and reports
    nothing about which categories the screening screened against.

    SPECIFIED, and asserted as the *absence* of the screened-against text
    anywhere on the product: "this capability records the result, never
    the question". Asserted over all three shapes of recording so that an
    implementation stashing the question alongside only one of them is
    caught.
    """
    product = _registered()

    product.record_hazard_categories(categories)

    assert _members(product) == list(categories)
    rendered = repr(vars(product)) if hasattr(product, "__dict__") else repr(product)
    assert SCREENED_AGAINST not in rendered, (
        "the product carries the categories the screening screened "
        "against; this capability records the result and never the question"
    )
    for probe in ("screened_against", "categories_screened", "screening_question"):
        assert not hasattr(product, probe), (
            f"the product exposes {probe!r}, recording what was screened "
            "against alongside the result"
        )


# ---------------------------------------------------------------------------
# Requirement: A product reports its hazard categories in three states,
# never two
# ---------------------------------------------------------------------------


def test_a_never_screened_product_reports_the_question_as_open() -> None:
    """Scenario: A never-screened product reports the question as open.

    WHEN a registered product that has never had hazard categories
    recorded is read back
    THEN its hazard categories are reported as never recorded, and not as
    an empty set.

    SPECIFIED: the second clause. Asserted against a product that *was*
    recorded empty rather than against a literal, so a different sentinel
    for "never recorded" is a fixture correction and the distinction is
    not.
    """
    never_screened = _registered()
    screened_clear = _registered("WIDGET-HAZ-002")
    screened_clear.record_hazard_categories(EMPTY)

    assert _reading(never_screened) != _reading(screened_clear), (
        "a product nothing has ever screened reads back the same as one a "
        "screening found clear"
    )
    # DERIVED from `tasks.md` 3.1's `Sequence[str] | None = None`: the
    # sentinel itself. A different sentinel is a fixture correction; the
    # assertion above is what traces to the delta.
    assert _reading(never_screened) is None


def test_a_cleared_product_reports_an_answered_question() -> None:
    """Scenario: A cleared product reports an answered question.

    WHEN a product for which an empty set was recorded is read back
    THEN its hazard categories are reported as recorded and empty,
    distinguishable from never recorded.
    """
    product = _registered()
    product.record_hazard_categories(EMPTY)

    assert _reading(product) is not None
    assert _members(product) == []


def test_a_flagged_product_reports_its_categories() -> None:
    """Scenario: A flagged product reports its categories.

    WHEN a product for which a non-empty set was recorded is read back
    THEN its hazard categories are reported as recorded, carrying exactly
    the members that were recorded.
    """
    product = _registered()

    product.record_hazard_categories(LATER_FLAGGED)

    assert _members(product) == list(LATER_FLAGGED)


def test_the_three_states_are_pairwise_distinguishable() -> None:
    """The requirement's own statement — "SHALL NOT collapse any two of
    them" — asserted pairwise rather than by comparing each reading to a
    literal.

    SPECIFIED, and stated as its own test so that a change of sentinel
    cannot silently take the distinction with it. A comparison against
    expected values passes for an implementation reporting two of the
    three states identically to a *caller* while differing internally;
    comparing the three readings against one another does not.
    """
    never = _registered("WIDGET-HAZ-003")
    clear = _registered("WIDGET-HAZ-004")
    clear.record_hazard_categories(EMPTY)
    flagged = _registered("WIDGET-HAZ-005")
    flagged.record_hazard_categories(FLAGGED)

    readings = {
        "never recorded": _reading(never),
        "recorded and empty": _reading(clear),
        "recorded and non-empty": _reading(flagged),
    }
    for left, right in (
        ("never recorded", "recorded and empty"),
        ("never recorded", "recorded and non-empty"),
        ("recorded and empty", "recorded and non-empty"),
    ):
        assert readings[left] != readings[right], (
            f"{left!r} and {right!r} report identically as "
            f"{readings[left]!r}; the requirement forbids collapsing any "
            "two of the three"
        )


def test_a_product_predating_the_field_reports_the_question_as_open() -> None:
    """Scenario: A product predating the field reports the question as
    open.

    WHEN a product registered before this capability held hazard
    categories is read back
    THEN its hazard categories are reported as never recorded.

    A product "registered before this capability held the field" is, at
    the aggregate level, one constructed without it — which is what
    `Product.register`'s existing signature produces, since `tasks.md` 3.1
    adds the field as defaulting to absent rather than as a required
    argument. Asserted through a product that has been moved through a
    stage as well, so that a product with a history rather than a fresh
    one is the subject.
    """
    product = _registered()
    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_MOVED)
    screened_clear = _registered("WIDGET-HAZ-006")
    screened_clear.record_hazard_categories(EMPTY)

    assert _reading(product) != _reading(screened_clear), (
        "a product predating the field reads back as screened and clear, "
        "declaring every existing product screened"
    )
    assert _reading(product) is None


# ---------------------------------------------------------------------------
# Requirement: A recorded hazard-category set is what a screening
# established, not what a member ratified — the recording half
# ---------------------------------------------------------------------------


def test_a_later_screening_replaces_a_disputed_value() -> None:
    """Scenario: A later screening replaces a disputed value.

    WHEN a subsequent screening records a different set for a product
    whose recorded set was disputed
    THEN reading the product back reports the later set, the replacement
    having been performed by the screening rather than by the earlier
    decision.

    The "having been performed by the screening" half is asserted here as
    what it is at this level: the recording call is the only thing that
    changed the value, and the value did not move between the dispute and
    that call. The decision half — that a rejection alone leaves the value
    standing — is in
    `tests/unit/launch/application/test_rejected_hazard_finding_stands.py`.
    """
    product = _registered()
    product.record_hazard_categories(FLAGGED)
    disputed = _members(product)

    # Nothing happens on a rejection's behalf: the value is unchanged
    # until a later screening records over it.
    assert _members(product) == disputed

    product.record_hazard_categories(LATER_FLAGGED)

    assert _members(product) == list(LATER_FLAGGED)


# ---------------------------------------------------------------------------
# `tasks.md` 3.1's immutability clause — DERIVED from a task, not from a
# delta scenario, and marked as such
# ---------------------------------------------------------------------------


def test_a_caller_cannot_mutate_what_the_aggregate_holds() -> None:
    """DERIVED from `tasks.md` 3.1 ("Store as an immutable sequence so a
    caller cannot mutate what the aggregate holds"), not from a `####
    Scenario:`.

    Asserted from the caller's side — mutating the list that was handed in
    must not change what the product reports — rather than by pinning
    `tuple`, so an implementation using any immutable carrier passes.
    """
    product = _registered()
    supplied = ["supplements"]

    product.record_hazard_categories(supplied)
    supplied.append("lighters")

    assert _members(product) == ["supplements"], (
        "mutating the sequence handed to `record_hazard_categories` changed "
        "what the product reports, so the aggregate holds the caller's own "
        "mutable object"
    )
