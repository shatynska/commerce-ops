"""Write use cases of the `roster` capability.

The roster lives in a store behind the `RosterStore` port; these four
operations — plus the startup seed — are the only way it changes. Every
write is validated by constructing the **entire** `Roster` the write
would produce, so the same coherence rulebook guards every path, and a
rejected write reports every fault at once (`InvalidRosterError`) while
persisting nothing.

Writes are serialized by the store's optimistic set-version: each
operation loads the roster with its version and persists conditionally on
that version being unchanged. A lost race (`StaleRosterError`) is retried
against the fresh roster, re-validating — the retry may now be rightly
rejected (the second of two deactivations that together would leave the
roster without an active admin).

Identifiers are generated, never chosen, and never reused: a step's
assignees reference them, so correcting a person's data must never move
their identifier. The Slack identity is likewise immutable — retire the
entry and create its successor rather than re-pointing an identifier at a
different human.

The shape mirrors `launch.application.playbook_authoring`, deliberately:
the two capabilities own editable sets with set-level invariants, and one
idiom for both is easier to hold than two.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from commerce_ops.access.domain.principals import (
    InvalidRosterError,
    Person,
    Roster,
)

_logger = logging.getLogger(__name__)

BOOTSTRAP_ADMIN_VARIABLE = "BOOTSTRAP_ADMIN_IDENTITY"
"""The declared variable naming the first admin's Slack identity."""

SYSTEM_PRINCIPAL = "system:bootstrap"
"""Who the startup seed attributes its write to. Never collides with a
Slack identity — different alphabet — so a seeded entry is always
distinguishable from one a human created."""

_WRITE_ATTEMPTS = 3
"""How many times a write retries after losing the set-version race."""

_UPDATABLE = ("display_name", "clickup_user_id", "admin")
"""Exactly what `update_person` may change. The identifier and the Slack
identity are immutable; active status moves only through deactivate and
reactivate, so those transitions always carry their own attribution."""


class StaleRosterError(RuntimeError):
    """A conditional persist lost the race: the roster changed between
    load and save."""


@dataclass(slots=True)
class PersonRecord:
    """One stored person: their identity data plus the attribution trail.

    The attribution is the audit that replaces the deleted directory
    file's git trail, so it is recorded here on the row rather than
    inferred from anything.
    """

    person: Person
    created_by: str | None = None
    created_on: datetime | None = None
    updated_by: str | None = None
    updated_on: datetime | None = None
    deactivated_by: str | None = None
    deactivated_on: datetime | None = None
    reactivated_by: str | None = None
    reactivated_on: datetime | None = None
    admin_conferred_by: str | None = None
    """Who made this entry an active admin — the creation or promotion
    that conferred the flag, not merely the last write to touch the row.

    Carried separately from `updated_by` on purpose: the startup seed's
    bounded re-assertion turns on whether the roster's only active admin
    is one the seed itself created, and a later edit by that admin (a
    corrected display name) confers nothing and must not erase the
    signal. Reading it off `updated_by` would let exactly that happen.
    """

    @property
    def identifier(self) -> str:
        return self.person.identifier

    @property
    def slack_identity(self) -> str:
        return self.person.slack_identity

    @property
    def active(self) -> bool:
        return self.person.active


class RosterStore(Protocol):
    """The roster persistence port.

    `load` returns every stored row — deactivated included, since the
    uniqueness rule spans them — with the current set-version; `save`
    persists a full replacement set conditionally on that version,
    raising `StaleRosterError` when it has moved.
    """

    async def load(self) -> tuple[Sequence[Any], int]: ...

    async def save(self, rows: Sequence[Any], *, expected_version: int) -> None: ...


def _as_record(row: Any) -> PersonRecord:
    """A loaded row as a `PersonRecord`, whatever concrete type the store
    yielded — the attribute spellings are the port's contract."""
    if isinstance(row, PersonRecord):
        return row
    return PersonRecord(
        person=row.person,
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        deactivated_by=row.deactivated_by,
        deactivated_on=row.deactivated_on,
        reactivated_by=row.reactivated_by,
        reactivated_on=row.reactivated_on,
        admin_conferred_by=getattr(row, "admin_conferred_by", None),
    )


def people_of(rows: Sequence[Any]) -> tuple[Person, ...]:
    """The people a set of stored rows carries, deactivated included."""
    return tuple(row.person for row in rows)


async def list_people(*, roster: RosterStore) -> tuple[Person, ...]:
    """Everyone the roster carries, deactivated included.

    The read half of this capability's public surface, added by
    `redesign-step-fields`: a step's assignees reference roster people by
    identifier, so `launch` has to resolve them — and it may only reach
    this module through the surface this function is part of. Deactivated
    entries are answered too, because "is this person still active" is a
    question the caller has to be able to ask rather than have decided
    for it.
    """
    rows, _version = await roster.load()
    return people_of(rows)


def _validate(rows: Sequence[Any]) -> None:
    """Construct the roster the write would produce; `InvalidRosterError`
    propagates with every fault."""
    Roster(people=people_of(rows))


def _generate_identifier() -> str:
    """A fresh identifier, independent of every attribute a person has —
    so correcting their data never moves it."""
    return str(uuid.uuid4())


def _find(rows: Sequence[Any], person_id: str) -> int:
    for index, row in enumerate(rows):
        if row.person.identifier == person_id:
            return index
    raise ValueError(f"no stored person carries the identifier '{person_id}'")


def _copy(row: Any) -> PersonRecord:
    """A fresh record for `row`, never the loaded object itself — so a
    write that loses the save race has mutated nothing."""
    record = _as_record(row)
    return replace(record) if record is row else record


async def create_person(
    *,
    roster: RosterStore,
    principal: str,
    display_name: str,
    slack_identity: str,
    clickup_user_id: str | None = None,
    admin: bool = False,
) -> PersonRecord:
    """Create a person with a generated identifier, attributed to
    `principal`. Validated as the whole roster it would produce."""
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roster.load()
        now = datetime.now(UTC)
        record = PersonRecord(
            person=Person(
                identifier=_generate_identifier(),
                display_name=display_name,
                slack_identity=slack_identity,
                clickup_user_id=clickup_user_id,
                admin=admin,
                active=True,
            ),
            created_by=principal,
            created_on=now,
            admin_conferred_by=principal if admin else None,
        )
        candidate = (*rows, record)
        _validate(candidate)
        try:
            await roster.save(candidate, expected_version=version)
        except StaleRosterError:
            continue
        return record
    raise StaleRosterError(
        f"create_person lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def update_person(
    *,
    roster: RosterStore,
    principal: str,
    person_id: str,
    **fields: Any,
) -> PersonRecord:
    """Update a person's updatable fields — the display name, the ClickUp
    user id and the admin flag, on deactivated entries as well as active
    ones. Never the identifier, never the Slack identity, and never the
    active status (which moves only through deactivate and reactivate, so
    those transitions keep their own attribution)."""
    if "identifier" in fields or "person_id" in fields:
        raise ValueError("a person's identifier is not updatable")
    if "slack_identity" in fields:
        raise ValueError(
            f"a person's Slack identity is not updatable: '{person_id}' keeps "
            f"the identity it was created with, so an identifier is never "
            f"re-pointed at a different human; deactivate the entry and "
            f"create its successor instead"
        )
    if "active" in fields:
        raise ValueError(
            "active status is not updatable: use deactivate_person or "
            "reactivate_person, so the transition records who made it"
        )
    unknown = sorted(set(fields) - set(_UPDATABLE))
    if unknown:
        raise ValueError(
            f"a person carries no updatable field named {', '.join(unknown)}"
        )

    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roster.load()
        index = _find(rows, person_id)
        record = _copy(rows[index])
        was_admin = record.person.admin
        record.person = replace(record.person, **fields)
        if record.person.admin != was_admin:
            record.admin_conferred_by = principal if record.person.admin else None
        record.updated_by = principal
        record.updated_on = datetime.now(UTC)
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate)
        try:
            await roster.save(candidate, expected_version=version)
        except StaleRosterError:
            continue
        return record
    raise StaleRosterError(
        f"update_person lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def deactivate_person(
    *, roster: RosterStore, principal: str, person_id: str
) -> PersonRecord:
    """Deactivate a person: excluded from access resolution, never
    deleted. Rejected whole when the remaining roster would hold no
    active admin."""
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roster.load()
        index = _find(rows, person_id)
        record = _copy(rows[index])
        record.person = replace(record.person, active=False)
        record.deactivated_by = principal
        record.deactivated_on = datetime.now(UTC)
        record.reactivated_by = None
        record.reactivated_on = None
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate)
        try:
            await roster.save(candidate, expected_version=version)
        except StaleRosterError:
            continue
        return record
    raise StaleRosterError(
        f"deactivate_person lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def reactivate_person(
    *, roster: RosterStore, principal: str, person_id: str
) -> PersonRecord:
    """Restore a deactivated person under their original identifier,
    attributing the reversal like the deactivation was."""
    for _ in range(_WRITE_ATTEMPTS):
        rows, version = await roster.load()
        index = _find(rows, person_id)
        record = _copy(rows[index])
        record.person = replace(record.person, active=True)
        record.reactivated_by = principal
        record.reactivated_on = datetime.now(UTC)
        candidate = (*rows[:index], record, *rows[index + 1 :])
        _validate(candidate)
        try:
            await roster.save(candidate, expected_version=version)
        except StaleRosterError:
            continue
        return record
    raise StaleRosterError(
        f"reactivate_person lost the set-version race {_WRITE_ATTEMPTS} times"
    )


def _seed_conferred(record: PersonRecord) -> bool:
    """Whether the seed itself made this entry an active admin."""
    return record.admin_conferred_by == SYSTEM_PRINCIPAL


async def seed_bootstrap_admin(
    *, roster: RosterStore, identity: str | None = None
) -> PersonRecord | None:
    """Ensure the roster has an admin, or explain why it cannot.

    Runs as a preparation step of its own — after the migrations that
    create the roster tables, before the server starts — never inside the
    serving process's startup, so that starting the application still
    opens no database connection before one is first needed
    (`database-session`). A store that cannot be read is a deployment
    fault here rather than a state to tolerate: the migrations just wrote
    to it.

    Four outcomes, exactly as the `roster` capability states them:

    - the roster already holds an active admin beyond a lone
      seed-attributed entry — nothing is touched and the variable confers
      nothing;
    - the roster's only active admin is one the seed created and the
      variable now names someone else — the newly named identity is
      seeded alongside it, deactivating nothing, so a mis-typed first
      seed is recoverable by fixing the variable and redeploying;
    - the roster holds no active admin and the variable names an identity
      — that identity is created, or promoted if already present, as one
      atomic write;
    - the roster holds no active admin and no variable is set — the step
      fails, naming the variable, and the server never starts.

    The seed is a single create-or-promote save rather than a
    reactivate-then-update pair: every intermediate roster in such a pair
    still holds zero active admins, which the last-admin floor rejects.
    """
    # Read by its literal name, which is how the settings drift check
    # detects that the declared variable is actually consumed. A value that
    # is empty or only whitespace counts as absent rather than as an
    # identity: a rendered `.env` line with nothing after the `=` is a
    # variable nobody set, and seeding an entry from it would fail later
    # with a fault about the entry instead of one naming the variable.
    wanted = (
        identity or os.environ.get("BOOTSTRAP_ADMIN_IDENTITY") or ""
    ).strip() or None

    # No tolerance for an unreadable store: this step runs after the
    # migrations that just wrote to it, so a failure here is a deployment
    # fault and must stop the deployment rather than pass quietly.
    rows, version = await roster.load()

    records = [_as_record(row) for row in rows]
    active_admins = [
        record for record in records if record.person.admin and record.active
    ]

    if active_admins:
        lone_seed = len(active_admins) == 1 and _seed_conferred(active_admins[0])
        misseeded = (
            lone_seed
            and wanted is not None
            and wanted != active_admins[0].person.slack_identity
        )
        if not misseeded:
            return None

    if wanted is None:
        raise RuntimeError(
            f"the roster holds no active admin and {BOOTSTRAP_ADMIN_VARIABLE} "
            f"is not set, so nobody could administer this deployment; set "
            f"{BOOTSTRAP_ADMIN_VARIABLE} to the Slack user id of the first "
            f"admin and deploy again"
        )

    now = datetime.now(UTC)
    existing = next(
        (
            index
            for index, record in enumerate(records)
            if record.person.slack_identity == wanted
        ),
        None,
    )

    if existing is None:
        seeded = PersonRecord(
            person=Person(
                identifier=_generate_identifier(),
                # The identity itself stands in as the display name until a
                # human corrects it; a blank one would fail validation.
                display_name=wanted,
                slack_identity=wanted,
                admin=True,
                active=True,
            ),
            created_by=SYSTEM_PRINCIPAL,
            created_on=now,
            admin_conferred_by=SYSTEM_PRINCIPAL,
        )
        candidate = (*rows, seeded)
    else:
        seeded = _copy(rows[existing])
        seeded.person = replace(seeded.person, admin=True, active=True)
        seeded.updated_by = SYSTEM_PRINCIPAL
        seeded.updated_on = now
        seeded.admin_conferred_by = SYSTEM_PRINCIPAL
        candidate = (*rows[:existing], seeded, *rows[existing + 1 :])

    _validate(candidate)
    await roster.save(candidate, expected_version=version)
    _logger.info(
        "seeded '%s' as the bootstrap admin from %s; correct the display "
        "name from the roster page",
        wanted,
        BOOTSTRAP_ADMIN_VARIABLE,
    )
    return seeded


__all__ = [
    "BOOTSTRAP_ADMIN_VARIABLE",
    "SYSTEM_PRINCIPAL",
    "InvalidRosterError",
    "PersonRecord",
    "RosterStore",
    "StaleRosterError",
    "create_person",
    "deactivate_person",
    "people_of",
    "reactivate_person",
    "seed_bootstrap_admin",
    "update_person",
]
