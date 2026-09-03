"""The admin surface's Team page (`members-admin`), plus the
absence-shaped guard on its routes (`admin-session`, first scenario of
*Admin access fails closed and absence-shaped*).

Derived strictly from the delta specs:
`openspec/changes/move-principals-to-roster/specs/roster-admin/spec.md`
(all three requirements, all seven scenarios) and
`.../specs/admin-session/spec.md` (*No session means no surface*, over
this change's new admin routes; its two revocation scenarios are
verification-side and live in
`tests/unit/access/application/test_admin_session_over_members.py`).

Two requirement sentences carry no scenario of their own — editing an
existing member, and reactivating a deactivated one — and are asserted
here as DERIVED (`test_an_edit_from_the_page_lands_through_the_use_cases`,
`test_a_reactivation_from_the_page_restores_the_member`), so that a page
offering neither would not pass silently.

Every `members-admin` scenario is stated over the rendered page and the
writes made from it, so the page's routes over a membership-store double are
the smallest observing unit. The page is HTML end to end, so these tests
drive it the way a browser does: they *discover* the page's own controls
and submit them, pinning as little of the URL surface as possible — the
idiom `tests/unit/launch/infrastructure/driving/
test_playbook_admin_page.py` established for the playbook page, which
`design.md` Decision 5 says this page mirrors.

## What is fixed, and what is INVENTED

Fixed by the artifacts: a Team page in
`access/infrastructure/driving/` gated by the existing admin-session
dependency (`tasks.md` 4.1, `design.md` Decision 5); every write going
through the membership's use cases; a rejected write re-presenting every
fault with the submitted values and persisting nothing; the last-admin
refusal surfaced on the page.

INVENTED, recorded in the manifest as unresolved project questions:

- The module `commerce_ops.access.infrastructure.driving.members_admin`
  exposing `router`. Correction point: the import and `_app`.
- The members store bound as a module-level `members` name, substituted
  with `monkeypatch.setattr` (raising) — the convention
  `test_playbook_admin_page.py` follows for `steps`. Correction point:
  `_app`.
- The guard consuming `verify_admin_session` imported into the page
  module; monkeypatched with a fake answering the principal only for one
  known session value. The *response shape* on refusal is real page code
  and is what the guard test asserts. Correction points: `_fake_verify`,
  `_SESSION_COOKIE`.
- Control-discovery vocabulary: a deactivate control's URL or fields
  mention "deactivate", a reactivate control "reactivate", a create form
  offers a display-name field and a Slack-identity field. Correction
  points: `_control`, `_create_form`.
- That an entry's attribution is readable in that entry's own region of
  the page, and that "when" renders carrying the current year.
  Correction points: `_segment`, `_YEAR`.
- The membership-store double and write call shapes, as
  `tests/unit/access/application/test_members_writes.py` records; the
  files correct together. They are repeated rather than shared because
  this pass may write only files matching `tests/**/test_*.py` — a
  shared `conftest.py` was not available to it.

## Expected first-run state

The page module does not exist, so every test here fails at import —
the absent-target state; the assertions have not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member, deactivate_member
from commerce_ops.access.infrastructure.driving import members_admin as page_module
from tests.support.admin import ADMIN_IDENTITY, fake_verify
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.fixtures import PRINCIPAL

SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
RETIRED_IDENTITY: Final = "U04DAVE"
NEWCOMER_IDENTITY: Final = "U05ERIN"

ADMIN_NAME: Final = "Alice Admin"
SECOND_ADMIN_NAME: Final = "Bob Admin"
MEMBER_NAME: Final = "Carol Member"
RETIRED_NAME: Final = "Dave Departed"
NEWCOMER_NAME: Final = "Erin Newcomer"

THE_CREATING_ADMIN: Final = "the-creating-admin"
THE_EDITING_ADMIN: Final = "the-editing-admin"

_YEAR: Final = str(datetime.now(UTC).year)


# ---------------------------------------------------------------------------
# The members store double (see test_members_writes.py)
# ---------------------------------------------------------------------------


class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
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


_ID_NAMES: Final = ("id", "member_id", "identifier")
_NAME_NAMES: Final = ("display_name", "name")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_ACTIVE_NAMES: Final = ("active", "is_active")


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


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _is_active(row: Any) -> bool:
    return bool(_field(row, _ACTIVE_NAMES, "active flag"))


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return _field(row, _ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


def _row_for(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return row
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


async def _create(
    store: _FakeMembersStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
    principal: str = PRINCIPAL,
) -> Any:
    return await create_member(
        members=store,
        principal=principal,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _build_seeded_store() -> _FakeMembersStore:
    """Two active admins, one active member, one deactivated member —
    built through the write path, so every row is one a real write
    produced. The second admin is what lets the first be deactivated at
    all under the last-admin floor.
    """
    store = _FakeMembersStore()
    await _create(
        store,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
        principal=THE_CREATING_ADMIN,
    )
    await _create(
        store,
        display_name=SECOND_ADMIN_NAME,
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
        principal=THE_CREATING_ADMIN,
    )
    await _create(
        store,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
        principal=THE_CREATING_ADMIN,
    )
    await _create(
        store,
        display_name=RETIRED_NAME,
        slack_identity=RETIRED_IDENTITY,
        principal=THE_CREATING_ADMIN,
    )
    await deactivate_member(
        members=store,
        principal=THE_EDITING_ADMIN,
        member_id=_id_of(store, RETIRED_IDENTITY),
    )
    return store


async def _build_store_with_one_admin() -> _FakeMembersStore:
    """One active admin — the last one — plus one ordinary member."""
    store = _FakeMembersStore()
    await _create(
        store,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
        principal=THE_CREATING_ADMIN,
    )
    await _create(
        store,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
        principal=THE_CREATING_ADMIN,
    )
    return store


def _seeded_store() -> _FakeMembersStore:
    """The seeded store, built off the event loop.

    The tests themselves are synchronous — `TestClient` drives the ASGI
    app from its own portal, the way every driving-adapter test in this
    project does — so the async write use cases that build the starting
    members run in their own loop here.
    """
    return asyncio.run(_build_seeded_store())


def _store_with_one_admin() -> _FakeMembersStore:
    return asyncio.run(_build_store_with_one_admin())


# ---------------------------------------------------------------------------
# HTML discovery: forms and controls, the way a browser sees them
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


class _PageParser(HTMLParser):
    """Collects submit-able things: forms with their fields, and any
    element carrying an `hx-*` request attribute or an `href`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.controls: list[tuple[str, str]] = []
        self._form: dict[str, Any] | None = None
        self._select: str | None = None
        self._textarea: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        for verb in _HX_VERBS:
            if verb in a:
                self.controls.append((verb.removeprefix("hx-"), a[verb]))
        if tag == "a" and "href" in a:
            self.controls.append(("get", a["href"]))
        if tag == "form":
            self._form = {
                "method": (a.get("method") or "get").lower(),
                "url": a.get("action", ""),
                "fields": {},
            }
            for verb in _HX_VERBS:
                if verb in a:
                    self._form["method"] = verb.removeprefix("hx-")
                    self._form["url"] = a[verb]
        elif self._form is not None and tag == "input":
            name = a.get("name")
            if not name:
                return
            kind = (a.get("type") or "text").lower()
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            default = "on" if kind == "checkbox" else ""
            self._form["fields"][name] = a.get("value", default)
        elif self._form is not None and tag == "select":
            self._select = a.get("name")
            if self._select:
                self._form["fields"][self._select] = ""
        elif self._form is not None and tag == "option" and self._select:
            if "selected" in a:
                self._form["fields"][self._select] = a.get("value", "")
        elif self._form is not None and tag == "textarea":
            self._textarea = a.get("name")
            if self._textarea:
                self._form["fields"][self._textarea] = ""

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea:
            self._form["fields"][self._textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


def _control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> tuple[str, str, dict[str, str]] | None:
    """The first form or control whose URL — plus, for forms, its
    serialized fields — mentions every `contains` substring."""
    parsed = _parse(html)
    for form in parsed.forms:
        haystack = (
            form["url"] + " " + " ".join(f"{k}={v}" for k, v in form["fields"].items())
        )
        if all(part in haystack for part in contains) and not any(
            part in haystack for part in excludes
        ):
            return form["method"], form["url"], dict(form["fields"])
    for method, url in parsed.controls:
        if all(part in url for part in contains) and not any(
            part in url for part in excludes
        ):
            return method, url, {}
    return None


def _require_control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> tuple[str, str, dict[str, str]]:
    found = _control(html, contains=contains, excludes=excludes)
    if found is None:
        pytest.fail(
            f"no page control mentioning {contains} was discovered — the "
            "invented control vocabulary in this file's docstring needs "
            "correcting to the implemented page"
        )
    return found


def _member_control(
    html: str,
    *,
    member_id: Any,
    identity: str,
    verb: str,
    excludes: tuple[str, ...] = (),
) -> tuple[str, str, dict[str, str]]:
    """A per-member action control, addressed by whichever of the
    generated id or the Slack identity the page routes by."""
    for handle in (str(member_id), identity):
        found = _control(html, contains=(handle, verb), excludes=excludes)
        if found is not None:
            return found
    pytest.fail(
        f"no {verb!r} control for the member carrying {identity!r} was "
        "discovered — correct this file's control vocabulary to the "
        "implemented page"
    )


def _create_form(client: TestClient, html: str) -> dict[str, Any]:
    """The create-a-member form: one offering both a display-name field
    and a Slack-identity field, on the page itself or behind a control
    that opens it."""

    def _candidate(page: str) -> dict[str, Any] | None:
        for form in _parse(page).forms:
            names = " ".join(form["fields"]).lower()
            if "name" in names and "slack" in names:
                return form
        return None

    found = _candidate(html)
    if found is not None:
        return found
    for word in ("new", "create", "add"):
        control = _control(html, contains=(word,))
        if control is None:
            continue
        method, url, _ = control
        response = _submit(client, method, url, {})
        if response.status_code == 200:
            opened = _candidate(response.text)
            if opened is not None:
                return opened
    pytest.fail(
        "no create-a-member form was discoverable on the Team page — "
        "correct this file's form-discovery vocabulary to the implemented "
        "page"
    )


def _edit_form(
    client: TestClient, html: str, *, member_id: Any, identity: str
) -> dict[str, Any]:
    """The edit form for one member: a form carrying that member's handle
    and a display-name field, either inline on the page or behind an
    "edit" control that opens it."""

    def _candidate(page: str) -> dict[str, Any] | None:
        for form in _parse(page).forms:
            haystack = form["url"] + " " + str(form["fields"])
            if str(member_id) not in haystack and identity not in haystack:
                continue
            if any("name" in name.lower() for name in form["fields"]):
                return form
        return None

    found = _candidate(html)
    if found is not None:
        return found
    for handle in (str(member_id), identity):
        control = _control(html, contains=(handle, "edit"))
        if control is None:
            continue
        method, url, fields = control
        response = _submit(client, method, url, fields)
        if response.status_code == 200:
            opened = _candidate(response.text)
            if opened is not None:
                return opened
    pytest.fail(
        f"no edit form for the member carrying {identity!r} was "
        "discoverable — correct this file's control vocabulary to the "
        "implemented page"
    )


def _fill(fields: dict[str, str], **by_substring: str) -> dict[str, str]:
    """Overrides form fields addressed by name substring, failing loudly
    if an addressed field has no match, so nothing is submitted
    vacuously."""
    filled = dict(fields)
    for fragment, value in by_substring.items():
        matches = [name for name in filled if fragment in name.lower()]
        if not matches:
            pytest.fail(
                f"the form offers no field whose name contains {fragment!r} "
                f"(fields: {sorted(filled)}) — correct this file's "
                "field-addressing to the implemented form"
            )
        for name in matches:
            filled[name] = value
    return filled


def _segment(html: str, anchor: str, others: tuple[str, ...]) -> str:
    """The page region belonging to one entry: from its anchor to the
    next entry's anchor. Markup-agnostic, so a table, a list or a stack
    of cards all read the same."""
    at = html.find(anchor)
    assert at >= 0, f"{anchor!r} is not rendered on the page"
    following = [
        html.find(other)
        for other in others
        if other != anchor and html.find(other) > at
    ]
    return html[at : min(following)] if following else html[at:]


def _positions(html: str, *needles: str) -> list[int]:
    found = []
    for needle in needles:
        at = html.find(needle)
        assert at >= 0, f"{needle!r} is not rendered on the page"
        found.append(at)
    return found


def _words(text: str) -> set[str]:
    return {word.strip(":;,.<>/\"'=()[]").lower() for word in text.split()}


def _distinctive_words(segment: str, handles: tuple[str, ...]) -> set[str]:
    """The words of one entry's page region, with every token carrying a
    member-specific handle — a name, a Slack identity, a generated id —
    discarded.

    Without that discount the comparison below would pass on nothing but
    per-member URLs, which differ for every entry whether or not the
    page renders an admin flag at all.
    """
    lowered = tuple(handle.lower() for handle in handles if handle)
    return {
        word
        for word in _words(segment)
        if not any(handle in word for handle in lowered)
    }


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


_fake_verify = fake_verify(PRINCIPAL)


def _app(monkeypatch: pytest.MonkeyPatch, store: _FakeMembersStore) -> TestClient:
    # The Team list reads the role collection for a member's roles column.
    # `main.py` binds the real Postgres store to this module at import and
    # that outlives the test that imported it, so it is pinned here to a
    # store this test controls. `None` renders the column empty, which is
    # right for a test that asserts nothing about roles.
    monkeypatch.setattr(page_module, "roles", None, raising=False)
    monkeypatch.setattr(page_module, "members", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    app = FastAPI()
    app.include_router(page_module.router)
    return TestClient(app)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeMembersStore
) -> TestClient:
    client = _app(monkeypatch, store)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _page_path() -> str:
    """The Team page: the shortest parameterless GET route the page
    router exposes."""
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the Team page router exposes no parameterless GET route"
    return min(candidates, key=len)


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return response.text


def _submit(client: TestClient, method: str, url: str, data: dict[str, str]) -> Any:
    if not url:
        target = _page_path()
    elif url.startswith("/"):
        target = url
    else:
        target = urljoin(_page_path() + "/", url)
    return client.request(method.upper(), target, data=data)


def _reachable_text(client: TestClient, html: str, needle: str) -> str:
    """The page text in which `needle` is reachable — the Team page
    itself, or a view one discovered control away (the delta requires
    deactivated members be *reachable* from the page, not necessarily
    listed on it)."""
    if needle in html:
        return html
    for word in ("deactivat", "inactive", "former", "archived"):
        control = _control(html, contains=(word,))
        if control is None:
            continue
        method, url, fields = control
        response = _submit(client, method, url, fields)
        if response.status_code == 200 and needle in response.text:
            return str(response.text)
    pytest.fail(
        f"{needle!r} was not reachable from the Team page — neither "
        "listed on it nor behind any discovered control"
    )


# ---------------------------------------------------------------------------
# admin-session: Admin access fails closed and absence-shaped
# ---------------------------------------------------------------------------


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def test_no_session_means_no_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario (`admin-session`): No session means no surface — over
    this change's new members routes.

    WHEN the Team page is requested without a session, and with a
    session verification refuses
    THEN each response is identical in shape to requesting a route that
    does not exist.

    The Team page is a new admin route, so the guarantee has to be
    re-established over it: a page mounted without the gate would leak
    the whole membership directory.
    """
    store = _seeded_store()
    client = _app(monkeypatch, store)
    nothing = _shape(client.get("/a-route-that-was-never-registered"))

    without_session = client.get(_page_path())
    client.cookies.set(_SESSION_COOKIE, "a-session-verification-refuses")
    with_refused_session = client.get(_page_path())

    # SPECIFIED: the absence shape, revealing neither the surface nor
    # the reason — and the two refusals are indistinguishable.
    assert _shape(without_session) == nothing
    assert _shape(with_refused_session) == nothing
    # DERIVED sanity guard: a verified session does see the surface, so
    # the equalities above are not an artifact of a dead router.
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    assert client.get(_page_path()).status_code == 200


# ---------------------------------------------------------------------------
# Requirement: The Team page shows the membership whole
# ---------------------------------------------------------------------------


def test_the_whole_active_members_is_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The whole active membership is one page.

    WHEN an admin opens the Team page
    THEN every active member is listed on that one page with their
    identity data and admin flag.

    "On that one page" is asserted by taking a single unparameterized
    GET and finding every active member in it — no pagination control
    followed, nothing fetched twice.

    The admin flag is asserted as a *distinction*: the admin's region of
    the page carries at least one word no ordinary member's region does,
    once each member's own name and identity words are discounted. That
    reads a "Yes", a badge, a checkmark or the word "admin" alike, and
    fails a page that renders the flag nowhere. DERIVED mechanism; the
    delta fixes that the flag is shown, not how.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    anchors = (ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY, MEMBER_IDENTITY)
    # SPECIFIED: every active member, with their identity data.
    for identity, name in (
        (ADMIN_IDENTITY, ADMIN_NAME),
        (SECOND_ADMIN_IDENTITY, SECOND_ADMIN_NAME),
        (MEMBER_IDENTITY, MEMBER_NAME),
    ):
        assert identity in html, f"{identity} is missing from the Team page"
        assert name in html, f"{name} is missing from the Team page"

    # SPECIFIED: and their admin flag.
    handles = tuple(
        part.lower()
        for identity in anchors + (RETIRED_IDENTITY,)
        for part in (identity, str(_id_of(store, identity)))
    ) + tuple(
        word.lower()
        for name in (ADMIN_NAME, SECOND_ADMIN_NAME, MEMBER_NAME, RETIRED_NAME)
        for word in name.split()
    )
    admin_words = _distinctive_words(_segment(html, ADMIN_IDENTITY, anchors), handles)
    member_words = _distinctive_words(_segment(html, MEMBER_IDENTITY, anchors), handles)
    assert admin_words - member_words, (
        "nothing on the page distinguishes an admin entry from an "
        "ordinary member's: the admin flag is not shown"
    )


def test_deactivated_members_are_reachable_but_set_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Deactivated members are reachable but set apart.

    WHEN the membership holds deactivated members
    THEN the page presents them distinctly from the active membership, and
    never mixed into it.

    Two readings satisfy "set apart" and both pass here: a separate
    region further down the same page, or a separate view one control
    away. What fails either way is interleaving — a deactivated entry
    rendered *between* two active ones, which is what the delta's
    "never interleaved with it" forbids.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: reachable from the page.
    view = _reachable_text(client, html, RETIRED_IDENTITY)

    if view is not html:
        # Set apart by living on its own view: nothing more to assert.
        assert RETIRED_IDENTITY not in html
        return

    actives = _positions(view, ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY, MEMBER_IDENTITY)
    (deactivated,) = _positions(view, RETIRED_IDENTITY)
    # SPECIFIED: never mixed into the active membership.
    assert deactivated > max(actives) or deactivated < min(actives), (
        "a deactivated member is rendered between active ones; the delta "
        "requires them visibly set apart, never interleaved"
    )


# ---------------------------------------------------------------------------
# Requirement: A member can be created and edited from the page
# ---------------------------------------------------------------------------
