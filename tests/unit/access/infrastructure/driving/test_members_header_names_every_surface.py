"""The Team page's header names **every** admin surface the session can
reach (`members-admin`).

Derived strictly from the MODIFIED requirement *The page carries a header
from which the other admin surface is reachable* in
`openspec/changes/add-launch-tracking-pages/specs/roster-admin/spec.md` —
the **two scenarios the delta adds**:

- *Every other admin surface is reachable from the membership*
- *A surface added later is named by the header*

The requirement's two pre-existing scenarios are carried forward verbatim
by the delta and are already covered, unweakened, by
`tests/unit/access/infrastructure/driving/test_members_admin_presentation_vocabulary.py`
— `test_the_playbook_page_is_reachable_from_the_members` and
`test_the_header_is_rendered_on_a_members_holding_nobody`. This pass
neither edits nor deletes them; the manifest at
`openspec/changes/add-launch-tracking-pages/test-manifest.md` records
that accounting.

## Why this file exists at all

`design.md` — Decision 9: generalizing one capability's header
requirement without the other "would leave the launch surface reachable
from the Team page and not from the step list ... the exact asymmetry
the generalization exists to close, and one that a test derived from a
single delta would not catch". `tasks.md` 5.3 asks for the header tests
where each capability is tested; the playbook half is
`tests/unit/launch/infrastructure/driving/test_admin_header_names_every_surface.py`.

## Level

The membership router mounted beside the playbook router and the new launch
router, the way `main.py` composes them — the smallest unit that can
observe that another module's surface is offered and actually served.

## Expected first-run state

**Absent target.** `commerce_ops.launch.infrastructure.driving.launch_admin`
does not exist, so both tests are expected to fail through
`_launch_module()`. Per `ai-toolkit:testing` that establishes absence and
nothing about whether these assertions are any good.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1133 passed, 0
failed, 94 skipped (the whole integration tier, no database configured)
on 2026-08-27.

## What is fixed, and what is INVENTED

Fixed: that the Team page carries the header, that it names every
admin surface the session can reach, that each is offered in one action
without scripting, that the membership is identified as the surface being
viewed, and that a surface added later is named there.

INVENTED, with correction points in the code: how a header is located
and how it identifies the current surface (`_header_of`,
`_identifies_current`, taken unchanged in shape from
`tests/unit/launch/infrastructure/driving/test_admin_surface_navigation_and_assets.py`);
the words by which each surface is named; and every seam of the launch
module (`_LAUNCH_SEAMS`).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import members_admin as page_module
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    LaunchPlaybook,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_module,
)

_LAUNCH_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _launch_module() -> ModuleType:
    try:
        return importlib.import_module(_LAUNCH_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_LAUNCH_MODULE_NAME} does not exist ({absent}), so there is no "
            "third admin surface for the membership's header to name — this is the "
            "absent-target state and establishes nothing about the assertions "
            "in this test"
        )


SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

#: INVENTED: how each admin surface is named in a header.
# A LOCATOR, not a prohibition: these are the words by which the header's
# entry for this surface is found, and it can still fail -- so it is renamed,
# not left. The header now labels this surface `Team`
# (`rename-the-roster-to-members`), so "team" is what locates it and must be
# here or the assertion has no subject. "members"/"member" stay because the
# page itself still says them. "user"/"users" are gone: the surface no longer
# uses that word anywhere, so accepting it would let this pass on a header
# that never names this surface.
_MEMBERS_WORDS: Final = ("team", "members", "member")
_PLAYBOOK_WORDS: Final = ("playbook", "step", "steps")
_LAUNCH_WORDS: Final = ("launch", "launches", "product")

_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")

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
_HIDDEN_CLASSES: Final = ("hidden", "is-hidden", "d-none", "sr-only", "visually-hidden")

_LAUNCH_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "members": ("members", "members_store", "read_members"),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
}
_PLAYBOOK_MEMBERS_SEAMS: Final = (
    "members",
    "read_members",
    "members",
    "members_reader",
)


# ---------------------------------------------------------------------------
# Store doubles (see test_members_admin_page.py)
# ---------------------------------------------------------------------------


class _FakeMembersStore:
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


async def _build_members() -> _FakeMembersStore:
    store = _FakeMembersStore()
    await create_member(
        members=store,
        principal="the-seeding-admin",
        display_name="Alice Admin",
        slack_identity=PRINCIPAL,
        clickup_user_id=None,
        admin=True,
    )
    return store


def _members_store() -> _FakeMembersStore:
    """Built off the event loop: these tests are synchronous and drive the
    ASGI app through `TestClient`'s own portal."""
    return asyncio.run(_build_members())


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member("prs_01HQ8Z6M4A", "Alice Admin"),)

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeStepStore:
    def __init__(self) -> None:
        self.records: tuple[Any, ...] = ()
        self.version = 41

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


class _EmptyLaunchStore:
    async def get_by_product_id(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def list_all(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return await self.list_all(*args, **kwargs)

    async def list_launches(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return await self.list_all(*args, **kwargs)


class _EmptyPlaybooks:
    def get(self, version: str) -> LaunchPlaybook:
        return LaunchPlaybook(
            version=version,
            gates=tuple(
                Gate(
                    identifier=identifier,
                    position=position,
                    opening=(
                        GateOpening.REQUIRES_CONFIRMATION
                        if identifier in CONFIRMATION_GATES
                        else GateOpening.AUTOMATIC
                    ),
                )
                for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
            ),
            steps=(),
        )


class _EmptyCatalog:
    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    async def get_product_by_id(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _install_launch_seam(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, seam: str, value: Any
) -> None:
    for name in _LAUNCH_SEAMS[seam]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"{_LAUNCH_MODULE_NAME} exposes no {seam!r} seam under any of "
        f"{_LAUNCH_SEAMS[seam]} — correct `_LAUNCH_SEAMS`"
    )


@dataclass(frozen=True)
class _Surfaces:
    client: TestClient
    launch: ModuleType


def _app(
    monkeypatch: pytest.MonkeyPatch, *, members: _FakeMembersStore | None = None
) -> _Surfaces:
    launch = _launch_module()

    monkeypatch.setattr(
        page_module, "members", _members_store() if members is None else members
    )
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)

    monkeypatch.setattr(playbook_module, "steps", _FakeStepStore())
    monkeypatch.setattr(playbook_module, "verify_admin_session", _fake_verify)
    for name in _PLAYBOOK_MEMBERS_SEAMS:
        if hasattr(playbook_module, name):
            monkeypatch.setattr(playbook_module, name, _FakeMembers())
            break

    _install_launch_seam(monkeypatch, launch, "verify", _fake_verify)
    _install_launch_seam(monkeypatch, launch, "launches", _EmptyLaunchStore())
    _install_launch_seam(monkeypatch, launch, "playbooks", _EmptyPlaybooks())
    _install_launch_seam(monkeypatch, launch, "members", _members_store())
    catalog = _EmptyCatalog()
    _install_launch_seam(monkeypatch, launch, "list_products", catalog.list_products)
    _install_launch_seam(
        monkeypatch, launch, "get_product_by_id", catalog.get_product_by_id
    )

    app = FastAPI()
    app.include_router(page_module.router)
    app.include_router(playbook_module.router)
    app.include_router(launch.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surfaces(client, launch)


def _shortest_get_route(router: Any) -> str:
    candidates = [
        str(route.path)
        for route in router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" not in route.path
    ]
    assert candidates, f"{router!r} exposes no parameterless GET route"
    return str(min(candidates, key=len))


def _members_html(surfaces: _Surfaces) -> str:
    response = surfaces.client.get(_shortest_get_route(page_module.router))
    assert response.status_code == 200, response.text
    return str(response.text)


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
            self._stack[-1].children.append(_Text(_flat(data)))


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


def _all_text(node: _Node) -> str:
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_all_text(child))
    return " ".join(part for part in found if part).lower()


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


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


def _size(node: _Node) -> int:
    return 1 + sum(1 for _ in _elements(node))


def _links_to(root: _Node, path: str) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and urlsplit(element.attrs.get("href", "")).path == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _names(node: _Node, words: tuple[str, ...]) -> bool:
    return any(word in _all_text(node) for word in words)


def _header_of(root: _Node, *, other_path: str) -> _Node:
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the Team page renders no link to {other_path!r} at all, so it "
            "carries no header from which that admin surface is reachable"
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
            f"the link to {other_path!r} sits in no element that also names the "
            "members without enclosing the page's own tables or forms — correct "
            "`_header_of` or `_MEMBERS_WORDS`"
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


# ===========================================================================
# MODIFIED requirement: The page carries a header from which the other admin
# surface is reachable — the two scenarios this change adds
# ===========================================================================


def test_every_other_admin_surface_is_reachable_from_the_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Every other admin surface is reachable from the membership.

    WHEN the Team page is rendered
    THEN its header offers each admin surface the session can reach,
    other than the membership itself, in one action.
    """
    surfaces = _app(monkeypatch)
    playbook_path = _shortest_get_route(playbook_module.router)
    launch_path = _shortest_get_route(surfaces.launch.router)

    header = _header_of(_tree(_members_html(surfaces)), other_path=playbook_path)

    # SPECIFIED: *each* other surface — not the playbook page alone — in
    # one action, and without scripting.
    for path, what in ((playbook_path, "playbook"), (launch_path, "launch")):
        assert _offers_in_one_action(header, path), (
            f"the Team page's header offers no live link to the {what} "
            f"surface at {path!r} — an admin who reaches the membership cannot get "
            "to it without typing a URL"
        )
        served = surfaces.client.get(_links_to(header, path)[0].attrs["href"])
        assert served.status_code == 200, (
            f"the header's {what} link does not serve that surface: "
            f"{served.status_code}"
        )
    # SPECIFIED (carried forward): the header still identifies the membership
    # as the surface being viewed.
    assert _identifies_current(header, words=_MEMBERS_WORDS), (
        "the header does not identify the membership as the surface currently "
        "viewed, so it reads as an undifferentiated set of links"
    )


def test_a_surface_added_later_is_named_by_the_members_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A surface added later is named by the header.

    WHEN an admin surface beyond the playbook and membership pages is
    reachable by the session
    THEN the Team page's header names it and offers it in one action.

    The surface beyond the two is the launch surface this change adds —
    the case the generalization was written for, and the one a header
    frozen at "the other admin surface" would leave unreachable.
    """
    surfaces = _app(monkeypatch)
    playbook_path = _shortest_get_route(playbook_module.router)
    launch_path = _shortest_get_route(surfaces.launch.router)

    header = _header_of(_tree(_members_html(surfaces)), other_path=playbook_path)

    # SPECIFIED: the header *names* it...
    assert _names(header, _LAUNCH_WORDS), (
        "the Team page's header does not name the launch surface: "
        f"{_flat(_all_text(header))[:300]!r}"
    )
    # ...and offers it in one action.
    assert _offers_in_one_action(header, launch_path), (
        f"the Team page's header offers no live link to {launch_path!r}, so "
        "a surface added later is left unreachable from a page that predates it"
    )


#: See the launch-side twin of this test for why the path assertion, not
#: the wording, is what discriminates here.
_PRODUCT_WORDS: Final = ("products", "product")


def test_the_product_index_is_named_by_the_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The index is reachable from another admin surface.

    WHEN an existing admin surface is rendered
    THEN its header offers the product index in one action.

    Both capabilities or neither: generalizing the header on one side
    alone would leave the product surface reachable from the playbook
    page and not from the membership, which is the asymmetry the
    generalization exists to close.
    """
    from commerce_ops.launch.infrastructure.driving import (
        product_dossier as product_module,
    )

    surfaces = _app(monkeypatch)
    playbook_path = _shortest_get_route(playbook_module.router)
    product_path = _shortest_get_route(product_module.router)

    header = _header_of(_tree(_members_html(surfaces)), other_path=playbook_path)

    assert _names(header, _PRODUCT_WORDS), (
        "the Team page's header does not name the product surface: "
        f"{_flat(_all_text(header))[:300]!r}"
    )
    assert _offers_in_one_action(header, product_path), (
        f"the Team page's header offers no live link to {product_path!r}, so "
        "a surface added later is left unreachable from a page that predates it"
    )
