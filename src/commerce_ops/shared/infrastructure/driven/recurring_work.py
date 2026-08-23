"""Driven adapter: the one declaration of what recurring work exists.

Implements the `scheduled-jobs` capability's "Each Piece Of Recurring Work
Declares Its Schedule And Tolerance In One Place"
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`).

Both consumers read this: the overdue check in the worker, and the freshness
endpoint in the HTTP process. Neither holds a copy, so neither can disagree
with the other about what is scheduled or how late is late.

Lives in `infrastructure/driven/` rather than in `application/` because
`.importlinter`'s `module-layers` forbids `shared.application` from importing
`shared.infrastructure`, and `register_scheduled` below must apply the job
runner's periodic decorator, which lives beside this module.

**The identifier is the runner's own task name**, not a second, friendlier
name mapped to it. The last-success accessor queries the run history by task
name, so a separate display identifier would be one more pair of values that
can drift -- the failure this change exists to prevent, reintroduced one
field over. See design.md, "Schedules and tolerances live in one registry".
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from commerce_ops.shared.infrastructure.driven.job_runner import app

__all__ = [
    "ConflictingRegistrationError",
    "RecurringWork",
    "register_scheduled",
    "registered_work",
]


@dataclass(frozen=True)
class RecurringWork:
    """What is scheduled, how often, and how late it may be before it is late.

    `identifier` is the job runner's task name -- see the module docstring.
    `tolerance` exceeds the longest gap between consecutive runs of
    `schedule`, which is asserted against the schedule expression itself
    rather than assumed uniform (tasks.md 1.6).
    """

    identifier: str
    schedule: str
    tolerance: datetime.timedelta


class ConflictingRegistrationError(RuntimeError):
    """Raised when one identifier is registered twice with different terms.

    Registration is idempotent per identifier: `register_all()` may run twice
    in one process (both composition roots imported in a test), and repeating
    an identical registration must be harmless. Silently overwriting it would
    not be -- a duplicate identifier declaring a different schedule or
    tolerance is a mistake, and the last import to win would decide which of
    two answers the check and the endpoint agree on (tasks.md 1.4b).
    """


_REGISTRY: dict[str, RecurringWork] = {}


def registered_work() -> Mapping[str, RecurringWork]:
    """Every piece of recurring work that has declared itself, by identifier.

    A copy: a caller iterating this must not be able to change what the other
    consumer reads.
    """
    return dict(_REGISTRY)


def _record(entry: RecurringWork) -> None:
    existing = _REGISTRY.get(entry.identifier)
    if existing is not None and existing != entry:
        raise ConflictingRegistrationError(
            f"{entry.identifier!r} is already registered as "
            f"schedule={existing.schedule!r} tolerance={existing.tolerance!r}; "
            f"refusing to replace it with schedule={entry.schedule!r} "
            f"tolerance={entry.tolerance!r}. Two pieces of recurring work "
            f"cannot share an identifier -- the run history is queried by it."
        )
    _REGISTRY[entry.identifier] = entry


def register_scheduled(
    *,
    name: str,
    schedule: str,
    tolerance: datetime.timedelta,
    **task_options: Any,
) -> Callable[[Callable[..., Any]], Any]:
    """Schedule a piece of work and declare its tolerance, in one act.

    The schedule is taken **once** and used twice from that single value: to
    apply the runner's periodic, and to write the registry entry. A job module
    that declared the cron expression to the runner and passed a copy here
    would let the two drift -- the runner firing on one value while the
    longest-gap check validated the other, so work moved to weekdays-only
    would report itself overdue every weekend (tasks.md 1.1a).
    """

    def decorate(function: Callable[..., Any]) -> Any:
        _record(RecurringWork(identifier=name, schedule=schedule, tolerance=tolerance))
        # The runner's `task`/`periodic` decorators are untyped, so applying
        # them by call rather than with `@` syntax is a call to an unknown
        # function in a typed context. Named `Any` here rather than silenced
        # with an ignore, so the untyped surface is where it actually is.
        task_decorator: Any = app.task(name=name, **task_options)
        periodic_decorator: Any = app.periodic(cron=schedule)
        return periodic_decorator(task_decorator(function))

    return decorate
