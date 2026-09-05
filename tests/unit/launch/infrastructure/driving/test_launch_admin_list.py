"""The launches list at `/admin/launches` (`launch-admin`).

Derived strictly from the delta spec
`openspec/changes/add-launch-tracking-pages/specs/launch-admin/spec.md` —
three ADDED requirements and all 28 of their scenarios:

- *The launch list enumerates every launch and renders those in play*
  (16 scenarios)
- *The list is ordered by attention, deterministically* (7 scenarios)
- *Narrowing the list changes what is shown, never what is enumerated*
  (5 scenarios)

The detail page's requirements, the read-only guarantee, the session and
header requirement and the presentation requirement live in
`test_launch_admin_detail.py` in this directory. The manifest at
`openspec/changes/add-launch-tracking-pages/test-manifest.md` records
every scenario, every assertion's classification and every unresolved
project question answered here by assumption.

## Level

The list router mounted in an app of its own, over fakes for the stores
and the catalog read. That is the smallest unit that can observe any of
these scenarios: every one of them is stated about what the *page*
renders — which rows, in what order, marked how — and `design.md`
Decision 3 is explicit that the defect the scope requirement guards
against is "an adapter that supplies its own scope", which no use-case
test can see. Same composition as
`tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`,
whose harness shapes this one; duplicated rather than imported, since
this project shares no test-helper module between test files and
`tests/**/test_*.py` is the only path a test may be written to here.

## Expected first-run state

**Absent target.** `commerce_ops.launch.infrastructure.driving.launch_admin`
does not exist, so every test here is expected to fail — resolved by
name through `_page_module()` so that each scenario fails on its own
with a readable message rather than the whole file failing to collect,
which would establish nothing about any single assertion. Per
`ai-toolkit:testing`, an absent-target failure establishes absence and
nothing about whether these assertions are any good.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1133 passed, 0
failed, 94 skipped (the whole integration tier, no database configured)
on 2026-08-27.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The module path `launch/infrastructure/driving/launch_admin.py` and
  the route `/admin/launches` (`proposal.md` — What Changes, Impact).
- That the scope is resolved for the session's own principal identity
  and never supplied by the surface (delta R1; `design.md` Decision 3;
  `tasks.md` 3.2).
- That the at-risk and awaits-confirmation states are evaluated as of
  the render date (delta R1; `tasks.md` 3.3).
- That each rendered row names the product, the current gate, the launch
  date **or the absence of one**, the at-risk state and the
  awaits-confirmation state, and offers the detail page in one action
  without scripting and independently of narrowing or row count.
- The default-view filter, its predicate (`briefing`'s: the catalog
  stage is steady-state or retired), the fail-toward-showing rule for an
  unresolvable product, the reveal control, the two distinguishable
  marks, the four empty states and which governs.
- The band order, the single appearance, the within-band key (launch
  date ascending, undated last, product identifier breaking ties), the
  revealed rows' key (most recent first, undated last, identifier
  breaking ties) and that no ordering may depend on arrival order.
- That narrowing is by gate and by needs-attention, changes only what is
  rendered, reaches the revealed rows within themselves, preserves
  relative order, and says so when it matches nothing.

INVENTED, each with its correction point named in the code:

- Every module seam: which attribute the adapter exposes for the launch
  store, the playbook port, the membership, the session guard, the scope
  resolver and the two catalog reads. `_SEAMS` and `_install` are the
  single correction point, and they fail loudly.
- How the render date is injected (`_render_on`): either a module-level
  clock callable, or the module's own `date` name, whichever is present.
  A page with neither is not testable across two dates, and that is
  reported as a finding rather than worked around.
- How a row is located: the smallest element holding exactly one
  launch's detail link (`_rows`). R1 guarantees every rendered row
  offers that link, so this is the one structural fact the spec fixes.
- The **wording** of every mark — at risk, awaiting confirmation, no
  launch date, no longer in play, steady state versus retired, the empty
  states, the offer to clear a narrowing. The delta fixes that each is
  *stated*, never how. `_WORDS` is the single correction point.
- How each narrowing and the reveal control are driven: discovered from
  the rendered page first, with an invented query parameter as fallback,
  the pattern `test_playbook_admin_page.py` already records for the
  retired-step reveal.
- The launch dates, gates and evaluation dates. No artifact fixes any;
  they are chosen so each judgement is unambiguous, and written as
  literals rather than recomputed.

Correcting a seam, a wording constant or a control probe is a fixture
correction (failure state 3 in `ai-toolkit:testing`). What must survive
unweakened is what each test asserts: which rows are rendered, in what
order, carrying which facts, and what the page says when it renders
none.
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Launching,
    Posture,
    Retired,
    SteadyState,
)
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fakes import FakeMembersStore as _FakeMembersStore
from tests.support.fakes import FakePlaybooks, StubDate
from tests.support.fixtures import MARKETPLACE
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import all_text as _all_text
from tests.support.html import ancestors as _ancestors
from tests.support.html import element_disabled as _element_disabled
from tests.support.html import element_hidden as _element_hidden
from tests.support.html import elements as _elements
from tests.support.html import flat as _flat
from tests.support.html import inherited as _inherited
from tests.support.html import size as _size
from tests.support.html import texts as _texts
from tests.support.html import tree as _tree
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

# ---------------------------------------------------------------------------
# The module under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    """The launch-admin driving module, or a loud per-test failure.

    Resolved by name rather than imported at module scope so that its
    absence fails each scenario on its own terms instead of collapsing
    the whole file into one collection error.
    """
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so no launch "
            "list is served — this is the absent-target state, and it "
            "establishes nothing about the assertions in this test"
        )


# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

A_DISCIPLINE: Final = Discipline("listing")
#: The session principal the guard hands the page, and the Slack identity
#: the seeded membership carries for it, so the real `resolve_scope` runs.
PRINCIPAL: Final = "U01ALICE"
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

#: The day the page is rendered in every test that does not say otherwise.
RENDER_DATE: Final = date(2027, 4, 1)

#: A launch date whose -30-day step is already fully past on RENDER_DATE
#: (the step falls on 2027-03-16), and a second one, later in the month,
#: for within-band ordering.
AT_RISK_DATE: Final = date(2027, 4, 15)
LATER_AT_RISK_DATE: Final = date(2027, 4, 20)
#: Launch dates whose -30-day step is comfortably in the future.
HEALTHY_DATE: Final = date(2027, 12, 1)
LATER_HEALTHY_DATE: Final = date(2028, 1, 15)
#: Dates for launches that have left play; both are in the past.
FINISHED_EARLIER: Final = date(2027, 1, 10)
FINISHED_LATER: Final = date(2027, 2, 20)

#: The blocking step whose due period decides the at-risk judgement. At
#: `graduated`, so it never holds the gate a fixture launch stands at.
RISK_STEP: Final = "strategy.launch-readiness"

#: INVENTED wording. The delta fixes that each fact is *stated*, never
#: how. Correction point for a page that words them differently.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "at_risk": ("at risk", "at-risk", "date at risk"),
    # The bare word "risk" is deliberately not here: this file's own
    # fixtures name a product "Risky widget", so it matched the label
    # rather than the mark and made the rendering unfalsifiable.
    "awaiting": (
        "awaiting confirmation",
        "awaits confirmation",
        "awaiting approval",
        "needs confirmation",
        "confirmation",
    ),
    "no_date": (
        "no launch date",
        "no date",
        "undated",
        "not scheduled",
        "date not set",
        "—",
        "not set",
        "none",
    ),
    "steady": (
        "steady state",
        "steady-state",
        "steady",
        "graduated",
        "in market",
        "finished",
        "completed",
    ),
    "retired": ("retired", "abandoned", "withdrawn"),
    "no_launches": (
        "no product is in launch",
        "no launches",
        "nothing is in launch",
        "no launch",
    ),
    "none_in_play": (
        "no launch is in play",
        "none in play",
        "nothing in play",
        "no launch in play",
    ),
    "none_out_of_play": (
        "none are out of play",
        "no launch is out of play",
        "nothing is out of play",
        "every launch is in play",
    ),
    "matched_nothing": (
        "matched nothing",
        "no launch matches",
        "nothing matches",
        "no match",
        "no results",
        "matches no",
    ),
    "clear": ("clear", "reset", "remove the filter", "show all", "clear filter"),
    "reveal": (
        "no longer in play",
        "out of play",
        "finished",
        "completed",
        "past launches",
        "retired",
        "steady",
        "show all",
        "archive",
    ),
    "attention": ("attention", "needs attention", "needing attention"),
}

#: Fallback query parameters, tried in order when no control on the page
#: can be discovered. INVENTED; the page is expected to carry a control.
_REVEAL_PARAMS: Final = (
    {"revealed": "1"},
    {"out_of_play": "1"},
    {"finished": "1"},
    {"show": "all"},
    {"include": "finished"},
    {"all": "1"},
)
_ATTENTION_PARAMS: Final = (
    {"attention": "1"},
    {"needs_attention": "1"},
    {"needing": "attention"},
    {"filter": "attention"},
)
_GATE_PARAM_NAMES: Final = ("gate", "current_gate", "at")


# ---------------------------------------------------------------------------
# Domain builders — the shapes `test_launch_reports.py` records
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "gate": "live",
            "discipline": A_DISCIPLINE,
            "timing_anchor": OffsetAnchor(days=-30),
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, anchored a year after launch so
    it can never be the overdue step an at-risk judgement is about."""
    return _build_hold(
        gate,
        discipline=A_DISCIPLINE,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook() -> LaunchPlaybook:
    """One playbook every fixture launch pins.

    It carries a single blocking step at `graduated` anchored 30 days
    before launch: whether that step is overdue as of the render date is
    what decides each launch's at-risk state, so the launch date alone
    distinguishes an at-risk launch from a healthy one.
    """
    unordered = (
        _step(
            identifier=RISK_STEP,
            name="Launch readiness is signed off",
            gate="graduated",
            blocking=True,
            timing_anchor=OffsetAnchor(days=-30),
        ),
        *tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate != "graduated"),
    )
    return _build_playbook(
        *(
            step
            for gate in SPECIFIED_GATE_ORDER
            for step in unordered
            if step.gate == gate
        ),
        filler=_hold,
        fillers_first=True,
    )


PLAYBOOK: Final = _playbook()


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who=APPROVER,
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver=APPROVER,
        when=APPROVED_AT,
        posture=None,
    )


def _satisfy_fillers(launch: Launch) -> None:
    for step in PLAYBOOK.steps_for_gate(launch.current_gate):
        if step.blocking and step.identifier.startswith("hold."):
            launch.record_step_outcome(
                PLAYBOOK,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _start(product_id: ProductId, launch_date: date | None) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=launch_date
    )
    return launch


def _advance_to(launch: Launch, gate: str) -> Launch:
    while launch.current_gate != gate:
        _satisfy_fillers(launch)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(PLAYBOOK)
    return launch


def _quiet(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    """Neither at risk nor awaiting confirmation: a healthy date, and the
    `commit` gate's blocking filler unresolved, so no human decision is
    due."""
    return _start(product_id, launch_date)


def _at_risk(product_id: ProductId, launch_date: date = AT_RISK_DATE) -> Launch:
    """At risk: the blocking `graduated` step's due period has fully
    passed by the render date, unresolved."""
    return _start(product_id, launch_date)


def _awaiting(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    """Awaiting confirmation: standing at `commit`, a confirmation gate,
    with every blocking condition attached to it satisfied and no
    approval recorded."""
    launch = _start(product_id, launch_date)
    _satisfy_fillers(launch)
    return launch


def _at_risk_and_awaiting(product_id: ProductId) -> Launch:
    launch = _start(product_id, AT_RISK_DATE)
    _satisfy_fillers(launch)
    return launch


# ---------------------------------------------------------------------------
# Catalog products
# ---------------------------------------------------------------------------


def _product(sku: str, name: str, stage: Any = None) -> Product:
    product = Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )
    product.change_stage(Launching(phase=1), confirmed_by=APPROVER, at=T_REGISTERED)
    if stage is not None:
        product.change_stage(stage, confirmed_by=APPROVER, at=T_REGISTERED)
    return product


def _launching(sku: str, name: str) -> Product:
    return _product(sku, name)


def _steady(sku: str, name: str) -> Product:
    return _product(sku, name, SteadyState(posture=Posture.OPTIMIZE))


def _retired(sku: str, name: str) -> Product:
    return _product(sku, name, Retired())


def _unresolvable_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class _FakeLaunchStore:
    """In-memory `LaunchStore`, answering to the enumeration spellings
    `test_launch_reports.py` records.

    `order` is the sequence the enumeration hands launches over in; it is
    a deliberate seam so that *Arrival order does not reach the page* can
    change it and nothing else.
    """

    def __init__(self, *launches: Launch) -> None:
        self.order: list[Launch] = list(launches)
        #: How many launches each enumeration handed over. The narrowing
        #: requirement is about what is *enumerated*, so this is where the
        #: "never what is enumerated" half is observed.
        self.enumerations: list[int] = []

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
        self.enumerations.append(len(self.order))
        return tuple(self.order)

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)

    async def list_launches(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)


class _FakePlaybooks(FakePlaybooks):
    """The shared store, adapted: this file's call sites rely on a default."""

    def __init__(self, playbook: LaunchPlaybook = PLAYBOOK) -> None:
        super().__init__(playbook)


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


class _Catalog:
    """Stands in for `catalog.application`'s two reads.

    `fails` makes the whole-catalog read raise, which is the outage
    *Product identities cannot be read at all* is about; a product absent
    from `products` is one the catalog cannot resolve.
    """

    def __init__(self, *products: Product, fails: bool = False) -> None:
        self.products = tuple(products)
        self.fails = fails
        self.list_calls = 0

    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
        self.list_calls += 1
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
        return self.products

    async def get_product_by_id(
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Product | None:
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
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
    "resolve_scope": ("resolve_scope",),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
}


def _install(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    seam: str,
    value: Any,
) -> None:
    for name in _SEAMS[seam]:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            return
    pytest.fail(
        f"{_PAGE_MODULE_NAME} exposes no {seam!r} seam under any of "
        f"{_SEAMS[seam]} — correct `_SEAMS` to the implemented module. Every "
        "collaborator this page reads through has to be replaceable, or its "
        "behaviour cannot be observed at all."
    )


_fake_verify = fake_verify(PRINCIPAL)


class _StubDate(StubDate):
    _today = RENDER_DATE


_CLOCK_NAMES: Final = ("today", "current_date", "now", "clock", "render_date")


def _render_on(monkeypatch: pytest.MonkeyPatch, module: ModuleType, day: date) -> None:
    """Fix the day the page renders on.

    INVENTED: either a module-level clock callable, or the module's own
    `date` name (the shape `from datetime import date` + `date.today()`
    produces). A module carrying neither cannot have its render-date
    behaviour observed at all, which is a finding rather than something
    to work around — so this fails loudly.
    """
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
        "`date`), so the requirement that the page evaluate as of the render "
        "date cannot be observed — correct `_render_on` to the implemented "
        "module"
    )


@dataclass(frozen=True)
class _Surface:
    client: TestClient
    launches: _FakeLaunchStore
    catalog: _Catalog
    module: ModuleType


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launches: _FakeLaunchStore,
    catalog: _Catalog,
    day: date = RENDER_DATE,
    scope: AccessScope | None = None,
) -> _Surface:
    """The list router mounted alone, over fakes.

    `scope` stubs **the scope resolver and nothing else** — the real
    enumeration stays behind it, per `design.md` Decision 3 and
    `tasks.md` 7.3. Left `None`, the real `resolve_scope` runs over a
    members seeded with the session principal.
    """
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)
    _render_on(monkeypatch, module, day)
    if scope is not None:

        async def _resolver(*_args: Any, **_kwargs: Any) -> AccessScope:
            return scope

        _install(monkeypatch, module, "resolve_scope", _resolver)

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, launches, catalog, module)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _list_path(module: ModuleType) -> str:
    candidates = [
        str(route.path)
        for route in module.router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" not in route.path
    ]
    assert candidates, f"{_PAGE_MODULE_NAME} exposes no parameterless GET route"
    return str(min(candidates, key=len))


def _detail_template(module: ModuleType) -> str:
    # A second parameterised GET route (the launch journal page
    # `add-admin-breadcrumb-navigation` adds) is excluded by name, so this
    # locator survives once that route exists alongside this one — the
    # same correction that route's own change made in its own test files.
    candidates = [
        str(route.path)
        for route in module.router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" in route.path
        and "journal" not in route.path.lower()
    ]
    assert len(candidates) == 1, (
        f"{_PAGE_MODULE_NAME} exposes {len(candidates)} parameterised GET "
        "routes not mentioning 'journal'; exactly one detail route is "
        "expected"
    )
    return str(candidates[0])


def _detail_path(module: ModuleType, product_id: ProductId) -> str:
    template = _detail_template(module)
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + product_id.value + template[closed + 1 :]


# ---------------------------------------------------------------------------
# An HTML tree (the parser `test_admin_surface_navigation_and_assets.py`
# records, duplicated per this project's no-shared-helper convention)
# ---------------------------------------------------------------------------


def _attribute_text(node: _Node) -> str:
    parts = [
        value
        for element in (node, *_elements(node))
        for key, value in element.attrs.items()
        if key in ("class", "title", "aria-label", "data-state", "data-mark")
        or key.startswith("data-")
    ]
    return " ".join(parts).lower()


def _says(subject: Any, key: str) -> bool:
    """Whether a node — or a row, for convenience — states `key`.

    Takes either because a scenario's THEN is sometimes about the page
    and sometimes about one row, and both are read the same way.
    """
    node = subject.node if hasattr(subject, "node") else subject
    haystack = f"{_all_text(node)} {_attribute_text(node)}"
    return any(word in haystack for word in _WORDS[key])


# ---------------------------------------------------------------------------
# Rows, read off a rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    product_id: str
    node: _Node
    link: _Node


def _detail_links(root: _Node, module: ModuleType) -> list[tuple[str, _Node]]:
    template = _detail_template(module)
    prefix = template[: template.index("{")]
    found: list[tuple[str, _Node]] = []
    for element in _elements(root):
        if element.tag != "a":
            continue
        href = element.attrs.get("href", "")
        path = urlsplit(href).path
        if not path.startswith(prefix) or path == prefix:
            continue
        remainder = path[len(prefix) :].strip("/")
        if remainder and "/" not in remainder:
            found.append((remainder, element))
    return found


def _rows(html: str, module: ModuleType) -> list[_Row]:
    """Every rendered row, in document order.

    INVENTED locator: a row is the smallest ancestor of a launch's detail
    link that holds that link and no other launch's. R1 guarantees every
    rendered row offers its detail page in one action, which is the one
    structural fact the delta fixes about a row.
    """
    root = _tree(html)
    links = _detail_links(root, module)
    rows: list[_Row] = []
    seen: set[str] = set()
    for product_id, link in links:
        if product_id in seen:
            continue
        seen.add(product_id)
        containers = [
            ancestor
            for ancestor in _ancestors(link)
            if ancestor.tag not in ("html", "body", "#document")
            and {other for other, _ in _detail_links(ancestor, module)} == {product_id}
        ]
        rows.append(
            _Row(product_id, min(containers, key=_size) if containers else link, link)
        )
    return rows


def _rendered_ids(html: str, module: ModuleType) -> list[str]:
    return [row.product_id for row in _rows(html, module)]


def _row_for(html: str, module: ModuleType, product_id: ProductId) -> _Row:
    for row in _rows(html, module):
        if row.product_id == product_id.value:
            return row
    pytest.fail(
        f"no row for {product_id} was rendered; the page rendered "
        f"{_rendered_ids(html, module)}"
    )


def _offers_in_one_action(row: _Row) -> bool:
    """A live anchor, which needs no scripting."""
    return (
        row.link.tag == "a"
        and bool(row.link.attrs.get("href"))
        and not _inherited(row.link, _element_disabled)
        and not _inherited(row.link, _element_hidden)
    )


def _mark_tokens(row: _Row, *identity: str) -> frozenset[str]:
    """The tokens a row carries that are not the launch's own identity.

    Used only where the fixture gives two launches identical names,
    gates and dates, so that what survives the subtraction is the mark
    itself. Every token that is part of the row's product identifier or
    SKU is dropped, since those differ per row by construction and would
    otherwise read as a mark.
    """
    known = tuple(part.lower() for part in (row.product_id, *identity))
    haystack = f"{_all_text(row.node)} {_attribute_text(row.node)}"
    return frozenset(
        token
        for token in haystack.replace("/", " ").replace("-", " ").split()
        if not any(token in part or part in token for part in known if part)
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Control:
    method: str
    url: str
    fields: tuple[tuple[str, str], ...] = ()
    inert: bool = False
    text: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.fields)

    @property
    def haystack(self) -> str:
        rendered = " ".join(f"{name}={value}" for name, value in self.fields)
        return f"{self.url} {rendered} {self.text}".lower()


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


def _form_of(node: _Node) -> tuple[str, str, dict[str, str]]:
    method = (node.attrs.get("method") or "get").lower()
    url = node.attrs.get("action", "")
    for verb in _HX_VERBS:
        if verb in node.attrs:
            method = verb.removeprefix("hx-")
            url = node.attrs[verb]
    fields: dict[str, str] = {}
    for element in _elements(node):
        name = element.attrs.get("name")
        if not name:
            continue
        if element.tag == "input":
            kind = (element.attrs.get("type") or "text").lower()
            if kind in ("submit", "image"):
                continue
            if kind in ("checkbox", "radio") and "checked" not in element.attrs:
                fields.setdefault(name, "")
                continue
            fields[name] = element.attrs.get(
                "value", "on" if kind == "checkbox" else ""
            )
        elif element.tag == "select":
            fields[name] = _selected_of(element)
        elif element.tag == "textarea":
            fields[name] = " ".join(_texts(element))
    return method, url, fields


def _controls(html: str) -> list[_Control]:
    found: list[_Control] = []
    for element in _elements(_tree(html)):
        disabled = _inherited(element, _element_disabled)
        if element.tag == "a":
            href = element.attrs.get("href", "")
            found.append(
                _Control(
                    "get", href, (), disabled or href in ("", "#"), _all_text(element)
                )
            )
        elif element.tag == "form":
            method, url, fields = _form_of(element)
            found.append(
                _Control(
                    method, url, tuple(fields.items()), disabled, _all_text(element)
                )
            )
    return found


def _resolve(module: ModuleType, url: str) -> str:
    if not url:
        return _list_path(module)
    if url.startswith("/"):
        return url
    return urljoin(_list_path(module) + "/", url)


def _with_query(url: str, extra: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(extra)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _issue(
    surface: _Surface, control: _Control, *, data: dict[str, str] | None = None
) -> Any:
    method = control.method.upper()
    target = _resolve(surface.module, control.url.split("#")[0])
    payload = dict(control.fields) if data is None else data
    if method == "GET":
        if payload:
            target = _with_query(target, payload)
        return surface.client.get(target)
    return surface.client.request(method, target, data=payload)


def _get(surface: _Surface, params: dict[str, str] | None = None) -> str:
    response = surface.client.get(_list_path(surface.module), params=params)
    assert response.status_code == 200, response.text
    return str(response.text)


def _live_control_saying(html: str, key: str) -> _Control | None:
    for control in _controls(html):
        if control.inert:
            continue
        if any(word in control.haystack for word in _WORDS[key]):
            return control
    return None


def _reveal(surface: _Surface, html: str | None = None) -> str:
    """Engage the control that shows launches no longer in play.

    Discovered from the page first, with invented query parameters as a
    fallback — the pattern `test_playbook_admin_page.py` records for the
    retired-step reveal.
    """
    page = _get(surface) if html is None else html
    control = _live_control_saying(page, "reveal")
    if control is not None:
        response = _issue(surface, control)
        if response.status_code == 200:
            return str(response.text)
    for params in _REVEAL_PARAMS:
        revealed = _get(surface, params=params)
        if _rendered_ids(revealed, surface.module) != _rendered_ids(
            page, surface.module
        ) or _says(_tree(revealed), "none_out_of_play"):
            return revealed
    pytest.fail(
        "no control on the list revealed launches no longer in play, and none "
        f"of the fallback parameters {_REVEAL_PARAMS} changed what was "
        "rendered — correct `_WORDS['reveal']` / `_REVEAL_PARAMS` to the "
        "implemented control"
    )


def _reveal_params(surface: _Surface) -> dict[str, str]:
    """The reveal, expressed as query parameters so a narrowing can be
    combined with it."""
    page = _get(surface)
    control = _live_control_saying(page, "reveal")
    if control is not None and control.method.upper() == "GET":
        carried = dict(parse_qsl(urlsplit(control.url).query, keep_blank_values=True))
        carried.update(dict(control.fields))
        if carried:
            return carried
    for params in _REVEAL_PARAMS:
        revealed = _get(surface, params=params)
        if _rendered_ids(revealed, surface.module) != _rendered_ids(
            page, surface.module
        ):
            return dict(params)
    pytest.fail(
        "the reveal control could not be expressed as query parameters, so a "
        "narrowing cannot be combined with it — correct `_reveal_params`"
    )


def _gate_params(surface: _Surface, gate: str) -> dict[str, str]:
    page = _get(surface)
    for control in _controls(page):
        if control.inert or control.method.upper() != "GET":
            continue
        for name in control.names:
            if any(hint in name.lower() for hint in _GATE_PARAM_NAMES):
                return {name: gate}
    for name in _GATE_PARAM_NAMES:
        narrowed = _get(surface, params={name: gate})
        if _rendered_ids(narrowed, surface.module) != _rendered_ids(
            page, surface.module
        ):
            return {name: gate}
    pytest.fail(
        f"no gate narrowing could be driven (tried field names containing "
        f"{_GATE_PARAM_NAMES}) — correct `_gate_params` to the implemented "
        "control"
    )


def _attention_params(surface: _Surface) -> dict[str, str]:
    page = _get(surface)
    for control in _controls(page):
        if control.inert or control.method.upper() != "GET":
            continue
        carried = dict(parse_qsl(urlsplit(control.url).query, keep_blank_values=True))
        carried.update(dict(control.fields))
        for name, value in carried.items():
            if any(hint in name.lower() for hint in ("attention", "needs", "needing")):
                return {name: value or "1"}
        if any(word in control.haystack for word in _WORDS["attention"]) and carried:
            return carried
    for params in _ATTENTION_PARAMS:
        narrowed = _get(surface, params=params)
        if _rendered_ids(narrowed, surface.module) != _rendered_ids(
            page, surface.module
        ):
            return dict(params)
    pytest.fail(
        "no needs-attention narrowing could be driven (tried "
        f"{_ATTENTION_PARAMS}) — correct `_attention_params` to the "
        "implemented control"
    )


# ===========================================================================
# Requirement: The launch list enumerates every launch and renders those in
# play
# ===========================================================================


def test_every_permitted_launch_is_listed_with_its_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Every permitted launch is listed.

    WHEN several launch positions exist whose products are in launching
    stages, and the list is opened with no narrowing under a scope
    permitting all of them
    THEN each is rendered as its own row, naming its product, current
    gate, launch date, at-risk state and awaiting-confirmation state.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    launches = _FakeLaunchStore(
        _at_risk(risky.id),
        _awaiting(waiting.id),
        _advance_to(_quiet(quiet.id), "listable"),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(risky, waiting, quiet)
    )

    html = _get(surface)

    # SPECIFIED: each is rendered as its own row.
    assert sorted(_rendered_ids(html, surface.module)) == sorted(
        product.id.value for product in (risky, waiting, quiet)
    )
    for product, gate, launch_date in (
        (risky, "commit", AT_RISK_DATE),
        (waiting, "commit", HEALTHY_DATE),
        (quiet, "listable", HEALTHY_DATE),
    ):
        row = _row_for(html, surface.module, product.id)
        text = _all_text(row.node)
        # SPECIFIED: naming its product...
        assert product.name.lower() in text, (
            f"the row for {product.name!r} does not name the product: {text!r}"
        )
        # ...its current gate...
        assert gate in text, (
            f"the row for {product.name!r} does not name its current gate "
            f"{gate!r}: {text!r}"
        )
        # ...and its launch date.
        assert str(launch_date.day) in text and (str(launch_date.year) in text), (
            f"the row for {product.name!r} does not render {launch_date}: {text!r}"
        )

    # SPECIFIED: the at-risk state and the awaiting-confirmation state are
    # each *named on the row* — a row that merely sorts into a band
    # satisfies the ordering requirement and not this one.
    assert _says(_row_for(html, surface.module, risky.id), "at_risk"), (
        "the at-risk launch's row does not say it is at risk"
    )
    assert _says(_row_for(html, surface.module, waiting.id), "awaiting"), (
        "the row of the launch whose gate awaits confirmation does not say so"
    )
    # SPECIFIED, the negative half: the quiet launch's row says neither,
    # so a page labelling every row identically fails here rather than
    # passing the two assertions above.
    quiet_row = _row_for(html, surface.module, quiet.id)
    assert not _says(quiet_row, "at_risk"), (
        "a launch that is not at risk is marked at risk, so the mark is "
        f"unconditional: {_all_text(quiet_row.node)!r}"
    )
    assert not _says(quiet_row, "awaiting"), (
        "a launch whose gate does not await confirmation is marked as "
        f"awaiting it: {_all_text(quiet_row.node)!r}"
    )


def test_the_list_is_evaluated_as_of_the_day_it_is_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The list is evaluated as of the day it is rendered.

    WHEN the list is rendered on two dates, between which a launch's
    blocking step passes its due period unresolved
    THEN that launch is not marked at risk on the earlier rendering and
    is marked at risk on the later one.

    The blocking step falls on 2027-03-16 (30 days before the 2027-04-15
    launch date), so 2027-03-01 is before it and 2027-04-01 after.
    """
    subject = _launching("SKU-RISK", "Risky widget")
    launches = _FakeLaunchStore(_at_risk(subject.id))

    before = _surface(
        monkeypatch,
        launches=launches,
        catalog=_Catalog(subject),
        day=date(2027, 3, 1),
    )
    earlier = _get(before)
    monkeypatch.undo()
    after = _surface(
        monkeypatch,
        launches=launches,
        catalog=_Catalog(subject),
        day=date(2027, 4, 1),
    )
    later = _get(after)

    # SPECIFIED: not marked at risk on the earlier rendering...
    assert not _says(_row_for(earlier, before.module, subject.id), "at_risk"), (
        "the launch is marked at risk on a rendering taken before its "
        "blocking step's due period had passed, so the page is not evaluating "
        "as of the day it renders"
    )
    # ...and marked at risk on the later one.
    assert _says(_row_for(later, after.module, subject.id), "at_risk"), (
        "the launch is not marked at risk on a rendering taken after its "
        "blocking step's due period passed unresolved — a defaulted or fixed "
        "evaluation date is the failure this scenario names"
    )


def test_a_row_opens_its_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A row opens its launch.

    WHEN the list is rendered
    THEN each row offers that launch's detail page in one action, without
    scripting.
    """
    products = (
        _launching("SKU-A", "Alpha widget"),
        _launching("SKU-B", "Beta widget"),
    )
    launches = _FakeLaunchStore(*(_quiet(product.id) for product in products))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(*products))

    html = _get(surface)

    for product in products:
        row = _row_for(html, surface.module, product.id)
        # SPECIFIED: in one action, without scripting — a live anchor.
        assert _offers_in_one_action(row), (
            f"the row for {product.name!r} offers no live link to its detail "
            "page, so the page is reachable only by typing a URL"
        )
        # SPECIFIED: and it is *that launch's* detail page.
        assert urlsplit(row.link.attrs["href"]).path == _detail_path(
            surface.module, product.id
        )


def test_a_row_opens_its_launch_however_many_are_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A row opens its launch however many are shown.

    WHEN the list is rendered under a narrowing, and again with none
    THEN every rendered row offers its detail page in one action in both
    cases.
    """
    here, elsewhere = (
        _launching("SKU-HERE", "Here widget"),
        _launching("SKU-ELSEWHERE", "Elsewhere widget"),
    )
    launches = _FakeLaunchStore(
        _quiet(here.id), _advance_to(_quiet(elsewhere.id), "listable")
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(here, elsewhere)
    )

    unnarrowed = _get(surface)
    narrowed = _get(surface, params=_gate_params(surface, "listable"))

    # DERIVED guard: the narrowing really shortened the list, so the
    # assertion below is about a narrowed rendering.
    assert len(_rows(narrowed, surface.module)) < len(_rows(unnarrowed, surface.module))
    for html, how in ((unnarrowed, "unnarrowed"), (narrowed, "narrowed")):
        rows = _rows(html, surface.module)
        assert rows, f"the {how} rendering shows no row at all"
        # SPECIFIED: every rendered row offers its detail page in one
        # action, in both cases.
        for row in rows:
            assert _offers_in_one_action(row), (
                f"a row in the {how} rendering offers no live link to its detail page"
            )


def test_a_restricted_scope_lists_only_its_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A restricted scope lists only its launches.

    WHEN the list is opened under a scope permitting some products but
    not others
    THEN exactly the permitted products' launches are rendered.

    No principal resolves to such a scope today, so **the scope resolver
    alone** is stubbed and the real enumeration stays behind it, with the
    rows actually rendered asserted — not merely that the surface passed
    the scope on (the spec's own inline note; `design.md` Decision 3;
    `tasks.md` 7.3).
    """
    permitted, forbidden = (
        _launching("SKU-MINE", "Permitted widget"),
        _launching("SKU-THEIRS", "Forbidden widget"),
    )
    launches = _FakeLaunchStore(_quiet(permitted.id), _quiet(forbidden.id))
    surface = _surface(
        monkeypatch,
        launches=launches,
        catalog=_Catalog(permitted, forbidden),
        scope=AccessScope.permitting((permitted.id,)),
    )

    html = _get(surface)

    # SPECIFIED: exactly the permitted products' launches are rendered.
    assert _rendered_ids(html, surface.module) == [permitted.id.value], (
        "the list rendered "
        f"{_rendered_ids(html, surface.module)} under a scope permitting only "
        f"{permitted.id}"
    )
    # SPECIFIED: and the forbidden launch is nowhere on the page at all —
    # not merely absent from the rows.
    assert forbidden.id.value not in html
    assert forbidden.name.lower() not in _all_text(_tree(html))


def test_a_launch_with_no_date_renders_the_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch with no date renders the absence.

    WHEN a listed launch has no launch date
    THEN its row states that it has none, rather than rendering an empty
    or defaulted date.
    """
    undated, dated = (
        _launching("SKU-UNDATED", "Undated widget"),
        _launching("SKU-DATED", "Dated widget"),
    )
    launches = _FakeLaunchStore(
        _quiet(undated.id, launch_date=None), _quiet(dated.id, HEALTHY_DATE)
    )
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(undated, dated))

    html = _get(surface)

    row = _row_for(html, surface.module, undated.id)
    # SPECIFIED: the row states that it has none.
    assert _says(row, "no_date"), (
        "the undated launch's row states nothing where its launch date would "
        f"be: {_all_text(row.node)!r}"
    )
    # SPECIFIED: rather than a defaulted date — no other launch's date is
    # borrowed, and no date at all is rendered on this row.
    assert str(HEALTHY_DATE.year) not in _all_text(row.node), (
        "the undated launch's row renders a date, which can only be a "
        "defaulted or borrowed one"
    )


def test_a_finished_launch_leaves_the_default_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A finished launch leaves the default view.

    WHEN the list is opened with no narrowing and a launch's catalog
    product is in a steady-state or retired stage
    THEN that launch is not rendered.
    """
    in_play = _launching("SKU-PLAY", "In-play widget")
    steady = _steady("SKU-STEADY", "Steady widget")
    retired = _retired("SKU-RETIRED", "Retired widget")
    launches = _FakeLaunchStore(
        _quiet(in_play.id), _quiet(steady.id), _quiet(retired.id)
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(in_play, steady, retired)
    )

    html = _get(surface)

    # SPECIFIED: neither is rendered, and the launch in play still is —
    # so the filter is reading the stage rather than emptying the page.
    assert _rendered_ids(html, surface.module) == [in_play.id.value], (
        "the default view rendered "
        f"{_rendered_ids(html, surface.module)}; only the launch whose "
        f"product is still launching ({in_play.id}) belongs there"
    )


def test_a_finished_launch_stays_reachable_and_is_marked_by_its_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A finished launch stays reachable.

    WHEN the control that shows launches no longer in play is used, and
    one launch's product is in steady state while another's is retired
    THEN both are rendered, each marked, and the two marks differ.
    """
    # Neutral SKUs: a SKU naming the stage would itself read as the mark.
    in_play = _launching("PX-100", "Widget")
    steady = _steady("PX-200", "Widget")
    retired = _retired("PX-300", "Widget")
    # Identical names, gates and dates, so what distinguishes the rows is
    # the mark and nothing else.
    launches = _FakeLaunchStore(
        _quiet(in_play.id, FINISHED_EARLIER),
        _quiet(steady.id, FINISHED_EARLIER),
        _quiet(retired.id, FINISHED_EARLIER),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(in_play, steady, retired)
    )

    revealed = _reveal(surface)

    # SPECIFIED: both are rendered.
    rendered = set(_rendered_ids(revealed, surface.module))
    assert {steady.id.value, retired.id.value} <= rendered, (
        f"revealing rendered {rendered}, which does not hold both launches no "
        "longer in play"
    )
    steady_row = _row_for(revealed, surface.module, steady.id)
    retired_row = _row_for(revealed, surface.module, retired.id)
    in_play_row = _row_for(revealed, surface.module, in_play.id)

    steady_marks = _mark_tokens(steady_row, "px-200")
    retired_marks = _mark_tokens(retired_row, "px-300")
    in_play_marks = _mark_tokens(in_play_row, "px-100")

    # SPECIFIED: each marked — each carries something the in-play row,
    # otherwise identical in name, gate and launch date, does not.
    assert steady_marks - in_play_marks, (
        "the steady-state launch's row carries no mark the in-play row does "
        "not, so it is not marked as no longer in play"
    )
    assert retired_marks - in_play_marks, (
        "the retired launch's row carries no mark the in-play row does not"
    )
    # SPECIFIED: and the two marks differ — a single "finished" mark for
    # both would hide the abandoned launch among the graduated ones.
    assert steady_marks != retired_marks, (
        "a steady-state launch and a retired one are marked identically, so a "
        "launch abandoned in flight is filed under a word saying it finished"
    )
    # SPECIFIED: and the mark derives from the stage, not the launch's own
    # gate — all three stand at the same gate, so only the stage can
    # explain the difference. The wording below is INVENTED (`_WORDS`);
    # what is not invented is that each is marked and the marks differ,
    # which the three assertions above establish without any wording.
    assert _says(retired_row, "retired"), (
        "the retired launch's row does not say the product was retired: "
        f"{_all_text(retired_row.node)!r}"
    )
    assert _says(steady_row, "steady"), (
        "the steady-state launch's row does not say the product reached "
        f"steady state: {_all_text(steady_row.node)!r}"
    )


def test_revealing_when_nothing_is_out_of_play_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Revealing when nothing is out of play says so.

    WHEN the control that reveals launches no longer in play is used and
    every enumerated launch is in play
    THEN the page says there are none, rather than revealing an empty
    section.
    """
    in_play = _launching("SKU-PLAY", "In-play widget")
    launches = _FakeLaunchStore(_quiet(in_play.id))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(in_play))

    revealed = _reveal(surface)

    # SPECIFIED: the page says there are none.
    assert _says(_tree(revealed), "none_out_of_play"), (
        "revealing on a list where every launch is in play rendered no "
        "statement that there are none — an empty section unannounced is what "
        f"this scenario forbids: {_flat(_all_text(_tree(revealed)))[:400]!r}"
    )
    # DERIVED guard: the launch in play is still rendered, so this is the
    # reveal-with-nothing case rather than an emptied page.
    assert _rendered_ids(revealed, surface.module) == [in_play.id.value]


def test_an_unresolvable_products_launch_stays_in_the_default_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unresolvable product's launch stays in the default
    view.

    WHEN the list is opened with no narrowing and a launch's catalog
    product cannot be resolved
    THEN that launch is rendered.
    """
    known = _launching("SKU-KNOWN", "Known widget")
    unknown_id = _unresolvable_product_id()
    launches = _FakeLaunchStore(_quiet(known.id), _quiet(unknown_id))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(known))

    html = _get(surface)

    # SPECIFIED: the filter fails toward showing.
    assert unknown_id.value in _rendered_ids(html, surface.module), (
        "a launch whose product the catalog cannot resolve was dropped from "
        "the default view, which is the silent shortening this rule exists to "
        f"prevent (rendered: {_rendered_ids(html, surface.module)})"
    )


def test_a_launch_at_the_final_gate_is_still_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch at the final gate is still listed.

    WHEN a launch stands at the last gate of the sequence with its
    graduation approval outstanding, so its product is not yet
    steady-state
    THEN it is rendered in the default view like any other launch.
    """
    graduating = _launching("SKU-GRAD", "Graduating widget")
    launch = _advance_to(_quiet(graduating.id, HEALTHY_DATE), "graduated")
    launches = _FakeLaunchStore(launch)
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(graduating))

    html = _get(surface)

    # DERIVED guard on the WHEN: the launch really stands at the last gate.
    assert launch.current_gate == SPECIFIED_GATE_ORDER[-1]
    # SPECIFIED: it is rendered in the default view.
    assert _rendered_ids(html, surface.module) == [graduating.id.value], (
        "a launch standing at the final gate with its approval outstanding is "
        "not rendered, though its product is still in a launching stage"
    )


def test_product_identities_cannot_be_read_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Product identities cannot be read at all.

    WHEN the list is rendered and product identities cannot be read at
    all
    THEN every row is rendered, each identified by its raw product
    identifier.
    """
    first, second = (
        _launching("SKU-A", "Alpha widget"),
        _launching("SKU-B", "Beta widget"),
    )
    launches = _FakeLaunchStore(_quiet(first.id), _quiet(second.id))
    surface = _surface(
        monkeypatch,
        launches=launches,
        catalog=_Catalog(first, second, fails=True),
    )

    response = surface.client.get(_list_path(surface.module))

    # SPECIFIED: the page renders rather than failing — the outage is
    # exactly when someone opens this page.
    assert response.status_code == 200, (
        "the list failed when product identities could not be read at all; "
        f"failing the page is the one outcome forbidden ({response.status_code})"
    )
    html = response.text
    # SPECIFIED: every row is rendered...
    assert sorted(_rendered_ids(html, surface.module)) == sorted(
        [first.id.value, second.id.value]
    )
    # ...each identified by its raw product identifier.
    for product in (first, second):
        row = _row_for(html, surface.module, product.id)
        assert (
            product.id.value in f"{_all_text(row.node)} {_attribute_text(row.node)}"
        ), (
            f"the row for {product.id} does not identify the launch by its raw "
            "product identifier"
        )


def test_a_launch_whose_product_cannot_be_resolved_is_still_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch whose product cannot be resolved is still
    listed.

    WHEN a launch position exists whose product identity cannot be
    resolved
    THEN its row is rendered, identified by its raw product identifier.
    """
    known = _launching("SKU-KNOWN", "Known widget")
    unknown_id = _unresolvable_product_id()
    launches = _FakeLaunchStore(_quiet(known.id), _quiet(unknown_id))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(known))

    html = _get(surface)

    row = _row_for(html, surface.module, unknown_id)
    # SPECIFIED: identified by its raw product identifier.
    assert unknown_id.value in f"{_all_text(row.node)} {_attribute_text(row.node)}", (
        "the unresolvable launch's row does not carry its raw product "
        f"identifier: {_all_text(row.node)!r}"
    )
    # DERIVED guard: the resolvable one is still named, so the page has
    # not fallen back to identifiers wholesale.
    assert known.name.lower() in _all_text(
        _row_for(html, surface.module, known.id).node
    )


def test_no_launches_renders_a_page_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No launches renders a page, not an error.

    WHEN the list is opened and no launch position the caller may see
    exists
    THEN the page is rendered and states that no product is in launch.
    """
    surface = _surface(monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog())

    response = surface.client.get(_list_path(surface.module))

    # SPECIFIED: the page is rendered — not an error, not an absent page.
    assert response.status_code == 200, response.text
    # SPECIFIED: and states that no product is in launch.
    assert _says(_tree(response.text), "no_launches"), (
        "an empty enumeration rendered no statement that no product is in "
        f"launch: {_flat(_all_text(_tree(response.text)))[:400]!r}"
    )


def test_a_narrowings_empty_state_governs_when_both_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A narrowing's empty state governs when both apply.

    WHEN every enumerated launch is no longer in play and a narrowing is
    also active
    THEN the page reports the narrowing as having matched nothing and
    offers to clear it, rather than reporting the filter-emptied state.
    """
    steady = _steady("SKU-STEADY", "Steady widget")
    launches = _FakeLaunchStore(_quiet(steady.id, FINISHED_EARLIER))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(steady))

    html = _get(surface, params=_gate_params(surface, "ignition"))

    # DERIVED guard: nothing is rendered, so this is an empty state.
    assert _rendered_ids(html, surface.module) == []
    tree = _tree(html)
    # SPECIFIED: the narrowing's empty state governs...
    assert _says(tree, "matched_nothing"), (
        "with both a narrowing and the default-view filter emptying the page, "
        "the page does not report the narrowing as having matched nothing: "
        f"{_flat(_all_text(tree))[:400]!r}"
    )
    # ...and offers to clear it.
    assert _live_control_saying(html, "clear") is not None, (
        "the narrowing's empty state offers no control that clears it"
    )
    # SPECIFIED: rather than the filter-emptied state.
    assert not _says(tree, "none_in_play"), (
        "the page reports the filter-emptied state as well, so the two are "
        "not distinguishable and the more actionable one does not govern"
    )


def test_a_default_view_emptied_by_the_filter_says_which_state_it_is_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A default view emptied by the filter says which state it
    is in.

    WHEN the list is opened with no narrowing and every enumerated launch
    is no longer in play
    THEN the page states that no launch is in play and offers the control
    that reveals the others
    AND says so distinguishably from the page rendered when no launch
    position exists at all.
    """
    steady = _steady("SKU-STEADY", "Steady widget")
    filtered = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(steady.id, FINISHED_EARLIER)),
        catalog=_Catalog(steady),
    )
    emptied = _get(filtered)
    monkeypatch.undo()
    nothing = _surface(monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog())
    no_launches = _get(nothing)

    # DERIVED guard: both render no rows.
    assert _rendered_ids(emptied, filtered.module) == []
    assert _rendered_ids(no_launches, nothing.module) == []

    # SPECIFIED: the page states that no launch is in play...
    assert _says(_tree(emptied), "none_in_play"), (
        "a default view emptied by the filter does not state that no launch "
        f"is in play: {_flat(_all_text(_tree(emptied)))[:400]!r}"
    )
    # ...and offers the control that reveals the others.
    assert _live_control_saying(emptied, "reveal") is not None, (
        "a default view emptied by the filter offers no control revealing the "
        "launches the filter removed"
    )
    # SPECIFIED: distinguishably from the no-launch-at-all page.
    assert _flat(_all_text(_tree(emptied))) != _flat(_all_text(_tree(no_launches))), (
        "the filter-emptied page reads identically to the page rendered when "
        "no launch position exists at all, so an admin cannot tell which "
        "question was answered"
    )


# ===========================================================================
# Requirement: The list is ordered by attention, deterministically
# ===========================================================================


def test_an_at_risk_launch_precedes_one_awaiting_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An at-risk launch precedes one awaiting confirmation.

    WHEN the list holds a launch whose date is at risk and a launch whose
    current gate awaits confirmation
    THEN the at-risk launch is rendered first.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    # Handed over in the opposite order, so passing cannot be arrival.
    launches = _FakeLaunchStore(
        _advance_to(_quiet(quiet.id), "listable"),
        _awaiting(waiting.id),
        _at_risk(risky.id),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(risky, waiting, quiet)
    )

    html = _get(surface)

    # SPECIFIED: at risk first, then awaiting confirmation, then the rest.
    assert _rendered_ids(html, surface.module) == [
        risky.id.value,
        waiting.id.value,
        quiet.id.value,
    ]


def test_revealed_rows_order_most_recent_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Revealed rows order most recent first.

    WHEN launches no longer in play are revealed, holding two with launch
    dates and one with none
    THEN the dated ones are rendered most recent first, and the undated
    one last.
    """
    later = _steady("SKU-LATER", "Later widget")
    earlier = _steady("SKU-EARLIER", "Earlier widget")
    undated = _steady("SKU-UNDATED", "Undated widget")
    launches = _FakeLaunchStore(
        _quiet(earlier.id, FINISHED_EARLIER),
        _quiet(undated.id, launch_date=None),
        _quiet(later.id, FINISHED_LATER),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(later, earlier, undated)
    )

    revealed = _reveal(surface)

    # SPECIFIED: most recent first, undated last.
    assert _rendered_ids(revealed, surface.module) == [
        later.id.value,
        earlier.id.value,
        undated.id.value,
    ]


def test_launches_no_longer_in_play_stand_outside_the_bands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Launches no longer in play stand outside the bands.

    WHEN the control revealing launches no longer in play is used, and
    one of them is reported at risk
    THEN it is rendered set apart from the launches in play, not among
    the at-risk band.
    """
    finished = _steady("SKU-DONE", "Finished widget")
    risky = _launching("SKU-RISK", "Risky widget")
    quiet = _launching("SKU-QUIET", "Quiet widget")
    launches = _FakeLaunchStore(
        _at_risk(finished.id),
        _at_risk(risky.id),
        _advance_to(_quiet(quiet.id), "listable"),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(finished, risky, quiet)
    )

    revealed = _reveal(surface)

    order = _rendered_ids(revealed, surface.module)
    # SPECIFIED: not among the at-risk band — the revealed row does not
    # stand next to the at-risk launch in play, and does not precede the
    # quiet one.
    assert order.index(finished.id.value) > order.index(quiet.id.value), (
        f"the revealed launch is interleaved into the bands: {order}. An "
        "at-risk revealed launch outranking a live one is exactly what "
        "setting them apart prevents"
    )
    # SPECIFIED: rendered set apart — an element holds every revealed row
    # and no row of a launch in play.
    revealed_rows = {finished.id.value}
    in_play_rows = {risky.id.value, quiet.id.value}
    root = _tree(revealed)
    apart = [
        element
        for element in _elements(root)
        if element.tag not in ("html", "body")
        and {product for product, _ in _detail_links(element, surface.module)}
        == revealed_rows
    ]
    assert apart, (
        "no element on the page holds the revealed rows and none of the rows "
        f"in play ({in_play_rows}), so they are not set apart from the bands"
    )


def test_a_launch_in_both_bands_appears_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch in both bands appears once.

    WHEN a launch's date is at risk and its current gate also awaits
    confirmation
    THEN it is rendered exactly once, among the at-risk launches.
    """
    both = _launching("SKU-BOTH", "Both widget")
    waiting = _launching("SKU-WAIT", "Waiting widget")
    launches = _FakeLaunchStore(_awaiting(waiting.id), _at_risk_and_awaiting(both.id))
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(both, waiting))

    html = _get(surface)

    links = [product for product, _ in _detail_links(_tree(html), surface.module)]
    # SPECIFIED: exactly once.
    assert links.count(both.id.value) == 1, (
        f"the launch in both bands is offered {links.count(both.id.value)} "
        "times, so it is rendered more than once"
    )
    # SPECIFIED: among the at-risk launches — before the one that only
    # awaits confirmation.
    assert _rendered_ids(html, surface.module) == [both.id.value, waiting.id.value]
    # DERIVED guard: the fixture launch really is in both bands.
    row = _row_for(html, surface.module, both.id)
    assert _says(row, "at_risk") and _says(row, "awaiting")


def test_unchanged_data_renders_in_the_same_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Unchanged data renders in the same order.

    WHEN the list is rendered twice over the same launches with nothing
    changed between
    THEN the rows appear in the same order both times.
    """
    products = tuple(
        _launching(f"SKU-{index}", f"Widget {index}") for index in range(5)
    )
    launches = _FakeLaunchStore(
        *(
            _quiet(product.id, HEALTHY_DATE if index % 2 else LATER_HEALTHY_DATE)
            for index, product in enumerate(products)
        )
    )
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(*products))

    first = _rendered_ids(_get(surface), surface.module)
    second = _rendered_ids(_get(surface), surface.module)

    # SPECIFIED: the same order both times.
    assert first == second
    # DERIVED guard: the page really rendered every launch, so equality is
    # not the equality of two empty lists.
    assert len(first) == len(products)


def test_arrival_order_does_not_reach_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Arrival order does not reach the page.

    WHEN two launches in the same attention band are enumerated in one
    order, and then in the opposite order with nothing else changed
    THEN the rows appear in the same order both times, earliest launch
    date first.
    """
    early, late = (
        _launching("SKU-EARLY", "Early widget"),
        _launching("SKU-LATE", "Late widget"),
    )
    launches = _FakeLaunchStore(
        _quiet(early.id, HEALTHY_DATE), _quiet(late.id, LATER_HEALTHY_DATE)
    )
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(early, late))

    forward = _rendered_ids(_get(surface), surface.module)
    launches.order.reverse()
    reversed_arrival = _rendered_ids(_get(surface), surface.module)

    # SPECIFIED: the same order both times...
    assert forward == reversed_arrival, (
        "reversing the order the enumeration hands launches over changed the "
        f"page's order ({forward} then {reversed_arrival}), so the ordering "
        "rests on arrival — which a stable sort over arrival order satisfies "
        "and this sentence exists to forbid"
    )
    # ...earliest launch date first.
    assert forward == [early.id.value, late.id.value]


def test_a_launch_with_no_date_sorts_last_within_its_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch with no date sorts last within its band.

    WHEN a band holds a launch with a launch date and a launch without
    one
    THEN the dated launch is rendered first.
    """
    dated, undated = (
        _launching("SKU-DATED", "Dated widget"),
        _launching("SKU-UNDATED", "Undated widget"),
    )
    # Handed over undated-first, so passing cannot be arrival order.
    launches = _FakeLaunchStore(
        _quiet(undated.id, launch_date=None), _quiet(dated.id, HEALTHY_DATE)
    )
    surface = _surface(monkeypatch, launches=launches, catalog=_Catalog(dated, undated))

    html = _get(surface)

    # SPECIFIED: the dated launch is rendered first.
    assert _rendered_ids(html, surface.module) == [dated.id.value, undated.id.value]


# ===========================================================================
# Requirement: Narrowing the list changes what is shown, never what is
# enumerated
# ===========================================================================


def test_a_gate_narrowing_hides_without_removing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate narrowing hides without removing.

    WHEN the list is narrowed to one gate
    THEN only launches at that gate are rendered, and the launches
    enumerated are unchanged.
    """
    here, elsewhere = (
        _launching("SKU-HERE", "Here widget"),
        _launching("SKU-ELSEWHERE", "Elsewhere widget"),
    )
    launches = _FakeLaunchStore(
        _advance_to(_quiet(here.id), "listable"), _quiet(elsewhere.id)
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(here, elsewhere)
    )

    params = _gate_params(surface, "listable")
    unnarrowed = _get(surface)
    enumerated_before = list(launches.enumerations)
    narrowed = _get(surface, params=params)

    # SPECIFIED: only launches at that gate are rendered.
    assert _rendered_ids(narrowed, surface.module) == [here.id.value]
    # SPECIFIED: the launches *enumerated* are unchanged. Observed on the
    # store: the narrowed request still enumerated both launch positions,
    # so the narrowing removed a row from the rendering and nothing from
    # the enumeration.
    assert len(launches.enumerations) > len(enumerated_before), (
        "the narrowed request enumerated nothing at all"
    )
    assert launches.enumerations[-1] == 2, (
        "the narrowed request enumerated "
        f"{launches.enumerations[-1]} launch positions rather than both, so "
        "the narrowing reached the enumeration rather than only the rendering"
    )
    assert sorted(_rendered_ids(unnarrowed, surface.module)) == sorted(
        [here.id.value, elsewhere.id.value]
    )
    # SPECIFIED: and clearing the narrowing shows the set again unchanged.
    assert sorted(_rendered_ids(_get(surface), surface.module)) == sorted(
        [here.id.value, elsewhere.id.value]
    )


def test_a_narrowing_reaches_the_revealed_rows_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A narrowing reaches the revealed rows too.

    WHEN launches no longer in play are revealed and a narrowing is
    applied
    THEN the narrowing applies to those rows as it does to the rows in
    play, and the two sets stay set apart.
    """
    in_play_here = _launching("SKU-IN-HERE", "In-play here")
    in_play_elsewhere = _launching("SKU-IN-ELSE", "In-play elsewhere")
    finished_here = _steady("SKU-OUT-HERE", "Finished here")
    finished_elsewhere = _steady("SKU-OUT-ELSE", "Finished elsewhere")
    launches = _FakeLaunchStore(
        _advance_to(_quiet(in_play_here.id), "listable"),
        _quiet(in_play_elsewhere.id),
        _advance_to(_quiet(finished_here.id, FINISHED_EARLIER), "listable"),
        _quiet(finished_elsewhere.id, FINISHED_LATER),
    )
    surface = _surface(
        monkeypatch,
        launches=launches,
        catalog=_Catalog(
            in_play_here, in_play_elsewhere, finished_here, finished_elsewhere
        ),
    )

    params = {**_reveal_params(surface), **_gate_params(surface, "listable")}
    html = _get(surface, params=params)

    rendered = set(_rendered_ids(html, surface.module))
    # SPECIFIED: the narrowing applies to the revealed rows as it does to
    # the rows in play — each set narrowed within itself.
    assert rendered == {in_play_here.id.value, finished_here.id.value}, (
        f"narrowing over a revealed list rendered {rendered}; it should hold "
        "the launch at that gate from each set and neither of the others"
    )
    # SPECIFIED: and the two stay set apart.
    root = _tree(html)
    apart = [
        element
        for element in _elements(root)
        if element.tag not in ("html", "body")
        and {product for product, _ in _detail_links(element, surface.module)}
        == {finished_here.id.value}
    ]
    assert apart, (
        "under a narrowing the revealed row is no longer held apart from the "
        "rows in play"
    )


def test_narrowing_to_launches_needing_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Narrowing to launches needing attention.

    WHEN the list is narrowed to launches needing attention
    THEN only launches whose date is at risk or whose current gate awaits
    confirmation are rendered.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    launches = _FakeLaunchStore(
        _at_risk(risky.id),
        _awaiting(waiting.id),
        _advance_to(_quiet(quiet.id), "listable"),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(risky, waiting, quiet)
    )

    html = _get(surface, params=_attention_params(surface))

    # SPECIFIED: only the at-risk and awaiting-confirmation launches.
    assert _rendered_ids(html, surface.module) == [risky.id.value, waiting.id.value]


def test_narrowing_preserves_the_attention_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Narrowing preserves the attention order.

    WHEN a narrowing is applied to a list holding launches in more than
    one attention band
    THEN the rendered rows keep the same relative order they had
    unnarrowed.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    launches = _FakeLaunchStore(
        _advance_to(_quiet(quiet.id), "listable"),
        _awaiting(waiting.id),
        _at_risk(risky.id),
    )
    surface = _surface(
        monkeypatch, launches=launches, catalog=_Catalog(risky, waiting, quiet)
    )

    unnarrowed = _rendered_ids(_get(surface), surface.module)
    narrowed = _rendered_ids(
        _get(surface, params=_attention_params(surface)), surface.module
    )

    # DERIVED guard: the narrowing kept more than one band, so relative
    # order has something to preserve.
    assert len(narrowed) > 1
    # SPECIFIED: the same relative order as unnarrowed.
    assert narrowed == [product for product in unnarrowed if product in narrowed], (
        f"unnarrowed {unnarrowed} became {narrowed} under the narrowing"
    )


def test_a_narrowing_matching_nothing_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A narrowing matching nothing says so.

    WHEN a narrowing matches no launch
    THEN the page says the narrowing matched nothing and offers to clear
    it, distinguishably from the page rendered when no launch exists.
    """
    present = _launching("SKU-PRESENT", "Present widget")
    populated = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(present.id)),
        catalog=_Catalog(present),
    )
    empty_narrowing = _get(populated, params=_gate_params(populated, "ignition"))
    monkeypatch.undo()
    no_launches_at_all = _surface(
        monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog()
    )
    empty_list = _get(no_launches_at_all)

    # DERIVED guard: the narrowing really matched nothing.
    assert _rendered_ids(empty_narrowing, populated.module) == []
    # SPECIFIED: the page says the narrowing matched nothing...
    assert _says(_tree(empty_narrowing), "matched_nothing"), (
        "a narrowing that matched no launch renders no statement saying so: "
        f"{_flat(_all_text(_tree(empty_narrowing)))[:400]!r}"
    )
    # ...and offers to clear it.
    assert _live_control_saying(empty_narrowing, "clear") is not None, (
        "a narrowing that matched nothing offers no control clearing it"
    )
    # SPECIFIED: distinguishably from the no-launch page.
    assert _flat(_all_text(_tree(empty_narrowing))) != _flat(
        _all_text(_tree(empty_list))
    ), (
        "a narrowing that matched nothing reads identically to the page "
        "rendered when no launch exists at all"
    )
