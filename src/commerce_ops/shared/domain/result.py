"""`Success[T]` / `Failure[E]`: the finding shape every automated step
handler's `StepResolution` may carry (`launch-step-automation`'s ADDED
requirement *A handler MAY report a typed finding alongside its outcome*).

Universal down to the field names, deliberately: `value`/`comment` on
`Success`, `error`/`comment` on `Failure` — not a bespoke field per
handler. Generic code that later reads a `finding` (the automation pass,
in particular) must never need to know a specific handler's own field is
called `sub_category` or `compliance_demands`; `value`/`comment` are the
whole vocabulary, whatever domain-specific meaning `T`/`E` carry for the
handler that produced one.

Frozen dataclasses, no I/O: this lives in `shared.domain` because it is
meant for reuse across every future automated handler, not owned by
`launch` or by any one `step_handlers` module (`shared-boundary` forbids
the reverse dependency).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Failure", "Result", "Success"]


@dataclass(frozen=True, slots=True)
class Success[T]:
    """A handler's finding, where it has one to report: `value` is exactly
    what gets recorded, laconic by design; `comment` is optional
    additional information for a person or for tuning the handler."""

    value: T
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class Failure[E]:
    """Why a handler has nothing to record: `error` is why, `comment` is
    optional additional information."""

    error: E
    comment: str | None = None


type Result[T, E] = Success[T] | Failure[E]
