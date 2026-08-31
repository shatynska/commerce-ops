"""What a step handler is given, and what it may say back.

`launch-step-automation`'s "A handler receives the step, the launch and
the product, and attributes nothing". Two frozen dataclasses, no I/O: a
handler is a function of the context it is given and nothing else, which
is what lets one be exercised without a database and keeps the catalog
read in one place instead of one place per handler.

**Neither type has a field for provenance, and that is the enforcement.**
The requirement says a handler may not attribute its own work; the
contract makes the claim unsayable rather than checking for it after the
fact — a dataclass raises for an argument it does not declare, so a
handler smuggling a `Provenance` is refused at construction. The system
builds the provenance itself, with source `automated`, from what it
already knows: the handler's registered name, the moment of the run, and
the produced text.

`product` is typed `Any` for the same reason `ProductReader` already is
(`clickup_sync.py`): `.importlinter`'s `products-infrastructure-boundary`
forbids this module's neighbours from naming catalog's own types, and the
pass resolves the product through a reader injected at `worker.py`. The
handler receives whatever that reader returned.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from commerce_ops.launch.domain.launch_playbook import StepDefinition
from commerce_ops.launch.domain.launch_run import Launch, StepOutcomeValue
from commerce_ops.shared.domain.result import Result

__all__ = ["StepContext", "StepHandler", "StepResolution"]


@dataclass(frozen=True, slots=True)
class StepContext:
    """Everything a handler is given to resolve one step on one launch.

    Frozen so that a handler cannot alter what runs after it sees — the
    requirement's "a handler is a function of the context it is given"
    read as a property of the value rather than as an instruction.
    """

    step: StepDefinition
    launch: Launch
    product: Any
    as_of: datetime


@dataclass(frozen=True, slots=True)
class StepResolution:
    """What a handler produced: an outcome, and the text a person reads.

    The outcome may be any of the six `launch-playbook` outcomes. Which
    of them are *held* for a decision is not this type's business — the
    pass holds a terminal proposal and records a non-terminal one
    directly, because a non-terminal outcome is not a result anyone can
    accept.

    `result` is plain text rather than a structure because both its
    consumers want text: the Slack message a person reads, and the
    `evidence` field of the recording it becomes.

    `finding` is additive and optional: what the handler discovered that
    something outside the launch itself — a product, a later automated
    step — might need to read, independent of what `outcome` and `result`
    already mean (`launch-step-automation`'s *A handler MAY report a typed
    finding alongside its outcome*). A handler with nothing to hand
    downstream — every handler before this field existed, and most future
    ones — simply leaves it `None`.
    """

    outcome: StepOutcomeValue
    result: str
    finding: Result[Any, Any] | None = None

    def __post_init__(self) -> None:
        # Empty evidence is refused by `Provenance` itself, one layer
        # down. Refusing it here means a handler learns it produced
        # nothing at the point it produced nothing, rather than at the
        # point something tries to record it.
        if not self.result.strip():
            raise ValueError(
                "a step resolution requires produced text: it becomes the "
                "recorded evidence, which every recording requires"
            )


StepHandler = Callable[[StepContext], Awaitable[StepResolution]]
"""What the registry holds. Awaited: a handler is free to reach a model or
a service, and the one this change ships does."""
