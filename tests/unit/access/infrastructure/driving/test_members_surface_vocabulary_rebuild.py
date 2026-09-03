"""The rebuilt Team surface's share of the admin presentation vocabulary,
and the header it now carries on all three pages (`members-admin`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/members-admin/spec.md`
— two of its five MODIFIED requirements, twelve scenarios:

- MODIFIED *The page's presentation comes from the shared admin
  vocabulary* (7)
- MODIFIED *The page carries a header from which the other admin surface
  is reachable* (5)

Five of those twelve are **not** written here, because the revision does
not touch what they observe and the tests already covering them stay
valid and unweakened:

- *The stylesheet is refused without an admin session* — covered by
  `test_members_admin_presentation_vocabulary.py::test_the_stylesheet_is_refused_without_an_admin_session`
- *The playbook page is reachable from the membership* — covered by
  `test_members_admin_presentation_vocabulary.py::test_the_playbook_page_is_reachable_from_the_members`
- *The header is rendered on a membership holding nobody* — covered by
  `test_members_admin_presentation_vocabulary.py::test_the_header_is_rendered_on_a_members_holding_nobody`
- *Every other admin surface is reachable from the membership* — covered
  by `test_members_header_names_every_surface.py::test_every_other_admin_surface_is_reachable_from_the_members`
- *A surface added later is named by the header* — covered by
  `test_members_header_names_every_surface.py` for the launch and
  product surfaces. The roles surface is the case in point this change
  adds, and the requirement's own prose names it, so it is asserted here
  as its own test rather than left to a generalisation written before it
  existed.

The manifest at
`openspec/changes/rebuild-the-member-directory/test-manifest.md` records
that accounting scenario by scenario, together with the three existing
vocabulary tests this change makes obsolete by moving what they observe
from a member's row onto the member's own page. This pass edits and
deletes none of them.

## Level

The Team surface's routes over a membership-store double, plus two
readings that reach past it: the stylesheet each page links is fetched
against the *shared* asset router, and the roles surface's path is read
off its own router without mounting it, since what the header must do is
*offer* it.

## What is fixed, and what is INVENTED

Fixed by the delta: the literal marker tokens `row-action` and `danger`;
that `Deactivate` is this surface's destructive action while reactivating
and creating are not; that the markers now sit on the create page and on
each member's own page and a row carries neither; that no Team surface
page carries a page-local style block; that the `display: contents`
workaround rule is removed with the row actions it worked around; and
that all three pages carry the header.

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a class token, per
  `design.md`'s `class="row-action"`. Correction point: `_carries`.
- That a page's *action controls* are its forms' submit controls.
  Reading every anchor as one would sweep in the header and breadcrumb
  links, which this requirement does not speak about. Correction point:
  `_page_actions`.
- How the workaround rule is recognised in the served stylesheet: a rule
  whose selector mentions both a form and an actions cell and whose body
  sets `display: contents`. Correction point:
  `_workaround_rules`.
- The page module's seams, the store double and the header reading, as
  `test_members_admin_presentation_vocabulary.py` records; the files
  correct together.

## Expected first-run state

The Team page today carries its markers on each member's row and no
create page or member page at all, so these tests fail on a *wrong
value* — the page renders and what is asserted of it is not there —
except the roles-header test, which fails on an *absent target* because
the roles module does not exist. The manifest records which is which.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import asyncio
import importlib
import re
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member, deactivate_member
from commerce_ops.access.infrastructure.driving import members_admin as page_module
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_surface,
)
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

_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"
_ROLES_MODULE_NAME: Final = "commerce_ops.access.infrastructure.driving.roles_admin"

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

EVERY_IDENTITY: Final = (
    ADMIN_IDENTITY,
    SECOND_ADMIN_IDENTITY,
    MEMBER_IDENTITY,
    RETIRED_IDENTITY,
)
EVERY_NAME: Final = (ADMIN_NAME, SECOND_ADMIN_NAME, MEMBER_NAME, RETIRED_NAME)

PRINCIPAL: Final = "helen"
THE_CREATING_ADMIN: Final = "the-creating-admin"
THE_EDITING_ADMIN: Final = "the-editing-admin"

_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

_DEACTIVATE_HINTS: Final = ("deactivat",)
_REACTIVATE_HINTS: Final = ("reactivat", "restore", "reinstate")

#: LOCATORS, not prohibitions: the words by which each surface's entry in
#: a header is found.
_MEMBERS_WORDS: Final = ("team", "members", "member")
_ROLES_WORDS: Final = ("roles", "role")

_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")


#: Structures a row never encloses. Used to tell a row from a whole-page
#: wrapper that happens to name one member.
_NOT_A_ROW: Final = (
    "html",
    "body",
    "head",
    "main",
    "table",
    "nav",
    "header",
    "footer",
    "h1",
    "h2",
    "link",
    "style",
)


def _assets_module() -> ModuleType:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist ({absent}), so the shared "
            "stylesheet this requirement is about cannot be driven"
        )


def _roles_module() -> ModuleType:
    try:
        return importlib.import_module(_ROLES_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_ROLES_MODULE_NAME} does not exist ({absent}), so there is no "
            "roles surface for the Team header to name — the absent-target "
            "state; nothing below has been exercised"
        )


# ---------------------------------------------------------------------------
# The members store double (see test_members_admin_page.py)
# ---------------------------------------------------------------------------


class _FakeMembersStore:
    def __init__(self, version: int = 13) -> None:
        self.rows: tuple[Any, ...] = ()
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(f"a stored row exposes no {what} under any of {names}")


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if str(_field(row, _SLACK_NAMES, "Slack identity")) == identity:
            return _field(row, _ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


async def _build() -> _FakeMembersStore:
    store = _FakeMembersStore()
    for name, identity, admin in (
        (ADMIN_NAME, ADMIN_IDENTITY, True),
        (SECOND_ADMIN_NAME, SECOND_ADMIN_IDENTITY, True),
        (MEMBER_NAME, MEMBER_IDENTITY, False),
        (RETIRED_NAME, RETIRED_IDENTITY, False),
    ):
        await create_member(
            members=store,
            principal=THE_CREATING_ADMIN,
            display_name=name,
            slack_identity=identity,
            clickup_user_id=None,
            admin=admin,
        )
    await deactivate_member(
        members=store,
        principal=THE_EDITING_ADMIN,
        member_id=_id_of(store, RETIRED_IDENTITY),
    )
    return store


def _store() -> _FakeMembersStore:
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


def _attribute_text(node: _Node) -> str:
    parts = [_all_text(node)]
    for element in [node, *_elements(node)]:
        parts.extend(element.attrs.values())
    return " ".join(parts).lower()


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
    found = [root] if _is_action_control(root) else []
    found.extend(element for element in _elements(root) if _is_action_control(element))
    return found


def _page_actions(root: _Node) -> list[_Node]:
    """The page's action controls: a submit control inside a form.

    Every change this surface offers — creating, editing, deactivating
    and reactivating — changes state, so each is a submitted form.
    Reading every anchor as an action control would sweep in the header
    and breadcrumb links, which this requirement does not speak about.
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


def _links(root: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a" and element.attrs.get("href")
    ]


def _links_to(root: _Node, path: str) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and urlsplit(element.attrs.get("href", "")).path == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _names(node: _Node, words: tuple[str, ...]) -> bool:
    text = _all_text(node).lower()
    return any(word in text for word in words)


def _header_of(root: _Node, *, other_path: str) -> _Node:
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
            "this surface without enclosing the page's own tables or forms — "
            "correct `_header_of` or `_MEMBERS_WORDS`"
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


def _member_row(root: _Node, identity: str, name: str) -> _Node:
    """The one member's own region of the list — the **largest** element
    naming this member and no other that encloses none of the structures
    a row never encloses.

    Largest rather than smallest deliberately: the smallest such element
    is a leaf cell carrying no controls whatever the page does, so a
    marker assertion read off it would pass by construction.
    """
    others = [
        other.lower()
        for other in EVERY_IDENTITY + EVERY_NAME
        if other not in (identity, name)
    ]
    candidates = [
        element
        for element in _elements(root)
        if identity.lower() in _attribute_text(element)
        and not any(other in _attribute_text(element) for other in others)
        and element.tag not in _NOT_A_ROW
        and not any(child.tag in _NOT_A_ROW for child in _elements(element))
    ]
    if not candidates:
        pytest.fail(
            f"no element of the page names {identity!r} without naming another "
            "member, so that member's row cannot be isolated"
        )
    return max(candidates, key=_size)


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _client(monkeypatch: pytest.MonkeyPatch, store: _FakeMembersStore) -> TestClient:
    # The Team list reads the role collection for the roles column.
    # `main.py` binds the real Postgres store to this module at import,
    # and that outlives whichever test imported it — so it is pinned to
    # one this test controls. `None` renders the column empty.
    monkeypatch.setattr(page_module, "roles", None, raising=False)
    monkeypatch.setattr(page_module, "members", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    app = FastAPI()
    app.include_router(page_module.router)
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
    return _shortest_get_route(page_module.router)


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


def _create_form_in(html: str) -> bool:
    for element in _elements(_tree(html)):
        if element.tag != "form":
            continue
        names = " ".join(
            child.attrs.get("name", "")
            for child in _elements(element)
            if child.tag in ("input", "select", "textarea")
        ).lower()
        if "name" in names and "slack" in names:
            return True
    return False


def _create_page_path(client: TestClient) -> str:
    for link in _links(_tree(_get(client))):
        haystack = (link.attrs["href"] + " " + _all_text(link)).lower()
        if any(word in haystack for word in ("new", "create", "add")):
            path = _resolve(link.attrs["href"])
            response = client.get(path)
            if response.status_code == 200 and _create_form_in(response.text):
                return path
    pytest.fail(
        "the Team list offers no link reaching a create page carrying a "
        "display-name field and a Slack-identity field"
    )


def _member_page_path(client: TestClient, identity: str, name: str) -> str:
    row = _member_row(_tree(_get(client)), identity, name)
    for link in _links(row):
        if name.lower() in _all_text(link).lower():
            return _resolve(link.attrs["href"])
    pytest.fail(
        f"{identity!r}'s row offers no link whose text is their display name, "
        "so the member's own page cannot be reached in one action"
    )


def _assets_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    module = _assets_module()
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _every_team_page(client: TestClient) -> tuple[tuple[str, str], ...]:
    return (
        ("the list", _get(client)),
        ("the create page", _get(client, _create_page_path(client))),
        (
            "a member's own page",
            _get(client, _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME)),
        ),
    )


def _actions_cell_form_rules(stylesheet: str) -> list[tuple[str, str]]:
    """Every rule whose selector reaches a form inside a table's actions
    cell, as (selector, normalised body).

    Comments are stripped first: the stylesheet's own commentary
    discusses `display: contents` in prose, and a parser that read it as
    a declaration would report a rule that is not there.

    INVENTED recognition: a selector mentioning both a form and an
    actions *cell* — `actions`, plural, which is how the cell is named
    and which does not match the `row-action` marker a neighbouring
    surface's own rules select on. What the delta forbids is the rule,
    not a spelling of it.
    """
    without_comments = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    found: list[tuple[str, str]] = []
    for chunk in without_comments.split("}"):
        selector, brace, body = chunk.partition("{")
        if not brace:
            continue
        lowered = selector.lower()
        if "form" in lowered and "actions" in lowered:
            found.append((" ".join(selector.split()), re.sub(r"\s+", "", body).lower()))
    return found


# ===========================================================================
# MODIFIED requirement: The page's presentation comes from the shared admin
# vocabulary
# ===========================================================================


def test_every_team_surface_page_carries_no_styling_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The page carries no styling of its own.

    WHEN any Team surface page is rendered
    THEN it loads the shared admin stylesheet
    AND carries no page-local style block.

    The revision widens this from the Team page to *any* Team surface
    page, so all three are asserted one by one — a rebuild can acquire a
    page-local block on one of the two pages it adds as easily as on the
    one it already had.

    DELIBERATELY UNTESTED: inline `style` attributes on individual
    elements, the bound
    `test_members_admin_presentation_vocabulary.py` already recorded.
    """
    client = _client(monkeypatch, _store())
    shared = _assets_client(monkeypatch)

    for what, page in _every_team_page(client):
        root = _tree(page)
        hrefs = _stylesheet_hrefs(root)
        # SPECIFIED: it loads a stylesheet at all …
        assert hrefs, f"{what} links no stylesheet"
        # SPECIFIED: … and carries no page-local style block.
        blocks = _style_blocks(root)
        assert blocks == [], (
            f"{what} carries {len(blocks)} inline <style> block(s), so a "
            "presentation fix applied to another admin surface silently does "
            "not apply here"
        )
        # SPECIFIED: the stylesheet it loads is the shared one.
        for href in hrefs:
            served = shared.get(_resolve(href))
            assert served.status_code == 200, (
                f"{what} links {href!r}, which the shared asset route answers "
                f"{served.status_code} for"
            )


def test_the_destructive_action_is_distinguished_not_amplified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The destructive action is distinguished, not amplified.

    WHEN an active member's own page is rendered
    THEN its deactivate control carries `danger`
    AND no other control on that page carries it.

    The revision moves the observation from the member's *row* to their
    own page. The requirement's prose adds that every action control
    carries `row-action`, the destructive one included, which is
    asserted alongside.
    """
    client = _client(monkeypatch, _store())

    root = _tree(_get(client, _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME)))
    deactivate = _one_action(
        root, hints=_DEACTIVATE_HINTS, excluding=_REACTIVATE_HINTS, what="deactivate"
    )

    # SPECIFIED: the deactivate control carries `danger`.
    assert _carries(deactivate, DANGER), (
        "the deactivate control on the member's own page carries no "
        f"{DANGER!r} marker (classes: {sorted(_classes(deactivate))})"
    )
    # SPECIFIED: and no other control on that page carries it.
    others = [
        control
        for control in _all_controls(root)
        if control is not deactivate and _carries(control, DANGER)
    ]
    assert others == [], (
        f"{len(others)} controls other than deactivate carry {DANGER!r} on the "
        f"member's page: {[_control_haystack(c)[:60] for c in others]}"
    )
    # SPECIFIED (requirement prose): every action control carries
    # `row-action`.
    unmarked = [
        control for control in _page_actions(root) if not _carries(control, ROW_ACTION)
    ]
    assert unmarked == [], (
        f"{len(unmarked)} action controls on the member's page carry no "
        f"{ROW_ACTION!r} marker: "
        f"{[_control_haystack(c)[:60] for c in unmarked]}"
    )


def test_a_deactivated_members_action_is_not_destructive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A deactivated member's action is not destructive.

    WHEN a deactivated member's own page is rendered
    THEN its reactivate control carries `row-action`
    AND does not carry `danger`.

    Restoring somebody destroys nothing.
    """
    client = _client(monkeypatch, _store())

    root = _tree(
        _get(client, _member_page_path(client, RETIRED_IDENTITY, RETIRED_NAME))
    )
    reactivate = _one_action(
        root, hints=_REACTIVATE_HINTS, excluding=(), what="reactivate"
    )

    # SPECIFIED: it carries `row-action`.
    assert _carries(reactivate, ROW_ACTION), (
        f"the reactivate control carries no {ROW_ACTION!r} marker (classes: "
        f"{sorted(_classes(reactivate))})"
    )
    # SPECIFIED: and does not carry `danger`.
    assert not _carries(reactivate, DANGER), (
        f"the reactivate control carries {DANGER!r}, marking a restoring "
        "action as the destructive one"
    )


def test_the_create_control_speaks_the_same_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The create control speaks the same vocabulary.

    WHEN the create page is rendered
    THEN its submit control carries `row-action`
    AND does not carry `danger`.

    The revision moves this from a form at the top of the list onto the
    create page, which is where the control now lives.
    """
    client = _client(monkeypatch, _store())

    root = _tree(_get(client, _create_page_path(client)))
    submits = _page_actions(root)
    assert submits, (
        "the create page renders no submit control, so there is no create "
        "action to read a vocabulary off"
    )
    for submit in submits:
        # SPECIFIED: it carries `row-action`.
        assert _carries(submit, ROW_ACTION), (
            "the create page's submit carries no "
            f"{ROW_ACTION!r} marker (classes: {sorted(_classes(submit))})"
        )
        # SPECIFIED: and does not carry `danger`. Creating destroys
        # nothing.
        assert not _carries(submit, DANGER), (
            f"the create page's submit carries {DANGER!r}"
        )


@pytest.mark.parametrize(
    ("identity", "name"),
    [
        pytest.param(MEMBER_IDENTITY, MEMBER_NAME, id="active"),
        pytest.param(RETIRED_IDENTITY, RETIRED_NAME, id="deactivated"),
    ],
)
def test_a_row_carries_neither_marker(
    monkeypatch: pytest.MonkeyPatch, identity: str, name: str
) -> None:
    """Scenario: A row carries neither marker.

    WHEN any member's row is rendered on the list
    THEN it carries no control marked `row-action` and none marked
    `danger`.

    A row has no action controls left to mark. This is the vocabulary
    half of the row-carries-no-actions rebuild, and it fails today: the
    Team page marks a deactivate control `row-action danger` on every
    active member's row.
    """
    client = _client(monkeypatch, _store())

    row = _member_row(_tree(_get(client)), identity, name)

    for marker in (ROW_ACTION, DANGER):
        marked = [
            control for control in _all_controls(row) if _carries(control, marker)
        ]
        assert marked == [], (
            f"{identity!r}'s row carries {len(marked)} control(s) marked "
            f"{marker!r}: {[_control_haystack(c)[:60] for c in marked]}"
        )


def test_the_workaround_rule_is_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The workaround rule is gone.

    WHEN the shared admin stylesheet is served
    THEN it carries no rule setting a form inside a table's actions cell
    to `display: contents`.

    **A defect in the change's artifacts, reported and not resolved
    here.** The scenario, `proposal.md` and `tasks.md` 8.5 all name the
    rule as `td.actions form { display: contents }`. The rule the served
    stylesheet actually carries is `td.actions form { display: inline;
    margin: 0 }`, and its own comment records that `display: contents`
    "was the first approach" and was replaced. So the scenario as
    literally stated is already satisfied and would pass whether or not
    this change happened — the fourth failure state, an assertion that
    establishes nothing.

    It is asserted literally all the same, because that is what the
    delta says, and *alongside* it the requirement's own sentence —
    "rather than left behind as a rule matching nothing" (`tasks.md` 8.5:
    "confirm no rule matching nothing is left behind") — which is what
    actually discriminates: with the row actions gone, no rule selecting
    a form inside an actions cell should remain at all. That second
    assertion is marked DERIVED and is the one that fails today.

    The stylesheet asserted on is the one the Team page itself links, so
    this is the asset *this surface* reaches for rather than one this
    file named.
    """
    client = _client(monkeypatch, _store())
    shared = _assets_client(monkeypatch)

    hrefs = _stylesheet_hrefs(_tree(_get(client)))
    assert hrefs, "the Team page links no stylesheet to inspect"

    checked = 0
    for href in hrefs:
        served = shared.get(_resolve(href))
        assert served.status_code == 200, (
            f"{href!r} is not served by the shared asset route ({served.status_code})"
        )
        checked += 1
        rules = _actions_cell_form_rules(served.text)
        # SPECIFIED, literally: no such rule sets `display: contents`.
        collapsing = [
            selector for selector, body in rules if "display:contents" in body
        ]
        assert collapsing == [], (
            f"{href!r} still carries {collapsing!r}, collapsing a form inside "
            "a table's actions cell"
        )
        # DERIVED, from "rather than left behind as a rule matching
        # nothing": with the row actions gone, no rule selecting a form
        # inside an actions cell remains at all.
        assert rules == [], (
            f"{href!r} still carries {[s for s, _ in rules]!r}; the rule goes "
            "with the row actions it was working around, rather than being "
            "left behind matching nothing"
        )
    assert checked, "no stylesheet was actually fetched, so nothing was checked"


# ===========================================================================
# MODIFIED requirement: The page carries a header from which the other admin
# surface is reachable
# ===========================================================================


def test_the_create_page_and_a_members_page_carry_the_header_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The create page and a member's page carry the header
    too.

    WHEN the create page or a member's own page is rendered
    THEN it carries the same header, offering the other admin surfaces
    in one action.

    This is the widening the revision makes: the requirement was written
    when the Team surface was one page and said "The Team page". A
    create page or a member's page rendered without the header would be
    a page from which the rest of the admin is unreachable — the gap
    this requirement exists to close, reopened on the two pages the
    rebuild adds.
    """
    client = _client(monkeypatch, _store())

    for what in ("the create page", "a member's own page"):
        page = dict(_every_team_page(client))[what]
        header = _header_of(_tree(page), other_path=_playbook_path())
        # SPECIFIED: the same header, offering the other surfaces in one
        # action.
        assert _offers_in_one_action(header, _playbook_path()), (
            f"{what} renders no live link to the playbook surface, so an "
            "admin who reaches it cannot get anywhere else"
        )
        # SPECIFIED (carried forward): it still identifies the membership
        # as the surface being viewed.
        assert _identifies_current(header, words=_MEMBERS_WORDS), (
            f"{what}'s header does not identify the membership as the surface "
            "currently viewed"
        )


def test_the_roles_listing_is_reached_from_the_members_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The roles listing is reached from the members listing.

    WHEN the Team page is rendered
    THEN the heading of the column presenting each member's roles offers
    the roles listing in one action.

    The link sits on the column it explains rather than in a navigation
    bar above the page: a reader looking at which roles a member holds is
    already looking at the subject the roles listing is about
    (`roles-admin`, *The Roles pages sit inside the Team surface*).

    Asserted in both directions — that the roles listing IS offered, and
    that it is not offered from the admin header, which names surfaces and
    of which roles are not one. Dropping the header entry without adding
    the column link would strand the roles pages entirely.
    """
    store = _store()
    monkeypatch.setattr(page_module, "roles", None, raising=False)
    client = _client(monkeypatch, store)
    tree = _tree(_get(client))

    roles_path = _roles_list_path()
    offered = [
        element
        for element in _elements(tree)
        if element.tag == "a" and element.attrs.get("href") == roles_path
    ]
    assert offered, (
        f"the Team page offers no link to the roles listing at {roles_path!r}, "
        "so the roles pages are unreachable from the surface they belong to"
    )

    # SPECIFIED: it is the roles COLUMN HEADING that offers it.
    in_a_heading = [
        link
        for link in offered
        if any(ancestor.tag == "th" for ancestor in _ancestors(link))
    ]
    assert in_a_heading, (
        "the roles listing is linked from the Team page, but not from a column "
        "heading — the requirement puts the link on the column it explains"
    )

    # SPECIFIED (by omission): not from the admin header, which names surfaces.
    header = next(
        (element for element in _elements(tree) if element.tag == "header"),
        None,
    )
    if header is not None:
        assert not [
            link
            for link in _elements(header)
            if link.tag == "a" and link.attrs.get("href") == roles_path
        ], (
            "the admin header offers the roles listing — roles are a section of "
            "Team, not a surface of their own"
        )


def _roles_list_path() -> str:
    """The roles listing's path, read off its router without mounting it."""
    from commerce_ops.access.infrastructure.driving import roles_admin

    candidates: list[str] = []
    for route in roles_admin.router.routes:
        # Read through `getattr`: `BaseRoute` declares neither attribute, and
        # the router holds routes of several kinds.
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if isinstance(path, str) and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the roles router exposes no parameterless GET route"
    return min(candidates, key=len)


def _admin_header_of(root: _Node) -> _Node | None:
    """The shared admin header, if the page carries one."""
    for element in _elements(root):
        if element.tag == "header" or "admin-header" in set(
            element.attrs.get("class", "").split()
        ):
            return element
    return None
