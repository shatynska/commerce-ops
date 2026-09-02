"""The product dossier's breadcrumb trail back to the product index
(`product-dossier`, `add-admin-breadcrumb-navigation`).

Derived strictly from the delta spec
`openspec/changes/add-admin-breadcrumb-navigation/specs/product-dossier/spec.md`
— its one ADDED requirement and its one scenario:

- ADDED *The dossier offers the way back to the product index*
  - *The index is reachable from a product's dossier*

The requirement's own prose states the destination's shape beyond the
literal scenario: "Following the index link SHALL reach the index in one
action, without scripting, **as the index renders with no narrowing
active**." That is read here, as in the sibling launch-detail file, as
the offered link carrying no query string at all.

## Level

The product router alone, over doubles for the catalog, the served
playbook and the retained-results read — the harness
`test_product_dossier_page.py` established for this module's other admin
surface, reproduced here (this project shares no test-helper module
between test files).

## Expected first-run state

The dossier route already exists (`product-dossier`'s prior change), and
today renders a bare `<h1>{{ it.name }}</h1>` with no `page-head` and no
way back to the index at all (`design.md`'s Context: "The dossier carries
no way back today ... nothing else on the page offers the index"). So
this test is expected to fail against a live route: no breadcrumb-shaped
offer of the index exists yet, confirmed by hand against the dossier as
it renders today.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at this worktree — 1472 passed, 0 failed, on
2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the delta: that the dossier's breadcrumb offers the product
index in one action, without scripting, reaching it unnarrowed; and that
the trail's last segment names the product and is not a link.

INVENTED, each with its correction point named in the code:

- How the breadcrumb trail is told apart from the shared admin header,
  which also links to the product index from every admin page: the trail
  is read as an element rendered *before* the page's `<h1>` (and not one
  of its ancestors) that offers the index as a plain, unnarrowed link,
  together with an un-linked element — also before the `<h1>` — naming
  the product. The "immediately above its title" placement is the
  requirement's own further clause, and doubles as what discriminates a
  genuine breadcrumb from an index link the header already carries lower
  on the page. Correction points: `_before_title`, `_unlinked_mentions`.
- Every module seam, the served-playbook shape and the catalog/members
  doubles — taken unchanged from `test_product_dossier_page.py`.

Correcting a locator is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what the test
asserts: that the index is reachable, unnarrowed, from a plain trail
above the title, and that the trail's last segment names the product and
is not a link.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as page_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import MarketplaceId, Sku

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

SKU: Final = "BCB-2027-01"
NAME: Final = "Bamboo Cutting Board"

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
_SCRIPTING_ATTRIBUTES: Final = (*_HX_VERBS, "onclick", "onmousedown", "onkeydown")
_HIDDEN_CLASSES: Final = ("hidden", "is-hidden", "d-none", "sr-only", "visually-hidden")
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


def _product(sku: str = SKU, name: str = NAME) -> Product:
    return Product.register(
        sku=Sku(sku), marketplace_id=MARKETPLACE, name=name, registered_at=T_REGISTERED
    )


# ---------------------------------------------------------------------------
# Doubles — reproduced from test_product_dossier_page.py
# ---------------------------------------------------------------------------


class _FakeCatalog:
    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)

    async def list_products(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        scope = _scope_in(args, kwargs)
        return tuple(product for product in self.products if scope.permits(product.id))

    async def get_product_by_id(self, *args: Any, **kwargs: Any) -> Product | None:
        scope = _scope_in(args, kwargs)
        wanted = _product_id_in(args, kwargs)
        for product in self.products:
            if str(product.id) == str(wanted) and scope.permits(product.id):
                return product
        return None


def _scope_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AccessScope:
    for value in (*args, *kwargs.values()):
        if isinstance(value, AccessScope):
            return value
    pytest.fail("the page made a scoped read without an access scope")


def _product_id_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    from commerce_ops.shared.domain.identity import ProductId

    for value in (*args, *kwargs.values()):
        if isinstance(value, ProductId):
            return value
    for value in (*args, *kwargs.values()):
        if isinstance(value, str) and value not in ("", PRINCIPAL):
            return value
    return None


class _FakeScopeResolution:
    def __init__(self, scope: AccessScope) -> None:
        self.scope = scope

    async def __call__(self, *args: Any, **kwargs: Any) -> AccessScope:
        return self.scope


class _FakeRetainedRead:
    def __init__(self, *records: Any) -> None:
        self.records = tuple(records)

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return self.records


class _FakeSteps:
    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (), 1

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return ()


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


def _install(
    monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...], value: Any, what: str
) -> str:
    for name in names:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, value)
            return name
    pytest.fail(f"the product surfaces expose no {what} seam under any of {names}")


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


@dataclass
class _Surface:
    client: TestClient
    product: Product


def _app(
    monkeypatch: pytest.MonkeyPatch, *, product: Product | None = None
) -> _Surface:
    subject = _product() if product is None else product
    catalog = _FakeCatalog(subject)
    resolution = _FakeScopeResolution(AccessScope.unrestricted())

    _install(monkeypatch, _VERIFY_NAMES, _fake_verify, "admin-session")
    _install(monkeypatch, _SCOPE_NAMES, resolution, "scope-resolution")
    _install(monkeypatch, _LIST_NAMES, catalog.list_products, "product listing")
    _install(monkeypatch, _GET_PRODUCT_NAMES, catalog.get_product_by_id, "product read")
    _install(monkeypatch, _RETAINED_NAMES, _FakeRetainedRead(), "retained-results read")
    _install(monkeypatch, _STEPS_NAMES, _FakeSteps(), "served-playbook")

    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, subject)


def _index_path() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the product router exposes no parameterless GET route"
    return min(candidates, key=len)


def _dossier_template() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and path.count("{") == 1:
            candidates.append(path)
    assert len(candidates) == 1, (
        f"expected exactly one dossier route, found {candidates}"
    )
    return candidates[0]


def _dossier_path(value: Any) -> str:
    value = getattr(value, "value", value)
    template = _dossier_template()
    opening = template.index("{")
    closing = template.index("}")
    return f"{template[:opening]}{value}{template[closing + 1 :]}"


def _get_dossier(surface: _Surface) -> str:
    response = surface.client.get(_dossier_path(surface.product.id))
    assert response.status_code == 200, response.text
    return str(response.text)


# ---------------------------------------------------------------------------
# An HTML tree, in document order
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


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _own_text(node: _Node) -> str:
    return " ".join(
        child.text for child in node.children if isinstance(child, _Text)
    ).lower()


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


def _links_to(root: _Node, path: str) -> list[_Node]:
    found: list[_Node] = []
    for element in _elements(root):
        if element.tag != "a":
            continue
        href = element.attrs.get("href")
        if not href:
            continue
        split = urlsplit(href)
        if split.path == path and not split.query:
            found.append(element)
    return found


def _live(node: _Node) -> bool:
    return (
        not _inherited(node, _element_disabled)
        and not _inherited(node, _element_hidden)
        and not any(attribute in node.attrs for attribute in _SCRIPTING_ATTRIBUTES)
    )


def _first(root: _Node, tag: str) -> _Node:
    for element in _elements(root):
        if element.tag == tag:
            return element
    pytest.fail(f"the page renders no {tag!r} element at all")


def _before_title(node: _Node, title: _Node) -> bool:
    if node is title:
        return False
    if any(ancestor is title for ancestor in (node, *_ancestors(node))):
        return False
    if any(ancestor is node for ancestor in _ancestors(title)):
        return False
    return node.order < title.order


def _in_shared_header(node: _Node) -> bool:
    """Whether `node` sits within the shared admin header — the
    site-wide chrome every admin page renders, which itself links to
    other top-level surfaces (the product index among them) from a fixed
    position above the page's own content. Excluded so the header's own
    link is never mistaken for this page's breadcrumb — the false
    positive confirmed by hand: the header's "Products" link to
    `/admin/products` already renders above every page's `<h1>`, which
    would otherwise satisfy an "offered above the title" check without
    any breadcrumb existing at all."""
    for candidate in (node, *_ancestors(node)):
        if candidate.tag == "header":
            return True
        if "admin-header" in _classes(candidate):
            return True
        if "admin-surface" in _classes(candidate):
            return True
        if "admin surfaces" in candidate.attrs.get("aria-label", "").lower():
            return True
    return False


def _current_segment_is(title: _Node, label: str) -> bool:
    """Whether the page's own `<h1>` — the breadcrumb's current, un-linked,
    last segment, since the two are now the same element
    (`.breadcrumb-current` IS the `<h1>`; a page carrying a breadcrumb
    renders no separate title of its own) — names `label` as its own text
    and is not itself, nor via an ancestor, a link.
    """
    return label.lower() in _own_text(title) and not _inherited(
        title, lambda n: n.tag == "a"
    )


# ===========================================================================
# ADDED requirement: The dossier offers the way back to the product index
# ===========================================================================


def test_the_index_is_reachable_from_a_products_dossier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The index is reachable from a product's dossier.

    WHEN a product's dossier is rendered
    THEN its breadcrumb trail offers the product index in one action,
    without scripting
    AND the trail's last segment names the product and is not a link.
    """
    surface = _app(monkeypatch)

    root = _tree(_get_dossier(surface))
    title = _first(root, "h1")
    index_path = _index_path()

    offers = [
        link
        for link in _links_to(root, index_path)
        if _live(link) and _before_title(link, title) and not _in_shared_header(link)
    ]
    # SPECIFIED: offered above the title, unnarrowed (no query — `_links_to`
    # already selects for that), in one action, without scripting.
    assert offers, (
        f"the dossier offers no plain, unnarrowed link to {index_path!r} "
        f"above its <h1> — anchors present: "
        f"{sorted({e.attrs.get('href', '') for e in _elements(root) if e.tag == 'a'})}"
    )

    # SPECIFIED: the trail's last segment names the product and is not a
    # link — the page's own `<h1>` *is* that segment now.
    assert _current_segment_is(title, NAME), (
        f"the dossier's <h1> does not name {NAME!r} as its own, un-linked "
        f"text ({_own_text(title)!r}) — correct `_current_segment_is` if "
        "the current segment is worded some other way"
    )
