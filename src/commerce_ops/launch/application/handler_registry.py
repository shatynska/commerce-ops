"""The names the deployed code answers to when a step is automated.

A step names a handler; the code registers handlers under names;
activating a step whose handler nothing registers is refused. That is the
`registrations.py` idiom this project already uses for scheduled work,
kept rather than a second one invented — and it is why activation must be
an explicit act rather than something a deploy causes: whoever registers
a handler is not necessarily whoever decides a step is ready to hold a
gate.

**One handler is registered, and no step names it.** The runtime that
invokes a handler and records what it returns shipped with
`introduce-automation-runtime`, and `listing.subcategory_advisor`
registers itself into this registry. What is absent is a step pointing at
it: the seeded set is 352 `human` drafts (`seed-the-reference-step-set`),
so `report_unregistered_handlers` has nothing to report on and the
automation pass walks every launch resolving nothing. Reaching a first
invocation is an authoring act -- a step made `automated` and `active`,
carrying a brief and this handler's name -- never a deploy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from commerce_ops.launch.application.handler_contract import StepHandler

__all__ = ["HANDLERS", "StepHandlerRegistry", "register_step_handler"]


class StepHandlerRegistry:
    """Handler names this deployment answers for.

    Reads as a container — `name in registry`, `iter(registry)`,
    `registry.names()` — because that is all any caller needs of it: the
    authoring write asks whether a name is registered, and the startup
    report asks the same question of every `active` step.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, StepHandler] = {}

    def register(self, name: str, handler: StepHandler) -> None:
        """Register `handler` under `name`.

        A conflicting re-registration raises rather than silently
        overwriting — the same rule `recurring_work` applies to a
        schedule, and for the same reason: two things answering to one
        name is a fault nobody would otherwise see.
        """
        existing = self._handlers.get(name)
        if existing is not None and existing is not handler:
            raise ValueError(
                f"step handler '{name}' is already registered by "
                f"{existing!r}; two handlers answering to one name is a "
                f"fault, not an override"
            )
        self._handlers[name] = handler

    def resolve(self, name: str) -> StepHandler | None:
        return self._handlers.get(name)

    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def __iter__(self) -> Iterator[str]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)


HANDLERS = StepHandlerRegistry()
"""The one registry, as `registrations.py` keeps one job list: a root
that saw a different set would judge a different deployment."""


def register_step_handler(
    name: str,
) -> Callable[[StepHandler], StepHandler]:
    """Decorator form, so a handler is registered where it is defined."""

    def decorate(handler: StepHandler) -> StepHandler:
        HANDLERS.register(name, handler)
        return handler

    return decorate
