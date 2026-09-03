"""The Roles surface's navigation and presentation vocabulary
(`roles-admin`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/roles-admin/spec.md`
— three of its eight ADDED requirements, eleven scenarios:

- *The create page and a role's own page carry a breadcrumb back to the
  list* (3)
- *The Roles pages carry the shared admin header* (4)
- *The Roles pages' presentation comes from the shared admin vocabulary*
  (4)

The other five requirements are covered in `test_roles_admin_page.py`.

## Level

The Roles router over store doubles, driven the way a browser drives it.
Two readings reach past that: the stylesheet the pages link is fetched
against the *shared* asset router, which is the only way "comes from the
shared vocabulary" is observable at all; and the other admin surfaces'
paths are read off their own routers without mounting them, since what
the header must do is *offer* them.

## What is fixed, and what is INVENTED

Fixed by the delta: that both sub-pages carry a breadcrumb whose linked
segment names the Roles list and whose current segment reads `New role`
or the role's title, rendered as the page's own title; that following it
needs no scripting; that all three pages carry the shared header
identifying the roles surface as current; that the pages carry no
page-local style block and load the shared stylesheet; that every action
control carries `row-action` and only **Retire** additionally carries
`danger`.

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a class token, per
  `design.md`'s `class="row-action"`. Correction point: `_carries`.
- That a page's *action controls* are its forms' submit controls. Every
  role action changes state, so each is a submitted form; reading every
  anchor as an action control would wrongly sweep in the header and
  breadcrumb links, which the requirement does not speak about.
  Correction point: `_page_actions`.
- How the header and breadcrumb are located, and how "identifies the
  current surface" is read — the readings
  `test_members_admin_presentation_vocabulary.py` and
  `tests/unit/launch/infrastructure/driving/
  test_playbook_admin_edit_create_breadcrumb.py` established, which
  these correct together with. Correction points: `_header_of`,
  `_breadcrumb_of`, `_ROLES_WORDS`.
- The page module's seams and the store doubles, as
  `test_roles_admin_page.py` records; the files correct together.

## Expected first-run state

Neither the page module nor the role use cases exist, so every test here
fails before its assertions run — the absent-target state.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import (
    members_admin as members_surface,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_surface,
)
from tests.support.admin import ADMIN_IDENTITY, fake_verify
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import Text as _Text
from tests.support.html import ancestors as _ancestors
from tests.support.html import carries as _carries
from tests.support.html import classes as _classes
from tests.support.html import element_disabled as _element_disabled
from tests.support.html import element_hidden as _element_hidden
from tests.support.html import elements as _elements
from tests.support.html import inherited as _inherited
from tests.support.html import nearest as _nearest
from tests.support.html import size as _size
from tests.support.html import tree as _tree

_PAGE_MODULE_NAME: Final = "commerce_ops.access.infrastructure.driving.roles_admin"
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

ROW_ACTION: Final = "row-action"
DANGER: Final = "danger"

SECOND_IDENTITY: Final = "U02BOB"
ADMIN_NAME: Final = "Alice Admin"
SECOND_NAME: Final = "Bob Deputy"

PRINCIPAL: Final = "helen"
THE_CREATING_ADMIN: Final = "the-creating-admin"
THE_EDITING_ADMIN: Final = "the-editing-admin"

DRAFT: Final = "draft"
ACTIVE: Final = "active"

ACTIVE_SLUG: Final = "supply-chain"
ACTIVE_TITLE: Final = "Supply Chain Manager"
DRAFT_SLUG: Final = "managing-director"
DRAFT_TITLE: Final = "Managing Director"
RETIRED_SLUG: Final = "brand"
RETIRED_TITLE: Final = "Brand Manager"

#: LOCATORS, not prohibitions: the words by which each surface's entry in
#: a header is found. A test that cannot find one fails loudly.
_ROLES_WORDS: Final = ("roles", "role")
_MEMBERS_WORDS: Final = ("team", "members", "member")
_PLAYBOOK_WORDS: Final = ("playbook", "step", "steps")

_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")

_RETIRE_HINTS: Final = ("retire",)
_UNRETIRE_HINTS: Final = ("unretire", "un-retire", "restore", "reinstate")
_REMOVE_HOLDER_HINTS: Final = ("remove",)


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}) — the "
            "absent-target state; nothing in this test has been exercised"
        )


def _assets_module() -> ModuleType:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist ({absent}), so the shared "
            "guarded route this requirement is about cannot be driven"
        )


# ---------------------------------------------------------------------------
# Store doubles (see tests/unit/access/application/test_role_writes.py)
# ---------------------------------------------------------------------------


class _Version:
    def __init__(self, value: int = 13) -> None:
        self.value = value


class _FakeMembersStore:
    def __init__(self, version: _Version | None = None) -> None:
        self.rows: tuple[Any, ...] = ()
        self._version = version or _Version()
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    @property
    def version(self) -> int:
        return self._version.value

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self._version.value

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1


class _FakeRolesStore:
    def __init__(self, version: _Version | None = None) -> None:
        self.rows: tuple[Any, ...] = ()
        self._version = version or _Version()
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    @property
    def version(self) -> int:
        return self._version.value

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self._version.value

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1

    async def load_roles(self) -> tuple[tuple[Any, ...], int]:
        return await self.load()

    async def save_roles(self, rows: Any, *, expected_version: int) -> None:
        await self.save(rows, expected_version=expected_version)


class _Collections:
    def __init__(self) -> None:
        version = _Version()
        self.members = _FakeMembersStore(version)
        self.roles = _FakeRolesStore(version)


_MEMBER_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_SLUG_NAMES: Final = ("slug", "identifier", "id")
_TITLE_NAMES: Final = ("title", "name")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("role", "member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _row_field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(f"a stored row exposes no {what} under any of {names}")


def _member_id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if str(_row_field(row, _SLACK_NAMES, "Slack identity")) == identity:
            return _row_field(row, _MEMBER_ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


def _slug_of(row: Any) -> str:
    return str(_row_field(row, _SLUG_NAMES, "slug"))


def _title_of(row: Any) -> str:
    return str(_row_field(row, _TITLE_NAMES, "title"))


# ---------------------------------------------------------------------------
# Role write use cases (see test_role_writes.py)
# ---------------------------------------------------------------------------


def _use_case(names: tuple[str, ...], what: str) -> Any:
    for name in names:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        f"the access application surface exports no {what} use case under any "
        f"of {names} — correct this file's candidate names to the implemented "
        "one"
    )


def _argument_shape(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _attempt(attempts: tuple[Callable[[], Any], ...], what: str) -> Any:
    for call in attempts:
        try:
            return await call()
        except TypeError as error:
            if not _argument_shape(error):
                raise
    pytest.fail(f"no attempted call shape matched the {what} signature")


async def _create_role(
    collections: _Collections,
    *,
    slug: str,
    title: str,
    status: str,
    default_holder: Any = None,
) -> Any:
    step = _use_case(("create_role",), "create-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_CREATING_ADMIN,
        "slug": slug,
        "title": title,
    }
    return await _attempt(
        (
            lambda: step(**common, status=status, default_holder=default_holder),
            lambda: step(**common, status=status, default_holder_id=default_holder),
            lambda: step(**common, status=status, holder=default_holder),
            lambda: step(**common, status=status),
        ),
        "create-a-role",
    )


async def _add_holder(collections: _Collections, slug: str, member_id: Any) -> Any:
    step = _use_case(
        ("add_role_holder", "add_holder", "add_role_member"), "add-a-holder"
    )
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_CREATING_ADMIN,
    }
    return await _attempt(
        (
            lambda: step(**common, slug=slug, member_id=member_id),
            lambda: step(**common, role_slug=slug, member_id=member_id),
            lambda: step(**common, slug=slug, holder=member_id),
        ),
        "add-a-holder",
    )


async def _retire(collections: _Collections, slug: str) -> Any:
    step = _use_case(("retire_role",), "retire-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_EDITING_ADMIN,
    }
    return await _attempt(
        (
            lambda: step(**common, slug=slug),
            lambda: step(**common, role_slug=slug),
        ),
        "retire-a-role",
    )


async def _build() -> _Collections:
    collections = _Collections()
    for name, identity in (
        (ADMIN_NAME, ADMIN_IDENTITY),
        (SECOND_NAME, SECOND_IDENTITY),
    ):
        await create_member(
            members=collections.members,
            principal=THE_CREATING_ADMIN,
            display_name=name,
            slack_identity=identity,
            clickup_user_id=None,
            admin=identity == ADMIN_IDENTITY,
        )
    alice = _member_id_of(collections.members, ADMIN_IDENTITY)
    bob = _member_id_of(collections.members, SECOND_IDENTITY)
    await _create_role(
        collections,
        slug=ACTIVE_SLUG,
        title=ACTIVE_TITLE,
        status=ACTIVE,
        default_holder=alice,
    )
    await _add_holder(collections, ACTIVE_SLUG, bob)
    await _create_role(collections, slug=DRAFT_SLUG, title=DRAFT_TITLE, status=DRAFT)
    await _create_role(
        collections,
        slug=RETIRED_SLUG,
        title=RETIRED_TITLE,
        status=ACTIVE,
        default_holder=alice,
    )
    await _retire(collections, RETIRED_SLUG)
    return collections


def _collections() -> _Collections:
    return asyncio.run(_build())


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


def _all_text(node: _Node) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            parts.append(child.text)
        else:
            parts.append(_all_text(child))
    return " ".join(part for part in parts if part)


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


def _all_controls(root: _Node) -> list[_Node]:
    return [element for element in _elements(root) if _is_action_control(element)]


def _page_actions(root: _Node) -> list[_Node]:
    """The page's action controls.

    INVENTED: a submit control inside a form. Every change this surface
    offers — renaming, adding and removing holders, moving the default,
    and each status transition — changes state, so each is a submitted
    form; reading every anchor as an action control would sweep in the
    header and breadcrumb links, which this requirement does not speak
    about.
    """
    found: list[_Node] = []
    for element in _elements(root):
        if _nearest(element, "form") is None:
            continue
        if (
            element.tag == "button"
            and (element.attrs.get("type") or "submit").lower() == "submit"
            or element.tag == "input"
            and (element.attrs.get("type") or "").lower()
            in (
                "submit",
                "image",
            )
        ):
            found.append(element)
    return found


def _control_haystack(node: _Node) -> str:
    parts: list[str] = [
        node.attrs.get(key, "")
        for key in ("href", "formaction", "name", "value", "aria-label", "title")
    ]
    parts.extend(node.attrs.get(verb, "") for verb in _HX_VERBS)
    parts.append(_all_text(node))
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
    root: _Node, *, hints: tuple[str, ...], excluding: tuple[str, ...], what: str
) -> _Node:
    controls = _page_actions(root)
    found = [
        control
        for control in controls
        if any(hint in _control_haystack(control) for hint in hints)
        and not any(word in _control_haystack(control) for word in excluding)
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} action controls on this page look like the {what} "
            f"action (hints {hints}, excluding {excluding}); the page offers "
            f"{[_control_haystack(c)[:80] for c in controls]}"
        )
    return found[0]


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
    text = _all_text(node).lower()
    return any(word in text for word in words)


def _header_of(root: _Node, *, other_path: str) -> _Node:
    """The page's admin header — the smallest element that links to
    another admin surface, names this one, and does not enclose the
    page's own tables or forms."""
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the page renders no link to {other_path!r} at all, so it carries "
            "no header from which the other admin surfaces are reachable"
        )
    candidates = [
        ancestor
        for link in outbound
        for ancestor in _ancestors(link)
        if _names(ancestor, _MEMBERS_WORDS)
        and ancestor.tag not in ("html", "body", "#document")
        and not any(e.tag in ("table", "form") for e in _elements(ancestor))
    ]
    if not candidates:
        pytest.fail(
            f"the link to {other_path!r} sits in no element that also names "
            "the Team surface without enclosing the page's own tables or "
            "forms — correct `_header_of` or `_MEMBERS_WORDS`"
        )
    return min(candidates, key=_size)


def _offers_in_one_action(node: _Node, path: str) -> bool:
    return any(
        not _inherited(link, _element_disabled)
        and not _inherited(link, _element_hidden)
        for link in _links_to(node, path)
    )


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _identifies_current(header: _Node, *, words: tuple[str, ...]) -> bool:
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


def _breadcrumb_of(root: _Node, *, list_path: str, current: str) -> _Node:
    """The page's breadcrumb — the smallest element carrying a link to
    the Roles list *and* the current segment's text, and enclosing no link
    to a different admin SURFACE (which is what tells it from the header).

    A link to Team is deliberately not disqualifying. Roles are a section of
    the Team surface, so the trail reads `Team > Roles > ...` and its first
    segment is a link there — the breadcrumb's own way back, and the only one
    the roles pages have, since the header marks Team current rather than
    linking it. The playbook link remains disqualifying: only the header
    carries one, so it is what separates the two.
    """
    inbound = _links_to(root, list_path)
    if not inbound:
        pytest.fail(
            f"the page renders no link to the Roles list at {list_path!r}, so "
            "it carries no breadcrumb back to it"
        )
    candidates = [
        ancestor
        for link in inbound
        for ancestor in _ancestors(link)
        if current.lower() in _all_text(ancestor).lower()
        and ancestor.tag not in ("html", "body", "#document")
        and not _links_to(ancestor, _playbook_path())
    ]
    if not candidates:
        pytest.fail(
            f"no element of the page carries both a link to the Roles list and "
            f"the text {current!r} without also carrying the header's links to "
            "other surfaces — correct `_breadcrumb_of` to the implemented page"
        )
    return min(candidates, key=_size)


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


_fake_verify = fake_verify(PRINCIPAL)


def _client(monkeypatch: pytest.MonkeyPatch, collections: _Collections) -> TestClient:
    module = _page_module()
    monkeypatch.setattr(module, "roles", collections.roles)
    monkeypatch.setattr(module, "members", collections.members)
    monkeypatch.setattr(module, "verify_admin_session", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
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


def _list_path() -> str:
    return _shortest_get_route(_page_module().router)


def _members_path() -> str:
    return _shortest_get_route(members_surface.router)


def _playbook_path() -> str:
    return _shortest_get_route(playbook_surface.router)


def _resolve(url: str) -> str:
    if not url:
        return _list_path()
    if url.startswith("/"):
        return url
    return urljoin(_list_path() + "/", url)


def _get(client: TestClient, path: str | None = None) -> str:
    response = client.get(_resolve(path or _list_path()))
    assert response.status_code == 200, response.text
    return response.text


def _links(root: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a" and element.attrs.get("href")
    ]


def _role_page_path(client: TestClient, title: str) -> str:
    """The path of one role's own page, discovered through its title link
    on the list."""
    for link in _links(_tree(_get(client))):
        if _all_text(link).strip() == title:
            return _resolve(link.attrs["href"])
    pytest.fail(
        f"the Roles list offers no link whose text is {title!r}, so that "
        "role's own page cannot be reached"
    )


def _create_page_path(client: TestClient) -> str:
    for link in _links(_tree(_get(client))):
        haystack = (link.attrs["href"] + " " + _all_text(link)).lower()
        if any(word in haystack for word in ("new", "create", "add")):
            path = _resolve(link.attrs["href"])
            response = client.get(path)
            if response.status_code == 200 and any(
                "slug" in element.attrs.get("name", "").lower()
                for element in _elements(_tree(response.text))
            ):
                return path
    pytest.fail("the Roles page offers no link reaching a create page")


def _assets_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    module = _assets_module()
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _every_roles_page(
    client: TestClient,
) -> tuple[tuple[str, str], ...]:
    """The three pages of the Roles surface, each with a label."""
    return (
        ("the list", _get(client)),
        ("the create page", _get(client, _create_page_path(client))),
        (
            "a role's own page",
            _get(client, _role_page_path(client, ACTIVE_TITLE)),
        ),
    )


# ===========================================================================
# Requirement: The create page and a role's own page carry a breadcrumb back
# to the list
# ===========================================================================


def test_a_roles_page_offers_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A role's page offers the list.

    WHEN a role's own page is rendered
    THEN it carries a breadcrumb naming the Roles list as a link and the
    role's title as the current, un-linked segment.

    The requirement adds that the current segment is rendered as the
    page's own title, so the page carries no separate title beside it —
    asserted as the title appearing once outside the breadcrumb's own
    link, rather than twice.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _get(client, _role_page_path(client, ACTIVE_TITLE))
    crumb = _breadcrumb_of(_tree(page), list_path=_list_path(), current=ACTIVE_TITLE)

    # SPECIFIED: the Roles list is named as a link.
    assert _offers_in_one_action(crumb, _list_path()), (
        "the breadcrumb renders no live link back to the Roles list"
    )
    # SPECIFIED: the role's title is the current, un-linked segment.
    linked_text = " ".join(_all_text(link) for link in _links_to(crumb, _list_path()))
    assert ACTIVE_TITLE not in linked_text, (
        "the role's title is rendered as the breadcrumb's link rather than as "
        "its current segment"
    )
    assert ACTIVE_TITLE in _all_text(crumb), (
        f"the breadcrumb does not name {ACTIVE_TITLE!r} at all: {_all_text(crumb)!r}"
    )
    title_links = [
        link for link in _links(_tree(page)) if _all_text(link).strip() == ACTIVE_TITLE
    ]
    assert title_links == [], (
        "the role's title is a link on its own page; the current segment is un-linked"
    )


def test_the_create_page_offers_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The create page offers the list.

    WHEN the create page is rendered
    THEN it carries a breadcrumb naming the Roles list as its linked
    segment and `New role` as its current, un-linked segment.

    `New role` is the delta's own literal, so it is asserted literally
    rather than as a family of words.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _get(client, _create_page_path(client))
    crumb = _breadcrumb_of(_tree(page), list_path=_list_path(), current="New role")

    # SPECIFIED: the Roles list as its linked segment.
    assert _offers_in_one_action(crumb, _list_path())
    # SPECIFIED: `New role` as its current, un-linked segment.
    text = _all_text(crumb)
    assert "New role" in text, f"the breadcrumb does not read `New role`: {text!r}"
    linked_text = " ".join(_all_text(link) for link in _links_to(crumb, _list_path()))
    assert "New role" not in linked_text, (
        "`New role` is rendered as the breadcrumb's link rather than as its "
        "current segment"
    )


def test_the_breadcrumb_needs_no_scripting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The breadcrumb needs no scripting.

    WHEN a role's page is rendered and its breadcrumb link is followed
    without scripting
    THEN the Roles list is reached.

    "Without scripting" is asserted by following a plain `href` with a
    GET — no `hx-*` attribute consulted — and reading what comes back:
    the list, holding every role.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _get(client, _role_page_path(client, ACTIVE_TITLE))
    crumb = _breadcrumb_of(_tree(page), list_path=_list_path(), current=ACTIVE_TITLE)
    links = _links_to(crumb, _list_path())
    assert links, "the breadcrumb carries no link to the Roles list"

    href = links[0].attrs["href"]
    assert href, "the breadcrumb's segment carries no plain href to follow"
    response = client.get(_resolve(href))

    # SPECIFIED: the Roles list is reached.
    assert response.status_code == 200, response.text
    for slug in (ACTIVE_SLUG, DRAFT_SLUG, RETIRED_SLUG):
        assert slug in response.text, (
            f"following the breadcrumb did not reach the Roles list ({slug!r} "
            "is not on the response)"
        )


# ===========================================================================
# Requirement: The Roles pages carry the shared admin header
# ===========================================================================


def test_every_other_admin_surface_is_reachable_from_the_roles_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Every other admin surface is reachable from the roles
    surface.

    WHEN the Roles page is rendered
    THEN its header offers each admin surface the session can reach in
    one action
    AND identifies Team as the surface currently viewed.

    Roles are a SECTION of the Team surface, not a surface of their own
    (`roles-admin`, *The Roles pages sit inside the Team surface*): a
    role's holders are members and both collections live in one module,
    so the header — which names surfaces — identifies Team here, and the
    roles listing is reached from Team's own secondary navigation.

    The playbook page is named explicitly because a header offering only
    one other surface would satisfy a test looking for "any other".
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    header = _header_of(_tree(_get(client)), other_path=_playbook_path())

    # SPECIFIED: each other surface, in one action and without scripting.
    # Team is NOT among them: roles are a section of it, so the header marks
    # Team as the surface currently viewed rather than linking to it. The way
    # back to the members list is Team's own section navigation, asserted by
    # `test_the_members_list_is_reachable_from_the_roles_pages` below.
    assert _offers_in_one_action(header, _playbook_path()), (
        "the Roles page's header offers no live link to the playbook surface "
        f"at {_playbook_path()!r}"
    )
    # SPECIFIED: and identifies Team as the surface currently viewed.
    assert _identifies_current(header, words=_MEMBERS_WORDS), (
        "the header does not identify Team as the surface being viewed "
        f"(header: {_all_text(header)[:300]!r})"
    )
    # SPECIFIED: the header carries no roles entry at all.
    assert not _offers_in_one_action(header, _list_path()), (
        "the admin header offers the roles listing — roles are a section of "
        "the Team surface, not a surface of their own, and the header names "
        "surfaces"
    )


def test_the_header_is_rendered_on_an_empty_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The header is rendered on an empty collection.

    WHEN the Roles page is rendered holding no roles at all
    THEN the header is still rendered and still offers the other admin
    surfaces.

    Reachability that depended on the collection the page lists would
    strand an admin on the one page where they have least to do.
    """
    collections = _Collections()
    client = _client(monkeypatch, collections)

    html = _get(client)

    # DERIVED guard: the collection really holds nothing, so the header
    # below is read off an empty page.
    for slug in (ACTIVE_SLUG, DRAFT_SLUG, RETIRED_SLUG):
        assert slug not in html
    header = _header_of(_tree(html), other_path=_playbook_path())
    # SPECIFIED: still rendered, still offering the other surfaces.
    # The playbook surface, not Team: Team is the surface these pages belong
    # to, so the header marks it current rather than linking to it.
    assert _offers_in_one_action(header, _playbook_path())
    assert _offers_in_one_action(header, _playbook_path())


def test_a_roles_own_page_carries_the_header_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A role's own page carries the header too.

    WHEN a role's page is rendered
    THEN it carries the same header, offering the other admin surfaces
    in one action.

    A sub-page rendered without it is a page from which the rest of the
    admin is unreachable.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _get(client, _role_page_path(client, ACTIVE_TITLE))
    header = _header_of(_tree(page), other_path=_playbook_path())

    # SPECIFIED: the same header, offering the other surfaces in one action.
    # The playbook surface, not Team: Team is the surface these pages belong
    # to, so the header marks it current rather than linking to it.
    assert _offers_in_one_action(header, _playbook_path())
    assert _identifies_current(header, words=_MEMBERS_WORDS)


def test_the_create_page_carries_the_header_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The create page carries the header too.

    WHEN the create page is rendered
    THEN it carries the same header, offering the other admin surfaces
    in one action.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _get(client, _create_page_path(client))
    header = _header_of(_tree(page), other_path=_playbook_path())

    # SPECIFIED: the same header, offering the other surfaces in one action.
    # The playbook surface, not Team: Team is the surface these pages belong
    # to, so the header marks it current rather than linking to it.
    assert _offers_in_one_action(header, _playbook_path())
    assert _offers_in_one_action(header, _playbook_path())


# ===========================================================================
# Requirement: The Roles pages' presentation comes from the shared admin
# vocabulary
# ===========================================================================


def test_the_pages_carry_no_styling_of_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The pages carry no styling of their own.

    WHEN any Roles surface is rendered
    THEN it loads the shared admin stylesheet
    AND carries no page-local style block.

    "Any Roles surface" is all three pages, asserted one by one — a new
    surface built to the pattern can acquire a page-local block on one
    of its pages as easily as on all of them.

    "The shared admin stylesheet" is asserted by fetching what each page
    links against an app mounting the *shared* asset router alone: a
    page linking a stylesheet of its own would not be served there.

    DELIBERATELY UNTESTED: inline `style` attributes on individual
    elements. The scenario says "carries no page-local style block", and
    asserting the absence of every inline attribute would oblige an
    implementer to a constraint nobody stated — the same bound
    `test_members_admin_presentation_vocabulary.py` recorded.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    shared = _assets_client(monkeypatch)

    for what, page in _every_roles_page(client):
        root = _tree(page)
        hrefs = _stylesheet_hrefs(root)
        # SPECIFIED: it loads a stylesheet at all …
        assert hrefs, (
            f"{what} links no stylesheet, so its presentation comes from nowhere shared"
        )
        # SPECIFIED: … and carries no page-local style block.
        blocks = _style_blocks(root)
        assert blocks == [], (
            f"{what} carries {len(blocks)} inline <style> block(s), so a "
            "presentation fix applied to another admin surface silently does "
            "not apply here"
        )
        # SPECIFIED: the stylesheet it loads is the shared one.
        for href in hrefs:
            assert not href.startswith(("http://", "https://", "//")), (
                f"{what} loads {href!r} from off the machine"
            )
            served = shared.get(_resolve(href))
            assert served.status_code == 200, (
                f"{what} links {href!r}, which the shared asset route answers "
                f"{served.status_code} for"
            )


def test_the_destructive_action_is_distinguished_not_amplified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The destructive action is distinguished, not amplified.

    WHEN an active role's page is rendered
    THEN its retire control carries `danger`
    AND no other control on that page carries it.

    The requirement's own prose adds that every action control carries
    `row-action`, the destructive one included, which is asserted
    alongside — a retire control marked `danger` but not `row-action`
    would speak half the vocabulary.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    root = _tree(_get(client, _role_page_path(client, ACTIVE_TITLE)))
    retire = _one_action(
        root, hints=_RETIRE_HINTS, excluding=_UNRETIRE_HINTS, what="retire"
    )

    # SPECIFIED: the retire control carries `danger`.
    assert _carries(retire, DANGER), (
        f"the retire control on the active role's page carries no {DANGER!r} "
        f"marker (classes: {sorted(_classes(retire))})"
    )
    # SPECIFIED: and no other control on that page carries it.
    others = [
        control
        for control in _all_controls(root)
        if control is not retire and _carries(control, DANGER)
    ]
    assert others == [], (
        f"{len(others)} controls other than retire carry {DANGER!r}: "
        f"{[_control_haystack(c)[:60] for c in others]}"
    )
    # SPECIFIED (requirement prose): every action control carries
    # `row-action`.
    unmarked = [
        control for control in _page_actions(root) if not _carries(control, ROW_ACTION)
    ]
    assert unmarked == [], (
        f"{len(unmarked)} action controls on the role's page carry no "
        f"{ROW_ACTION!r} marker: "
        f"{[_control_haystack(c)[:60] for c in unmarked]}"
    )


def test_un_retiring_is_not_destructive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Un-retiring is not destructive.

    WHEN a retired role's page is rendered
    THEN its un-retire control carries `row-action`
    AND does not carry `danger`.

    Restoring a role destroys nothing, and marking it `danger` alongside
    retirement would flatten the distinction the marker exists to draw.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    root = _tree(_get(client, _role_page_path(client, RETIRED_TITLE)))
    unretire = _one_action(root, hints=_UNRETIRE_HINTS, excluding=(), what="un-retire")

    # SPECIFIED: it carries `row-action`.
    assert _carries(unretire, ROW_ACTION), (
        f"the un-retire control carries no {ROW_ACTION!r} marker (classes: "
        f"{sorted(_classes(unretire))})"
    )
    # SPECIFIED: and does not carry `danger`.
    assert not _carries(unretire, DANGER), (
        f"the un-retire control carries {DANGER!r}, marking a restoring action "
        "as the destructive one"
    )


def test_removing_a_holder_is_not_destructive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Removing a holder is not destructive.

    WHEN a role's page is rendered offering a holder's removal
    THEN that control carries `row-action`
    AND does not carry `danger`.

    Removing a holder takes nothing away that cannot be restored by
    adding the member back, which is the delta's own reason for the
    distinction.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    root = _tree(_get(client, _role_page_path(client, ACTIVE_TITLE)))
    remove = _one_action(
        root,
        hints=_REMOVE_HOLDER_HINTS,
        excluding=_RETIRE_HINTS + _UNRETIRE_HINTS,
        what="remove-a-holder",
    )

    # SPECIFIED: it carries `row-action`.
    assert _carries(remove, ROW_ACTION), (
        f"the remove-a-holder control carries no {ROW_ACTION!r} marker "
        f"(classes: {sorted(_classes(remove))})"
    )
    # SPECIFIED: and does not carry `danger`.
    assert not _carries(remove, DANGER), (
        f"the remove-a-holder control carries {DANGER!r}, flattening the "
        "distinction the marker exists to draw"
    )
