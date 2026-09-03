"""The launches list's last-completed column, read off the rendered page
(`launch-admin`, `tidy-the-launch-pages-presentation`).

Derived strictly from the delta spec
`openspec/changes/tidy-the-launch-pages-presentation/specs/launch-admin/spec.md`
— the requirement *The list names the completion recorded most recently*
and all six of its scenarios:

- *The most recently recorded completion is named*
- *Recording time governs, not playbook order*
- *Only a completion counts*
- *A tie is broken in a stated direction*
- *A launch with nothing completed says so*
- *The column does not change what is listed*

plus two normative clauses of the same requirement's prose that no
scenario carries: that the row names the step **by its name, never by
its identifier**, and that the recording time is rendered **no coarser
than the minute**. Both are stated as SHALL and both are readable from a
response, so each has a test of its own below.

## Its relationship to `test_launch_admin_last_completed.py`

That file exists in this directory and covers four of the six scenarios
— the latest recording, recording time over playbook order, only
`Satisfied` counting, and the tie — but it covers them **at
`_last_completed` and `_rows_for`**, over stand-in report objects, and
it was written alongside the implementation rather than derived from the
delta. Every scenario above is stated about what a **row** names, and a
choosing function that returns the right answer while the page renders
none of it satisfies none of them; that file's own comment records the
preview where exactly that happened. So the scenarios are derived again
here at the level they are stated at, through the rendered page. Neither
file is redundant with the other and neither is edited by the other's
pass; the manifest records the split.

## Level

The list router mounted in an app of its own, over fakes for the stores
and the catalog read — the level and harness
`test_launch_admin_list.py` established for the same page and
`test_launch_admin_list_presentation.py` reuses, duplicated rather than
imported because this project shares no test-helper module between test
files and `tests/**/test_*.py` is the only path a test may be written
to here.

Every scenario is stated about what the page renders, so nothing above
the router is needed and nothing below it can observe them.

## Expected first-run state

**The target already exists.** This change's implementation is in the
working tree ahead of these tests, which reverses this project's usual
order (`design.md` — Decision 7, `tasks.md` 4a.4). Per
`ai-toolkit:testing`, a pass on the first run is therefore the expected
result and establishes that the page currently behaves as asserted — it
is *not* the fourth failure state. What a pass here does not establish
is that these assertions discriminate; that was established separately,
by re-running each predicate against the same responses with the
column's evidence removed, and is recorded in the manifest.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1427 passed, 0
failed, 2 xfailed, on 2026-08-28. Scoped to the two commit-time tiers,
which are the tiers this file joins; the integration tier was not run
(no database configured here).

## What is fixed, and what is INVENTED

Fixed by the delta:

- That the row names the step whose completion was recorded most
  recently, and when it was recorded.
- That "most recently" is by **recording time**, not by playbook order.
- That only a `Satisfied` outcome counts — the terminal-but-not-
  completed outcomes `Refused` and `NotApplicable` excluded by name
  along with the unresolved ones.
- That a same-instant tie is broken by the report's own order, and that
  the **latest** such step in that order wins.
- That a launch with nothing completed states that, rather than
  rendering an empty cell.
- That the row names the step by its **name**, never its identifier.
- That the recording time is rendered no coarser than the minute.
- That the launches enumerated, their order and any active narrowing are
  what they would be without the column.

INVENTED, each with its correction point named in the code:

- The **wording** of the nothing-completed statement. The delta fixes
  that the row says so, never how. Correction point:
  `_WORDS["nothing_completed"]`. A bare em-dash is deliberately not in
  that list: an em-dash in a cell *is* the empty cell the requirement
  forbids.
- That "the report's own order" is the served order — gate-sequence
  order, and within a gate the authored order — which is what
  `design.md` means by "the authored order `launch-playbook` obliges".
  Computed from the playbook (`SERVED_ORDER`) rather than restated, so
  the expectation cannot drift from the fixture. Correction point:
  `SERVED_ORDER`.
- That a rendered time is read as an `H:MM` token (`_time_tokens`), so
  "no coarser than the minute" is observable without knowing the zone
  the page renders in.
- Every module seam, the render date's injection and how a row is
  located — inherited unchanged from `test_launch_admin_list.py`.
  Correction points: `_SEAMS`, `_render_on`, `_rows`.
- The fixture's dates, recording instants, gates and step identifiers.

Correcting a seam, a wording constant or the row locator is a fixture
correction (failure state 3 in `ai-toolkit:testing`). What must survive
unweakened is what each test asserts: which completion a row names, and
what it says when there is none.
"""

from __future__ import annotations

import asyncio
import importlib
import re
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

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    InProgress,
    LaunchPlaybook,
    NotApplicable,
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
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.playbook import SPECIFIED_GATE_ORDER

# ---------------------------------------------------------------------------
# The module under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so no launch "
            "list is served — the absent-target state, which establishes "
            "nothing about the assertions in this test"
        )


# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

#: SPECIFIED. "the gate narrowing by the `gate` parameter, the
#: needs-attention narrowing by `attention=1`" — used only by the
#: scenario that the column changes neither.
GATE_PARAM: Final = "gate"
ATTENTION_PARAM: Final = "attention"
ATTENTION_VALUE: Final = "1"

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

RECORDER: Final = "Nadia Recorder"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
HEALTHY_DATE: Final = date(2027, 12, 1)

#: Three recording instants, each at a distinct minute of a distinct
#: day, so that a rendering coarser than the minute is distinguishable
#: from one that is not.
EARLY: Final = datetime(2027, 1, 5, 9, 14, tzinfo=UTC)
MIDDLE: Final = datetime(2027, 2, 11, 16, 2, tzinfo=UTC)
LATE: Final = datetime(2027, 3, 2, 11, 47, tzinfo=UTC)
#: One minute after LATE, on the same day and hour. The only difference
#: between the two launches in the minute-precision test.
LATE_PLUS_A_MINUTE: Final = datetime(2027, 3, 2, 11, 48, tzinfo=UTC)

#: The steps this fixture records against. Authored in this order at the
#: `commit` gate, which is where every launch here stands, so that the
#: report's order over them is this order.
COPY_STEP: Final = "listing.copy-approved"
IMAGES_STEP: Final = "listing.images-uploaded"
UNITS_STEP: Final = "inventory.units-received"
BRIEF_STEP: Final = "strategy.brief-signed-off"
PROHIBITED_STEP: Final = "listing.no-incentivised-reviews"

STEP_NAMES: Final[dict[str, str]] = {
    COPY_STEP: "Marketing copy is approved",
    IMAGES_STEP: "Hero and gallery images are uploaded",
    UNITS_STEP: "Units are received into the warehouse",
    BRIEF_STEP: "The launch brief is signed off",
    PROHIBITED_STEP: "No incentivised reviews are solicited",
}

#: INVENTED wording. The delta fixes that the row *states* the absence,
#: never how. A bare dash is excluded on purpose — a dash in the cell is
#: the empty cell the requirement forbids, not a statement of absence.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "nothing_completed": (
        "nothing completed",
        "no completed step",
        "no step completed",
        "nothing recorded",
        "nothing yet",
        "none yet",
        "not yet",
        "no completion",
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
_HIDDEN_CLASSES: Final = ("hidden", "is-hidden", "d-none", "sr-only", "visually-hidden")

#: INVENTED. A time rendered to the minute carries an `H:MM` token; a
#: date alone does not. Correction point for a page rendering the minute
#: some other way.
_TIME_TOKEN: Final = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


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
        "gate": "commit",
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


def _hold(gate: str) -> StepDefinition:
    """A blocking step per gate, left unsatisfied.

    It keeps every launch standing at `commit` with its gate *not*
    awaiting confirmation, so that recording a completion on one of the
    named steps below changes nothing the list orders or bands by. That
    isolation is what the last scenario in this file rests on.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        handler="fixture.holding_check",
    )


def _playbook() -> LaunchPlaybook:
    named = (
        _step(COPY_STEP),
        _step(IMAGES_STEP),
        _step(UNITS_STEP, discipline=INVENTORY),
        _step(BRIEF_STEP),
        _step(PROHIBITED_STEP, hazard=Hazard.PROHIBITED_TACTIC),
    )
    holds = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    ordered = tuple(
        step
        for gate in SPECIFIED_GATE_ORDER
        for step in (*named, *holds)
        if step.gate == gate
    )
    return LaunchPlaybook(version="last-completed-v1", gates=_gates(), steps=ordered)


PLAYBOOK: Final = _playbook()

#: The order the served playbook hands its steps over in: gate-sequence
#: order, and within a gate the authored order. Computed from the domain
#: rather than restated, so the tie-break expectation cannot drift from
#: the fixture.
SERVED_ORDER: Final = tuple(
    step.identifier
    for gate in SPECIFIED_GATE_ORDER
    for step in PLAYBOOK.steps_for_gate(gate)
)


def _provenance(when: datetime) -> Provenance:
    return Provenance(
        source="clickup",
        who=RECORDER,
        when=when,
        evidence="screenshot in the launch Slack thread",
    )


def _start(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=launch_date
    )
    return launch


def _record(launch: Launch, step_id: str, outcome: Any, when: datetime) -> None:
    launch.record_step_outcome(
        PLAYBOOK, step_id=step_id, outcome=outcome, provenance=_provenance(when)
    )


def _completed(
    product_id: ProductId,
    *completions: tuple[str, datetime],
    launch_date: date | None = HEALTHY_DATE,
) -> Launch:
    launch = _start(product_id, launch_date)
    for step_id, when in completions:
        _record(launch, step_id, Satisfied, when)
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
class _Surface:
    client: TestClient
    module: ModuleType


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launches: _FakeLaunchStore,
    catalog: _Catalog,
    day: date = RENDER_DATE,
) -> _Surface:
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)
    _render_on(monkeypatch, module, day)

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, module)


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
    # locator survives once that route exists alongside this one.
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
        "routes not mentioning 'journal'"
    )
    return str(candidates[0])


def _get(surface: _Surface, params: dict[str, str] | None = None) -> str:
    response = surface.client.get(_list_path(surface.module), params=params)
    assert response.status_code == 200, (
        f"the list was not served: {response.status_code} {response.text[:400]}"
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


def _raw_text(node: _Node) -> str:
    """The element's rendered text, case preserved — what a reader sees."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_raw_text(child))
    return " ".join(part for part in found if part)


def _all_text(node: _Node) -> str:
    return _raw_text(node).lower()


def _attribute_text(node: _Node) -> str:
    parts = [
        value
        for element in (node, *_elements(node))
        for key, value in element.attrs.items()
        if key in ("class", "title", "aria-label", "id") or key.startswith("data-")
    ]
    return " ".join(parts).lower()


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _says(node: _Node, key: str) -> bool:
    haystack = f"{_all_text(node)} {_attribute_text(node)}"
    return any(word in haystack for word in _WORDS[key])


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


# ---------------------------------------------------------------------------
# Rows, read off a rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    product_id: str
    node: _Node


def _detail_links(root: _Node, module: ModuleType) -> list[tuple[str, _Node]]:
    template = _detail_template(module)
    prefix = template[: template.index("{")]
    found: list[tuple[str, _Node]] = []
    for element in _elements(root):
        if element.tag != "a":
            continue
        path = urlsplit(element.attrs.get("href", "")).path
        if not path.startswith(prefix) or path == prefix:
            continue
        remainder = path[len(prefix) :].strip("/")
        if remainder and "/" not in remainder:
            found.append((remainder, element))
    return found


def _rows(html: str, module: ModuleType) -> list[_Row]:
    """Every rendered row, in document order — the locator
    `test_launch_admin_list.py` established: the smallest element
    holding exactly one launch's detail link."""
    root = _tree(html)
    rows: list[_Row] = []
    seen: set[str] = set()
    for product_id, link in _detail_links(root, module):
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
            _Row(product_id, min(containers, key=_size) if containers else link)
        )
    return rows


def _rendered_ids(html: str, module: ModuleType) -> list[str]:
    return [row.product_id for row in _rows(html, module)]


def _row_for(surface: _Surface, html: str, product_id: ProductId) -> _Row:
    for row in _rows(html, surface.module):
        if row.product_id == product_id.value:
            return row
    pytest.fail(
        f"no row for {product_id.value} was rendered; the page rendered "
        f"{_rendered_ids(html, surface.module)}"
    )


def _names_step(row: _Row, step_id: str) -> bool:
    """Whether the row names that step — by its **name**, which is the
    only way the requirement permits a step to be named."""
    return STEP_NAMES[step_id].lower() in _all_text(row.node)


def _time_tokens(row: _Row) -> list[str]:
    """The `H:MM` tokens the row renders.

    INVENTED reading of "no coarser than the minute": a time rendered to
    the minute carries one; a date alone does not. Correction point for
    a page rendering a minute some other way.
    """
    return _TIME_TOKEN.findall(_raw_text(row.node))


def _shown(row: _Row) -> str:
    return _flat(_raw_text(row.node))


# ===========================================================================
# Requirement: The list names the completion recorded most recently
# ===========================================================================


def test_the_most_recently_recorded_completion_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The most recently recorded completion is named.

    WHEN a listed launch has two completed steps recorded at different
    times
    THEN its row names the one recorded later, and when it was recorded.

    The second launch carries only the earlier of the same two
    completions. It is what makes the "and when it was recorded" half
    readable without knowing the zone the page renders in: two rows that
    named their completions correctly but rendered one fixed instant
    would pass the first half and fail here.
    """
    two = _launching("PX-100", "Alpha widget")
    one = _launching("PX-200", "Beta widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _completed(two.id, (COPY_STEP, EARLY), (IMAGES_STEP, LATE)),
            _completed(one.id, (COPY_STEP, EARLY)),
        ),
        catalog=_Catalog(two, one),
    )

    html = _get(surface)
    later = _row_for(surface, html, two.id)
    earlier = _row_for(surface, html, one.id)

    # SPECIFIED: the row names the completion recorded later.
    assert _names_step(later, IMAGES_STEP), (
        "the row does not name the step whose completion was recorded most "
        f"recently ({STEP_NAMES[IMAGES_STEP]!r}): {_shown(later)!r}"
    )
    # SPECIFIED: and not the one recorded earlier, which is the whole of
    # what "most recently" decides between.
    assert not _names_step(later, COPY_STEP), (
        "the row names the earlier completion as well as the later one, so it "
        f"does not name *the* most recent one: {_shown(later)!r}"
    )
    # SPECIFIED: and when it was recorded — read as the time tracking the
    # completion named, not as a constant the page renders on every row.
    assert _time_tokens(later) and _time_tokens(earlier), (
        "a row renders no time at all, so it does not say when the completion "
        f"it names was recorded: {_shown(later)!r} / {_shown(earlier)!r}"
    )
    assert _time_tokens(later) != _time_tokens(earlier), (
        "both rows render the same time although they name completions "
        f"recorded a month apart: {_shown(later)!r} / {_shown(earlier)!r}"
    )


def test_recording_time_governs_not_playbook_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Recording time governs, not playbook order.

    WHEN a listed launch has a completion recorded today for a step
    earlier in the playbook than one recorded last week
    THEN its row names the step recorded today.

    This is the case the two candidate readings disagree on, so it is the
    one assertion that establishes which reading the page took.
    """
    backfilled = _launching("PX-100", "Alpha widget")
    assert SERVED_ORDER.index(COPY_STEP) < SERVED_ORDER.index(UNITS_STEP), (
        "the fixture no longer places the backfilled step earlier in the "
        "playbook than the one completed before it, so this test would no "
        "longer distinguish the two readings — correct the fixture"
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _completed(backfilled.id, (COPY_STEP, LATE), (UNITS_STEP, MIDDLE))
        ),
        catalog=_Catalog(backfilled),
    )

    row = _row_for(surface, _get(surface), backfilled.id)

    # SPECIFIED: the step recorded most recently, though it is earlier in
    # the playbook than one already completed.
    assert _names_step(row, COPY_STEP), (
        "the row does not name the step whose completion was recorded most "
        f"recently, which is earlier in the playbook: {_shown(row)!r}"
    )
    assert not _names_step(row, UNITS_STEP), (
        "the row names the step further along the playbook, so the column "
        f"reads by playbook order rather than by recording time: {_shown(row)!r}"
    )


def test_only_a_completion_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Only a completion counts.

    WHEN a listed launch has one step completed earlier and a
    **different** step whose most recent recording is an outcome other
    than completion
    THEN its row names the completed step, not the more recently
    recorded one.

    Three such steps rather than one, because the requirement excludes
    two kinds of outcome for two different reasons: the unresolved ones
    (`Blocked` here) and the terminal-but-not-completed ones (`Refused`
    and `NotApplicable`, both named in the requirement's own prose).
    """
    launch_product = _launching("PX-100", "Alpha widget")
    launch = _completed(launch_product.id, (COPY_STEP, EARLY))
    _record(launch, UNITS_STEP, Blocked(reason="the freight forwarder has it"), LATE)
    _record(launch, PROHIBITED_STEP, Refused, LATE)
    _record(
        launch,
        BRIEF_STEP,
        NotApplicable(reason="this marketplace asks for no brief"),
        LATE,
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(launch_product),
    )

    row = _row_for(surface, _get(surface), launch_product.id)

    # SPECIFIED: the completed step, though three later recordings exist.
    assert _names_step(row, COPY_STEP), (
        f"the row does not name the launch's only completed step: {_shown(row)!r}"
    )
    # SPECIFIED: not the unresolved outcome recorded later.
    assert not _names_step(row, UNITS_STEP), (
        "the row names a step recorded as blocked, so a step that was never "
        f"completed reads as the launch's latest completion: {_shown(row)!r}"
    )
    # SPECIFIED: nor either terminal outcome that is not a completion.
    assert not _names_step(row, PROHIBITED_STEP), (
        "the row names a step recorded as refused — resolved without being "
        f"completed, which the requirement excludes by name: {_shown(row)!r}"
    )
    assert not _names_step(row, BRIEF_STEP), (
        "the row names a step recorded as not applicable — resolved without "
        f"being completed, which the requirement excludes by name: "
        f"{_shown(row)!r}"
    )


def test_a_tie_is_broken_in_a_stated_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A tie is broken in a stated direction.

    WHEN two of a launch's steps are completed and recorded at the same
    instant
    THEN its row names the later of the two in the report's order, on
    every rendering.

    The winner is computed from the playbook rather than restated, so the
    assertion cannot silently agree with a fixture that was reordered.
    "On every rendering" is read as two renderings of the same state
    agreeing — the failure it guards against is a tie broken by a set's
    iteration order, which is stable within a process but not across
    equal inputs.
    """
    tied = _launching("PX-100", "Alpha widget")
    first, second = COPY_STEP, UNITS_STEP
    expected = max((first, second), key=SERVED_ORDER.index)
    loser = first if expected == second else second
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_completed(tied.id, (first, LATE), (second, LATE))),
        catalog=_Catalog(tied),
    )

    renderings = [_row_for(surface, _get(surface), tied.id) for _ in range(2)]

    for row in renderings:
        # SPECIFIED: the latest of the tied steps in the report's order.
        assert _names_step(row, expected), (
            f"two completions recorded at the same instant, and the row does "
            f"not name {STEP_NAMES[expected]!r}, which is the later of the two "
            f"in the report's order: {_shown(row)!r}"
        )
        assert not _names_step(row, loser), (
            f"the row names {STEP_NAMES[loser]!r}, the earlier of the two tied "
            f"steps in the report's order: {_shown(row)!r}"
        )
    # SPECIFIED: on every rendering.
    assert _shown(renderings[0]) == _shown(renderings[1]), (
        "two renderings of the same launch resolve the tie differently: "
        f"{_shown(renderings[0])!r} then {_shown(renderings[1])!r}"
    )


def test_a_launch_with_nothing_completed_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch with nothing completed says so.

    WHEN a listed launch has no completed step
    THEN its row states that nothing has been completed, rather than
    rendering an empty cell.

    The launch is not untouched: one step is recorded as blocked and one
    as in progress, so a row that named "the latest recording" rather
    than "the latest completion" would have something to name and would
    fail the second assertion.
    """
    nothing = _launching("PX-100", "Alpha widget")
    launch = _start(nothing.id)
    _record(launch, UNITS_STEP, Blocked(reason="the freight forwarder has it"), LATE)
    _record(launch, IMAGES_STEP, InProgress, MIDDLE)
    _record(launch, COPY_STEP, NotStarted, EARLY)
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(launch), catalog=_Catalog(nothing)
    )

    row = _row_for(surface, _get(surface), nothing.id)

    # SPECIFIED: the row states the absence.
    assert _says(row.node, "nothing_completed"), (
        "the row of a launch with nothing completed states no absence, so the "
        "column reads as a fact the page failed to fetch: "
        f"{_shown(row)!r} — correct `_WORDS['nothing_completed']` if the page "
        "words it differently"
    )
    # SPECIFIED: and names no step, because none was completed.
    for step_id in (COPY_STEP, IMAGES_STEP, UNITS_STEP):
        assert not _names_step(row, step_id), (
            f"the row names {STEP_NAMES[step_id]!r} although that step was "
            f"never completed: {_shown(row)!r}"
        )


def test_the_column_does_not_change_what_is_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The column does not change what is listed.

    WHEN the list is rendered
    THEN the launches enumerated, their order and any active narrowing
    are what they would be without this column.

    Read as: the fact's presence or absence changes none of the three.
    Two worlds are rendered whose launches are identical in every
    respect the list enumerates, orders or narrows by, and differ only in
    which completions are recorded on them — recorded on **non-blocking**
    steps, so no gate opens and no attention state moves. Anything the
    two renderings disagree on is the column changing what is listed.

    Each world is rendered inside its own `monkeypatch` context and its
    responses captured before the next is built. The two worlds install
    their seams on the *same* module object, so a second world built
    before the first has been read replaces the first's store and the
    comparison silently becomes a page against itself.
    """
    identities = [
        _launching("PX-100", "Alpha widget"),
        _launching("PX-200", "Beta widget"),
        _launching("PX-300", "Gamma widget"),
    ]
    dates = [HEALTHY_DATE, date(2027, 9, 3), None]
    narrowings: tuple[tuple[str, dict[str, str] | None], ...] = (
        ("unnarrowed", None),
        ("under a gate narrowing", {GATE_PARAM: "commit"}),
        ("under the needs-attention narrowing", {ATTENTION_PARAM: ATTENTION_VALUE}),
        ("under a gate narrowing matching nothing", {GATE_PARAM: "graduated"}),
    )

    def _render(with_completions: bool) -> dict[str, str]:
        launches = []
        for index, (product, launch_date) in enumerate(zip(identities, dates)):
            completions = (
                ((COPY_STEP, EARLY), (IMAGES_STEP, LATE))[: index + 1]
                if with_completions
                else ()
            )
            launches.append(
                _completed(product.id, *completions, launch_date=launch_date)
            )
        with pytest.MonkeyPatch.context() as patching:
            surface = _surface(
                patching,
                launches=_FakeLaunchStore(*launches),
                catalog=_Catalog(*identities),
            )
            return {label: _get(surface, params) for label, params in narrowings}

    module = _page_module()
    with_column = _render(True)
    without = _render(False)

    for label, _params in narrowings:
        listed = _rendered_ids(with_column[label], module)
        unlisted = _rendered_ids(without[label], module)
        # SPECIFIED: the launches enumerated, and their order, are what
        # they would be without the column.
        assert listed == unlisted, (
            f"{label}, the list renders {listed} when completions are recorded "
            f"and {unlisted} when none are, so the column changes what is "
            "listed or the order it is listed in"
        )

    # DERIVED guard: the comparison above is only worth anything if the
    # unnarrowed list actually rendered rows, and if the fact really is
    # present in one world and absent in the other. Without it, two
    # renderings of the same world compare equal and the test passes
    # having observed nothing — which is how this test first ran.
    populated = with_column["unnarrowed"]
    assert len(_rendered_ids(populated, module)) == len(identities), (
        "the fixture's launches are not all listed, so the comparison above "
        "ranges over fewer rows than it appears to"
    )
    named = [
        row
        for row in _rows(populated, module)
        if _names_step(row, COPY_STEP) or _names_step(row, IMAGES_STEP)
    ]
    assert named, (
        "no completion is named anywhere in the populated world, so the two "
        "worlds do not differ and the comparison observed nothing: "
        f"{_shown(_rows(populated, module)[0])!r}"
    )
    unnamed = [
        row
        for row in _rows(without["unnarrowed"], module)
        if _names_step(row, COPY_STEP) or _names_step(row, IMAGES_STEP)
    ]
    assert not unnamed, (
        "a completion is named in the world where none was recorded, so the "
        "two worlds are the same world"
    )


# ===========================================================================
# Two normative clauses of the same requirement that carry no scenario
# ===========================================================================


def test_the_row_names_the_step_by_name_never_by_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clause: "The row SHALL name the step by its **name**, never by its
    identifier — the identifier is opaque, and this capability already
    keeps opaque identifiers off a row that resolved."

    No scenario carries it, and it is readable from a response, so it has
    a test of its own.
    """
    named = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_completed(named.id, (IMAGES_STEP, LATE))),
        catalog=_Catalog(named),
    )

    row = _row_for(surface, _get(surface), named.id)

    # SPECIFIED: named by its name.
    assert _names_step(row, IMAGES_STEP), (
        f"the row does not name the completed step: {_shown(row)!r}"
    )
    # SPECIFIED: never by its identifier.
    assert (
        IMAGES_STEP.lower() not in f"{_all_text(row.node)} {_attribute_text(row.node)}"
    ), (
        f"the row renders the step identifier {IMAGES_STEP!r}, which is opaque "
        f"and which this capability keeps off a row that resolved: "
        f"{_shown(row)!r}"
    )


def test_the_recording_time_is_rendered_no_coarser_than_the_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clause: "The recording time SHALL be rendered no coarser than the
    minute."

    Two launches identical in everything the row renders — same product
    name, same launch date, same gate, same completed step — whose
    completions were recorded one minute apart. A page rendering the day
    alone, or the hour, renders the two rows identically; a page
    rendering the minute cannot. The check is therefore independent of
    which zone the page renders in, which the sibling clause about the
    zone is what constrains.
    """
    one = _launching("PX-100", "Alpha widget")
    other = _launching("PX-200", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _completed(one.id, (COPY_STEP, LATE)),
            _completed(other.id, (COPY_STEP, LATE_PLUS_A_MINUTE)),
        ),
        catalog=_Catalog(one, other),
    )

    html = _get(surface)
    first = _row_for(surface, html, one.id)
    second = _row_for(surface, html, other.id)

    # SPECIFIED: a time to the minute is rendered at all.
    assert _time_tokens(first), (
        f"the row renders no time to the minute: {_shown(first)!r} — correct "
        "`_TIME_TOKEN` if the page renders one some other way"
    )
    # SPECIFIED: and it is no coarser than the minute — two recordings a
    # minute apart do not render the same.
    assert _time_tokens(first) != _time_tokens(second), (
        "two completions recorded one minute apart render the same time, so "
        f"the recording time is rendered coarser than the minute: "
        f"{_shown(first)!r} / {_shown(second)!r}"
    )
