"""Tests for the `Product` aggregate's lifecycle-stage machine
(`product-catalog`).

Derived strictly from the ADDED requirements in
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`:

- Requirement: *A new product starts in Development*
- Requirement: *Stage changes follow the legal-transition table and are
  human-confirmed*
- Requirement: *A product reports when its current stage was entered*

These are the pure-domain scenarios: every outcome they state — which
stage the product reports, what a rejection leaves unchanged, what the
notification object carries — is observable on the aggregate alone, with
no I/O, which is the level `ai-toolkit:testing`'s level rule assigns
(tasks.md 2.3 places them here too). The registration/persistence and
read-back scenarios of the same capability need a real store to observe
and live in `tests/integration/catalog/`.

## The interface under test does not exist yet, and its shape is INVENTED

`src/commerce_ops/catalog/` does not exist (this change creates it), so
every test here is expected to fail on an absent target
(`ModuleNotFoundError`). No artifact fixes the aggregate's API. This file
assumes, and the manifest records as unresolved project questions:

- `commerce_ops.catalog.domain.product` exporting `Product`,
  `StageChanged`, and `StageTransitionError` (the single rejection signal
  for the whole rejected-transition family, following this project's
  one-exception-per-family precedent recorded in
  `tests/integration/products/test_product_repository.py`).
- `Product.register(sku=..., marketplace_id=..., name=...,
  registered_at=...)` as the construction path (tasks.md 3.1's "register
  product" use case delegating to it), returning a product exposing
  `.id`, `.stage`, `.stage_entered_at`, `.stage_confirmed_by`.
- `product.change_stage(new_stage, confirmed_by=..., at=...)`, returning
  the `StageChanged` object on success. Time is passed in explicitly so
  the "time of the change" assertions can be exact; if the real aggregate
  stamps its own clock, relaxing those to a before/after window is a
  fixture correction.
- `StageChanged` exposing `.product_id`, `.previous_stage`, `.new_stage`,
  `.confirmed_by`, `.occurred_at` — the five things the spec says it
  carries; only the attribute spellings are invented.

Correcting any of those names/shapes is a fixture correction (failure
state 3 in `ai-toolkit:testing`); what must survive unweakened is what
each test asserts: which transitions apply, which are rejected, that a
rejection leaves stage and entry time untouched, and what a successful
change records and yields.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from commerce_ops.catalog.domain.product import (
    Product,
    StageChanged,
    StageTransitionError,
)
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    LifecycleStage,
    Posture,
    Retired,
    SteadyState,
)

# DERIVED fixed times: the spec fixes no clock; distinct, ordered,
# timezone-aware instants make "entry time equals the change time" and
# "entry time unchanged" exact rather than window-based.
T_REGISTERED = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_FIRST_CHANGE = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
T_SECOND_CHANGE = datetime(2026, 8, 25, 16, 45, tzinfo=UTC)

CONFIRMER = "Helen"


def _registered() -> Product:
    """A freshly registered product, in `Development` by the spec."""
    return Product.register(
        sku=Sku("WIDGET-001"),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=T_REGISTERED,
    )


def _launching(phase: int = 1) -> Product:
    """A product walked to `Launching(phase)` along legal transitions."""
    product = _registered()
    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE)
    for next_phase in range(2, phase + 1):
        product.change_stage(
            Launching(phase=next_phase), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE
        )
    return product


def _steady(posture: Posture = Posture.OPTIMIZE) -> Product:
    """A product walked to `SteadyState(posture)` along legal transitions."""
    product = _launching(1)
    product.change_stage(
        SteadyState(posture=posture), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE
    )
    return product


def _retired() -> Product:
    product = _registered()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE)
    return product


# ---------------------------------------------------------------------------
# Requirement: A new product starts in Development
# ---------------------------------------------------------------------------


def test_registration_stamps_development() -> None:
    """Scenario: Registration stamps Development.

    WHEN a product is registered
    THEN its lifecycle stage is reported as `Development`.
    """
    product = _registered()

    # SPECIFIED: the stage is Development.
    assert product.stage == Development()


def test_registration_provenance_is_the_registration_time_and_no_confirmer() -> None:
    """Scenario: Registration provenance.

    WHEN a freshly registered product's stage is read
    THEN its stage-entry time equals the registration time
    AND no stage-change confirmer is reported.
    """
    product = _registered()

    # SPECIFIED: entry time equals the registration time.
    assert product.stage_entered_at == T_REGISTERED
    # SPECIFIED: no confirmer — Development is stamped by definition.
    assert product.stage_confirmed_by is None


# ---------------------------------------------------------------------------
# Requirement: Stage changes follow the legal-transition table and are
# human-confirmed
# ---------------------------------------------------------------------------


def test_a_legal_transition_is_applied_and_attributed() -> None:
    """Scenario: A legal transition is applied and attributed.

    WHEN a product in `Development` is moved to `Launching` phase 1 with a
    confirming person named
    THEN the product's stage is reported as `Launching` phase 1
    AND the change records the confirmer and the time of the change.
    """
    product = _registered()

    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE)

    # SPECIFIED: the stage is Launching phase 1.
    assert product.stage == Launching(phase=1)
    # SPECIFIED: the change records the confirmer and the time.
    assert product.stage_confirmed_by == CONFIRMER
    assert product.stage_entered_at == T_FIRST_CHANGE


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_launching_advances_one_phase_at_a_time(phase: int) -> None:
    """SPECIFIED by the transition table's "`Launching` phase n →
    `Launching` phase n+1"; the named scenarios cover only the entry into
    phase 1 and a rejected skip, not the legal advances between them.
    """
    product = _launching(phase)

    product.change_stage(
        Launching(phase=phase + 1), confirmed_by=CONFIRMER, at=T_SECOND_CHANGE
    )

    assert product.stage == Launching(phase=phase + 1)


def test_a_skipped_phase_is_rejected() -> None:
    """Scenario: A phase is skipped.

    WHEN a product in `Launching` phase 1 is moved to `Launching` phase 3
    THEN the change is rejected and the stored stage is unchanged.
    """
    product = _launching(1)

    with pytest.raises(StageTransitionError):
        product.change_stage(
            Launching(phase=3), confirmed_by=CONFIRMER, at=T_SECOND_CHANGE
        )

    # SPECIFIED: the stored stage is unchanged.
    assert product.stage == Launching(phase=1)


def test_development_straight_to_steady_state_is_rejected() -> None:
    """Scenario: An illegal transition is rejected.

    WHEN a product in `Development` is moved directly to `SteadyState`
    THEN the change is rejected and the stored stage is unchanged.
    """
    product = _registered()

    with pytest.raises(StageTransitionError):
        product.change_stage(
            SteadyState(posture=Posture.SCALE),
            confirmed_by=CONFIRMER,
            at=T_FIRST_CHANGE,
        )

    # SPECIFIED: the stored stage is unchanged.
    assert product.stage == Development()
    # DERIVED: a rejection also leaves provenance untouched — the change
    # "leaves the stored stage unchanged", and entry time / confirmer are
    # the stage's recorded provenance.
    assert product.stage_entered_at == T_REGISTERED
    assert product.stage_confirmed_by is None


def test_graduation_without_a_posture_is_rejected() -> None:
    """Scenario: Graduation requires an explicit posture.

    WHEN a product in `Launching` is graduated to `SteadyState` without a
    posture supplied
    THEN the change is rejected — the system never chooses a posture
    itself.

    Under the sum-type shape design.md Decision 4 fixes, a posture-less
    `SteadyState` is only expressible as a construction attempt, so the
    rejection is observed there; if the real change-stage API instead
    takes a stage name plus an optional posture, redirecting this to that
    call is a fixture correction — what must survive is that the attempt
    fails and the product's stage is untouched, with no default posture
    ever chosen.
    """
    product = _launching(2)

    with pytest.raises((TypeError, ValueError)):
        SteadyState()  # type: ignore[call-arg]

    # SPECIFIED: no change occurred.
    assert product.stage == Launching(phase=2)


@pytest.mark.parametrize("phase", [1, 4])
def test_graduation_from_any_phase_with_an_explicit_posture_is_legal(
    phase: int,
) -> None:
    """SPECIFIED by the transition table's "`Launching` (any phase) →
    `SteadyState` with an explicitly supplied posture (graduation)" — no
    named scenario exercises the legal graduation itself. Phases 1 and 4
    cover both bounds of "any phase".
    """
    product = _launching(phase)

    product.change_stage(
        SteadyState(posture=Posture.SCALE),
        confirmed_by=CONFIRMER,
        at=T_SECOND_CHANGE,
    )

    assert product.stage == SteadyState(posture=Posture.SCALE)


def test_reposturing_including_inventory_override_round_trip_is_legal() -> None:
    """SPECIFIED by the transition table's "`SteadyState` posture p →
    `SteadyState` posture p′ (re-posturing, including entering and
    leaving `InventoryOverride`)" — no named scenario exercises the legal
    re-posture.
    """
    product = _steady(Posture.OPTIMIZE)

    product.change_stage(
        SteadyState(posture=Posture.INVENTORY_OVERRIDE),
        confirmed_by=CONFIRMER,
        at=T_SECOND_CHANGE,
    )
    assert product.stage == SteadyState(posture=Posture.INVENTORY_OVERRIDE)

    product.change_stage(
        SteadyState(posture=Posture.RECOVER),
        confirmed_by=CONFIRMER,
        at=T_SECOND_CHANGE,
    )
    assert product.stage == SteadyState(posture=Posture.RECOVER)


def test_a_same_stage_change_is_rejected_and_entry_time_kept() -> None:
    """Scenario: A same-stage change is rejected.

    WHEN a product in `SteadyState` with posture `Optimize` is moved to
    `SteadyState` with posture `Optimize`
    THEN the change is rejected and the stage-entry time is unchanged.
    """
    product = _steady(Posture.OPTIMIZE)
    entered_at_before = product.stage_entered_at

    with pytest.raises(StageTransitionError):
        product.change_stage(
            SteadyState(posture=Posture.OPTIMIZE),
            confirmed_by=CONFIRMER,
            at=T_SECOND_CHANGE,
        )

    # SPECIFIED: the stage-entry time is unchanged — the requirement's
    # stated reason for rejecting no-op changes.
    assert product.stage_entered_at == entered_at_before
    assert product.stage == SteadyState(posture=Posture.OPTIMIZE)


@pytest.mark.parametrize(
    "product_factory",
    [
        pytest.param(_registered, id="development-to-development"),
        pytest.param(lambda: _launching(2), id="launching-2-to-launching-2"),
    ],
)
def test_other_same_stage_targets_are_rejected_too(product_factory: object) -> None:
    """SPECIFIED by the requirement statement ("a transition whose target
    equals the product's current stage ... SHALL be rejected") — the
    named scenario covers only the same-posture case.
    """
    product = product_factory()  # type: ignore[operator]
    target = product.stage
    entered_at_before = product.stage_entered_at

    with pytest.raises(StageTransitionError):
        product.change_stage(target, confirmed_by=CONFIRMER, at=T_SECOND_CHANGE)

    assert product.stage_entered_at == entered_at_before


def test_a_successful_change_yields_a_stage_changed_notification() -> None:
    """Scenario: A successful change yields a stage-changed notification.

    WHEN a legal, confirmed stage change is applied to a product
    THEN a stage-changed object is produced carrying the product
    identifier, the prior stage, the new stage, the confirmer, and the
    time of the change.
    """
    product = _registered()

    event = product.change_stage(
        Launching(phase=1), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE
    )

    # SPECIFIED: the five things the notification carries. Attribute
    # spellings are the invented part (module docstring); the carried
    # values are what trace to the spec.
    assert isinstance(event, StageChanged)
    assert event.product_id == product.id
    assert event.previous_stage == Development()
    assert event.new_stage == Launching(phase=1)
    assert event.confirmed_by == CONFIRMER
    assert event.occurred_at == T_FIRST_CHANGE


@pytest.mark.parametrize(
    "product_factory",
    [
        pytest.param(_registered, id="from-development"),
        pytest.param(lambda: _launching(2), id="from-launching-2"),
        pytest.param(lambda: _steady(Posture.HOLD), id="from-steady-state-hold"),
    ],
)
def test_any_stage_can_be_retired(product_factory: object) -> None:
    """SPECIFIED by the transition table's "any stage → `Retired`" (and
    design.md Decision 5) — no named scenario exercises the legal
    retirement itself, only that `Retired` is then terminal.
    """
    product = product_factory()  # type: ignore[operator]

    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_SECOND_CHANGE)

    assert product.stage == Retired()


@pytest.mark.parametrize(
    "target",
    [
        pytest.param(Launching(phase=1), id="to-launching-1"),
        pytest.param(SteadyState(posture=Posture.SCALE), id="to-steady-state"),
        pytest.param(Development(), id="to-development"),
    ],
)
def test_a_retired_product_cannot_change_stage(target: LifecycleStage) -> None:
    """Scenario: A retired product cannot change stage.

    WHEN any stage change targets a product in `Retired`
    THEN the change is rejected.
    """
    product = _retired()

    with pytest.raises(StageTransitionError):
        product.change_stage(target, confirmed_by=CONFIRMER, at=T_SECOND_CHANGE)

    # DERIVED: rejected means the stage is still Retired.
    assert product.stage == Retired()


@pytest.mark.parametrize(
    "confirmer",
    [pytest.param(None, id="none"), pytest.param("", id="empty-string")],
)
def test_an_unconfirmed_change_is_rejected(confirmer: str | None) -> None:
    """Scenario: An unconfirmed change is rejected.

    WHEN a stage change is requested without a confirming person
    THEN the change is rejected and the stored stage is unchanged.

    DERIVED mechanism: "without a confirming person" is exercised as a
    `None` and an empty-string confirmer; the accepted rejection signals
    include `TypeError`/`ValueError` alongside `StageTransitionError`
    because an implementation may enforce the confirmer at the signature
    or validation layer rather than the transition table — any raise that
    leaves the stage unchanged satisfies "rejected".
    """
    product = _registered()

    with pytest.raises((StageTransitionError, ValueError, TypeError)):
        product.change_stage(
            Launching(phase=1),
            confirmed_by=confirmer,  # type: ignore[arg-type]
            at=T_FIRST_CHANGE,
        )

    # SPECIFIED: the stored stage is unchanged.
    assert product.stage == Development()
    assert product.stage_confirmed_by is None


# ---------------------------------------------------------------------------
# Requirement: A product reports when its current stage was entered
# ---------------------------------------------------------------------------


def test_stage_entry_time_is_reported_after_a_change() -> None:
    """Scenario: Stage entry time is reported.

    WHEN a product's stage is read after a stage change
    THEN the time the current stage was entered is reported with it.
    """
    product = _registered()

    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_FIRST_CHANGE)
    # SPECIFIED: entry time is the time of the change that entered it.
    assert product.stage_entered_at == T_FIRST_CHANGE

    product.change_stage(Launching(phase=2), confirmed_by=CONFIRMER, at=T_SECOND_CHANGE)
    # DERIVED: it tracks the *current* stage — a second change moves it.
    assert product.stage_entered_at == T_SECOND_CHANGE
