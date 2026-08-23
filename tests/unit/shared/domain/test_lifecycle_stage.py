"""Tests for the shared lifecycle-stage vocabulary (`shared-vocabulary`).

Derived strictly from the ADDED requirements in
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/shared-vocabulary/spec.md`:

- Requirement: *Lifecycle-stage vocabulary names the stages a product can
  be in*
- Requirement: *The vocabulary identifies which stages are temporary*
- Requirement: *Value objects are immutable and compare by value* — the
  stage-value half ("every vocabulary value object"); the identity-VO
  half lives in `test_identity_value_objects.py`.

See `test-manifest.md` at the change root for the full accounting.

## The interface under test does not exist yet, and its shape is INVENTED

`shared/domain` has no stage vocabulary yet (tasks.md 1.2 introduces it),
so every test here is expected to fail on an absent target
(`ModuleNotFoundError`) — per `ai-toolkit:testing`, that establishes only
absence.

design.md Decision 4 fixes the *shape* — a sum type
`Development | Launching(phase) | SteadyState(posture) | Retired` plus an
is-temporary predicate that is "a property of a value" — but no artifact
fixes module path or spelling. This file assumes, and the manifest records
as unresolved project questions:

- `commerce_ops.shared.domain.lifecycle_stage` as the module, exporting
  `Development`, `Launching`, `SteadyState`, `Retired`, and a `Posture`
  enum with members `SCALE`, `OPTIMIZE`, `HOLD`, `RECOVER`,
  `INVENTORY_OVERRIDE`.
- `Launching(phase=n)` and `SteadyState(posture=Posture.X)` as keyword
  constructions, exposing `.phase` / `.posture`; `Development()` and
  `Retired()` as no-argument constructions comparing by value.
- The is-temporary predicate as an `.is_temporary` property on every
  stage value.
- Out-of-range phase construction raises `ValueError`.

If the real vocabulary differs — an ADT library, string-literal postures,
a free function `is_temporary(stage)` instead of a property — correcting
the construction calls or the predicate access is a fixture correction;
what must survive unweakened is what each test asserts: which stage
values exist, that phase 0/5 are rejected, and which values report
temporary.
"""

from __future__ import annotations

import pytest

from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    Posture,
    Retired,
    SteadyState,
)

# ---------------------------------------------------------------------------
# Requirement: Lifecycle-stage vocabulary names the stages a product can
# be in
# ---------------------------------------------------------------------------


def test_a_launching_stage_carries_its_phase() -> None:
    """Scenario: A launching stage carries its phase.

    WHEN a `Launching` stage value is constructed with phase 2
    THEN it reports phase 2.
    """
    stage = Launching(phase=2)

    # SPECIFIED: it reports phase 2.
    assert stage.phase == 2


@pytest.mark.parametrize("phase", [0, 5])
def test_an_out_of_range_launch_phase_is_rejected(phase: int) -> None:
    """Scenario: An out-of-range launch phase is rejected.

    WHEN a `Launching` stage value is constructed with phase 0 or phase 5
    THEN construction fails.
    """
    # SPECIFIED: construction fails. DERIVED mechanism: ValueError (see
    # module docstring).
    with pytest.raises(ValueError):
        Launching(phase=phase)


@pytest.mark.parametrize("phase", [1, 2, 3, 4])
def test_every_in_range_launch_phase_is_accepted(phase: int) -> None:
    """SPECIFIED by the requirement statement ("carrying a phase from 1 to
    4"), not a named scenario: the named pair covers phase 2 accepted and
    0/5 rejected; the boundary phases 1 and 4 are asserted here so an
    off-by-one range check cannot pass the named scenarios alone.
    """
    assert Launching(phase=phase).phase == phase


def test_a_steady_state_stage_carries_its_posture() -> None:
    """Scenario: A steady-state stage carries its posture.

    WHEN a `SteadyState` stage value is constructed with the posture
    `Hold`
    THEN it reports the posture `Hold`.
    """
    stage = SteadyState(posture=Posture.HOLD)

    # SPECIFIED: it reports the posture Hold.
    assert stage.posture is Posture.HOLD


def test_the_posture_set_is_exactly_the_five_the_spec_names() -> None:
    """SPECIFIED by the requirement statement ("a posture that is one of
    `Scale`, `Optimize`, `Hold`, `Recover`, or `InventoryOverride`"), not
    a named scenario. Asserted on the enum's membership so a sixth
    invented posture, or a missing one, is caught here rather than only
    at whatever call site first uses it.
    """
    assert {member.name for member in Posture} == {
        "SCALE",
        "OPTIMIZE",
        "HOLD",
        "RECOVER",
        "INVENTORY_OVERRIDE",
    }


# ---------------------------------------------------------------------------
# Requirement: The vocabulary identifies which stages are temporary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", [1, 2, 3, 4])
def test_launching_is_temporary_at_every_phase(phase: int) -> None:
    """Scenario: Launching is temporary.

    WHEN any `Launching` stage value is asked whether it is temporary
    THEN it reports that it is. Parametrized over all four phases per the
    requirement statement's "`Launching` (every phase)".
    """
    assert Launching(phase=phase).is_temporary


def test_inventory_override_is_temporary() -> None:
    """Scenario: Inventory override is temporary.

    WHEN a `SteadyState` stage value with posture `InventoryOverride` is
    asked whether it is temporary
    THEN it reports that it is.
    """
    assert SteadyState(posture=Posture.INVENTORY_OVERRIDE).is_temporary


@pytest.mark.parametrize(
    "posture",
    [Posture.SCALE, Posture.OPTIMIZE, Posture.HOLD, Posture.RECOVER],
    ids=["scale", "optimize", "hold", "recover"],
)
def test_ordinary_steady_state_is_not_temporary(posture: Posture) -> None:
    """Scenario: Ordinary steady state is not temporary.

    WHEN a `SteadyState` stage value with posture `Scale`, `Optimize`,
    `Hold`, or `Recover` is asked whether it is temporary
    THEN it reports that it is not.
    """
    assert not SteadyState(posture=posture).is_temporary


@pytest.mark.parametrize(
    "stage_factory",
    [
        pytest.param(Development, id="development"),
        pytest.param(Retired, id="retired"),
    ],
)
def test_development_and_retired_are_not_temporary(stage_factory: object) -> None:
    """SPECIFIED by the requirement statement ("`Development`, `Retired`
    ... SHALL NOT"), which the three named scenarios do not reach.
    """
    assert not stage_factory().is_temporary  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Requirement: Value objects are immutable and compare by value
# (stage-value half — "every vocabulary value object")
# ---------------------------------------------------------------------------


def test_stage_values_compare_by_value_and_hash_equal() -> None:
    """SPECIFIED by the requirement statement applied to stage values;
    the named equality scenario itself uses a SKU and is covered in
    `test_identity_value_objects.py`. Asserted here because `monitoring`
    keying thresholds by stage (design.md Decision 4's stated consumer)
    depends on exactly this dictionary-key behavior.
    """
    assert Launching(phase=2) == Launching(phase=2)
    assert hash(Launching(phase=2)) == hash(Launching(phase=2))
    assert Launching(phase=2) != Launching(phase=3)
    assert Development() == Development()
    assert SteadyState(posture=Posture.HOLD) == SteadyState(posture=Posture.HOLD)
    assert SteadyState(posture=Posture.HOLD) != SteadyState(posture=Posture.SCALE)
    # Usable as set members across constructions.
    assert len({Development(), Development(), Retired()}) == 2


def test_mutation_of_a_stage_value_fails() -> None:
    """Scenario: Mutation is not possible — applied to a stage value, per
    the requirement statement's "every vocabulary value object". DERIVED
    mechanism: see `test_identity_value_objects.py`'s counterpart.
    """
    stage = Launching(phase=1)

    with pytest.raises((AttributeError, TypeError)):
        stage.phase = 3  # type: ignore[misc]
