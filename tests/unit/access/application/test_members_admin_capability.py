"""Resolving admin capability from the membership (`access-scope`).

Derived strictly from the delta spec:
`openspec/changes/move-principals-to-roster/specs/access-scope/spec.md`,
the ADDED requirement *Admin capability resolves from the membership* — all
five scenarios.

This file replaces nothing: `tests/unit/access/application/
test_admin_capability.py` still stands, and this pass never edits it.
The manifest records it as an obsolete-test candidate, since the
directory-file declaration it resolves against is REMOVED by this
change.

## Why the application level

Each scenario is stated about what *resolution* answers, and resolution
is `resolve_admin_capability` over one collaborator — the members store,
supplied here as a double. No Postgres, no I/O.

## The interface under test does not exist yet

Fixed by the artifacts, not invented: `resolve_admin_capability` becomes
async and reads the membership, fail-closed for unknown, deactivated and
non-admin entries (`tasks.md` 2.3); the admin declaration is orthogonal
to membership, and no membership confers it.

INVENTED, recorded in the manifest: the call shape
`resolve_admin_capability(members, identity=...)`, async. Correction
point: `_resolves_admin`. The store double, row accessors and write call
shapes are the ones `test_members_writes.py` records; the files correct
together, and are repeated rather than shared because this pass may
write only files matching `tests/**/test_*.py`.

## Expected first-run state

The membership use cases do not exist, so every test here is expected to
fail on an absent target (`ImportError`) — which establishes only
absence.

NOTE for the implementation step: the four `False` assertions could pass
vacuously against a resolution that always answers `False`; the
`True` assertion in the first test is the discriminating one, and every
`False` test below re-asserts it alongside for exactly that reason.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25).
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.access.application import (
    create_member,
    deactivate_member,
    resolve_admin_capability,
)
from tests.support._paired import paired as _paired
from tests.support.admin import ADMIN_IDENTITY
from tests.support.fakes import FakeMembersStore as _MembersStoreShared
from tests.support.fixtures import PRINCIPAL

pytestmark = pytest.mark.anyio

SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
STRANGER_IDENTITY: Final = "U99STRANGER"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Store doubles and row accessors (see test_members_writes.py)
# ---------------------------------------------------------------------------


@_paired(
    _MembersStoreShared,
    build=lambda rows=(), version=5: _MembersStoreShared(rows, version),
)
class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 5) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self.version
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


class _UnreadableMembersStore(_FakeMembersStore):
    async def load(self) -> tuple[tuple[Any, ...], int]:
        raise ConnectionError("could not connect to the members store")


_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None:
            found.append(nested)
    return tuple(found)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored membership row exposes no {what} under any of {names} — "
        "correct this file's accessor names to the implemented row"
    )


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if str(_field(row, _SLACK_NAMES, "Slack identity")) == identity:
            return _field(row, _ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


# ---------------------------------------------------------------------------
# Call shapes: the single correction points
# ---------------------------------------------------------------------------


async def _create(
    store: _FakeMembersStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
) -> Any:
    return await create_member(
        members=store,
        principal=PRINCIPAL,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _resolves_admin(store: Any, identity: str) -> bool:
    """The single correction point for the resolution call shape."""
    answer = await resolve_admin_capability(store, identity=identity)
    assert isinstance(answer, bool), (
        "admin-capability resolution answered something other than a "
        f"boolean: {answer!r} — fail-closed resolution must answer the "
        "question, not defer it"
    )
    return answer


async def _members() -> _FakeMembersStore:
    """One active admin and one active member with no admin declaration."""
    store = _FakeMembersStore()
    await _create(
        store,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create(store, display_name="Carol Member", slack_identity=MEMBER_IDENTITY)
    return store


# ---------------------------------------------------------------------------
# Scenario: A declared entry resolves admin-capable
# ---------------------------------------------------------------------------


async def test_a_declared_entry_resolves_admin_capable() -> None:
    """Scenario: A declared entry resolves admin-capable.

    WHEN admin capability is resolved for an identity whose active
    members entry carries the admin declaration
    THEN the identity resolves as admin-capable.

    This is the file's one discriminating positive: every other test
    asserts `False`, and a resolution stuck on `False` would pass them
    all.
    """
    store = await _members()

    # SPECIFIED: the declaration confers the capability.
    assert await _resolves_admin(store, ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: Membership confers nothing
# ---------------------------------------------------------------------------


async def test_membership_confers_nothing() -> None:
    """Scenario: Membership confers nothing.

    WHEN admin capability is resolved for an identity whose active
    members entry carries no admin declaration
    THEN the identity resolves as not admin-capable.

    The member resolves to the *unrestricted* scope (the delta's other
    ADDED requirement), which is what makes this the strongest reading
    of "no membership of any shape SHALL by itself confer it": the
    widest visibility there is still confers no admin authority.
    """
    store = await _members()

    # SPECIFIED: membership alone confers nothing.
    assert await _resolves_admin(store, MEMBER_IDENTITY) is False
    # DERIVED discrimination guard: the same resolution answers True for
    # the declared entry, so False above is not a constant.
    assert await _resolves_admin(store, ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: A deactivated admin fails closed
# ---------------------------------------------------------------------------


async def test_a_deactivated_admin_fails_closed() -> None:
    """Scenario: A deactivated admin fails closed.

    WHEN admin capability is resolved for an identity whose membership entry
    carries the admin declaration but is deactivated
    THEN the identity resolves as not admin-capable.

    The entry keeps its admin flag through deactivation — the delta
    reserves active-status changes for deactivate/reactivate — so this
    is specifically the *active* half of the check, not a withdrawn
    declaration. A second admin exists so the deactivation is permitted
    by the last-admin floor at all.
    """
    store = await _members()
    await _create(
        store,
        display_name="Bob Admin",
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    assert await _resolves_admin(store, ADMIN_IDENTITY) is True

    await deactivate_member(
        members=store, principal=PRINCIPAL, member_id=_id_of(store, ADMIN_IDENTITY)
    )

    # SPECIFIED: a deactivated entry is not admin-capable.
    assert await _resolves_admin(store, ADMIN_IDENTITY) is False
    # DERIVED discrimination guard: the remaining admin still resolves.
    assert await _resolves_admin(store, SECOND_ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: An unknown identity fails closed
# ---------------------------------------------------------------------------


async def test_an_unknown_identity_fails_closed() -> None:
    """Scenario: An unknown identity fails closed.

    WHEN admin capability is resolved for an identity the membership does
    not know
    THEN the identity resolves as not admin-capable.

    The membership is not empty, so the refusal is the fail-closed rule at
    work. Resolving rather than raising is asserted by reaching the
    assertion at all.
    """
    store = await _members()

    # SPECIFIED: an identity the membership does not know is not admin-capable.
    assert await _resolves_admin(store, STRANGER_IDENTITY) is False
    # DERIVED discrimination guard.
    assert await _resolves_admin(store, ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: An unreachable store fails closed
# ---------------------------------------------------------------------------


async def test_an_unreachable_store_fails_closed() -> None:
    """Scenario: An unreachable store fails closed.

    WHEN admin capability is resolved while the members store cannot be
    read
    THEN the identity resolves as not admin-capable, and the resolution
    succeeds.

    "Succeeds" is asserted by reaching the assertion: a propagating
    `ConnectionError` fails the test. The identity used is one that
    *would* resolve admin-capable against a readable membership, so `False`
    here is the unreadable store's doing.
    """
    store = _UnreadableMembersStore()

    # SPECIFIED: fail-closed, never an error toward the asker.
    assert await _resolves_admin(store, ADMIN_IDENTITY) is False
