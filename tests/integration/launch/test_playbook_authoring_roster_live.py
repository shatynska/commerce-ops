"""The roster collaborator an authoring write is given, against real
Postgres and the real adapters.

Derived strictly from the delta spec
`openspec/changes/restore-admin-step-writes/specs/playbook-authoring/spec.md`
(MODIFIED requirement *Every write is validated as the playbook it would
produce* — cases 1 and 3 of the roster collaborator's stated shape), and
placed here by `tasks.md` 5.1 and 5.2.

## Why this exists as well as the unit tier

`tests/unit/launch/application/test_authoring_roster_collaborator_shape.py`
hands the use cases a double shaped like `PostgresRoster`.
This file hands them **`PostgresRoster` itself**, over a live session,
which is the object `main.py` actually injects. A double can be shaped
wrongly and pass; the real adapter cannot.

`tests/integration/launch/test_playbook_authoring_live.py` — the file
`tasks.md` 5.1 names — passes no `roster=` at all, and so covers the
delta's case 2 and nothing else. This file is **additive** to it rather
than an edit of it: those no-roster cases are the suite's only coverage
of the permitted case and are left exactly as they are.

## Fixed by the artifacts, and what is INVENTED

Fixed: the collaborator's three cases, and that case 3 is a raised, named
error identifying what was supplied and what was expected.

INVENTED — the same two this directory's sibling records, plus one:

- The write store the use cases take as `steps=`, resolved from
  `launch/infrastructure/driven/playbook_repository`. Correction point:
  `_store`.
- The roster store adapter, `PostgresRoster()`, from
  `access/infrastructure/driven/roster_repository` — constructed with no
  session, since it opens its own per operation. Correction point:
  `_roster_store`.
- The session-scoped store it wraps, `RosterRepository(session)`, used
  wherever this file actually *reads* the roster. Correction point:
  `_roster_reader`.
- The error's class, and the spelling by which its message names the
  expected shape (`list_people`). Correction point:
  `_EXPECTED_SHAPE_NAMES`.

## Test-database lifecycle

This file's first test **writes nothing**: the refusal precedes any
persistence, which is also `proposal.md` — *Impact*'s reason for there
being no data migration. Its second test creates one `mg.*` step and
retires it, the convention this directory already follows; seeded `lp.*`
rows are never touched, and neither is the roster — no test here adds,
edits or deactivates a person.

One consequence is worth stating because it is easy to reintroduce:
nothing here **reads** the roster through `PostgresRoster()`. That
adapter opens its own connection pool and binds it to whichever event
loop first touches it, which outlives this module and breaks a later
test in this tier (`test_slack_entry_start.py`, "attached to a different
loop" — observed while writing these tests). It is used only where the
write is refused before any connection is opened; every read goes
through `RosterRepository(session)` on a session this file disposes.

`design.md` — *Risks* records that the local development roster is
empty, and that an empty roster makes the fixed path look like a
different failure. The second test therefore reads the live roster first
and **skips, saying so**, where it carries nobody active — rather than
asserting against an empty roster or inventing a person in a shared
database.

## Expected first-run state

`test_the_real_roster_store_is_refused_by_name` fails: today the real
store reaches `_read_people` unadapted and raises `TypeError: 'PostgresRoster'
object is not iterable`, which names what arrived and nothing about what
was expected.

`test_a_write_judged_against_the_live_roster_lands` **skips** on the
database this was written against, whose roster carries nobody — the
empty local roster `design.md` — *Risks* names. It is the only skip
these tests add, and the skip message says what to do about it. Where a
roster does carry an active person it is expected to pass, a reader
having always been an accepted shape, and is recorded in the manifest as
a regression guard that narrowing the collaborator to one shape does not
break case 1 against the real adapters.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 985 passed, 0 failed, 0 skipped, this tier included
(2026-08-26, commit `a9414ba`, clean tree).
"""

from __future__ import annotations

import inspect
import os
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.access.application import list_people
from commerce_ops.access.infrastructure.driven import roster_repository
from commerce_ops.launch.application import create_step, retire_step
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driven import playbook_repository
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"
A_DISCIPLINE: Final = next(iter(Discipline))

#: How a refusal may spell "the shape expected" (INVENTED — see the
#: docstring), matching the unit-tier file's set.
_EXPECTED_SHAPE_NAMES: Final = ("list_people", "listpeople", "list people")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate, as its sibling
    `test_playbook_authoring_live.py` records it: `_session()` is reached
    from test bodies rather than from a fixture, so this is how the file
    skips — or fails where the tier is required — when nothing is
    configured."""


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        value = await value
    return value


def _store(session: AsyncSession) -> Any:
    """The step write store — the correction point its sibling records."""
    factory = (
        getattr(playbook_repository, "PlaybookStepStore", None)
        or playbook_repository.PlaybookRepository
    )
    return factory(session)


def _roster_store() -> Any:
    """The roster store `main.py` injects into the admin page.

    Constructed with no session: it is "the `RosterStore` port, opening
    its own session per operation", which is why the admin surface holds
    one of these rather than a session.

    Used **only** by the refusal test, which never reaches a connection —
    the collaborator is refused on its shape before anything is loaded.
    Reading the roster through it would open its internal pool on this
    module's event loop and leave it bound there for the rest of the
    tier; `_roster_reader` below exists for that reason.
    """
    return roster_repository.PostgresRoster()


def _roster_reader(session: AsyncSession) -> Any:
    """The same roster, read over a session this file owns and disposes.

    `RosterRepository(session)` is the store `PostgresRoster` wraps, so
    what `list_people` sees is identical — only the session's lifetime
    differs, and this one ends with the test rather than outliving it.
    """
    return _ReaderOverTheStore(roster_repository.RosterRepository(session))


async def _served() -> LaunchPlaybook:
    async with _session() as session:
        served = await _maybe_await(
            playbook_repository.PlaybookRepository(session).get(
                "any-version-read-through"
            )
        )
        assert isinstance(served, LaunchPlaybook)
        return served


def _unique_description(label: str) -> str:
    return f"{label} ({uuid.uuid4().hex[:12]})"


def _authorable_fields(description: str, assignees: tuple[str, ...]) -> dict[str, Any]:
    return {
        "name": description,
        "gate": "ignition",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-3),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": None,
        "assignees": assignees,
    }


class _ReaderOverTheStore:
    """The adaptation the admin page is required to make: the roster
    store, read through `access`'s own public `list_people`."""

    def __init__(self, store: Any) -> None:
        self._store = store

    async def list_people(self) -> Sequence[Any]:
        return tuple(await _maybe_await(list_people(roster=self._store)))


async def _active_person() -> Any | None:
    async with _session() as session:
        people = await _roster_reader(session).list_people()
    return next((person for person in people if getattr(person, "active", True)), None)


def _identifier_of(person: Any) -> str:
    for name in ("identifier", "id", "person_id"):
        if hasattr(person, name):
            return str(getattr(person, name))
    pytest.fail(f"a roster person carries no identifier: {person!r}")


# ---------------------------------------------------------------------------
# MODIFIED requirement: Every write is validated as the playbook it would
# produce — the roster collaborator, against the real adapters
# ---------------------------------------------------------------------------


async def test_the_real_roster_store_is_refused_by_name() -> None:
    """Scenario: A collaborator of the wrong shape is refused by name —
    with the collaborator being the real `PostgresRoster`.

    WHEN a write is given a roster collaborator that cannot answer who
    the roster carries
    THEN the write is refused with a named error identifying the
    collaborator supplied and the shape expected
    AND the step set is unchanged.

    This is the production wiring exactly: the object `main.py` injects,
    handed to the use case the way the admin page's write routes hand it
    over today. Nothing is written — the refusal precedes any
    persistence, which is why this change carries no data migration.
    """
    description = _unique_description("A step no write should ever persist")
    version_before = (await _served()).version

    async with _session() as session:
        supplied = _roster_store()
        with pytest.raises(Exception) as caught:
            await _maybe_await(
                create_step(
                    steps=_store(session),
                    principal=PRINCIPAL,
                    roster=supplied,
                    **_authorable_fields(description, ()),
                )
            )

    # SPECIFIED: not among the write's coherence faults …
    assert not isinstance(caught.value, InvalidPlaybookError), (
        "the real roster store was refused as an `InvalidPlaybookError`, the "
        "type a rejected write's fault list arrives in — a mis-wired "
        "deployment would be rendered to an author as a fault of what they "
        "submitted"
    )
    message = str(caught.value)
    # … and it identifies both what was supplied …
    assert type(supplied).__name__ in message, (
        "the refusal does not name the collaborator that was supplied "
        f"({type(supplied).__name__!r}): {message!r}"
    )
    # … and what was expected.
    assert any(name in message.lower() for name in _EXPECTED_SHAPE_NAMES), (
        "the refusal names only what arrived, not the shape expected: "
        f"{message!r} — which is the production message that made a wholly "
        "broken write path read as an unexplained internal error"
    )

    # SPECIFIED: the step set is unchanged — nothing was half-written and
    # the served version did not move.
    served = await _served()
    assert served.version == version_before
    assert all(step.name != description for step in served.steps)


async def test_a_write_judged_against_the_live_roster_lands() -> None:
    """Scenario: A roster that answers the stated shape — case 1, against
    the live roster.

    WHEN a write is given a roster collaborator answering the stated
    shape, naming a person that roster carries as active
    THEN the two preconditions are evaluated and the write lands.

    `design.md` — *Risks*: "an empty roster is not a neutral state for
    the fixed path: once the preconditions actually run, an `active`
    `human` step can no longer be saved without an assignee the roster
    carries. Verification has to happen against a roster that holds
    people, or the fix will look like a different failure." So this test
    skips, saying so, rather than asserting against an empty one — and
    it adds nobody to a shared roster to avoid the skip.
    """
    person = await _active_person()
    if person is None:
        pytest.skip(
            "the live roster carries no active person, so the two write-side "
            "preconditions cannot be satisfied by any assignee — see "
            "`design.md` — *Risks*; seed a person and re-run to cover this"
        )

    identifier = _identifier_of(person)
    description = _unique_description("Work judged against the live roster")
    before = {step.identifier for step in (await _served()).steps}

    async with _session() as session:
        await _maybe_await(
            create_step(
                steps=_store(session),
                principal=PRINCIPAL,
                roster=_roster_reader(session),
                **_authorable_fields(description, (identifier,)),
            )
        )

    served = await _served()
    created = [
        step
        for step in served.steps
        if step.identifier not in before and step.name == description
    ]
    # SPECIFIED: the preconditions were evaluated and the write landed.
    assert len(created) == 1, (
        "the write naming a person the live roster carries as active did not "
        f"join the served set: {[s.identifier for s in created]}"
    )
    assert tuple(created[0].assignees) == (identifier,)

    # This directory's residue convention: the step this test authored is
    # retired again, leaving the served set as it found it.
    async with _session() as session:
        await _maybe_await(
            retire_step(
                steps=_store(session),
                principal=PRINCIPAL,
                step_id=created[0].identifier,
            )
        )
