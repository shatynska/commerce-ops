"""The roster: who is known, and in what capacity.

Implements the coherence rules of the `roster` capability. Deterministic
and I/O-free: persistence is the store adapter's concern
(`access.infrastructure.driven.roster_repository`), which translates
stored rows into the values these constructors expect and re-implements
none of the rules below.

Two of those rules are properties of the whole set rather than of any one
person — a Slack identity names exactly one human, and the roster never
loses its last active admin — which is why a write validates the roster it
would produce rather than the row it touches.

Nothing here authenticates. A person's Slack identity is the opaque string
an adapter has already established; the domain never learns how.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class InvalidRosterError(ValueError):
    """A roster (or a person within one) fails coherence.

    Carries every fault found in one validation, not just the first, so a
    rejected write does not have to be corrected one fault at a time —
    the shape `InvalidPrincipalsError` established, kept deliberately
    (`move-principals-to-roster`, tasks.md 1.1).
    """

    def __init__(self, faults: Sequence[str]) -> None:
        self.faults: tuple[str, ...] = tuple(faults)
        super().__init__("; ".join(self.faults))


@dataclass(frozen=True, slots=True)
class Person:
    """One known human: identity data, authority, and whether they are current.

    The identifier is generated, never chosen by a caller, and never
    reused — a step's assignees will reference it, so it must not move
    when the person's data is corrected. The Slack identity is the
    credential an adapter establishes; it is unique across the *whole*
    roster, deactivated entries included, and immutable, so an identifier
    can never be quietly re-pointed at a different human.

    Attribution does not live here: who created, updated, deactivated or
    reactivated a person is recorded on the stored row
    (`access.application.roster.PersonRecord`), the split
    `launch`'s `StepDefinition`/`StepRecord` already uses.
    """

    identifier: str
    display_name: str
    slack_identity: str
    clickup_user_id: str | None = None
    admin: bool = False
    active: bool = True

    def __post_init__(self) -> None:
        faults = self.faults()
        if faults:
            raise InvalidRosterError(faults)

    def faults(self) -> tuple[str, ...]:
        """Every coherence fault this person carries, named against it.

        Exposed as well as raised so a whole-roster validation can gather
        each entry's faults into one rejection rather than surfacing the
        first and hiding the rest.
        """
        found: list[str] = []
        who = self.slack_identity or self.identifier or "<unidentified>"

        if not self.identifier or not self.identifier.strip():
            found.append("a person entry carries an empty identifier")

        if not self.display_name or not self.display_name.strip():
            found.append(f"person '{who}' carries an empty display name")

        if not self.slack_identity:
            found.append(f"person '{self.identifier}' carries an empty Slack identity")
        elif self.slack_identity != self.slack_identity.strip():
            found.append(
                f"person '{self.identifier}' carries a Slack identity with "
                f"leading or trailing whitespace: {self.slack_identity!r}"
            )

        if self.clickup_user_id is not None and not self.clickup_user_id.strip():
            found.append(
                f"person '{who}' carries an empty ClickUp user id — omit it "
                f"instead, since absent and empty differ"
            )

        return tuple(found)


@dataclass(frozen=True, slots=True)
class Roster:
    """Every known person, validated as a whole.

    Two of the rules are properties of the *set*, not of any entry, which
    is why validation happens here and why a write validates the roster
    it would produce rather than the row it touches: a Slack identity is
    unique across every entry, and the roster never loses its last active
    admin.
    """

    people: tuple[Person, ...] = ()

    def __post_init__(self) -> None:
        faults = [fault for person in self.people for fault in person.faults()]
        faults.extend(self._duplicate_identity_faults())
        faults.extend(self._admin_floor_faults())
        if faults:
            raise InvalidRosterError(faults)

    def _duplicate_identity_faults(self) -> list[str]:
        seen: set[str] = set()
        duplicated: list[str] = []
        for person in self.people:
            if (
                person.slack_identity in seen
                and person.slack_identity not in duplicated
            ):
                duplicated.append(person.slack_identity)
            seen.add(person.slack_identity)
        return [
            f"the Slack identity '{identity}' is carried by more than one "
            f"person — an identity names exactly one human, deactivated "
            f"entries included"
            for identity in duplicated
        ]

    def _admin_floor_faults(self) -> list[str]:
        """The floor: a roster holding anyone holds an active admin.

        An empty roster is coherent — nobody is declared yet, which is
        the state the startup seed exists to resolve. A roster holding
        people but no active admin is not: it locks the door and
        swallows the key, so the write producing it is rejected whole.
        """
        if not self.people:
            return []
        if any(person.active and person.admin for person in self.people):
            return []
        return [
            (
                "the roster would be left without an active admin — nobody "
                "could administer it, and no write could restore one"
            )
        ]

    def entry_for(self, slack_identity: str) -> Person | None:
        """The person carrying `slack_identity`, or `None` for a stranger."""
        for person in self.people:
            if person.slack_identity == slack_identity:
                return person
        return None

    def active_admins(self) -> tuple[Person, ...]:
        return tuple(person for person in self.people if person.active and person.admin)
