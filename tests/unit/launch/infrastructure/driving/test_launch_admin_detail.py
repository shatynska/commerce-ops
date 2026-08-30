"""The launch detail page at `/admin/launches/{product_id}`, and the two
guarantees both launch surfaces carry (`launch-admin`).

Derived strictly from the delta spec
`openspec/changes/add-launch-tracking-pages/specs/launch-admin/spec.md` —
six ADDED requirements and all 25 of their scenarios:

- *A launch's detail page renders its position and every served step*
  (12 scenarios)
- *A launch's detail page renders its journal, newest first* (3
  scenarios) — **blocked on the sibling change `add-launch-journal`**,
  which provides the read; see below.
- *Both surfaces are read-only* (1 scenario)
- *A launch the caller may not see is indistinguishable from one that
  does not exist* (4 scenarios)
- *Both surfaces ride the admin session and carry the shared header* (2
  scenarios)
- *The pages' presentation comes from the shared admin vocabulary* (3
  scenarios)

The list's own three requirements live in `test_launch_admin_list.py` in
this directory, whose harness this file duplicates — this project shares
no test-helper module between test files, and `tests/**/test_*.py` is
the only path a test may be written to here. The manifest at
`openspec/changes/add-launch-tracking-pages/test-manifest.md` records
every scenario, every assertion's classification and every unresolved
project question answered here by assumption.

## Level

The launch router mounted beside the two existing admin routers and the
shared asset router, the way `main.py` composes them, over fakes for the
stores and the catalog read. That is the smallest unit that can observe
the header scenario (whose THEN is that *another module's* surface is
offered) and the stylesheet scenarios (whose THEN is that the asset is
served by a route neither surface owns). Same composition as
`test_admin_surface_navigation_and_assets.py`.

## Expected first-run state

**Absent target.** `commerce_ops.launch.infrastructure.driving.launch_admin`
does not exist, so every test here is expected to fail, resolved by name
through `_page_module()` so each scenario fails on its own rather than
the file failing to collect. Per `ai-toolkit:testing`, that establishes
absence and nothing about whether these assertions are any good.

**The three journal scenarios are additionally blocked.** `tasks.md` 4.8
and 7.1 record that the detail page's journal section cannot be
implemented before `add-launch-journal` lands, and that change is on a
different branch. Their tests fail through `_journal_seam()`, which says
so by name. A failure there is **not** a defect in this change: it is
the sequencing those tasks already record. It becomes a defect in this
change only once `add-launch-journal` has landed.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1133 passed, 0
failed, 94 skipped (the whole integration tier, no database configured)
on 2026-08-27.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the module path and both routes; that the page
renders the gate sequence with the launch's position, every served step
with name, identifier, discipline, blocking flag, recorded outcome and
its provenance, due period and overdue mark; that steps are grouped by
gate in sequence order and within a gate in the authored order; that the
current gate's group is the landing position; that an unrecorded step is
distinct from one recorded not-started; that the overdue judgement comes
from the report and is evaluated as of the render date; that the
no-served-step case is stated; that the three refusals are identical and
turn on the launch position; that an unresolvable product is served by
raw identifier; that neither page offers a state-changing control; that
both ride the admin session and carry the shared header; and that both
take their presentation from the shared stylesheet through a route no
single surface owns.

INVENTED, each with its correction point named in the code: every module
seam (`_SEAMS`); how the render date is injected (`_render_on`); how a
step's row is located (`_step_row`); how a gate group is located
(`_gate_group`); how the landing position is expressed (`_lands_on`);
the wording of the overdue mark, the blocking mark, the no-served-step
statement and the unrecorded/not-started distinction (`_WORDS`); how a
header is located and how it identifies the current surface (`_header_of`,
`_identifies_current`, taken from
`test_admin_surface_navigation_and_assets.py`); and the fixture dates,
gates and step identifiers.

Correcting any of those is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts.
"""

from __future__ import annotations

import asyncio
import importlib
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
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as playbook_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching

# ---------------------------------------------------------------------------
# The modules under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so no launch "
            "detail page is served — this is the absent-target state, and it "
            "establishes nothing about the assertions in this test"
        )


def _assets_module() -> ModuleType:
    return importlib.import_module(_ASSETS_MODULE_NAME)


_JOURNAL_SEAM_NAMES: Final = (
    "read_journal",
    "journal",
    "read_launch_journal",
    "journal_entries",
)


def _journal_seam(module: ModuleType) -> str:
    """The name the page reads the launch journal through.

    `add-launch-journal` provides that read and has not landed, so this
    fails by naming the blocking change rather than by looking like a
    defect in this one (`tasks.md` 4.8, 7.1).
    """
    for name in _JOURNAL_SEAM_NAMES:
        if hasattr(module, name):
            return name
    pytest.fail(
        f"{_PAGE_MODULE_NAME} exposes no journal seam under any of "
        f"{_JOURNAL_SEAM_NAMES}. The journal read belongs to the sibling "
        "change `add-launch-journal`, which has not landed — `tasks.md` 4.8 "
        "and 7.1 record this sequencing, so this failure is that dependency "
        "and not a defect in `add-launch-tracking-pages`"
    )


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
INVENTORY: Final = Discipline("inventory")
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
RECORDER: Final = "Nadia Recorder"
EVIDENCE: Final = "screenshot in the launch Slack thread"
SOURCE: Final = "attestation"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)
#: The single day a -30-day offset from LAUNCH_DATE resolves to.
OVERDUE_DAY: Final = date(2027, 3, 16)

# Step identifiers, chosen so each is unique text on the page.
COMMIT_STEP: Final = "strategy.commitment-agreed"
TITLE_STEP: Final = "listing.title-conforms"
IMAGES_STEP: Final = "listing.images-uploaded"
UNITS_STEP: Final = "inventory.units-received"
PROHIBITED_STEP: Final = "listing.no-incentivised-reviews"
UNTOUCHED_STEP: Final = "listing.nobody-has-touched-this"
NOT_STARTED_STEP: Final = "listing.recorded-not-started"

STEP_NAMES: Final[dict[str, str]] = {
    COMMIT_STEP: "Commitment to launch is agreed",
    TITLE_STEP: "Title conforms to marketplace policy",
    IMAGES_STEP: "Hero and gallery images are uploaded",
    UNITS_STEP: "Units are received into the warehouse",
    PROHIBITED_STEP: "No incentivised reviews are solicited",
    UNTOUCHED_STEP: "Work nobody has touched",
    NOT_STARTED_STEP: "Work recorded as not started",
}

#: INVENTED wording. The delta fixes that each fact is *stated*, never
#: how. Correction point for a page that words them differently.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "overdue": ("overdue", "past due", "overrun", "behind schedule"),
    "blocking": ("blocking", "blocks", "holds the gate", "gate-holding"),
    "no_steps": (
        "no step is served",
        "no steps",
        "serves no step",
        "nothing is served",
        "no step",
    ),
    "unrecorded": (
        "unrecorded",
        "nothing recorded",
        "no outcome",
        "not recorded",
        "no record",
        "—",
    ),
    "launch_words": ("launch", "launches", "product"),
    "playbook_words": ("playbook", "step", "steps"),
    "roster_words": ("roster", "people", "person"),
}

_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = (
    "current",
    "active",
    "here",
    "is-current",
    "is-active",
    "now",
)

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
_HIDDEN_CLASSES: Final = ("hidden", "is-hidden", "d-none", "sr-only", "visually-hidden")


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
        "name": STEP_NAMES.get(identifier, "Work this step asks for"),
        "description": None,
        "gate": "listable",
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
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


def _detail_playbook() -> LaunchPlaybook:
    """A playbook holding steps at three gates only.

    Three rather than eight so that the gate *sequence* the page renders
    is distinguishable from the gate *groups* it renders: five gates
    appear in the sequence and nowhere else. The steps are authored in
    the order below, which is the within-gate order the page must follow.
    """
    steps = (
        _step(COMMIT_STEP, gate="commit", blocking=True, discipline=LISTING),
        _step(TITLE_STEP, gate="listable", timing_anchor=OffsetAnchor(days=-30)),
        _step(IMAGES_STEP, gate="listable", timing_anchor=OffsetAnchor(days=-20)),
        _step(
            UNITS_STEP,
            gate="listable",
            blocking=True,
            discipline=INVENTORY,
            timing_anchor=OffsetAnchor(days=365),
        ),
        _step(
            PROHIBITED_STEP,
            gate="ignition",
            hazard=Hazard.PROHIBITED_TACTIC,
            timing_anchor=OffsetAnchor(days=-30),
        ),
        _step(UNTOUCHED_STEP, gate="ignition", timing_anchor=OffsetAnchor(days=365)),
        _step(NOT_STARTED_STEP, gate="ignition", timing_anchor=OffsetAnchor(days=365)),
    )
    return LaunchPlaybook(version="detail-v1", gates=_gates(), steps=steps)


PLAYBOOK: Final = _detail_playbook()
EMPTY_PLAYBOOK: Final = LaunchPlaybook(version="empty-v1", gates=_gates(), steps=())

#: The order the served playbook hands its steps over in: gate-sequence
#: order, and within a gate the authored order. Computed from the domain,
#: not restated, so the expectation cannot drift from the fixture.
SERVED_ORDER: Final = tuple(
    step.identifier
    for gate in SPECIFIED_GATE_ORDER
    for step in PLAYBOOK.steps_for_gate(gate)
)
GATES_WITH_STEPS: Final = ("commit", "listable", "ignition")


def _provenance() -> Provenance:
    return Provenance(source=SOURCE, who=RECORDER, when=RECORDED_AT, evidence=EVIDENCE)


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=APPROVED_AT,
        posture=None,
    )


def _start(
    product_id: ProductId,
    *,
    playbook: LaunchPlaybook = PLAYBOOK,
    launch_date: date | None = LAUNCH_DATE,
) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    return launch


def _satisfy_blocking(launch: Launch, playbook: LaunchPlaybook = PLAYBOOK) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _advance_to(
    launch: Launch, gate: str, playbook: LaunchPlaybook = PLAYBOOK
) -> Launch:
    while launch.current_gate != gate:
        _satisfy_blocking(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


def _fully_recorded(product_id: ProductId) -> Launch:
    """A launch standing at `listable` with a spread of recorded and
    unrecorded outcomes across its served steps."""
    launch = _advance_to(_start(product_id), "listable")
    launch.record_step_outcome(
        PLAYBOOK, step_id=TITLE_STEP, outcome=Satisfied, provenance=_provenance()
    )
    launch.record_step_outcome(
        PLAYBOOK,
        step_id=PROHIBITED_STEP,
        outcome=Refused,
        provenance=_provenance(),
    )
    launch.record_step_outcome(
        PLAYBOOK,
        step_id=NOT_STARTED_STEP,
        outcome=NotStarted,
        provenance=_provenance(),
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


def _unresolvable_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


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


class _FakeRosterStore:
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

    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
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


class _FakeStepStore:
    """The playbook-admin page's own store, so its router can be mounted
    beside the launch one for the header scenario."""

    def __init__(self) -> None:
        self.records: tuple[Any, ...] = ()
        self.version = 41

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


class _Person:
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_Person, ...]:
        return (_Person("prs_01HQ8Z6M4A", "Alice Admin"),)

    people = list_people

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


# ---------------------------------------------------------------------------
# Installing the page's seams — the single correction point
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
_PLAYBOOK_ROSTER_SEAMS: Final = ("roster", "read_roster", "people", "roster_reader")


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
        "`date`), so the requirement that the page evaluate as of the render "
        "date cannot be observed"
    )


@dataclass(frozen=True)
class _Surface:
    client: TestClient
    module: ModuleType
    launches: _FakeLaunchStore


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launches: _FakeLaunchStore,
    catalog: _Catalog,
    playbook: LaunchPlaybook = PLAYBOOK,
    day: date = RENDER_DATE,
    scope: AccessScope | None = None,
    with_neighbours: bool = False,
    signed_in: bool = True,
) -> _Surface:
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks(playbook))
    _install(monkeypatch, module, "roster", _roster_store())
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    # An empty journal by default, so the surface stays hermetic: the read
    # is wired to a real store by the composition root, and a test that
    # does not stub it would otherwise reach for a database. The three
    # journal tests install their own.
    async def _no_journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    monkeypatch.setattr(module, _journal_seam(module), _no_journal)
    _render_on(monkeypatch, module, day)
    if scope is not None:

        async def _resolver(*_args: Any, **_kwargs: Any) -> AccessScope:
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
    return _Surface(client, module, launches)


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


def _list_path(module: ModuleType) -> str:
    return _shortest_get_route(module.router)


def _detail_template(module: ModuleType) -> str:
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


def _open_detail(
    surface: _Surface, product_id: ProductId, *, follow_redirects: bool = True
) -> Any:
    return surface.client.get(
        _detail_path(surface.module, product_id), follow_redirects=follow_redirects
    )


def _detail_html(surface: _Surface, product_id: ProductId) -> str:
    response = _open_detail(surface, product_id)
    assert response.status_code == 200, (
        f"the detail page for {product_id} was not served: "
        f"{response.status_code} {response.text[:400]}"
    )
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


def _attribute_text(node: _Node) -> str:
    parts = [
        value
        for element in (node, *_elements(node))
        for key, value in element.attrs.items()
        if key in ("class", "title", "aria-label", "id") or key.startswith("data-")
    ]
    return " ".join(parts).lower()


def _haystack(node: _Node) -> str:
    return f"{_all_text(node)} {_attribute_text(node)}"


def _says(node: _Node, key: str) -> bool:
    return any(word in _haystack(node) for word in _WORDS[key])


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


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


# ---------------------------------------------------------------------------
# Reading the detail page
# ---------------------------------------------------------------------------


def _step_row(html: str, step_id: str) -> _Node:
    """The smallest element holding that step's identifier **and** its
    name, and no other served step.

    INVENTED locator; correction point for a page that renders a step's
    facts somewhere other than in one element of its own. The name is
    part of the locator so that a `<td>` holding only the identifier is
    not mistaken for the row, which would leave every other assertion
    reading the wrong element.
    """
    root = _tree(html)
    others = [other for other in SERVED_ORDER if other != step_id]
    mine = [
        element
        for element in _elements(root)
        if _holds(element, step_id)
        and not any(_holds(element, other) for other in others)
    ]
    if not mine:
        pytest.fail(
            f"no element on the detail page holds {step_id!r} without also "
            "holding another served step, so the step's own facts cannot be "
            f"read off one row — correct `_step_row` (page text: "
            f"{_flat(_all_text(root))[:400]!r})"
        )
    named = [element for element in mine if _holds(element, STEP_NAMES[step_id])]
    if not named:
        pytest.fail(
            f"no element holding {step_id!r} also holds its name "
            f"{STEP_NAMES[step_id]!r}, so the page renders the step by "
            "identifier alone — which is exactly what carrying the name on the "
            "report exists to end"
        )
    return min(named, key=_size)


_MONTHS: Final = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def _renders_date(node: _Node, day: date) -> bool:
    """Whether the element renders that calendar day.

    INVENTED: an ISO rendering, or the month named (in full or by its
    first three letters) alongside the day and year. Correction point for
    a page using some other format.
    """
    haystack = _haystack(node)
    if day.isoformat() in haystack:
        return True
    month = _MONTHS[day.month - 1]
    return (month in haystack or month[:3] in haystack) and (
        str(day.day) in haystack and str(day.year) in haystack
    )


def _gate_sequence_region(html: str) -> _Node:
    """The element rendering the gate sequence.

    INVENTED locator: the smallest element naming every gate while
    holding no served step, which the fixture makes findable by leaving
    five of the eight gates with no step at all. A page rendering the
    sequence inside the same element as its step groups needs this
    corrected — the assertion it carries, that the gates appear in the
    sequence's order, would otherwise be read off step-group headings.
    """
    root = _tree(html)
    candidates = [
        element
        for element in _elements(root)
        if all(gate in _all_text(element) for gate in SPECIFIED_GATE_ORDER)
        and not any(_holds(element, step_id) for step_id in SERVED_ORDER)
    ]
    if not candidates:
        pytest.fail(
            "no element on the detail page names every gate of the sequence "
            "without also holding a served step, so the gate sequence is not "
            "rendered as its own thing — correct `_gate_sequence_region` if it "
            f"is expressed differently (page text: "
            f"{_flat(_all_text(root))[:400]!r})"
        )
    return min(candidates, key=_size)


def _step_order(html: str) -> list[str]:
    """The served steps in the order the page first renders them."""
    text = html.lower()
    positions = [
        (text.index(step_id.lower()), step_id)
        for step_id in SERVED_ORDER
        if step_id.lower() in text
    ]
    return [step_id for _, step_id in sorted(positions)]


def _gate_group(html: str, gate: str) -> _Node:
    """The smallest *addressable* element holding every step of `gate` and
    no step of another gate — addressable because this is what the
    scenario below lands a reader on, and an element with no `id` cannot
    be.

    Correction point: since the gate's steps now render inside a
    `<table>` (`add-admin-breadcrumb-navigation`'s launch-page redesign),
    an un-addressed `<tbody>` also holds exactly one gate's steps and is
    strictly smaller than the `id`-carrying element wrapping it — the
    smallest *candidate*, but not what a fragment can land on. Filtering
    to `id`-carrying candidates first is what keeps this locator finding
    the group the page actually addresses, on either shape.
    """
    root = _tree(html)
    mine = [step.identifier for step in PLAYBOOK.steps_for_gate(gate)]
    theirs = [step_id for step_id in SERVED_ORDER if step_id not in mine]
    candidates = [
        element
        for element in _elements(root)
        if all(_holds(element, step_id) for step_id in mine)
        and not any(_holds(element, other) for other in theirs)
    ]
    addressable = [element for element in candidates if element.attrs.get("id")]
    if not addressable:
        pytest.fail(
            f"no addressable (`id`-carrying) element holds exactly the steps "
            f"of gate {gate!r} ({mine}) without holding another gate's, so "
            "the page does not group steps by gate — correct `_gate_group` "
            "if the grouping is expressed differently"
        )
    return min(addressable, key=_size)


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _lands_on(surface: _Surface, product_id: ProductId, anchor: str) -> bool:
    """Whether the page's landing position is `anchor`.

    INVENTED reading: without scripting, a server-rendered page lands
    somewhere only through a URL fragment — either the detail route
    redirects to one, or the list's row link carries one. Both are
    accepted; a page expressing it some third way needs this corrected.
    """
    unfollowed = _open_detail(surface, product_id, follow_redirects=False)
    location = unfollowed.headers.get("location", "")
    if urlsplit(location).fragment == anchor:
        return True
    listed = surface.client.get(_list_path(surface.module))
    if listed.status_code == 200:
        detail = _detail_path(surface.module, product_id)
        for element in _elements(_tree(listed.text)):
            href = element.attrs.get("href", "")
            if urlsplit(href).path == detail and urlsplit(href).fragment == anchor:
                return True
    return False


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


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


def _links_to(root: _Node, path: str) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and urlsplit(element.attrs.get("href", "")).path == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _names(node: _Node, key: str) -> bool:
    return any(word in _all_text(node) for word in _WORDS[key])


def _header_of(root: _Node, *, other_path: str, current_key: str) -> _Node:
    """The page's admin header — the smallest element that links to
    another admin surface and names this one.

    Taken unchanged in shape from
    `test_admin_surface_navigation_and_assets.py`, whose docstring
    records why a candidate enclosing the page's own tables or forms is
    rejected.
    """
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the page renders no link to {other_path!r} at all, so it carries "
            "no header from which the other admin surfaces are reachable"
        )
    candidates = [
        ancestor
        for link in outbound
        for ancestor in _ancestors(link)
        if _names(ancestor, current_key)
        and ancestor.tag not in ("html", "body", "#document")
        and not any(e.tag in ("table", "form") for e in _elements(ancestor))
    ]
    if not candidates:
        pytest.fail(
            f"the link to {other_path!r} sits in no element that also names "
            "the launch surface, so the header names one surface rather than "
            "the set — correct `_header_of` or `_WORDS['launch_words']`"
        )
    return min(candidates, key=_size)


def _offers_in_one_action(header: _Node, path: str) -> bool:
    return any(
        not _inherited(link, _element_disabled)
        and not _inherited(link, _element_hidden)
        for link in _links_to(header, path)
    )


def _identifies_current(header: _Node, *, key: str) -> bool:
    within = [header, *_elements(header)]
    naming = [
        element
        for element in within
        if _names(element, key)
        and not any(_names(child, key) for child in _elements(element))
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


# ---------------------------------------------------------------------------
# A world every detail test starts from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    surface: _Surface
    product: Product
    launch: Launch


def _world(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> _World:
    product = _launching("PX-100", "Alpha widget")
    launch = _fully_recorded(product.id)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        **overrides,
    )
    return _World(surface, product, launch)


# ===========================================================================
# Requirement: A launch's detail page renders its position and every served
# step
# ===========================================================================


def test_the_page_names_its_product(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The page names its product.

    WHEN a launch's detail page is opened
    THEN it names the launch's product.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    # SPECIFIED: the page names the product — its catalog name, which the
    # launch report does not carry.
    assert world.product.name.lower() in _all_text(_tree(html)), (
        "the detail page does not name the launch's product: "
        f"{_flat(_all_text(_tree(html)))[:400]!r}"
    )


def test_an_unresolvable_product_falls_back_to_its_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unresolvable product falls back to its identifier.

    WHEN a launch's detail page is opened and the catalog cannot resolve
    its product
    THEN the page identifies the launch by its raw product identifier and
    renders the rest unchanged.
    """
    unknown_id = _unresolvable_product_id()
    launch = _fully_recorded(unknown_id)
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(launch), catalog=_Catalog()
    )

    html = _detail_html(surface, unknown_id)

    # SPECIFIED: identified by its raw product identifier.
    assert unknown_id.value in html, (
        "the detail page of a launch whose product cannot be resolved does not "
        "identify it by its raw product identifier"
    )
    # SPECIFIED: and renders the rest unchanged — every served step is
    # still there, so the fallback narrows nothing.
    assert _step_order(html) == list(SERVED_ORDER), (
        "the unresolvable-product page renders "
        f"{_step_order(html)} rather than every served step"
    )


def test_the_gate_sequence_shows_the_launchs_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The gate sequence shows the launch's position.

    WHEN a launch's detail page is opened
    THEN every gate of the sequence is rendered in order and the launch's
    current gate is identified among them.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    region = _gate_sequence_region(html)
    text = _all_text(region)
    # SPECIFIED: every gate of the sequence is rendered — `_gate_sequence_region`
    # fails above if any is missing, and this restates it as an assertion
    # rather than leaving it to a locator.
    assert all(gate in text for gate in SPECIFIED_GATE_ORDER)
    # SPECIFIED: in order.
    positions = [text.index(gate) for gate in SPECIFIED_GATE_ORDER]
    assert positions == sorted(positions), (
        "the gates are not rendered in the sequence's order: "
        f"{list(zip(SPECIFIED_GATE_ORDER, positions, strict=True))}"
    )
    # SPECIFIED: and the launch's current gate is identified among them.
    current = world.launch.current_gate
    identified = [
        element
        for element in _elements(region)
        if current in _all_text(element)
        and not any(current in _all_text(child) for child in _elements(element))
        and any(_marked_current(node) for node in (element, *_ancestors(element)))
    ]
    assert identified, (
        f"nothing on the page marks {current!r} as the gate the launch stands "
        "at, so the sequence reads as an undifferentiated list — correct "
        "`_CURRENT_ATTRIBUTES` / `_CURRENT_CLASSES` if it is marked another way"
    )


def test_a_launch_whose_playbook_serves_no_step_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch whose playbook serves no step says so.

    WHEN a launch's detail page is opened and the served playbook holds no
    step
    THEN the gate sequence is rendered and the page states that no step is
    served.
    """
    product = _launching("PX-100", "Alpha widget")
    launch = _start(product.id, playbook=EMPTY_PLAYBOOK)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        playbook=EMPTY_PLAYBOOK,
    )

    html = _detail_html(surface, product.id)

    text = _all_text(_tree(html))
    # SPECIFIED: the gate sequence is still rendered.
    for gate in SPECIFIED_GATE_ORDER:
        assert gate in text, (
            f"the gate sequence is not rendered on a launch serving no step: "
            f"{gate!r} is absent"
        )
    # SPECIFIED: and the page states that no step is served, rather than
    # rendering gate groups that are silently empty.
    assert _says(_tree(html), "no_steps"), (
        "a launch whose served playbook holds no step renders no statement "
        f"saying so: {_flat(_all_text(_tree(html)))[:400]!r}"
    )


def test_steps_are_grouped_by_gate_and_the_page_lands_on_the_current_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Steps are grouped by gate and the page lands on the
    current one.

    WHEN a launch's detail page is opened and its steps span several gates
    THEN the steps are rendered grouped by their gate in the gate
    sequence's order
    AND within each gate they stand in that gate's authored order
    AND the group holding the launch's current gate is the page's landing
    position.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    # SPECIFIED: grouped by gate — one element per gate holding that
    # gate's steps and no other's.
    groups = {gate: _gate_group(html, gate) for gate in GATES_WITH_STEPS}
    # SPECIFIED: in the gate sequence's order, and within each gate in the
    # authored order. Both at once: the order the steps are first rendered
    # in is the served playbook's own order.
    assert _step_order(html) == list(SERVED_ORDER), (
        f"the page renders steps as {_step_order(html)} where the served "
        f"playbook's order is {list(SERVED_ORDER)} — gate-sequence order, and "
        "within a gate the authored order `launch-playbook` obliges every "
        "consumer to follow"
    )
    # SPECIFIED: the current gate's group is the page's landing position.
    current = world.launch.current_gate
    anchor = groups[current].attrs.get("id", "")
    assert anchor, (
        f"the group holding the current gate {current!r} carries no `id`, so "
        "nothing can land on it without scripting"
    )
    assert _lands_on(world.surface, world.product.id, anchor), (
        f"opening the launch does not land on {anchor!r}, the group holding "
        f"its current gate {current!r} — neither the detail route's redirect "
        "nor the list's link to it carries that fragment"
    )
    # DERIVED guard: the fixture really spans several gates.
    assert len(groups) > 1


def test_a_step_renders_its_name_not_only_its_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step renders its name, not only its identifier.

    WHEN a launch's detail page is opened
    THEN each step is rendered with the name the served playbook gives it.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    # SPECIFIED: *each* step carries its name — asserted over the whole
    # served set, so a page naming one step and identifying the rest fails.
    for step_id in SERVED_ORDER:
        row = _step_row(html, step_id)
        assert STEP_NAMES[step_id].lower() in _all_text(row), (
            f"the row for {step_id!r} does not render its name "
            f"{STEP_NAMES[step_id]!r}: {_all_text(row)!r}"
        )


def test_a_recorded_step_renders_its_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A recorded step renders its provenance.

    WHEN a step has a recorded outcome
    THEN the page renders that outcome together with who recorded it,
    when, from what source, and the evidence given.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    row = _step_row(html, TITLE_STEP)
    text = _haystack(row)
    # SPECIFIED: the outcome...
    assert "satisfied" in text, (
        f"the recorded step's row does not render its outcome: {text!r}"
    )
    # ...who recorded it...
    assert RECORDER.lower() in text, (
        f"the recorded step's row does not name who recorded it: {text!r}"
    )
    # ...when...
    assert _renders_date(row, RECORDED_AT.date()), (
        f"the recorded step's row does not render when it was recorded: {text!r}"
    )
    # ...from what source...
    assert SOURCE in text, (
        f"the recorded step's row does not render the recording's source: {text!r}"
    )
    # ...and the evidence given.
    assert EVIDENCE.lower() in text, (
        f"the recorded step's row does not render the evidence given: {text!r}"
    )


def test_an_unrecorded_step_is_distinct_from_one_recorded_not_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unrecorded step is distinct from one recorded
    not-started.

    WHEN one step has no recorded outcome and another is recorded as not
    started
    THEN the two are rendered distinguishably.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    untouched = _step_row(html, UNTOUCHED_STEP)
    recorded = _step_row(html, NOT_STARTED_STEP)

    # SPECIFIED: the two are rendered distinguishably. Compared with each
    # row's own identity and name removed, so what remains is how the page
    # renders the outcome and its provenance.
    def _outcome_tokens(node: _Node, step_id: str) -> frozenset[str]:
        known = (step_id.lower(), STEP_NAMES[step_id].lower())
        return frozenset(
            token
            for token in _haystack(node).replace("-", " ").replace(".", " ").split()
            if not any(token in part for part in known)
        )

    assert _outcome_tokens(untouched, UNTOUCHED_STEP) != _outcome_tokens(
        recorded, NOT_STARTED_STEP
    ), (
        "a step nobody has touched renders identically to one recorded as not "
        "started, though only the second carries a provenance naming who said "
        f"so: {_haystack(untouched)!r} versus {_haystack(recorded)!r}"
    )
    # SPECIFIED, the sharper half: only the recorded one names who
    # recorded it.
    assert RECORDER.lower() in _haystack(recorded)
    assert RECORDER.lower() not in _haystack(untouched), (
        "the untouched step's row names a recorder, so nothing having been "
        "recorded is being rendered as though something had been"
    )


def test_a_step_renders_its_discipline_blocking_flag_and_due_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step renders its discipline, whether it blocks, and its
    due period.

    WHEN a launch with a launch date has its detail page opened
    THEN each step renders the discipline it is owned by, whether it
    blocks its gate, and the due period the launch date yields for it.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    # SPECIFIED: each step renders the discipline it is owned by.
    for step_id in SERVED_ORDER:
        step = next(s for s in PLAYBOOK.served_steps if s.identifier == step_id)
        row = _step_row(html, step_id)
        assert step.discipline.value in _haystack(row), (
            f"the row for {step_id!r} does not render its owning discipline "
            f"{step.discipline.value!r}: {_haystack(row)!r}"
        )
    # SPECIFIED: whether it blocks its gate — the blocking step says so
    # and a non-blocking one at the same gate does not, so an
    # unconditional label fails here.
    blocking_row = _step_row(html, UNITS_STEP)
    passive_row = _step_row(html, TITLE_STEP)
    assert _says(blocking_row, "blocking"), (
        f"the blocking step's row does not say it blocks: {_haystack(blocking_row)!r}"
    )
    assert not _says(passive_row, "blocking"), (
        "a non-blocking step's row says it blocks, so the mark is "
        f"unconditional: {_haystack(passive_row)!r}"
    )
    # SPECIFIED: and the due period the launch date yields for it. The
    # -30-day offset from 2027-04-15 is the single day 2027-03-16.
    assert _renders_date(passive_row, OVERDUE_DAY), (
        f"the row for {TITLE_STEP!r} renders no due period, though the launch "
        f"has a date and the step's anchor resolves to {OVERDUE_DAY}: "
        f"{_haystack(passive_row)!r}"
    )


def test_the_detail_page_is_evaluated_as_of_the_day_it_is_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The page is evaluated as of the day it is rendered.

    WHEN the same launch's detail page is rendered on two dates, between
    which a step's due period fully passes with the step unresolved
    THEN the step is not marked overdue on the earlier rendering and is
    marked overdue on the later one.

    The unresolved step used is `listing.images-uploaded`, whose -20-day
    offset from 2027-04-15 falls on 2027-03-26.
    """
    product = _launching("PX-100", "Alpha widget")
    launch = _advance_to(_start(product.id), "listable")

    earlier_surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        day=date(2027, 3, 1),
    )
    earlier = _detail_html(earlier_surface, product.id)
    monkeypatch.undo()
    later_surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        day=date(2027, 4, 1),
    )
    later = _detail_html(later_surface, product.id)

    # SPECIFIED: not marked overdue on the earlier rendering...
    assert not _says(_step_row(earlier, IMAGES_STEP), "overdue"), (
        "the step is marked overdue on a rendering taken before its due period "
        "had passed, so the page is not evaluating as of the day it renders"
    )
    # ...and marked overdue on the later one.
    assert _says(_step_row(later, IMAGES_STEP), "overdue"), (
        "the step is not marked overdue on a rendering taken after its due "
        "period passed unresolved — a defaulted or fixed evaluation date is "
        "the failure this scenario names"
    )


def test_a_step_the_report_does_not_mark_overdue_is_not_rendered_overdue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step the report does not mark overdue is not rendered
    overdue.

    WHEN a step whose hazard permits only `Refused` has reached `Refused`,
    its due period has fully passed, and the report does not mark it
    overdue
    THEN the page does not render it as overdue.
    """
    world = _world(monkeypatch)

    html = _detail_html(world.surface, world.product.id)

    row = _step_row(html, PROHIBITED_STEP)
    # DERIVED guard: the step's due period really has fully passed by the
    # render date, so a page deriving overdue itself would say yes.
    assert _renders_date(row, OVERDUE_DAY)
    # SPECIFIED: the page does not render it as overdue — the judgement is
    # taken from the report, whose hazard rules resolve it.
    assert not _says(row, "overdue"), (
        "a prohibited-tactic step that has reached `Refused` is rendered "
        "overdue, so the page is deriving the judgement from the due period "
        "and the outcome — which would mark this step overdue forever: "
        f"{_haystack(row)!r}"
    )


def test_an_overdue_step_is_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An overdue step is marked.

    WHEN the launch report marks a step overdue
    THEN the page renders it as overdue.
    """
    product = _launching("PX-100", "Alpha widget")
    launch = _advance_to(_start(product.id), "listable")
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(launch), catalog=_Catalog(product)
    )

    html = _detail_html(surface, product.id)

    # SPECIFIED: the page renders it as overdue. `listing.images-uploaded`
    # is unresolved and its -20-day due period fell on 2027-03-26, before
    # the 2027-04-01 render date, so the report marks it overdue.
    assert _says(_step_row(html, IMAGES_STEP), "overdue"), (
        "a step the report marks overdue is not rendered overdue: "
        f"{_haystack(_step_row(html, IMAGES_STEP))!r}"
    )
    # DERIVED guard: a step whose due period has not passed is *not*
    # marked, so the mark is conditional rather than universal.
    assert not _says(_step_row(html, UNTOUCHED_STEP), "overdue")


# ===========================================================================
# Requirement: A launch's detail page renders its journal, newest first
#
# REMOVED by `add-admin-breadcrumb-navigation`: the journal no longer
# renders inline on the detail page. The three scenarios this section
# once carried now belong to `test_launch_journal_page.py`, testing the
# launch's own journal page; `test_launch_detail_breadcrumb.py` covers
# what the detail page does carry — an offer of that page in one action.
# ===========================================================================


# ===========================================================================
# Requirement: Both surfaces are read-only
# ===========================================================================


def test_the_pages_present_no_launch_changing_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The pages present no launch-changing control.

    WHEN either page is rendered for a launch in any state
    THEN it offers no control that records an outcome, approves a gate,
    decides an automated result, or moves a launch date.

    Read structurally: a server-rendered page changes state only through
    a submission that is not a GET. Narrowing is carried in query
    parameters (`design.md` Decision 8), so a read-only pair of pages
    carries no non-GET control at all. That is stronger than hunting for
    verbs in labels, and it is what makes the guarantee checkable.
    """
    world = _world(monkeypatch)
    listed = world.surface.client.get(_list_path(world.surface.module))
    assert listed.status_code == 200, listed.text
    detail = _detail_html(world.surface, world.product.id)

    for html, page in ((listed.text, "list"), (detail, "detail")):
        writing = [
            control
            for control in _controls(html)
            if control.method.upper() != "GET" and not control.inert
        ]
        # SPECIFIED: no control that changes launch state.
        assert not writing, (
            f"the {page} page offers {[(c.method, c.url, c.text) for c in writing]}, "
            "a control that submits something — these pages render an admin's "
            "own launches beside controls they act through elsewhere, and "
            '"there is deliberately nothing to press here" is what makes the '
            "surface safe to open on a live launch"
        )


# ===========================================================================
# Requirement: A launch the caller may not see is indistinguishable from one
# that does not exist
# ===========================================================================


def _absent_route(surface: _Surface) -> Any:
    return surface.client.get("/a-route-this-application-does-not-register")


def _shape_of(response: Any) -> tuple[int, str, str]:
    return (
        response.status_code,
        response.headers.get("content-type", ""),
        response.text,
    )


def test_a_product_with_no_launch_is_refused_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A product with no launch is refused as absent.

    WHEN a detail page is requested for a product that has no launch
    position
    THEN the response is shaped like a request for a route that does not
    exist.
    """
    catalogued = _launching("PX-100", "Catalogued but never launched")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(),
        catalog=_Catalog(catalogued),
    )

    refused = _open_detail(surface, catalogued.id, follow_redirects=False)

    # SPECIFIED: shaped like a request for a route that does not exist.
    assert _shape_of(refused) == _shape_of(_absent_route(surface)), (
        "a product with no launch position is refused differently from an "
        f"unregistered route: {refused.status_code} {refused.text[:200]!r}"
    )


def test_a_forbidden_launch_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A forbidden launch is refused identically.

    WHEN a detail page is requested for a launch the caller's scope does
    not permit
    THEN the response is identical in shape to the one given for a product
    with no launch.

    Unreachable end to end today, and covered as the spec's own inline
    note prescribes: **the scope resolver alone** is stubbed, the real
    read stays behind it, and the response is asserted against the one
    given for a product with no launch (`tasks.md` 7.3).
    """
    permitted = _launching("PX-100", "Permitted widget")
    forbidden = _launching("PX-200", "Forbidden widget")
    never_launched = _launching("PX-300", "Never launched")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _fully_recorded(permitted.id), _fully_recorded(forbidden.id)
        ),
        catalog=_Catalog(permitted, forbidden, never_launched),
        scope=AccessScope.permitting((permitted.id, never_launched.id)),
    )

    out_of_scope = _open_detail(surface, forbidden.id, follow_redirects=False)
    no_launch = _open_detail(surface, never_launched.id, follow_redirects=False)

    # SPECIFIED: identical in shape to the product-with-no-launch refusal.
    assert _shape_of(out_of_scope) == _shape_of(no_launch), (
        "a launch the caller's scope forbids is refused differently from a "
        "product with no launch, so the surface confirms the existence of a "
        f"launch the caller may not see: {out_of_scope.status_code} versus "
        f"{no_launch.status_code}"
    )
    # SPECIFIED: and neither leaks the forbidden launch.
    assert forbidden.name.lower() not in out_of_scope.text.lower()
    # DERIVED guard: the permitted launch is still served, so the stub is
    # a restriction rather than a blanket refusal.
    assert _open_detail(surface, permitted.id).status_code == 200


def test_a_launch_whose_product_cannot_be_resolved_is_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch whose product cannot be resolved is served.

    WHEN a detail page is requested for a launch position whose product
    the catalog cannot resolve
    THEN the page is served, identifying the launch by its raw product
    identifier.
    """
    unknown_id = _unresolvable_product_id()
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(unknown_id)),
        catalog=_Catalog(),
    )

    served = _open_detail(surface, unknown_id)

    # SPECIFIED: served, not refused — the refusal turns on the launch
    # position, never on whether the catalog can name the product.
    assert served.status_code == 200, (
        "a launch whose product the catalog cannot resolve is refused, which "
        "puts a dead end behind a row the list deliberately keeps visible — "
        "and during a catalog outage, behind every row"
    )
    # SPECIFIED: identifying the launch by its raw product identifier.
    assert unknown_id.value in served.text


def test_an_unknown_identifier_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unknown identifier is refused identically.

    WHEN a detail page is requested for an identifier with no launch
    position and no catalog product
    THEN the response is identical in shape to the other two refusals.
    """
    catalogued = _launching("PX-100", "Catalogued but never launched")
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(), catalog=_Catalog(catalogued)
    )

    unknown = _open_detail(surface, _unresolvable_product_id(), follow_redirects=False)
    no_launch = _open_detail(surface, catalogued.id, follow_redirects=False)

    # SPECIFIED: identical in shape to the other refusals, and to an
    # unregistered route.
    assert (
        _shape_of(unknown) == _shape_of(no_launch) == _shape_of(_absent_route(surface))
    ), (
        "an identifier naming nothing the system knows is refused differently "
        f"from a product with no launch: {unknown.status_code} versus "
        f"{no_launch.status_code}"
    )


# ===========================================================================
# Requirement: Both surfaces ride the admin session and carry the shared
# header
# ===========================================================================


def test_a_request_without_a_session_is_refused_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A request without a session is refused as absent.

    WHEN either page is requested with no admin session, or with one that
    has expired
    THEN the response is shaped like a request for a route that does not
    exist.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(product.id)),
        catalog=_Catalog(product),
        signed_in=False,
    )
    absent = _shape_of(_absent_route(surface))

    for path, page in (
        (_list_path(surface.module), "list"),
        (_detail_path(surface.module, product.id), "detail"),
    ):
        # SPECIFIED: with no session at all...
        no_session = surface.client.get(path, follow_redirects=False)
        assert _shape_of(no_session) == absent, (
            f"the {page} page requested with no admin session answers "
            f"{no_session.status_code}, not the shape an unregistered route "
            "answers with"
        )
        # ...and with one that has expired, which `_fake_verify` rejects
        # exactly as it rejects an absent one.
        surface.client.cookies.set(_SESSION_COOKIE, "an-expired-session")
        expired = surface.client.get(path, follow_redirects=False)
        assert _shape_of(expired) == absent, (
            f"the {page} page requested with an expired admin session answers "
            f"{expired.status_code}, not the shape an unregistered route "
            "answers with"
        )
        surface.client.cookies.delete(_SESSION_COOKIE)


def test_the_header_names_the_other_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The header names the other surfaces.

    WHEN either page is rendered
    THEN its header identifies the launch surface as the one being viewed
    and offers the other admin surfaces in one action.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    playbook_path = _shortest_get_route(playbook_module.router)
    roster_path = _shortest_get_route(roster_module.router)

    listed = surface.client.get(_list_path(surface.module))
    assert listed.status_code == 200, listed.text
    detail = _detail_html(surface, product.id)

    for html, page in ((listed.text, "list"), (detail, "detail")):
        header = _header_of(
            _tree(html), other_path=roster_path, current_key="launch_words"
        )
        # SPECIFIED: the other admin surfaces are offered in one action,
        # without scripting — both of them, not one.
        for path, what in ((roster_path, "roster"), (playbook_path, "playbook")):
            assert _offers_in_one_action(header, path), (
                f"the {page} page's header offers no live link to the {what} "
                f"surface at {path!r}"
            )
        # SPECIFIED: and it identifies the launch surface as current.
        assert _identifies_current(header, key="launch_words"), (
            f"the {page} page's header does not identify the launch surface as "
            "the one being viewed, so it reads as an undifferentiated set of "
            f"links: {_flat(_all_text(header))[:300]!r}"
        )
        # SPECIFIED: and travelling there really serves that surface.
        link = _links_to(header, roster_path)[0]
        served = surface.client.get(link.attrs["href"])
        assert served.status_code == 200, served.text


# ===========================================================================
# Requirement: The pages' presentation comes from the shared admin
# vocabulary
# ===========================================================================


def _both_pages(surface: _Surface, product: Product) -> tuple[tuple[str, str], ...]:
    listed = surface.client.get(_list_path(surface.module))
    assert listed.status_code == 200, listed.text
    return (("list", str(listed.text)), ("detail", _detail_html(surface, product.id)))


def test_the_pages_carry_no_styling_of_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The pages carry no styling of their own.

    WHEN either page is rendered
    THEN its presentation comes from the shared admin stylesheet, and the
    page carries no styling of its own.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    shared_paths = {
        route.path
        for route in _assets_module().router.routes
        if getattr(route, "path", None)
    }
    shared_prefixes = tuple(path.split("{")[0] for path in shared_paths)

    for page, html in _both_pages(surface, product):
        root = _tree(html)
        hrefs = _stylesheet_hrefs(root)
        # SPECIFIED: its presentation comes from the shared admin
        # stylesheet — every sheet it loads is served by the shared route
        # and is actually served.
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
        # SPECIFIED: and the page carries no styling of its own.
        assert not _style_blocks(root), (
            f"the {page} page carries a page-local <style> block, which is the "
            "divergence this requirement exists to prevent"
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

    WHEN either page is rendered
    THEN the stylesheet it loads is served by a route no single admin
    surface owns.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    owned = {
        route.path.split("{")[0]
        for module in (playbook_module, roster_module, surface.module)
        for route in module.router.routes
        if getattr(route, "path", None)
    }

    for page, html in _both_pages(surface, product):
        for href in _stylesheet_hrefs(_tree(html)):
            path = urlsplit(href).path
            # SPECIFIED: not a route belonging to a module that owns an
            # admin surface — this one included.
            assert not any(
                path.startswith(prefix) for prefix in owned if prefix not in ("/", "")
            ), (
                f"the {page} page reaches {href!r} through a route owned by an "
                "admin surface's own module, so deleting that route while "
                "working on that surface would break this page silently"
            )


def test_a_vocabulary_change_reaches_these_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A vocabulary change reaches these pages.

    WHEN the shared admin stylesheet changes
    THEN both pages render under the changed vocabulary without either
    page being edited.

    Operationalised as identity of source rather than by editing a
    committed asset: the bytes each page loads are the bytes the shared
    asset route serves, so a change to that source is the change both
    pages render under. An app mounting the shared router *alone* serves
    them, which is what distinguishes a shared sheet from a copy either
    surface carries.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_fully_recorded(product.id)),
        catalog=_Catalog(product),
        with_neighbours=True,
    )
    assets = _assets_module()
    shared_app = FastAPI()
    shared_app.include_router(assets.router)
    shared_client = TestClient(shared_app)
    shared_client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)

    loaded: dict[str, set[str]] = {}
    for page, html in _both_pages(surface, product):
        hrefs = _stylesheet_hrefs(_tree(html))
        assert hrefs, f"the {page} page loads no stylesheet at all"
        loaded[page] = {urlsplit(href).path for href in hrefs}
        for path in loaded[page]:
            through_shared = shared_client.get(path)
            # SPECIFIED: the sheet is the shared route's own, so a change
            # to it reaches this page without the page being edited.
            assert through_shared.status_code == 200, (
                f"the {page} page's stylesheet {path!r} is not served by the "
                "shared asset route mounted alone, so it is a copy this "
                "surface carries rather than the shared vocabulary"
            )
            assert through_shared.content == surface.client.get(path).content, (
                f"the {page} page's stylesheet {path!r} differs from what the "
                "shared route serves"
            )
    # SPECIFIED: *both* pages — the same sheets, so one vocabulary change
    # reaches the pair rather than one of them.
    assert loaded["list"] == loaded["detail"], (
        f"the list loads {sorted(loaded['list'])} and the detail page "
        f"{sorted(loaded['detail'])}, so a vocabulary change would reach one "
        "and not the other"
    )
