"""The lifecycle-stage vocabulary: which stages a product can be in.

Implements `shared-vocabulary`'s stage requirements (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/shared-vocabulary/spec.md`).
A sum type — `Development | Launching(phase) | SteadyState(posture) |
Retired` — plus the is-temporary predicate, which is a property of a stage
value. Which *transitions* between stages are legal is deliberately not
expressed here: transition rules belong to the catalog context (design.md
Decision 4), and the moment this module grew them it would hold behavior
two modules argue about.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_MIN_PHASE = 1
_MAX_PHASE = 4


class Posture(Enum):
    """A steady-state product's operating posture."""

    SCALE = "scale"
    OPTIMIZE = "optimize"
    HOLD = "hold"
    RECOVER = "recover"
    INVENTORY_OVERRIDE = "inventory-override"


@dataclass(frozen=True, slots=True)
class Development:
    @property
    def is_temporary(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Launching:
    """A launching product, in phase 1–4 of its launch."""

    phase: int

    def __post_init__(self) -> None:
        if not _MIN_PHASE <= self.phase <= _MAX_PHASE:
            raise ValueError(
                f"launch phase must be between {_MIN_PHASE} and {_MAX_PHASE}: "
                f"{self.phase}"
            )

    @property
    def is_temporary(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class SteadyState:
    posture: Posture

    def __post_init__(self) -> None:
        if not isinstance(self.posture, Posture):
            raise TypeError(f"not a recognised posture: {self.posture!r}")

    @property
    def is_temporary(self) -> bool:
        return self.posture is Posture.INVENTORY_OVERRIDE


@dataclass(frozen=True, slots=True)
class Retired:
    @property
    def is_temporary(self) -> bool:
        return False


LifecycleStage = Development | Launching | SteadyState | Retired
