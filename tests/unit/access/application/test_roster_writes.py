"""The roster's validated, attributed write use cases (`roster`).

Derived strictly from the delta spec:
`openspec/changes/move-principals-to-roster/specs/roster/spec.md` — four
of its five ADDED requirements, twelve scenarios:

- *A person is a declared identity with coherent identity data* (3)
- *Every roster write is validated whole and attributed* (4)
- *The roster never loses its last active admin* (3)
- *A person is deactivated, never deleted* (2)

The fifth requirement (*The first admin is seeded from declared
configuration*) is covered in `test_roster_bootstrap.py`.

## Why the application level

Every scenario above is stated about a *write* and what the roster holds
afterwards — "nothing is persisted", "a subsequent read observes the
roster exactly as it was", "records who deactivated it and when". The
domain alone cannot observe persistence, so the smallest observing unit
is the write use case over a store double: no Postgres, no I/O, the
project's fast mocked unit tier.

## Seed state is built through the use cases, deliberately

The only shape any artifact fixes for a stored roster row is whatever the
write use cases produce (`design.md` Decision 1: `load() -> (rows,
version)` / `save(rows, expected_version)`), so these tests build their
starting rosters by *calling* `create_person` rather than by inventing a
row class and handing it to `load()`. The trade — a `create_person`
defect fails tests written for `update`/`deactivate` too — is the one
`tests/unit/access/application/test_resolve_scope.py` recorded for
building directories through the loader, and is recorded again in
`test-manifest.md`.

The first write against an empty roster is always an *admin* create.
That is forced by the last-admin floor as the delta states it ("a write
whose outcome would leave the roster without at least one active entry
carrying the admin flag SHALL be rejected whole"): on an empty roster no
non-admin create has a coherent outcome. `design.md` Decision 4 confirms
the reading — it is why the startup seed must be one atomic write rather
than composed from the enumerated verbs.

## The interface under test does not exist yet

Fixed by the artifacts, not invented: the four use-case names
`create_person`, `update_person`, `deactivate_person`,
`reactivate_person` exported from `commerce_ops.access.application`
(`tasks.md` 2.1, 2.4); the aggregated error `InvalidRosterError` in
`commerce_ops.access.domain.principals`, same shape as
`InvalidPrincipalsError` (`tasks.md` 1.1); the store port's
`load`/`save` pair (`design.md` Decision 1); that `update` may change
exactly the display name, the ClickUp user id and the admin flag.

INVENTED, each recorded in the manifest as an unresolved project
question, with its single correction point named:

- The call shape `create_person(roster=store, principal=..., ...)` and
  its siblings — collaborator-first with a keyword `principal`,
  mirroring `create_step(steps=..., principal=...)` in
  `tests/unit/launch/application/test_playbook_authoring.py`.
  Correction points: `_create`, `_update`, `_deactivate`, `_reactivate`.
- The field keywords `display_name`, `slack_identity`,
  `clickup_user_id`, `admin`, and the addressing keyword `person_id`.
  Correction points: the same four helpers.
- The stored row's attribute spellings, read through `_field` with
  candidate names — including whether attribution sits on the row or on
  a nested person object. Correction point: the `_*_NAMES` tuples.
- `REFUSED`, the tuple of acceptable exception types where the delta
  fixes the outcome ("refused", "rejected") but not the type — the
  `REJECTED` precedent from `test_playbook_authoring.py`.

What must survive any of those corrections is what each test asserts:
what was persisted, what was not, and who is recorded as having done it.

## Expected first-run state

`commerce_ops.access.application` exports none of these use cases, so
every test here is expected to fail on an absent target (`ImportError`).
Per `ai-toolkit:testing` that failure establishes only absence — the
assertions below have not been exercised by it.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25). The `tests/integration` tier was not run: it needs a live
Postgres, and another session holds that directory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

import pytest

import commerce_ops.access.application as access_application
from commerce_ops.access.application import (
    create_person,
    deactivate_person,
    reactivate_person,
    resolve_scope,
    update_person,
)
from commerce_ops.access.domain.principals import InvalidRosterError
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

# DERIVED sample values; no artifact fixes example identities or names.
ADMIN_IDENTITY: Final = "U01ALICE"
SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
NEWCOMER_IDENTITY: Final = "U04DAVE"

ADMIN_NAME: Final = "Alice Admin"
MEMBER_NAME: Final = "Carol Member"

PRINCIPAL: Final = "helen"
ANOTHER_PRINCIPAL: Final = "the-second-admin"

# INVENTED refusal surface: the delta fixes the outcome, not the type.
REFUSED: Final = (InvalidRosterError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# The roster store double (the port `design.md` Decision 1 fixes)
# ---------------------------------------------------------------------------


class _FakeRosterStore:
    """In-memory whole-set roster store with the optimistic set-version.

    `load()` answers every stored row — deactivated included, since the
    uniqueness rule spans them — together with the current version;
    `save()` persists a replacement set conditionally on the version it
    was loaded at. Shaped after `_FakeStepStore` in
    `tests/unit/launch/application/test_playbook_authoring.py`.
    """

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


# ---------------------------------------------------------------------------
# Row accessors: the single correction point for attribute spellings
# ---------------------------------------------------------------------------

_ID_NAMES: Final = ("id", "person_id", "identifier")
_NAME_NAMES: Final = ("display_name", "name")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_CLICKUP_NAMES: Final = ("clickup_user_id", "clickup_id")
_ADMIN_NAMES: Final = ("admin", "is_admin")
_ACTIVE_NAMES: Final = ("active", "is_active")

_CREATED_BY: Final = ("created_by",)
_CREATED_ON: Final = ("created_on", "created_at")
_UPDATED_BY: Final = ("updated_by",)
_UPDATED_ON: Final = ("updated_on", "updated_at")
_DEACTIVATED_BY: Final = ("deactivated_by",)
_DEACTIVATED_ON: Final = ("deactivated_on", "deactivated_at")
_REACTIVATED_BY: Final = ("reactivated_by",)
_REACTIVATED_ON: Final = ("reactivated_on", "reactivated_at")


def _targets(row: Any) -> tuple[Any, ...]:
    """The row itself plus any nested person/entry object, since no
    artifact fixes whether attribution sits beside the identity data or
    wraps it."""
    found = [row]
    for attribute in ("person", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None:
            found.append(nested)
    return tuple(found)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    """Reads one field of a stored row, failing loudly rather than
    defaulting, so no assertion below can pass vacuously."""
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored roster row exposes no {what} under any of {names} — "
        "correct this file's accessor names to the implemented row"
    )


def _id(row: Any) -> Any:
    return _field(row, _ID_NAMES, "generated identifier")


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _name(row: Any) -> str:
    return str(_field(row, _NAME_NAMES, "display name"))


def _is_admin(row: Any) -> bool:
    return bool(_field(row, _ADMIN_NAMES, "admin flag"))


def _is_active(row: Any) -> bool:
    return bool(_field(row, _ACTIVE_NAMES, "active flag"))


def _row_for(store: _FakeRosterStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return row
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


def _row_by_id(store: _FakeRosterStore, person_id: Any) -> Any:
    for row in store.rows:
        if _id(row) == person_id:
            return row
    pytest.fail(f"no stored row carries the identifier {person_id!r}")


def _faults(error: BaseException) -> tuple[str, ...]:
    """Every fault the rejection reports, however the aggregated error
    carries them (`InvalidPrincipalsError`'s shape is a list of
    messages; `tasks.md` 1.1 keeps it for `InvalidRosterError`)."""
    for attribute in ("faults", "errors", "messages", "reasons"):
        carried = getattr(error, attribute, None)
        if isinstance(carried, (list, tuple)) and carried:
            return tuple(str(fault) for fault in carried)
    if error.args and isinstance(error.args[0], (list, tuple)):
        return tuple(str(fault) for fault in error.args[0])
    return tuple(line for line in str(error).splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Use-case call shapes: the single correction point
# ---------------------------------------------------------------------------


async def _create(
    store: _FakeRosterStore,
    *,
    display_name: str,
    slack_identity: str,
    clickup_user_id: str | None = None,
    admin: bool = False,
    principal: str = PRINCIPAL,
) -> Any:
    return await create_person(
        roster=store,
        principal=principal,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=clickup_user_id,
        admin=admin,
    )


async def _update(
    store: _FakeRosterStore,
    person_id: Any,
    *,
    principal: str = PRINCIPAL,
    **fields: Any,
) -> Any:
    return await update_person(
        roster=store, principal=principal, person_id=person_id, **fields
    )


async def _deactivate(
    store: _FakeRosterStore, person_id: Any, *, principal: str = PRINCIPAL
) -> Any:
    return await deactivate_person(
        roster=store, principal=principal, person_id=person_id
    )


async def _reactivate(
    store: _FakeRosterStore, person_id: Any, *, principal: str = PRINCIPAL
) -> Any:
    return await reactivate_person(
        roster=store, principal=principal, person_id=person_id
    )


async def _roster_with_an_admin() -> _FakeRosterStore:
    """A store holding exactly one active admin, built through the write
    path (see the module docstring)."""
    store = _FakeRosterStore()
    await _create(
        store,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    return store


def _snapshot(store: _FakeRosterStore) -> tuple[Any, int, int]:
    return store.rows, store.version, len(store.saves)


def _assert_unchanged(store: _FakeRosterStore, before: tuple[Any, int, int]) -> None:
    """SPECIFIED across three scenarios: a rejected write persists
    nothing — asserted as the stored set, the set-version and the number
    of saves all standing exactly where they stood."""
    assert (store.rows, store.version, len(store.saves)) == before, (
        "a rejected write reached the store: the roster must be left exactly as it was"
    )


# ---------------------------------------------------------------------------
# Requirement: A person is a declared identity with coherent identity data
# ---------------------------------------------------------------------------


async def test_a_created_person_carries_a_generated_identifier() -> None:
    """Scenario: A created person carries a generated identifier.

    WHEN a person is created with a display name and a Slack identity
    THEN the created entry carries an identifier the caller did not
    supply, and the entry is retrievable by it.

    "Retrievable by it" is asserted twice over: the identifier locates
    the row in the store, and an `update` addressed by that identifier
    lands on the same row. Without the second half, an implementation
    generating an identifier it cannot address by would pass.

    A second create asserts the identifiers differ — the requirement's
    "never reused" clause at the only strength a two-write test can
    reach.
    """
    store = await _roster_with_an_admin()
    before = {_id(row) for row in store.rows}

    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)

    created = [row for row in store.rows if _id(row) not in before]
    assert len(created) == 1
    person_id = _id(created[0])

    # SPECIFIED: an identifier the caller did not supply.
    assert person_id is not None
    assert str(person_id).strip() != ""
    assert str(person_id) not in (MEMBER_IDENTITY, MEMBER_NAME)

    # SPECIFIED: the entry is retrievable by it.
    assert _slack(_row_by_id(store, person_id)) == MEMBER_IDENTITY
    await _update(store, person_id, display_name="Carol Corrected")
    assert _name(_row_by_id(store, person_id)) == "Carol Corrected"

    # SPECIFIED: identifiers are never reused (two writes' worth).
    await _create(store, display_name="Dave Newcomer", slack_identity=NEWCOMER_IDENTITY)
    assert len({_id(row) for row in store.rows}) == len(store.rows)


@pytest.mark.parametrize(
    "deactivate_first", [False, True], ids=["active", "deactivated"]
)
async def test_a_duplicate_slack_identity_is_rejected(deactivate_first: bool) -> None:
    """Scenario: A duplicate Slack identity is rejected.

    WHEN a person is created with a Slack identity an existing entry
    already carries — even a deactivated one
    THEN the write is rejected with a fault naming that Slack identity,
    and nothing is persisted.

    Parametrized over both halves of "even a deactivated one": the
    deactivated case is the discriminating one, since an implementation
    checking uniqueness against only the active roster passes the first
    and fails the second.
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    if deactivate_first:
        await _deactivate(store, _id(_row_for(store, MEMBER_IDENTITY)))

    before = _snapshot(store)

    with pytest.raises(REFUSED) as excinfo:
        await _create(
            store,
            display_name="Someone Else Entirely",
            slack_identity=MEMBER_IDENTITY,
        )

    # SPECIFIED: a fault naming that Slack identity.
    assert MEMBER_IDENTITY in str(excinfo.value)
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(store, before)


async def test_multiple_faults_are_reported_together() -> None:
    """Scenario: Multiple faults are reported together.

    WHEN a person is created with an empty display name and a
    whitespace-padded Slack identity
    THEN the write is rejected reporting both faults at once, and
    nothing is persisted.

    "Both at once" is asserted structurally — the rejection carries two
    or more faults, and one of them mentions the padded identity — so an
    implementation that stopped at the first fault fails. DERIVED: which
    words a fault uses; the delta fixes that each fault names the
    offending entry, not its wording.
    """
    store = await _roster_with_an_admin()
    before = _snapshot(store)
    padded = f"  {NEWCOMER_IDENTITY}  "

    with pytest.raises(REFUSED) as excinfo:
        await _create(store, display_name="", slack_identity=padded)

    faults = _faults(excinfo.value)
    # SPECIFIED: every fault at once, not the first one only.
    assert len(faults) >= 2, (
        f"the rejection reported one fault where the entry carries two: {faults!r}"
    )
    # SPECIFIED: the faults name the offending entry.
    assert any(NEWCOMER_IDENTITY in fault for fault in faults)
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(store, before)


# ---------------------------------------------------------------------------
# Requirement: Every roster write is validated whole and attributed
# ---------------------------------------------------------------------------


async def test_a_landed_write_is_attributed() -> None:
    """Scenario: A landed write is attributed.

    WHEN a person is created by an authenticated admin principal
    THEN the stored entry records that principal as its creator with the
    time of creation.

    The creating principal differs from the one that seeded the admin
    row, so "records that principal" is a per-write decision rather than
    a store-wide constant.
    """
    store = await _roster_with_an_admin()

    await _create(
        store,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
        principal=ANOTHER_PRINCIPAL,
    )
    row = _row_for(store, MEMBER_IDENTITY)

    # SPECIFIED: which principal made the write.
    assert _field(row, _CREATED_BY, "creator attribution") == ANOTHER_PRINCIPAL
    # SPECIFIED: and when. DERIVED: that "when" is a datetime.
    assert isinstance(_field(row, _CREATED_ON, "creation time"), datetime)
    # DERIVED discrimination guard: the seeding write kept its own
    # principal, so the assertion above is not a constant.
    assert _field(_row_for(store, ADMIN_IDENTITY), _CREATED_BY, "creator") == PRINCIPAL


async def test_a_rejected_write_leaves_the_roster_unchanged() -> None:
    """Scenario: A rejected write leaves the roster unchanged.

    WHEN an update would produce an incoherent roster
    THEN the update is rejected with its faults and a subsequent read
    observes the roster exactly as it was.

    The incoherence is an emptied display name — a per-entry rule from
    the first requirement, so this scenario is not a restatement of the
    last-admin floor below. The "subsequent read" is asserted through
    `load()`, the same door the use cases go through.
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    person_id = _id(_row_for(store, MEMBER_IDENTITY))
    before = _snapshot(store)

    with pytest.raises(REFUSED) as excinfo:
        await _update(store, person_id, display_name="")

    # SPECIFIED: rejected with its faults.
    assert _faults(excinfo.value)
    # SPECIFIED: a subsequent read observes the roster exactly as it was.
    _assert_unchanged(store, before)
    rows, version = await store.load()
    assert version == before[1]
    assert _name(_row_by_id(store, person_id)) == MEMBER_NAME
    assert len(rows) == len(before[0])


async def test_a_slack_identity_cannot_be_updated() -> None:
    """Scenario: A Slack identity cannot be updated.

    WHEN an update names a person's Slack identity as a field to change
    THEN the update is refused, explaining that the identity is not
    updatable.

    The refusal must name the field — otherwise nothing tells the caller
    which of the fields they submitted was the unacceptable one. A
    `TypeError` from an unexpected keyword satisfies that reading as
    much as a domain refusal does, which is why both are in `REFUSED`.
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    person_id = _id(_row_for(store, MEMBER_IDENTITY))
    before = _snapshot(store)

    with pytest.raises(REFUSED) as excinfo:
        await _update(store, person_id, slack_identity=NEWCOMER_IDENTITY)

    # SPECIFIED: the refusal explains itself by naming the field.
    assert "slack" in str(excinfo.value).lower()
    # SPECIFIED (from the requirement's "a rejected write SHALL persist
    # nothing"): the identity stands and nothing was written.
    _assert_unchanged(store, before)
    assert _slack(_row_by_id(store, person_id)) == MEMBER_IDENTITY


async def test_a_deactivated_entry_can_be_corrected_in_place() -> None:
    """Scenario: A deactivated entry can be corrected in place.

    WHEN an update changes a deactivated person's display name
    THEN the update lands, is attributed, and the entry remains
    deactivated.

    The "remains deactivated" half is what stops an implementation from
    treating any successful update as a reactivation — the requirement
    reserves active-status changes for deactivate/reactivate, "so those
    transitions always carry their own attribution".
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    person_id = _id(_row_for(store, MEMBER_IDENTITY))
    await _deactivate(store, person_id)

    await _update(
        store, person_id, display_name="Carol Corrected", principal=ANOTHER_PRINCIPAL
    )
    row = _row_by_id(store, person_id)

    # SPECIFIED: the update lands.
    assert _name(row) == "Carol Corrected"
    # SPECIFIED: it is attributed.
    assert _field(row, _UPDATED_BY, "updater attribution") == ANOTHER_PRINCIPAL
    assert isinstance(_field(row, _UPDATED_ON, "update time"), datetime)
    # SPECIFIED: the entry remains deactivated.
    assert _is_active(row) is False


# ---------------------------------------------------------------------------
# Requirement: The roster never loses its last active admin
# ---------------------------------------------------------------------------


async def test_deactivating_the_last_active_admin_is_refused() -> None:
    """Scenario: Deactivating the last active admin is refused.

    WHEN the roster holds exactly one active admin and a write
    deactivates that person
    THEN the write is rejected with a fault explaining the roster would
    be left without an active admin, and nothing is persisted.

    An ordinary active member stands beside the admin, so the refusal is
    about the *admin* floor and not about emptying the roster.
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    admin_id = _id(_row_for(store, ADMIN_IDENTITY))
    before = _snapshot(store)

    with pytest.raises(REFUSED) as excinfo:
        await _deactivate(store, admin_id)

    # SPECIFIED: a fault explaining the roster would be left without an
    # active admin. DERIVED: the marker word "admin" — the delta fixes
    # that the refusal explains itself, not its wording.
    assert "admin" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(store, before)
    assert _is_active(_row_by_id(store, admin_id)) is True


async def test_withdrawing_the_last_active_admins_flag_is_refused() -> None:
    """Scenario: Withdrawing the last active admin's flag is refused.

    WHEN the roster holds exactly one active admin and an update
    withdraws that person's admin flag
    THEN the write is rejected with the same explanation, and nothing is
    persisted.

    "The same explanation" is asserted as the same refusal type carrying
    the same marker as the deactivation refusal above — the strongest
    reading available without pinning wording the delta does not fix.
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    admin_id = _id(_row_for(store, ADMIN_IDENTITY))
    before = _snapshot(store)

    with pytest.raises(REFUSED) as excinfo:
        await _update(store, admin_id, admin=False)

    # SPECIFIED: rejected with the same explanation.
    assert "admin" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(store, before)
    assert _is_admin(_row_by_id(store, admin_id)) is True


async def test_an_admin_among_admins_can_step_down() -> None:
    """Scenario: An admin among admins can step down.

    WHEN the roster holds two active admins and a write deactivates one
    of them
    THEN the write lands.

    This is what stops the floor from being implemented as "admins are
    undeactivatable". The requirement's second sentence — withdrawing
    the flag while another active admin remains is likewise permitted —
    is asserted alongside it, since the same floor governs both.
    """
    store = await _roster_with_an_admin()
    await _create(
        store,
        display_name="Bob Admin",
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    first_admin_id = _id(_row_for(store, ADMIN_IDENTITY))
    second_admin_id = _id(_row_for(store, SECOND_ADMIN_IDENTITY))

    await _deactivate(store, first_admin_id)

    # SPECIFIED: the write lands.
    assert _is_active(_row_by_id(store, first_admin_id)) is False
    assert _is_active(_row_by_id(store, second_admin_id)) is True

    # SPECIFIED (same requirement, second sentence): withdrawing the
    # flag is permitted while another active admin remains. A third
    # admin is created first, so the withdrawal is not the last one.
    await _create(
        store,
        display_name="Dave Admin",
        slack_identity=NEWCOMER_IDENTITY,
        admin=True,
    )
    await _update(store, second_admin_id, admin=False)
    assert _is_admin(_row_by_id(store, second_admin_id)) is False


# ---------------------------------------------------------------------------
# Requirement: A person is deactivated, never deleted
# ---------------------------------------------------------------------------


async def test_a_deactivated_person_remains_on_the_roster() -> None:
    """Scenario: A deactivated person remains on the roster.

    WHEN a person is deactivated
    THEN the entry is still readable with its history, records who
    deactivated it and when, and no longer resolves to any access.

    The last clause is `access-scope`'s "a deactivated member sees
    nothing" observed from this side; `test_roster_scope_resolution.py`
    covers it as its own scenario. Asserting it here too is what ties
    *this* write to that resolution.
    """
    store = await _roster_with_an_admin()
    await _create(
        store,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
        principal=ANOTHER_PRINCIPAL,
    )
    person_id = _id(_row_for(store, MEMBER_IDENTITY))
    row_count = len(store.rows)

    await _deactivate(store, person_id)
    row = _row_by_id(store, person_id)

    # SPECIFIED: the entry is still readable — deactivation is not
    # deletion.
    assert len(store.rows) == row_count
    assert _slack(row) == MEMBER_IDENTITY
    assert _name(row) == MEMBER_NAME
    # SPECIFIED: with its history intact.
    assert _field(row, _CREATED_BY, "creator attribution") == ANOTHER_PRINCIPAL
    # SPECIFIED: records who deactivated it and when.
    assert _field(row, _DEACTIVATED_BY, "deactivator attribution") == PRINCIPAL
    assert isinstance(_field(row, _DEACTIVATED_ON, "deactivation time"), datetime)
    # SPECIFIED: and no longer resolves to any access.
    scope = await resolve_scope(store, identity=MEMBER_IDENTITY)
    assert scope.permits(ProductId("11111111-1111-1111-1111-111111111111")) is False


async def test_reactivation_restores_the_same_entry() -> None:
    """Scenario: Reactivation restores the same entry.

    WHEN a deactivated person is reactivated
    THEN the same identifier resolves again, and the entry records who
    reactivated it and when.

    "The same identifier" is the point: a reactivation that recreated
    the person under a fresh identifier would break every step assignee
    pointing at the old one (`design.md` Decision 2).
    """
    store = await _roster_with_an_admin()
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    person_id = _id(_row_for(store, MEMBER_IDENTITY))
    await _deactivate(store, person_id)

    await _reactivate(store, person_id, principal=ANOTHER_PRINCIPAL)
    row = _row_by_id(store, person_id)

    # SPECIFIED: the same identifier resolves again.
    assert _is_active(row) is True
    assert _slack(row) == MEMBER_IDENTITY
    assert len([r for r in store.rows if _slack(r) == MEMBER_IDENTITY]) == 1
    # SPECIFIED: records who reactivated it and when.
    assert _field(row, _REACTIVATED_BY, "reactivator attribution") == (
        ANOTHER_PRINCIPAL
    )
    assert isinstance(_field(row, _REACTIVATED_ON, "reactivation time"), datetime)
    # SPECIFIED: the entry resolves to access again.
    scope = await resolve_scope(store, identity=MEMBER_IDENTITY)
    assert scope.permits(ProductId("22222222-2222-2222-2222-222222222222")) is True


def test_the_roster_offers_no_deletion() -> None:
    """Requirement text: "The roster SHALL offer no deletion." — no
    scenario states it, so this is the requirement's own sentence
    asserted structurally.

    DERIVED mechanism: the public application surface exports no
    delete/remove/purge verb for a person. A deletion reachable only
    through the store adapter would not be caught here; that bound is
    recorded in the manifest.
    """
    exported = tuple(getattr(access_application, "__all__", ()))
    assert exported, "the access application surface declares no __all__"

    offending = [
        name
        for name in exported
        if any(verb in name.lower() for verb in ("delete", "remove", "purge"))
    ]
    # SPECIFIED: no deletion is offered.
    assert offending == [], (
        f"the roster's public surface offers deletion verbs {offending!r}; "
        "people are deactivated, never deleted"
    )
