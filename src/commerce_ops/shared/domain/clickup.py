"""ClickUp domain value objects: no behavior, no I/O.

Lives in `shared.domain` rather than next to the driven adapter so both
`shared.application`'s `ClickUpTaskWriter` port and
`shared.infrastructure.driven.clickup_client`'s concrete adapter can
reference it without either layer importing the other -- see
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ClickUpTask:
    """A ClickUp task's identifier and URL, as returned by a create or
    update call."""

    id: str
    url: str


@dataclass(frozen=True, slots=True)
class ClickUpListState:
    """A ClickUp list's own state, as a read of the list reports it.

    Added by `heal-a-launchs-deleted-list`, which needs to tell a list that
    still exists from one deleted in ClickUp. That cannot be told from the
    list's *tasks*: a deleted list answers a read of them successfully and
    empty, which is indistinguishable from a live list holding none.

    Carries only `deleted`, because only `deleted` is judged. A list whose
    state could not be read is not represented here at all — the read
    raises instead, so absence of an answer can never be mistaken for an
    answer of "not deleted".
    """

    deleted: bool


@dataclass(frozen=True, slots=True)
class ClickUpFieldOption:
    """One option a Custom Field declares, as a read of the field reports it.

    Added by `record-gate-and-discipline-as-fields`. Carries the option's
    identifier and its name, because both are needed and for different
    reasons: a value is *written* by identifier, and an option is
    *recognised* by name — the projection matches a step's gate identifier
    or discipline value against this name, exactly, and writes the
    identifier the match carries.
    """

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ClickUpFieldDefinition:
    """A Custom Field as a read of a folder's fields reports it.

    Added by `record-gate-and-discipline-as-fields`, which records a step's
    gate and discipline as values on two hand-configured fields.

    `options` is a *sequence*, and its order is the order the field
    declares — load-bearing rather than incidental. The gates are a
    sequence, and a field whose gate options are declared out of that
    sequence produces a view that reads as meaninglessly as the tags this
    replaced, so the configuration check compares the declared order and
    reports a departure. A field declaring no options carries an empty
    sequence, which is a fact about the field rather than an error.

    `uninterpretable` marks a field this capability could not make sense of
    — a type it does not anticipate, a shape it was not written against. It
    is deliberately distinct from "declares no options", though every
    uninterpretable field trivially declares none: collapsing the two would
    have a caller tell somebody to add options to a field that already has
    eight. Where it is set, the option sequence carries no meaning.
    """

    id: str
    name: str
    type: str
    options: tuple[ClickUpFieldOption, ...] = ()
    uninterpretable: bool = False


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
    both fields. `assignees` joined with `redesign-step-fields` for the
    same reason — a member's own assignment change is respected the way
    an edited name or body is, which the loop can only tell by reading
    what the task currently carries. They default to empty/absent so
    earlier constructions stay valid.

    `tags` joined with `tag-tasks-with-gate-and-discipline`, and for a
    different reason than the fields above: the projection adds an owned
    tag a task lacks and never removes one, so what it needs from a read
    is only whether the tag is already there. Tag *names* alone, because
    nothing judges a tag's colour — ClickUp assigns one and a member may
    change it.
    `custom_field_values` joined with `record-gate-and-discipline-as-fields`,
    keyed by the field's identifier. A value drawn from a field's option set
    is carried as that option's *identifier* — the same representation a
    write of it sends — so a caller can compare what a task holds against
    what it would write and send nothing when they agree. A value the client
    could not interpret is carried **exactly as the payload reported it** --
    a list, a mapping, whatever it was -- which is why the value type is
    `object` rather than `str`: stringifying it would alter it, and a caller
    must be able to tell what is actually there. It is not dropped either: this read gates a launch's projection and its completion
    intake, so a value nobody can make sense of must not be able to stop
    either, and reporting it absent would discard the difference between
    "nothing set" and "something not recognised".

    Defaults empty, the treatment `name`, `description`, `assignees` and
    `tags` were each given, so every earlier construction stays valid.
    """

    id: str
    status: str
    closed: bool
    due_date: date | None
    name: str = ""
    description: str | None = None
    assignees: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    custom_field_values: Mapping[str, object] = MappingProxyType({})
