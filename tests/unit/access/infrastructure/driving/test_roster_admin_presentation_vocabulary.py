"""The roster page's share of the admin presentation vocabulary
(`roster-admin`).

Derived strictly from the delta spec
`openspec/changes/admin-presentation-vocabulary/specs/roster-admin/spec.md`
— both its requirements, all seven scenarios:

- ADDED *The page carries a header from which the other admin surface is
  reachable* — both scenarios.
- ADDED *The page's presentation comes from the shared admin vocabulary*
  — all five scenarios, plus the one sentence of its prose that carries
  no scenario: that the page SHALL NOT reach the asset through a route
  belonging to the module that owns the other admin surface.

The manifest at
`openspec/changes/admin-presentation-vocabulary/test-manifest.md` records
every scenario, every assertion's classification, and the project
questions this file answered by assumption.

**Level.** The roster page's routes over a roster-store double, driven
the way a browser drives them — the harness
`test_roster_admin_page.py` established for this page, repeated here
rather than imported because this directory carries no `__init__.py` and
this project keeps its test files self-contained. Two tests reach past
that: the stylesheet the page links is fetched against the *shared*
asset router, and asserted not to be served by `launch`'s, which is the
only way the "not through the other module's route" sentence is
observable at all.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The literal marker tokens `row-action` and `danger`, and that
  `Deactivate` is this page's destructive action while reactivating is
  not (delta).
- That the create control is included in the vocabulary deliberately —
  "the one action not on a person's row" (delta).
- That the page carries no page-local style block, and loads the same
  stylesheet the playbook surfaces load, from a shared guarded route
  (delta; `design.md` — *The shared asset route lives in `shared`, with
  its guard injected*).
- That the guard's refusal is the app's own 404, identical to an
  unregistered route (delta; `design.md` — Context, which records both
  admin guards raising a bare `HTTPException(404)`).

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a **class token**, per
  `design.md`'s `class="row-action"`. Correction point: `_carries`.
- What counts as an action control, and how one action is told from
  another (the enclosing form's action and hidden fields, plus the
  control's own href, name, value and text). Correction points:
  `_is_action_control`, `_control_haystack`.
- How a person's row is located: the smallest element naming that person
  and no other, holding at least one action control. Correction point:
  `_person_row`.
- How the header is located and how "identifies the surface currently
  viewed" is read — the same reading as
  `tests/unit/launch/infrastructure/driving/
  test_admin_surface_navigation_and_assets.py`, and the two files
  correct together. Correction points: `_header_of`,
  `_identifies_current`, `_PLAYBOOK_WORDS`, `_ROSTER_WORDS`.
- The page module's seams and the roster-store double, taken from
  `test_roster_admin_page.py`. Correction point: `_app`.

## What this file deliberately does NOT cover

- Whether the page carries **inline `style` attributes** on individual
  elements. The scenario says "carries no page-local style block", and
  the requirement's target is the nine-line `<style>` block the page
  ships today. Asserting the absence of every inline attribute would
  oblige an implementer to a constraint nobody stated. Recorded in the
  manifest as deliberately untested.
- How anything looks. `tasks.md` 7.5 and 7.7 carry the manual checks.

## Expected first-run state

The roster page carries an inline `<style>` block, no header and no
markers today, and the shared asset route does not exist. So the marker,
header and no-style tests are expected to fail on a wrong value — the
page renders, what is asserted of it is not there — while the two tests
that drive the shared route directly fail at the *absent-target* state:
the module is not there, so their assertions never execute and establish
nothing about themselves.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 954 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_person, deactivate_person
from commerce_ops.access.infrastructure.driving import roster_admin as page_module
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as other_surface_module,
)

#: The shared asset route this change adds. Resolved by name so that its
#: absence fails only the tests that actually drive it, rather than
#: turning every test in this file into an import error.
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"


def _assets_module() -> ModuleType | None:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError:
        return None


def _require_assets_module() -> ModuleType:
    module = _assets_module()
    if module is None:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist, so the shared guarded "
            "route this requirement is about cannot be driven — the "
            "absent-target state; nothing below has been exercised"
        )
    return module


ROW_ACTION: Final = "row-action"
DANGER: Final = "danger"

ADMIN_IDENTITY: Final = "U01ALICE"
SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
RETIRED_IDENTITY: Final = "U04DAVE"

ADMIN_NAME: Final = "Alice Admin"
SECOND_ADMIN_NAME: Final = "Bob Admin"
MEMBER_NAME: Final = "Carol Member"
RETIRED_NAME: Final = "Dave Departed"

PRINCIPAL: Final = "helen"
THE_CREATING_ADMIN: Final = "the-creating-admin"
THE_EDITING_ADMIN: Final = "the-editing-admin"

_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

_EVERY_IDENTITY: Final = (
    ADMIN_IDENTITY,
    SECOND_ADMIN_IDENTITY,
    MEMBER_IDENTITY,
    RETIRED_IDENTITY,
)

#: How the page spells each action. Correction point for the implemented
#: page's action vocabulary.
_DEACTIVATE_HINTS: Final = ("deactivat",)
_REACTIVATE_HINTS: Final = ("reactivat", "restore", "reinstate")

#: How each admin surface is named in a header, and the markers by which
#: a header may identify the current one. Kept identical to the launch
#: side's file, which this one corrects together with.
_PLAYBOOK_WORDS: Final = ("playbook", "step", "steps")
_ROSTER_WORDS: Final = ("roster", "people", "person")
_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")

_HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "sr-only",
    "visually-hidden",
)

_VOID_TAGS: Final = (
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
)


# ---------------------------------------------------------------------------
# The roster store double (see test_roster_admin_page.py)
# ---------------------------------------------------------------------------


class _FakeRosterStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


_ID_NAMES: Final = ("id", "person_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("person", "entry", "definition", "record"):
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
        f"a stored roster row exposes no {what} under any of {names} — "
        "correct this file's accessor names to the implemented row"
    )


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _id_of(store: _FakeRosterStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return _field(row, _ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


async def _create(
    store: _FakeRosterStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
) -> Any:
    return await create_person(
        roster=store,
        principal=THE_CREATING_ADMIN,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _build_seeded_store() -> _FakeRosterStore:
    """Two active admins, one active member, one deactivated person —
    built through the write path, so every row is one a real write
    produced."""
    store = _FakeRosterStore()
    await _create(
        store, display_name=ADMIN_NAME, slack_identity=ADMIN_IDENTITY, admin=True
    )
    await _create(
        store,
        display_name=SECOND_ADMIN_NAME,
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    await _create(store, display_name=MEMBER_NAME, slack_identity=MEMBER_IDENTITY)
    await _create(store, display_name=RETIRED_NAME, slack_identity=RETIRED_IDENTITY)
    await deactivate_person(
        roster=store,
        principal=THE_EDITING_ADMIN,
        person_id=_id_of(store, RETIRED_IDENTITY),
    )
    return store


def _seeded_store() -> _FakeRosterStore:
    """The seeded store, built off the event loop — the tests themselves
    are synchronous and drive the ASGI app from `TestClient`'s portal."""
    return asyncio.run(_build_seeded_store())


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


@dataclass
class _Text:
    ordinal: int
    text: str


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None
    children: list[_Node | _Text] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {}, None)
        self._stack: list[_Node] = [self.root]
        self._ordinal = 0

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._ordinal += 1
            self._stack[-1].children.append(_Text(self._ordinal, _flat(data)))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _tree(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    return parser.root


def _elements(node: _Node) -> Iterator[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _elements(child)


def _texts(node: _Node) -> list[_Text]:
    found: list[_Text] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child)
        else:
            found.extend(_texts(child))
    return found


def _all_text(node: _Node) -> str:
    return " ".join(t.text for t in _texts(node)).lower()


def _attribute_text(node: _Node) -> str:
    """Everything a person's row may carry them by, values included —
    a hidden `person_id` or a per-person URL is how a row names its
    subject when the identity itself is not printed."""
    parts = [_all_text(node)]
    for element in [node, *_elements(node)]:
        parts.extend(element.attrs.values())
    return " ".join(parts).lower()


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    """Whether an element carries a vocabulary marker — read as a class
    token, per `design.md`. Correction point for a page that marks some
    other way."""
    return marker in _classes(node)


def _element_hidden(node: _Node) -> bool:
    attrs = node.attrs
    if "hidden" in attrs and attrs["hidden"].lower() != "false":
        return True
    if attrs.get("aria-hidden", "").lower() == "true":
        return True
    style = attrs.get("style", "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    return any(
        name in _HIDDEN_CLASSES for name in attrs.get("class", "").lower().split()
    )


def _element_disabled(node: _Node) -> bool:
    return (
        "disabled" in node.attrs
        or node.attrs.get("aria-disabled", "").lower() == "true"
    )


def _inherited(node: _Node, predicate: Callable[[_Node], bool]) -> bool:
    walker: _Node | None = node
    while walker is not None and walker.tag != "#document":
        if predicate(walker):
            return True
        walker = walker.parent
    return False


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _nearest(node: _Node, tag: str) -> _Node | None:
    return next((a for a in _ancestors(node) if a.tag == tag), None)


def _size(node: _Node) -> int:
    return 1 + sum(1 for _ in _elements(node))


# ---------------------------------------------------------------------------
# Action controls
# ---------------------------------------------------------------------------


def _is_action_control(node: _Node) -> bool:
    if node.attrs.get("role", "").lower() == "button":
        return True
    if node.tag == "button":
        return True
    if node.tag == "input":
        return (node.attrs.get("type") or "text").lower() in ("submit", "image")
    if node.tag == "a":
        return "href" in node.attrs or any(verb in node.attrs for verb in _HX_VERBS)
    return False


def _action_controls(node: _Node) -> list[_Node]:
    found = [node] if _is_action_control(node) else []
    found.extend(child for child in _elements(node) if _is_action_control(child))
    return found


def _control_haystack(node: _Node) -> str:
    """Everything naming what this control does: its own destination,
    label and text, plus its enclosing form's action and hidden fields."""
    parts: list[str] = [
        node.attrs.get(key, "")
        for key in ("href", "formaction", "name", "value", "aria-label", "title")
    ]
    parts.extend(node.attrs.get(verb, "") for verb in _HX_VERBS)
    parts.append(_flat(" ".join(t.text for t in _texts(node))))
    form = _nearest(node, "form")
    if form is not None:
        parts.append(form.attrs.get("action", ""))
        parts.extend(form.attrs.get(verb, "") for verb in _HX_VERBS)
        for element in _elements(form):
            if element.tag == "input" and element.attrs.get("type", "").lower() == (
                "hidden"
            ):
                parts.append(element.attrs.get("name", ""))
                parts.append(element.attrs.get("value", ""))
    return " ".join(part for part in parts if part).lower()


def _one_action(
    row: _Node, *, hints: tuple[str, ...], excluding: tuple[str, ...], what: str
) -> _Node:
    controls = _action_controls(row)
    found = [
        control
        for control in controls
        if any(hint in _control_haystack(control) for hint in hints)
        and not any(word in _control_haystack(control) for word in excluding)
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} controls on this row look like the {what} action "
            f"(hints {hints}, excluding {excluding}); the row offers "
            f"{[_control_haystack(c)[:80] for c in controls]} — correct this "
            "file's action vocabulary to the implemented page"
        )
    return found[0]


def _person_row(root: _Node, identity: str) -> _Node:
    """The one person's own region of the page.

    INVENTED: the smallest element that names this person, offers at
    least one action control, and names no other person on the roster.
    Markup-agnostic, so a table row, a list item or a card all read the
    same. Correction point for a page that groups people differently.
    """
    wanted = identity.lower()
    others = [other.lower() for other in _EVERY_IDENTITY if other != identity]
    candidates = [
        element
        for element in _elements(root)
        if wanted in _attribute_text(element)
        and _action_controls(element)
        and not any(other in _attribute_text(element) for other in others)
    ]
    if not candidates:
        pytest.fail(
            f"no element of the page names {identity!r}, offers an action and "
            "names nobody else, so that person's row cannot be isolated — "
            "correct `_person_row` to the implemented page"
        )
    return min(candidates, key=_size)


# ---------------------------------------------------------------------------
# The header
# ---------------------------------------------------------------------------


def _path_of(href: str) -> str:
    return urlsplit(href).path


def _links_to(root: _Node, path: str) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and _path_of(element.attrs.get("href", "")) == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _names(node: _Node, words: tuple[str, ...]) -> bool:
    text = _all_text(node)
    return any(word in text for word in words)


def _header_of(
    root: _Node, *, other_path: str, current_words: tuple[str, ...]
) -> _Node:
    """The page's admin header — the smallest element that links to the
    other admin surface, names this one, and does not enclose the page's
    own tables or forms."""
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the page renders no link to {other_path!r} at all, so it carries "
            "no header from which the other admin surface is reachable"
        )
    candidates = [
        ancestor
        for link in outbound
        for ancestor in _ancestors(link)
        if _names(ancestor, current_words)
        and ancestor.tag not in ("html", "body", "#document")
        and not any(e.tag in ("table", "form") for e in _elements(ancestor))
    ]
    if not candidates:
        pytest.fail(
            f"the link to {other_path!r} sits in no element that also names "
            f"this surface (looked for {current_words}) without enclosing the "
            "page's own tables or forms — correct `_header_of` or "
            "`_PLAYBOOK_WORDS`/`_ROSTER_WORDS` to the implemented header"
        )
    return min(candidates, key=_size)


def _offers_in_one_action(header: _Node, path: str) -> bool:
    return any(
        not _inherited(link, _element_disabled)
        and not _inherited(link, _element_hidden)
        for link in _links_to(header, path)
    )


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _identifies_current(header: _Node, *, words: tuple[str, ...]) -> bool:
    """Whether the header reads as a position: the current surface is
    named by something either explicitly marked current or not rendered
    as a link at all."""
    within = [header, *_elements(header)]
    naming = [
        element
        for element in within
        if _names(element, words)
        and not any(_names(child, words) for child in _elements(element))
    ]
    for element in naming:
        chain = [element]
        walker = element.parent
        while walker is not None and walker is not header.parent:
            chain.append(walker)
            walker = walker.parent
        if any(_marked_current(node) for node in chain):
            return True
        if not any(node.tag == "a" for node in chain):
            return True
    return False


def _stylesheet_hrefs(root: _Node) -> list[str]:
    return [
        element.attrs["href"]
        for element in _elements(root)
        if element.tag == "link"
        and "stylesheet" in element.attrs.get("rel", "").lower()
        and element.attrs.get("href")
    ]


def _style_blocks(root: _Node) -> list[_Node]:
    return [element for element in _elements(root) if element.tag == "style"]


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _app(monkeypatch: pytest.MonkeyPatch, store: _FakeRosterStore) -> TestClient:
    monkeypatch.setattr(page_module, "roster", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    app = FastAPI()
    app.include_router(page_module.router)
    return TestClient(app)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeRosterStore
) -> TestClient:
    client = _app(monkeypatch, store)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _shortest_get_route(router: Any) -> str:
    candidates: list[str] = []
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, f"{router!r} exposes no parameterless GET route"
    return min(candidates, key=len)


def _page_path() -> str:
    return _shortest_get_route(page_module.router)


def _playbook_path() -> str:
    return _shortest_get_route(other_surface_module.router)


def _resolve(url: str) -> str:
    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return response.text


def _assets_client(monkeypatch: pytest.MonkeyPatch, *, signed: bool) -> TestClient:
    """An app mounting the *shared* asset router alone, with its guard
    injected the way `main.py` injects it."""
    module = _require_assets_module()
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    if signed:
        client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _other_module_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app mounting only the router of the module that owns the other
    admin surface — used to establish that this page does *not* reach its
    asset through it."""
    monkeypatch.setattr(other_surface_module, "verify_admin_session", _fake_verify)
    app = FastAPI()
    app.include_router(other_surface_module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def _reachable_html(client: TestClient, html: str, needle: str) -> str:
    """The page in which `needle` is reachable — the roster page itself,
    or a view one control away, since the served spec requires
    deactivated people be *reachable* rather than listed."""
    if needle in html:
        return html
    for word in ("deactivat", "inactive", "former", "archived"):
        for element in _elements(_tree(html)):
            if element.tag != "a" or word not in _control_haystack(element):
                continue
            response = client.get(_resolve(element.attrs.get("href", "")))
            if response.status_code == 200 and needle in response.text:
                return str(response.text)
    pytest.fail(
        f"{needle!r} was not reachable from the roster page — neither listed "
        "on it nor behind any discovered control"
    )


def _create_form(root: _Node) -> _Node:
    """The add-a-person form: the one offering both a display-name field
    and a Slack-identity field."""
    for element in _elements(root):
        if element.tag != "form":
            continue
        names = " ".join(
            child.attrs.get("name", "")
            for child in _elements(element)
            if child.tag in ("input", "select", "textarea")
        ).lower()
        if "name" in names and "slack" in names:
            return element
    pytest.fail(
        "no add-a-person form was discoverable on the roster page — correct "
        "`_create_form` to the implemented page"
    )


# ---------------------------------------------------------------------------
# ADDED requirement: The page carries a header from which the other admin
# surface is reachable
# ---------------------------------------------------------------------------


def test_the_playbook_page_is_reachable_from_the_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The playbook page is reachable from the roster.

    WHEN the roster page is rendered
    THEN its header offers the playbook page in one action
    AND identifies the roster as the surface currently viewed.

    The page carries no `href` of any kind today, so there is no way back
    to the playbook page without typing a URL.
    """
    client = _signed_client(monkeypatch, _seeded_store())

    header = _header_of(
        _tree(_get_page(client)),
        other_path=_playbook_path(),
        current_words=_ROSTER_WORDS,
    )

    # SPECIFIED: the playbook page is offered in one action, and without
    # scripting — a plain anchor.
    assert _offers_in_one_action(header, _playbook_path()), (
        f"the header renders no live link to {_playbook_path()!r}, so an "
        "admin who reaches the roster cannot get back"
    )
    # SPECIFIED: and identifies the roster as current.
    assert _identifies_current(header, words=_ROSTER_WORDS), (
        "the header does not identify the roster as the surface being "
        "viewed, so it reads as an undifferentiated pair of links rather "
        f"than as a position (header: {_flat(_all_text(header))[:300]!r})"
    )


def test_the_header_is_rendered_on_a_roster_holding_nobody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The header is rendered on a roster holding nobody.

    WHEN the roster page is rendered holding no people at all
    THEN the header is still rendered and still offers the playbook page.
    """
    client = _signed_client(monkeypatch, _FakeRosterStore())

    html = _get_page(client)

    # DERIVED guard: the roster really holds nobody, so the header below
    # is read off an empty page.
    for identity in _EVERY_IDENTITY:
        assert identity not in html

    header = _header_of(
        _tree(html), other_path=_playbook_path(), current_words=_ROSTER_WORDS
    )
    # SPECIFIED: the header is still rendered and still offers the
    # playbook page.
    assert _offers_in_one_action(header, _playbook_path()), (
        "the header stops offering the playbook page once the roster holds "
        "nobody, so reachability depends on the people the page lists"
    )


# ---------------------------------------------------------------------------
# ADDED requirement: The page's presentation comes from the shared admin
# vocabulary
# ---------------------------------------------------------------------------


def test_the_page_carries_no_styling_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The page carries no styling of its own.

    WHEN the roster page is rendered
    THEN it loads the shared admin stylesheet
    AND carries no page-local style block.

    "The shared admin stylesheet" is asserted by fetching what the page
    links against an app mounting the *shared* asset router alone: a page
    linking `launch`'s `/admin/static/…` would not be served there.

    The requirement's own prose adds a sentence its scenarios do not: the
    page SHALL NOT reach the asset through a route belonging to the
    module that owns the other admin surface. That is asserted here too,
    by fetching the same href against an app mounting only that module's
    router — where it must find nothing.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    html = _get_page(client)
    root = _tree(html)

    hrefs = _stylesheet_hrefs(root)
    # SPECIFIED: it loads a stylesheet at all …
    assert hrefs, (
        "the roster page links no stylesheet, so its presentation comes from "
        "nowhere shared"
    )
    # SPECIFIED: … and carries no page-local style block.
    blocks = _style_blocks(root)
    assert blocks == [], (
        f"the roster page still carries {len(blocks)} inline <style> block(s), "
        "so a presentation fix applied to the playbook page silently does not "
        "apply here"
    )

    # SPECIFIED: the stylesheet it loads is the shared one — served by
    # the shared route.
    shared = _assets_client(monkeypatch, signed=True)
    elsewhere = _other_module_client(monkeypatch)
    for href in hrefs:
        assert not href.startswith(("http://", "https://", "//")), (
            f"the roster page loads {href!r} from off the machine, so what is "
            "served is not what the repository committed"
        )
        served = shared.get(_resolve(href))
        assert served.status_code == 200, (
            f"the roster page links {href!r}, which the shared asset route "
            f"answers {served.status_code} for — the page's presentation does "
            "not come from the shared vocabulary"
        )
        # SPECIFIED (requirement prose): and not through the other admin
        # surface's own route.
        through_other = elsewhere.get(_resolve(href))
        assert through_other.status_code != 200, (
            f"{href!r} is served by the module that owns the other admin "
            "surface, so deleting that route while working on the playbook "
            "page would break this page with nothing in the import graph "
            "recording the dependency"
        )


def test_the_stylesheet_is_refused_without_an_admin_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The stylesheet is refused without an admin session.

    WHEN the stylesheet is requested from the roster surface with no
    admin session cookie
    THEN the response is the same 404 an unregistered route returns
    AND carries no stylesheet content.

    The href is taken from what the roster page itself renders, so this
    is the asset *this surface* reaches for rather than one this file
    named.
    """
    signed_page = _signed_client(monkeypatch, _seeded_store())
    hrefs = _stylesheet_hrefs(_tree(_get_page(signed_page)))
    assert hrefs, "the roster page links no stylesheet to request"

    signed = _assets_client(monkeypatch, signed=True)
    anonymous = _assets_client(monkeypatch, signed=False)
    nothing = _shape(anonymous.get("/a-route-that-was-never-registered"))

    for href in hrefs:
        served = signed.get(_resolve(href))
        assert served.status_code == 200, (
            f"{href!r} is not served even to an admin, so the refusal below "
            "would say nothing about the guard"
        )
        response = anonymous.get(_resolve(href))
        # SPECIFIED: the same 404 an unregistered route returns —
        # revealing neither the surface nor the reason.
        assert _shape(response) == nothing, (
            f"{href!r} answers {response.status_code} to a caller with no "
            "admin session, which differs from what an unregistered route "
            "answers and so tells an anonymous caller the admin surface exists"
        )
        # SPECIFIED: and carries no stylesheet content.
        assert served.content not in response.content, (
            f"the refusal for {href!r} carries the stylesheet itself"
        )


def test_the_destructive_action_is_distinguished_not_amplified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The destructive action is distinguished, not amplified.

    WHEN an active person's row is rendered
    THEN its deactivate control carries `danger`
    AND no other action control on that row carries it.
    """
    client = _signed_client(monkeypatch, _seeded_store())

    row = _person_row(_tree(_get_page(client)), MEMBER_IDENTITY)
    deactivate = _one_action(
        row, hints=_DEACTIVATE_HINTS, excluding=_REACTIVATE_HINTS, what="deactivate"
    )

    # SPECIFIED: the deactivate control carries `danger`.
    assert _carries(deactivate, DANGER), (
        f"the deactivate control on {MEMBER_IDENTITY!r}'s row carries no "
        f"{DANGER!r} marker (classes: {sorted(_classes(deactivate))})"
    )
    # SPECIFIED: and no other action control on that row carries it.
    others = [
        c for c in _action_controls(row) if c is not deactivate and _carries(c, DANGER)
    ]
    assert others == [], (
        f"{len(others)} controls other than deactivate carry {DANGER!r} on "
        f"{MEMBER_IDENTITY!r}'s row: "
        f"{[_control_haystack(c)[:60] for c in others]}"
    )
    # SPECIFIED (the requirement's own prose): every one of the page's
    # actions carries `row-action`, the destructive one included.
    unmarked = [c for c in _action_controls(row) if not _carries(c, ROW_ACTION)]
    assert unmarked == [], (
        f"{len(unmarked)} action controls on {MEMBER_IDENTITY!r}'s row carry "
        f"no {ROW_ACTION!r} marker: "
        f"{[_control_haystack(c)[:60] for c in unmarked]}"
    )


def test_a_deactivated_persons_action_is_not_destructive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A deactivated person's action is not destructive.

    WHEN a deactivated person's row is rendered
    THEN its reactivate control carries `row-action`
    AND does not carry `danger`.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    reachable = _reachable_html(client, _get_page(client), RETIRED_IDENTITY)

    row = _person_row(_tree(reachable), RETIRED_IDENTITY)
    reactivate = _one_action(
        row, hints=_REACTIVATE_HINTS, excluding=(), what="reactivate"
    )

    # SPECIFIED: its reactivate control carries `row-action`.
    assert _carries(reactivate, ROW_ACTION), (
        "the reactivate control carries no "
        f"{ROW_ACTION!r} marker (classes: {sorted(_classes(reactivate))}), so "
        "a deactivated person's row speaks a vocabulary of its own"
    )
    # SPECIFIED: and does not carry `danger` — restoring somebody
    # destroys nothing.
    assert not _carries(reactivate, DANGER), (
        f"the reactivate control carries {DANGER!r}, marking a restoring "
        "action as the destructive one"
    )


def test_the_create_control_speaks_the_same_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The create control speaks the same vocabulary.

    WHEN the page's add-a-person form is rendered
    THEN its submit control carries `row-action`
    AND does not carry `danger`.

    The delta includes the create control deliberately: it is the one
    action not on a person's row, and a create submit left at the default
    weight while every neighbour is restyled is exactly the mismatch the
    requirement exists to end.
    """
    client = _signed_client(monkeypatch, _seeded_store())

    form = _create_form(_tree(_get_page(client)))
    submits = [
        control
        for control in _action_controls(form)
        if (
            control.tag == "button"
            and (control.attrs.get("type") or "submit").lower() == "submit"
        )
        or (
            control.tag == "input"
            and (control.attrs.get("type") or "").lower() in ("submit", "image")
        )
    ]
    assert submits, (
        "the add-a-person form renders no submit control, so there is no "
        "create action to read a vocabulary off"
    )
    for submit in submits:
        # SPECIFIED: its submit control carries `row-action`.
        assert _carries(submit, ROW_ACTION), (
            "the add-a-person form's submit carries no "
            f"{ROW_ACTION!r} marker (classes: {sorted(_classes(submit))}) — "
            "the one action not on a person's row was missed"
        )
        # SPECIFIED: and does not carry `danger`. Creating destroys
        # nothing.
        assert not _carries(submit, DANGER), (
            f"the add-a-person form's submit carries {DANGER!r}"
        )
