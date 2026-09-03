"""The guard, the header and the shared stylesheet the two product
surfaces carry (`product-dossier`, eleventh requirement).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/product-dossier/spec.md`
— the ADDED requirement *Both pages ride the admin session guard and
carry the shared header*, all five scenarios:

- *No admin session means no surface*
- *A revoked admin resolves to the same absence*
- *The index is reachable from another admin surface*
- *The dossier carries the header*
- *Presentation is shared, not page-local*

The index's own requirement is in `test_product_index_page.py` and the
dossier's in `test_product_dossier_page.py`. `test-manifest.md` at the
change root records every scenario, every assertion's classification,
and the project questions this file answered by assumption.

`tasks.md` 6.6 is why the third scenario is driven over the *existing*
admin surfaces rather than over a header this change ships: "a test
derived from this change alone would not catch an existing surface's
header failing to offer the index". The playbook and membership routers are
therefore mounted alongside the new one, the way `main.py` composes
them, and their headers are what the assertion reads. This change edits
no existing test file to do it — `test_admin_surface_navigation_and_
assets.py` is left exactly as it stands.

This change carries **no** `members-admin` and no `playbook-admin` delta,
deliberately and in either archive order (`tasks.md` 7.4). Both
capabilities' served requirements already oblige the header to name "the
admin surfaces the session can reach", so a header naming the product
index satisfies them as they stand; what is asserted below is
`product-dossier`'s own reachability obligation, which that requirement
carries itself (`tasks.md` 7.5).

## Level

All three admin routers plus the shared asset router, mounted in one
app over stores of their own. That is the smallest unit that can observe
a scenario whose WHEN starts on the playbook surface and whose THEN is
that the product index is served: neither module's routes alone can show
it. It is the level and composition
`test_admin_surface_navigation_and_assets.py` already established for
the same question about the other pair.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the absence-shaped refusal produced by one
dependency (`design.md` — Decision 10; `tasks.md` 3.2); that the index
is the surface the header names and the dossier carries the header
without being a named entry in it (`tasks.md` 6.1, 6.2); that both pages
load the shared stylesheet through `admin_assets`' route rather than
through `playbook_admin.py`'s own, and carry no page-local style block
(`tasks.md` 6.3, 6.4).

INVENTED, each recorded in the manifest with its correction point:

- The page module's seams and the session cookie's name, as in the two
  sibling files.
- That "reachable in one action" is read as a **live anchor** whose path
  is the index's — needing no scripting. Correction point:
  `_offers_in_one_action`.
- The playbook and Team page modules' own seams and store doubles,
  taken from `test_admin_surface_navigation_and_assets.py` and
  `test_members_admin_page.py`. Correction point: `_existing_surfaces`.
- That a revoked admin presents to the page as a verification that
  refuses. The *verification* half — that a principal who has lost the
  admin declaration is refused — is `access.application`'s and is
  covered in `tests/unit/access/application/
  test_admin_session_use_cases.py`; only the response shape is asserted
  here, the same split `test_playbook_admin_page.py` records.

## Expected first-run state

`commerce_ops.launch.infrastructure.driving.product_dossier` does not
exist, so every test here is expected to fail at **import** — the
absent-target state.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import members_admin as members_module
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_module,
)
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as page_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.playbook import SPECIFIED_GATE_ORDER

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"
#: An unexpired session whose principal has since lost the admin
#: declaration. It presents to the page exactly as any other refusal.
_REVOKED_SESSION_VALUE: Final = "a-session-whose-principal-lost-admin"

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

SKU: Final = "BCB-2027-01"
NAME: Final = "Bamboo Cutting Board"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
MEMBER_ADMIN_IDENTITY: Final = "U01ALICE"

_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

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

_HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "sr-only",
    "visually-hidden",
)


def _assets_module() -> ModuleType | None:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError:  # pragma: no cover - the module ships today
        return None


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
    order: int
    children: list[_Node | _Text] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {}, None, 0)
        self._stack: list[_Node] = [self.root]
        self._order = 0

    def _open(self, tag: str, attrs: list[tuple[str, str | None]]) -> _Node:
        self._order += 1
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1], self._order)
        self._stack[-1].children.append(node)
        return node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = self._open(tag, attrs)
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


def _tree(page: str) -> _Node:
    parser = _TreeParser()
    parser.feed(page)
    return parser.root


def _elements(node: _Node) -> Iterator[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _elements(child)


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


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


def _inert(node: _Node) -> bool:
    if _element_disabled(node) or _element_hidden(node):
        return True
    return any(
        _element_disabled(ancestor) or _element_hidden(ancestor)
        for ancestor in _ancestors(node)
    )


def _path_of(href: str) -> str:
    return urlsplit(href).path


def _links_to(page: str, path: str) -> list[_Node]:
    """Every anchor whose destination is exactly that page — no query,
    so a narrowing offer pointing back at a list is not mistaken for a
    header link."""
    return [
        element
        for element in _elements(_tree(page))
        if element.tag == "a"
        and _path_of(element.attrs.get("href", "")) == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _offers_in_one_action(page: str, path: str) -> bool:
    """INVENTED reading of "in one action": a live anchor, which needs
    no scripting. Correction point for a differently offered link."""
    return any(not _inert(link) for link in _links_to(page, path))


def _stylesheet_hrefs(page: str) -> list[str]:
    return [
        element.attrs["href"]
        for element in _elements(_tree(page))
        if element.tag == "link"
        and "stylesheet" in element.attrs.get("rel", "").lower()
        and element.attrs.get("href")
    ]


def _style_blocks(page: str) -> list[_Node]:
    return [element for element in _elements(_tree(page)) if element.tag == "style"]


# ---------------------------------------------------------------------------
# The product surfaces' seams
# ---------------------------------------------------------------------------

_VERIFY_NAMES: Final = ("verify_admin_session", "verify")
_SCOPE_NAMES: Final = ("resolve_scope",)
_LIST_NAMES: Final = ("list_products",)
_GET_PRODUCT_NAMES: Final = ("get_product_by_id",)
_RETAINED_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)
_STEPS_NAMES: Final = (
    "steps",
    "playbook",
    "playbooks",
    "step_store",
    "playbook_store",
    "read_playbook",
    "served_playbook",
)
_PLAYBOOK_MEMBERS_NAMES: Final = (
    "members",
    "read_members",
    "members",
    "members_reader",
)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    names: tuple[str, ...],
    value: Any,
    what: str,
) -> None:
    for name in names:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"{module.__name__} exposes no {what} seam under any of {names} — "
        "correct this file's probe to the implemented name"
    )


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


class _FakeScopeResolution:
    async def __call__(self, *args: Any, **kwargs: Any) -> AccessScope:
        return AccessScope.unrestricted()


class _FakeCatalog:
    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)

    async def list_products(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        return self.products

    async def get_product_by_id(self, *args: Any, **kwargs: Any) -> Product | None:
        wanted = None
        for value in (*args, *kwargs.values()):
            if isinstance(value, ProductId):
                wanted = value
        if wanted is None:
            for value in (*args, *kwargs.values()):
                if isinstance(value, str) and value != PRINCIPAL:
                    wanted = value  # type: ignore[assignment]
        for product in self.products:
            if str(product.id) == str(wanted):
                return product
        return None


class _EmptyRetainedRead:
    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return ()


class _EmptySteps:
    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (), 1

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return ()


def _product() -> Product:
    return Product.register(
        sku=Sku(SKU),
        marketplace_id=MARKETPLACE,
        name=NAME,
        registered_at=T_REGISTERED,
    )


# ---------------------------------------------------------------------------
# The existing admin surfaces' doubles (see
# `test_admin_surface_navigation_and_assets.py`)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _StepRecord:
    def __init__(self, definition: StepDefinition, display_order: int) -> None:
        self.definition = definition
        self.display_order = display_order
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None


class _FakeStepStore:
    def __init__(self, records: tuple[_StepRecord, ...], version: int = 41) -> None:
        self.records = records
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _PlaybookMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member(ALICE, ALICE_NAME),)


class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
        self.version += 1


def _seeded_steps() -> _FakeStepStore:
    records = tuple(
        _StepRecord(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work of hold.{gate}",
                gate=gate,
                blocking=True,
            ),
            display_order=(index + 1) * 10,
        )
        for index, gate in enumerate(SPECIFIED_GATE_ORDER)
    )
    return _FakeStepStore(records)


async def _build_members_store() -> _FakeMembersStore:
    store = _FakeMembersStore()
    await create_member(
        members=store,
        principal="the-creating-admin",
        display_name=ALICE_NAME,
        slack_identity=MEMBER_ADMIN_IDENTITY,
        clickup_user_id=None,
        admin=True,
    )
    return store


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


@dataclass
class _Surfaces:
    client: TestClient
    product: Product


def _install_product_seams(monkeypatch: pytest.MonkeyPatch, product: Product) -> None:
    catalog = _FakeCatalog(product)
    _install(monkeypatch, page_module, _VERIFY_NAMES, _fake_verify, "admin-session")
    _install(
        monkeypatch,
        page_module,
        _SCOPE_NAMES,
        _FakeScopeResolution(),
        "scope-resolution",
    )
    _install(
        monkeypatch, page_module, _LIST_NAMES, catalog.list_products, "product listing"
    )
    _install(
        monkeypatch,
        page_module,
        _GET_PRODUCT_NAMES,
        catalog.get_product_by_id,
        "product read",
    )
    _install(
        monkeypatch,
        page_module,
        _RETAINED_NAMES,
        _EmptyRetainedRead(),
        "retained-results read",
    )
    _install(monkeypatch, page_module, _STEPS_NAMES, _EmptySteps(), "served-playbook")


def _existing_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """The playbook and members admin surfaces, wired the way
    `test_admin_surface_navigation_and_assets.py` wires them."""
    monkeypatch.setattr(playbook_module, "steps", _seeded_steps())
    monkeypatch.setattr(playbook_module, "verify_admin_session", _fake_verify)
    _install(
        monkeypatch,
        playbook_module,
        _PLAYBOOK_MEMBERS_NAMES,
        _PlaybookMembers(),
        "members",
    )
    # The Team list reads the role collection for a member's roles column.
    # `main.py` binds the real Postgres store to this module at import and
    # that outlives the test that imported it, so it is pinned here to a
    # store this test controls. `None` renders the column empty, which is
    # right for a test that asserts nothing about roles.
    monkeypatch.setattr(members_module, "roles", None, raising=False)
    monkeypatch.setattr(members_module, "members", asyncio.run(_build_members_store()))
    monkeypatch.setattr(members_module, "verify_admin_session", _fake_verify)


def _app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_existing_surfaces: bool = False,
    session: str | None = _SESSION_VALUE,
) -> _Surfaces:
    product = _product()
    _install_product_seams(monkeypatch, product)

    app = FastAPI()
    app.include_router(page_module.router)
    if with_existing_surfaces:
        _existing_surfaces(monkeypatch)
        app.include_router(playbook_module.router)
        app.include_router(members_module.router)
    assets = _assets_module()
    if assets is not None:
        monkeypatch.setattr(assets, "verify", _fake_verify)
        app.include_router(assets.router)

    client = TestClient(app)
    if session is not None:
        client.cookies.set(_SESSION_COOKIE, session)
    return _Surfaces(client, product)


def _shortest_get_route(router: Any) -> str:
    candidates: list[str] = []
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, f"{router!r} exposes no parameterless GET route"
    return min(candidates, key=len)


def _index_path() -> str:
    return _shortest_get_route(page_module.router)


def _playbook_path() -> str:
    return _shortest_get_route(playbook_module.router)


def _members_path() -> str:
    return _shortest_get_route(members_module.router)


def _dossier_template() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and path.count("{") == 1:
            candidates.append(path)
    assert len(candidates) == 1, (
        "expected exactly one GET route taking a single path parameter — "
        f"the dossier's address — and found {candidates}"
    )
    return candidates[0]


def _dossier_path(value: Any) -> str:
    # Unwrapped, because `str(ProductId(...))` is the dataclass repr and
    # not the identifier: interpolating it builds a URL naming no product.
    value = getattr(value, "value", value)
    template = _dossier_template()
    opening = template.index("{")
    closing = template.index("}")
    return f"{template[:opening]}{value}{template[closing + 1 :]}"


def _assets_prefix() -> str:
    """The path prefix of the shared asset route `shared` owns."""
    module = _assets_module()
    assert module is not None, f"{_ASSETS_MODULE_NAME} does not exist"
    for route in module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" in path:
            return str(path[: path.index("{")])
    pytest.fail("the shared asset router exposes no parameterised GET route")


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


# ---------------------------------------------------------------------------
# Requirement: Both pages ride the admin session guard and carry the
# shared header
# ---------------------------------------------------------------------------


def test_no_admin_session_means_no_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: No admin session means no surface.

    WHEN either page is requested without an admin session
    THEN the response is identical in shape to requesting a route that
    does not exist.
    """
    surfaces = _app(monkeypatch, session=None)
    nothing = _shape(surfaces.client.get("/a-route-that-was-never-registered"))

    index = surfaces.client.get(_index_path())
    dossier = surfaces.client.get(_dossier_path(surfaces.product.id))

    # SPECIFIED: the absence shape, on both pages, revealing neither the
    # surface nor the reason.
    assert _shape(index) == nothing
    assert _shape(dossier) == nothing
    # DERIVED sanity guard: a verified session does see both surfaces, so
    # the equalities above are not an artifact of two dead routes.
    surfaces.client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    assert surfaces.client.get(_index_path()).status_code == 200
    assert surfaces.client.get(_dossier_path(surfaces.product.id)).status_code == 200


def test_a_revoked_admin_resolves_to_the_same_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A revoked admin resolves to the same absence.

    WHEN either page is requested with an unexpired session whose
    principal's members entry has since lost the admin declaration
    THEN the request is refused with the absence-shaped response.

    The response-shape half only: a revoked principal presents to the
    page as a verification that refuses, and that it *is* refused is
    `admin-session`'s own requirement, verified in
    `tests/unit/access/application/test_admin_session_use_cases.py`.
    That split is the one `test_playbook_admin_page.py` records for the
    same scenario on the other surface.
    """
    surfaces = _app(monkeypatch, session=_REVOKED_SESSION_VALUE)
    nothing = _shape(surfaces.client.get("/a-route-that-was-never-registered"))

    index = surfaces.client.get(_index_path())
    dossier = surfaces.client.get(_dossier_path(surfaces.product.id))

    # SPECIFIED: refused with the absence-shaped response — the same one
    # a request with no session at all gets.
    assert _shape(index) == nothing
    assert _shape(dossier) == nothing


def test_the_index_is_reachable_from_another_admin_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The index is reachable from another admin surface.

    WHEN an existing admin surface is rendered
    THEN its header offers the product index in one action.

    Both existing surfaces are asserted, per `tasks.md` 6.6: a test
    derived from this change alone would not catch one of them failing
    to offer the index. Following the link is part of the assertion, so
    "offers" means a served index rather than a plausible `href`.
    """
    surfaces = _app(monkeypatch, with_existing_surfaces=True)

    for label, path in (
        ("the playbook surface", _playbook_path()),
        ("the membership surface", _members_path()),
    ):
        rendered = surfaces.client.get(path)
        assert rendered.status_code == 200, rendered.text
        page = str(rendered.text)

        # SPECIFIED: the product index in one action.
        assert _offers_in_one_action(page, _index_path()), (
            f"{label} offers no live link to {_index_path()!r}, so the "
            "product index is reachable only by an admin who already knows "
            "the URL"
        )
        # SPECIFIED: and travelling there really serves the index.
        link = _links_to(page, _index_path())[0]
        served = surfaces.client.get(link.attrs["href"])
        assert served.status_code == 200, served.text
        assert SKU in served.text, (
            f"{label}'s product-index link does not lead to the index"
        )

        # SPECIFIED: the index is the surface the header names — the
        # dossier is not a named entry, having no address a header could
        # name (`tasks.md` 6.2).
        dossier_named = _links_to(page, _dossier_path(surfaces.product.id))
        assert dossier_named == [], (
            f"{label} names a per-product dossier in its header, which has "
            "no id-less form and so cannot be a header entry"
        )


def test_the_dossier_carries_the_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The dossier carries the header.

    WHEN the dossier is rendered
    THEN it carries the header, from which the other admin surfaces are
    reachable.
    """
    surfaces = _app(monkeypatch, with_existing_surfaces=True)

    rendered = surfaces.client.get(_dossier_path(surfaces.product.id))
    assert rendered.status_code == 200, rendered.text
    page = str(rendered.text)

    # SPECIFIED: the other admin surfaces are reachable from it.
    for label, path in (
        ("the product index", _index_path()),
        ("the playbook surface", _playbook_path()),
        ("the membership surface", _members_path()),
    ):
        assert _offers_in_one_action(page, path), (
            f"the dossier offers no live link to {label} at {path!r}, so it "
            "carries no header from which the other admin surfaces are "
            "reachable"
        )


def test_presentation_is_shared_not_page_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Presentation is shared, not page-local.

    WHEN either page is rendered
    THEN it loads the shared admin stylesheet and carries no page-local
    style block.

    "The shared admin stylesheet" is read as the route `shared` owns
    (`admin_assets`), not `playbook_admin.py`'s own static route:
    depending on a route belonging to another admin surface is what
    `members-admin`'s presentation requirement forbids (`tasks.md` 6.3).
    The stylesheet is fetched from an app mounting *only* the shared
    asset router, so one served by `launch`'s own route is
    distinguishable from one the shared route serves.
    """
    surfaces = _app(monkeypatch)
    prefix = _assets_prefix()

    index = surfaces.client.get(_index_path())
    dossier = surfaces.client.get(_dossier_path(surfaces.product.id))
    assert index.status_code == 200, index.text
    assert dossier.status_code == 200, dossier.text

    shared_only = _shared_assets_client(monkeypatch)

    for label, response in (("index", index), ("dossier", dossier)):
        page = str(response.text)
        hrefs = _stylesheet_hrefs(page)
        # SPECIFIED: it loads a stylesheet, from the shared route.
        assert hrefs, f"the {label} loads no stylesheet at all"
        shared = [href for href in hrefs if _path_of(href).startswith(prefix)]
        assert shared, (
            f"the {label}'s stylesheets are {hrefs}, none of them served by "
            f"the shared admin asset route at {prefix!r}"
        )
        # SPECIFIED: and that stylesheet really is served there.
        served = shared_only.get(shared[0])
        assert served.status_code == 200, served.text
        assert served.content, f"the {label}'s shared stylesheet is empty"
        # SPECIFIED: and no page-local style block.
        assert _style_blocks(page) == [], (
            f"the {label} carries a page-local style block, so its "
            "presentation is not the shared vocabulary's"
        )


def _shared_assets_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app mounting the shared asset router *alone* — the shape
    `test_admin_surface_navigation_and_assets.py` records."""
    module = _assets_module()
    assert module is not None, f"{_ASSETS_MODULE_NAME} does not exist"
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - How the header *looks*, and that the index identifies itself as the
#   current surface within it. `product-dossier`'s header requirement
#   states reachability and which surface the header names, and states
#   no current-surface obligation of its own; `playbook-admin`'s and
#   `members-admin`'s do, and their own tests assert them. `tasks.md` 9.1
#   carries the by-hand check that the links work in a real browser.
# - The three `vocabulary.css` rules `tasks.md` 6.4a adds. A rule is a
#   computed style; no server response carries one, and asserting the
#   stylesheet's *bytes* would pin an implementation rather than a
#   requirement.
# ---------------------------------------------------------------------------
