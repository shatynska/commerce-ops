"""The advisor, registered as the step handler the runtime invokes.

Registration happens where the handler is defined, through
`register_step_handler` — the `registrations.py` idiom this project keeps
for scheduled work, and for the same reason: whoever registers a handler
is not necessarily whoever decides a step is ready to hold a gate.

**Which processes import this module is load-bearing.** Activation is
validated against the registry in the process serving the admin surface,
while the pass needs the same handler in the worker; a handler imported
into only one leaves them disagreeing, with `check_step_handlers`
reporting it registered while the admin's activation is refused as naming
an unknown handler. `registrations.py` — the one list both composition
roots import — is what keeps them in step.

The graph is built once and reused. It carries no state between
invocations, which is what makes reuse safe and is separately required of
the advisor.
"""

from __future__ import annotations

import functools

from commerce_ops.launch.application import (
    StepContext,
    StepResolution,
    register_step_handler,
)
from commerce_ops.subcategory_advisor.application.graph import (
    build_production_graph,
    propose,
)

__all__ = ["HANDLER_NAME", "advise_sub_category"]

HANDLER_NAME = "listing.subcategory_advisor"


@functools.lru_cache
def _graph() -> object:
    """Built on first use, never at import: constructing the model reads
    credentials, and importing this module must not require them."""
    return build_production_graph()


@register_step_handler(HANDLER_NAME)
async def advise_sub_category(context: StepContext) -> StepResolution:
    """Propose the sub-category node, or say it cannot support a choice.

    Reads only what the context carries — the product the pass resolved,
    never a catalog of its own. A model failure propagates, and the pass
    records nothing for a step it could not evaluate.
    """
    product = context.product
    proposal = propose(
        product_name=str(getattr(product, "name", "")),
        marketplace=str(getattr(product, "marketplace_id", "")),
        graph=_graph(),
    )
    return StepResolution(outcome=proposal.outcome, result=proposal.result)
