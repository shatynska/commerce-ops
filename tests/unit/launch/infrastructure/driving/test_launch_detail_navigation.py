"""Getting around the launch detail page: the way back to the list, and
the gate a reader navigated to (`launch-admin`,
`tidy-the-launch-pages-presentation`).

Derived strictly from the delta spec
`openspec/changes/tidy-the-launch-pages-presentation/specs/launch-admin/spec.md`
— two of its requirements and the single scenario each carries:

- *A launch's detail page offers the way back to the list*
  - *The list is reachable from a launch's detail page*
- *The gate a reader navigated to is distinct from the gate the launch
  stands at*
  - *The stylesheet distinguishes the two*

The second requirement's other claim — that the two "read as different
at a glance" — is inspection-only by its own text (`tasks.md` 6.4) and
takes no test here. The requirement is emphatic about why the scenario
is stated over a **stylesheet** rather than over a page: "Which entry a
reader followed is a URL fragment, and a fragment is never sent to a
server: the response is identical whichever entry was followed, so no
scenario over a response can observe it." This file therefore reads the
served stylesheet, exactly as
`test_launch_surface_vocabulary_rules.py` does for the same reason.

## Level

The launch router mounted beside the shared asset router, the way
`main.py` composes them, over fakes for the stores and the catalog read.
That is the smallest unit that can observe both scenarios: one is about
a link the detail page renders, and the other is about a stylesheet no
launch route serves. The sibling admin surfaces are *not* mounted —
neither scenario ranges over them, and the cross-surface obligation that
does is `test_launch_surface_vocabulary_rules.py`'s, which mounts all
five.

## Reading a stylesheet in a test

The parser and matcher below are INVENTED whole and support the selector
subset an admin stylesheet uses: type, class, id and attribute
compounds, the four combinators, selector groups, and `@media` /
`@supports` / `@layer` nesting. They are the ones
`test_launch_surface_vocabulary_rules.py` established, duplicated rather
than imported because this project shares no test-helper module between
test files. Anything they cannot parse is collected and **fails the
test that reads it** rather than being silently skipped, so an exotic
selector cannot slip past by being unreadable.

Pseudo-classes are parsed but not evaluated: no static matcher can tell
which element `:target` selects, since that depends on a fragment the
server never sees. That is exactly why the requirement is stated over
the sheet's own selectors, and it is why `:target` is detected here as
**intent in the selector text** rather than as a matched element. See
`_navigated_rules`.

## Expected first-run state

**The target already exists.** This change's implementation is in the
working tree ahead of these tests, which reverses this project's usual
order (`design.md` — Decision 9). Per `ai-toolkit:testing`, a pass on
the first run is therefore the expected result and establishes that the
surfaces currently behave as asserted — it is *not* the fourth failure
state. What a pass does not establish is that these assertions
discriminate; that was established separately, by re-running each
predicate against the same responses with the back link removed and
with the `:target` rule removed, and is recorded in the manifest.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1427 passed, 0
failed, 2 xfailed, on 2026-08-28. Scoped to the two commit-time tiers,
which are the tiers this file joins; the integration tier was not run
(no database configured here).

## What is fixed, and what is INVENTED

Fixed by the delta:

- That the detail page offers the launch list **in one action, without
  scripting**.
- That the offer reaches the list "as the list renders with no narrowing
  and nothing revealed" — so the destination carries no query, which is
  a deliberate choice the requirement argues for rather than an
  accident.
- That the served stylesheet carries a rule applying to the gate group a
  reader has navigated to, and that the rule is **distinct** from the
  one marking the gate the launch stands at.

INVENTED, each with its correction point named in the code:

- That "a rule that applies to the gate group a reader has navigated to"
  is read as a rule whose selector uses `:target` — including
  `:target-within` and `:has(:target)` — and which matches the gate
  group, an anchor target within the gate sequence's own destinations,
  or an element inside a gate group. CSS offers no other mechanism for
  "the element the reader navigated to". Correction point:
  `_TARGET_PSEUDO`, `_navigated_rules`.
- That "the rule marking the gate the launch stands at" is a rule whose
  selector names the marker the page itself uses for the launch's
  position — read off the rendering rather than spelled here — and
  which matches an element carrying it. Correction points:
  `_CURRENT_CLASSES`, `_CURRENT_ATTRIBUTES`, `_current_rules`.
- That "distinct" is read first as **not the same declaration block**:
  a selector group pairing `:target` with the current-gate selector on
  one block gives the two states one treatment, which is the way this
  requirement is most plausibly satisfied on paper and defeated in
  fact. A second, weaker reading — that the declarations differ — is
  applied only where a current-marking rule reaches a gate group, so
  that a rule marking a *sequence entry* is not required to differ from
  a rule filling a *group*. Correction point: the test's own body,
  which labels the two readings apart.
- Every module seam, the render date's injection, and how the gate
  sequence and a gate group are located — inherited from
  `test_launch_admin_detail.py` and
  `test_launch_surface_vocabulary_rules.py`.

Correcting a seam or a locator is a fixture correction (failure state 3
in `ai-toolkit:testing`). What must survive unweakened is what each test
asserts: that the list is reachable in one plain action, and that the
sheet treats the two gates as two things.
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    NotStarted,
    OffsetAnchor,
    Refused,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import all_text as _all_text
from tests.support.html import ancestors as _ancestors
from tests.support.html import attribute_text as _attribute_text
from tests.support.html import classes as _classes
from tests.support.html import element_disabled as _element_disabled
from tests.support.html import element_hidden as _element_hidden
from tests.support.html import elements as _elements
from tests.support.html import inherited as _inherited
from tests.support.html import size as _size
from tests.support.html import tree as _tree
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

# ---------------------------------------------------------------------------
# The modules under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

#: SPECIFIED. The vocabulary both launch surfaces are required to take
#: their presentation from.
VOCABULARY_ASSET: Final = "vocabulary.css"


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so no launch "
            "detail page is served — the absent-target state, which "
            "establishes nothing about the assertions in this test"
        )


def _assets_module() -> ModuleType:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist ({absent}), so no shared "
            "stylesheet is served and the gate scenario cannot be read"
        )


# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

RECORDER: Final = "Nadia Recorder"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RECORDED_AT: Final = datetime(2027, 3, 2, 11, 47, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 12, 1)

COMMIT_STEP: Final = "strategy.commitment-agreed"
TITLE_STEP: Final = "listing.title-conforms"
IMAGES_STEP: Final = "listing.images-uploaded"
UNITS_STEP: Final = "inventory.units-received"
PROHIBITED_STEP: Final = "listing.no-incentivised-reviews"
UNTOUCHED_STEP: Final = "listing.nobody-has-touched-this"

STEP_NAMES: Final[dict[str, str]] = {
    COMMIT_STEP: "Commitment to launch is agreed",
    TITLE_STEP: "Title conforms to marketplace policy",
    IMAGES_STEP: "Hero and gallery images are uploaded",
    UNITS_STEP: "Units are received into the warehouse",
    PROHIBITED_STEP: "No incentivised reviews are solicited",
    UNTOUCHED_STEP: "Work nobody has touched",
}

#: INVENTED. How a page marks the surface, or the entry, being viewed —
#: taken unchanged from `test_launch_admin_detail.py`, which established
#: it for this same page's gate sequence.
_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = (
    "current",
    "active",
    "here",
    "is-current",
    "is-active",
    "now",
)

#: INVENTED. The only CSS mechanisms for "the element the reader
#: navigated to". `:has(:target)` is covered by the substring, which is
#: why intent is read from the selector's text rather than from a parsed
#: pseudo-class list.
_TARGET_PSEUDO: Final = ":target"

_SCRIPTING_ATTRIBUTES: Final = (*_HX_VERBS, "onclick", "onmousedown", "onkeydown")


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": STEP_NAMES.get(identifier, "Work this step asks for"),
        "description": None,
        "gate": "listable",
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=365),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook() -> LaunchPlaybook:
    """Steps at three of the eight gates, so the gate *sequence* is
    findable as the one region naming every gate while holding no served
    step — the locator `test_launch_admin_detail.py` established."""
    steps = (
        _step(COMMIT_STEP, gate="commit", blocking=True),
        _step(TITLE_STEP, gate="listable"),
        _step(IMAGES_STEP, gate="listable"),
        _step(UNITS_STEP, gate="listable", discipline=INVENTORY, blocking=True),
        _step(PROHIBITED_STEP, gate="ignition", hazard=Hazard.PROHIBITED_TACTIC),
        _step(UNTOUCHED_STEP, gate="ignition"),
    )
    return LaunchPlaybook(version="navigation-v1", gates=_gates(), steps=steps)


PLAYBOOK: Final = _playbook()

SERVED_ORDER: Final = tuple(
    step.identifier
    for gate in SPECIFIED_GATE_ORDER
    for step in PLAYBOOK.steps_for_gate(gate)
)
GATES_WITH_STEPS: Final = ("commit", "listable", "ignition")


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who=RECORDER,
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _launch(product_id: ProductId) -> Launch:
    """A launch standing at its first gate, with a spread of recorded
    and unrecorded outcomes, so that every region the two scenarios read
    is rendered."""
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=LAUNCH_DATE
    )
    for step_id, outcome in (
        (TITLE_STEP, Satisfied),
        (PROHIBITED_STEP, Refused),
        (UNITS_STEP, NotStarted),
    ):
        launch.record_step_outcome(
            PLAYBOOK, step_id=step_id, outcome=outcome, provenance=_provenance()
        )
    return launch


# ---------------------------------------------------------------------------
# Catalog products
# ---------------------------------------------------------------------------


def _launching(sku: str, name: str) -> Product:
    product = Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
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
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Launch | None:
        for launch in self.order:
            if launch.product_id == product_id:
                return launch
        return None

    async def save(self, launch: Launch) -> None:  # pragma: no cover - unused
        self.order.append(launch)

    async def list_all(self, *_args: Any, **_kwargs: Any) -> tuple[Launch, ...]:
        return tuple(self.order)

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)

    async def list_launches(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook = PLAYBOOK) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


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

    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
        return self.products

    async def get_product_by_id(
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Product | None:
        for product in self.products:
            if product.id == product_id:
                return product
        return None


# ---------------------------------------------------------------------------
# Installing the page's seams — the single correction point
# ---------------------------------------------------------------------------

_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "members": ("members", "members_store", "read_members"),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
    "read_journal": ("read_journal", "journal", "journal_entries"),
}


def _install(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, seam: str, value: Any
) -> None:
    for name in _SEAMS[seam]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"{_PAGE_MODULE_NAME} exposes no {seam!r} seam under any of "
        f"{_SEAMS[seam]} — correct `_SEAMS` to the implemented module"
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
        f"{_PAGE_MODULE_NAME} exposes no seam for the day it renders on "
        f"(looked for a callable named one of {_CLOCK_NAMES}, or its own "
        "`date`) — correct `_render_on` to the implemented module"
    )


@dataclass(frozen=True)
class _World:
    client: TestClient
    module: ModuleType
    product: Product


def _world(monkeypatch: pytest.MonkeyPatch) -> _World:
    product = _launching("PX-100", "Alpha widget")
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", _FakeLaunchStore(_launch(product.id)))
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
    catalog = _Catalog(product)
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    # Stubbed empty, so the surface stays hermetic. `read_journal` was
    # `None` when this file was written and reached nothing; it is wired
    # to a real store now, so a detail page rendered without this reaches
    # for a database.
    async def _no_journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    _install(monkeypatch, module, "read_journal", _no_journal)
    _render_on(monkeypatch, module, RENDER_DATE)

    assets = _assets_module()
    monkeypatch.setattr(assets, "verify", _fake_verify)

    app = FastAPI()
    app.include_router(module.router)
    app.include_router(assets.router)
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


def _parameterised_get_route(router: Any) -> str:
    # A second single-parameter GET route (the launch journal page
    # `add-admin-breadcrumb-navigation` adds) is excluded by name, so this
    # locator survives once that route exists alongside this one.
    candidates = [
        str(route.path)
        for route in router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and str(route.path).count("{") == 1
        and "journal" not in str(route.path).lower()
    ]
    assert len(candidates) == 1, (
        f"{router!r} exposes {len(candidates)} GET routes taking one path "
        "parameter and not mentioning 'journal'; exactly one is expected"
    )
    return str(candidates[0])


def _fill(template: str, value: str) -> str:
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + value + template[closed + 1 :]


def _fetch(world: _World, path: str) -> str:
    response = world.client.get(path)
    assert response.status_code == 200, (
        f"{path} was not served: {response.status_code} {response.text[:300]}"
    )
    return str(response.text)


def _list_path(world: _World) -> str:
    return _shortest_get_route(world.module.router)


def _detail_html(world: _World) -> str:
    template = _parameterised_get_route(world.module.router)
    return _fetch(world, _fill(template, world.product.id.value))


def _vocabulary(world: _World) -> str:
    template = _parameterised_get_route(_assets_module().router)
    return _fetch(world, _fill(template, VOCABULARY_ASSET))


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


def _haystack(node: _Node) -> str:
    return f"{_all_text(node)} {_attribute_text(node)}"


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


def _siblings(node: _Node) -> list[_Node]:
    parent = node.parent
    if parent is None:
        return [node]
    return [child for child in parent.children if isinstance(child, _Node)]


def _within(node: _Node) -> list[_Node]:
    return [node, *_elements(node)]


# ---------------------------------------------------------------------------
# The detail page's regions
# ---------------------------------------------------------------------------


def _gate_sequence(html: str) -> _Node:
    """The smallest element naming every gate while holding no served
    step — findable because five of the eight gates carry no step."""
    candidates = [
        element
        for element in _elements(_tree(html))
        if all(gate in _all_text(element) for gate in SPECIFIED_GATE_ORDER)
        and not any(_holds(element, step_id) for step_id in SERVED_ORDER)
    ]
    if not candidates:
        pytest.fail(
            "no element on the detail page names every gate of the sequence "
            "without also holding a served step — correct `_gate_sequence`"
        )
    return min(candidates, key=_size)


def _gate_group(html: str, gate: str) -> _Node:
    """The smallest *addressable* element holding every step of `gate` and
    no step of another gate.

    Correction point: since the gate's steps now render inside a `<table>`
    (`add-admin-breadcrumb-navigation`'s launch-page redesign), an
    un-addressed `<tbody>` also holds exactly one gate's steps and is
    strictly smaller than the `id`-carrying `<section>` wrapping it — the
    smallest *candidate*, but neither the fragment target nor an ancestor
    of the gate's own name (`.gate-name`, a *sibling* of the `<table>`
    inside that `<section>`, so `_within(tbody)` never reaches it).
    Filtering to `id`-carrying candidates first is what keeps this locator
    finding the group `:target` actually applies to.
    """
    mine = [step.identifier for step in PLAYBOOK.steps_for_gate(gate)]
    theirs = [step_id for step_id in SERVED_ORDER if step_id not in mine]
    candidates = [
        element
        for element in _elements(_tree(html))
        if all(_holds(element, step_id) for step_id in mine)
        and not any(_holds(element, other) for other in theirs)
    ]
    addressable = [element for element in candidates if element.attrs.get("id")]
    if not addressable:
        pytest.fail(
            f"no addressable (`id`-carrying) element holds exactly the steps "
            f"of gate {gate!r} ({mine}) without holding another gate's — "
            "correct `_gate_group`"
        )
    return min(addressable, key=_size)


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _anchor_targets(html: str) -> list[_Node]:
    """The elements the gate sequence's own entries navigate to.

    "Every entry in the sequence is an anchor into its own gate's
    steps", so the reader's fragment names one of these — and `:target`
    selects exactly the element the fragment names.
    """
    root = _tree(html)
    fragments = {
        urlsplit(entry.attrs.get("href", "")).fragment
        for entry in _within(_gate_sequence(html))
        if entry.tag == "a" and urlsplit(entry.attrs.get("href", "")).fragment
    }
    return [
        element
        for element in _elements(root)
        if element.attrs.get("id") and element.attrs["id"] in fragments
    ]


def _links_to(root: _Node, path: str) -> list[_Node]:
    """Every plain anchor whose destination is exactly `path` — no query,
    which is what "as the list renders with no narrowing and nothing
    revealed" requires of the destination."""
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


# ---------------------------------------------------------------------------
# The served stylesheet: parsing and matching
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Compound:
    tag: str | None
    classes: frozenset[str]
    identifier: str | None
    attributes: tuple[tuple[str, str, str], ...]
    pseudo_classes: tuple[str, ...]
    pseudo_elements: tuple[str, ...]


@dataclass(frozen=True)
class _Rule:
    selector: str
    group: str
    declarations: str
    context: str
    parts: tuple[tuple[str, _Compound], ...]

    @property
    def block(self) -> tuple[str, str, str]:
        """What identifies the declaration block this selector shares.

        Two selectors in one group share one block, and therefore one
        treatment — which is the way "distinct" is most plausibly
        breached.
        """
        return (self.context, self.group, self.declarations)

    @property
    def settled(self) -> str:
        return " ".join(self.declarations.split()).rstrip(";").strip()

    @property
    def names_current(self) -> bool:
        return any(
            (compound.classes & set(_CURRENT_CLASSES))
            or any(name in _CURRENT_ATTRIBUTES for name, _, _ in compound.attributes)
            for _, compound in self.parts
        )


@dataclass(frozen=True)
class _Vocabulary:
    rules: tuple[_Rule, ...]
    unparsed: tuple[str, ...]


def _strip_comments(css: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(css):
        if css.startswith("/*", index):
            closed = css.find("*/", index + 2)
            index = len(css) if closed == -1 else closed + 2
        else:
            out.append(css[index])
            index += 1
    return "".join(out)


def _split_group(selectors: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in selectors:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


_NESTING_AT_RULES: Final = ("@media", "@supports", "@layer", "@container", "@scope")


def _parse_rules(
    css: str, context: tuple[str, ...], unparsed: list[str]
) -> list[_Rule]:
    rules: list[_Rule] = []
    index = 0
    start = 0
    length = len(css)
    while index < length:
        character = css[index]
        if character == ";" and css[start:index].strip().startswith("@"):
            index += 1
            start = index
            continue
        if character == "{":
            prelude = css[start:index].strip()
            depth = 1
            cursor = index + 1
            while cursor < length and depth:
                if css[cursor] == "{":
                    depth += 1
                elif css[cursor] == "}":
                    depth -= 1
                cursor += 1
            body = css[index + 1 : cursor - 1]
            if prelude.startswith("@"):
                name = prelude.split(None, 1)[0].lower()
                if name in _NESTING_AT_RULES:
                    rules.extend(_parse_rules(body, (*context, prelude), unparsed))
            else:
                for selector in _split_group(prelude):
                    parts = _parse_complex(selector)
                    if parts is None:
                        unparsed.append(selector)
                        continue
                    rules.append(
                        _Rule(
                            selector=selector,
                            group=prelude,
                            declarations=body,
                            context=" ".join(context),
                            parts=parts,
                        )
                    )
            index = cursor
            start = cursor
            continue
        index += 1
    return rules


def _identifier_end(text: str, start: int) -> int:
    index = start
    while index < len(text) and (text[index].isalnum() or text[index] in "-_"):
        index += 1
    return index


def _parse_attribute(text: str) -> tuple[str, str, str]:
    for operator in ("~=", "|=", "^=", "$=", "*=", "="):
        if operator in text:
            name, _, value = text.partition(operator)
            return (name.strip().lower(), operator, value.strip().strip("\"'").lower())
    return (text.strip().lower(), "", "")


def _parse_compound(text: str) -> _Compound | None:
    tag: str | None = None
    classes: set[str] = set()
    identifier: str | None = None
    attributes: list[tuple[str, str, str]] = []
    pseudo_classes: list[str] = []
    pseudo_elements: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == ".":
            end = _identifier_end(text, index + 1)
            if end == index + 1:
                return None
            classes.add(text[index + 1 : end])
            index = end
        elif character == "#":
            end = _identifier_end(text, index + 1)
            identifier = text[index + 1 : end]
            index = end
        elif character == "[":
            end = text.find("]", index)
            if end == -1:
                return None
            attributes.append(_parse_attribute(text[index + 1 : end]))
            index = end + 1
        elif character == ":":
            double = text.startswith("::", index)
            offset = index + (2 if double else 1)
            end = _identifier_end(text, offset)
            name = text[offset:end]
            if end < len(text) and text[end] == "(":
                depth = 0
                cursor = end
                while cursor < len(text):
                    if text[cursor] == "(":
                        depth += 1
                    elif text[cursor] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    cursor += 1
                if depth:
                    return None
                end = cursor + 1
            (pseudo_elements if double else pseudo_classes).append(name)
            index = end
        elif character == "*":
            tag = "*"
            index += 1
        elif character.isalpha():
            end = _identifier_end(text, index)
            tag = text[index:end].lower()
            index = end
        else:
            return None
    return _Compound(
        tag=tag,
        classes=frozenset(classes),
        identifier=identifier,
        attributes=tuple(attributes),
        pseudo_classes=tuple(pseudo_classes),
        pseudo_elements=tuple(pseudo_elements),
    )


def _parse_complex(selector: str) -> tuple[tuple[str, _Compound], ...] | None:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for character in selector.strip():
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and (character.isspace() or character in ">+~"):
            if current:
                tokens.append("".join(current))
                current = []
            if not character.isspace():
                tokens.append(character)
            elif tokens and tokens[-1] != " ":
                tokens.append(" ")
            continue
        current.append(character)
    if current:
        tokens.append("".join(current))
    while tokens and tokens[0] == " ":
        tokens.pop(0)
    while tokens and tokens[-1] == " ":
        tokens.pop()
    parts: list[tuple[str, _Compound]] = []
    combinator = ""
    for token in tokens:
        if token in (" ", ">", "+", "~"):
            combinator = token.strip() or " "
            continue
        compound = _parse_compound(token)
        if compound is None:
            return None
        parts.append((combinator, compound))
        combinator = ""
    return tuple(parts) if parts else None


def _compound_matches(compound: _Compound, node: _Node) -> bool:
    """Whether the compound's *static* half selects this element.

    Pseudo-classes are deliberately not evaluated: `:target` depends on
    a fragment no server sees, which is why the requirement is stated
    over the sheet rather than over a response. So a `:target` rule
    matches here on everything else it says, and the `:target` itself is
    read from the selector's text.
    """
    if compound.tag not in (None, "*") and node.tag != compound.tag:
        return False
    if compound.identifier and node.attrs.get("id") != compound.identifier:
        return False
    if not compound.classes <= _classes(node):
        return False
    for name, operator, value in compound.attributes:
        present = node.attrs.get(name)
        if present is None:
            return False
        present = present.lower()
        if operator == "=" and present != value:
            return False
        if operator == "~=" and value not in present.split():
            return False
        if operator == "^=" and not present.startswith(value):
            return False
        if operator == "$=" and not present.endswith(value):
            return False
        if operator == "*=" and value not in present:
            return False
        if operator == "|=" and not (
            present == value or present.startswith(f"{value}-")
        ):
            return False
    if "root" in compound.pseudo_classes and node.tag != "html":
        return False
    if (
        compound.tag in (None, "*")
        and not compound.classes
        and not compound.identifier
        and not compound.attributes
    ):
        return "root" in compound.pseudo_classes and node.tag == "html"
    return True


def _parts_match(parts: tuple[tuple[str, _Compound], ...], node: _Node) -> bool:
    combinator, compound = parts[-1]
    if not _compound_matches(compound, node):
        return False
    rest = parts[:-1]
    if not rest:
        return True
    candidates: list[_Node] = []
    if combinator in ("", " "):
        candidates = list(_ancestors(node))
    elif combinator == ">":
        parent = node.parent
        candidates = (
            [parent] if parent is not None and parent.tag != "#document" else []
        )
    elif combinator in ("+", "~"):
        siblings = _siblings(node)
        position = siblings.index(node)
        earlier = siblings[:position]
        candidates = earlier[-1:] if combinator == "+" else earlier
    return any(_parts_match(rest, candidate) for candidate in candidates)


def _matches(rule: _Rule, node: _Node) -> bool:
    return _parts_match(rule.parts, node)


def _read(css: str) -> _Vocabulary:
    unparsed: list[str] = []
    rules = _parse_rules(_strip_comments(css), (), unparsed)
    return _Vocabulary(tuple(rules), tuple(unparsed))


def _readable(vocabulary: _Vocabulary) -> None:
    """Every selector in the sheet was read, so nothing below skipped one
    silently."""
    assert not vocabulary.unparsed, (
        f"{len(vocabulary.unparsed)} selector(s) in the served stylesheet "
        f"could not be read: {list(vocabulary.unparsed)}. A selector this "
        "matcher cannot parse is one this scenario cannot be read against — "
        "correct `_parse_complex` rather than accepting the gap"
    )
    assert vocabulary.rules, (
        "the served stylesheet carries no rule at all, so nothing below reads anything"
    )


def _navigated_rules(vocabulary: _Vocabulary, reachable: list[_Node]) -> list[_Rule]:
    """Rules applying to the gate group a reader has navigated to.

    INVENTED reading, and the only one CSS admits: a rule whose selector
    uses `:target` (or `:target-within`, or `:has(:target)`, both of
    which the substring catches) and which otherwise selects a region a
    gate-sequence entry navigates into.
    """
    return [
        rule
        for rule in vocabulary.rules
        if _TARGET_PSEUDO in rule.selector
        and any(_matches(rule, node) for node in reachable)
    ]


def _current_rules(vocabulary: _Vocabulary, marked: list[_Node]) -> list[_Rule]:
    """Rules marking the gate the launch stands at: a rule naming the
    marker the page itself uses for its position, which matches an
    element carrying it, and which is not about the navigated-to state."""
    return [
        rule
        for rule in vocabulary.rules
        if _TARGET_PSEUDO not in rule.selector
        and rule.names_current
        and any(_matches(rule, node) for node in marked)
    ]


# ===========================================================================
# Requirement: A launch's detail page offers the way back to the list
# ===========================================================================


def test_the_list_is_reachable_from_a_launchs_detail_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The list is reachable from a launch's detail page.

    WHEN a launch's detail page is rendered
    THEN it offers the launch list in one action, without scripting.

    "In one action" is read as a single plain anchor a reader can
    follow; "without scripting" as that anchor needing no script to do
    it, so an `hx-get` or an `onclick` standing in for an `href` does
    not satisfy it. The destination carries no query, which is the
    requirement's own further clause: the offer reaches the list "as the
    list renders with no narrowing and nothing revealed", deliberately
    rather than carrying the reader's narrowing back.
    """
    world = _world(monkeypatch)

    root = _tree(_detail_html(world))
    offers = [
        link
        for link in _links_to(root, _list_path(world))
        if not _inherited(link, _element_disabled)
        and not _inherited(link, _element_hidden)
    ]

    # SPECIFIED: the page offers the list at all. Nothing obliged this
    # before — the header renders the launch surface as a position
    # rather than a link, because the list *is* that surface.
    assert offers, (
        f"the detail page offers no way to {_list_path(world)!r} with no "
        "query, so a reader who arrived from the list cannot return to it: "
        "the page's anchors go to "
        f"{sorted({e.attrs.get('href', '') for e in _elements(root) if e.tag == 'a'})}"
    )
    # SPECIFIED: in one action, without scripting.
    plain = [
        link
        for link in offers
        if not any(attribute in link.attrs for attribute in _SCRIPTING_ATTRIBUTES)
    ]
    assert plain, (
        "every offer of the list needs scripting to follow "
        f"({[link.attrs for link in offers]}), so the page does not offer it "
        "in one action without scripting"
    )


# ===========================================================================
# Requirement: The gate a reader navigated to is distinct from the gate
# the launch stands at
# ===========================================================================


def test_the_stylesheet_distinguishes_the_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The stylesheet distinguishes the two.

    WHEN the served stylesheet is read
    THEN it carries a rule that applies to the gate group a reader has
    navigated to
    AND that rule is distinct from the one marking the gate the launch
    stands at.

    The scenario is stated over the sheet because no response can carry
    which entry was followed. "Distinct" is read here in two strengths,
    labelled apart below: first that the two do not share one
    declaration block — a selector group pairing them gives both states
    one treatment, which is how this requirement is most plausibly
    satisfied on paper and defeated in fact — and second, more weakly,
    that where both reach a gate *group* their declarations differ.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    html = _detail_html(world)
    groups = [_gate_group(html, gate) for gate in GATES_WITH_STEPS]
    anchors = _anchor_targets(html)
    # DERIVED guard: the entries really are anchors into the page, which
    # is the premise the requirement's whole argument rests on. Without
    # a target to navigate to, a `:target` rule could never apply and
    # the assertion below would be about nothing.
    assert anchors, (
        "no gate-sequence entry navigates to an element on the page, so "
        "nothing can be 'the gate a reader navigated to' — correct "
        "`_anchor_targets` if the sequence links some other way"
    )
    reachable = [node for group in groups for node in _within(group)] + anchors

    navigated = _navigated_rules(vocabulary, reachable)
    # SPECIFIED: the sheet carries a rule applying to the navigated-to
    # gate group.
    assert navigated, (
        "the served stylesheet carries no rule reaching the gate group a "
        "reader has navigated to, so following an entry moves the page "
        "without saying so, and the mark on the current gate keeps reading "
        "as 'the entry you selected'. The sheet's selectors using "
        f"{_TARGET_PSEUDO!r} are "
        f"{[rule.selector for rule in vocabulary.rules if _TARGET_PSEUDO in rule.selector]}"
    )

    marked = [
        node
        for region in (_gate_sequence(html), *groups)
        for node in _within(region)
        if _marked_current(node)
    ]
    # DERIVED guard: the page marks the gate the launch stands at, and
    # the sheet carries a rule for that mark. Without both, "distinct
    # from" has nothing to be distinct from and this test would pass
    # while observing half of what it claims.
    assert marked, (
        "no element of the gate sequence or of a gate group is marked as the "
        "launch's position, so there is no current-gate mark for the "
        "navigated-to rule to be distinct from — correct `_CURRENT_CLASSES` "
        "or `_CURRENT_ATTRIBUTES`"
    )
    current = _current_rules(vocabulary, marked)
    assert current, (
        "the served stylesheet carries no rule marking the gate the launch "
        "stands at, so the two states are already indistinguishable for a "
        "reason this scenario does not name"
    )

    shared = [
        (rule.selector, other.selector)
        for rule in navigated
        for other in current
        if rule.block == other.block
    ]
    # SPECIFIED: the navigated-to rule is distinct from the one marking
    # the gate the launch stands at.
    assert not shared, (
        "the navigated-to gate and the gate the launch stands at share one "
        f"declaration block, so they receive one treatment: {shared}. Two "
        "selectors in one group are one rule, and the requirement asks for two"
    )
    # DERIVED, and weaker: where a current-gate rule reaches a gate group
    # — the same element the navigated-to rule reaches — the two saying
    # exactly the same thing would leave them indistinguishable by
    # another route. Rules marking a *sequence entry* are excluded from
    # this comparison, since the two never render on one element.
    at_group = [
        rule for rule in current if any(_matches(rule, group) for group in groups)
    ]
    identical = [
        (rule.selector, other.selector)
        for rule in navigated
        for other in at_group
        if rule.settled and rule.settled == other.settled
    ]
    assert not identical, (
        "a navigated-to rule and a current-gate rule reach the same gate "
        f"group and declare exactly the same thing: {identical}"
    )
