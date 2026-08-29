"""The launch journal page, and every guarantee this change extends from
the list and the detail page to cover it too (`launch-admin`,
`add-admin-breadcrumb-navigation`).

Derived strictly from the delta spec
`openspec/changes/add-admin-breadcrumb-navigation/specs/launch-admin/spec.md`
— two ADDED requirements (all four of their scenarios) and four MODIFIED
requirements, each read for the scenarios stated **as revised**, which
now range over "any of the list, the detail page, or the journal page" /
"the three pages" rather than "either page":

- ADDED *A launch's journal page carries a breadcrumb to the list and to
  its launch* — *Both ancestors are reachable from the journal page*
- ADDED *A launch's journal page renders its journal, newest first* — all
  three scenarios
- MODIFIED *Both surfaces are read-only* — *The pages present no
  launch-changing control*, now over the three pages
- MODIFIED *A launch the caller may not see is indistinguishable from one
  that does not exist* — all four scenarios, now naming "a detail page or
  a journal page" throughout
- MODIFIED *Both surfaces ride the admin session and carry the shared
  header* — both scenarios, now over "any of the three pages"
- MODIFIED *The pages' presentation comes from the shared admin
  vocabulary* — all three scenarios, now over "any of the three pages" /
  "all three pages"

One requirement's own scenario is narrower than its prose: *A launch
whose product cannot be resolved is served* states its WHEN/THEN only
over "a detail page", though the requirement text says outright "The
journal page resolves the same launch position the detail page does, so
it is served or refused by the identical rule." Per this file's dispatch,
that clause is exercised too, as a DERIVED extension of the same
scenario onto the journal page rather than as a fifth literal scenario
(`test_a_launch_whose_product_cannot_be_resolved_is_served`).

The detail page's own breadcrumb, and its offer of the journal in one
action, are covered in `test_launch_detail_breadcrumb.py`, not here — this
file is scoped to the journal page itself and to the four MODIFIED
requirements' now-three-page reach.

## Level

The launch router mounted alone for the journal-specific requirements,
and beside the playbook, roster and shared-asset routers (via
`with_neighbours=True`) for the two requirements whose THEN reaches
another module's surface or asset route — the same composition
`test_launch_admin_detail.py` uses, for the same reason.

## Expected first-run state

**Absent target for the journal-specific requirements.** No GET route
whose path mentions "journal" exists on `launch_admin.router` yet, so
`_journal_template` fails by name for every test that needs it, rather
than the file failing to collect.

**Live-route failures for the three-page extensions.** The list and the
detail page already exist and already carry a working session guard,
header and stylesheet — what's new is the journal page's absence from
the response the read-only, absence-refusal, session/header and
vocabulary requirements are now stated over. Those tests are written to
range over exactly the three pages the requirement now names, so a
journal route that raises `AttributeError`/`RouteNotFound` (or a similar
failure) resolving `_journal_template`/`_journal_path` is what they are
expected to fail on until the route exists.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at this worktree — 1472 passed, 0 failed, on
2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the delta: that the journal page carries a breadcrumb naming, in
order, the list and the launch, each as a link, with the journal page
itself as the un-linked last segment; that the journal page renders
entries newest-first, each naming what occurred, when, and what caused
it, and states plainly when there is nothing recorded; that none of the
three pages offers any launch-changing control; that a detail page or a
journal page requested for an absent, forbidden or unknown launch
position is refused identically to a route that does not exist, while
one whose product the catalog cannot resolve is served; that all three
pages require a valid admin session, carry the shared header, and take
their presentation from the shared admin vocabulary through a route no
single admin surface owns.

INVENTED, each with its correction point named in the code:

- The journal route's path template: the one single-parameter GET route
  on `launch_admin.router` whose path mentions "journal". Correction
  point: `_journal_template`.
- The breadcrumb locator: an offer (a plain, unnarrowed link) rendered
  above the page's `<h1>` and not one of its ancestors, together with an
  un-linked "Journal" segment rendered the same way — the identical
  reading `test_launch_detail_breadcrumb.py` uses, for the identical
  reason (a locator that did not discriminate "above the title" would
  pass against an accidental match elsewhere on the page). Correction
  points: `_before_title`, `_unlinked_mentions`.
- Every module seam, the render-date injection, the header locator and
  the stylesheet locators — taken unchanged from
  `test_launch_admin_detail.py`.

Correcting a locator is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_person
from commerce_ops.access.infrastructure.driving import roster_admin as roster_module
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import (
    launch_admin as page_module,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching

_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"


def _assets_module() -> ModuleType:
    import importlib

    return importlib.import_module(_ASSETS_MODULE_NAME)


VOCABULARY_ASSET: Final = "vocabulary.css"

# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

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

LISTING: Final = Discipline("listing")
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 12, 1)

PRODUCT_NAME: Final = "Alpha widget"

_HEADER_WORDS: Final = ("playbook", "roster", "people", "users")
_LAUNCH_WORDS: Final = ("launch", "launches", "product")

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


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": "Work this step asks for",
        "description": None,
        "gate": "commit",
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=365),
        "blocking": True,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "assignees": (),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="journal-page-v1",
        gates=_gates(),
        steps=(_step("strategy.commitment-agreed"),),
    )


PLAYBOOK: Final = _playbook()


def _start(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=LAUNCH_DATE
    )
    return launch


def _launching(sku: str, name: str) -> Product:
    product = Product.register(
        sku=Sku(sku), marketplace_id=MARKETPLACE, name=name, registered_at=T_REGISTERED
    )
    product.change_stage(Launching(phase=1), confirmed_by="Helen", at=T_REGISTERED)
    return product


def _unresolvable_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class _FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self.order: list[Launch] = list(launches)

    async def get_by_product_id(
        self, product_id: ProductId, *_a: Any, **_k: Any
    ) -> Launch | None:
        for launch in self.order:
            if launch.product_id == product_id:
                return launch
        return None

    async def save(self, launch: Launch) -> None:  # pragma: no cover - unused
        self.order.append(launch)

    async def list_all(self, *_a: Any, **_k: Any) -> tuple[Launch, ...]:
        return tuple(self.order)

    async def all(self, *a: Any, **k: Any) -> tuple[Launch, ...]:
        return await self.list_all(*a, **k)

    async def list_launches(self, *a: Any, **k: Any) -> tuple[Launch, ...]:
        return await self.list_all(*a, **k)


class _FakePlaybooks:
    def get(self, version: str) -> LaunchPlaybook:
        return PLAYBOOK


class _FakeRosterStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
        self.version += 1


async def _build_roster() -> _FakeRosterStore:
    store = _FakeRosterStore()
    await create_person(
        roster=store,
        principal="the-seeding-admin",
        display_name="Alice Admin",
        slack_identity=PRINCIPAL,
        clickup_user_id=None,
        admin=True,
    )
    return store


def _roster_store() -> _FakeRosterStore:
    return asyncio.run(_build_roster())


class _Catalog:
    def __init__(self, *products: Product, fails: bool = False) -> None:
        self.products = tuple(products)
        self.fails = fails

    async def list_products(self, *_a: Any, **_k: Any) -> tuple[Product, ...]:
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
        return self.products

    async def get_product_by_id(
        self, product_id: ProductId, *_a: Any, **_k: Any
    ) -> Product | None:
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
        for product in self.products:
            if product.id == product_id:
                return product
        return None


class _FakeStepStore:
    """The playbook-admin page's own store, so its router can be mounted
    beside the launch one for the header/vocabulary scenarios."""

    def __init__(self) -> None:
        self.records: tuple[Any, ...] = ()
        self.version = 41

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


class _FakePerson:
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_FakePerson, ...]:
        return (_FakePerson("prs_01HQ8Z6M4A", "Alice Admin"),)

    people = list_people


# ---------------------------------------------------------------------------
# Installing the page's seams
# ---------------------------------------------------------------------------

_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "roster": ("roster", "people", "roster_store", "read_roster"),
    "resolve_scope": ("resolve_scope",),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
}
_JOURNAL_SEAM_NAMES: Final = (
    "read_journal",
    "journal",
    "read_launch_journal",
    "journal_entries",
)
_PLAYBOOK_ROSTER_SEAMS: Final = ("roster", "read_roster", "people", "roster_reader")


def _install(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, seam: str, value: Any
) -> None:
    for name in _SEAMS[seam]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"launch_admin exposes no {seam!r} seam under any of {_SEAMS[seam]} — "
        "correct `_SEAMS` to the implemented module"
    )


def _install_journal(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, value: Any
) -> None:
    for name in _JOURNAL_SEAM_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"launch_admin exposes no journal seam under any of {_JOURNAL_SEAM_NAMES} — "
        "correct `_JOURNAL_SEAM_NAMES` to the implemented module"
    )


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


class _StubDate(date):
    _today: date = RENDER_DATE

    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return cls._today


_CLOCK_NAMES: Final = ("today", "current_date", "now", "clock", "render_date")


def _render_on(monkeypatch: pytest.MonkeyPatch, module: ModuleType, day: date) -> None:
    for name in _CLOCK_NAMES:
        if callable(getattr(module, name, None)):
            monkeypatch.setattr(module, name, lambda *_a, **_k: day)
            return
    if isinstance(getattr(module, "date", None), type):
        stub = type("_FixedDate", (_StubDate,), {"_today": day})
        monkeypatch.setattr(module, "date", stub)
        return
    pytest.fail(
        "launch_admin exposes no seam for the day it renders on — correct "
        "`_render_on` to the implemented module"
    )


@dataclass(frozen=True)
class _Surface:
    client: TestClient
    module: ModuleType
    #: `None` only where the fixture's catalog holds no product at all
    #: (the unresolvable-product scenarios) — every such test passes its
    #: product identifier explicitly, so this is never dereferenced there.
    product: Product | None


def _empty_journal_fn() -> Any:
    async def _empty(*_a: Any, **_k: Any) -> tuple[Any, ...]:
        return ()

    return _empty


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launches: _FakeLaunchStore,
    catalog: _Catalog,
    journal: Any = None,
    scope: AccessScope | None = None,
    with_neighbours: bool = False,
    signed_in: bool = True,
) -> _Surface:
    module = page_module
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "roster", _roster_store())
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)
    _install_journal(
        monkeypatch, module, journal if journal is not None else _empty_journal_fn()
    )
    _render_on(monkeypatch, module, RENDER_DATE)
    if scope is not None:

        async def _resolver(*_a: Any, **_k: Any) -> AccessScope:
            return scope

        _install(monkeypatch, module, "resolve_scope", _resolver)

    app = FastAPI()
    app.include_router(module.router)
    if with_neighbours:
        monkeypatch.setattr(playbook_module, "steps", _FakeStepStore())
        monkeypatch.setattr(playbook_module, "verify_admin_session", _fake_verify)
        for name in _PLAYBOOK_ROSTER_SEAMS:
            if hasattr(playbook_module, name):
                monkeypatch.setattr(playbook_module, name, _FakeRoster())
                break
        monkeypatch.setattr(roster_module, "roster", _roster_store())
        monkeypatch.setattr(roster_module, "verify_admin_session", _fake_verify)
        assets = _assets_module()
        monkeypatch.setattr(assets, "verify", _fake_verify)
        app.include_router(playbook_module.router)
        app.include_router(roster_module.router)
        app.include_router(assets.router)

    client = TestClient(app)
    if signed_in:
        client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    product = catalog.products[0] if catalog.products else None
    return _Surface(client, module, product)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


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


def _detail_template(module: ModuleType) -> str:
    candidates = [
        str(route.path)
        for route in module.router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and str(route.path).count("{") == 1
        and "journal" not in str(route.path).lower()
    ]
    assert len(candidates) == 1, (
        f"launch_admin exposes {len(candidates)} single-parameter GET routes "
        f"not mentioning 'journal' ({candidates}) — correct `_detail_template`"
    )
    return candidates[0]


def _journal_template(module: ModuleType) -> str:
    candidates = [
        str(route.path)
        for route in module.router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and str(route.path).count("{") == 1
        and "journal" in str(route.path).lower()
    ]
    if len(candidates) != 1:
        pytest.fail(
            f"launch_admin exposes {len(candidates)} single-parameter GET routes "
            f"mentioning 'journal' ({candidates}); exactly one journal route is "
            "expected — correct `_journal_template` to the implemented route, or "
            "this is the absent-target state if the route does not exist yet"
        )
    return candidates[0]


def _fill(template: str, value: str) -> str:
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + value + template[closed + 1 :]


def _list_path(surface: _Surface) -> str:
    return _shortest_get_route(surface.module.router)


def _detail_path(surface: _Surface, product_id: ProductId | None = None) -> str:
    if product_id is not None:
        pid = product_id
    else:
        assert surface.product is not None, (
            "no product_id was given and the surface's fixture catalog holds "
            "no product to fall back to"
        )
        pid = surface.product.id
    return _fill(_detail_template(surface.module), pid.value)


def _journal_path(surface: _Surface, product_id: ProductId | None = None) -> str:
    if product_id is not None:
        pid = product_id
    else:
        assert surface.product is not None, (
            "no product_id was given and the surface's fixture catalog holds "
            "no product to fall back to"
        )
        pid = surface.product.id
    return _fill(_journal_template(surface.module), pid.value)


def _get(surface: _Surface, path: str, *, follow_redirects: bool = True) -> Any:
    return surface.client.get(path, follow_redirects=follow_redirects)


def _fetch(surface: _Surface, path: str) -> str:
    response = _get(surface, path)
    assert response.status_code == 200, (
        f"{path} was not served: {response.status_code} {response.text[:300]}"
    )
    return str(response.text)


def _list_html(surface: _Surface) -> str:
    return _fetch(surface, _list_path(surface))


def _detail_html(surface: _Surface, product_id: ProductId | None = None) -> str:
    return _fetch(surface, _detail_path(surface, product_id))


def _journal_html(surface: _Surface, product_id: ProductId | None = None) -> str:
    return _fetch(surface, _journal_path(surface, product_id))


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


def _all_text(node: _Node) -> str:
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_all_text(child))
    return " ".join(part for part in found if part).lower()


def _own_text(node: _Node) -> str:
    return " ".join(
        child.text for child in node.children if isinstance(child, _Text)
    ).lower()


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

    Correction point, added after the current segment stopped being a
    distinct element that rendered *before* a separate `<h1>`: a locator
    still searching the whole tree for an unlinked element before the
    title falls through to a false positive on the document's own
    `<title>` tag, which independently happens to carry the same text and
    render before the `<h1>` in document order — exactly the false match
    `ai-toolkit:testing` requires a locator not to produce.
    """
    return label.lower() in _own_text(title) and not _inherited(
        title, lambda n: n.tag == "a"
    )


def _names(node: _Node, words: tuple[str, ...]) -> bool:
    return any(word in _all_text(node) for word in words)


def _header_of(root: _Node, *, other_path: str) -> _Node:
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the page renders no link to {other_path!r} at all, so it carries "
            "no header from which that admin surface is reachable"
        )
    candidates = [
        ancestor
        for link in outbound
        for ancestor in _ancestors(link)
        if _names(ancestor, _LAUNCH_WORDS)
        and ancestor.tag not in ("html", "body", "#document")
        and not any(e.tag in ("table", "form") for e in _elements(ancestor))
    ]
    if not candidates:
        pytest.fail(
            f"the link to {other_path!r} sits in no element that also names "
            "the launch surface — correct `_header_of` or `_LAUNCH_WORDS`"
        )
    return min(candidates, key=lambda n: 1 + sum(1 for _ in _elements(n)))


def _offers_in_one_action(header: _Node, path: str) -> bool:
    return any(_live(link) for link in _links_to(header, path))


_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _identifies_current(header: _Node) -> bool:
    within = [header, *_elements(header)]
    naming = [
        element
        for element in within
        if _names(element, _LAUNCH_WORDS)
        and not any(_names(child, _LAUNCH_WORDS) for child in _elements(element))
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


@dataclass(frozen=True)
class _Control:
    method: str
    url: str
    inert: bool
    text: str


def _controls(html: str) -> list[_Control]:
    found: list[_Control] = []
    for element in _elements(_tree(html)):
        disabled = _inherited(element, _element_disabled)
        if element.tag == "a":
            href = element.attrs.get("href", "")
            found.append(
                _Control("get", href, disabled or href in ("", "#"), _all_text(element))
            )
            continue
        if element.tag == "form":
            method = (element.attrs.get("method") or "get").lower()
            url = element.attrs.get("action", "")
            for verb in _HX_VERBS:
                if verb in element.attrs:
                    method = verb.removeprefix("hx-")
                    url = element.attrs[verb]
            found.append(_Control(method, url, disabled, _all_text(element)))
            continue
        for verb in _HX_VERBS:
            if verb in element.attrs:
                found.append(
                    _Control(
                        verb.removeprefix("hx-"),
                        element.attrs[verb],
                        disabled,
                        _all_text(element),
                    )
                )
    return found


def _shape_of(response: Any) -> tuple[int, str, str]:
    return (
        response.status_code,
        response.headers.get("content-type", ""),
        response.text,
    )


def _absent_route(surface: _Surface) -> Any:
    return surface.client.get("/a-route-this-application-does-not-register")


# ===========================================================================
# ADDED requirement: A launch's journal page carries a breadcrumb to the
# list and to its launch
# ===========================================================================


def test_both_ancestors_are_reachable_from_the_journal_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Both ancestors are reachable from the journal page.

    WHEN a launch's journal page is rendered
    THEN its breadcrumb trail offers the launch list and that launch's
    detail page, each in one action
    AND the trail's last segment names the journal and is not a link.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
    )

    root = _tree(_journal_html(surface))
    title = _first(root, "h1")
    list_path = _list_path(surface)
    detail_path = _detail_path(surface)

    list_offers = [
        link
        for link in _links_to(root, list_path)
        if _live(link)
        and _before_title(link, title)
        and not _in_shared_header(link)
        and not _in_shared_header(link)
    ]
    # SPECIFIED: the list, offered as a link, above the title.
    assert list_offers, (
        f"the journal page offers no plain link to {list_path!r} above its "
        f"<h1> — anchors present: "
        f"{sorted({e.attrs.get('href', '') for e in _elements(root) if e.tag == 'a'})}"
    )

    detail_offers = [
        link
        for link in _links_to(root, detail_path)
        if _live(link) and _before_title(link, title) and not _in_shared_header(link)
    ]
    # SPECIFIED: the launch's own detail page, also offered above the title.
    assert detail_offers, (
        f"the journal page offers no plain link to {detail_path!r} (this "
        f"launch's own detail page) above its <h1>"
    )

    # SPECIFIED: the trail's last segment names the journal and is not a
    # link — the page's own `<h1>` *is* that segment now.
    assert _current_segment_is(title, "journal"), (
        f"the journal page's <h1> does not name 'journal' as its own, "
        f"un-linked text ({_own_text(title)!r}) — correct "
        "`_current_segment_is` if the current segment is worded some other way"
    )


# ===========================================================================
# ADDED requirement: A launch's journal page renders its journal, newest
# first
# ===========================================================================


def test_a_journal_entry_names_what_occurred_when_and_what_caused_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An entry names when it occurred, and shows its subject,
    source and who recorded it as separate facts.

    WHEN a launch's journal holds an entry
    THEN the journal page renders it naming when it occurred, and shows
    its subject, its source, and who recorded it, each in its own
    column -- `raw-out-the-journal-columns` replaced this page's earlier
    composed `what`/`cause` fields entirely with these raw ones plus a
    composed `detail` phrase.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    subject = "commit"
    when = datetime(2027, 3, 2, 10, 30, tzinfo=UTC)
    source = "slack"
    actor = "an-actor-not-on-the-roster"

    async def _one_entry(*_a: Any, **_k: Any) -> tuple[Any, ...]:
        return (
            type(
                "_Entry",
                (),
                {
                    "when": when,
                    "kind": "approval",
                    "label": "Approval",
                    "category": "judgment",
                    "subject": subject,
                    "source": source,
                    "actor": actor,
                    "playbook_version": None,
                    "outcome": None,
                    "reason": None,
                    "evidence": None,
                    "gate_id": None,
                    "decision": "approving",
                    "posture": None,
                    "standing_at": None,
                    "previous_date": None,
                    "new_date": None,
                    "unsatisfied": (),
                },
            )(),
        )

    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        journal=_one_entry,
    )

    text = _all_text(_tree(_journal_html(surface)))
    # SPECIFIED: when it occurred...
    assert when.date().isoformat() in text or (
        str(when.day) in text and str(when.year) in text
    ), f"the journal page does not name when it occurred: {text!r}"
    # ...and its subject, source and who recorded it, each its own fact.
    assert subject in text, f"the journal page does not show its subject: {text!r}"
    assert source in text, f"the journal page does not show its source: {text!r}"
    assert actor.lower() in text, (
        f"the journal page does not show who recorded it: {text!r}"
    )


def test_journal_entries_render_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Entries render newest first.

    WHEN a launch's journal holds several entries
    THEN the journal page renders them most recent first.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    marks = ("the-oldest-entry", "the-middle-entry", "the-newest-entry")
    moments = (
        datetime(2027, 1, 2, 9, 0, tzinfo=UTC),
        datetime(2027, 2, 3, 9, 0, tzinfo=UTC),
        datetime(2027, 3, 4, 9, 0, tzinfo=UTC),
    )

    async def _entries(*_a: Any, **_k: Any) -> tuple[Any, ...]:
        # Handed over oldest-first, so passing cannot be arrival order.
        # The mark rides `outcome` -- `step-outcome-recorded`'s own fact
        # field, folded into the composed `detail` phrase -- since `what`
        # no longer exists (`raw-out-the-journal-columns`).
        return tuple(
            type(
                "_Entry",
                (),
                {
                    "when": moment,
                    "kind": "step-outcome-recorded",
                    "label": "Outcome",
                    "category": "progression",
                    "subject": None,
                    "source": None,
                    "actor": None,
                    "playbook_version": None,
                    "outcome": mark,
                    "reason": None,
                    "evidence": None,
                    "gate_id": None,
                    "decision": None,
                    "posture": None,
                    "standing_at": None,
                    "previous_date": None,
                    "new_date": None,
                    "unsatisfied": (),
                },
            )()
            for mark, moment in zip(marks, moments, strict=True)
        )

    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        journal=_entries,
    )

    html = _journal_html(surface).lower()
    positions = [html.index(mark) for mark in reversed(marks)]
    assert positions == sorted(positions), (
        f"the journal page renders {marks} in the order they arrived, not "
        "most recent first"
    )


def test_an_empty_journal_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An empty journal says so.

    WHEN a launch's journal holds no entry
    THEN the journal page renders and states that nothing is recorded.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
    )

    text = _all_text(_tree(_journal_html(surface)))
    assert any(
        phrase in text
        for phrase in ("nothing is recorded", "no entries", "nothing recorded", "empty")
    ), f"the empty journal page states nothing: {text[:400]!r}"


# ===========================================================================
# MODIFIED requirement: Both surfaces are read-only — now the three pages
# ===========================================================================


def test_the_pages_present_no_launch_changing_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The pages present no launch-changing control.

    WHEN any of the list, the detail page, or the journal page is
    rendered for a launch in any state
    THEN it offers no control that records an outcome, approves a gate,
    decides an automated result, or moves a launch date.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
    )

    pages = {
        "list": _list_html(surface),
        "detail": _detail_html(surface),
        "journal": _journal_html(surface),
    }
    for page, html in pages.items():
        writing = [
            control
            for control in _controls(html)
            if control.method.upper() != "GET" and not control.inert
        ]
        assert not writing, (
            f"the {page} page offers {[(c.method, c.url, c.text) for c in writing]}, "
            "a control that submits something"
        )


# ===========================================================================
# MODIFIED requirement: A launch the caller may not see is indistinguishable
# from one that does not exist — now over a detail page or a journal page
# ===========================================================================


def test_a_product_with_no_launch_is_refused_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A product with no launch is refused as absent.

    WHEN a detail page or a journal page is requested for a product that
    has no launch position
    THEN the response is shaped like a request for a route that does not
    exist.
    """
    catalogued = _launching("PX-100", "Catalogued but never launched")
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog(catalogued)
    )
    absent = _shape_of(_absent_route(surface))

    for path, page in (
        (_detail_path(surface, catalogued.id), "detail"),
        (_journal_path(surface, catalogued.id), "journal"),
    ):
        refused = _get(surface, path, follow_redirects=False)
        assert _shape_of(refused) == absent, (
            f"the {page} page for a product with no launch position answers "
            f"{refused.status_code}, not the shape an unregistered route answers "
            "with"
        )


def test_a_forbidden_launch_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A forbidden launch is refused identically.

    WHEN a detail page or a journal page is requested for a launch the
    caller's scope does not permit
    THEN the response is identical in shape to the one given for a
    product with no launch.

    Unreachable end to end today, and covered as the spec's own inline
    note prescribes: **the scope resolver alone** is stubbed, the real
    read stays behind it, and the response is asserted against the one
    given for a product with no launch.
    """
    permitted = _launching("PX-100", "Permitted widget")
    forbidden = _launching("PX-200", "Forbidden widget")
    never_launched = _launching("PX-300", "Never launched")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(permitted.id), _start(forbidden.id)),
        catalog=_Catalog(permitted, forbidden, never_launched),
        scope=AccessScope.permitting((permitted.id, never_launched.id)),
    )

    for kind, path_of in (("detail", _detail_path), ("journal", _journal_path)):
        out_of_scope = _get(
            surface, path_of(surface, forbidden.id), follow_redirects=False
        )
        no_launch = _get(
            surface, path_of(surface, never_launched.id), follow_redirects=False
        )
        assert _shape_of(out_of_scope) == _shape_of(no_launch), (
            f"the {kind} page for a forbidden launch is refused differently "
            f"from one for a product with no launch: {out_of_scope.status_code} "
            f"versus {no_launch.status_code}"
        )
        assert forbidden.name.lower() not in out_of_scope.text.lower()
    # DERIVED guard: the permitted launch is still served on both pages.
    assert _get(surface, _detail_path(surface, permitted.id)).status_code == 200
    assert _get(surface, _journal_path(surface, permitted.id)).status_code == 200


def test_a_launch_whose_product_cannot_be_resolved_is_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch whose product cannot be resolved is served.

    WHEN a detail page is requested for a launch position whose product
    the catalog cannot resolve
    THEN the page is served, identifying the launch by its raw product
    identifier.

    DERIVED extension: the requirement's own text states "the journal
    page resolves the same launch position the detail page does, so it
    is served or refused by the identical rule" — exercised here too,
    though the literal scenario names only the detail page.
    """
    unknown_id = _unresolvable_product_id()
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(_start(unknown_id)), catalog=_Catalog()
    )

    served = _get(surface, _detail_path(surface, unknown_id))
    assert served.status_code == 200, (
        "a detail page for a launch whose product the catalog cannot resolve "
        f"is refused: {served.status_code}"
    )
    assert unknown_id.value in served.text

    # DERIVED: the journal page, by the requirement's own stated rule.
    served_journal = _get(surface, _journal_path(surface, unknown_id))
    assert served_journal.status_code == 200, (
        "the journal page for a launch whose product the catalog cannot "
        f"resolve is refused: {served_journal.status_code} — the requirement "
        "text states the journal page follows the identical rule the detail "
        "page's own scenario states"
    )
    assert unknown_id.value in served_journal.text


def test_an_unknown_identifier_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unknown identifier is refused identically.

    WHEN a detail page or a journal page is requested for an identifier
    with no launch position and no catalog product
    THEN the response is identical in shape to the other two refusals.
    """
    catalogued = _launching("PX-100", "Catalogued but never launched")
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog(catalogued)
    )
    absent = _shape_of(_absent_route(surface))

    for kind, path_of in (("detail", _detail_path), ("journal", _journal_path)):
        unknown = _get(
            surface,
            path_of(surface, _unresolvable_product_id()),
            follow_redirects=False,
        )
        no_launch = _get(
            surface, path_of(surface, catalogued.id), follow_redirects=False
        )
        assert _shape_of(unknown) == _shape_of(no_launch) == absent, (
            f"the {kind} page for an identifier naming nothing the system "
            f"knows is refused differently from a product with no launch: "
            f"{unknown.status_code} versus {no_launch.status_code}"
        )


# ===========================================================================
# MODIFIED requirement: Both surfaces ride the admin session and carry the
# shared header — now any of the three pages
# ===========================================================================


def test_a_request_without_a_session_is_refused_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A request without a session is refused as absent.

    WHEN any of the three pages is requested with no admin session, or
    with one that has expired
    THEN the response is shaped like a request for a route that does not
    exist.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        signed_in=False,
    )
    absent = _shape_of(_absent_route(surface))

    for path, page in (
        (_list_path(surface), "list"),
        (_detail_path(surface), "detail"),
        (_journal_path(surface), "journal"),
    ):
        no_session = surface.client.get(path, follow_redirects=False)
        assert _shape_of(no_session) == absent, (
            f"the {page} page requested with no admin session answers "
            f"{no_session.status_code}, not the shape an unregistered route "
            "answers with"
        )
        surface.client.cookies.set(_SESSION_COOKIE, "an-expired-session")
        expired = surface.client.get(path, follow_redirects=False)
        assert _shape_of(expired) == absent, (
            f"the {page} page requested with an expired admin session answers "
            f"{expired.status_code}, not the shape an unregistered route "
            "answers with"
        )
        surface.client.cookies.delete(_SESSION_COOKIE)


def test_the_header_names_the_other_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The header names the other surfaces.

    WHEN any of the three pages is rendered
    THEN its header identifies the launch surface as the one being viewed
    and offers the other admin surfaces in one action.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    playbook_path = _shortest_get_route(playbook_module.router)
    roster_path = _shortest_get_route(roster_module.router)

    pages = {
        "list": _list_html(surface),
        "detail": _detail_html(surface),
        "journal": _journal_html(surface),
    }
    for page, html in pages.items():
        header = _header_of(_tree(html), other_path=roster_path)
        for path, what in ((roster_path, "roster"), (playbook_path, "playbook")):
            assert _offers_in_one_action(header, path), (
                f"the {page} page's header offers no live link to the {what} "
                f"surface at {path!r}"
            )
        assert _identifies_current(header), (
            f"the {page} page's header does not identify the launch surface "
            "as the one being viewed"
        )


# ===========================================================================
# MODIFIED requirement: The pages' presentation comes from the shared
# admin vocabulary — now all three pages
# ===========================================================================


def test_the_pages_carry_no_styling_of_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The pages carry no styling of their own.

    WHEN any of the three pages is rendered
    THEN its presentation comes from the shared admin stylesheet, and the
    page carries no styling of its own.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    shared_paths = {
        route.path
        for route in _assets_module().router.routes
        if getattr(route, "path", None)
    }
    shared_prefixes = tuple(path.split("{")[0] for path in shared_paths)

    pages = {
        "list": _list_html(surface),
        "detail": _detail_html(surface),
        "journal": _journal_html(surface),
    }
    for page, html in pages.items():
        root = _tree(html)
        hrefs = _stylesheet_hrefs(root)
        assert hrefs, f"the {page} page loads no stylesheet at all"
        for href in hrefs:
            path = urlsplit(href).path
            assert path.startswith(shared_prefixes), (
                f"the {page} page loads {href!r}, which the shared admin asset "
                f"route ({sorted(shared_paths)}) does not serve"
            )
            served = surface.client.get(path)
            assert served.status_code == 200, (
                f"the {page} page links {href!r} but it is not served: "
                f"{served.status_code}"
            )
        assert not _style_blocks(root), (
            f"the {page} page carries a page-local <style> block"
        )
        assert not [
            element
            for element in _elements(root)
            if element.attrs.get("style", "").strip()
        ], f"the {page} page carries inline `style` attributes of its own"


def test_the_stylesheet_is_not_reached_through_another_surfaces_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The stylesheet is not reached through another surface's
    route.

    WHEN any of the three pages is rendered
    THEN the stylesheet it loads is served by a route no single admin
    surface owns.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    owned = {
        route.path.split("{")[0]
        for module in (playbook_module, roster_module, surface.module)
        for route in module.router.routes
        if getattr(route, "path", None)
    }

    pages = {
        "list": _list_html(surface),
        "detail": _detail_html(surface),
        "journal": _journal_html(surface),
    }
    for page, html in pages.items():
        for href in _stylesheet_hrefs(_tree(html)):
            path = urlsplit(href).path
            assert not any(
                path.startswith(prefix) for prefix in owned if prefix not in ("/", "")
            ), (
                f"the {page} page reaches {href!r} through a route owned by an "
                "admin surface's own module"
            )


def test_a_vocabulary_change_reaches_these_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A vocabulary change reaches these pages.

    WHEN the shared admin stylesheet changes
    THEN all three pages render under the changed vocabulary without any
    of them being edited.
    """
    product = _launching("PX-100", PRODUCT_NAME)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    assets = _assets_module()
    shared_app = FastAPI()
    shared_app.include_router(assets.router)
    shared_client = TestClient(shared_app)
    shared_client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)

    pages = {
        "list": _list_html(surface),
        "detail": _detail_html(surface),
        "journal": _journal_html(surface),
    }
    loaded: dict[str, set[str]] = {}
    for page, html in pages.items():
        hrefs = _stylesheet_hrefs(_tree(html))
        assert hrefs, f"the {page} page loads no stylesheet at all"
        loaded[page] = {urlsplit(href).path for href in hrefs}
        for path in loaded[page]:
            through_shared = shared_client.get(path)
            assert through_shared.status_code == 200, (
                f"the {page} page's stylesheet {path!r} is not served by the "
                "shared asset route mounted alone, so it is a copy this "
                "surface carries rather than the shared vocabulary"
            )
            assert through_shared.content == surface.client.get(path).content, (
                f"the {page} page's stylesheet {path!r} differs from what the "
                "shared route serves"
            )
    # SPECIFIED: *all three* pages — the same sheets, so one vocabulary
    # change reaches every one of them rather than some of them.
    assert loaded["list"] == loaded["detail"] == loaded["journal"], (
        f"the three pages load different stylesheets: {loaded}, so a "
        "vocabulary change would reach some of them and not others"
    )
