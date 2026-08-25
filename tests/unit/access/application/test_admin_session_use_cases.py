"""The Slack-to-browser bridge's use cases (`admin-session`).

Derived strictly from the delta spec:
`openspec/changes/add-playbook-admin-ui/specs/admin-session/spec.md`

Covers, at the use-case level, the logic halves of every requirement:

- *An admin-capable principal can request an admin link from Slack* —
  the minting halves of all three scenarios: who gets a token, whom it
  is bound to, its expiry bound, and that both non-admin caller kinds
  are refused identically with nothing minted. The Slack-presentation
  halves (the reply being ephemeral, the refusal message's wording
  carrying no URL) are recorded as uncovered in the manifest: no
  artifact names the command's registration module or handler seam, and
  the identical-`None` refusal here makes the handler *unable* to
  distinguish the two caller kinds.
- *A link token is single-use and short-lived* — all three scenarios'
  exchange outcomes; the HTTP absence-shape halves live in
  `tests/unit/access/infrastructure/test_admin_link_exchange_route.py`.
- *A browser session is bounded and rides a hardened cookie* — the
  bounded-session scenario; the cookie scenario is route-level, in the
  same route file.
- *Admin access fails closed and absence-shaped* — the verification
  halves: expiry, directory removal, declaration withdrawal, unknown
  session. The response-shape halves live in
  `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`.

## What is fixed, and what is INVENTED

Fixed by the artifacts, not invented: three use cases —
`mint_admin_link`, `exchange_link_token`, `verify_admin_session` — on
the access module's public application surface, behind `LinkTokenStore`
/ `AdminSessionStore` ports (`design.md` Decision 6, `tasks.md` 2.3);
tokens single-use, expiring ≤10 minutes; sessions expiring ≤12 hours;
verification re-resolving the principal against the directory on every
request (`design.md` Decision 5).

INVENTED, recorded in the manifest as unresolved project questions,
correction points named:

- Call shapes, ports-first like `resolve_scope(directory, resolver,
  identity=)`:
  `mint_admin_link(directory, tokens, identity=, base_url=, now=)`
  answering the full link URL or `None`;
  `exchange_link_token(tokens, sessions, token=, now=)` answering the
  session identifier or `None`;
  `verify_admin_session(directory, sessions, session_id=, now=)`
  answering the principal or `None`. Correction points: `_mint`,
  `_exchange`, `_verify` below. `now=` is the injected clock — if the
  implementation reads a real clock internally, these fixtures need a
  patch point instead; recorded as a question.
- The store protocols the fakes implement:
  `LinkTokenStore.save(token_hash=, principal=, expires_at=)` /
  `.claim(token_hash, now=) -> principal | None` (claim atomically
  spends);
  `AdminSessionStore.save(session_hash=, principal=, expires_at=)` /
  `.find(session_hash, now=) -> principal | None`. Correction points:
  the fake classes. Hashing lives inside the use cases; these tests
  never compute a hash, they only round-trip values through the same
  stores.
- How the raw token rides the minted link: taken as the text after the
  link's last `=` (query parameter) or `/` (path segment) — `_token_of`
  below is the correction point.
- The directory the use cases consult is a loaded principals directory
  with the `admin: true` entry spelling
  `test_admin_capability.py` records; both files correct together.

## Expected first-run state

`commerce_ops.access.application` exports none of the three use cases,
so every test fails at import — the absent-target state; the assertions
have not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest

from commerce_ops.access.application import (
    Person,
    PersonRecord,
    exchange_link_token,
    mint_admin_link,
    verify_admin_session,
)

pytestmark = pytest.mark.anyio

ADMIN_IDENTITY: Final = "U01ALICE"
VISIBILITY_ONLY_IDENTITY: Final = "U02BOB"
STRANGER_IDENTITY: Final = "U99STRANGER"

BASE_URL: Final = "http://testserver"

T0: Final = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)

TEN_MINUTES: Final = timedelta(minutes=10)
TWELVE_HOURS: Final = timedelta(hours=12)
A_TICK: Final = timedelta(seconds=1)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Directory fixtures (through the loader, like test_resolve_scope.py)
# ---------------------------------------------------------------------------


class _FakeRosterStore:
    """The roster these tests mint and verify against.

    Adapted from a YAML directory by `move-principals-to-roster`: the
    requirements exercised below — single-use tokens and bounded
    sessions — are untouched by that change, only the collaborator they
    read admin capability from moved.
    """

    def __init__(self, people: tuple[Person, ...]) -> None:
        self.rows = tuple(PersonRecord(person=person) for person in people)

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, 1

    async def save(self, rows: Any, *, expected_version: int) -> None:
        raise AssertionError("these tests never write to the roster")


def _roster_with_admin() -> _FakeRosterStore:
    return _FakeRosterStore(
        (
            Person(
                identifier="person-admin",
                display_name="Alice Admin",
                slack_identity=ADMIN_IDENTITY,
                admin=True,
            ),
            Person(
                identifier="person-member",
                display_name="Bob Member",
                slack_identity=VISIBILITY_ONLY_IDENTITY,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Store fakes (INVENTED protocols — see the module docstring)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Use-case call shapes: the single correction points
# ---------------------------------------------------------------------------


async def _mint(
    directory: Any,
    tokens: _FakeLinkTokens,
    identity: str,
    *,
    now: datetime = T0,
) -> str | None:
    return await mint_admin_link(
        directory, tokens, identity=identity, base_url=BASE_URL, now=now
    )


async def _exchange(
    tokens: _FakeLinkTokens,
    sessions: _FakeAdminSessions,
    token: str,
    *,
    now: datetime,
) -> str | None:
    return await exchange_link_token(tokens, sessions, token=token, now=now)


async def _verify(
    directory: Any,
    sessions: _FakeAdminSessions,
    session_id: str,
    *,
    now: datetime,
) -> str | None:
    return await verify_admin_session(
        directory, sessions, session_id=session_id, now=now
    )


def _token_of(link: str) -> str:
    """The raw token as it rides the minted link (see the docstring)."""
    tail = link.rsplit("=", 1)[-1] if "=" in link else link.rsplit("/", 1)[-1]
    assert tail and tail != link, f"no token found riding the link {link!r}"
    return tail


# ---------------------------------------------------------------------------
# Requirement: A link token is single-use and short-lived
# ---------------------------------------------------------------------------


async def test_a_token_exchanges_once_for_a_bounded_session() -> None:
    """Scenario: A token exchanges once.

    WHEN a freshly minted, unexpired token is opened
    THEN the response establishes a browser session for the token's
    principal — verified end-to-end: the session the exchange answers
    verifies back to the identity the link was minted for
    AND (requirement *A browser session is bounded ...*) the stored
    session expires no more than twelve hours after it was established.
    """
    directory = _roster_with_admin()
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(directory, tokens, ADMIN_IDENTITY)
    assert link is not None

    session_id = await _exchange(tokens, sessions, _token_of(link), now=T0 + A_TICK)

    # SPECIFIED: a session for the token's principal.
    assert isinstance(session_id, str) and session_id
    principal = await _verify(directory, sessions, session_id, now=T0 + 2 * A_TICK)
    assert principal == ADMIN_IDENTITY
    # SPECIFIED: bounded — no more than twelve hours.
    assert len(sessions.rows) == 1
    (row,) = sessions.rows.values()
    assert row["expires_at"] <= (T0 + A_TICK) + TWELVE_HOURS


async def test_a_spent_token_is_refused_like_one_that_never_existed() -> None:
    """Scenario: A spent token is refused like nothing — the exchange
    half.

    WHEN the same token is opened a second time
    THEN the exchange refuses it with the same outcome as a token the
    system never minted, and establishes no second session.

    The response-shape half ("identical in shape to requesting a route
    that does not exist") is route-level, in
    `test_admin_link_exchange_route.py`.
    """
    directory = _roster_with_admin()
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(directory, tokens, ADMIN_IDENTITY)
    assert link is not None
    token = _token_of(link)
    assert await _exchange(tokens, sessions, token, now=T0 + A_TICK) is not None
    sessions_after_first = dict(sessions.rows)

    second_use = await _exchange(tokens, sessions, token, now=T0 + 2 * A_TICK)
    never_minted = await _exchange(
        tokens, sessions, "token-the-system-never-minted", now=T0 + 2 * A_TICK
    )

    # SPECIFIED: refused, indistinguishably from a token that never
    # existed, with no session established by either attempt.
    assert second_use is None
    assert second_use == never_minted
    assert sessions.rows == sessions_after_first


async def test_an_expired_token_is_refused_identically() -> None:
    """Scenario: An expired token is refused identically.

    WHEN a token is opened after its expiry
    THEN the exchange refuses it with the same outcome as the spent and
    never-minted cases, and establishes no session.
    """
    directory = _roster_with_admin()
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(directory, tokens, ADMIN_IDENTITY)
    assert link is not None

    expired = await _exchange(
        tokens, sessions, _token_of(link), now=T0 + TEN_MINUTES + A_TICK
    )

    # SPECIFIED: refused past the ten-minute bound, identically.
    assert expired is None
    assert sessions.rows == {}


# ---------------------------------------------------------------------------
# Requirement: A browser session is bounded and rides a hardened cookie
# (the bounded half; the cookie is route-level)
# ---------------------------------------------------------------------------


async def test_a_session_outlives_its_lifetime_and_stops_working() -> None:
    """Scenario: A session outlives its usefulness and stops working —
    the verification half.

    WHEN a session older than its lifetime is verified
    THEN verification refuses it with the same outcome as a session that
    never existed — "refused exactly as if no session were presented".

    The response-shape half is in `test_playbook_admin_page.py`.
    """
    directory = _roster_with_admin()
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(directory, tokens, ADMIN_IDENTITY)
    assert link is not None
    session_id = await _exchange(tokens, sessions, _token_of(link), now=T0 + A_TICK)
    assert session_id is not None

    outlived = await _verify(
        directory, sessions, session_id, now=T0 + A_TICK + TWELVE_HOURS + A_TICK
    )
    unknown = await _verify(
        directory, sessions, "session-that-never-existed", now=T0 + 2 * A_TICK
    )

    # SPECIFIED: refused exactly as an absent session is.
    assert outlived is None
    assert outlived == unknown


# ---------------------------------------------------------------------------
# Requirement: Admin access fails closed and absence-shaped
# (the verification halves; the response shape is page-level)
# ---------------------------------------------------------------------------
