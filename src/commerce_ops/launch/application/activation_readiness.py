"""What blocks a step from being activated, and what a deploy broke.

Two reports, both pure queries, and both here because they answer the
same question from opposite ends: *is this step ready to hold a gate?*

`report_activation_blockers` runs over the **authored** set while it is
being authored, so the outstanding work of getting a step ready stays
visible rather than surfacing one step at a time when someone tries to
activate it. It replaces the undecided-rule-policy report, whose subject
was one field; this one covers the brief, the handler and an active
human step's assignees.

`report_unregistered_handlers` runs at startup, over the set a
deployment is about to serve. That a handler is *registered* is a
property of the deployed code, which changes without the step set
changing — so it is checked when a step is activated and never at load,
and a deployment whose registry no longer answers for an `active` step's
handler is reported here, where a deployment fault belongs, rather than
by making every playbook load fail.

Neither reaches the storage adapter: `.importlinter`'s module-layers
contract forbids this layer from importing infrastructure, so the caller
supplies the step definitions, the roster reader and the handler
registry.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from commerce_ops.launch.domain.launch_playbook import (
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

MISSING_BRIEF = "an automation brief"
MISSING_HANDLER = "a handler the deployed code registers"
MISSING_ASSIGNEE = "an assignee who is active on the roster"


@dataclass(frozen=True, slots=True)
class ActivationBlocker:
    """One step that cannot yet be made `active`, and what it lacks."""

    identifier: str
    gate: str
    discipline: Discipline
    status: StepStatus
    missing: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"step '{self.identifier}' ({self.discipline.value}, gate "
            f"'{self.gate}', status '{self.status.value}') still needs "
            f"{', '.join(self.missing)}"
        )


def report_activation_blockers(
    *,
    steps: Sequence[StepDefinition],
    roster: Any = None,
    handlers: Any = None,
) -> tuple[ActivationBlocker, ...]:
    """The steps of the authored set that cannot yet be made `active`.

    An `active` step is reported too where it has since stopped
    satisfying what activation requires: a step whose sole assignee was
    deactivated keeps loading and keeps being served (the roster is not a
    load-time rule), and this report is where that gap surfaces instead.
    """
    active_people = _active_identifiers(roster)
    registered = _registered_names(handlers)
    reported: list[ActivationBlocker] = []
    for step in steps:
        if step.status is StepStatus.RETIRED:
            # Not work anyone is getting ready; reporting it would make
            # the signal noise.
            continue
        missing = _what_is_missing(step, active_people, registered)
        if missing:
            reported.append(
                ActivationBlocker(
                    identifier=step.identifier,
                    gate=step.gate,
                    discipline=step.discipline,
                    status=step.status,
                    missing=missing,
                )
            )
    return tuple(reported)


def _what_is_missing(
    step: StepDefinition,
    active_people: frozenset[str],
    registered: frozenset[str],
) -> tuple[str, ...]:
    missing: list[str] = []
    if step.kind is StepKind.AUTOMATED:
        if step.automation_brief is None:
            missing.append(MISSING_BRIEF)
        if step.handler is None or step.handler not in registered:
            missing.append(MISSING_HANDLER)
    elif not any(identifier in active_people for identifier in step.assignees):
        missing.append(MISSING_ASSIGNEE)
    return tuple(missing)


@dataclass(frozen=True, slots=True)
class UnregisteredHandler:
    """One `active` step whose handler this deployment cannot answer for."""

    identifier: str
    handler: str

    def __str__(self) -> str:
        return (
            f"active step '{self.identifier}' names handler "
            f"'{self.handler}', which this deployment does not register"
        )


def report_unregistered_handlers(
    *,
    steps: Sequence[StepDefinition],
    handlers: Any = None,
) -> tuple[UnregisteredHandler, ...]:
    """Every `active` step whose handler the deployed registry no longer
    answers for — a deployment fault, reported at the deployment
    boundary.

    Only `active` steps are the subject: a step still in development is
    expected to name a handler nothing registers yet, and reporting it
    would make the signal noise.
    """
    registered = _registered_names(handlers)
    return tuple(
        UnregisteredHandler(identifier=step.identifier, handler=step.handler)
        for step in steps
        if step.status is StepStatus.ACTIVE
        and step.kind is StepKind.AUTOMATED
        and step.handler is not None
        and step.handler not in registered
    )


def _registered_names(handlers: Any) -> frozenset[str]:
    if handlers is None:
        return frozenset()
    names = getattr(handlers, "names", None)
    if callable(names):
        return frozenset(str(name) for name in names())
    return frozenset(str(name) for name in handlers)


def _active_identifiers(roster: Any) -> frozenset[str]:
    """Who the roster carries and counts as active, read synchronously.

    Both reports are pure queries a caller composes into a page or a
    startup check, so they are synchronous; a caller whose roster read is
    asynchronous resolves it and passes the people. A reader whose
    `list_people` happens to be a coroutine function that never suspends
    is driven to completion here — a real store's read must be awaited by
    the caller instead, and says so.
    """
    if roster is None:
        return frozenset()
    people = _people_of(roster)
    return frozenset(
        _identifier_of(person) for person in people if getattr(person, "active", True)
    )


def _people_of(roster: Any) -> tuple[Any, ...]:
    lister = getattr(roster, "list_people", None)
    source: Any = roster
    if lister is not None:
        source = lister()
    elif callable(roster):
        source = roster()
    if inspect.isawaitable(source):
        source = _resolve_now(source)
    return tuple(source)


def _resolve_now(awaitable: Any) -> Any:
    try:
        awaitable.send(None)
    except StopIteration as finished:
        return finished.value
    raise RuntimeError(
        "the roster reader suspended: these reports are synchronous, so a "
        "caller whose roster read touches I/O must await it and pass the "
        "people it answered"
    )


def _identifier_of(person: Any) -> str:
    for name in ("identifier", "id", "person_id"):
        value = getattr(person, name, None)
        if value is not None:
            return str(value)
    raise ValueError(f"a roster person exposes no identifier: {person!r}")
