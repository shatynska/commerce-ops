"""The `Product` aggregate: identity, name, and the lifecycle-stage machine.

Implements `product-catalog`'s stage requirements (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`).
Pure domain code — no I/O, no framework. The stage vocabulary comes from
`shared.domain`; the legal-transition table lives here, because transition
rules are catalog behavior, not shared vocabulary (design.md Decision 4).

Every stage change is human-confirmed: the aggregate refuses a change
without a named confirmer, and it never chooses a posture or a stage on its
own. `Retired` is reachable from any stage and terminal (design.md
Decision 5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    LifecycleStage,
    Retired,
    SteadyState,
)


class StageTransitionError(Exception):
    """A stage change was rejected: the transition is not in the legal
    table, targets the product's current stage, or leaves `Retired`."""


@dataclass(frozen=True, slots=True)
class StageChanged:
    """What a successful stage change yields: the five things the spec
    says the notification carries. A returned domain object — no dispatch
    infrastructure exists yet (design.md, Non-goals)."""

    product_id: ProductId
    previous_stage: LifecycleStage
    new_stage: LifecycleStage
    confirmed_by: str
    occurred_at: datetime


def _is_legal_transition(current: LifecycleStage, target: LifecycleStage) -> bool:
    if isinstance(target, Retired):
        return True
    match current:
        case Development():
            return target == Launching(phase=1)
        case Launching(phase=phase):
            if isinstance(target, Launching):
                return target.phase == phase + 1
            return isinstance(target, SteadyState)
        case SteadyState():
            # Same-posture targets are rejected before this table is
            # consulted, so any SteadyState target here is a re-posture.
            return isinstance(target, SteadyState)
        case _:
            return False


class Product:
    """Aggregate root. Registration is the only creation path for a new
    product; the repository reconstitutes persisted ones via `__init__`."""

    def __init__(
        self,
        *,
        id: ProductId,
        sku: Sku,
        marketplace_id: MarketplaceId,
        name: str,
        asin: Asin | None,
        stage: LifecycleStage,
        stage_entered_at: datetime,
        stage_confirmed_by: str | None,
        sub_category: str | None = None,
    ) -> None:
        self.id = id
        self.sku = sku
        self.marketplace_id = marketplace_id
        self.name = name
        self.asin = asin
        self.stage = stage
        self.stage_entered_at = stage_entered_at
        self.stage_confirmed_by = stage_confirmed_by
        self.sub_category = sub_category

    @classmethod
    def register(
        cls,
        *,
        sku: Sku,
        marketplace_id: MarketplaceId,
        name: str,
        registered_at: datetime,
        asin: Asin | None = None,
    ) -> Product:
        """A new product starts in `Development`, entered at registration
        time, with no confirmer — `Development` is stamped by definition,
        not by a human decision."""
        return cls(
            id=ProductId(str(uuid.uuid4())),
            sku=sku,
            marketplace_id=marketplace_id,
            name=name,
            asin=asin,
            stage=Development(),
            stage_entered_at=registered_at,
            stage_confirmed_by=None,
        )

    def record_asin(self, asin: Asin) -> None:
        self.asin = asin

    def record_sub_category(self, sub_category: str) -> None:
        """A standalone fact, not part of the stage machine: overwritable,
        no confirmer tracked, recordable in any stage — mirrors
        `record_asin` exactly."""
        self.sub_category = sub_category

    def change_stage(
        self,
        new_stage: LifecycleStage,
        *,
        confirmed_by: str,
        at: datetime,
    ) -> StageChanged:
        if not confirmed_by:
            raise StageTransitionError(
                "a stage change requires a named human confirmer"
            )
        if isinstance(self.stage, Retired):
            raise StageTransitionError("a retired product cannot change stage")
        if new_stage == self.stage:
            raise StageTransitionError(
                "a stage change must target a different stage: a no-op change "
                "would spuriously reset the stage-entry time"
            )
        if not _is_legal_transition(self.stage, new_stage):
            raise StageTransitionError(
                f"illegal stage transition: {self.stage!r} -> {new_stage!r}"
            )

        previous = self.stage
        self.stage = new_stage
        self.stage_entered_at = at
        self.stage_confirmed_by = confirmed_by
        return StageChanged(
            product_id=self.id,
            previous_stage=previous,
            new_stage=new_stage,
            confirmed_by=confirmed_by,
            occurred_at=at,
        )
