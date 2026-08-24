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
from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.access.application import (
    exchange_link_token,
    mint_admin_link,
    verify_admin_session,
)
from commerce_ops.access.infrastructure.driven.principals_loader import (
    load_principals,
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


def _directory(tmp_path: Path, body: str) -> Any:
    path = tmp_path / "principals.yaml"
    path.write_text(f"principals:\n{body}", encoding="utf-8")
    return load_principals(path)


def _directory_with_admin(tmp_path: Path) -> Any:
    return _directory(
        tmp_path,
        f"""\
  - identity: {ADMIN_IDENTITY}
    skus: []
    admin: true
  - identity: {VISIBILITY_ONLY_IDENTITY}
    all_products: true
""",
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
# Requirement: An admin-capable principal can request an admin link
# ---------------------------------------------------------------------------


async def test_minting_for_an_admin_capable_principal_binds_a_short_lived_token(
    tmp_path: Path,
) -> None:
    """Scenario: An admin-capable principal receives a link — the
    minting half.

    WHEN a link is minted for an identity that resolves admin-capable
    THEN the answer is a link carrying a token
    AND the stored token is bound to that principal
    AND it expires no more than ten minutes after minting.

    The ephemeral-only reply is the Slack handler's half, recorded as
    uncovered in the manifest.
    """
    tokens = _FakeLinkTokens()

    link = await _mint(_directory_with_admin(tmp_path), tokens, ADMIN_IDENTITY)

    assert isinstance(link, str) and link, "minting answered no link"
    _token_of(link)  # the link carries a token at all
    # SPECIFIED: the token is bound to the verified principal.
    assert len(tokens.rows) == 1
    (row,) = tokens.rows.values()
    assert row["principal"] == ADMIN_IDENTITY
    # SPECIFIED: expiry no more than ten minutes after minting.
    assert row["expires_at"] <= T0 + TEN_MINUTES
    assert row["expires_at"] > T0


async def test_a_visibility_only_caller_is_refused_exactly_like_an_unknown_one(
    tmp_path: Path,
) -> None:
    """Scenarios: A visibility-only principal is refused like an unknown
    one / An unknown caller's refusal confirms nothing — the minting
    halves.

    WHEN a link is requested for a known identity without the admin
    declaration, and for an identity the directory does not know
    THEN both are refused with one and the same outcome
    AND nothing is minted for either.

    The refusal outcome is `None` for both, so a handler rendering the
    refusal *cannot* distinguish the two caller kinds, and no URL exists
    to leak — the use-case-level substance of "one and the same
    ephemeral refusal, with no admin URL". The message-wording half is
    the handler's, recorded as uncovered in the manifest.
    """
    directory = _directory_with_admin(tmp_path)
    tokens = _FakeLinkTokens()

    visibility_only = await _mint(directory, tokens, VISIBILITY_ONLY_IDENTITY)
    unknown = await _mint(directory, tokens, STRANGER_IDENTITY)

    # SPECIFIED: refused — membership and visibility grants do not
    # suffice — and both refusals are one and the same outcome.
    assert visibility_only is None
    assert unknown is None
    assert visibility_only == unknown
    # SPECIFIED: no token exists for either caller; a refusal mints
    # nothing that could later be exchanged.
    assert tokens.rows == {}


# ---------------------------------------------------------------------------
# Requirement: A link token is single-use and short-lived
# ---------------------------------------------------------------------------


async def test_a_token_exchanges_once_for_a_bounded_session(tmp_path: Path) -> None:
    """Scenario: A token exchanges once.

    WHEN a freshly minted, unexpired token is opened
    THEN the response establishes a browser session for the token's
    principal — verified end-to-end: the session the exchange answers
    verifies back to the identity the link was minted for
    AND (requirement *A browser session is bounded ...*) the stored
    session expires no more than twelve hours after it was established.
    """
    directory = _directory_with_admin(tmp_path)
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


async def test_a_spent_token_is_refused_like_one_that_never_existed(
    tmp_path: Path,
) -> None:
    """Scenario: A spent token is refused like nothing — the exchange
    half.

    WHEN the same token is opened a second time
    THEN the exchange refuses it with the same outcome as a token the
    system never minted, and establishes no second session.

    The response-shape half ("identical in shape to requesting a route
    that does not exist") is route-level, in
    `test_admin_link_exchange_route.py`.
    """
    directory = _directory_with_admin(tmp_path)
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


async def test_an_expired_token_is_refused_identically(tmp_path: Path) -> None:
    """Scenario: An expired token is refused identically.

    WHEN a token is opened after its expiry
    THEN the exchange refuses it with the same outcome as the spent and
    never-minted cases, and establishes no session.
    """
    directory = _directory_with_admin(tmp_path)
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


async def test_a_session_outlives_its_lifetime_and_stops_working(
    tmp_path: Path,
) -> None:
    """Scenario: A session outlives its usefulness and stops working —
    the verification half.

    WHEN a session older than its lifetime is verified
    THEN verification refuses it with the same outcome as a session that
    never existed — "refused exactly as if no session were presented".

    The response-shape half is in `test_playbook_admin_page.py`.
    """
    directory = _directory_with_admin(tmp_path)
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


async def test_removal_from_the_directory_revokes_on_the_next_request(
    tmp_path: Path,
) -> None:
    """Scenario: Removal from the directory revokes access on the next
    request — the verification half.

    WHEN a principal's entry is removed from the principals directory
    while their session is still unexpired, and the session is then
    verified
    THEN verification refuses it.

    The directory is re-read per request (`design.md` Decision 5's
    request-time revocation), modeled here as verification against the
    edited directory the next request would load.
    """
    before = _directory_with_admin(tmp_path)
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(before, tokens, ADMIN_IDENTITY)
    assert link is not None
    session_id = await _exchange(tokens, sessions, _token_of(link), now=T0 + A_TICK)
    assert session_id is not None

    edited = _directory(
        tmp_path,
        f"""\
  - identity: {VISIBILITY_ONLY_IDENTITY}
    all_products: true
""",
    )

    # SPECIFIED: the unexpired session no longer verifies once the
    # principal has left the directory.
    assert await _verify(edited, sessions, session_id, now=T0 + 2 * A_TICK) is None


async def test_withdrawing_the_admin_declaration_revokes_likewise(
    tmp_path: Path,
) -> None:
    """Scenario: Withdrawing the admin declaration revokes access
    likewise — the verification half.

    WHEN a principal's entry loses its admin declaration while their
    session is still unexpired, and the session is then verified
    THEN verification refuses it — the entry remains in the directory,
    so this discriminates re-resolving *admin capability* from merely
    re-checking membership.
    """
    before = _directory_with_admin(tmp_path)
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    link = await _mint(before, tokens, ADMIN_IDENTITY)
    assert link is not None
    session_id = await _exchange(tokens, sessions, _token_of(link), now=T0 + A_TICK)
    assert session_id is not None

    declaration_withdrawn = _directory(
        tmp_path,
        f"""\
  - identity: {ADMIN_IDENTITY}
    skus: []
""",
    )

    # SPECIFIED: still a directory member, no longer admin-capable, no
    # longer verified.
    assert (
        await _verify(declaration_withdrawn, sessions, session_id, now=T0 + 2 * A_TICK)
        is None
    )
