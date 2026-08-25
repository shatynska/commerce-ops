"""The names the deployed code answers to when a step is automated.

A step names a handler; the code registers handlers under names;
activating a step whose handler nothing registers is refused. That is the
`registrations.py` idiom this project already uses for scheduled work,
kept rather than a second one invented — and it is why activation must be
an explicit act rather than something a deploy causes: whoever registers
a handler is not necessarily whoever decides a step is ready to hold a
gate.

**No handler is registered yet, and that is the honest state.** Running an
automated step is deliberately out of `redesign-step-fields`'s scope: this
change lets a step *declare* a handler and refuses to activate one naming
a handler the code does not register. Invoking it, and recording what it
returns, is the automation runtime and belongs to its own change. Until
then the registry is empty and the two seeded automated steps stay
`in-development`, which the readiness report says out loud.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

__all__ = ["HANDLERS", "StepHandlerRegistry", "register_step_handler"]


class StepHandlerRegistry:
    """Handler names this deployment answers for.

    Reads as a container — `name in registry`, `iter(registry)`,
    `registry.names()` — because that is all any caller needs of it: the
    authoring write asks whether a name is registered, and the startup
    report asks the same question of every `active` step.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., object]] = {}

    def register(self, name: str, handler: Callable[..., object]) -> None:
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

    def resolve(self, name: str) -> Callable[..., object] | None:
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
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Decorator form, so a handler is registered where it is defined."""

    def decorate(handler: Callable[..., object]) -> Callable[..., object]:
        HANDLERS.register(name, handler)
        return handler

    return decorate
