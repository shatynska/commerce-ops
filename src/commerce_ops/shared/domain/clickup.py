"""ClickUp domain value objects: no behavior, no I/O.

Lives in `shared.domain` rather than next to the driven adapter so both
`shared.application`'s `ClickUpTaskWriter` port and
`shared.infrastructure.driven.clickup_client`'s concrete adapter can
reference it without either layer importing the other -- see
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ClickUpTask:
    """A ClickUp task's identifier and URL, as returned by a create or
    update call."""

    id: str
    url: str


@dataclass(frozen=True, slots=True)
class ClickUpTaskState:
    """A ClickUp task as a *read* reports it, added by
    `add-clickup-completion-loop` for the launch completion loop.

    Distinct from `ClickUpTask`, which is what a write hands back: a read
    carries the facts the loop judges against — the status, whether that
    status is of the closed type, and the due date it currently holds.

    `closed` is taken from ClickUp's status `type` field, never from the
    status name, so the ops team can rename statuses freely.

    `name` and `description` joined with `move-playbook-steps-to-postgres`:
    conditional wording-healing compares what a task currently carries
    against the composition the system last wrote, so a read must expose
    both fields. They default to empty/absent so earlier constructions
    stay valid.
    """

    id: str
    status: str
    closed: bool
    due_date: date | None
    name: str = ""
    description: str | None = None
