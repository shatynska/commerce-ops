"""The product index (`product-dossier`, first requirement).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/product-dossier/spec.md`
— the ADDED requirement *The index lists every product the caller's
scope permits*, all six scenarios, plus the index's half of *Both pages
are read-only* (*Neither page writes*), which is asserted over both
pages in `test_product_dossier_page.py` and over the index here as well
because the index is the page that would grow a row action first.

The dossier's own requirements are in `test_product_dossier_page.py`;
the guard, the header and the shared stylesheet are in
`test_product_surfaces_header_and_presentation.py`. `test-manifest.md` at
the change root records every scenario, every assertion's
classification, and the project questions this file answered by
assumption.

## Level

The page's route over doubles for its collaborators, driven the way a
browser drives it: the test reads the response's markup and follows the
page's own links. That is the smallest unit that can observe "the
catalog held it and the page did not list it", which is what the
restricted-scope scenario requires. It is the harness
`test_playbook_admin_page.py` established for this module's other admin
surface, reproduced rather than imported because this directory carries
no `__init__.py` and this project keeps its test files self-contained.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The module
  `commerce_ops.launch.infrastructure.driving.product_dossier` exposing
  `router`, holding both routes (`design.md` — Decision 1; `tasks.md`
  3.1, 4.1).
- That the index reads `list_products` through `catalog.application` and
  hands it the caller's resolved `AccessScope`, never
  `AccessScope.unrestricted()` (`tasks.md` 3.3).
- That the caller's scope is resolved from the session principal by
  `resolve_scope` (`tasks.md` 3.3).
- The literal markers `product-retired` and `nothing-to-show`, and that
  a synonym is a failing test rather than a stylistic choice
  (`design.md` — Decision 11; `tasks.md` 5.2a).
- That rows are ordered by SKU ascending *within each group*, and that
  retired products are set apart and never interleaved (the requirement,
  whose qualification is load-bearing: a single ascending sort across
  the whole page and the set-apart rule cannot both hold).
- Read-only asserted negatively — no form, and no element carrying
  `row-action` (`tasks.md` 8.4b).

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a **class token**, on the
  element or on something inside it. `playbook-admin`'s served
  requirement fixes `class="row-action"`, and this delta says only
  "carries". Correction point: `_carries`.
- How a row is located: the smallest element naming the product's SKU,
  widened to its enclosing `<tr>`/`<li>` where there is one. Correction
  point: `_row_of`.
- The page module's seams — `verify_admin_session`, `resolve_scope`,
  `list_products`, `get_product_by_id`, the retained-results read and
  the served-playbook source — each installed by name through
  `_install`, which fails loudly naming the candidates rather than
  defaulting. Correction points: the `_*_NAMES` tuples.
- The session cookie's name, `admin_session`, taken from
  `test_playbook_admin_page.py`. Correction point: `_SESSION_COOKIE`.
- That the lifecycle stage is rendered naming its stage
  (`_STAGE_WORDS`). The requirement fixes that the stage is carried, not
  the wording.

## Expected first-run state

`commerce_ops.launch.infrastructure.driving.product_dossier` does not
exist, so every test here is expected to fail at **import** — the
absent-target state. Per `ai-toolkit:testing` that establishes absence
only: none of the assertions below has been exercised.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27); the 96
skips are the whole integration tier, which finds no database here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as page_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching, Retired
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import MARKETPLACE, PRINCIPAL
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import Text as _Text
from tests.support.html import ancestors as _ancestors
from tests.support.html import classes as _classes
from tests.support.html import document_order as _document_order
from tests.support.html import element_disabled as _element_disabled
from tests.support.html import element_hidden as _element_hidden
from tests.support.html import elements as _elements
from tests.support.html import tree as _tree

T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_MOVED: Final = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
CONFIRMER: Final = "Helen"

# The literal markers the delta fixes (`design.md` — Decision 11).
PRODUCT_RETIRED: Final = "product-retired"
NOTHING_TO_SHOW: Final = "nothing-to-show"
ROW_ACTION: Final = "row-action"

#: DERIVED: how a lifecycle stage is expected to name itself in a row.
#: The requirement fixes that the stage is carried, not its wording.
_STAGE_WORDS: Final = {
    "development": ("development",),
    "launching": ("launching",),
    "retired": ("retired",),
}


# ---------------------------------------------------------------------------
# An HTML tree, in document order
# ---------------------------------------------------------------------------


def _all_text(node: _Node) -> str:
    """**Kept local**: this is not `tests.support.html.all_text`, which
    lowercases its answer. This one preserves case, and the difference is
    live -- driven side by side with the shared function over this file's
    own pages, they disagreed on **5,861 of 6,134 calls**
    (`share-the-ordered-html-harness`).
    """
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_all_text(child))
    return " ".join(part for part in found if part)


def _carries(node: _Node, marker: str) -> bool:
    """Whether an element carries a vocabulary marker.

    INVENTED: read as a class token on the element or on something
    inside it — the reading `playbook-admin`'s `row-action` already
    established, widened to descendants because this delta says the row
    "carries" the marker without saying on which of the row's elements.

    **Kept local**: that widening is exactly what separates this from
    `tests.support.html.carries`, which reads the class token on the element
    alone.

    **The proof agreed here, and that is not the licence.** Over this file's
    4 calls the two answered identically, because none of the 4 asked about
    an element whose *descendant* carries the marker. Agreement over the
    inputs a tier happens to supply is a property of the sample, not of the
    function. Its callees `_classes` and `_elements` migrated to the shared
    module in the same commit; both were compared against their local
    originals and answer the same, so this reading did not move with them.
    """
    if marker in _classes(node):
        return True
    return any(marker in _classes(child) for child in _elements(node))


def _page_carries(html: str, marker: str) -> bool:
    root = _tree(html)
    return any(marker in _classes(element) for element in _elements(root))


def _inert(node: _Node) -> bool:
    if _element_disabled(node) or _element_hidden(node):
        return True
    return any(
        _element_disabled(ancestor) or _element_hidden(ancestor)
        for ancestor in _ancestors(node)
    )


def _row_of(root: _Node, needle: str) -> _Node:
    """The row naming `needle`.

    INVENTED: the smallest element whose text names it, widened to the
    enclosing `<tr>` or `<li>` where the page uses one. Correction point
    for a differently shaped row.
    """
    naming = [element for element in _elements(root) if needle in _all_text(element)]
    if not naming:
        pytest.fail(f"nothing on the page names {needle!r}")
    smallest = min(naming, key=lambda element: len(_all_text(element)))
    for ancestor in (smallest, *_ancestors(smallest)):
        if ancestor.tag in ("tr", "li"):
            return ancestor
    return smallest


def _rows_in_order(html: str, needles: tuple[str, ...]) -> list[tuple[str, _Node]]:
    root = _tree(html)
    rows = [(needle, _row_of(root, needle)) for needle in needles]
    return sorted(rows, key=lambda pair: _document_order(pair[1]))


def _links(node: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(node)
        if element.tag == "a" and element.attrs.get("href")
    ]


def _forms(html: str) -> list[_Node]:
    return [element for element in _elements(_tree(html)) if element.tag == "form"]


def _submitting_controls(html: str) -> list[_Node]:
    """Anything that would send a request other than a plain link — the
    shapes a write would arrive through on an htmx page."""
    found: list[_Node] = []
    for element in _elements(_tree(html)):
        if element.tag == "form" or any(
            verb in element.attrs for verb in _HX_VERBS[1:]
        ):
            found.append(element)
    return found


# ---------------------------------------------------------------------------
# The page module's seams
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


def _install(
    monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...], value: Any, what: str
) -> str:
    for name in names:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, value)
            return name
    pytest.fail(
        f"the product surfaces expose no {what} seam under any of {names} — "
        "correct this file's probe to the implemented name"
    )


_fake_verify = fake_verify(PRINCIPAL)


def _scope_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AccessScope:
    for value in (*args, *kwargs.values()):
        if isinstance(value, AccessScope):
            return value
    pytest.fail(
        "the page called a catalog read without an access scope, so the "
        "caller's scope never reaches it (`tasks.md` 3.3)"
    )


def _product_id_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    for value in (*args, *kwargs.values()):
        if isinstance(value, ProductId):
            return value
    for value in (*args, *kwargs.values()):
        if isinstance(value, str) and value not in ("", PRINCIPAL):
            return value
    return None


class _FakeScopeResolution:
    """Stands in for `resolve_scope`, answering the scope the test chose
    for this caller."""

    def __init__(self, scope: AccessScope) -> None:
        self.scope = scope
        self.calls: list[tuple[Any, ...]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> AccessScope:
        self.calls.append((args, kwargs))
        return self.scope


class _FakeCatalog:
    """Stands in for `catalog.application`'s two reads, applying the
    scope it is handed exactly as the real ones do — so a page passing
    `AccessScope.unrestricted()` instead of the caller's scope is
    visible here rather than invisible."""

    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)
        self.list_scopes: list[AccessScope] = []

    async def list_products(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        scope = _scope_in(args, kwargs)
        self.list_scopes.append(scope)
        return tuple(product for product in self.products if scope.permits(product.id))

    async def get_product_by_id(self, *args: Any, **kwargs: Any) -> Product | None:
        scope = _scope_in(args, kwargs)
        wanted = _product_id_in(args, kwargs)
        for product in self.products:
            if str(product.id) == str(wanted) and scope.permits(product.id):
                return product
        return None


class _FakeRetainedRead:
    """Stands in for the retained-results read. Answers nothing here:
    the index renders no results, and the dossier reached from a row is
    exercised for its identity half only."""

    def __init__(self) -> None:
        self.scopes: list[AccessScope] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        for value in (*args, *kwargs.values()):
            if isinstance(value, AccessScope):
                self.scopes.append(value)
        return ()


class _FakeSteps:
    """The served-playbook source. Answers no step at all, which is
    enough for the index and leaves the dossier's entries — of which
    there are none here — to `test_product_dossier_page.py`."""

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (), 1

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return ()


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def _product(sku: str, name: str) -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )


def _retired(sku: str, name: str) -> Product:
    product = _product(sku, name)
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_MOVED)
    return product


def _launching(sku: str, name: str) -> Product:
    product = _product(sku, name)
    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_MOVED)
    return product


#: Two active products and two retired ones, with a retired SKU
#: (`BBB-003`) sorting *between* the two active SKUs — so a single
#: ascending sort across the whole page and the set-apart rule cannot
#: both hold, which is what the requirement's qualification is about.
ALPHA_SKU: Final = "AAA-001"
MID_SKU: Final = "MMM-002"
RETIRED_EARLY_SKU: Final = "BBB-003"
RETIRED_LATE_SKU: Final = "ZZZ-004"

ALPHA_NAME: Final = "Alpha Widget"
MID_NAME: Final = "Mid Widget"
RETIRED_EARLY_NAME: Final = "Discontinued Widget"
RETIRED_LATE_NAME: Final = "Last Widget"


def _catalog() -> _FakeCatalog:
    return _FakeCatalog(
        _launching(MID_SKU, MID_NAME),
        _retired(RETIRED_LATE_SKU, RETIRED_LATE_NAME),
        _product(ALPHA_SKU, ALPHA_NAME),
        _retired(RETIRED_EARLY_SKU, RETIRED_EARLY_NAME),
    )


ALL_SKUS: Final = (ALPHA_SKU, MID_SKU, RETIRED_EARLY_SKU, RETIRED_LATE_SKU)
ACTIVE_SKUS: Final = (ALPHA_SKU, MID_SKU)
RETIRED_SKUS: Final = (RETIRED_EARLY_SKU, RETIRED_LATE_SKU)


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


@dataclass
class _Surface:
    client: TestClient
    catalog: _FakeCatalog
    scope: _FakeScopeResolution
    retained: _FakeRetainedRead


def _app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    catalog: _FakeCatalog | None = None,
    scope: AccessScope | None = None,
    signed_in: bool = True,
) -> _Surface:
    reads = _catalog() if catalog is None else catalog
    resolution = _FakeScopeResolution(
        AccessScope.unrestricted() if scope is None else scope
    )
    retained = _FakeRetainedRead()

    _install(monkeypatch, _VERIFY_NAMES, _fake_verify, "admin-session")
    _install(monkeypatch, _SCOPE_NAMES, resolution, "scope-resolution")
    _install(monkeypatch, _LIST_NAMES, reads.list_products, "product listing")
    _install(monkeypatch, _GET_PRODUCT_NAMES, reads.get_product_by_id, "product read")
    _install(monkeypatch, _RETAINED_NAMES, retained, "retained-results read")
    _install(monkeypatch, _STEPS_NAMES, _FakeSteps(), "served-playbook")

    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    if signed_in:
        client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, reads, resolution, retained)


def _index_path() -> str:
    """The index: the shortest parameterless GET route the router
    exposes. The dossier carries a path parameter, so the two cannot be
    confused."""
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the product router exposes no parameterless GET route"
    return min(candidates, key=len)


def _get_index(surface: _Surface) -> str:
    response = surface.client.get(_index_path())
    assert response.status_code == 200, response.text
    return str(response.text)


def _permitting(*product_ids: ProductId) -> AccessScope:
    return AccessScope.permitting(product_ids)


def _id_of(catalog: _FakeCatalog, sku: str) -> ProductId:
    for product in catalog.products:
        if getattr(product.sku, "value", product.sku) == sku:
            return product.id
    pytest.fail(f"no fixture product carries SKU {sku!r}")


# ---------------------------------------------------------------------------
# Requirement: The index lists every product the caller's scope permits
# ---------------------------------------------------------------------------


def test_every_permitted_product_is_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Every permitted product is listed.

    WHEN an admin opens the product index under a scope permitting every
    registered product
    THEN every registered product appears with its SKU, its name and its
    current lifecycle stage.
    """
    surface = _app(monkeypatch, scope=AccessScope.unrestricted())

    listed = _get_index(surface)
    root = _tree(listed)

    for sku, name, stage in (
        (ALPHA_SKU, ALPHA_NAME, "development"),
        (MID_SKU, MID_NAME, "launching"),
        (RETIRED_EARLY_SKU, RETIRED_EARLY_NAME, "retired"),
        (RETIRED_LATE_SKU, RETIRED_LATE_NAME, "retired"),
    ):
        # SPECIFIED: its SKU and its name.
        assert sku in listed, f"{sku} is not listed"
        row = _row_of(root, sku)
        row_text = _all_text(row).lower()
        assert name.lower() in row_text, f"{sku}'s row does not carry its name"
        # SPECIFIED that the row carries the current lifecycle stage;
        # DERIVED that the stage names itself with these words.
        assert any(word in row_text for word in _STAGE_WORDS[stage]), (
            f"{sku}'s row carries no lifecycle stage naming {stage!r} "
            f"(row: {row_text[:200]!r}) — correct `_STAGE_WORDS` to the "
            "implemented rendering"
        )


def test_a_restricted_scope_lists_only_its_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A restricted scope lists only its products.

    WHEN the index is rendered under a scope permitting some registered
    products' identifiers but not others
    THEN exactly the permitted products appear, and the others are
    absent.
    """
    catalog = _catalog()
    permitted = (_id_of(catalog, ALPHA_SKU), _id_of(catalog, RETIRED_EARLY_SKU))
    surface = _app(monkeypatch, catalog=catalog, scope=_permitting(*permitted))

    listed = _get_index(surface)

    # SPECIFIED: exactly the permitted products appear...
    assert ALPHA_SKU in listed
    assert RETIRED_EARLY_SKU in listed
    # ...and the others are absent.
    assert MID_SKU not in listed
    assert RETIRED_LATE_SKU not in listed
    assert MID_NAME not in listed
    # SPECIFIED by `tasks.md` 3.3: the scope the page handed the read is
    # the caller's resolved one, not an unrestricted stand-in. Without
    # this, a page passing `AccessScope.unrestricted()` would be caught
    # only by the double above happening to be strict.
    assert surface.catalog.list_scopes, "the index never listed products at all"
    assert all(
        not scope.permits(_id_of(catalog, MID_SKU))
        for scope in surface.catalog.list_scopes
    )


def test_an_empty_index_is_a_page_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An empty index is a page, not a failure.

    WHEN the index is rendered under a scope permitting no product
    identifier
    THEN the page renders with no rows and carries `nothing-to-show`.

    The same page is asserted for a catalog holding no product at all,
    which the requirement statement names alongside the empty scope and
    which no scenario of its own covers.
    """
    surface = _app(monkeypatch, scope=_permitting())

    response = surface.client.get(_index_path())

    # SPECIFIED: a page, not a failure.
    assert response.status_code == 200, response.text
    listed = str(response.text)
    # SPECIFIED: with no rows.
    for sku in ALL_SKUS:
        assert sku not in listed, f"{sku} is listed under a scope permitting nothing"
    # SPECIFIED: and carries `nothing-to-show`.
    assert _page_carries(listed, NOTHING_TO_SHOW), (
        f"the empty index carries no {NOTHING_TO_SHOW!r} marker, so a "
        "blank region is indistinguishable from a page that failed to load"
    )

    # SPECIFIED by the requirement statement, which has no scenario of
    # its own: a catalog holding no products renders the same way.
    empty = _app(monkeypatch, catalog=_FakeCatalog())
    rendered = _get_index(empty)
    assert _page_carries(rendered, NOTHING_TO_SHOW)


def test_retired_products_are_set_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Retired products are set apart.

    WHEN the index is rendered and the catalog holds retired products
    alongside others
    THEN every retired product's row carries `product-retired`, no other
    row carries it, and every row carrying it follows every row that
    does not.
    """
    surface = _app(monkeypatch)

    listed = _get_index(surface)
    rows = _rows_in_order(listed, ALL_SKUS)
    marked = {sku for sku, row in rows if _carries(row, PRODUCT_RETIRED)}

    # SPECIFIED: every retired product's row carries it...
    assert marked >= set(RETIRED_SKUS), (
        f"these retired rows carry no {PRODUCT_RETIRED!r}: "
        f"{sorted(set(RETIRED_SKUS) - marked)}"
    )
    # ...and no other row does.
    assert marked == set(RETIRED_SKUS), (
        f"these rows carry {PRODUCT_RETIRED!r} and are not retired: "
        f"{sorted(marked - set(RETIRED_SKUS))}"
    )
    # SPECIFIED: every row carrying it follows every row that does not.
    positions = [sku in marked for sku, _ in rows]
    assert positions == sorted(positions), (
        "retired rows are interleaved with the rest — the rendered order "
        f"is {[sku for sku, _ in rows]}"
    )


def test_setting_apart_outranks_the_sku_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Setting apart outranks the SKU sort.

    WHEN the index is rendered and a retired product's SKU sorts before
    an active product's
    THEN the active product's row still precedes the retired one's
    AND within each group the rows are ordered by SKU ascending.
    """
    surface = _app(monkeypatch)

    listed = _get_index(surface)
    order = [sku for sku, _ in _rows_in_order(listed, ALL_SKUS)]

    # DERIVED precondition, asserted so the scenario is really reached:
    # the retired SKU does sort before an active one.
    assert RETIRED_EARLY_SKU < MID_SKU

    # SPECIFIED: the active product's row still precedes the retired
    # one's.
    assert order.index(MID_SKU) < order.index(RETIRED_EARLY_SKU)
    # SPECIFIED: and within each group, SKU ascending.
    assert [sku for sku in order if sku in ACTIVE_SKUS] == sorted(ACTIVE_SKUS)
    assert [sku for sku in order if sku in RETIRED_SKUS] == sorted(RETIRED_SKUS)


def test_a_row_reaches_the_dossier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A row reaches the dossier.

    WHEN a row on the index is followed
    THEN that product's dossier is opened.

    The link is discovered from the row rather than composed from a URL
    this file invented, and it is followed for real — so "reaches"
    means a served page about that product, not a plausible `href`.
    """
    surface = _app(monkeypatch)

    listed = _get_index(surface)
    row = _row_of(_tree(listed), MID_SKU)
    offered = [link for link in _links(row) if not _inert(link)]

    # SPECIFIED: in one action — a live link, needing no scripting.
    assert offered, (
        f"{MID_SKU}'s row offers no live link, so its dossier is reachable "
        "only by an admin who already knows the URL"
    )

    opened = surface.client.get(offered[0].attrs["href"])
    # SPECIFIED: that product's dossier is opened.
    assert opened.status_code == 200, opened.text
    assert MID_SKU in opened.text
    assert MID_NAME in opened.text
    # DERIVED guard: it is *that* product's page, not the index again.
    assert ALPHA_SKU not in opened.text


# ---------------------------------------------------------------------------
# Requirement: Both pages are read-only — the index's half
# ---------------------------------------------------------------------------


def test_the_index_offers_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Neither page writes — asserted here over the index, and
    over both pages in `test_product_dossier_page.py`.

    WHEN either page is rendered
    THEN its response contains no form and no element carrying
    `row-action`.

    Asserted negatively, per `tasks.md` 8.4b: on a page with no action
    controls, the absence of that marker is the whole claim.
    """
    surface = _app(monkeypatch)

    listed = _get_index(surface)

    # SPECIFIED: no form.
    assert _forms(listed) == [], "the index renders a form, so it offers a write"
    # SPECIFIED: no element carrying `row-action`.
    assert not _page_carries(listed, ROW_ACTION), (
        f"the index carries {ROW_ACTION!r}, the marker every action control "
        "on an admin page must carry — so it offers an action"
    )
    # DERIVED, from the same requirement's statement that neither page
    # offers "any action that changes stored state": nothing on the page
    # issues a non-GET request either.
    assert _submitting_controls(listed) == []


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - How the retired group is *presented* — a heading, a second table, a
#   rule between the two. The requirement fixes the marker and the
#   ordering, and says outright that "presented distinctly" is not
#   assertable; `tasks.md` 9.1 carries the by-hand check.
# - Pagination, filtering and search. `design.md` — Non-Goals excludes
#   all three, so there is nothing to assert and no scenario to cover.
# ---------------------------------------------------------------------------
