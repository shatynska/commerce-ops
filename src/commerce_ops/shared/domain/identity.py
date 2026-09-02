"""Shared identity value objects: `ProductId`, `Sku`, `Asin`, `MarketplaceId`, `MetricId`.

Implements `shared-vocabulary`'s identity requirements (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/shared-vocabulary/spec.md`).
Vocabulary only: construction-time validation, value equality, immutability
— no transition rules or other behavior. Lives in `shared.domain` so every
module speaks the same validated values instead of raw strings.

Each of these renders as its own value (`__str__`), per `shared-vocabulary`'s
requirement that a single-valued vocabulary object's textual form *is* its
value. That is a guard, not a convenience: `fix-launch-thread-mentions`
records the same mistake made four times in three modules — an identifier
composed into a Slack message, a thread anchor, a prompt and a control
payload as `ProductId(value='…')`, silently each time, and permanently
wherever the text was written once and never rewritten. A rule obeyed only
by remembering it was broken four times; a spelling that is correct by
default cannot be.

`__repr__` is deliberately left as the dataclass default. It is the
diagnostic form — what a debugger, a traceback and a `%r` log line want —
and the requirement keeps the two distinct rather than collapsing them.
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

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Sku:
    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "SKU")

    def __str__(self) -> str:
        return self.value


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

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MarketplaceId:
    value: str

    def __post_init__(self) -> None:
        _require_well_formed(self.value, "marketplace identifier")

    def __str__(self) -> str:
        return self.value


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

    def __str__(self) -> str:
        return self.value
