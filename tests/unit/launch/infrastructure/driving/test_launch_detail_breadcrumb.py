"""The launch detail page's breadcrumb trail and its offer of the launch's
journal page (`launch-admin`, `add-admin-breadcrumb-navigation`).

Derived strictly from the delta spec
`openspec/changes/add-admin-breadcrumb-navigation/specs/launch-admin/spec.md`
— one MODIFIED requirement (its one scenario, as revised) and one ADDED
requirement (both its scenarios):

- MODIFIED *A launch's detail page offers the way back to the list*
  - *The list is reachable from a launch's detail page*
- ADDED *A launch's detail page offers its journal in one action*
  - *The journal is reachable from a launch's detail page*
  - *An empty journal is still reachable*

The requirement's own prose states two further, testable claims beyond
its one literal scenario:

- "The detail page SHALL carry a breadcrumb trail immediately above its
  title" — read here as: the offer of the list, and the un-linked
  current segment, both render *before* the page's `<h1>` in document
  order, and neither is the `<h1>` itself or one of its ancestors. This
  is what tells the new breadcrumb apart from the page's *existing*
  title (which already names the launch) and its existing
  `page-head`-local "Back to the launches" control (which today sits
  *after* the `<h1>`, inside the same flex row) — a locator that did not
  discriminate the two would pass against the page as it renders today,
  which is exactly the false-positive `ai-toolkit:testing` warns a test
  must not produce.
- "The link SHALL reach the list as the list renders with no narrowing
  and nothing revealed" — carried forward unchanged from the pre-existing
  (pre-breadcrumb) requirement this one supersedes. `test_launch_detail_
  navigation.py`, testing the superseded wording, already asserts this as
  a DERIVED clause over the offered link's own query string; this file
  does the same over the breadcrumb's version of that link.

## What this file does NOT cover

Two guarantees the journal page itself carries — its own breadcrumb
("Both ancestors are reachable from the journal page") and its rendering
of the journal's contents — are covered in `test_launch_journal_page.py`
beside every other guarantee extended to the journal page by this
change's MODIFIED requirements (read-only, the absence-shaped refusals,
the session guard and shared header, and the shared vocabulary). This
file is scoped to the detail page's own two requirements: what its
breadcrumb offers, and that it offers the journal at all.

## Level

The launch router alone, over fakes for the launch store, the served
playbook, the membership and the catalog read — the smallest unit that can
render the detail page. Neither the header nor the shared stylesheet is
under test here, so no sibling admin router is mounted; the breadcrumb
locator below discriminates the trail from the header by document order
and by the header's own vocabulary, rather than by mounting it.

## Expected first-run state

**The target already exists**, in the sense that
`commerce_ops.launch.infrastructure.driving.launch_admin` and its detail
route are already implemented (this is a presentation-only change to an
already-built page) — but the breadcrumb and the journal offer this file
asserts are not, so every test here is expected to fail against a live
route rather than at import: confirmed by hand against the page as it
renders today, whose `page-head` still carries a "Back to the launches"
control *after* the `<h1>` rather than a breadcrumb *before* it, and
which offers no link mentioning "journal" at all. Per
`ai-toolkit:testing`, a failure here establishes only that today's page
does not yet carry the asserted behaviour — and, per the same standard,
a locator that passed unmodified against today's page would have
established nothing at all, which is why the ordering constraint above
was added and confirmed to flip this test to failing before it was kept.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at this worktree — 1472 passed, 0 failed, on
2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the delta: that the breadcrumb offers the list in one action,
without scripting; that the trail's last segment names the launch and is
not a link; that the trail sits immediately above the page's title; that
the detail page offers the launch's journal page in one action, without
scripting, regardless of whether the journal holds anything.

INVENTED, each with its correction point named in the code:

- How the breadcrumb trail is told apart from the shared admin header,
  which also links to list-adjacent surfaces: the trail is read as an
  element rendered *before* the `<h1>` (and not one of its ancestors)
  that offers the list as a plain, unnarrowed link, together with an
  element — also before the `<h1>` and not one of its ancestors — whose
  own text states the launch's label and names none of the header's own
  surface words (`_HEADER_WORDS`). Correction point:
  `_is_breadcrumb_candidate`, `_before_title`, `_unlinked_mentions`.
- That "the current page as the un-linked last segment" is read as an
  element whose **own** text (not text contributed by a nested link)
  names the launch, and which is not itself inside an anchor. Correction
  point: `_unlinked_mentions`.
- That the journal is offered as a plain link whose own text mentions
  "journal" — the label `tasks.md` 2.1 names for the descendants region.
  Correction point: `_live_offers_mentioning`.
- Every module seam, the render-date injection and the domain fixtures —
  taken unchanged from `test_launch_admin_detail.py` and
  `test_launch_detail_navigation.py`.

Correcting a locator is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: that the list is reachable, unnarrowed, from a plain trail
above the title; that the trail's last segment is the launch and is not
a link; and that the journal is offered in one action regardless of
whether it holds anything.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
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
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fakes import StubDate
from tests.support.fixtures import MARKETPLACE
from tests.support.playbook import gates as _gates

# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

LISTING: Final = Discipline("listing")
PRINCIPAL: Final = "U01ALICE"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 12, 1)

PRODUCT_NAME: Final = "Alpha widget"

#: INVENTED. The words the shared admin header, but no breadcrumb, uses to
#: name the *other* top-level admin surfaces — used to tell the two apart
#: without mounting the header's own routers.
_HEADER_WORDS: Final = ("playbook", "team", "members", "member")

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
        "status": StepStatus.ACTIVE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="breadcrumb-v1",
        gates=_gates(),
        steps=(_step("strategy.commitment-agreed"),),
    )


PLAYBOOK: Final = _playbook()


def _launch(product_id: ProductId) -> Launch:
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


class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
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
    return asyncio.run(_build_members())


class _Catalog:
    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)

    async def list_products(self, *_a: Any, **_k: Any) -> tuple[Product, ...]:
        return self.products

    async def get_product_by_id(
        self, product_id: ProductId, *_a: Any, **_k: Any
    ) -> Product | None:
        for product in self.products:
            if product.id == product_id:
                return product
        return None


# ---------------------------------------------------------------------------
# Installing the page's seams
# ---------------------------------------------------------------------------

_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "members": ("members", "members_store", "read_members"),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
}
_JOURNAL_SEAM_NAMES: Final = (
    "read_journal",
    "journal",
    "read_launch_journal",
    "journal_entries",
)


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


_fake_verify = fake_verify(PRINCIPAL)


class _StubDate(StubDate):
    _today = RENDER_DATE


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
class _World:
    client: TestClient
    module: ModuleType
    product: Product


def _world(monkeypatch: pytest.MonkeyPatch, *, journal: Any = None) -> _World:
    product = _launching("PX-100", PRODUCT_NAME)
    module = page_module
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", _FakeLaunchStore(_launch(product.id)))
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
    catalog = _Catalog(product)
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    async def _empty_journal(*_a: Any, **_k: Any) -> tuple[Any, ...]:
        return ()

    _install_journal(
        monkeypatch, module, journal if journal is not None else _empty_journal
    )
    _render_on(monkeypatch, module, RENDER_DATE)

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _World(client, module, product)


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
    """The detail route's own path template.

    A second single-parameter GET route (the journal route this change
    adds) is deliberately excluded by name, so this locator survives once
    that route exists alongside this one.
    """
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
        f"not mentioning 'journal' ({candidates}); exactly one detail route is "
        "expected — correct `_detail_template`"
    )
    return candidates[0]


def _fill(template: str, value: str) -> str:
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + value + template[closed + 1 :]


def _list_path(world: _World) -> str:
    return _shortest_get_route(world.module.router)


def _detail_path(world: _World) -> str:
    return _fill(_detail_template(world.module), world.product.id.value)


def _fetch(world: _World, path: str) -> str:
    response = world.client.get(path)
    assert response.status_code == 200, (
        f"{path} was not served: {response.status_code} {response.text[:300]}"
    )
    return str(response.text)


def _detail_html(world: _World) -> str:
    return _fetch(world, _detail_path(world))


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
    """Only the text *directly* held by this element — not text
    contributed by a nested element (in particular, not by a nested
    anchor). This is what "the current segment is un-linked" is read
    against: an element that merely *contains* an unlinked sibling text
    run would otherwise pass by accident."""
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
    """Every plain, unnarrowed anchor to `path` — no query at all, which
    is what "as the list renders with no narrowing and nothing revealed"
    requires of the destination."""
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


def _live_offers_mentioning(root: _Node, word: str) -> list[_Node]:
    """Plain, live anchors (no scripting, not disabled or hidden) whose
    own visible text mentions `word`."""
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and element.attrs.get("href")
        and _live(element)
        and word.lower() in _all_text(element)
    ]


def _first(root: _Node, tag: str) -> _Node:
    for element in _elements(root):
        if element.tag == tag:
            return element
    pytest.fail(f"the page renders no {tag!r} element at all")


def _before_title(node: _Node, title: _Node) -> bool:
    """Whether `node` renders before the page's title, in document order,
    and is not one of the title's own ancestors (a container that merely
    *wraps* the title does not count as sitting "above" it)."""
    if node is title:
        return False
    if any(ancestor is title for ancestor in (node, *_ancestors(node))):
        # node is the title or a descendant of it
        return False
    if any(ancestor is node for ancestor in _ancestors(title)):
        return False
    return node.order < title.order


def _is_breadcrumb_candidate(node: _Node) -> bool:
    """Whether this element could plausibly be (part of) the breadcrumb
    trail rather than the shared admin header, which links to the same
    handful of top-level surfaces from every page. Excludes anything
    naming one of the header's own surface words."""
    return not any(word in _all_text(node) for word in _HEADER_WORDS)


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


def _common_ancestor(a: _Node, b: _Node) -> _Node | None:
    chain_b = [b, *_ancestors(b)]
    for node in [a, *_ancestors(a)]:
        for other in chain_b:
            if node is other:
                return node
    return None


# ===========================================================================
# MODIFIED requirement: A launch's detail page offers the way back to the
# list — revised to a breadcrumb trail
# ===========================================================================


def test_the_breadcrumb_offers_the_list_and_names_the_launch_as_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The list is reachable from a launch's detail page.

    WHEN a launch's detail page is rendered
    THEN its breadcrumb trail offers the launch list in one action, without
    scripting
    AND the trail's last segment names the launch and is not a link.

    Both halves are read against the page's own `<h1>`: the requirement
    states the trail sits "immediately above its title", so an offer or a
    segment that is not the title itself, and renders before it, is what
    a breadcrumb — as opposed to the page's existing title and its
    existing (post-title) "Back to the launches" control — looks like.
    """
    world = _world(monkeypatch)

    root = _tree(_detail_html(world))
    title = _first(root, "h1")
    list_path = _list_path(world)

    offers = [
        link
        for link in _links_to(root, list_path)
        if _live(link) and _before_title(link, title) and not _in_shared_header(link)
    ]
    # SPECIFIED: the trail offers the list, in one action, without
    # scripting, above the title — and, the requirement's further clause,
    # reaching it unnarrowed (no query at all is what `_links_to` already
    # selects for).
    assert offers, (
        f"the detail page offers no plain, unnarrowed link to {list_path!r} "
        "rendered above its <h1> — its anchors are "
        f"{sorted({e.attrs.get('href', '') for e in _elements(root) if e.tag == 'a'})}"
    )

    # SPECIFIED: the trail's last segment names the launch and is not a
    # link. The launch's own label is its product's name, which the
    # header does not render (the header names the *surface*, "Launches",
    # never an individual launch). The page's own `<h1>` *is* that
    # segment now — a page carrying a breadcrumb renders no separate
    # title of its own.
    assert _current_segment_is(title, PRODUCT_NAME), (
        f"the page's <h1> does not name {PRODUCT_NAME!r} as its own, "
        f"un-linked text ({_own_text(title)!r}) — correct "
        "`_current_segment_is` if the page renders the current segment "
        "some other way"
    )

    # DERIVED: the list-offering link and the current segment sit together
    # in one container that is not the shared admin header —
    # establishing these are one trail rather than two unrelated facts.
    container = None
    for offer in offers:
        found = _common_ancestor(offer, title)
        if found is not None and _is_breadcrumb_candidate(found):
            container = found
            break
    assert container is not None, (
        "no element on the page holds both the list-offering link and the "
        "<h1> together, outside the shared header — correct `_HEADER_WORDS` "
        "or `_is_breadcrumb_candidate` if the trail is expressed some other way"
    )


# ===========================================================================
# ADDED requirement: A launch's detail page offers its journal in one
# action
# ===========================================================================


def test_the_journal_is_reachable_from_a_launchs_detail_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The journal is reachable from a launch's detail page.

    WHEN a launch's detail page is rendered
    THEN it offers that launch's journal page in one action, without
    scripting.

    Exercised with a *non-empty* journal, so this scenario is not
    conditioned on the empty case the next test states separately.
    """

    async def _one_entry(*_a: Any, **_k: Any) -> tuple[Any, ...]:
        return (
            type(
                "_Entry",
                (),
                {
                    "when": datetime(2027, 3, 2, 10, 30, tzinfo=UTC),
                    "kind": "approval",
                    "label": "Approval",
                    "category": "judgment",
                    "subject": "commit",
                    "source": "slack",
                    "actor": "Helen",
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

    world = _world(monkeypatch, journal=_one_entry)
    root = _tree(_detail_html(world))
    detail_path = _detail_path(world)
    list_path = _list_path(world)

    offers = _live_offers_mentioning(root, "journal")
    # SPECIFIED: offered in one action, without scripting.
    assert offers, (
        "the detail page offers no plain, live link mentioning 'journal' — "
        "correct `_live_offers_mentioning` if the offer is worded or marked "
        "up another way"
    )
    # DERIVED guard: the offer really leads somewhere other than the
    # detail page or the list, and that destination actually serves.
    href = offers[0].attrs["href"]
    target = (
        href
        if href.startswith("/")
        else urlsplit(urljoin(detail_path + "/", href)).path
    )
    assert urlsplit(target).path not in (detail_path, list_path), (
        f"the 'journal' offer's target {target!r} is the detail page or the "
        "list itself, so it does not lead to a distinct journal page"
    )
    served = world.client.get(target)
    assert served.status_code == 200, (
        f"following the detail page's journal offer to {target!r} does not "
        f"serve a page: {served.status_code} {served.text[:300]}"
    )


def test_an_empty_journal_is_still_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An empty journal is still reachable.

    WHEN a launch's detail page is rendered for a launch whose journal
    holds no entry
    THEN the detail page still offers the journal page in one action.

    The fixture's journal is empty by default (`_world`'s `_empty_journal`
    stub), which is exactly the condition this scenario names.
    """
    world = _world(monkeypatch)  # journal defaults to empty

    root = _tree(_detail_html(world))

    offers = _live_offers_mentioning(root, "journal")
    # SPECIFIED: still offered, in one action.
    assert offers, (
        "a launch whose journal holds nothing offers no link mentioning "
        "'journal' on its detail page — the journal page itself, not the "
        "detail page, is what should state there is nothing recorded"
    )
