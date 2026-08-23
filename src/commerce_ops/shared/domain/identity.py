"""Shared identity value objects: `ProductId`, `Sku`, `Asin`, `MarketplaceId`, `MetricId`.

Implements `shared-vocabulary`'s identity requirements (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/shared-vocabulary/spec.md`).
Vocabulary only: construction-time validation, value equality, immutability
— no transition rules or other behavior. Lives in `shared.domain` so every
module speaks the same validated values instead of raw strings.
"""

from __future__ import annotations

from dataclasses import dataclass

_ASIN_LENGTH = 10


def _require_well_formed(value: str, kind: str) -> None:
    if not value:
        raise ValueError(f"{kind} must not be empty")
    if value != value.strip():
        raise ValueError(
            f"{kind} must not carry leading or trailing whitespace: {value!r}"
        )


@dataclass(frozen=True, slots=True)
class ProductId:
    """A product's opaque identifier: generated, never parsed for meaning."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("product identifier must not be empty")


@dataclass(frozen=True, slots=True)
class Sku:
    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "SKU")


@dataclass(frozen=True, slots=True)
class Asin:
    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "ASIN")
        if len(self.value) != _ASIN_LENGTH or not self.value.isalnum():
            raise ValueError(
                f"ASIN must be exactly {_ASIN_LENGTH} alphanumeric characters: "
                f"{self.value!r}"
            )


@dataclass(frozen=True, slots=True)
class MarketplaceId:
    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "marketplace identifier")


@dataclass(frozen=True, slots=True)
class MetricId:
    """A metric's opaque reference.

    Until a metric registry exists (domain-map slice 7), nothing validates
    that the metric it names is defined: a reference to be resolved later,
    not a checked foreign key.
    """

    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "metric identifier")
