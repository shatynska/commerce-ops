"""The admin surface's Roles pages (`roles-admin`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/roles-admin/spec.md`
— five of its eight ADDED requirements, eighteen scenarios:

- *The Roles page lists the collection grouped by status* (4)
- *A role's title in the list opens its own page* (2)
- *A role is created on its own page* (4)
- *A role's own page carries every change to it* (5)
- *A rejected role write re-presents the form with its faults* (3)

The remaining three — the breadcrumb, the shared header and the
presentation vocabulary — are covered in
`test_roles_admin_navigation_and_vocabulary.py`.

## Level

Every scenario is stated over the rendered page and the writes made from
it, so the page's routes over store doubles are the smallest observing
unit. The page is HTML end to end, so these tests drive it the way a
browser does: they *discover* the page's own controls and submit them,
pinning as little of the URL surface as possible — the idiom
`tests/unit/access/infrastructure/driving/test_members_admin_page.py`
established for the Team page, which `design.md` Decision 10 says this
surface is built to.

## What is fixed, and what is INVENTED

Fixed by the artifacts: a Roles surface in
`access/infrastructure/driving/` gated by the existing admin-session
dependency; every write going through the role collection's use cases; a
rejected write re-presenting every fault with the submitted values and
persisting nothing without returning to the list; the grouping by
status; the row carrying no actions; the title being the row's only way
in; the create page taking status and default holder in one submission;
the role's page offering only its permitted transitions.

INVENTED, each recorded in the manifest with its correction point:

- The module `commerce_ops.access.infrastructure.driving.roles_admin`
  exposing `router`, with the role and membership stores bound as
  module-level `roles` and `members` names and the guard consuming
  `verify_admin_session` — the seams
  `test_members_admin_page.py` uses for the Team page. Correction
  point: `_app`.
- Control-discovery vocabulary: which words a control's destination,
  label or hidden fields carry for each action. Correction points:
  `_ACTION_HINTS`.
- How a role's row is located: the smallest element naming that role's
  slug or title and naming no other role. Correction point: `_role_row`.
- Which form field takes each value, addressed by name substring.
  Correction point: `_fill`.
- The role use cases and store doubles, as
  `tests/unit/access/application/test_role_writes.py` records; the files
  correct together. They are repeated rather than shared because this
  pass may write only files matching `tests/**/test_*.py` — a shared
  `conftest.py` was not available to it.

## Expected first-run state

Neither the page module nor the role use cases exist, so every test here
fails before its assertions run — the absent-target state, which
establishes only absence.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member
from tests.support.admin import ADMIN_IDENTITY, fake_verify
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import Text as _Text
from tests.support.html import elements as _elements
from tests.support.html import nearest as _nearest
from tests.support.html import size as _size
from tests.support.html import tree as _tree

_PAGE_MODULE_NAME: Final = "commerce_ops.access.infrastructure.driving.roles_admin"

SECOND_IDENTITY: Final = "U02BOB"
THIRD_IDENTITY: Final = "U03CAROL"
DEPARTED_IDENTITY: Final = "U04DAVE"

ADMIN_NAME: Final = "Alice Admin"
SECOND_NAME: Final = "Bob Deputy"
THIRD_NAME: Final = "Carol Colleague"
DEPARTED_NAME: Final = "Dave Departed"

PRINCIPAL: Final = "helen"
THE_CREATING_ADMIN: Final = "the-creating-admin"
THE_EDITING_ADMIN: Final = "the-editing-admin"

_YEAR: Final = str(datetime.now(UTC).year)

DRAFT: Final = "draft"
ACTIVE: Final = "active"
RETIRED: Final = "retired"

#: The starting collection. One role of each status, plus a second
#: active one, so "grouped, never interleaved" has something to fail on.
ACTIVE_SLUG: Final = "supply-chain"
ACTIVE_TITLE: Final = "Supply Chain Manager"
SECOND_ACTIVE_SLUG: Final = "ppc"
SECOND_ACTIVE_TITLE: Final = "PPC Manager"
DRAFT_SLUG: Final = "managing-director"
DRAFT_TITLE: Final = "Managing Director"
RETIRED_SLUG: Final = "brand"
RETIRED_TITLE: Final = "Brand Manager"

EVERY_SLUG: Final = (ACTIVE_SLUG, SECOND_ACTIVE_SLUG, DRAFT_SLUG, RETIRED_SLUG)
EVERY_TITLE: Final = (
    ACTIVE_TITLE,
    SECOND_ACTIVE_TITLE,
    DRAFT_TITLE,
    RETIRED_TITLE,
)

#: INVENTED: how the page spells each action. A LOCATOR, not a
#: prohibition — a test that cannot find a control fails loudly.
_ACTION_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "retire": ("retire",),
    "unretire": ("unretire", "un-retire", "restore", "reinstate"),
    "activate": ("activate",),
    "add-holder": ("add", "holder"),
    "remove-holder": ("remove", "holder"),
    "move-default": ("default",),
    "rename": ("title", "rename"),
}


#: Structures a row never encloses. Used to tell a row from a
#: whole-page wrapper that happens to name one role.
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


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}) — the "
            "absent-target state; nothing in this test has been exercised"
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


# ---------------------------------------------------------------------------
# Row accessors (see test_role_writes.py)
# ---------------------------------------------------------------------------

_MEMBER_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_SLUG_NAMES: Final = ("slug", "identifier", "id")
_TITLE_NAMES: Final = ("title", "name")
_STATUS_NAMES: Final = ("status", "state", "lifecycle_status")
_HOLDERS_NAMES: Final = ("holders", "role_holders", "members")
_DEFAULT_NAMES: Final = (
    "default_holder",
    "default_holder_id",
    "default_member_id",
    "default",
)


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("role", "member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _has(row: Any, names: tuple[str, ...]) -> bool:
    return any(hasattr(target, name) for target in _targets(row) for name in names)


def _row_field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored row exposes no {what} under any of {names} — correct this "
        "file's accessor names to the implemented row"
    )


def _scalar(value: Any) -> str:
    return str(getattr(value, "value", value))


def _slug_of(row: Any) -> str:
    return str(_row_field(row, _SLUG_NAMES, "slug"))


def _title_of(row: Any) -> str:
    return str(_row_field(row, _TITLE_NAMES, "title"))


def _status_of(row: Any) -> str:
    return _scalar(_row_field(row, _STATUS_NAMES, "lifecycle status")).lower()


def _holder_identifier(holder: Any) -> str:
    if isinstance(holder, (str, bytes, uuid.UUID)):
        return str(holder)
    for name in ("member_id", "member", "id", "identifier", "holder"):
        if hasattr(holder, name):
            value = getattr(holder, name)
            if isinstance(value, (str, bytes, uuid.UUID, int)):
                return str(value)
            if value is not None and name in ("member", "holder"):
                return _holder_identifier(value)
    pytest.fail(f"a stored holder {holder!r} exposes no member identifier")


def _holders_of(row: Any) -> set[str]:
    return {
        _holder_identifier(holder)
        for holder in _row_field(row, _HOLDERS_NAMES, "holders")
    }


def _default_of(row: Any) -> str | None:
    if _has(row, _DEFAULT_NAMES):
        value = _row_field(row, _DEFAULT_NAMES, "default holder")
        return None if value is None else _holder_identifier(value)
    marked = [
        holder
        for holder in _row_field(row, _HOLDERS_NAMES, "holders")
        if any(
            bool(getattr(holder, name, False))
            for name in ("is_default", "default", "is_the_default")
        )
    ]
    if len(marked) > 1:
        pytest.fail(f"{len(marked)} holders of {_slug_of(row)!r} are marked default")
    return _holder_identifier(marked[0]) if marked else None


def _role(store: _FakeRolesStore, slug: str) -> Any:
    for row in store.rows:
        if _slug_of(row) == slug:
            return row
    pytest.fail(
        f"no stored role carries the slug {slug!r} (stored: "
        f"{sorted(_slug_of(row) for row in store.rows)})"
    )


def _member_id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if str(_row_field(row, _SLACK_NAMES, "Slack identity")) == identity:
            return _row_field(row, _MEMBER_ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


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


_CREATE_NAMES: Final = ("create_role",)
_ADD_HOLDER_NAMES: Final = ("add_role_holder", "add_holder", "add_role_member")
_RETIRE_NAMES: Final = ("retire_role",)


async def _create_role(
    collections: _Collections,
    *,
    slug: str,
    title: str,
    status: str,
    default_holder: Any = None,
    principal: str = THE_CREATING_ADMIN,
) -> Any:
    step = _use_case(_CREATE_NAMES, "create-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": principal,
        "slug": slug,
        "title": title,
    }
    attempts: tuple[Callable[[], Any], ...] = (
        lambda: step(**common, status=status, default_holder=default_holder),
        lambda: step(**common, status=status, default_holder_id=default_holder),
        lambda: step(**common, status=status, holder=default_holder),
        lambda: step(**common, status=status),
    )
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _argument_shape(error):
                raise
    pytest.fail("no attempted call shape matched `create_role`'s signature")


async def _add_holder(collections: _Collections, slug: str, member_id: Any) -> Any:
    step = _use_case(_ADD_HOLDER_NAMES, "add-a-holder")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_CREATING_ADMIN,
    }
    attempts: tuple[Callable[[], Any], ...] = (
        lambda: step(**common, slug=slug, member_id=member_id),
        lambda: step(**common, role_slug=slug, member_id=member_id),
        lambda: step(**common, slug=slug, holder=member_id),
    )
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _argument_shape(error):
                raise
    pytest.fail("no attempted call shape matched the add-a-holder signature")


async def _retire(collections: _Collections, slug: str) -> Any:
    step = _use_case(_RETIRE_NAMES, "retire-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_EDITING_ADMIN,
    }
    attempts: tuple[Callable[[], Any], ...] = (
        lambda: step(**common, slug=slug),
        lambda: step(**common, role_slug=slug),
    )
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _argument_shape(error):
                raise
    pytest.fail("no attempted call shape matched the retire signature")


def _argument_shape(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _build() -> _Collections:
    collections = _Collections()
    for name, identity in (
        (ADMIN_NAME, ADMIN_IDENTITY),
        (SECOND_NAME, SECOND_IDENTITY),
        (THIRD_NAME, THIRD_IDENTITY),
        (DEPARTED_NAME, DEPARTED_IDENTITY),
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
    await _create_role(
        collections,
        slug=SECOND_ACTIVE_SLUG,
        title=SECOND_ACTIVE_TITLE,
        status=ACTIVE,
        default_holder=bob,
    )
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
    """Built off the event loop: the tests themselves are synchronous and
    drive the ASGI app through `TestClient`'s own portal."""
    return asyncio.run(_build())


# ---------------------------------------------------------------------------
# An HTML tree (shaped after test_members_admin_presentation_vocabulary.py)
# ---------------------------------------------------------------------------


def _all_text(node: _Node) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            parts.append(child.text)
        else:
            parts.append(_all_text(child))
    return " ".join(part for part in parts if part)


def _holders_listing(root: _Node) -> str:
    """The text of the role page's holders listing.

    Identified by the marker the template carries rather than by position, so
    the two do not drift apart under a rearrangement of the page.
    """
    for element in _elements(root):
        if "role-holders" in set(element.attrs.get("class", "").split()):
            return _all_text(element)
    return ""


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


def _action_controls(node: _Node) -> list[_Node]:
    found = [node] if _is_action_control(node) else []
    found.extend(child for child in _elements(node) if _is_action_control(child))
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


@dataclass
class _Form:
    method: str
    url: str
    fields: dict[str, str]
    options: dict[str, list[str]]
    node: _Node


def _forms(root: _Node) -> list[_Form]:
    found: list[_Form] = []
    for element in _elements(root):
        if element.tag != "form":
            continue
        method = (element.attrs.get("method") or "get").lower()
        url = element.attrs.get("action", "")
        for verb in _HX_VERBS:
            if verb in element.attrs:
                method = verb.removeprefix("hx-")
                url = element.attrs[verb]
        fields: dict[str, str] = {}
        options: dict[str, list[str]] = {}
        for child in _elements(element):
            name = child.attrs.get("name")
            if not name:
                continue
            if child.tag == "input":
                kind = (child.attrs.get("type") or "text").lower()
                if kind in ("checkbox", "radio") and "checked" not in child.attrs:
                    options.setdefault(name, []).append(child.attrs.get("value", "on"))
                    continue
                fields[name] = child.attrs.get(
                    "value", "on" if kind == "checkbox" else ""
                )
            elif child.tag == "select":
                values = [
                    option.attrs.get("value", _all_text(option))
                    for option in _elements(child)
                    if option.tag == "option"
                ]
                selected = [
                    option.attrs.get("value", _all_text(option))
                    for option in _elements(child)
                    if option.tag == "option" and "selected" in option.attrs
                ]
                options[name] = values
                fields[name] = (
                    selected[0] if selected else (values[0] if values else "")
                )
            elif child.tag == "textarea":
                fields[name] = _all_text(child)
        found.append(_Form(method, url, fields, options, element))
    return found


def _fill(form: _Form, **by_substring: str) -> dict[str, str]:
    """Overrides form fields addressed by name substring, failing loudly
    if an addressed field has no match, so nothing is submitted
    vacuously."""
    filled = dict(form.fields)
    for fragment, value in by_substring.items():
        matches = [name for name in filled if fragment in name.lower()]
        if not matches:
            pytest.fail(
                f"the form offers no field whose name contains {fragment!r} "
                f"(fields: {sorted(filled)}) — correct this file's "
                "field-addressing to the implemented form"
            )
        for name in matches:
            if name in form.options and form.options[name] and value != "":
                assert value in form.options[name], (
                    f"the form's {name!r} offers {form.options[name]!r}, which "
                    f"does not include {value!r}"
                )
            filled[name] = value
    return filled


def _drop(fields: dict[str, str], fragment: str) -> dict[str, str]:
    return {
        name: value for name, value in fields.items() if fragment not in name.lower()
    }


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


def _list_path() -> str:
    """The Roles list: the shortest parameterless GET route the router
    exposes."""
    candidates: list[str] = []
    for route in _page_module().router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the Roles router exposes no parameterless GET route"
    return min(candidates, key=len)


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


def _submit(client: TestClient, form: _Form, data: dict[str, str]) -> Any:
    return client.request(form.method.upper(), _resolve(form.url), data=data)


def _links(root: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a" and element.attrs.get("href")
    ]


def _role_row(root: _Node, slug: str, title: str) -> _Node:
    """The one role's own region of the list.

    INVENTED: the **largest** element naming this role and naming no
    other, that encloses none of the structures a row never encloses — a
    table, the page's header or navigation, a heading, a stylesheet
    link. Markup-agnostic, so a table row, a list item or a card all
    read the same.

    Largest rather than smallest deliberately: the smallest such element
    is a leaf cell carrying no controls whatever the page does, so a
    row-carries-no-actions assertion read off it would pass by
    construction — the defect `tasks.md` 10.9 names.
    """
    others = [
        other.lower()
        for other in EVERY_SLUG + EVERY_TITLE
        if other not in (slug, title)
    ]
    candidates = [
        element
        for element in _elements(root)
        if slug.lower() in _attribute_text(element)
        and title.lower() in _attribute_text(element)
        and not any(other in _attribute_text(element) for other in others)
        and element.tag not in _NOT_A_ROW
        and not any(child.tag in _NOT_A_ROW for child in _elements(element))
    ]
    if not candidates:
        pytest.fail(
            f"no element of the Roles page names {slug!r} and {title!r} without "
            "naming another role, so that role's row cannot be isolated — "
            "correct `_role_row` to the implemented page"
        )
    return max(candidates, key=_size)


def _role_page(client: TestClient, html: str, slug: str, title: str) -> str:
    """That role's own page, reached from the list the way an admin
    reaches it — through the title link on its row."""
    row = _role_row(_tree(html), slug, title)
    for link in _links(row):
        if _all_text(link).strip() == title or title.lower() in _all_text(link).lower():
            response = client.get(_resolve(link.attrs["href"]))
            assert response.status_code == 200, response.text
            return str(response.text)
    pytest.fail(
        f"{slug!r}'s row offers no link whose text is its title, so the role's "
        "own page cannot be reached in one action from the list"
    )


def _create_page(client: TestClient, html: str) -> tuple[str, str]:
    """The create page, reached from the list, with the path it sits at."""
    root = _tree(html)
    for link in _links(root):
        haystack = (link.attrs["href"] + " " + _all_text(link)).lower()
        if any(word in haystack for word in ("new", "create", "add")):
            path = _resolve(link.attrs["href"])
            response = client.get(path)
            if response.status_code == 200 and _create_form_in(response.text):
                return str(response.text), path
    pytest.fail(
        "the Roles page offers no link reaching a create page carrying a slug "
        "field — correct this file's control vocabulary to the implemented page"
    )


def _create_form_in(html: str) -> _Form | None:
    for form in _forms(_tree(html)):
        names = " ".join(form.fields).lower() + " " + " ".join(form.options).lower()
        if "slug" in names:
            return form
    return None


def _require_create_form(html: str) -> _Form:
    found = _create_form_in(html)
    if found is None:
        pytest.fail("no create-a-role form carrying a slug field was found on the page")
    return found


def _action_form(page: str, what: str, *, excluding: tuple[str, ...] = ()) -> _Form:
    """The form on a role's page that performs one named action."""
    hints = _ACTION_HINTS[what]
    found = [
        form
        for form in _forms(_tree(page))
        if all(
            hint
            in (form.url + " " + str(form.fields) + " " + _all_text(form.node)).lower()
            for hint in hints
        )
        and not any(
            word
            in (form.url + " " + str(form.fields) + " " + _all_text(form.node)).lower()
            for word in excluding
        )
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} forms on the role's page look like the {what} action "
            f"(hints {hints}); correct this file's `_ACTION_HINTS` to the "
            "implemented page"
        )
    return found[0]


def _offers(page: str, what: str, *, excluding: tuple[str, ...] = ()) -> bool:
    hints = _ACTION_HINTS[what]
    root = _tree(page)
    for control in _action_controls(root):
        haystack = _control_haystack(control)
        if all(hint in haystack for hint in hints) and not any(
            word in haystack for word in excluding
        ):
            return True
    return False


def _positions(html: str, *needles: str) -> list[int]:
    found = []
    for needle in needles:
        at = html.find(needle)
        assert at >= 0, f"{needle!r} is not rendered on the page"
        found.append(at)
    return found


# ===========================================================================
# Requirement: The Roles page lists the collection grouped by status
# ===========================================================================


def test_the_whole_collection_is_one_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The whole collection is one page.

    WHEN an admin opens the Roles page
    THEN every role is listed on that one page with its title, slug and
    default holder.

    "On that one page" is asserted by taking a single unparameterized
    GET and finding every role in it — no pagination control followed,
    nothing fetched twice. Retired and draft roles are included: the
    collection offers no deletion, so "every role" means all four.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    html = _get(client)

    # SPECIFIED: every role, with its title and slug.
    for slug, title in zip(EVERY_SLUG, EVERY_TITLE, strict=True):
        assert slug in html, f"{slug!r} is missing from the Roles page"
        assert title in html, f"{title!r} is missing from the Roles page"
    # SPECIFIED: and its default holder, where it has one.
    row = _role_row(_tree(html), ACTIVE_SLUG, ACTIVE_TITLE)
    # `_attribute_text` lowercases what it returns, so the needles are
    # lowercased with it; comparing a capitalised display name against a
    # lowercased haystack fails for a page that renders the holder correctly.
    assert ADMIN_NAME.lower() in _attribute_text(row) or str(
        _member_id_of(collections.members, ADMIN_IDENTITY)
    ).lower() in _attribute_text(row), (
        f"{ACTIVE_SLUG!r}'s row does not present its default holder"
    )
    # DERIVED discrimination: the *default* is shown, not merely some
    # holder — the row names Alice and not Bob, who holds the role
    # without being its default.
    assert SECOND_NAME not in _all_text(row), (
        f"{ACTIVE_SLUG!r}'s row names a non-default holder, so what it "
        "presents is the holder set rather than the default holder"
    )


def test_the_three_statuses_are_set_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The three statuses are set apart.

    WHEN the collection holds active, draft and retired roles
    THEN the page presents each status group distinctly, and never mixes
    roles of different statuses into one group.

    Asserted as contiguity: the two active roles are adjacent in the
    rendered order with no role of another status between them. A page
    sorted alphabetically would place `brand` (retired) between `ppc`
    and `supply-chain`, which is exactly the interleaving the
    requirement forbids and what this test catches.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    html = _get(client)

    at = dict(zip(EVERY_SLUG, _positions(html, *EVERY_SLUG), strict=True))
    active_span = (
        min(at[ACTIVE_SLUG], at[SECOND_ACTIVE_SLUG]),
        max(at[ACTIVE_SLUG], at[SECOND_ACTIVE_SLUG]),
    )
    # SPECIFIED: never mixes roles of different statuses into one group.
    for slug in (DRAFT_SLUG, RETIRED_SLUG):
        assert not (active_span[0] < at[slug] < active_span[1]), (
            f"{slug!r} is rendered between the two active roles, so the "
            "status groups are interleaved"
        )
    # SPECIFIED: each group is presented distinctly — the page names each
    # status somewhere, so the grouping is readable rather than implied
    # by order alone.
    lowered = html.lower()
    for status in (ACTIVE, DRAFT, RETIRED):
        assert status in lowered, (
            f"the page never says {status!r}, so a reader cannot tell which "
            "group is which"
        )


def test_a_role_with_no_default_holder_is_listed_without_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A role with no default holder is listed without one.

    WHEN a draft role holding nobody is listed
    THEN its row is rendered showing no default holder, rather than
    being omitted or rendered as holding a placeholder person.

    "No placeholder person" is asserted as the row naming none of the
    membership — a row reading `—`, `None` or nothing at all all pass,
    while one that fell back to the first member does not.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    html = _get(client)

    # SPECIFIED: rather than being omitted.
    assert DRAFT_SLUG in html
    row = _role_row(_tree(html), DRAFT_SLUG, DRAFT_TITLE)
    text = _attribute_text(row)
    # SPECIFIED: showing no default holder, and no placeholder person.
    for name, identity in (
        (ADMIN_NAME, ADMIN_IDENTITY),
        (SECOND_NAME, SECOND_IDENTITY),
        (THIRD_NAME, THIRD_IDENTITY),
        (DEPARTED_NAME, DEPARTED_IDENTITY),
    ):
        assert name.lower() not in text, (
            f"the unstaffed draft role's row names {name!r} as a holder"
        )
        assert str(_member_id_of(collections.members, identity)) not in text


@pytest.mark.parametrize(
    ("slug", "title"),
    list(zip(EVERY_SLUG, EVERY_TITLE, strict=True)),
    ids=list(EVERY_SLUG),
)
def test_a_roles_row_carries_no_actions(
    monkeypatch: pytest.MonkeyPatch, slug: str, title: str
) -> None:
    """Scenario: A role's row carries no actions.

    WHEN any role's row is rendered, whatever its status
    THEN the row carries no control that renames, retires, un-retires or
    activates the role, and none that changes its holders.

    Parametrized over every status, because "whatever its status" is the
    scenario's own scope and a page could plausibly leave an un-retire
    control on a retired row alone.

    The row's link to the role's own page is not such a control: the
    requirement's neighbour makes the title the row's way in. So what is
    asserted is that the row encloses no form at all, and that every
    control on it is a plain link.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    row = _role_row(_tree(_get(client)), slug, title)

    # SPECIFIED: no control that changes the role.
    forms = [element for element in _elements(row) if element.tag == "form"]
    assert forms == [], (
        f"{slug!r}'s row encloses {len(forms)} form(s), so a change to the "
        "role is submitted from the row rather than from its own page"
    )
    for control in _action_controls(row):
        assert control.tag == "a", (
            f"{slug!r}'s row carries a {control.tag!r} control "
            f"({_control_haystack(control)[:80]!r}); a row offers only its "
            "way into the role's own page"
        )
        haystack = _control_haystack(control)
        for what, hints in _ACTION_HINTS.items():
            assert not all(hint in haystack for hint in hints), (
                f"{slug!r}'s row carries a {what} control: {haystack[:120]!r}"
            )


# ===========================================================================
# Requirement: A role's title in the list opens its own page
# ===========================================================================


def test_a_roles_title_opens_its_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A role's title opens its page.

    WHEN any role's row is rendered
    THEN its title offers that role's own page in one action.

    "That role's own page" is asserted by following the link and reading
    what comes back: the page names this role's slug and no other's, so
    a title linking to the list, to a filter or to another role fails.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    html = _get(client)

    page = _role_page(client, html, ACTIVE_SLUG, ACTIVE_TITLE)

    # SPECIFIED: the page reached is that role's own.
    assert ACTIVE_SLUG in page
    assert ACTIVE_TITLE in page
    for other in (SECOND_ACTIVE_SLUG, DRAFT_SLUG, RETIRED_SLUG):
        assert other not in page, (
            f"the page reached from {ACTIVE_SLUG!r}'s title also names "
            f"{other!r}, so it is not that role's own page"
        )


def test_the_slug_is_shown_but_is_not_a_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The slug is shown but is not a link.

    WHEN any role's row is rendered
    THEN its slug is readable on the row and offers no destination of
    its own.

    One row, one destination, so that which of two adjacent controls an
    admin clicked is never the question.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    row = _role_row(_tree(_get(client)), ACTIVE_SLUG, ACTIVE_TITLE)

    # SPECIFIED: the slug is readable on the row.
    assert ACTIVE_SLUG in _all_text(row), (
        f"{ACTIVE_SLUG!r} is not readable as text on its own row"
    )
    # SPECIFIED: and offers no destination of its own.
    slug_links = [
        link for link in _links(row) if _all_text(link).strip() == ACTIVE_SLUG
    ]
    assert slug_links == [], (
        "the slug is rendered as a link, giving the row a second way in"
    )
    # SPECIFIED (the neighbouring requirement, asserted as the count):
    # the row offers exactly one destination.
    destinations = {urlsplit(link.attrs["href"]).path for link in _links(row)}
    assert len(destinations) == 1, (
        f"{ACTIVE_SLUG!r}'s row offers {len(destinations)} destinations "
        f"{sorted(destinations)!r}; one row, one destination"
    )


# ===========================================================================
# Requirement: A role is created on its own page
# ===========================================================================


def test_creating_is_reached_from_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Creating is reached from the list.

    WHEN the Roles page is rendered
    THEN it offers the create page in one action, and carries no create
    form of its own.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    html = _get(client)

    # SPECIFIED: it offers the create page in one action.
    page, _path = _create_page(client, html)
    assert _create_form_in(page) is not None
    # SPECIFIED: and carries no create form of its own.
    assert _create_form_in(html) is None, (
        "the Roles list still carries a create form at its top; creating "
        "happens on a page of its own"
    )


def test_an_active_role_is_created_with_its_default_holder_in_one_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An active role is created with its default holder in
    one submission.

    WHEN an admin submits a new role with status `active`, a slug, a
    title and a default holder
    THEN the role is created active with that member as its sole holder
    and default, and appears in the active group.

    "One submission" is the point: the store is asserted to have taken
    exactly one role write, so a page composing create-then-add-holder
    fails even though the end state would look the same.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    carol = _member_id_of(collections.members, THIRD_IDENTITY)
    page, _path = _create_page(client, _get(client))
    form = _require_create_form(page)
    before_saves = len(collections.roles.saves)

    submitted = _fill(
        form,
        slug="creative",
        title="Creative Manager",
        status=ACTIVE,
        holder=str(carol),
    )
    response = _submit(client, form, submitted)
    assert response.status_code < 400, response.text

    role = _role(collections.roles, "creative")
    # SPECIFIED: created active, with that member as sole holder and default.
    assert _status_of(role) == ACTIVE
    assert _holders_of(role) == {str(carol)}
    assert _default_of(role) == str(carol)
    # SPECIFIED: in one submission.
    assert len(collections.roles.saves) == before_saves + 1, (
        "the create page composed more than one role write; a role created "
        "`active` takes its default holder in the same write"
    )
    # SPECIFIED: and appears in the active group.
    after = _get(client)
    assert "creative" in after
    at = _positions(after, "creative", ACTIVE_SLUG, DRAFT_SLUG, RETIRED_SLUG)
    assert abs(at[0] - at[1]) < max(abs(at[0] - at[2]), abs(at[0] - at[3])) or at[
        0
    ] < min(at[2], at[3]), "the new active role is not rendered among the active group"


def test_a_draft_role_is_created_holding_nobody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A draft role is created holding nobody.

    WHEN an admin submits a new role with status `draft` and no holder
    THEN the role is created and appears in the draft group holding
    nobody.

    The holder field is dropped from the submission entirely rather than
    submitted empty, since "creating a `draft` role SHALL NOT require a
    holder" is about the page not demanding one.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    page, _path = _create_page(client, _get(client))
    form = _require_create_form(page)

    submitted = _drop(
        _fill(form, slug="operations", title="Operations Manager", status=DRAFT),
        "holder",
    )
    response = _submit(client, form, submitted)
    assert response.status_code < 400, response.text

    role = _role(collections.roles, "operations")
    # SPECIFIED: created, draft, holding nobody.
    assert _status_of(role) == DRAFT
    assert _holders_of(role) == set()
    assert _default_of(role) is None
    # SPECIFIED: and appears in the draft group.
    assert "operations" in _get(client)


def test_an_active_role_submitted_without_a_holder_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An active role submitted without a default holder is
    rejected.

    WHEN an admin submits a new role with status `active` and no default
    holder
    THEN the create page is re-presented with the fault and the
    submitted values still in place, and no role is created.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    page, create_path = _create_page(client, _get(client))
    form = _require_create_form(page)
    before_rows = collections.roles.rows
    before_saves = len(collections.roles.saves)

    submitted = _drop(
        _fill(form, slug="controller", title="Financial Controller", status=ACTIVE),
        "holder",
    )
    response = _submit(client, form, submitted)

    # SPECIFIED: the create page is re-presented (not an error page, not
    # the list).
    assert response.status_code < 500, response.text
    body = response.text
    represented = _create_form_in(body)
    assert represented is not None, (
        "the rejected create did not re-present the create form"
    )
    for slug in EVERY_SLUG:
        assert slug not in body, (
            f"the rejection returned the admin to the list ({slug!r} is on the "
            "response), so the refusal is read away from the values that "
            "caused it"
        )
    # SPECIFIED: with the submitted values still in place.
    assert "controller" in body
    assert "Financial Controller" in body
    # SPECIFIED: with the fault.
    assert any(word in body.lower() for word in ("default", "holder")), (
        "the re-presented page shows no fault about the missing default holder"
    )
    # SPECIFIED: and no role is created.
    assert collections.roles.rows == before_rows
    assert len(collections.roles.saves) == before_saves
    assert create_path  # the create page has a path of its own


# ===========================================================================
# Requirement: A role's own page carries every change to it
# ===========================================================================


def test_the_slug_is_not_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The slug is not editable.

    WHEN a role's page is rendered
    THEN its slug is presented as a value and not as an editable input.

    A hidden input carrying the slug is not an editable one — it is how
    a form addresses its subject — so what fails here is a *typeable*
    field: a text input, a textarea or a select whose name mentions the
    slug.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _role_page(client, _get(client), ACTIVE_SLUG, ACTIVE_TITLE)

    # SPECIFIED: presented as a value.
    assert ACTIVE_SLUG in page
    # SPECIFIED: and not as an editable input.
    editable = [
        element
        for element in _elements(_tree(page))
        if "slug" in element.attrs.get("name", "").lower()
        and (
            element.tag in ("textarea", "select")
            or (
                element.tag == "input"
                and (element.attrs.get("type") or "text").lower() not in ("hidden",)
            )
        )
    ]
    assert editable == [], (
        f"the role's page offers {len(editable)} editable slug field(s); the "
        "slug is chosen once and never changes"
    )


def test_only_permitted_transitions_are_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Only permitted transitions are offered.

    WHEN a retired role's page is rendered
    THEN it offers un-retiring, and offers neither retiring nor any
    return to `draft`.

    The page offers only what is permitted from the role's current
    status rather than offering all of them and refusing on submission,
    which is what the requirement asks for.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _role_page(client, _get(client), RETIRED_SLUG, RETIRED_TITLE)

    # SPECIFIED: it offers un-retiring.
    assert _offers(page, "unretire") or _offers(page, "activate"), (
        "the retired role's page offers no way back into the collection"
    )
    # SPECIFIED: and offers neither retiring …
    assert not _offers(page, "retire", excluding=("unretire", "un-retire")), (
        "the retired role's page still offers retiring it"
    )
    # SPECIFIED: … nor any return to `draft`.
    for control in _action_controls(_tree(page)):
        assert DRAFT not in _control_haystack(control), (
            "the retired role's page offers a return to `draft`: "
            f"{_control_haystack(control)[:120]!r}"
        )


def test_a_draft_role_is_offered_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A draft role is offered activation.

    WHEN a draft role's page is rendered
    THEN it offers activating the role and retiring it, and does not
    offer un-retiring.

    Both halves matter: `draft -> retired` is a permitted transition, so
    a page offering only activation would be missing the way to clear an
    abandoned sketch from a collection that offers no deletion.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _role_page(client, _get(client), DRAFT_SLUG, DRAFT_TITLE)

    # SPECIFIED: it offers activating the role …
    assert _offers(page, "activate"), (
        "the draft role's page offers no way to activate it"
    )
    # SPECIFIED: … and retiring it …
    assert _offers(page, "retire", excluding=("unretire", "un-retire")), (
        "the draft role's page offers no way to retire it, so an abandoned "
        "sketch cannot be cleared from a collection offering no deletion"
    )
    # SPECIFIED: … and does not offer un-retiring.
    assert not _offers(page, "unretire"), (
        "the draft role's page offers un-retiring a role that was never retired"
    )


def test_holders_are_managed_from_the_roles_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Holders are managed from the role's page.

    WHEN an admin adds a holder, removes a non-default holder, and moves
    the default on a role's page
    THEN each write lands and the page reflects the role's holders and
    default afterwards.

    All three actions in one test, in the order the scenario states
    them, because each is submitted from the page the previous one
    returned — which is what "managed from the role's page" means.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    alice = str(_member_id_of(collections.members, ADMIN_IDENTITY))
    bob = str(_member_id_of(collections.members, SECOND_IDENTITY))
    carol = str(_member_id_of(collections.members, THIRD_IDENTITY))

    page = _role_page(client, _get(client), ACTIVE_SLUG, ACTIVE_TITLE)

    # Add a holder.
    form = _action_form(page, "add-holder", excluding=("remove",))
    response = _submit(client, form, _fill(form, member=carol))
    assert response.status_code < 400, response.text
    role = _role(collections.roles, ACTIVE_SLUG)
    assert _holders_of(role) == {alice, bob, carol}

    # Remove a non-default holder.
    page = _get(client, _role_path(client, ACTIVE_SLUG, ACTIVE_TITLE))
    form = _action_form(page, "remove-holder", excluding=("add",))
    response = _submit(client, form, _fill(form, member=bob))
    assert response.status_code < 400, response.text
    role = _role(collections.roles, ACTIVE_SLUG)
    assert _holders_of(role) == {alice, carol}
    assert _default_of(role) == alice

    # Move the default.
    page = _get(client, _role_path(client, ACTIVE_SLUG, ACTIVE_TITLE))
    form = _action_form(page, "move-default", excluding=("remove", "add"))
    response = _submit(client, form, _fill(form, member=carol))
    assert response.status_code < 400, response.text
    role = _role(collections.roles, ACTIVE_SLUG)
    assert _default_of(role) == carol

    # SPECIFIED: the page reflects the holders and default afterwards.
    page = _get(client, _role_path(client, ACTIVE_SLUG, ACTIVE_TITLE))
    assert THIRD_NAME in page or carol in page
    # Read off the holders listing rather than the whole page. A removed
    # holder legitimately reappears elsewhere on it — as a candidate the
    # add-a-holder control offers, since removing somebody is exactly what
    # makes them addable again — so searching the whole document would fail a
    # page that is behaving correctly. What the scenario asks is that they are
    # no longer listed as a HOLDER.
    listing = _holders_listing(_tree(page))
    assert SECOND_NAME not in listing and bob not in listing, (
        "the removed holder is still presented among the role's holders"
    )


def _role_path(client: TestClient, slug: str, title: str) -> str:
    row = _role_row(_tree(_get(client)), slug, title)
    for link in _links(row):
        if title.lower() in _all_text(link).lower():
            return _resolve(link.attrs["href"])
    pytest.fail(f"no link to {slug!r}'s own page was found on its row")


def test_the_roles_attribution_is_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The role's attribution is readable.

    WHEN an admin views a role's page
    THEN the page presents who created the role and when, and its most
    recent change with who made it and when.

    The retired role is the one whose creator and most recent change
    were made by *different* principals, which is what makes "the most
    recent change" a real assertion rather than a second reading of the
    creation. DERIVED: that "when" renders carrying the current year —
    the delta fixes that a time is presented, not its format.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)

    page = _role_page(client, _get(client), RETIRED_SLUG, RETIRED_TITLE)

    # SPECIFIED: who created the role.
    assert THE_CREATING_ADMIN in page, "the role's page does not present who created it"
    # SPECIFIED: its most recent change, with who made it.
    assert THE_EDITING_ADMIN in page, (
        "the role's page does not present its most recent change and who made it"
    )
    # SPECIFIED: and when, for both.
    assert _YEAR in page, "the role's page presents no time alongside its attribution"


# ===========================================================================
# Requirement: A rejected role write re-presents the form with its faults
# ===========================================================================


def test_a_rejected_write_shows_every_fault_with_the_typed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected write shows every fault with the typed
    values.

    WHEN an admin submits a role change the collection's validation
    rejects
    THEN the form is re-presented showing every fault and still holding
    the submitted values, and the collection is unchanged.

    The submission carries *two* faults — a duplicate slug and an empty
    title — so "every fault" is a real count rather than a single
    message.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    page, _path = _create_page(client, _get(client))
    form = _require_create_form(page)
    before_rows = collections.roles.rows
    before_saves = len(collections.roles.saves)

    submitted = _drop(_fill(form, slug=DRAFT_SLUG, title="", status=DRAFT), "holder")
    response = _submit(client, form, submitted)

    # SPECIFIED: the form is re-presented.
    assert response.status_code < 500, response.text
    body = response.text
    represented = _create_form_in(body)
    assert represented is not None, "the rejected write re-presented no form"
    # SPECIFIED: still holding the submitted values.
    assert any(DRAFT_SLUG in str(value) for value in represented.fields.values()), (
        "the re-presented form does not hold the submitted slug; fields: "
        f"{represented.fields}"
    )
    # SPECIFIED: showing every fault — both of them, distinguishably.
    lowered = body.lower()
    assert DRAFT_SLUG in lowered, "no fault names the duplicated slug"
    assert "title" in lowered, "no fault mentions the empty title"
    # SPECIFIED: and the collection is unchanged.
    assert collections.roles.rows == before_rows
    assert len(collections.roles.saves) == before_saves


def test_a_refused_activation_explains_its_own_obligation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A refused activation explains its own obligation.

    WHEN an admin activates a draft role holding nobody
    THEN the page shows that an active role must have a default holder,
    and the role remains draft.

    "Its own obligation" rather than a generic refusal: the response
    must say something about a default holder, not merely that the write
    failed.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    page = _role_page(client, _get(client), DRAFT_SLUG, DRAFT_TITLE)
    before_saves = len(collections.roles.saves)

    form = _action_form(page, "activate")
    response = _submit(client, form, dict(form.fields))

    # SPECIFIED: the page shows the obligation that failed.
    assert response.status_code < 500, response.text
    lowered = response.text.lower()
    assert "default" in lowered and "holder" in lowered, (
        "the refused activation surfaced no explanation naming the "
        f"active-role obligation: {response.text[:600]!r}"
    )
    # SPECIFIED: and the role remains draft.
    assert _status_of(_role(collections.roles, DRAFT_SLUG)) == DRAFT
    assert len(collections.roles.saves) == before_saves


def test_a_refused_default_removal_explains_its_own_obligation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A refused default removal explains its own obligation.

    WHEN an admin removes the default holder of an active role holding
    other members
    THEN the page shows that the default must be moved to another holder
    first, and the holders are unchanged.

    The role holds two members, so what is refused is removing the
    *default* rather than removing the last holder — the two refusals
    read differently and the requirement asks for the specific one.
    """
    collections = _collections()
    client = _client(monkeypatch, collections)
    alice = str(_member_id_of(collections.members, ADMIN_IDENTITY))
    bob = str(_member_id_of(collections.members, SECOND_IDENTITY))
    page = _role_page(client, _get(client), ACTIVE_SLUG, ACTIVE_TITLE)
    before_saves = len(collections.roles.saves)

    form = _action_form(page, "remove-holder", excluding=("add",))
    response = _submit(client, form, _fill(form, member=alice))

    # SPECIFIED: the page shows the specific obligation.
    assert response.status_code < 500, response.text
    lowered = response.text.lower()
    assert "default" in lowered, (
        "the refused removal surfaced no explanation naming the default: "
        f"{response.text[:600]!r}"
    )
    # SPECIFIED: and the holders are unchanged.
    role = _role(collections.roles, ACTIVE_SLUG)
    assert _holders_of(role) == {alice, bob}
    assert _default_of(role) == alice
    assert len(collections.roles.saves) == before_saves
