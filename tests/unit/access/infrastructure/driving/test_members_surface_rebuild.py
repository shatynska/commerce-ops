"""The rebuilt Team surface: the list, the create page and a member's own
page (`members-admin`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/members-admin/spec.md`
— three of its five MODIFIED requirements and its one ADDED requirement,
fifteen scenarios:

- MODIFIED *The Team page shows the membership whole* (5)
- MODIFIED *A member can be created and edited from the page* (4)
- MODIFIED *Deactivation and reactivation are available from the page* (3)
- ADDED *The create page and a member's own page carry a breadcrumb back
  to the list* (3)

Three of those fifteen are **not** written here, because the revision
does not touch what they observe and the tests already covering them stay
valid and unweakened:

- *The whole active membership is one page* — covered by
  `test_members_admin_page.py::test_the_whole_active_members_is_one_page`
- *Deactivated members are reachable but set apart* — covered by
  `test_members_admin_page.py::test_deactivated_members_are_reachable_but_set_apart`
- *A blocked deactivation explains itself* is **not** among them: the
  refusal moves onto the member's own page, so it is rewritten here and
  the existing test is recorded as obsolete.

The manifest at
`openspec/changes/rebuild-the-member-directory/test-manifest.md` records
that accounting scenario by scenario, together with the existing tests
this change makes obsolete. This pass edits and deletes none of them.

## Level

The Team surface's routes over store doubles, driven the way a browser
drives them — the harness `test_members_admin_page.py` established,
repeated here rather than imported because this directory carries no
`__init__.py` and this project keeps its test files self-contained.

## What is fixed, and what is INVENTED

Fixed by the delta: that the list carries no create form and no row
actions; that a member's display name opens their own page; that
creating happens on its own page reached from the list in one action;
that editing, deactivating and reactivating happen on the member's page;
that attribution is read there; that a rejection re-presents the
submitted form without returning to the list; that the role-blocked
refusal names every blocking role; and the breadcrumb's two segments.

INVENTED, each recorded in the manifest with its correction point:

- That the page module binds the role collection as a module-level
  `roles` name, the way it binds `members`. The role-blocked refusal
  cannot be surfaced without the page reaching the roles somehow, and no
  artifact fixes how. Correction point: `_client`.
- How a member's row is located, and how each sub-page is reached — by
  discovering the list's own links rather than by naming a URL.
  Correction points: `_member_row`, `_member_page_path`,
  `_create_page_path`.
- Which form field takes each value, addressed by name substring.
  Correction point: `_fill`.
- The role use cases and store doubles, as
  `tests/unit/access/application/test_role_writes.py` records; the files
  correct together.

## Expected first-run state

The Team page today carries its create form and its row actions inline,
so the tests that discover a create page or a member's page fail on a
*wrong value* — the page renders, what is asserted of it is not there.
The role-blocked test fails on an *absent target*, the role use cases not
existing. The two states establish different things and the manifest
records which is which.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member, deactivate_member
from commerce_ops.access.infrastructure.driving import members_admin as page_module

# DERIVED sample values; no artifact fixes example identities or names.
ADMIN_IDENTITY: Final = "U01ALICE"
SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
RETIRED_IDENTITY: Final = "U04DAVE"
NEWCOMER_IDENTITY: Final = "U05ERIN"

ADMIN_NAME: Final = "Alice Admin"
SECOND_ADMIN_NAME: Final = "Bob Admin"
MEMBER_NAME: Final = "Carol Member"
RETIRED_NAME: Final = "Dave Departed"
NEWCOMER_NAME: Final = "Erin Newcomer"

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

_YEAR: Final = str(datetime.now(UTC).year)

#: INVENTED: how the surface spells each action. LOCATORS, not
#: prohibitions — a test that cannot find a control fails loudly.
_DEACTIVATE_HINTS: Final = ("deactivat",)
_REACTIVATE_HINTS: Final = ("reactivat", "restore", "reinstate")
_ROW_ACTION_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "edit": ("edit",),
    "deactivate": ("deactivat",),
    "reactivate": ("reactivat",),
}

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")

#: Structures a row never encloses. Used to tell a row from a
#: whole-page wrapper that happens to name one member.
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


_ID_NAMES: Final = ("id", "member_id", "identifier")
_NAME_NAMES: Final = ("display_name", "name")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_ACTIVE_NAMES: Final = ("active", "is_active")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("member", "role", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored row exposes no {what} under any of {names} — correct this "
        "file's accessor names to the implemented row"
    )


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _is_active(row: Any) -> bool:
    return bool(_field(row, _ACTIVE_NAMES, "active flag"))


def _row_for(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return row
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    return _field(_row_for(store, identity), _ID_NAMES, "generated identifier")


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


async def _create_role(
    collections: _Collections, *, slug: str, title: str, default_holder: Any
) -> Any:
    step = _use_case(("create_role",), "create-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": THE_CREATING_ADMIN,
        "slug": slug,
        "title": title,
    }
    attempts: tuple[Callable[[], Any], ...] = (
        lambda: step(**common, status="active", default_holder=default_holder),
        lambda: step(**common, status="active", default_holder_id=default_holder),
        lambda: step(**common, status="active", holder=default_holder),
    )
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _argument_shape(error):
                raise
    pytest.fail("no attempted call shape matched `create_role`'s signature")


# ---------------------------------------------------------------------------
# Starting states
# ---------------------------------------------------------------------------


async def _create(
    store: _FakeMembersStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
    principal: str = THE_CREATING_ADMIN,
) -> Any:
    return await create_member(
        members=store,
        principal=principal,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _build_seeded() -> _Collections:
    """Two active admins, one active member, one deactivated member —
    built through the write path, so every row is one a real write
    produced. The second admin is what lets the first be deactivated at
    all under the last-admin floor."""
    collections = _Collections()
    await _create(
        collections.members,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create(
        collections.members,
        display_name=SECOND_ADMIN_NAME,
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    await _create(
        collections.members,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
    )
    await _create(
        collections.members,
        display_name=RETIRED_NAME,
        slack_identity=RETIRED_IDENTITY,
    )
    await deactivate_member(
        members=collections.members,
        principal=THE_EDITING_ADMIN,
        member_id=_id_of(collections.members, RETIRED_IDENTITY),
    )
    return collections


async def _build_with_one_admin() -> _Collections:
    """One active admin — the last one — plus one ordinary member."""
    collections = _Collections()
    await _create(
        collections.members,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create(
        collections.members,
        display_name=MEMBER_NAME,
        slack_identity=MEMBER_IDENTITY,
    )
    return collections


async def _build_with_blocking_roles() -> _Collections:
    """A member who is the default holder of three active roles."""
    collections = await _build_seeded()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    for slug, title in (
        ("supply-chain", "Supply Chain Manager"),
        ("ppc", "PPC Manager"),
        ("brand", "Brand Manager"),
    ):
        await _create_role(collections, slug=slug, title=title, default_holder=member)
    return collections


def _seeded() -> _Collections:
    """Built off the event loop: the tests are synchronous and drive the
    ASGI app through `TestClient`'s own portal."""
    return asyncio.run(_build_seeded())


def _one_admin() -> _Collections:
    return asyncio.run(_build_with_one_admin())


def _blocking_roles() -> _Collections:
    return asyncio.run(_build_with_blocking_roles())


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


@dataclass
class _Text:
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

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(
            _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        )

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
            self._stack[-1].children.append(_Text(" ".join(data.split())))


def _tree(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    return parser.root


def _elements(node: _Node) -> Iterator[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _elements(child)


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


def _size(node: _Node) -> int:
    return 1 + sum(1 for _ in _elements(node))


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _nearest(node: _Node, tag: str) -> _Node | None:
    return next((a for a in _ancestors(node) if a.tag == tag), None)


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
        for child in _elements(element):
            name = child.attrs.get("name")
            if not name:
                continue
            if child.tag == "input":
                kind = (child.attrs.get("type") or "text").lower()
                if kind in ("checkbox", "radio") and "checked" not in child.attrs:
                    continue
                fields[name] = child.attrs.get(
                    "value", "on" if kind == "checkbox" else ""
                )
            elif child.tag == "select":
                selected = [
                    option.attrs.get("value", _all_text(option))
                    for option in _elements(child)
                    if option.tag == "option" and "selected" in option.attrs
                ]
                values = [
                    option.attrs.get("value", _all_text(option))
                    for option in _elements(child)
                    if option.tag == "option"
                ]
                fields[name] = (
                    selected[0] if selected else (values[0] if values else "")
                )
            elif child.tag == "textarea":
                fields[name] = _all_text(child)
        found.append(_Form(method, url, fields, element))
    return found


def _fill(form: _Form, **by_substring: str) -> dict[str, str]:
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
            filled[name] = value
    return filled


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _client(monkeypatch: pytest.MonkeyPatch, collections: _Collections) -> TestClient:
    monkeypatch.setattr(page_module, "members", collections.members)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    # INVENTED: the page reaches the role collection through a
    # module-level `roles` name, the way it reaches the membership. It
    # must reach it somehow — the role-blocked refusal cannot be
    # surfaced otherwise — and no artifact fixes how.
    monkeypatch.setattr(page_module, "roles", collections.roles, raising=False)
    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _list_path() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the Team router exposes no parameterless GET route"
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


def _reachable(client: TestClient, html: str, needle: str) -> str:
    """The page text in which `needle` is reachable — the list itself, or
    a view one discovered link away, since the delta requires
    deactivated members be *reachable* rather than listed."""
    if needle in html:
        return html
    for word in ("deactivat", "inactive", "former", "archived"):
        for link in _links(_tree(html)):
            if word not in (link.attrs["href"] + " " + _all_text(link)).lower():
                continue
            response = client.get(_resolve(link.attrs["href"]))
            if response.status_code == 200 and needle in response.text:
                return str(response.text)
    pytest.fail(
        f"{needle!r} was not reachable from the Team list — neither listed on "
        "it nor behind any discovered link"
    )


def _member_row(root: _Node, identity: str, name: str) -> _Node:
    """The one member's own region of the list.

    INVENTED: the **largest** element naming this member and naming no
    other, that encloses none of the structures a row never encloses — a
    table, the page's header or navigation, a heading, a stylesheet
    link. Markup-agnostic, so a table row, a list item or a card all
    read the same.

    Largest rather than smallest deliberately. The smallest such element
    is a leaf cell carrying the identity and nothing else, which carries
    no controls whatever the page does — so a row-carries-no-actions
    assertion read off it passes by construction. That is the defect
    `tasks.md` 10.9 names, and it was observed in this very file before
    the locator was corrected.
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
            "member, so that member's row cannot be isolated — correct "
            "`_member_row` to the implemented page"
        )
    return max(candidates, key=_size)


def _member_page_path(client: TestClient, identity: str, name: str) -> str:
    """That member's own page, reached the way an admin reaches it —
    through the display-name link on their row."""
    view = _reachable(client, _get(client), identity)
    row = _member_row(_tree(view), identity, name)
    for link in _links(row):
        if _all_text(link).strip() == name or name.lower() in _all_text(link).lower():
            return _resolve(link.attrs["href"])
    pytest.fail(
        f"{identity!r}'s row offers no link whose text is their display name, "
        "so the member's own page cannot be reached in one action"
    )


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


def _create_form_in(html: str) -> _Form | None:
    for form in _forms(_tree(html)):
        names = " ".join(form.fields).lower()
        if "name" in names and "slack" in names:
            return form
    return None


def _require_create_form(html: str) -> _Form:
    found = _create_form_in(html)
    if found is None:
        pytest.fail("no create-a-member form was found on the page")
    return found


def _action_form(
    page: str, hints: tuple[str, ...], excluding: tuple[str, ...]
) -> _Form:
    found = [
        form
        for form in _forms(_tree(page))
        if any(
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
            f"{len(found)} forms on the page look like the {hints} action; "
            "correct this file's action vocabulary to the implemented page"
        )
    return found[0]


def _positions(html: str, *needles: str) -> list[int]:
    found = []
    for needle in needles:
        at = html.find(needle)
        assert at >= 0, f"{needle!r} is not rendered on the page"
        found.append(at)
    return found


def _breadcrumb_of(root: _Node, *, current: str) -> _Node:
    """The page's breadcrumb — the smallest element carrying a link to
    the Team list *and* the current segment's text."""
    inbound = [
        link
        for link in _links(root)
        if urlsplit(link.attrs["href"]).path == _list_path()
        and not urlsplit(link.attrs["href"]).query
    ]
    if not inbound:
        pytest.fail(
            f"the page renders no link to the Team list at {_list_path()!r}, "
            "so it carries no breadcrumb back to it"
        )
    candidates = [
        ancestor
        for link in inbound
        for ancestor in _ancestors(link)
        if current.lower() in _all_text(ancestor).lower()
        and ancestor.tag not in ("html", "body", "#document")
    ]
    if not candidates:
        pytest.fail(
            "no element of the page carries both a link to the Team list and "
            f"the text {current!r} — correct `_breadcrumb_of` to the "
            "implemented page"
        )
    return min(candidates, key=_size)


# ===========================================================================
# MODIFIED requirement: The Team page shows the membership whole
# ===========================================================================


def test_an_entrys_attribution_is_readable_on_the_members_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An entry's attribution is readable.

    WHEN an admin opens a member's own page
    THEN the page presents who created the entry and when, and the most
    recent change to it with who made it and when.

    The revision moves this from the list to the member's page, so the
    assertion is made against that page and the *list* is asserted not
    to carry it — four attribution facts per row is what made the list a
    place to cram things, and leaving them there would mean the rebuild
    did not happen.

    The deactivated member is the one entry whose creator and most
    recent change were made by different principals, which is what makes
    "the most recent change" a real assertion rather than a second
    reading of the creation.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    page = _get(client, _member_page_path(client, RETIRED_IDENTITY, RETIRED_NAME))

    # SPECIFIED: who created the entry.
    assert THE_CREATING_ADMIN in page, (
        "the member's page does not present who created the entry"
    )
    # SPECIFIED: the most recent change, with who made it.
    assert THE_EDITING_ADMIN in page, (
        "the member's page does not present its most recent change and who made it"
    )
    # SPECIFIED: and when, for both.
    assert _YEAR in page, "the member's page presents no time alongside the attribution"
    # SPECIFIED (the revision itself): read from the member's own page
    # rather than from the list.
    listing = _get(client)
    assert THE_CREATING_ADMIN not in listing, (
        "the Team list still presents each entry's attribution; the revision "
        "moves it onto the member's own page"
    )


@pytest.mark.parametrize(
    ("identity", "name"),
    [
        pytest.param(MEMBER_IDENTITY, MEMBER_NAME, id="active"),
        pytest.param(RETIRED_IDENTITY, RETIRED_NAME, id="deactivated"),
    ],
)
def test_a_members_row_carries_no_actions(
    monkeypatch: pytest.MonkeyPatch, identity: str, name: str
) -> None:
    """Scenario: A member's row carries no actions.

    WHEN any member's row is rendered, active or deactivated
    THEN the row carries no control that edits, deactivates or
    reactivates the member.

    Parametrized over both, since "active or deactivated" is the
    scenario's own scope and a page could plausibly leave the reactivate
    control on a deactivated row alone.

    The row's link to the member's own page is not such a control: the
    requirement's neighbour makes the display name the row's way in. So
    what is asserted is that the row encloses no form, and that no
    control on it names an edit, a deactivation or a reactivation.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    view = _reachable(client, _get(client), identity)
    row = _member_row(_tree(view), identity, name)

    # SPECIFIED: no control that edits, deactivates or reactivates.
    forms = [element for element in _elements(row) if element.tag == "form"]
    assert forms == [], (
        f"{identity!r}'s row encloses {len(forms)} form(s), so a change to the "
        "member is submitted from the row rather than from their own page"
    )
    for control in _action_controls(row):
        haystack = _control_haystack(control)
        for what, hints in _ROW_ACTION_HINTS.items():
            assert not any(hint in haystack for hint in hints), (
                f"{identity!r}'s row carries a {what} control: {haystack[:120]!r}"
            )


def test_a_members_name_opens_their_own_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A member's name opens their own page.

    WHEN any member's row is rendered
    THEN their display name offers that member's own page in one action.

    "That member's own page" is asserted by following the link and
    reading what comes back: the page names this member's Slack identity
    and no other's, so a name linking to the list, to a filter or to
    another member fails.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    page = _get(client, _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME))

    # SPECIFIED: the page reached is that member's own.
    assert MEMBER_IDENTITY in page
    assert MEMBER_NAME in page
    for other in (ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY, RETIRED_IDENTITY):
        assert other not in page, (
            f"the page reached from {MEMBER_IDENTITY!r}'s name also names "
            f"{other!r}, so it is not that member's own page"
        )


# ===========================================================================
# MODIFIED requirement: A member can be created and edited from the page
# ===========================================================================


def test_creating_is_reached_from_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Creating is reached from the list.

    WHEN the Team page is rendered
    THEN it offers the create page in one action, and carries no create
    form of its own.

    The second half is the whole of the change on this scenario: the
    list carried a full-width create form at its top, and it goes.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    html = _get(client)

    # SPECIFIED: it offers the create page in one action.
    path = _create_page_path(client)
    assert _create_form_in(_get(client, path)) is not None
    # SPECIFIED: and carries no create form of its own.
    assert _create_form_in(html) is None, (
        "the Team list still carries a create form at its top; creating "
        "happens on a page of its own"
    )


def test_a_created_member_appears_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A created member appears on the page.

    WHEN an admin submits a valid new member from the create page
    THEN the member appears on the active membership with the submitted
    identity data.

    The write is asserted twice over — through the store (it went
    through the membership's use cases, so a row exists and is active)
    and through the reloaded list (the admin sees what they submitted).
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    form = _require_create_form(_get(client, _create_page_path(client)))
    submitted = _fill(form, name=NEWCOMER_NAME, slack=NEWCOMER_IDENTITY)
    response = _submit(client, form, submitted)
    assert response.status_code < 400, response.text

    # SPECIFIED: the member is on the active membership.
    row = _row_for(collections.members, NEWCOMER_IDENTITY)
    assert _is_active(row) is True
    assert str(_field(row, _NAME_NAMES, "display name")) == NEWCOMER_NAME
    # SPECIFIED: and appears with the submitted data.
    after = _get(client)
    assert NEWCOMER_NAME in after
    assert NEWCOMER_IDENTITY in after


def test_a_rejected_write_shows_every_fault_with_the_typed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected write shows every fault with the typed
    values.

    WHEN an admin submits a member the membership's validation rejects
    THEN the form is re-presented showing every fault and still holding
    the submitted values, and the membership is unchanged.

    The submission carries *two* faults — a duplicate Slack identity and
    an empty display name — so "every fault" is a real count rather than
    a single message.

    What the revision adds is the last clause of the requirement's own
    prose: a rejection SHALL NOT return the admin to the list. That is
    asserted as the response not listing the rest of the membership,
    which is the state an admin would be left reading a refusal away
    from the values that caused it.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)
    before_rows = collections.members.rows
    before_saves = len(collections.members.saves)

    form = _require_create_form(_get(client, _create_page_path(client)))
    submitted = _fill(form, name="", slack=MEMBER_IDENTITY)
    response = _submit(client, form, submitted)

    # SPECIFIED: the form is re-presented (not an error page).
    assert response.status_code < 500, response.text
    body = response.text
    represented = _create_form_in(body)
    assert represented is not None, "the rejected write re-presented no form"
    # SPECIFIED: still holding the submitted values.
    assert any(
        MEMBER_IDENTITY in str(value) for value in represented.fields.values()
    ), (
        "the re-presented form does not hold the submitted Slack identity; "
        f"fields: {represented.fields}"
    )
    # SPECIFIED: showing every fault — both of them, distinguishably.
    assert MEMBER_IDENTITY in body, "no fault names the duplicated identity"
    assert any(marker in body.lower() for marker in ("name", "display")), (
        "no fault mentions the empty display name"
    )
    # SPECIFIED: a rejection does not return the admin to the list.
    for other in (ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY, RETIRED_IDENTITY):
        assert other not in body, (
            f"the rejection returned the admin to the list ({other!r} is on "
            "the response), so the refusal is read away from the values that "
            "caused it"
        )
    # SPECIFIED: and the membership is unchanged.
    assert collections.members.rows == before_rows
    assert len(collections.members.saves) == before_saves


def test_editing_happens_on_the_members_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Editing happens on the member's page.

    WHEN an admin changes a member's display name
    THEN the change is submitted from that member's own page and the
    page reflects it afterwards.

    "From that member's own page" is not incidental: the edit form is
    discovered on the page reached through the row's name link, so an
    implementation still editing in a row's cells has no page for this
    test to find.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)
    path = _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME)

    page = _get(client, path)
    forms = [
        form
        for form in _forms(_tree(page))
        if any("name" in name.lower() for name in form.fields)
    ]
    assert forms, (
        "the member's own page offers no form carrying a display-name field, "
        "so editing does not happen there"
    )
    form = forms[0]
    response = _submit(client, form, _fill(form, name="Carol Corrected"))
    assert response.status_code < 400, response.text

    # SPECIFIED: the change lands through the membership's use cases.
    row = _row_for(collections.members, MEMBER_IDENTITY)
    assert str(_field(row, _NAME_NAMES, "display name")) == "Carol Corrected"
    assert _slack(row) == MEMBER_IDENTITY
    # SPECIFIED: and the page reflects it afterwards.
    assert "Carol Corrected" in _get(client, path)


# ===========================================================================
# MODIFIED requirement: Deactivation and reactivation are available from the
# page
# ===========================================================================


def test_a_deactivation_lands_and_the_member_is_set_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A deactivation lands and the member is set apart.

    WHEN an admin deactivates a member who is neither the last active
    admin nor an active role's default holder
    THEN the member leaves the active membership and appears among the
    deactivated.

    The control is discovered on the member's own page, which is where
    the revision puts it. The member holds no role at all, so the
    scenario's second exclusion is met by construction — and its first
    by the membership holding two active admins.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)
    path = _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME)

    form = _action_form(_get(client, path), _DEACTIVATE_HINTS, _REACTIVATE_HINTS)
    response = _submit(client, form, dict(form.fields))
    assert response.status_code < 400, response.text

    # SPECIFIED: the member leaves the active membership.
    assert _is_active(_row_for(collections.members, MEMBER_IDENTITY)) is False
    after = _get(client)
    actives = _positions(after, ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY)
    # SPECIFIED: and appears among the deactivated.
    view = _reachable(client, after, MEMBER_IDENTITY)
    if view is after:
        (moved,) = _positions(view, MEMBER_IDENTITY)
        assert moved > max(actives) or moved < min(actives), (
            "the deactivated member is still rendered among the active membership"
        )


def test_a_reactivation_is_offered_on_the_members_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED, from the requirement's own sentence: "Deactivating an
    active member and reactivating a deactivated one SHALL be offered on
    that member's own page, not on their row."

    Only the deactivation half carries scenarios; the reactivation half
    is asserted here as derived, so that a rebuild offering no way back
    from deactivation is caught rather than passing silently.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)
    path = _member_page_path(client, RETIRED_IDENTITY, RETIRED_NAME)

    form = _action_form(_get(client, path), _REACTIVATE_HINTS, ())
    response = _submit(client, form, dict(form.fields))
    assert response.status_code < 400, response.text

    # DERIVED: the member is active again, under the same entry.
    assert _is_active(_row_for(collections.members, RETIRED_IDENTITY)) is True
    assert RETIRED_IDENTITY in _get(client)


def test_a_blocked_deactivation_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A blocked deactivation explains itself.

    WHEN an admin attempts to deactivate the last active admin
    THEN the page shows the refusal's explanation and the member remains
    on the active membership.

    Observed on the member's own page, which is where the revision puts
    both the control and the refusal. A refusal that reached the admin
    as a blank page, a 500 or a silent no-op would leave them with no
    idea why nothing happened.
    """
    collections = _one_admin()
    client = _client(monkeypatch, collections)
    before_saves = len(collections.members.saves)
    path = _member_page_path(client, ADMIN_IDENTITY, ADMIN_NAME)

    form = _action_form(_get(client, path), _DEACTIVATE_HINTS, _REACTIVATE_HINTS)
    response = _submit(client, form, dict(form.fields))

    # SPECIFIED: the page shows the refusal's explanation.
    assert response.status_code < 500, response.text
    assert "admin" in response.text.lower(), (
        "the refused deactivation surfaced no explanation on the page"
    )
    # SPECIFIED: the member remains on the active membership.
    assert _is_active(_row_for(collections.members, ADMIN_IDENTITY)) is True
    assert len(collections.members.saves) == before_saves
    assert ADMIN_IDENTITY in _get(client)


def test_a_role_blocked_deactivation_names_every_blocking_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A role-blocked deactivation names every blocking role.

    WHEN an admin attempts to deactivate a member who is the default
    holder of several active roles
    THEN the page shows the refusal naming all of those roles, and the
    member remains on the active membership.

    Three blocking roles, and every one of them asserted: "a refusal
    listing one of eight roles would be read as the only obstacle" is
    the requirement's own reason, and a page surfacing only the first
    fault is exactly what it forbids.
    """
    collections = _blocking_roles()
    client = _client(monkeypatch, collections)
    before_saves = len(collections.members.saves)
    path = _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME)

    form = _action_form(_get(client, path), _DEACTIVATE_HINTS, _REACTIVATE_HINTS)
    response = _submit(client, form, dict(form.fields))

    # SPECIFIED: the page shows the refusal naming all of those roles.
    assert response.status_code < 500, response.text
    lowered = response.text.lower()
    missing = [
        slug
        for slug in ("supply-chain", "ppc", "brand")
        if slug not in lowered
        and slug.replace("-", " ") not in lowered
        and slug.replace("-", " ").title().lower() not in lowered
    ]
    assert missing == [], (
        f"the page names only some of the blocking roles; missing {missing!r}"
    )
    # SPECIFIED: and the member remains on the active membership.
    assert _is_active(_row_for(collections.members, MEMBER_IDENTITY)) is True
    assert len(collections.members.saves) == before_saves


# ===========================================================================
# ADDED requirement: The create page and a member's own page carry a
# breadcrumb back to the list
# ===========================================================================


def test_a_members_page_offers_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A member's page offers the list.

    WHEN a member's own page is rendered
    THEN it carries a breadcrumb naming the Team list as a link and the
    member's display name as the current, un-linked segment.

    The requirement adds that the current segment is rendered as the
    page's own title, so the page carries no separate title beside it —
    asserted as the display name appearing nowhere as a link on that
    page.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    page = _get(client, _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME))
    crumb = _breadcrumb_of(_tree(page), current=MEMBER_NAME)

    # SPECIFIED: the Team list is named as a link.
    linked = [
        link
        for link in _links(crumb)
        if urlsplit(link.attrs["href"]).path == _list_path()
    ]
    assert linked, "the breadcrumb renders no live link back to the Team list"
    # SPECIFIED: the display name is the current, un-linked segment.
    assert MEMBER_NAME in _all_text(crumb)
    assert MEMBER_NAME not in " ".join(_all_text(link) for link in linked), (
        "the member's display name is rendered as the breadcrumb's link rather "
        "than as its current segment"
    )
    assert [
        link for link in _links(_tree(page)) if _all_text(link).strip() == MEMBER_NAME
    ] == [], "the member's display name is a link on their own page"


def test_the_create_page_offers_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The create page offers the list.

    WHEN the create page is rendered
    THEN it carries a breadcrumb naming the Team list as its linked
    segment and `New member` as its current, un-linked segment.

    `New member` is the delta's own literal, so it is asserted literally
    rather than as a family of words.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    page = _get(client, _create_page_path(client))
    crumb = _breadcrumb_of(_tree(page), current="New member")

    linked = [
        link
        for link in _links(crumb)
        if urlsplit(link.attrs["href"]).path == _list_path()
    ]
    # SPECIFIED: the Team list as its linked segment.
    assert linked, "the create page's breadcrumb links nowhere"
    # SPECIFIED: `New member` as its current, un-linked segment.
    assert "New member" in _all_text(crumb)
    assert "New member" not in " ".join(_all_text(link) for link in linked), (
        "`New member` is rendered as the breadcrumb's link rather than as its "
        "current segment"
    )


def test_the_breadcrumb_needs_no_scripting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The breadcrumb needs no scripting.

    WHEN a member's page is rendered and its breadcrumb link is followed
    without scripting
    THEN the Team list is reached.

    "Without scripting" is asserted by following a plain `href` with a
    GET — no `hx-*` attribute consulted — and reading what comes back:
    the list, holding the active membership.
    """
    collections = _seeded()
    client = _client(monkeypatch, collections)

    page = _get(client, _member_page_path(client, MEMBER_IDENTITY, MEMBER_NAME))
    crumb = _breadcrumb_of(_tree(page), current=MEMBER_NAME)
    linked = [
        link
        for link in _links(crumb)
        if urlsplit(link.attrs["href"]).path == _list_path()
    ]
    assert linked, "the breadcrumb carries no link to the Team list"

    response = client.get(_resolve(linked[0].attrs["href"]))

    # SPECIFIED: the Team list is reached.
    assert response.status_code == 200, response.text
    for identity in (ADMIN_IDENTITY, SECOND_ADMIN_IDENTITY, MEMBER_IDENTITY):
        assert identity in response.text, (
            f"following the breadcrumb did not reach the Team list ({identity!r} "
            "is not on the response)"
        )
