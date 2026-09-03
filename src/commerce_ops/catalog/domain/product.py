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
from collections.abc import Sequence
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
        hazard_categories: Sequence[str] | None = None,
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
        # `None` and `()` are different facts and the default is `None`:
        # a product nobody has screened has an open question, not an
        # answered one (`product-catalog`, *A product reports its hazard
        # categories in three states, never two*).
        self.hazard_categories = (
            None if hazard_categories is None else tuple(hazard_categories)
        )

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

    def record_hazard_categories(self, categories: Sequence[str]) -> None:
        """What a compliance screening found — replacing wholesale, never
        merging, and recordable in any stage. Shaped like
        `record_sub_category`, with one difference that carries the whole
        point of the field.

        **An empty sequence is a recording, not a way of clearing this.**
        `()` asserts that the product was screened and fell in none of the
        categories screened against; `None` asserts that nothing has
        screened it. A caller with nothing to assert records nothing at
        all rather than recording `()`, and this method has no way to put
        the field back to `None` because reverting an answered question to
        an open one is not something any screening establishes.

        Stored as a `tuple` so that a caller mutating what it passed in
        cannot reach through and change what the aggregate holds.

        **A bare string is refused rather than accepted as a sequence.**
        `str` satisfies `Sequence[str]`, so the annotation cannot catch it
        and neither can `mypy`: `record_hazard_categories("supplements")`
        would otherwise store eleven single-character categories, and the
        dossier would render "Screened; found in s, u, p, ...". The sink
        that feeds this is typed `value: Any` -- deliberately, since sinks
        write different value types -- so nothing between a handler and
        this method would notice. A handler returning a scalar `Success`
        value, which is exactly the shape the sub-category advisor uses,
        is the way in.
        """
        if isinstance(categories, str):
            raise TypeError(
                "hazard categories must be a sequence of category names, "
                f"not a single string: {categories!r} would be recorded as "
                "its individual characters"
            )
        self.hazard_categories = tuple(categories)

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
