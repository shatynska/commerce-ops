"""The dossier's region for what automated steps established about the
product (`product-dossier`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/product-dossier/spec.md`

Covers all four ADDED requirements and all twelve of their scenarios:

*The dossier renders what the product's automated steps have established
about it*
- The region is present and marked
- A recorded sub-category is rendered
- The region renders for a product with nothing established

*An unrecorded sub-category is stated, not blank*
- An absent sub-category carries the page's absence marker

*The dossier renders hazard categories in three states, and never renders
a clear screening as an absence*
- A never-screened product says so
- A screened-clear product is not rendered as unscreened
- A flagged product presents its categories
- Categories are not presented in a collection's notation
- The three states render three ways
- The field claims no ratification

*The region established by automation offers no action and carries no
page-local styling*
- The region is read-only
- The new state's presentation is shared, not page-local

`tasks.md` 1.22-1.26. See `test-manifest.md` at the change root for the
full accounting.

## Level

The dossier route over doubles for its collaborators — the level
`test_product_dossier_page.py` established, and the smallest that can
observe any of these, since every scenario is stated over the rendered
page. The harness is duplicated from that file rather than imported: this
project shares no test-helper module, and `tests/**/test_*.py` is the
only path a test may be written to.

## How the assertions are made falsifiable

- **By marker and pairwise, never by prose match** (`tasks.md` 1.24). The
  three hazard states are asserted through the literal markers the delta
  fixes, and additionally against one another, so a page rendering two of
  them identically fails even where each carries the right class.
- **The middle row is asserted against `not-recorded`, negatively.** "A
  screened-clear product is not rendered as unscreened" is the assertion
  the whole surface change exists for, and a positive-only test of
  `screened-clear` would pass a page carrying both.
- **The region is located and every within-region assertion is scoped to
  it.** A page-wide search for "accepted" would match the retained-results
  record, which legitimately carries decisions.

## What is fixed, and what is INVENTED

Fixed by the delta: the three literal markers `established-by-automation`,
`not-recorded` and `screened-clear`; that the region is distinct from
`retained-for-decision`; that it renders for a product with nothing
established, stating each field's absence rather than being omitted; that
a non-empty set presents every category with none of a collection's
notation and carries neither marker; that no state is rendered blank;
that the field is presented as what a screening established and never as
confirmed, approved or accepted; and that the region contains no form and
no element carrying `row-action`, taking its presentation from the shared
stylesheet.

Deliberately **not** fixed by the delta, and therefore not asserted: how
the categories are separated from one another, and the wording behind
`screened-clear` — `design.md`'s Open Questions settles the latter
against the running page, and records that it "changes no test derived
from" the specified parts.

INVENTED, each recorded in `test-manifest.md`:

- That "carries the marker `X`" is read as a class token on the element or
  on something inside it — the reading
  `test_product_dossier_page.py` records. Correction point: `_carries`.
- How the region is located: the element carrying
  `established-by-automation`. Fixed by the delta, unlike the *fields*
  inside it, which are located by the label text near them
  (`_labels_near`) — the same probe the ASIN and stage-confirmer absence
  scenarios already use.
- The page module's seams, installed by name through `_install`, and the
  retained-result record shape — inherited unchanged from
  `test_product_dossier_page.py`'s own documented assumptions.

## Expected first-run state

`Product.record_hazard_categories` does not exist (`tasks.md` 3.1) and the
dossier renders no region marked `established-by-automation`
(`tasks.md` 7.1-7.3), so every test here is expected to fail on an absent
target — `AttributeError` in the fixtures that record a hazard set, and a
missing region for the rest. Per `ai-toolkit:testing` that establishes
absence only.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from itertools import pairwise
from typing import Any, Final, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.catalog.application import record_asin
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as page_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import Asin, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import MARKETPLACE, PRINCIPAL
from tests.support.steps import step as _build_step

T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_MOVED: Final = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
CONFIRMER: Final = "Helen Shatynska"

SKU: Final = "BCB-2027-01"
NAME: Final = "Bamboo Cutting Board"
ASIN: Final = "B0EXAMPLE1"

# The literal markers the delta fixes.
ESTABLISHED_BY_AUTOMATION: Final = "established-by-automation"
RETAINED_FOR_DECISION: Final = "retained-for-decision"
NOT_RECORDED: Final = "not-recorded"
SCREENED_CLEAR: Final = "screened-clear"
ROW_ACTION: Final = "row-action"

SUB_CATEGORY: Final = "Home and Kitchen then Kitchen and Dining then Cutting Boards"

#: Three members, phrases rather than single words, so a rendering that
#: ran them together is legible as a failure rather than as an accident of
#: short tokens.
HAZARD_CATEGORIES: Final = ("supplements", "medical devices", "CO detectors")

#: The delta's own list: "no brackets, no quotation marks around each
#: category, no type name".
_COLLECTION_NOTATION: Final = ("[", "]", "{", "}", "'", '"')
_COLLECTION_TYPE_NAMES: Final = ("list", "tuple", "set", "frozenset", "dict")

#: The vocabulary of a *decision*, which `product-catalog` forbids this
#: field being presented in: "a page describing it in the vocabulary of a
#: decision would assert on the product's own record something no member
#: did".
_RATIFICATION_WORDS: Final = ("confirmed", "approved", "accepted")

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

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")

SERVED_STEP: Final = "listing.sub-category"
SERVED_STEP_NAME: Final = "Choose the sub-category node"
HANDLER: Final = "listing.subcategory_advisor"


# ---------------------------------------------------------------------------
# An HTML tree — inherited from test_product_dossier_page.py
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


def _all_text(node: _Node) -> str:
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_all_text(child))
    return " ".join(part for part in found if part)


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    if marker in _classes(node):
        return True
    return any(marker in _classes(child) for child in _elements(node))


def _marked(page: str, marker: str) -> list[_Node]:
    return [
        element for element in _elements(_tree(page)) if marker in _classes(element)
    ]


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _region(page: str) -> _Node:
    """The region the delta marks `established-by-automation`.

    Fails loudly rather than returning the document, which would make
    every within-region assertion below vacuous.
    """
    found = _marked(page, ESTABLISHED_BY_AUTOMATION)
    if not found:
        carried = sorted(
            {name for element in _elements(_tree(page)) for name in _classes(element)}
        )
        pytest.fail(
            f"the dossier carries no region marked "
            f"{ESTABLISHED_BY_AUTOMATION!r}; the classes it does carry are "
            f"{carried}"
        )
    assert len(found) == 1, (
        f"the dossier carries {len(found)} elements marked "
        f"{ESTABLISHED_BY_AUTOMATION!r}; the delta names one region"
    )
    return found[0]


def _field_in_region(page: str, label: str) -> _Node:
    """The smallest element inside the region whose text names `label`.

    INVENTED locator, on the same reasoning as the sibling file's
    `_labels_near`: the delta fixes the region's marker and each field's
    own markers, and fixes no element structure. Correction point for a
    differently shaped field.
    """
    region = _region(page)
    naming = [
        element
        for element in _elements(region)
        if label.lower() in _all_text(element).lower()
    ]
    if not naming:
        pytest.fail(
            f"nothing inside the region marked {ESTABLISHED_BY_AUTOMATION!r} "
            f"names {label!r}; the region reads as "
            f"{_all_text(region)[:300]!r}"
        )
    return min(naming, key=lambda element: len(_all_text(element)))


def _is_control(node: _Node) -> bool:
    """An affordance a member clicks — the reading
    `test_product_dossier_page.py` records."""
    if node.attrs.get("role", "").lower() == "button":
        return True
    if node.tag in ("button", "form"):
        return True
    if node.tag == "input":
        return (node.attrs.get("type") or "text").lower() in ("submit", "image")
    return any(verb in node.attrs for verb in _HX_VERBS)


# ---------------------------------------------------------------------------
# The record the retained-results read answers — inherited
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RetainedResult:
    step_id: str
    handler: str
    proposed_outcome: str
    result_text: str
    produced_at: datetime
    state: str
    decided_by: str | None = None
    decided_at: datetime | None = None


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": SERVED_STEP,
            "name": SERVED_STEP_NAME,
            "kind": StepKind.AUTOMATED,
            "confirmer": "prs_confirmer",
            "handler": HANDLER,
            **overrides,
        }
    )


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


class _FakeSteps:
    def __init__(self, *definitions: StepDefinition) -> None:
        self.records = tuple(
            _StepRecord(definition, (index + 1) * 10)
            for index, definition in enumerate(definitions)
        )

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, 7

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return tuple(record.definition for record in self.records)


# ---------------------------------------------------------------------------
# The page module's seams — inherited
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
    pytest.fail("the page made a scoped read without an access scope")


def _product_id_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
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


class _FakeRetainedRead:
    def __init__(self, *records: _RetainedResult) -> None:
        self.records = tuple(records)

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        _scope_in(args, kwargs)
        return self.records


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class _AsinStore:
    def __init__(self, product: Product) -> None:
        self.product = product

    async def get_by_id(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get_by_product_id(
        self, product_id: Any, *args: Any, **kwargs: Any
    ) -> Product:
        return self.product

    async def save(self, product: Product) -> None:
        self.product = product


def _product(sku: str = SKU, name: str = NAME) -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )


def _identified(sku: str = SKU) -> Product:
    """A product whose *identity* is fully populated — ASIN, stage,
    confirmer — and about which no automated step has established
    anything.

    Deliberately separated from the automation-established facts: this is
    the product the third scenario is about ("a product with no
    sub-category and no hazard categories recorded").
    """
    product = _product(sku)
    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_MOVED)
    store = _AsinStore(product)
    asyncio.run(record_asin(cast(Any, store), product.id, Asin(ASIN)))
    return store.product


def _never_screened(sku: str = "HAZ-NEVER-01") -> Product:
    return _identified(sku)


def _screened_clear(sku: str = "HAZ-CLEAR-01") -> Product:
    product = _identified(sku)
    product.record_hazard_categories(())
    return product


def _flagged(sku: str = "HAZ-FLAG-01") -> Product:
    product = _identified(sku)
    product.record_hazard_categories(HAZARD_CATEGORIES)
    return product


def _with_sub_category(product: Product) -> Product:
    product.record_sub_category(SUB_CATEGORY)
    return product


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


@dataclass
class _Surface:
    client: TestClient
    product: Product


def _app(
    monkeypatch: pytest.MonkeyPatch,
    product: Product,
    *,
    results: tuple[_RetainedResult, ...] = (),
) -> _Surface:
    catalog = _FakeCatalog(product)
    _install(monkeypatch, _VERIFY_NAMES, _fake_verify, "admin-session")
    _install(
        monkeypatch,
        _SCOPE_NAMES,
        _FakeScopeResolution(AccessScope.unrestricted()),
        "scope-resolution",
    )
    _install(monkeypatch, _LIST_NAMES, catalog.list_products, "product listing")
    _install(monkeypatch, _GET_PRODUCT_NAMES, catalog.get_product_by_id, "product read")
    _install(
        monkeypatch,
        _RETAINED_NAMES,
        _FakeRetainedRead(*results),
        "retained-results read",
    )
    _install(monkeypatch, _STEPS_NAMES, _FakeSteps(_step()), "served-playbook")

    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, product)


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
    value = getattr(value, "value", value)
    template = _dossier_template()
    opening = template.index("{")
    closing = template.index("}")
    return f"{template[:opening]}{value}{template[closing + 1 :]}"


def _render(monkeypatch: pytest.MonkeyPatch, product: Product) -> str:
    surface = _app(monkeypatch, product)
    response = surface.client.get(_dossier_path(product.id))
    assert response.status_code == 200, response.text
    return str(response.text)


# ---------------------------------------------------------------------------
# Requirement: The dossier renders what the product's automated steps have
# established about it
# ---------------------------------------------------------------------------


def test_the_region_is_present_and_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The region is present and marked.

    WHEN the dossier is rendered for any product
    THEN it carries a region marked `established-by-automation`, distinct
    from the region marked `retained-for-decision`.

    SPECIFIED: both the marker and the distinctness. The second is what
    excludes folding the two facts into the retained record — "they are
    not retained results, which are proposals held for a decision".
    """
    page = _render(monkeypatch, _flagged())

    region = _region(page)
    retained = _marked(page, RETAINED_FOR_DECISION)
    assert retained, (
        "the dossier carries no region marked "
        f"{RETAINED_FOR_DECISION!r}, so the distinctness this scenario "
        "requires cannot be observed"
    )
    for other in retained:
        assert other is not region, (
            "one element carries both markers, so the two regions are the "
            "same region wearing two class names"
        )
        assert region not in list(_ancestors(other)), (
            f"the {RETAINED_FOR_DECISION!r} region is nested inside the "
            f"{ESTABLISHED_BY_AUTOMATION!r} one"
        )
        assert other not in list(_ancestors(region)), (
            f"the {ESTABLISHED_BY_AUTOMATION!r} region is nested inside the "
            f"{RETAINED_FOR_DECISION!r} one"
        )


def test_a_recorded_sub_category_is_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A recorded sub-category is rendered.

    WHEN the dossier is rendered for a product with a sub-category
    recorded
    THEN the region presents that sub-category.

    `product-catalog` has specified a read for this since it was
    introduced and no surface has ever rendered it; this is the first
    test that says a surface must.
    """
    page = _render(monkeypatch, _with_sub_category(_flagged()))

    assert SUB_CATEGORY in _all_text(_region(page)), (
        "the recorded sub-category is not presented inside the region "
        f"marked {ESTABLISHED_BY_AUTOMATION!r}"
    )


def test_the_region_renders_for_a_product_with_nothing_established(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The region renders for a product with nothing established.

    WHEN the dossier is rendered for a product with no sub-category and no
    hazard categories recorded
    THEN the region still renders, stating each field's absence rather
    than being omitted.

    SPECIFIED: both halves. "Stating each field's absence" is asserted as
    two separately-marked fields, because one `not-recorded` inside the
    region would satisfy a page that rendered one field and dropped the
    other.
    """
    product = _never_screened()
    assert product.sub_category is None  # precondition

    page = _render(monkeypatch, product)

    region = _region(page)
    absent = [
        element for element in _elements(region) if NOT_RECORDED in _classes(element)
    ]
    assert len(absent) >= 2, (
        "the region marked "
        f"{ESTABLISHED_BY_AUTOMATION!r} carries {len(absent)} field(s) "
        f"marked {NOT_RECORDED!r}; both the sub-category and the hazard "
        "categories are absent and each must state its own absence"
    )


# ---------------------------------------------------------------------------
# Requirement: An unrecorded sub-category is stated, not blank
# ---------------------------------------------------------------------------


def test_an_absent_sub_category_carries_the_pages_absence_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An absent sub-category carries the page's absence marker.

    WHEN the dossier is rendered for a product that has never had a
    sub-category recorded
    THEN its sub-category field is rendered carrying `not-recorded`, and
    is not left blank.

    SPECIFIED: the marker, and that the field is not blank — a blank
    "reads as data the page failed to load".
    """
    page = _render(monkeypatch, _flagged())

    field_element = _field_in_region(page, "sub-category")
    assert _carries(field_element, NOT_RECORDED), (
        "the absent sub-category field carries no "
        f"{NOT_RECORDED!r}: {_all_text(field_element)!r}"
    )
    assert _all_text(field_element).strip(), (
        "the absent sub-category field is rendered blank"
    )


# ---------------------------------------------------------------------------
# Requirement: The dossier renders hazard categories in three states, and
# never renders a clear screening as an absence
# ---------------------------------------------------------------------------


def _hazard_field(page: str) -> _Node:
    """The hazard-categories field inside the region.

    Located by the word "hazard" rather than by a fixed label, since the
    delta fixes the markers and not the wording.
    """
    return _field_in_region(page, "hazard")


def test_a_never_screened_product_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A never-screened product says so.

    WHEN the dossier is rendered for a product with no hazard categories
    recorded
    THEN its hazard-categories field carries `not-recorded`, does not
    carry `screened-clear`, and is not left blank.

    SPECIFIED: all three clauses, asserted by marker rather than by prose
    match (`tasks.md` 1.24).
    """
    page = _render(monkeypatch, _never_screened())

    field_element = _hazard_field(page)
    assert _carries(field_element, NOT_RECORDED)
    assert not _carries(field_element, SCREENED_CLEAR), (
        "a product nothing has screened is marked as screened and clear"
    )
    assert _all_text(field_element).strip()


def test_a_screened_clear_product_is_not_rendered_as_unscreened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A screened-clear product is not rendered as unscreened.

    WHEN the dossier is rendered for a product whose recorded hazard
    categories are an empty set
    THEN its hazard-categories field carries `screened-clear`, does not
    carry `not-recorded`, and states that the product was screened and no
    category was found.

    **The assertion the whole surface change exists for.** The negative
    clause is what a positive-only test would miss: a page carrying both
    markers would tell an admin that a screened product is unscreened,
    "collapsing, on the only surface that shows the field, the distinction
    the storage was extended to keep".

    The third clause is asserted as *readable text beyond the field's own
    label*, not against a wording — `design.md`'s Open Questions leaves
    the phrasing to be settled against the running page and records that
    doing so "changes no test derived from" the specified parts.
    """
    page = _render(monkeypatch, _screened_clear())

    field_element = _hazard_field(page)
    assert _carries(field_element, SCREENED_CLEAR), (
        "a screening that found the product clear carries no "
        f"{SCREENED_CLEAR!r}: {_all_text(field_element)!r}"
    )
    assert not _carries(field_element, NOT_RECORDED), (
        "a screened product is marked as never recorded, which is the one "
        "confusion the three-state rule exists to prevent"
    )
    assert _all_text(field_element).strip(), (
        "the screened-clear field is rendered blank"
    )


def test_a_flagged_product_presents_its_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A flagged product presents its categories.

    WHEN the dossier is rendered for a product whose recorded hazard
    categories are non-empty
    THEN its hazard-categories field presents every recorded category,
    each readable and separated from the next, and carries neither
    `not-recorded` nor `screened-clear`.

    SPECIFIED: every category, the separation, and both negative markers.
    *How* they are separated is a visual judgement the delta declines to
    fix, so what is asserted is that something stands between them.
    """
    page = _render(monkeypatch, _flagged())

    field_element = _hazard_field(page)
    text = _all_text(field_element)
    for category in HAZARD_CATEGORIES:
        assert category in text, (
            f"the recorded category {category!r} is not presented: {text!r}"
        )
    squashed = "".join(text.split())
    for left, right in pairwise(HAZARD_CATEGORIES):
        run_together = "".join(left.split()) + "".join(right.split())
        assert run_together not in squashed, (
            f"{left!r} and {right!r} are presented run together with "
            f"nothing between them: {text!r}"
        )
    assert not _carries(field_element, NOT_RECORDED)
    assert not _carries(field_element, SCREENED_CLEAR)


def test_categories_are_not_presented_in_a_collections_notation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Categories are not presented in a collection's notation.

    WHEN the dossier renders a product whose recorded hazard categories
    carry several members
    THEN the field carries no bracket, no quotation mark around a category
    and no type name from a collection's programming notation.

    Asserted item by item so the failure names which notation leaked. A
    view model handing the template the sequence itself, rendered with
    `{{ value }}`, produces `['supplements', ...]` — which is the exact
    failure this scenario names and the most likely one.
    """
    page = _render(monkeypatch, _flagged())

    text = _all_text(_hazard_field(page))
    for notation in _COLLECTION_NOTATION:
        assert notation not in text, (
            f"the hazard-categories field carries {notation!r}, a "
            f"collection's own programming notation: {text!r}"
        )
    lowered = text.lower()
    for type_name in _COLLECTION_TYPE_NAMES:
        assert type_name not in lowered, (
            f"the hazard-categories field carries the type name {type_name!r}: {text!r}"
        )


def test_the_three_states_render_three_ways(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The three states render three ways.

    WHEN the dossier is rendered for each of a never-screened product, a
    screened-clear product and a flagged product
    THEN the three hazard-categories fields are distinguishable from one
    another in the rendered response.

    SPECIFIED, and asserted **pairwise** on the rendered field rather than
    each against a literal (`tasks.md` 1.24) — a per-state assertion
    passes an implementation that renders two of them identically while
    each satisfies its own clause.
    """
    never = _all_text(_hazard_field(_render(monkeypatch, _never_screened())))
    clear = _all_text(_hazard_field(_render(monkeypatch, _screened_clear())))
    flagged = _all_text(_hazard_field(_render(monkeypatch, _flagged())))

    rendered = {
        "never screened": never,
        "screened clear": clear,
        "flagged": flagged,
    }
    for left, right in (
        ("never screened", "screened clear"),
        ("never screened", "flagged"),
        ("screened clear", "flagged"),
    ):
        assert rendered[left] != rendered[right], (
            f"{left!r} and {right!r} render identically as {rendered[left]!r}"
        )


@pytest.mark.parametrize(
    "make_product",
    [_screened_clear, _flagged],
    ids=["screened-clear", "flagged"],
)
def test_the_field_claims_no_ratification(
    make_product: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: The field claims no ratification.

    WHEN the dossier renders a product's hazard categories in any recorded
    state
    THEN the field is presented as what a screening established, and
    presents it as neither confirmed, approved nor accepted by a member.

    SPECIFIED: the negative clause, over **both** recorded states, since
    "any recorded state" is what the WHEN says.

    Scoped to the field rather than to the page: the retained-results
    record legitimately carries the vocabulary of a decision, and a
    page-wide search would match it and assert nothing about this field.

    The positive half — "presented as what a screening established" — is
    asserted as the screening vocabulary being present, DERIVED as a
    keyword set since the delta fixes what the field must convey and not
    its wording.
    """
    page = _render(monkeypatch, make_product())

    text = _all_text(_hazard_field(page)).lower()
    for word in _RATIFICATION_WORDS:
        assert word not in text, (
            f"the hazard-categories field presents its value as {word!r}, "
            "asserting on the product's own record something no member did: "
            f"{text!r}"
        )
    # DERIVED keyword set for the positive half.
    assert any(word in text for word in ("screen", "screened", "screening")), (
        "the hazard-categories field does not present its value as what a "
        f"screening established: {text!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: The region established by automation offers no action and
# carries no page-local styling
# ---------------------------------------------------------------------------


def test_the_region_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The region is read-only.

    WHEN the region marked `established-by-automation` is rendered
    THEN it contains no form and no element carrying `row-action`.

    SPECIFIED: both, asserted negatively as this capability already
    requires of the dossier as a whole. `_is_control` additionally catches
    a button or an htmx verb, which is the same affordance under another
    tag.
    """
    page = _render(monkeypatch, _with_sub_category(_flagged()))

    region = _region(page)
    forms = [element for element in _elements(region) if element.tag == "form"]
    assert not forms, (
        f"the region marked {ESTABLISHED_BY_AUTOMATION!r} contains {len(forms)} form(s)"
    )
    actions = [
        element for element in _elements(region) if ROW_ACTION in _classes(element)
    ]
    assert not actions, (
        f"the region carries {len(actions)} element(s) marked {ROW_ACTION!r}"
    )
    controls = [element for element in _elements(region) if _is_control(element)]
    assert not controls, (
        "the region carries a clickable affordance: "
        f"{[element.tag for element in controls]}"
    )


def test_the_new_states_presentation_is_shared_not_page_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The new state's presentation is shared, not page-local.

    WHEN the dossier renders a field carrying `screened-clear`
    THEN the page carries no page-local style block, that marker's
    presentation coming from the shared admin stylesheet.

    SPECIFIED. This is the change most likely to reach for a page-local
    rule, since a new marker is exactly the occasion for one — which is
    why the delta restates the prohibition for this region rather than
    relying on the page-wide one.
    """
    page = _render(monkeypatch, _screened_clear())

    assert _marked(page, SCREENED_CLEAR), (
        f"nothing on the page carries {SCREENED_CLEAR!r}, so this scenario's "
        "WHEN was never reached"
    )
    styles = [element for element in _elements(_tree(page)) if element.tag == "style"]
    assert not styles, (
        f"the dossier carries {len(styles)} page-local style block(s); the "
        f"presentation of {SCREENED_CLEAR!r} belongs in the shared admin "
        "stylesheet beside the page's other markers"
    )
    inline = [
        element
        for element in _elements(_tree(page))
        if element.attrs.get("style", "").strip()
    ]
    assert not inline, (
        "the dossier carries inline style attributes, which is page-local "
        f"styling by another spelling: {[element.tag for element in inline]}"
    )
