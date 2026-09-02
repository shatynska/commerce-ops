"""The token-exchange route: absence-shaped refusals and the hardened
cookie (`admin-session`).

Derived strictly from the delta spec:
`openspec/changes/add-playbook-admin-ui/specs/admin-session/spec.md`

Covers the HTTP halves that
`tests/unit/access/application/test_admin_session_use_cases.py` cannot
observe through the use cases alone:

- *A link token is single-use and short-lived* — the response-shape
  halves of all three scenarios: a refused exchange is "identical in
  shape to requesting a route that does not exist", asserted by
  comparing against the very response this app gives for an
  unregistered route, so the shape cannot drift from FastAPI's own 404
  (`design.md` Decision 7).
- *A browser session is bounded and rides a hardened cookie* — the
  cookie scenario: HttpOnly always, Secure in deployed environments.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the exchange route is an `access` driving
adapter (`design.md` Decision 6, `tasks.md` 2.5); opening the minted
link *is* the exchange, so the link `mint_admin_link` answers with
`base_url="http://testserver"` is requestable directly against a test
app — no route path is transcribed anywhere in this file.

INVENTED, recorded in the manifest, correction points named:

- The module `commerce_ops.access.infrastructure.driving.admin_link`
  exposing `router` (an `APIRouter`) — no artifact names the file.
  Correction point: the import and `_app()` below.
- The route reads its stores off two module-level names, `link_tokens`
  and `admin_sessions`, substituted here with `monkeypatch.setattr` at
  its default `raising=True` so a differently-named collaborator fails
  loudly — the convention `test_clickup_webhook.py` records.
- The deployed-environment switch: a module-level `deployed` flag,
  monkeypatched with `raising=False` because guessing its spelling
  wrong must not mask the Secure assertion — if the flag is spelled
  differently, `test_the_cookie_is_marked_secure_when_deployed` fails
  at its Secure assertion and the one monkeypatch line is the
  correction point.
- The fake stores and use-case call shapes are the ones
  `test_admin_session_use_cases.py` records; the two files correct
  together.

## Expected first-run state

The module does not exist, so every test fails at import — the
absent-target state; the assertions have not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import Member, MemberRecord, mint_admin_link
from commerce_ops.access.infrastructure.driving import admin_link as admin_link_module

ADMIN_IDENTITY: Final = "U01ALICE"
BASE_URL: Final = "http://testserver"


# ---------------------------------------------------------------------------
# Fakes: the store protocols test_admin_session_use_cases.py records
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
# Harness
# ---------------------------------------------------------------------------


class _FakeMembersStore:
    """The membership the link is minted against.

    Adapted from a YAML directory by `move-principals-to-roster`; the
    link-exchange requirements these tests cover are untouched by that
    change, only the collaborator admin capability resolves from.
    """

    def __init__(self) -> None:
        self.rows = (
            MemberRecord(
                member=Member(
                    identifier="member-admin",
                    display_name="Alice Admin",
                    slack_identity=ADMIN_IDENTITY,
                    admin=True,
                )
            ),
        )

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, 1

    async def save(self, rows: Any, *, expected_version: int) -> None:
        raise AssertionError("these tests never write to the membership")


def _members(tmp_path: Path) -> Any:
    return _FakeMembersStore()


def _mint_link_path(
    tmp_path: Path, tokens: _FakeLinkTokens, *, minted_at: datetime | None = None
) -> str:
    """Mint a real link and hand back its request path.

    Minting with a `now` in the past is how token expiry is reached
    without a clock seam inside the route: the token's stored expiry
    predates the route's real clock.
    """
    link = asyncio.run(
        mint_admin_link(
            _members(tmp_path),
            tokens,
            identity=ADMIN_IDENTITY,
            base_url=BASE_URL,
            now=minted_at or datetime.now(UTC),
        )
    )
    assert isinstance(link, str) and link.startswith(BASE_URL)
    return link.removeprefix(BASE_URL)


def _app(
    monkeypatch: pytest.MonkeyPatch,
    tokens: _FakeLinkTokens,
    sessions: _FakeAdminSessions,
) -> TestClient:
    monkeypatch.setattr(admin_link_module, "link_tokens", tokens)
    monkeypatch.setattr(admin_link_module, "admin_sessions", sessions)
    app = FastAPI()
    app.include_router(admin_link_module.router)
    return TestClient(app)


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    """What "identical in shape" is compared on: status, body, and
    content type."""
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def _nothing_shape(client: TestClient) -> tuple[int, bytes, str | None]:
    """The response this very app gives for a route that does not exist."""
    return _shape(client.get("/a-route-that-was-never-registered"))


def _session_cookie_headers(response: Any) -> list[str]:
    return [
        value
        for key, value in response.headers.multi_items()
        if key.lower() == "set-cookie"
    ]


# ---------------------------------------------------------------------------
# Requirement: A link token is single-use and short-lived — the shapes
# ---------------------------------------------------------------------------


def test_a_fresh_token_exchange_establishes_a_session_cookie(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: A token exchanges once — the route half.

    WHEN a freshly minted, unexpired token is opened
    THEN the response establishes a browser session: it is not the
    absence-shaped refusal, and it sets a session cookie.

    That the session belongs to the token's principal is asserted at the
    use-case tier, where the principal is observable.
    """
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    client = _app(monkeypatch, tokens, sessions)
    path = _mint_link_path(tmp_path, tokens)

    response = client.get(path, follow_redirects=False)

    # SPECIFIED: an exchange, not a refusal.
    assert _shape(response) != _nothing_shape(client)
    assert response.status_code < 400
    # SPECIFIED: the browser session rides a cookie set by this response.
    assert len(_session_cookie_headers(response)) == 1
    # SPECIFIED: a stored session exists once the response is sent.
    assert len(sessions.rows) == 1


def test_a_spent_token_is_refused_like_a_route_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: A spent token is refused like nothing.

    WHEN the same token is opened a second time
    THEN the response is identical in shape to requesting a route that
    does not exist.
    """
    tokens = _FakeLinkTokens()
    client = _app(monkeypatch, tokens, _FakeAdminSessions())
    path = _mint_link_path(tmp_path, tokens)
    first = client.get(path, follow_redirects=False)
    assert first.status_code < 400  # the first use succeeded

    second = client.get(path, follow_redirects=False)

    # SPECIFIED: indistinguishable from an unregistered route.
    assert _shape(second) == _nothing_shape(client)
    # SPECIFIED: no cookie rides a refusal.
    assert _session_cookie_headers(second) == []


def test_an_expired_token_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: An expired token is refused identically.

    WHEN a token is opened after its expiry
    THEN the response is identical to the spent-token refusal — here
    compared against the same unregistered-route shape both must equal.
    """
    tokens = _FakeLinkTokens()
    client = _app(monkeypatch, tokens, _FakeAdminSessions())
    # Minted more than ten minutes ago: expired by the spec's bound,
    # whatever shorter lifetime the implementation may choose.
    path = _mint_link_path(
        tmp_path, tokens, minted_at=datetime.now(UTC) - timedelta(minutes=11)
    )

    response = client.get(path, follow_redirects=False)

    # SPECIFIED: the absence shape, with no session established.
    assert _shape(response) == _nothing_shape(client)
    assert _session_cookie_headers(response) == []


def test_a_token_the_system_never_minted_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Requirement statement (*A link token is single-use and
    short-lived*): "a token the system never minted SHALL ... be refused
    with the same absence-shaped response".

    WHEN a link carrying a token the system never minted is opened
    THEN the response is the same absence shape.
    """
    tokens = _FakeLinkTokens()
    client = _app(monkeypatch, tokens, _FakeAdminSessions())
    genuine = _mint_link_path(tmp_path, tokens)
    # Replace the riding token (the tail after the last `=` or `/`) with
    # a value that was never minted — same route, foreign token.
    separator = "=" if "=" in genuine else "/"
    forged = genuine.rsplit(separator, 1)[0] + separator + "never-minted-token"

    response = client.get(forged, follow_redirects=False)

    assert _shape(response) == _nothing_shape(client)


# ---------------------------------------------------------------------------
# Requirement: A browser session is bounded and rides a hardened cookie
# ---------------------------------------------------------------------------


def test_the_cookie_is_hardened_against_page_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: The cookie is hardened — the always-on half.

    WHEN the session cookie is set by the token exchange
    THEN it is marked unreadable to page script (HttpOnly).
    """
    tokens = _FakeLinkTokens()
    client = _app(monkeypatch, tokens, _FakeAdminSessions())
    path = _mint_link_path(tmp_path, tokens)

    response = client.get(path, follow_redirects=False)

    (cookie,) = _session_cookie_headers(response)
    # SPECIFIED: unreadable to page script.
    assert "httponly" in cookie.lower()


def test_the_cookie_is_marked_secure_when_deployed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: The cookie is hardened — the deployed half.

    WHEN the session cookie is set by the token exchange in a deployed
    environment
    THEN it is marked for secure transport only.

    The deployed switch is the INVENTED `deployed` module flag (see the
    docstring); if the implementation spells its deployed-environment
    determination differently, correct the monkeypatch line — the
    Secure assertion itself is SPECIFIED and stands.
    """
    tokens = _FakeLinkTokens()
    sessions = _FakeAdminSessions()
    monkeypatch.setattr(admin_link_module, "deployed", True, raising=False)
    client = _app(monkeypatch, tokens, sessions)
    path = _mint_link_path(tmp_path, tokens)

    response = client.get(path, follow_redirects=False)

    (cookie,) = _session_cookie_headers(response)
    assert "secure" in cookie.lower()
