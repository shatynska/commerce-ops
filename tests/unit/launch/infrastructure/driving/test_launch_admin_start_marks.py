"""A launch's detail page marks a step that has not started
(`launch-admin`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-admin/spec.md`
— its one ADDED requirement, *A launch's detail page distinguishes a step
that has not started*, and all seven of its scenarios.

The manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
accounts for every scenario in the change.

## Level

The launch router over fakes for the stores and the catalog read — the
level and the seam-installing harness `test_launch_admin_detail.py`
establishes, reproduced here rather than imported because this project
shares no test-helper module between test files.

## How a "mark" is read off a rendered page

**Differentially**, so that no wording is pinned. The fixture playbook
carries, at one gate, three steps identical in every respect the page
renders except their start declarations: one released, one held by its
start gate, one held by an unresolved dependency. What a step's own row
says that the *released* step's row does not is what that step was
marked with.

That is what makes *Unreleased is distinguishable from unrecorded*
assertable at all — all three are unrecorded, so anything separating
them is the release mark and nothing else. It is also what makes *The
page carries no third sense of blocked* assertable without forbidding
the word on a page that legitimately renders "Blocks its gate" and the
`Blocked` outcome: the prohibition is read against the *added* text
alone.

Correction points: `_row_of` (how a step's row is located) and `_added`
(the differential). Both fail loudly rather than defaulting.

## INVENTED, with correction points

Inherited from `test_launch_admin_detail.py`: the page module, `_SEAMS`,
`_render_on`, the session cookie, the detail route's discovery, and
`_WORDS["overdue"]` as the overdue mark's wording. Added here:
`starts_at_gate` / `after_steps` as constructor keywords on
`StepDefinition` (correction point: `_step`).

## Expected first-run state

`starts_at_gate` does not exist, so every test here is expected to fail
on an **absent target** (`TypeError` from the constructor). That
establishes absence and nothing about these assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
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

from commerce_ops.access.application import create_person
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    return importlib.import_module(_PAGE_MODULE_NAME)


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
LAUNCH_DATE: Final = date(2027, 4, 15)

#: Step identifiers, chosen so each is unique text on the page.
RELEASED_STEP: Final = "listing.released-and-unrecorded"
HELD_BY_GATE: Final = "listing.held-by-its-start-gate"
HELD_BY_DEPENDENCY: Final = "listing.held-by-a-dependency"
DEPENDENCY_STEP: Final = "listing.the-dependency-it-waits-on"
COMMIT_STEP: Final = "strategy.commitment-agreed"

STEP_NAMES: Final[dict[str, str]] = {
    RELEASED_STEP: "Work released and not yet recorded",
    HELD_BY_GATE: "Work held by the gate it starts at",
    HELD_BY_DEPENDENCY: "Work held by the step it waits on",
    DEPENDENCY_STEP: "Work another step waits on",
    COMMIT_STEP: "Commitment to launch is agreed",
}

#: INVENTED wording for the overdue mark, taken unchanged from
#: `test_launch_admin_detail.py`.
_OVERDUE_WORDS: Final = ("overdue", "past due", "overrun", "behind schedule")

#: SPECIFIED prohibition: the mark's wording "SHALL NOT use *blocked* or
#: any inflection of it".
_BLOCKED_INFLECTIONS: Final = ("block", "blocks", "blocked", "blocking")

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
        "name": STEP_NAMES.get(identifier, "Work this step asks for"),
        "description": None,
        "gate": "listable",
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _detail_playbook() -> LaunchPlaybook:
    """Three `listable` steps identical but for their start declarations,
    plus the blocking work holding each gate.

    All three carry the same anchor (-30, a due period fully past on the
    render date) and no recorded outcome, so nothing but the start
    declaration distinguishes them — which is what the differential
    below depends on.
    """
    steps = (
        _step(
            COMMIT_STEP,
            gate="commit",
            blocking=True,
            timing_anchor=OffsetAnchor(days=365),
        ),
        _step(RELEASED_STEP),
        _step(HELD_BY_GATE, starts_at_gate="listable"),
        _step(
            DEPENDENCY_STEP,
            gate="commit",
            timing_anchor=OffsetAnchor(days=365),
        ),
        _step(
            HELD_BY_DEPENDENCY,
            starts_at_gate="commit",
            after_steps=(DEPENDENCY_STEP,),
        ),
    )
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(
        _step(
            f"hold.{gate}",
            gate=gate,
            blocking=True,
            timing_anchor=OffsetAnchor(days=365),
        )
        for gate in SPECIFIED_GATE_ORDER
        if gate not in held
    )
    return LaunchPlaybook(
        version="start-marks-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _served_order(playbook: LaunchPlaybook) -> tuple[str, ...]:
    return tuple(
        step.identifier
        for gate in SPECIFIED_GATE_ORDER
        for step in playbook.steps_for_gate(gate)
    )


def _start(product_id: ProductId, playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Ports
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

    async def save(self, launch: Launch) -> None:
        self.order.append(launch)

    async def list_all(self, *_args: Any, **_kwargs: Any) -> tuple[Launch, ...]:
        return tuple(self.order)

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)

    async def list_launches(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


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
# Seams — the single correction point
# ---------------------------------------------------------------------------

_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "roster": ("roster", "people", "roster_store", "read_roster"),
    "list_products": ("list_products", "products", "catalog_products"),
    "get_product_by_id": ("get_product_by_id", "product_by_id", "get_product"),
}
_JOURNAL_SEAM_NAMES: Final = (
    "read_journal",
    "journal",
    "read_launch_journal",
    "journal_entries",
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
        "`date`)"
    )


@dataclass(frozen=True)
class _Surface:
    client: TestClient
    module: ModuleType


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    launch: Launch,
    product: Product,
    playbook: LaunchPlaybook,
) -> _Surface:
    module = _page_module()
    catalog = _Catalog(product)
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", _FakeLaunchStore(launch))
    _install(monkeypatch, module, "playbooks", _FakePlaybooks(playbook))
    _install(monkeypatch, module, "roster", asyncio.run(_build_roster()))
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    async def _no_journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    for name in _JOURNAL_SEAM_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, _no_journal)
            break
    _render_on(monkeypatch, module, RENDER_DATE)

    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, module)


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
        "routes not mentioning 'journal'; exactly one detail route is expected"
    )
    return candidates[0]


def _detail_html(surface: _Surface, product_id: ProductId) -> str:
    template = _detail_template(surface.module)
    opened = template.index("{")
    closed = template.index("}", opened)
    path = template[:opened] + product_id.value + template[closed + 1 :]
    response = surface.client.get(path, follow_redirects=True)
    assert response.status_code == 200, (
        f"the detail page was not served: {response.status_code} {response.text[:400]}"
    )
    return str(response.text)


# ---------------------------------------------------------------------------
# An HTML tree, and reading a step's row off it
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
            self._stack[-1].children.append(_Text(data))


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
    return " ".join(part for part in found if part.strip())


def _haystack(node: _Node) -> str:
    attributes = " ".join(
        value
        for element in (node, *_elements(node))
        for value in element.attrs.values()
    )
    return " ".join((_all_text(node), attributes)).lower()


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


def _outside_start_mark(node: _Node, needle: str) -> bool:
    """Whether `needle` appears in `node` other than inside a start mark.

    The locator below is looking for a row that stands for exactly one
    step. A row *may* legitimately name another step now — the start mark
    states the steps this one waits on, which the capability requires it
    to say — so that mention must not make the row read as belonging to
    two steps. Everything outside the mark still must.
    """
    for element in _elements(node):
        classes = str(element.attrs.get("class", ""))
        if "starts" in classes and _holds(element, needle):
            return _holds(node, needle) and not _only_within(node, needle)
    return _holds(node, needle)


def _only_within(node: _Node, needle: str) -> bool:
    """Whether every occurrence of `needle` in `node` sits inside a start
    mark."""
    marks = [
        element
        for element in _elements(node)
        if "starts" in str(element.attrs.get("class", ""))
    ]
    if not marks:
        return False
    occurrences = _haystack(node).count(needle.lower())
    inside = sum(_haystack(mark).count(needle.lower()) for mark in marks)
    return occurrences > 0 and occurrences == inside


def _row_of(html: str, step_id: str, served: tuple[str, ...]) -> _Node:
    """The smallest element holding that step's identifier and its name,
    and no other served step *except* one its start mark names.

    INVENTED locator, taken from `test_launch_admin_detail.py`, and
    widened here: that file predates a row being able to name another
    step, which the start mark now does by requirement. Fails loudly
    rather than returning the document, which would make every
    differential below vacuous.
    """
    root = _tree(html)
    others = [other for other in served if other != step_id]
    mine = [
        element
        for element in _elements(root)
        if _holds(element, step_id)
        and not any(
            _holds(element, other) and not _only_within(element, other)
            for other in others
        )
        and _holds(element, STEP_NAMES[step_id])
    ]
    if not mine:
        pytest.fail(
            f"no element on the detail page holds {step_id!r} and its name "
            "without also holding another served step, so the step's own "
            "marks cannot be read off one row — correct `_row_of`"
        )
    return min(mine, key=lambda element: len(_haystack(element)))


def _gate_group(html: str, gate: str, playbook: LaunchPlaybook) -> _Node:
    """The smallest element holding every step of `gate` and no step of
    another gate, except where another gate's step is named only by a
    start mark.

    Widened for the same reason `_row_of` is: a step's start mark states
    the steps it waits on, and one of those may belong to another gate.
    Such a mention does not make the group hold that step — the group
    holds the row of every step at this gate and the row of none other,
    which is what the grouping requirement is about.
    """
    root = _tree(html)
    mine = [step.identifier for step in playbook.steps_for_gate(gate)]
    theirs = [step_id for step_id in _served_order(playbook) if step_id not in mine]
    candidates = [
        element
        for element in _elements(root)
        if all(_holds(element, step_id) for step_id in mine)
        and not any(
            _holds(element, other) and not _only_within(element, other)
            for other in theirs
        )
    ]
    if not candidates:
        pytest.fail(
            f"no element on the detail page groups the {gate!r} gate's steps "
            "apart from every other gate's — correct `_gate_group`"
        )
    return min(candidates, key=lambda element: len(_haystack(element)))


def _words_of(node: _Node) -> set[str]:
    return {word for word in _haystack(node).replace(",", " ").split() if word}


def _added(html: str, step_id: str, served: tuple[str, ...]) -> set[str]:
    """The words a step's row carries that the released step's row does
    not — the mark, whatever it says.

    The two rows differ in exactly one respect the page could render
    (their start declarations) plus their own identifiers and names,
    which are subtracted here so they cannot be mistaken for a mark.
    """
    subject = _words_of(_row_of(html, step_id, served))
    control = _words_of(_row_of(html, RELEASED_STEP, served))
    own = {
        word
        for identifier in (step_id, RELEASED_STEP, DEPENDENCY_STEP)
        for word in (identifier.lower(), *STEP_NAMES[identifier].lower().split())
    }
    return (subject - control) - own


@dataclass(frozen=True)
class _Rendered:
    """One rendered detail page, with the playbook it was rendered from.

    The playbook is built per test rather than at module scope: it is
    constructed with fields that do not exist yet, and a module-scope
    construction would fail at *collection* — taking every test in the
    file down as one error rather than letting each report its own
    absent target.
    """

    html: str
    playbook: LaunchPlaybook

    @property
    def served(self) -> tuple[str, ...]:
        return _served_order(self.playbook)


@pytest.fixture()
def rendered(monkeypatch: pytest.MonkeyPatch) -> _Rendered:
    playbook = _detail_playbook()
    product = _launching("BCB-2027-01", "Bamboo Cutting Board")
    launch = _start(product.id, playbook)
    assert launch.current_gate == "commit"
    surface = _surface(monkeypatch, launch, product, playbook)
    return _Rendered(_detail_html(surface, product.id), playbook)


# ---------------------------------------------------------------------------
# ADDED Requirement: A launch's detail page distinguishes a step that has
# not started
# ---------------------------------------------------------------------------


def test_an_unreleased_step_is_rendered_not_hidden(rendered: _Rendered) -> None:
    """Scenario: An unreleased step is rendered, not hidden.

    WHEN a launch standing at `commit` is rendered and its served
    playbook carries steps that start at `listable`
    THEN those steps appear on the page under their own gates.

    SPECIFIED reason: "the page exists to show the launch's whole plan
    against its position, and a page showing less than the playbook would
    misrepresent what the launch is committed to".
    """
    group = _gate_group(rendered.html, "listable", rendered.playbook)
    listable = [
        step.identifier for step in rendered.playbook.steps_for_gate("listable")
    ]

    for step_id in listable:
        assert _holds(group, step_id), (
            f"{step_id!r} is not rendered under the `listable` gate; an "
            "unreleased step must be shown, never hidden"
        )


def test_an_unreleased_step_says_what_it_waits_for(rendered: _Rendered) -> None:
    """Scenario: An unreleased step says what it waits for.

    WHEN a step the launch has not released is rendered
    THEN it carries a mark naming the gate it starts at, the steps it
    waits on, or both.
    """
    by_gate = _row_of(rendered.html, HELD_BY_GATE, rendered.served)
    by_dependency = _row_of(rendered.html, HELD_BY_DEPENDENCY, rendered.served)

    # SPECIFIED: the step held by its start gate names that gate.
    assert _holds(by_gate, "listable"), (
        "a step held by its start gate does not name the gate it starts at"
    )
    # SPECIFIED: the step held by a dependency names the step it waits on.
    assert _holds(by_dependency, DEPENDENCY_STEP), (
        "a step held by an unresolved dependency does not name that "
        "dependency, so a reader cannot tell what it is waiting for"
    )


def test_unreleased_is_distinguishable_from_unrecorded(
    rendered: _Rendered,
) -> None:
    """Scenario: Unreleased is distinguishable from unrecorded.

    WHEN a page renders one released step with no recorded outcome and
    one unreleased step with no recorded outcome
    THEN the two are distinguishable from one another on the page.

    Both fixture steps are unrecorded and identical in every other
    respect the page renders, so anything separating them is the release
    mark.
    """
    assert _added(rendered.html, HELD_BY_GATE, rendered.served), (
        "a released unrecorded step and an unreleased unrecorded step render "
        "identically, so a reader cannot tell work outstanding from work not "
        "yet asked for"
    )


def test_a_released_step_carries_no_such_mark(rendered: _Rendered) -> None:
    """Scenario: A released step carries no such mark.

    WHEN a step the launch has released is rendered
    THEN it carries no start mark, whatever it declares.

    Asserted the other way round from the differential: the released
    step's row carries none of the words the unreleased rows added.
    """
    released_row = _words_of(_row_of(rendered.html, RELEASED_STEP, rendered.served))
    marks = _added(rendered.html, HELD_BY_GATE, rendered.served) | _added(
        rendered.html, HELD_BY_DEPENDENCY, rendered.served
    )

    assert not (released_row & marks), (
        "the released step's row carries "
        f"{sorted(released_row & marks)}, which the page uses to mark an "
        "unreleased step"
    )


def test_a_step_whose_start_gate_is_not_reached_is_never_marked_overdue(
    rendered: _Rendered,
) -> None:
    """Scenario: A step whose start gate is not reached is never marked
    overdue.

    WHEN a step whose start gate the launch has not reached has a due
    period that has passed
    THEN it is not marked overdue, the launch report not stating it as
    overdue.

    SPECIFIED: "The page SHALL NOT reach that conclusion itself" — which
    is why the assertion is on the rendering while the rule lives in
    `launch-instance`, covered by
    `tests/unit/launch/application/test_launch_report_release.py`.
    """
    row = _haystack(_row_of(rendered.html, HELD_BY_GATE, rendered.served))

    assert not any(word in row for word in _OVERDUE_WORDS), (
        "a step whose start gate the launch has not reached is marked "
        "overdue, attributing a failure to whoever the step names for work "
        "nobody asked them for"
    )


def test_a_step_waiting_on_a_dependency_can_be_both_overdue_and_waiting(
    rendered: _Rendered,
) -> None:
    """Scenario: A step waiting on a dependency can be both overdue and
    waiting.

    WHEN a step the launch has reached waits on an unresolved dependency
    and the report states it as overdue
    THEN the page renders both the overdue mark and the mark naming what
    it waits for.

    SPECIFIED: "The two say different things — the work is late, and this
    is what it is late behind — and a reader needs them together."
    """
    row = _row_of(rendered.html, HELD_BY_DEPENDENCY, rendered.served)
    text = _haystack(row)

    # SPECIFIED: the overdue mark.
    assert any(word in text for word in _OVERDUE_WORDS), (
        "a step held only by an unresolved dependency, whose due period has "
        "passed, is not marked overdue — the exclusion turns on the start "
        "gate alone"
    )
    # SPECIFIED: and the mark naming what it waits for, rendered together
    # rather than either suppressing the other.
    assert _holds(row, DEPENDENCY_STEP)


def test_the_page_carries_no_third_sense_of_blocked(rendered: _Rendered) -> None:
    """Scenario: The page carries no third sense of blocked.

    WHEN the detail page is rendered for a launch with unreleased steps
    THEN no mark introduced for release uses the word *blocked* or an
    inflection of it.

    SPECIFIED reason: "This surface already renders a step's `blocking`
    declaration and the `Blocked` step outcome, which are two distinct
    senses of the word on one page; a third would make the page
    unreadable."

    Asserted against the *added* text alone, so the page keeps its
    existing, legitimate uses of the word.
    """
    for step_id in (HELD_BY_GATE, HELD_BY_DEPENDENCY):
        marks = _added(rendered.html, step_id, rendered.served)
        offending = sorted(
            word
            for word in marks
            if any(inflection in word for inflection in _BLOCKED_INFLECTIONS)
        )
        assert not offending, (
            f"the mark on {step_id!r} uses {offending}; the wording must be "
            "drawn from *starting*, never from *blocked*"
        )
