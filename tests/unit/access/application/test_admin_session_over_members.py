"""The admin-session use cases resolving against the membership
(`admin-session`, both MODIFIED requirements).

Derived strictly from the delta spec:
`openspec/changes/move-principals-to-roster/specs/admin-session/spec.md`

- *An admin-capable principal can request an admin link from Slack* —
  its three scenarios' use-case halves.
- *Admin access fails closed and absence-shaped* — the two membership-side
  revocation scenarios (*Removal from the directory revokes access on
  the next request*, *Withdrawing the admin declaration revokes access
  likewise*). Its first scenario (*No session means no surface*) is a
  response-shape claim about an admin route, and is covered over the
  Team page in `tests/unit/access/infrastructure/driving/
  test_members_admin_page.py`.

The ephemeral-delivery halves ("visible only to them", "does not confirm
that an admin surface exists") are the Slack handler's, and no adapter
test exists for that handler; they are recorded as uncovered in
`test-manifest.md` with that reason — unchanged from how the previous
pass recorded them.

This file replaces nothing: `test_admin_session_use_cases.py` still
stands, and this pass never edits it. The manifest records its
directory-built halves as obsolete-test candidates.

## What is fixed, and what is INVENTED

Fixed by the artifacts: `resolve_admin_capability` becomes async against
the membership and its callers are updated (`tasks.md` 2.3); minting
verifies admin capability before it mints; deactivation is the membership's
form of removal; a token binds the verified principal and expires no
more than ten minutes after minting (delta text).

INVENTED, recorded in the manifest:

- That `mint_admin_link` and `verify_admin_session` take the members
  store where they took the loaded directory, in the same first
  position. Correction points: `_mint`, `_verify`.
- The token/session store protocols, carried over verbatim from
  `test_admin_session_use_cases.py` (`_FakeLinkTokens`,
  `_FakeAdminSessions`) — this change touches neither.
- The store double and write call shapes, as `test_members_writes.py`
  records; the files correct together. Repeated rather than shared
  because this pass may write only files matching `tests/**/test_*.py`.

Deliberately *not* pinned: whether the principal a token binds is the
Slack identity or the generated member id. The delta fixes only that it
is "the verified principal", so every assertion here round-trips
mint → exchange → verify rather than comparing against a literal.

## Expected first-run state

The membership use cases do not exist, so every test here is expected to
fail on an absent target (`ImportError`) — which establishes only
absence.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from commerce_ops.access.application import (
    create_member,
    deactivate_member,
    exchange_link_token,
    mint_admin_link,
    update_member,
    verify_admin_session,
)
from tests.support._paired import paired as _paired
from tests.support.admin import ADMIN_IDENTITY
from tests.support.fakes import FakeMembersStore as _MembersStoreShared
from tests.support.fixtures import PRINCIPAL

pytestmark = pytest.mark.anyio

SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
STRANGER_IDENTITY: Final = "U99STRANGER"

BASE_URL: Final = "http://testserver"

T0: Final = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
TEN_MINUTES: Final = timedelta(minutes=10)
A_TICK: Final = timedelta(seconds=1)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Store doubles (members: see test_members_writes.py; tokens and sessions:
# carried over from test_admin_session_use_cases.py unchanged)
# ---------------------------------------------------------------------------


@_paired(
    _MembersStoreShared,
    build=lambda rows=(), version=11: _MembersStoreShared(rows, version),
)
class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 11) -> None:
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


class _FakeLinkTokens:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def save(
        self, *, token_hash: str, principal: str, expires_at: datetime
    ) -> None:
        self.rows[token_hash] = {
            "principal": principal,
            "expires_at": expires_at,
            "spent": False,
        }

    async def claim(self, token_hash: str, *, now: datetime) -> str | None:
        row = self.rows.get(token_hash)
        if row is None or row["spent"] or now >= row["expires_at"]:
            return None
        row["spent"] = True
        principal: str = row["principal"]
        return principal


class _FakeAdminSessions:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def save(
        self, *, session_hash: str, principal: str, expires_at: datetime
    ) -> None:
        self.rows[session_hash] = {"principal": principal, "expires_at": expires_at}

    async def find(self, session_hash: str, *, now: datetime) -> str | None:
        row = self.rows.get(session_hash)
        if row is None or now >= row["expires_at"]:
            return None
        principal: str = row["principal"]
        return principal


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


async def _mint(
    members: Any,
    tokens: _FakeLinkTokens,
    identity: str,
    *,
    now: datetime = T0,
) -> str | None:
    return await mint_admin_link(
        members, tokens, identity=identity, base_url=BASE_URL, now=now
    )


async def _exchange(
    tokens: _FakeLinkTokens,
    sessions: _FakeAdminSessions,
    token: str,
    *,
    now: datetime = T0,
) -> str | None:
    return await exchange_link_token(tokens, sessions, token=token, now=now)


async def _verify(
    members: Any,
    sessions: _FakeAdminSessions,
    session_id: str,
    *,
    now: datetime,
) -> str | None:
    return await verify_admin_session(members, sessions, session_id=session_id, now=now)


def _token_of(link: str) -> str:
    """The raw token as it rides the minted link (the reading
    `test_admin_session_use_cases.py` records)."""
    tail = link.rsplit("=", 1)[-1] if "=" in link else link.rsplit("/", 1)[-1]
    assert tail and tail != link, f"no token found riding the link {link!r}"
    return tail


async def _members() -> _FakeMembersStore:
    """Two active admins — the second keeps the last-admin floor from
    blocking a deactivation — plus one active member with no admin
    declaration."""
    store = _FakeMembersStore()
    await _create(
        store,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create(
        store,
        display_name="Bob Admin",
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    await _create(store, display_name="Carol Member", slack_identity=MEMBER_IDENTITY)
    return store


async def _session_for(
    store: _FakeMembersStore,
    identity: str,
) -> tuple[_FakeAdminSessions, str]:
    """A live admin session, established the way a real one is: mint,
    exchange, and hold the session id."""
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(store, tokens, identity)
    assert isinstance(link, str) and link, "minting answered no link"
    session_id = await _exchange(tokens, sessions, _token_of(link))
    assert isinstance(session_id, str) and session_id, "the token did not exchange"
    return sessions, session_id


# ---------------------------------------------------------------------------
# Requirement: An admin-capable principal can request an admin link
# ---------------------------------------------------------------------------


async def test_an_admin_capable_principal_receives_a_link() -> None:
    """Scenario: An admin-capable principal receives a link — the
    minting half.

    WHEN a Slack user who resolves admin-capable against the membership
    invokes the command
    THEN they receive a reply carrying a link with a token bound to
    their principal identity.

    The token's binding is asserted by round-trip rather than against a
    literal: the minted token exchanges into a session that verifies,
    which is what "bound to the verified principal" buys the caller.
    Whether that principal is spelled as the Slack identity or the
    generated member id is deliberately not pinned.

    The requirement's expiry clause is asserted alongside, since the
    delta re-states it and no scenario of its own carries it.

    The "visible only to them" half is the Slack handler's, recorded as
    uncovered in the manifest.
    """
    store = await _members()
    tokens = _FakeLinkTokens()

    link = await _mint(store, tokens, ADMIN_IDENTITY)

    # SPECIFIED: a link carrying a token.
    assert isinstance(link, str) and link, "minting answered no link"
    _token_of(link)
    # SPECIFIED: bound to the verified principal — one token, and it
    # exchanges into a session that verifies as an admin.
    assert len(tokens.rows) == 1
    (row,) = tokens.rows.values()
    assert row["principal"], "the token binds no principal"
    # SPECIFIED: expires no more than ten minutes after minting.
    assert row["expires_at"] <= T0 + TEN_MINUTES
    assert row["expires_at"] > T0

    sessions = _FakeAdminSessions()
    session_id = await _exchange(tokens, sessions, _token_of(link))
    assert isinstance(session_id, str) and session_id
    assert await _verify(store, sessions, session_id, now=T0 + A_TICK)


async def test_a_visibility_only_principal_is_refused_like_an_unknown_one() -> None:
    """Scenarios: A visibility-only principal is refused like an unknown
    one / An unknown caller's refusal confirms nothing — the minting
    halves.

    WHEN an active member without the admin declaration invokes
    the command, and when a Slack user the membership does not know invokes
    it
    THEN both receive one and the same refusal, carrying no admin URL.

    The refusal outcome is the same value for both, so a handler
    rendering it cannot distinguish the two caller kinds, and no URL
    exists to leak — the use-case substance of "one and the same
    ephemeral refusal ... does not confirm that an admin surface
    exists". The message-wording half is the handler's, recorded as
    uncovered in the manifest.
    """
    store = await _members()
    tokens = _FakeLinkTokens()

    member = await _mint(store, tokens, MEMBER_IDENTITY)
    unknown = await _mint(store, tokens, STRANGER_IDENTITY)

    # SPECIFIED: active membership alone does not suffice, and
    # both refusals are one and the same outcome.
    assert member is None
    assert unknown is None
    assert member == unknown
    # SPECIFIED: nothing is minted that could later be exchanged.
    assert tokens.rows == {}
    # DERIVED discrimination guard: the same call mints for an admin, so
    # the refusals above are not a dead code path.
    assert await _mint(store, tokens, ADMIN_IDENTITY) is not None


async def test_a_deactivated_admin_is_refused_a_link() -> None:
    """DERIVED, from the requirement's re-stated refusal clause: "A
    caller who does not resolve admin-capable — whether unknown to the
    members, deactivated, or an active member without the admin
    declaration — SHALL receive one and the same ephemeral refusal".

    The deactivated case has no scenario of its own; it is new in this
    delta (the YAML directory had no deactivation), so it is asserted
    here against the same refusal value the other two produce.
    """
    store = await _members()
    await deactivate_member(
        members=store, principal=PRINCIPAL, member_id=_id_of(store, ADMIN_IDENTITY)
    )
    tokens = _FakeLinkTokens()

    deactivated = await _mint(store, tokens, ADMIN_IDENTITY)
    unknown = await _mint(store, tokens, STRANGER_IDENTITY)

    # SPECIFIED (requirement text): one and the same refusal.
    assert deactivated is None
    assert deactivated == unknown
    assert tokens.rows == {}


# ---------------------------------------------------------------------------
# Requirement: Admin access fails closed and absence-shaped
# ---------------------------------------------------------------------------


async def test_deactivation_revokes_access_on_the_next_request() -> None:
    """Scenario: Removal from the directory revokes access on the next
    request — the verification half.

    WHEN a principal's members entry is deactivated while their session
    is still unexpired, and they then request an admin route
    THEN the request is refused.

    The session verifies immediately before the deactivation, so the
    refusal afterwards is the membership read at work and not an expiry, a
    bad session id, or a store that never verified anything. The
    absence-*shape* of the response is the route's half, asserted in
    `test_members_admin_page.py`.
    """
    store = await _members()
    sessions, session_id = await _session_for(store, ADMIN_IDENTITY)
    assert await _verify(store, sessions, session_id, now=T0 + A_TICK)

    await deactivate_member(
        members=store, principal=PRINCIPAL, member_id=_id_of(store, ADMIN_IDENTITY)
    )

    # SPECIFIED: the still-unexpired session no longer verifies.
    assert await _verify(store, sessions, session_id, now=T0 + 2 * A_TICK) is None


async def test_withdrawing_the_admin_declaration_revokes_likewise() -> None:
    """Scenario: Withdrawing the admin declaration revokes access
    likewise — the verification half.

    WHEN a principal's members entry loses its admin declaration while
    their session is still unexpired, and they then request an admin
    route
    THEN the request is refused.

    The entry stays *active* here: this is the declaration's half, kept
    distinct from the deactivation scenario above. A second admin
    remains, so the withdrawal is permitted by the last-admin floor.
    """
    store = await _members()
    sessions, session_id = await _session_for(store, ADMIN_IDENTITY)
    assert await _verify(store, sessions, session_id, now=T0 + A_TICK)

    await update_member(
        members=store,
        principal=PRINCIPAL,
        member_id=_id_of(store, ADMIN_IDENTITY),
        admin=False,
    )

    # SPECIFIED: the still-unexpired session no longer verifies.
    assert await _verify(store, sessions, session_id, now=T0 + 2 * A_TICK) is None
    # DERIVED discrimination guard: the other admin's session is
    # unaffected, so the refusal is per-principal.
    other_sessions, other_id = await _session_for(store, SECOND_ADMIN_IDENTITY)
    assert await _verify(store, other_sessions, other_id, now=T0 + 2 * A_TICK)
