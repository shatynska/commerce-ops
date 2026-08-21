"""ClickUp domain value objects: no behavior, no I/O.

Lives in `shared.domain` rather than next to the driven adapter so both
`shared.application`'s `ClickUpTaskWriter` port and
`shared.infrastructure.driven.clickup_client`'s concrete adapter can
reference it without either layer importing the other -- see
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClickUpTask:
    """A ClickUp task's identifier and URL, as returned by a create or
    update call."""

    id: str
    url: str
