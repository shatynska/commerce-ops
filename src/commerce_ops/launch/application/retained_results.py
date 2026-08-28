"""Reading what automated steps produced for a product.

`launch-step-automation`'s retained results, read as a **record** rather
than as a decision awaiting one. Every other read the result store offers
serves the decision loop — the pending result for a step, a result by its
identifier, the undelivered ones, the most recent rejection — and none of
them answers "what has been produced for this product". Without this one,
"settled rows are kept, never deleted" buys storage and nothing else.

Two properties this module is responsible for, and the repository is not:

- **The caller's scope.** A product the scope does not permit answers
  exactly as a product with nothing retained does, so a read can never
  confirm the existence of a product or a result the caller may not see.
  The same shape `read_launch` and `read_launches` already use.
- **The exposed shape.** Callers receive `RetainedResult`, not the ORM
  row. A driving adapter reading `AutomatedStepResult` attributes would
  reach through this layer into `launch.infrastructure.driven`, which is
  what the module's public surface exists to prevent.

The decider is carried as recorded and is never re-resolved against the
roster. `decided_by` holds the name written at the moment of the decision,
so rendering it as stored is both the store's shape and the requirement: a
record of past decisions that silently re-renders itself as its subjects
change is not a record. A voided row carries no decider at all — voiding
refuses a decision rather than recording one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId

__all__ = ["RetainedResult", "RetainedResults", "read_retained_results"]


@dataclass(frozen=True, slots=True)
class RetainedResult:
    """One result retained for a decision, as a consumer reads it.

    Spelled as the row is spelled. The fields are the whole of what was
    retained: what produced it, what it proposed, what it said, when, and
    what became of it.
    """

    step_id: str
    handler: str
    proposed_outcome: str
    result_text: str
    produced_at: datetime
    state: str
    decided_by: str | None
    decided_at: datetime | None

    @property
    def decided(self) -> bool:
        """Whether a person decided this result.

        A voided row is settled without a decider, so "has a state other
        than pending" and "somebody decided it" are different questions.
        """
        return self.decided_by is not None


class RetainedResults(Protocol):
    """What this use case needs of the result store: one read."""

    async def for_product(self, product_id: ProductId) -> Any: ...


async def read_retained_results(
    results: RetainedResults,
    *,
    product_id: ProductId,
    scope: AccessScope,
) -> tuple[RetainedResult, ...]:
    """Every result retained for the product, newest first.

    Answers emptily — never raises — for a product the scope does not
    permit, and for one with nothing retained. The two are deliberately
    indistinguishable.
    """
    if not scope.permits(product_id):
        return ()
    rows = await results.for_product(product_id)
    return tuple(_exposed(row) for row in rows)


def _exposed(row: Any) -> RetainedResult:
    return RetainedResult(
        step_id=row.step_id,
        handler=row.handler,
        proposed_outcome=row.proposed_outcome,
        result_text=row.result_text,
        produced_at=row.produced_at,
        state=row.state,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
    )
