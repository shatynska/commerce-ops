"""The shared vocabulary's rules for what the launch surfaces render
(`launch-admin`, `tidy-the-launch-pages-presentation`).

Derived strictly from the delta spec
`openspec/changes/tidy-the-launch-pages-presentation/specs/launch-admin/spec.md`
— the third of its three ADDED requirements and all six of its
scenarios:

- *The list's rows are marked as rows*
- *The detail page's rows are marked as rows*
- *No fact is lost to the vocabulary*
- *The vocabulary carries a rule for each region*
- *No selector this change adds reaches another surface*
- *A reused class name is never selected unqualified*

The other two requirements of the same delta — the narrowing bar and the
row's product identity — are covered in
`test_launch_admin_list_presentation.py` in this directory. The manifest
at
`openspec/changes/tidy-the-launch-pages-presentation/test-manifest.md`
records every scenario, every assertion's classification and every
project question answered here by assumption.

## Level

The launch router mounted beside the playbook, members and product
routers and the shared asset router, the way `main.py` composes them,
over fakes for the stores and the catalog read. That is the smallest
unit that can observe these scenarios: three of them are stated about
the **served stylesheet**, which no launch route serves, and two of
those are about whether a selector reaches an element rendered by
*another* surface — which cannot be seen from an app holding only the
launch pages. Same composition as
`test_product_surfaces_header_and_presentation.py`, duplicated rather
than imported per this project's no-shared-helper convention.

## Reading a stylesheet in a test

Three scenarios say "WHEN the served stylesheet is read". This file
therefore parses the sheet the guarded asset route serves and matches
its selectors against the element trees the pages render. The parser and
the matcher are INVENTED whole (`_parse_rules`, `_matches`) and support
the selector subset an admin stylesheet uses: type, class, id and
attribute compounds, the four combinators, selector groups, and
`@media` / `@supports` / `@layer` nesting. Anything they cannot parse is
collected in `_Vocabulary.unparsed` and **fails the test that reads it**
rather than being silently skipped, so an exotic selector cannot slip
past a check by being unreadable.

## What "a selector this change adds" is taken to mean

Two scenarios are scoped to "no selector **this change adds**". A test
cannot read a diff, so that scope is operationalised, and the reading is
recorded here because it decides what those two tests can and cannot
catch:

- *No selector this change adds reaches another surface* considers a
  selector in scope when it matches an element inside one of this
  change's five regions **and** either mentions a class token that the
  launch pages render and no sibling surface renders, or is a bare
  unqualified selector on one of the five reused names. Its blind spot
  is a newly added rule keyed only on a token the siblings render too
  (`.mark`, `.row-action`); `tasks.md` 3.4 and 6.5 carry that by
  inspection, and 6.5 is explicit that direct comparison "is the only
  check that can actually catch a stylesheet rule reaching a sibling
  surface".
- *A reused class name is never selected unqualified* is read over
  **every** selector in the sheet rather than only over added ones. That
  is a strictly stronger reading, and it is safe because the sheet
  carries no such selector today: `design.md` — Context records that of
  everything the two launch pages render, `vocabulary.css` matches only
  `mark`, `container` and `form.narrowing`, and both pages render
  `gate`, `finished`, `empty`, `launch-date` and `current`. A bare
  `.current` rule would restyle the header on all five surfaces, which
  is the widest blast radius any rule in this change could have.

## What this file deliberately does NOT cover

- That a row **reads as a row** — "SHALL be confirmed by direct
  inspection of the rendered page" (`tasks.md` 6.3, 6.4). No response
  carries it.
- The **legibility** half of the negative obligation ("less legible than
  the surface's ordinary text"). A dim is a computed style; only "not
  displayed" is read here, which is the same line
  `test_playbook_admin_presentation_vocabulary.py` drew for the same
  vocabulary.
- The **journal** region, which the delta's region list excludes. It was
  written when `read_journal` was `None` and no entry could render, then
  `add-launch-journal` landed and the read was wired, and this file
  asserted the empty-journal statement was still rendered on the detail
  page and not hidden. `add-admin-breadcrumb-navigation` has since moved
  the journal off the detail page onto its own — `launch-admin`'s
  REMOVED requirement records the move — so that assertion is gone from
  here; the equivalent check on the journal page itself lives in
  `test_launch_journal_page.py`, which this file does not duplicate.

## Expected first-run state

**The change is not implemented.** Both pages, all four sibling surfaces
and the asset route exist, so every test here executes.

- *The vocabulary carries a rule for each region* is expected to
  **fail**: the sheet reaches almost nothing either page renders, which
  is the state the surfaces shipped in and the defect this requirement
  exists to end.
- The other five are expected to **pass**, and none of them is evidence
  that anything was implemented. Both pages already carry `launch-row`
  and `step-row` (`proposal.md` — Impact: the detail template needs no
  edit), no rule hides anything yet, and no unqualified rule on a reused
  name exists yet. They are regression guards over what this change must
  not break while adding rules — which is the whole of the third
  requirement's negative half — and the manifest records them as such
  rather than counting them as coverage of new behaviour.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1356 passed, 0
failed, 102 skipped (the whole integration tier, no database
configured), 2 xfailed, on 2026-08-28.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import members_admin as members_module
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
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
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as product_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Launching,
    Posture,
    Retired,
    SteadyState,
)
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

# ---------------------------------------------------------------------------
# The modules under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

#: SPECIFIED. The vocabulary the pages are required to take their
#: presentation from (`admin-presentation-vocabulary`, `tasks.md` 2.1).
VOCABULARY_ASSET: Final = "vocabulary.css"

#: SPECIFIED markers, given literally by the delta's own scenarios.
LAUNCH_ROW: Final = "launch-row"
STEP_ROW: Final = "step-row"

#: SPECIFIED. The class names the delta names as reused for two
#: unrelated things, and forbids being selected unqualified.
REUSED_NAMES: Final = ("finished", "gate", "launch-date", "empty", "current")


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}) — the "
            "absent-target state, which establishes nothing about the "
            "assertions in this test"
        )


def _assets_module() -> ModuleType:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist ({absent}), so no shared "
            "stylesheet is served and none of these scenarios can be read"
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

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
RECORDER: Final = "Nadia Recorder"
EVIDENCE: Final = "screenshot in the launch Slack thread"
SOURCE: Final = "clickup"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)
#: The day a -30-day offset from LAUNCH_DATE resolves to.
DUE_DAY: Final = date(2027, 3, 16)
HEALTHY_DATE: Final = date(2027, 12, 1)
FINISHED_DATE: Final = date(2027, 1, 10)

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

#: INVENTED wording, inherited from `test_launch_admin_list.py` and
#: `test_launch_admin_detail.py`, whose implementations satisfy them.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "at_risk": ("at risk", "at-risk", "date at risk"),
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
    "overdue": ("overdue", "past due", "overrun", "behind schedule"),
    "blocking": ("blocking", "blocks", "holds the gate", "gate-holding"),
    "empty_journal": (
        "nothing is recorded",
        "no entries",
        "nothing recorded",
        "empty",
    ),
}

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


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": STEP_NAMES[identifier],
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


def _playbook() -> LaunchPlaybook:
    """Steps at three gates only, so the gate *sequence* the detail page
    renders is distinguishable from the gate *groups* it renders."""
    steps = (
        _step(COMMIT_STEP, gate="commit", blocking=True),
        _step(TITLE_STEP, gate="listable"),
        _step(IMAGES_STEP, gate="listable", timing_anchor=OffsetAnchor(days=-20)),
        _step(
            UNITS_STEP,
            gate="listable",
            blocking=True,
            discipline=INVENTORY,
            timing_anchor=OffsetAnchor(days=365),
        ),
        _step(PROHIBITED_STEP, gate="ignition", hazard=Hazard.PROHIBITED_TACTIC),
        _step(UNTOUCHED_STEP, gate="ignition", timing_anchor=OffsetAnchor(days=365)),
        _step(NOT_STARTED_STEP, gate="ignition", timing_anchor=OffsetAnchor(days=365)),
    )
    return LaunchPlaybook(version="vocabulary-v1", gates=_gates(), steps=steps)


PLAYBOOK: Final = _playbook()
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


def _start(product_id: ProductId, launch_date: date | None = LAUNCH_DATE) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=launch_date
    )
    return launch


def _satisfy_blocking(launch: Launch) -> None:
    for step in PLAYBOOK.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                PLAYBOOK,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _advance_to(launch: Launch, gate: str) -> Launch:
    while launch.current_gate != gate:
        _satisfy_blocking(launch)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(PLAYBOOK)
    return launch


def _fully_recorded(product_id: ProductId) -> Launch:
    """Standing at `listable`, with a spread of recorded and unrecorded
    outcomes across its served steps."""
    launch = _advance_to(_start(product_id), "listable")
    launch.record_step_outcome(
        PLAYBOOK, step_id=TITLE_STEP, outcome=Satisfied, provenance=_provenance()
    )
    launch.record_step_outcome(
        PLAYBOOK, step_id=PROHIBITED_STEP, outcome=Refused, provenance=_provenance()
    )
    launch.record_step_outcome(
        PLAYBOOK, step_id=NOT_STARTED_STEP, outcome=NotStarted, provenance=_provenance()
    )
    return launch


def _at_risk(product_id: ProductId) -> Launch:
    """At `commit`, whose blocking step's -30-day due period has passed
    unresolved by the render date."""
    return _start(product_id, LAUNCH_DATE)


def _awaiting(product_id: ProductId) -> Launch:
    """At `commit`, a confirmation gate, with its blocking condition
    satisfied and no approval recorded."""
    launch = _start(product_id, HEALTHY_DATE)
    _satisfy_blocking(launch)
    return launch


def _undated(product_id: ProductId) -> Launch:
    return _start(product_id, None)


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
    product.change_stage(Launching(phase=1), confirmed_by="Helen", at=T_REGISTERED)
    if stage is not None:
        product.change_stage(stage, confirmed_by="Helen", at=T_REGISTERED)
    return product


def _launching(sku: str, name: str) -> Product:
    return _product(sku, name)


def _steady(sku: str, name: str) -> Product:
    return _product(sku, name, SteadyState(posture=Posture.OPTIMIZE))


def _retired(sku: str, name: str) -> Product:
    return _product(sku, name, Retired())


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
    def __init__(
        self, records: tuple[_StepRecord, ...] = (), version: int = 41
    ) -> None:
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
        return (_Member("prs_01HQ8Z6M4A", "Alice Admin"),)

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeScopeResolution:
    async def __call__(self, *_args: Any, **_kwargs: Any) -> AccessScope:
        return AccessScope.unrestricted()


class _EmptyRead:
    async def __call__(self, *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (), 1


def _seeded_steps() -> _FakeStepStore:
    """A step per gate, so the steps page renders rows of its own."""
    records = tuple(
        _StepRecord(
            _step(
                COMMIT_STEP,
                gate=gate,
                blocking=True,
                assignees=("prs_01HQ8Z6M4A",),
            ),
            display_order=(index + 1) * 10,
        )
        for index, gate in enumerate(SPECIFIED_GATE_ORDER)
    )
    return _FakeStepStore(records)


# ---------------------------------------------------------------------------
# Installing the surfaces' seams — the single correction point
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


# ---------------------------------------------------------------------------
# The world: the launch pages, their four siblings and the asset route
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    client: TestClient
    module: ModuleType
    subject: Product
    risky: Product
    waiting: Product
    undated: Product
    steady: Product
    retired: Product


def _world(monkeypatch: pytest.MonkeyPatch) -> _World:
    subject = _launching("PX-100", "Alpha widget")
    risky = _launching("PX-200", "Risky widget")
    waiting = _launching("PX-300", "Waiting widget")
    undated = _launching("PX-400", "Undated widget")
    steady = _steady("PX-500", "Graduated widget")
    retired = _retired("PX-600", "Abandoned widget")
    catalog = _Catalog(subject, risky, waiting, undated, steady, retired)
    launches = _FakeLaunchStore(
        _fully_recorded(subject.id),
        _at_risk(risky.id),
        _awaiting(waiting.id),
        _undated(undated.id),
        _start(steady.id, FINISHED_DATE),
        _start(retired.id, FINISHED_DATE),
    )

    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    # Stubbed empty, so the surface stays hermetic: the read is bound to a
    # real store by the composition root, and a page rendered without this
    # would reach for a database. What this file asserts about the journal
    # is that the empty statement renders, which is what this produces.
    async def _no_journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    _install(monkeypatch, module, "read_journal", _no_journal)
    _render_on(monkeypatch, module, RENDER_DATE)

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

    assets = _assets_module()
    monkeypatch.setattr(assets, "verify", _fake_verify)

    app = FastAPI()
    app.include_router(module.router)
    app.include_router(playbook_module.router)
    app.include_router(members_module.router)
    app.include_router(product_module.router)
    app.include_router(assets.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _World(client, module, subject, risky, waiting, undated, steady, retired)


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


def _list_html(world: _World, params: dict[str, str] | None = None) -> str:
    response = world.client.get(_shortest_get_route(world.module.router), params=params)
    assert response.status_code == 200, response.text
    return str(response.text)


def _detail_html(world: _World, product_id: ProductId) -> str:
    template = _parameterised_get_route(world.module.router)
    return _fetch(world, _fill(template, product_id.value))


def _sibling_pages(world: _World) -> dict[str, str]:
    """The four surfaces this change may not reach: the step list, the
    Team page, the product index and the product dossier."""
    return {
        "step list": _fetch(world, _shortest_get_route(playbook_module.router)),
        "Team page": _fetch(world, _shortest_get_route(members_module.router)),
        "product index": _fetch(world, _shortest_get_route(product_module.router)),
        "product dossier": _fetch(
            world,
            _fill(
                _parameterised_get_route(product_module.router),
                world.subject.id.value,
            ),
        ),
    }


def _vocabulary(world: _World) -> str:
    template = _parameterised_get_route(_assets_module().router)
    return _fetch(world, _fill(template, VOCABULARY_ASSET))


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
        if key in ("class", "title", "aria-label") or key.startswith("data-")
    ]
    return " ".join(parts).lower()


def _haystack(node: _Node) -> str:
    return f"{_all_text(node)} {_attribute_text(node)}"


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    return marker in _classes(node)


def _says(node: _Node, key: str) -> bool:
    return any(word in _haystack(node) for word in _WORDS[key])


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _siblings(node: _Node) -> list[_Node]:
    if node.parent is None:
        return [node]
    return [child for child in node.parent.children if isinstance(child, _Node)]


def _size(node: _Node) -> int:
    return 1 + sum(1 for _ in _elements(node))


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


def _renders_date(node: _Node, day: date) -> bool:
    haystack = _haystack(node)
    if day.isoformat() in haystack:
        return True
    month = _MONTHS[day.month - 1]
    return (month in haystack or month[:3] in haystack) and (
        str(day.day) in haystack and str(day.year) in haystack
    )


# ---------------------------------------------------------------------------
# Regions, read off a rendering
# ---------------------------------------------------------------------------


def _detail_links(root: _Node, world: _World) -> list[tuple[str, _Node]]:
    template = _parameterised_get_route(world.module.router)
    prefix = template[: template.index("{")]
    found: list[tuple[str, _Node]] = []
    for element in _elements(root):
        if element.tag != "a":
            continue
        path = element.attrs.get("href", "").split("?")[0].split("#")[0]
        if not path.startswith(prefix) or path == prefix:
            continue
        remainder = path[len(prefix) :].strip("/")
        if remainder and "/" not in remainder:
            found.append((remainder, element))
    return found


def _row_of(html: str, world: _World, product_id: ProductId) -> _Node:
    """The structural row: the smallest element holding that launch's
    detail link and no other's. The locator `test_launch_admin_list.py`
    established, used here so the region is found independently of the
    marker this requirement is about."""
    root = _tree(html)
    links = [
        link
        for identifier, link in _detail_links(root, world)
        if identifier == product_id.value
    ]
    if not links:
        pytest.fail(f"no row for {product_id.value} was rendered")
    containers = [
        ancestor
        for ancestor in _ancestors(links[0])
        if ancestor.tag not in ("html", "body")
        and {other for other, _ in _detail_links(ancestor, world)} == {product_id.value}
    ]
    return min(containers, key=_size) if containers else links[0]


def _revealed_section(html: str, world: _World, revealed: set[str]) -> _Node:
    """The smallest element holding exactly the revealed rows and no row
    of a launch in play."""
    candidates = [
        element
        for element in _elements(_tree(html))
        if element.tag not in ("html", "body")
        and {product for product, _ in _detail_links(element, world)} == revealed
    ]
    if not candidates:
        pytest.fail(
            "no element holds the revealed rows and none of the rows in play, "
            "so the list renders no revealed section to carry a rule"
        )
    return max(candidates, key=_size)


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
    strictly smaller than the `id`/class-carrying element wrapping it —
    the smallest *candidate*, but not the region the vocabulary rule
    below (or `launch-admin`'s own fragment-landing requirement) is about.
    Filtering to `id`-carrying candidates first is what keeps this locator
    finding the group the page actually addresses, on either shape.
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


def _step_row_of(html: str, step_id: str) -> _Node:
    """The smallest element holding that step's identifier and its name
    and no other served step."""
    others = [other for other in SERVED_ORDER if other != step_id]
    mine = [
        element
        for element in _elements(_tree(html))
        if _holds(element, step_id)
        and not any(_holds(element, other) for other in others)
        and _holds(element, STEP_NAMES[step_id])
    ]
    if not mine:
        pytest.fail(
            f"no element on the detail page holds {step_id!r} and its name "
            "without also holding another served step — correct `_step_row_of`"
        )
    return min(mine, key=_size)


def _marked(node: _Node, marker: str) -> _Node:
    """The element carrying `marker` that is this region, or the nearest
    ancestor carrying it."""
    for candidate in (node, *_ancestors(node)):
        if _carries(candidate, marker):
            return candidate
    pytest.fail(
        f"neither the region nor any ancestor of it carries {marker!r}: the "
        f"region carries {sorted(_classes(node))} and its ancestors "
        f"{[sorted(_classes(a)) for a in _ancestors(node)]}"
    )


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

    @property
    def qualified(self) -> bool:
        """Whether anything but a single class narrows this compound."""
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
    group: str
    declarations: str
    context: str
    parts: tuple[tuple[str, _Compound], ...]

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(
            name for _, compound in self.parts for name in compound.classes
        )

    @property
    def has_class_or_id(self) -> bool:
        return any(
            compound.classes or compound.identifier for _, compound in self.parts
        )

    @property
    def hides(self) -> bool:
        flat = self.declarations.replace(" ", "").replace("\n", "").lower()
        return any(
            hidden in flat
            for hidden in (
                "display:none",
                "visibility:hidden",
                "visibility:collapse",
                "content-visibility:hidden",
            )
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


def _parse_attribute(text: str) -> tuple[str, str, str] | None:
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
            parsed = _parse_attribute(text[index + 1 : end])
            if parsed is None:
                return None
            attributes.append(parsed)
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
        # A compound made only of pseudo-classes selects nothing this
        # matcher can judge; `:root` is the one it can, above.
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
    """Every selector in the sheet was read, so no check below skipped
    one silently."""
    assert not vocabulary.unparsed, (
        f"{len(vocabulary.unparsed)} selector(s) in the served stylesheet "
        f"could not be read: {list(vocabulary.unparsed)}. A selector this "
        "matcher cannot parse is one these scenarios cannot be read against "
        "— correct `_parse_complex` rather than accepting the gap"
    )
    assert vocabulary.rules, (
        "the served stylesheet carries no rule at all, so nothing below reads anything"
    )


def _tokens_of(pages: dict[str, str]) -> set[str]:
    return {
        name
        for html in pages.values()
        for element in _elements(_tree(html))
        for name in _classes(element)
    }


def _within(region: _Node) -> list[_Node]:
    return [region, *_elements(region)]


# ===========================================================================
# Requirement: The shared vocabulary carries rules for what these
# surfaces render
# ===========================================================================


def test_the_lists_rows_are_marked_as_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The list's rows are marked as rows.

    WHEN the list is rendered
    THEN each launch is rendered within one element carrying
    `launch-row`, holding every fact that row shows.
    """
    world = _world(monkeypatch)

    html = _list_html(world)

    facts: tuple[tuple[Product, tuple[str, ...], str | None], ...] = (
        (world.subject, ("listable",), None),
        (world.risky, ("commit",), "at_risk"),
        (world.waiting, ("commit",), "awaiting"),
        (world.undated, ("commit",), "no_date"),
    )
    for product, plain, mark in facts:
        row = _row_of(html, world, product.id)
        # SPECIFIED: each launch is rendered within one element carrying
        # `launch-row`.
        marked = _marked(row, LAUNCH_ROW)
        held = {product_id for product_id, _ in _detail_links(marked, world)}
        assert held == {product.id.value}, (
            f"the element carrying {LAUNCH_ROW!r} for {product.name!r} holds "
            f"{held}, so it is not one launch's row"
        )
        # SPECIFIED: holding every fact that row shows — the product, its
        # gate, its launch date or the absence of one, and its marks.
        assert product.name.lower() in _all_text(marked), (
            f"the {LAUNCH_ROW!r} element does not name {product.name!r}"
        )
        for needle in plain:
            assert needle in _haystack(marked), (
                f"the {LAUNCH_ROW!r} element for {product.name!r} does not "
                f"hold {needle!r}: {_haystack(marked)!r}"
            )
        if mark is not None:
            assert _says(marked, mark), (
                f"the {LAUNCH_ROW!r} element for {product.name!r} does not "
                f"hold its {mark!r} fact: {_haystack(marked)!r}"
            )
        elif product is world.subject:
            assert _renders_date(marked, LAUNCH_DATE), (
                f"the {LAUNCH_ROW!r} element for {product.name!r} does not "
                f"render its launch date: {_haystack(marked)!r}"
            )


def test_the_detail_pages_rows_are_marked_as_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The detail page's rows are marked as rows.

    WHEN a launch's detail page is rendered
    THEN each served step is rendered within one element carrying
    `step-row`, holding every fact that step shows.
    """
    world = _world(monkeypatch)

    html = _detail_html(world, world.subject.id)

    for step_id in SERVED_ORDER:
        step = next(s for s in PLAYBOOK.served_steps if s.identifier == step_id)
        row = _step_row_of(html, step_id)
        # SPECIFIED: within one element carrying `step-row`.
        marked = _marked(row, STEP_ROW)
        others = [other for other in SERVED_ORDER if other != step_id]
        assert not any(_holds(marked, other) for other in others), (
            f"the element carrying {STEP_ROW!r} for {step_id!r} also holds "
            "another served step, so it is not one step's row"
        )
        # SPECIFIED: holding every fact that step shows — its name, its
        # identifier and the discipline that owns it, at least.
        for needle in (step_id, STEP_NAMES[step_id], step.discipline.value):
            assert _holds(marked, needle), (
                f"the {STEP_ROW!r} element for {step_id!r} does not hold "
                f"{needle!r}: {_haystack(marked)!r}"
            )
    # SPECIFIED, the facts that distinguish one row from another: the
    # blocking flag, the recorded provenance and the overdue mark each
    # sit inside the row they belong to.
    assert _says(_marked(_step_row_of(html, UNITS_STEP), STEP_ROW), "blocking"), (
        "the blocking step's `step-row` does not say it blocks"
    )
    recorded = _marked(_step_row_of(html, TITLE_STEP), STEP_ROW)
    for needle in ("satisfied", RECORDER, SOURCE, EVIDENCE):
        assert _holds(recorded, needle), (
            f"the recorded step's `step-row` does not hold {needle!r}: "
            f"{_haystack(recorded)!r}"
        )
    assert _says(_marked(_step_row_of(html, IMAGES_STEP), STEP_ROW), "overdue"), (
        "the overdue step's `step-row` does not carry its overdue mark"
    )


def test_no_fact_is_lost_to_the_vocabulary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: No fact is lost to the vocabulary.

    WHEN either page is rendered
    THEN every fact the capability requires that page to render is
    present in the response
    AND none of them, nor a container holding one, is rendered as not
    displayed.

    Read two ways, because the vocabulary can quiet a fact without the
    markup saying so: no fact-bearing element or ancestor of one is
    hidden in the markup, **and** no rule in the served stylesheet that
    matches one declares it undisplayed. The requirement's other half —
    "less legible than the surface's ordinary text" — is a computed
    style no response carries, and is deliberately not asserted.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    list_html = _list_html(world)
    revealed_html = _list_html(world, params=_reveal_params(world, list_html))
    detail_html = _detail_html(world, world.subject.id)

    checks: list[tuple[str, _Node]] = []
    for product, key in (
        (world.risky, "at_risk"),
        (world.waiting, "awaiting"),
        (world.undated, "no_date"),
    ):
        row = _row_of(list_html, world, product.id)
        checks.append(
            (f"the list's {key} mark", _bearing(row, _WORDS[key], key, product.name))
        )
    subject_row = _row_of(list_html, world, world.subject.id)
    checks.append(
        (
            "the list's product name",
            _bearing(subject_row, (world.subject.name.lower(),), "name", "the list"),
        )
    )
    checks.append(
        (
            "the list's current gate",
            _bearing(subject_row, ("listable",), "gate", "the list"),
        )
    )
    checks.append(
        (
            "the list's launch date",
            _bearing(
                subject_row, (LAUNCH_DATE.isoformat(),), "launch date", "the list"
            ),
        )
    )
    for product, key in ((world.steady, "steady"), (world.retired, "retired")):
        row = _row_of(revealed_html, world, product.id)
        checks.append(
            (
                f"the revealed row's {key} mark",
                _bearing(row, _WORDS[key], key, product.name),
            )
        )

    detail_root = _tree(detail_html)
    checks.append(
        (
            "the detail page's product name",
            _bearing(
                detail_root,
                (world.subject.name.lower(),),
                "name",
                "the detail page",
            ),
        )
    )
    checks.append(("the detail page's gate sequence", _gate_sequence(detail_html)))
    for gate in GATES_WITH_STEPS:
        checks.append((f"the {gate} gate's group", _gate_group(detail_html, gate)))
    for step_id in SERVED_ORDER:
        step = next(s for s in PLAYBOOK.served_steps if s.identifier == step_id)
        row = _step_row_of(detail_html, step_id)
        checks.append((f"the row for {step_id}", row))
        for label, needles in (
            ("identifier", (step_id.lower(),)),
            ("name", (STEP_NAMES[step_id].lower(),)),
            ("discipline", (step.discipline.value.lower(),)),
        ):
            checks.append(
                (f"{step_id}'s {label}", _bearing(row, needles, label, step_id))
            )
    recorded = _step_row_of(detail_html, TITLE_STEP)
    for label, needle in (
        ("outcome", "satisfied"),
        ("recorder", RECORDER.lower()),
        ("source", SOURCE.lower()),
        ("evidence", EVIDENCE.lower()),
    ):
        checks.append(
            (
                f"the recorded step's {label}",
                _bearing(recorded, (needle,), label, TITLE_STEP),
            )
        )
    checks.append(
        (
            "the blocking step's blocking flag",
            _bearing(
                _step_row_of(detail_html, UNITS_STEP),
                _WORDS["blocking"],
                "blocking flag",
                UNITS_STEP,
            ),
        )
    )
    checks.append(
        (
            "the overdue step's overdue mark",
            _bearing(
                _step_row_of(detail_html, IMAGES_STEP),
                _WORDS["overdue"],
                "overdue mark",
                IMAGES_STEP,
            ),
        )
    )
    checks.append(
        (
            "the due period",
            _bearing(
                _step_row_of(detail_html, TITLE_STEP),
                (DUE_DAY.isoformat(),),
                "due period",
                TITLE_STEP,
            ),
        )
    )
    for description, element in checks:
        # SPECIFIED: the fact is present in the response — `_bearing`
        # fails by name where it is not.
        chain = [element, *_ancestors(element)]
        # SPECIFIED: and neither it nor a container holding it is
        # rendered as not displayed — in the markup...
        for node in chain:
            assert not _element_hidden(node), (
                f"{description} sits inside a <{node.tag}> the markup renders "
                f"as not displayed (class {sorted(_classes(node))})"
            )
        # ...or by a rule of the vocabulary the pages inherit.
        for rule in vocabulary.rules:
            if not rule.hides or rule.parts[-1][1].pseudo_elements:
                continue
            if "print" in rule.context.lower():
                continue
            hit = next((node for node in chain if _matches(rule, node)), None)
            if hit is not None:
                pytest.fail(
                    f"{description} is hidden by the vocabulary: "
                    f"{rule.selector!r} matches a <{hit.tag}> holding it and "
                    "declares it undisplayed. A step's recorded provenance and "
                    "a launch's attention marks are what an admin opens the "
                    "page for"
                )


def test_the_vocabulary_carries_a_rule_for_each_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The vocabulary carries a rule for each region.

    WHEN the served stylesheet is read
    THEN it carries a rule reaching each of the list's rows, the list's
    revealed section, the detail page's gate sequence, its gate groups
    and its step rows.

    "A rule reaching the region" is read as: a rule that matches the
    region's element, names a class or an id (so a bare `ul` or `mark`
    inherited from the page's substrate does not count as the vocabulary
    holding up its half), and matches no element any sibling surface
    renders — which the scenario below requires of the same rules
    anyway. INVENTED reading; correction point for a vocabulary that
    reaches its regions some other way.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)
    siblings = _sibling_pages(world)
    sibling_elements = [
        element for html in siblings.values() for element in _elements(_tree(html))
    ]

    list_html = _list_html(world)
    revealed_html = _list_html(world, params=_reveal_params(world, list_html))
    detail_html = _detail_html(world, world.subject.id)
    regions: dict[str, _Node] = {
        "the list's rows": _row_of(list_html, world, world.subject.id),
        "the list's revealed section": _revealed_section(
            revealed_html, world, {world.steady.id.value, world.retired.id.value}
        ),
        "the detail page's gate sequence": _gate_sequence(detail_html),
        "the detail page's gate groups": _gate_group(detail_html, "listable"),
        "the detail page's step rows": _step_row_of(detail_html, TITLE_STEP),
    }

    for description, region in regions.items():
        reaching = [
            rule
            for rule in vocabulary.rules
            if rule.has_class_or_id
            and _matches(rule, region)
            and not any(_matches(rule, other) for other in sibling_elements)
        ]
        # SPECIFIED: the sheet carries a rule reaching this region.
        assert reaching, (
            f"the served stylesheet carries no rule reaching {description} "
            f"(the region is a <{region.tag}> carrying "
            f"{sorted(_classes(region))}). Inheriting a vocabulary that says "
            "nothing about you is not the guarantee the pages' presentation "
            "requirement was written to give"
        )


def test_no_selector_this_change_adds_reaches_another_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No selector this change adds reaches another surface.

    WHEN the served stylesheet is read
    THEN no selector this change adds matches an element rendered by the
    step list, the Team page, the product index or the product
    dossier.

    "A selector this change adds" is operationalised, because a test
    cannot read a diff: a selector matching an element inside one of
    this change's five regions, which either names a class the launch
    pages render and no sibling surface does, or is a bare unqualified
    selector on one of the reused names. The file docstring records what
    that reading cannot catch, and which task carries it instead.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    list_html = _list_html(world)
    revealed_html = _list_html(world, params=_reveal_params(world, list_html))
    detail_html = _detail_html(world, world.subject.id)
    launch_pages = {"list": revealed_html, "detail": detail_html}
    siblings = _sibling_pages(world)

    launch_only = _tokens_of(launch_pages) - _tokens_of(siblings)
    # DERIVED guard: the launch pages really do render markers of their
    # own, or the filter below selects nothing and the test is vacuous.
    assert launch_only, (
        "the launch pages render no class the four sibling surfaces do not, "
        "so no selector could be attributed to this change at all"
    )

    regions = [
        _row_of(revealed_html, world, world.subject.id),
        _revealed_section(
            revealed_html, world, {world.steady.id.value, world.retired.id.value}
        ),
        _gate_sequence(detail_html),
        *(_gate_group(detail_html, gate) for gate in GATES_WITH_STEPS),
        *(_step_row_of(detail_html, step_id) for step_id in SERVED_ORDER),
    ]
    inside = [node for region in regions for node in _within(region)]
    sibling_elements = [
        (name, element)
        for name, html in siblings.items()
        for element in _elements(_tree(html))
    ]

    for rule in vocabulary.rules:
        if not any(_matches(rule, node) for node in inside):
            continue
        bare_reused = (
            len(rule.parts) == 1
            and not rule.parts[0][1].qualified
            and rule.parts[0][1].classes
            and set(rule.parts[0][1].classes) <= set(REUSED_NAMES)
        )
        if not (rule.classes & launch_only) and not bare_reused:
            continue
        reached = [
            (name, element)
            for name, element in sibling_elements
            if _matches(rule, element)
        ]
        # SPECIFIED: no such selector matches an element rendered by any
        # of the four sibling surfaces.
        assert not reached, (
            f"the selector {rule.selector!r} reaches this change's own "
            f"regions and also matches {len(reached)} element(s) on "
            f"{sorted({name for name, _ in reached})} — for instance a "
            f"<{reached[0][1].tag}> carrying "
            f"{sorted(_classes(reached[0][1]))}. A selector reaching a "
            "sibling surface is a defect of this change, not a bonus"
        )


def test_a_reused_class_name_is_never_selected_unqualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A reused class name is never selected unqualified.

    WHEN the served stylesheet is read
    THEN no selector this change adds selects `finished`, `gate`,
    `launch-date`, `empty` or `current` unqualified.

    Read over every selector in the sheet rather than only over added
    ones — a strictly stronger reading, safe because the sheet carries
    no such selector today (`design.md` — Context). "Unqualified" is the
    literal reading: a selector that is one compound holding exactly
    that class and nothing else — no tag, no second class, no id, no
    attribute, no pseudo, and no ancestor context. `section.finished`,
    `.launch-row .gate` and `.launches .launch-date` are all qualified
    and all allowed.
    """
    world = _world(monkeypatch)
    vocabulary = _read(_vocabulary(world))
    _readable(vocabulary)

    offenders = [
        rule
        for rule in vocabulary.rules
        if len(rule.parts) == 1
        and not rule.parts[0][1].qualified
        and rule.parts[0][1].classes
        and set(rule.parts[0][1].classes) <= set(REUSED_NAMES)
    ]

    # SPECIFIED: none of the five reused names is selected unqualified.
    assert not offenders, (
        "the served stylesheet selects a reused class name unqualified: "
        f"{[rule.selector for rule in offenders]}. Both launch pages reuse "
        "each of these names for two unrelated things, and `current` escapes "
        "the launch surfaces altogether — the shared header marks the surface "
        "being viewed with it on every admin page, so an unqualified rule "
        "restyles all five"
    )


# ---------------------------------------------------------------------------
# Reading a fact off a rendering
# ---------------------------------------------------------------------------


def _bearing(region: _Node, needles: tuple[str, ...], label: str, whose: Any) -> _Node:
    """The smallest element within `region` whose own text states the
    fact — and a named failure where the region states it nowhere, which
    is the "every fact is present in the response" half of the scenario
    this serves."""
    candidates = [
        element
        for element in _within(region)
        if any(needle.lower() in _haystack(element) for needle in needles)
    ]
    if not candidates:
        pytest.fail(
            f"{whose}'s {label} is not rendered at all: nothing within the "
            f"region states any of {list(needles)} "
            f"({_flat(_haystack(region))[:300]!r})"
        )
    return min(candidates, key=_size)


def _reveal_params(world: _World, html: str) -> dict[str, str]:
    """The query the list's reveal control carries, read off the page
    rather than spelled — the pattern `test_launch_admin_list.py`
    records."""
    from urllib.parse import parse_qsl, urlsplit

    for element in _elements(_tree(html)):
        if element.tag != "a" or "href" not in element.attrs:
            continue
        href = element.attrs["href"]
        haystack = f"{_all_text(element)} {href.lower()}"
        if not any(word in haystack for word in _WORDS["reveal"]):
            continue
        carried = dict(parse_qsl(urlsplit(href).query, keep_blank_values=True))
        if carried:
            return carried
    pytest.fail(
        "no control on the list carries a query revealing launches no longer "
        "in play — correct `_reveal_params` / `_WORDS['reveal']` to the "
        "implemented control"
    )
