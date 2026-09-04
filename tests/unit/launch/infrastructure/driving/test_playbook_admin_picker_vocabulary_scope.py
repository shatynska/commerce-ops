"""What the two multi-valued controls' styles may reach (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/pick-steps-and-people-by-checkbox/specs/playbook-admin/spec.md`
— the scoping clause of the MODIFIED requirement *The step form carries
every authorable field*:

    No rule introduced for either of these controls, or for the
    filtering of the dependency control's options, SHALL render on an
    element another admin surface renders — save for a rule whose
    declarations are custom properties only […]. None SHALL select
    `gate` or `empty` unqualified.

Stated in prose and in no scenario of its own, and the requirement is
explicit that it is to be "arranged rather than left to be caught by
inspection"; `tasks.md` 5.5 turns that into this file. Every other
obligation of both requirements is covered in
`test_playbook_admin_multi_value_controls.py` and
`test_playbook_admin_dependency_option_filtering.py` in this directory,
and accounted for in the manifest at
`openspec/changes/pick-steps-and-people-by-checkbox/test-manifest.md`.

## Level

The playbook-admin router mounted beside the membership, launch and product
routers and the shared asset router, the way `main.py` composes them,
over doubles for every store. That is the smallest unit that can observe
this obligation: it is stated about the **served stylesheet**, which no
playbook route serves, and about whether a selector reaches an element
rendered by *another* surface — which cannot be seen from an app holding
only the step form. Same composition as
`test_launch_surface_vocabulary_rules.py`, which established this reading
for `launch-admin`'s own version of the rule; reproduced here rather than
imported per this project's self-contained-test-file convention.

## Reading a stylesheet in a test

The sheet the guarded asset route serves is parsed and its selectors
matched against the element trees the pages render. The parser and the
matcher are reproduced from `test_launch_surface_vocabulary_rules.py` and
support the selector subset an admin stylesheet uses: type, class, id and
attribute compounds, the four combinators, selector groups, and
`@media`/`@supports`/`@layer` nesting. Anything they cannot parse is
collected in `_Vocabulary.unparsed` and **fails the test that reads it**
rather than being silently skipped.

## What "a rule this change adds" is taken to mean

A test cannot read a diff, so the scope is operationalised, and the
reading is recorded here because it decides what this file can and
cannot catch. A rule is in scope when it matches an element inside one
of this change's own regions — a `chosen-set` region, a control marked
`option-filter` or `option-gate-filter`, the `hidden-chosen-notice`
region, or either control's option list — **and** either mentions a
class token those regions render that no sibling surface renders, or is
a bare unqualified selector on `gate` or `empty`.

Its blind spot is a newly added rule keyed only on a token the siblings
render too. `tasks.md` 5.2 carries that by inspection; this file is what
5.5 asks for and no more.

The requirement's own exemption is honoured: a rule whose declarations
are custom properties only changes nothing on a surface that never reads
them, and is skipped. Correction point: `_custom_properties_only`.

## Expected first-run state

**The change is not implemented.** No page renders `chosen-set`,
`option-filter`, `option-gate-filter` or `hidden-chosen-notice`, so:

- `test_no_rule_this_change_adds_renders_on_another_admin_surface` is
  expected to fail on the **absent region** — the state that establishes
  the regions do not exist and nothing about the assertion beyond it. It
  becomes readable the moment the controls render.
- `test_gate_and_empty_are_never_selected_unqualified` is expected to
  **pass**, and is recorded in the manifest as a regression guard rather
  than as coverage: the sheet carries no such selector today, and this
  is what would catch the picker's styles adding one. `gate` is already
  a class name several admin surfaces render, and `empty` another.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1660 passed, 0 failed — at the worktree root
on 2026-08-29, commit `81e042a`, tree clean but for an untracked
`.claude/worktrees/`.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import members_admin as members_module
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_module,
)
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as product_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import ALICE, ALICE_NAME, MARKETPLACE
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import classes as _classes
from tests.support.html import elements as _elements
from tests.support.html import tree as _tree
from tests.support.playbook import gates as _gates

_LAUNCH_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

#: SPECIFIED. The vocabulary asset the admin surfaces take their
#: presentation from (`admin-presentation-vocabulary`).
VOCABULARY_ASSET: Final = "vocabulary.css"

#: SPECIFIED markers, given literally by this change's delta.
CHOSEN_SET: Final = "chosen-set"
OPTION_FILTER: Final = "option-filter"
OPTION_GATE_FILTER: Final = "option-gate-filter"
HIDDEN_CHOSEN_NOTICE: Final = "hidden-chosen-notice"

#: SPECIFIED. The two class names the delta forbids being selected
#: unqualified, each already rendered by another admin surface.
REUSED_NAMES: Final = ("gate", "empty")

ASSIGNEES: Final = "assignees"
AFTER_STEPS: Final = "after_steps"

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")
PRINCIPAL: Final = "U01ALICE"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)

EDITED: Final = "listing.the-step-being-edited"
EDITED_NAME: Final = "Work the author is editing"
COMMIT_OPTION: Final = "listing.commitment-agreed"
TITLE_OPTION: Final = "listing.title-conforms"
LIVE_OPTION: Final = "inventory.units-received"

STEP_NAMES: Final[dict[str, str]] = {
    EDITED: EDITED_NAME,
    COMMIT_OPTION: "Commitment to launch is agreed",
    TITLE_OPTION: "Title conforms to marketplace policy",
    LIVE_OPTION: "Units are received into the warehouse",
}
STEP_GATES: Final[dict[str, str]] = {
    EDITED: "listable",
    COMMIT_OPTION: "commit",
    TITLE_OPTION: "listable",
    LIVE_OPTION: "live",
}

_CREATE_HINTS: Final = ("new", "create", "add")


def _module(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as absent:  # pragma: no cover - both ship today
        pytest.fail(
            f"{name} does not exist ({absent}) — the absent-target state, "
            "which establishes nothing about the assertions in this test"
        )


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": STEP_NAMES[identifier],
        "description": None,
        "gate": STEP_GATES[identifier],
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
        "starts_at_gate": None,
        "after_steps": (),
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


PLAYBOOK: Final = LaunchPlaybook(
    version="picker-scope-v1",
    gates=_gates(),
    steps=(
        _step(COMMIT_OPTION),
        _step(TITLE_OPTION),
        _step(EDITED, after_steps=(COMMIT_OPTION, TITLE_OPTION)),
        _step(LIVE_OPTION, discipline=INVENTORY),
    ),
)


class _Record:
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
    def __init__(self, records: tuple[_Record, ...], version: int = 41) -> None:
        self.records = records
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


def _seeded_steps() -> _FakeStepStore:
    return _FakeStepStore(
        tuple(
            _Record(step, display_order=(index + 1) * 10)
            for index, step in enumerate(PLAYBOOK.steps)
        )
    )


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _PlaybookMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member(ALICE, ALICE_NAME),)

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


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
        display_name=ALICE_NAME,
        slack_identity=PRINCIPAL,
        clickup_user_id=None,
        admin=True,
    )
    return store


def _members_store() -> _FakeMembersStore:
    return asyncio.run(_build_members())


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
    def get(self, version: str) -> LaunchPlaybook:
        return PLAYBOOK


class _Catalog:
    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)

    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
        return self.products

    async def get_product_by_id(self, *args: Any, **kwargs: Any) -> Product | None:
        wanted: Any = None
        for value in (*args, *kwargs.values()):
            if isinstance(value, ProductId):
                wanted = value.value
        if wanted is None:
            for value in (*args, *kwargs.values()):
                if isinstance(value, str) and value != PRINCIPAL:
                    wanted = value
        for product in self.products:
            if product.id.value == wanted:
                return product
        return None


class _FakeScopeResolution:
    async def __call__(self, *_args: Any, **_kwargs: Any) -> AccessScope:
        return AccessScope.unrestricted()


class _EmptyRead:
    async def __call__(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (), 1


def _product() -> Product:
    product = Product.register(
        sku=Sku("PX-100"),
        marketplace_id=MARKETPLACE,
        name="Alpha widget",
        registered_at=T_REGISTERED,
    )
    product.change_stage(Launching(phase=1), confirmed_by="Helen", at=T_REGISTERED)
    return product


# ---------------------------------------------------------------------------
# Installing the surfaces' seams — the single correction point
# ---------------------------------------------------------------------------

_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session", "verify"),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "members": ("members", "members_store", "read_members"),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
    "read_journal": ("read_journal", "journal", "journal_entries"),
}
_PLAYBOOK_MEMBERS_SEAMS: Final = (
    "members",
    "read_members",
    "members",
    "members_reader",
)
_PRODUCT_RETAINED_SEAMS: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)
_PRODUCT_STEPS_SEAMS: Final = (
    "steps",
    "playbook",
    "playbooks",
    "step_store",
    "playbook_store",
    "read_playbook",
    "served_playbook",
)
_CLOCK_NAMES: Final = ("today", "current_date", "now", "clock", "render_date")


def _install(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, seam: str, value: Any
) -> None:
    for name in _SEAMS[seam]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"{module.__name__} exposes no {seam!r} seam under any of "
        f"{_SEAMS[seam]} — correct `_SEAMS` to the implemented module"
    )


def _install_any(
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


_fake_verify = fake_verify(PRINCIPAL)


class _StubDate(date):
    _today: date = RENDER_DATE

    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return cls._today


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
        f"{module.__name__} exposes no seam for the day it renders on — "
        "correct `_render_on` to the implemented module"
    )


# ---------------------------------------------------------------------------
# The world: the step form, its five sibling surfaces and the asset route
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    client: TestClient
    launch_module: ModuleType
    product: Product


def _world(monkeypatch: pytest.MonkeyPatch) -> _World:
    product = _product()
    catalog = _Catalog(product)
    launch, _ = Launch.start(
        product_id=product.id, playbook=PLAYBOOK, launch_date=LAUNCH_DATE
    )
    launch_module = _module(_LAUNCH_MODULE_NAME)
    assets = _module(_ASSETS_MODULE_NAME)

    _install(monkeypatch, launch_module, "verify", _fake_verify)
    _install(monkeypatch, launch_module, "launches", _FakeLaunchStore(launch))
    _install(monkeypatch, launch_module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, launch_module, "members", _members_store())
    _install(monkeypatch, launch_module, "list_products", catalog.list_products)
    _install(monkeypatch, launch_module, "get_product_by_id", catalog.get_product_by_id)
    _install(monkeypatch, launch_module, "read_journal", _EmptyRead())
    _render_on(monkeypatch, launch_module, RENDER_DATE)

    monkeypatch.setattr(playbook_module, "steps", _seeded_steps())
    monkeypatch.setattr(playbook_module, "verify_admin_session", _fake_verify)
    _install_any(
        monkeypatch,
        playbook_module,
        _PLAYBOOK_MEMBERS_SEAMS,
        _PlaybookMembers(),
        "members",
    )

    # The Team list reads the role collection for a member's roles column.
    # `main.py` binds the real Postgres store to this module at import and
    # that outlives the test that imported it, so it is pinned here to a
    # store this test controls. `None` renders the column empty, which is
    # right for a test that asserts nothing about roles.
    monkeypatch.setattr(members_module, "roles", None, raising=False)
    monkeypatch.setattr(members_module, "members", _members_store())
    monkeypatch.setattr(members_module, "verify_admin_session", _fake_verify)

    _install(monkeypatch, product_module, "verify", _fake_verify)
    _install(monkeypatch, product_module, "list_products", catalog.list_products)
    _install(
        monkeypatch, product_module, "get_product_by_id", catalog.get_product_by_id
    )
    _install_any(
        monkeypatch,
        product_module,
        ("resolve_scope",),
        _FakeScopeResolution(),
        "scope-resolution",
    )
    _install_any(
        monkeypatch,
        product_module,
        _PRODUCT_RETAINED_SEAMS,
        _EmptyRead(),
        "retained-results read",
    )
    _install_any(
        monkeypatch,
        product_module,
        _PRODUCT_STEPS_SEAMS,
        _EmptyRead(),
        "served-playbook",
    )
    monkeypatch.setattr(assets, "verify", _fake_verify)

    app = FastAPI()
    app.include_router(playbook_module.router)
    app.include_router(launch_module.router)
    app.include_router(members_module.router)
    app.include_router(product_module.router)
    app.include_router(assets.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _World(client, launch_module, product)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _shortest_get_route(router: Any) -> str:
    candidates = [
        str(route.path)
        for route in router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" not in str(route.path)
    ]
    assert candidates, f"{router!r} exposes no parameterless GET route"
    return min(candidates, key=len)


def _parameterised_get_route(router: Any) -> str:
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
        f"parameter and not mentioning 'journal': {candidates}"
    )
    return candidates[0]


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


def _step_list(world: _World) -> str:
    return _fetch(world, _shortest_get_route(playbook_module.router))


def _edit_surface(world: _World) -> str:
    page = _step_list(world)
    for _, url in _links(page):
        if url.rstrip("/").endswith("/edit") and EDITED in url:
            return _fetch(world, url)
    pytest.fail(
        f"no edit affordance for {EDITED!r} was discoverable — correct this "
        "file's control vocabulary to the implemented page"
    )


def _create_surface(world: _World) -> str:
    page = _step_list(world)
    for _, url in _links(page):
        if url.startswith(("#", "http://", "https://", "mailto:")):
            continue
        if not any(hint in url.lower() for hint in _CREATE_HINTS):
            continue
        response = world.client.get(url)
        if response.status_code == 200 and _forms(str(response.text)):
            return str(response.text)
    pytest.fail(
        "no control on the list led to a create surface — correct "
        "`_CREATE_HINTS` to the implemented page"
    )


def _sibling_pages(world: _World) -> dict[str, str]:
    """The surfaces this change's rules may not reach: the step list, the
    Team page, the launch list, the launch detail, the product index
    and the product dossier."""
    launch_router = world.launch_module.router
    return {
        "step list": _step_list(world),
        "Team page": _fetch(world, _shortest_get_route(members_module.router)),
        "launch list": _fetch(world, _shortest_get_route(launch_router)),
        "launch detail": _fetch(
            world,
            _fill(_parameterised_get_route(launch_router), world.product.id.value),
        ),
        "product index": _fetch(world, _shortest_get_route(product_module.router)),
        "product dossier": _fetch(
            world,
            _fill(
                _parameterised_get_route(product_module.router),
                world.product.id.value,
            ),
        ),
    }


def _vocabulary(world: _World) -> str:
    template = _parameterised_get_route(_module(_ASSETS_MODULE_NAME).router)
    return _fetch(world, _fill(template, VOCABULARY_ASSET))


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


def _carries(node: _Node, marker: str) -> bool:
    if marker in _classes(node):
        return True
    if node.attrs.get("id") == marker:
        return True
    return any(
        key.startswith("data-") and marker in value.split()
        for key, value in node.attrs.items()
    )


def _marked(root: _Node, marker: str) -> list[_Node]:
    return [element for element in _elements(root) if _carries(element, marker)]


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None:
        yield walker
        walker = walker.parent


def _siblings(node: _Node) -> list[_Node]:
    parent = node.parent
    if parent is None:
        return [node]
    return [child for child in parent.children if isinstance(child, _Node)]


def _within(node: _Node, container: _Node) -> bool:
    return node is container or any(walker is container for walker in _ancestors(node))


def _common_ancestor(nodes: list[_Node]) -> _Node:
    chains = [[*reversed([node, *_ancestors(node)])] for node in nodes]
    shared = chains[0]
    for chain in chains[1:]:
        keep: list[_Node] = []
        for left, right in zip(shared, chain, strict=False):
            if left is not right:
                break
            keep.append(left)
        shared = keep
    assert shared, "the nodes share no ancestor, which a parsed document forbids"
    return shared[-1]


def _links(html: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for element in _elements(_tree(html)):
        for verb in _HX_VERBS:
            if verb in element.attrs:
                found.append((verb.removeprefix("hx-"), element.attrs[verb]))
        if element.tag == "a" and element.attrs.get("href"):
            found.append(("get", element.attrs["href"]))
    return found


def _forms(html: str) -> list[_Node]:
    return [element for element in _elements(_tree(html)) if element.tag == "form"]


# ---------------------------------------------------------------------------
# This change's own regions
# ---------------------------------------------------------------------------


def _picker_of(root: _Node, name: str) -> _Node | None:
    """The element holding one control's option rows — the labels bound
    to that field's per-value controls."""
    controls = [
        element
        for element in _elements(root)
        if element.tag == "input"
        and element.attrs.get("name") == name
        and (element.attrs.get("type") or "text").lower() == "checkbox"
    ]
    labels = [element for element in _elements(root) if element.tag == "label"]
    regions = _marked(root, CHOSEN_SET)
    rows: list[_Node] = []
    for control in controls:
        identifier = control.attrs.get("id", "")
        for label in labels:
            bound = (identifier and label.attrs.get("for") == identifier) or _within(
                control, label
            )
            if bound and not any(_within(label, region) for region in regions):
                rows.append(label)
                break
    return _common_ancestor(rows) if rows else None


def _own_regions(html: str) -> list[_Node]:
    """Everything this change draws, on one surface."""
    root = _tree(html)
    regions = [
        *_marked(root, CHOSEN_SET),
        *_marked(root, OPTION_FILTER),
        *_marked(root, OPTION_GATE_FILTER),
        *_marked(root, HIDDEN_CHOSEN_NOTICE),
    ]
    for name in (ASSIGNEES, AFTER_STEPS):
        picker = _picker_of(root, name)
        if picker is not None:
            regions.append(picker)
    return regions


def _within_own_regions(html: str) -> list[_Node]:
    return [
        node for region in _own_regions(html) for node in (region, *_elements(region))
    ]


def _tokens_of(pages: dict[str, str]) -> set[str]:
    return {
        name
        for html in pages.values()
        for element in _elements(_tree(html))
        for name in _classes(element)
    }


# ===========================================================================
# MODIFIED Requirement: The step form carries every authorable field
# — its scoping clause (`tasks.md` 5.5)
# ===========================================================================


def test_no_rule_this_change_adds_renders_on_another_admin_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "No rule introduced for either of these
    controls, or for the filtering of the dependency control's options,
    SHALL render on an element another admin surface renders — save for
    a rule whose declarations are custom properties only."

    One stylesheet serves every admin surface, and `gate` is already a
    class name several of them use, so this is arranged rather than left
    to be caught by inspection. "A rule this change adds" is
    operationalised — see this file's docstring for the reading and its
    blind spot.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    surfaces = {
        "the edit surface": _edit_surface(world),
        "the create surface": _create_surface(world),
    }
    inside: list[_Node] = []
    for what, html in surfaces.items():
        regions = _within_own_regions(html)
        # The absent-target guard: with the controls undrawn there is
        # nothing for a rule to be scoped to, and a silent pass here
        # would read as the scoping having been arranged.
        assert regions, (
            f"{what} renders none of this change's regions — no "
            f"{CHOSEN_SET!r}, {OPTION_FILTER!r}, {OPTION_GATE_FILTER!r} or "
            f"{HIDDEN_CHOSEN_NOTICE!r}, and no per-value control to find an "
            "option list by — so nothing here establishes that the rules are "
            "scoped"
        )
        inside.extend(regions)

    siblings = _sibling_pages(world)
    own_tokens = {name for node in inside for name in _classes(node)} - _tokens_of(
        siblings
    )
    # DERIVED guard: the controls really render markers of their own, or
    # the filter below selects nothing and this test is vacuous.
    assert own_tokens, (
        "this change's regions render no class the six sibling surfaces do "
        "not, so no rule could be attributed to it at all"
    )

    sibling_elements = [
        (name, element)
        for name, html in siblings.items()
        for element in _elements(_tree(html))
    ]

    for rule in vocabulary.rules:
        if _custom_properties_only(rule):
            continue
        if not any(_matches(rule, node) for node in inside):
            continue
        bare_reused = (
            len(rule.parts) == 1
            and not rule.parts[0][1].qualified
            and rule.parts[0][1].classes
            and set(rule.parts[0][1].classes) <= set(REUSED_NAMES)
        )
        if not (rule.classes & own_tokens) and not bare_reused:
            continue
        reached = [
            (name, element)
            for name, element in sibling_elements
            if _matches(rule, element)
        ]
        # SPECIFIED: no such rule renders on an element another admin
        # surface renders.
        assert not reached, (
            f"the selector {rule.selector!r} reaches this change's own "
            f"regions and also matches {len(reached)} element(s) on "
            f"{sorted({name for name, _ in reached})} — for instance a "
            f"<{reached[0][1].tag}> carrying {sorted(_classes(reached[0][1]))}"
        )


def test_gate_and_empty_are_never_selected_unqualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "None SHALL select `gate` or `empty`
    unqualified — both are class names another admin surface already
    renders."

    Read over **every** selector in the sheet rather than only over the
    ones this change adds — a strictly stronger reading, and safe
    because the sheet carries no such selector today. "Unqualified" is
    the literal reading `launch-admin`'s own version of this rule
    established: one compound holding exactly that class and nothing else
    — no tag, no second class, no id, no attribute, no pseudo, and no
    ancestor context. `.picker .gate` and `li.empty` are both qualified
    and both allowed.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    offenders = [
        rule
        for rule in vocabulary.rules
        if not _custom_properties_only(rule)
        and len(rule.parts) == 1
        and not rule.parts[0][1].qualified
        and rule.parts[0][1].classes
        and set(rule.parts[0][1].classes) <= set(REUSED_NAMES)
    ]

    # SPECIFIED: neither reused name is selected unqualified.
    assert not offenders, (
        "the served stylesheet selects a reused class name unqualified: "
        f"{[rule.selector for rule in offenders]}. One stylesheet serves "
        "every admin surface, and an unqualified rule on either name "
        "restyles the launch list's gate cell and the detail page's gate "
        "sequence"
    )


# ---------------------------------------------------------------------------
# The served stylesheet: parsing and matching
#
# Reproduced from `test_launch_surface_vocabulary_rules.py`, which
# established this reading for `launch-admin`'s own scoping requirement.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Compound:
    tag: str | None
    classes: frozenset[str]
    identifier: str | None
    attributes: tuple[tuple[str, str, str], ...]
    pseudo_classes: tuple[str, ...]
    pseudo_elements: tuple[str, ...]

    @property
    def qualified(self) -> bool:
        return bool(
            self.tag
            or self.identifier
            or self.attributes
            or self.pseudo_classes
            or self.pseudo_elements
            or len(self.classes) > 1
        )


@dataclass(frozen=True)
class _Rule:
    selector: str
    declarations: str
    parts: tuple[tuple[str, _Compound], ...]

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(
            name for _, compound in self.parts for name in compound.classes
        )


@dataclass(frozen=True)
class _Vocabulary:
    rules: tuple[_Rule, ...]
    unparsed: tuple[str, ...]


def _custom_properties_only(rule: _Rule) -> bool:
    """The requirement's own exemption: a rule whose declarations are
    custom properties only changes nothing on a surface that never reads
    them."""
    declarations = [
        part.strip() for part in rule.declarations.split(";") if part.strip()
    ]
    return bool(declarations) and all(part.startswith("--") for part in declarations)


_NESTING_AT_RULES: Final = ("@media", "@supports", "@layer", "@container", "@scope")


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


def _parse_rules(css: str, unparsed: list[str]) -> list[_Rule]:
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
                if prelude.split(None, 1)[0].lower() in _NESTING_AT_RULES:
                    rules.extend(_parse_rules(body, unparsed))
            else:
                for selector in _split_group(prelude):
                    parts = _parse_complex(selector)
                    if parts is None:
                        unparsed.append(selector)
                        continue
                    rules.append(_Rule(selector, body, parts))
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
    rules = _parse_rules(_strip_comments(css), unparsed)
    return _Vocabulary(tuple(rules), tuple(unparsed))


def _readable(vocabulary: _Vocabulary) -> None:
    assert not vocabulary.unparsed, (
        f"{len(vocabulary.unparsed)} selector(s) in the served stylesheet "
        f"could not be read: {list(vocabulary.unparsed)} — a selector this "
        "matcher cannot parse is one this obligation cannot be read against"
    )
    assert vocabulary.rules, "the served stylesheet carries no rule at all"
