"""The launches list's narrowing bar and its row identity
(`launch-admin`, `tidy-the-launch-pages-presentation`).

Derived strictly from the delta spec
`openspec/changes/tidy-the-launch-pages-presentation/specs/launch-admin/spec.md`
— two of its three ADDED requirements and all 13 of their scenarios:

- *The list's narrowing is one bar of peer controls* (9 scenarios)
- *A row names its product, and falls back to the raw identifier only
  when it must* (4 scenarios)

The third requirement, *The shared vocabulary carries rules for what
these surfaces render*, is covered in
`test_launch_surface_vocabulary_rules.py` in this directory, which needs
the detail page and the four sibling admin surfaces this file does not.
The manifest at
`openspec/changes/tidy-the-launch-pages-presentation/test-manifest.md`
records every scenario, every assertion's classification and every
project question answered here by assumption.

## Level

The list router mounted in an app of its own, over fakes for the stores
and the catalog read — the level and harness
`test_launch_admin_list.py` established for the same page, duplicated
rather than imported because this project shares no test-helper module
between test files and `tests/**/test_*.py` is the only path a test may
be written to here.

Every scenario below is stated about what the *page* renders or about
the request a control on it submits, so nothing above the router is
needed and nothing below it can observe them.

## What this file deliberately does NOT cover

The requirement's own prose says so outright: that the bar occupies one
line, that no control runs to the container's width, and that a row
reads as a row are not scenarios and "SHALL be confirmed by direct
inspection of the rendered page" (`tasks.md` 6.1, 6.3). The markers
asserted below are a necessary condition, not a sufficient one, and an
assertion pretending otherwise would be worse than the gap.

## Expected first-run state

**The change is not implemented.** The page, its route and its narrowing
exist and render, so these tests execute and fail on wrong values rather
than at an absent target: today the list renders no `narrowing-bar`, no
`row-action`/`quiet` markers and no `launch-row`, and it renders the raw
product identifier on every row. Per `ai-toolkit:testing` that is
failure state 1 — the code ran and produced a value the requirement
forbids — for every test here except any that fails through `_bar`,
whose message says which marker is missing.

**Two tests are expected to PASS on their first run**, and neither is
evidence that anything was implemented. Both are regression guards over
behaviour the delta restates rather than introduces, recorded as such in
the manifest instead of counted as coverage of new behaviour:

- *An empty narrowing parameter narrows nothing* — the delta says
  outright that this "is not a new licence: it is how the surface
  already reads both", and states it so that a control which always
  submits its name is a legitimate way to offer a narrowing. What the
  test guards is that the checkbox-to-select substitution does not
  change it.
- *A resolved product's row still opens its launch* — the row opens its
  launch today. What the test guards is that removing the identifier
  from the row's facts does not take the link with it, which is the one
  way that removal could break the row.

A pass here is therefore the expected result, not the fourth failure
state; a *failure* on either would mean the change broke something it
was never about.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1356 passed, 0
failed, 102 skipped (the whole integration tier, no database
configured), 2 xfailed, on 2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The literal marker tokens `narrowing-bar`, `row-action` and `quiet`,
  which the delta gives "because they are what a test is derived from".
- The literal query contract: the gate narrowing by the `gate`
  parameter, the needs-attention narrowing by `attention=1`, and that a
  narrowing parameter present but empty narrows exactly as an absent one
  does.
- That the bar's action controls are its submit and the reveal control,
  that the controls selecting a narrowing carry no action marker, and
  that the reveal control leads the bar carrying `quiet`.
- That a narrowing submitted from the bar leaves a revealed set
  revealed, narrowed within itself and set apart; that clearing a
  narrowing leaves it revealed; and that the reveal control still
  reveals.
- That a resolved row names its product and renders no raw identifier
  among its facts, that it still opens its launch, that an unresolved
  row renders the identifier once, and that a wholesale identity outage
  renders every row's identifier.

INVENTED, each with its correction point named in the code:

- That "carries the marker `X`" is read as a **class token** on the
  element, the reading `test_playbook_admin_presentation_vocabulary.py`
  already established for the same vocabulary. Correction point:
  `_carries`.
- What counts as an **action control**: a `<button>`, an
  `<input type=submit|image>`, an `<a>` with a destination, or any
  element carrying `role="button"`. Correction point: `_is_action_control`.
- That the identifier is "rendered as a fact" when it appears in the
  row's visible text or in a `title` / `aria-label`, and is not a
  rendered fact when it appears only in an `href`, an `id` or a `data-`
  attribute — which is what the requirement's own "stays in the row's
  link target" clause requires of the reading. Correction point:
  `_rendered_facts`.
- Every module seam, the render date's injection, how a row is located
  and the wording of each mark — all inherited unchanged from
  `test_launch_admin_list.py`, whose implementation already satisfies
  them. Correction points: `_SEAMS`, `_render_on`, `_rows`, `_WORDS`.

Correcting a seam, a marker reading or a control probe is a fixture
correction (failure state 3 in `ai-toolkit:testing`). What must survive
unweakened is what each test asserts: which markers the bar carries,
which parameters its controls submit, which rows come back, and what a
row does and does not print.
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

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
from tests.support.fakes import FakeCatalogPort as _Catalog
from tests.support.fakes import FakeMembersStore as _FakeMembersStore
from tests.support.fakes import FakePlaybooks, StubDate
from tests.support.fixtures import MARKETPLACE
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import all_text as _all_text
from tests.support.html import ancestors as _ancestors
from tests.support.html import classes as _classes
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
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so no launch "
            "list is served — the absent-target state, which establishes "
            "nothing about the assertions in this test"
        )


# ---------------------------------------------------------------------------
# The vocabulary's literal tokens and the literal query contract
# ---------------------------------------------------------------------------

#: SPECIFIED. The delta gives these tokens on purpose: "the literal
#: tokens are given because they are what a test is derived from".
NARROWING_BAR: Final = "narrowing-bar"
ROW_ACTION: Final = "row-action"
QUIET: Final = "quiet"

#: SPECIFIED. "the gate narrowing by the `gate` parameter, the
#: needs-attention narrowing by `attention=1`".
GATE_PARAM: Final = "gate"
ATTENTION_PARAM: Final = "attention"
ATTENTION_VALUE: Final = "1"

A_DISCIPLINE: Final = Discipline("listing")
PRINCIPAL: Final = "U01ALICE"
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
AT_RISK_DATE: Final = date(2027, 4, 15)
HEALTHY_DATE: Final = date(2027, 12, 1)
FINISHED_EARLIER: Final = date(2027, 1, 10)
FINISHED_LATER: Final = date(2027, 2, 20)

RISK_STEP: Final = "strategy.launch-readiness"

#: INVENTED wording, inherited from `test_launch_admin_list.py`.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "at_risk": ("at risk", "at-risk", "date at risk"),
    "awaiting": (
        "awaiting confirmation",
        "awaits confirmation",
        "awaiting approval",
        "needs confirmation",
        "confirmation",
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
}


# ---------------------------------------------------------------------------
# Domain builders
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
    return _build_hold(
        gate,
        discipline=A_DISCIPLINE,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook() -> LaunchPlaybook:
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
    return _start(product_id, launch_date)


def _at_risk(product_id: ProductId, launch_date: date = AT_RISK_DATE) -> Launch:
    return _start(product_id, launch_date)


def _awaiting(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    launch = _start(product_id, launch_date)
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
    def __init__(self, *launches: Launch) -> None:
        self.order: list[Launch] = list(launches)
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
    return asyncio.run(_build_members())


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
        f"{_SEAMS[seam]} — correct `_SEAMS` to the implemented module"
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
        f"{_PAGE_MODULE_NAME} exposes no seam for the day it renders on "
        f"(looked for a callable named one of {_CLOCK_NAMES}, or its own "
        "`date`) — correct `_render_on` to the implemented module"
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


def _detail_path(module: ModuleType, product_id: ProductId) -> str:
    template = _detail_template(module)
    opened = template.index("{")
    closed = template.index("}", opened)
    return str(template[:opened] + product_id.value + template[closed + 1 :])


# ---------------------------------------------------------------------------
# An HTML tree
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


def _carries(node: _Node, marker: str) -> bool:
    """Whether an element carries a vocabulary marker.

    INVENTED: read as a class token, the reading
    `test_playbook_admin_presentation_vocabulary.py` established for
    this same vocabulary. The delta says only "marker". Correction point
    for a page that marks some other way.
    """
    return marker in _classes(node)


def _says(subject: Any, key: str) -> bool:
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
    """Every rendered row, in document order — the locator
    `test_launch_admin_list.py` established."""
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
    return (
        row.link.tag == "a"
        and bool(row.link.attrs.get("href"))
        and not _inherited(row.link, _element_disabled)
        and not _inherited(row.link, _element_hidden)
    )


def _set_apart(html: str, module: ModuleType, revealed: set[str]) -> bool:
    """Whether some element holds exactly the revealed rows and no row of
    a launch in play — the reading `test_launch_admin_list.py` uses for
    *set apart*."""
    root = _tree(html)
    return any(
        element.tag not in ("html", "body")
        and {product for product, _ in _detail_links(element, module)} == revealed
        for element in _elements(root)
    )


def _rendered_facts(node: _Node) -> str:
    """What a row renders *as a fact*: its visible text, plus the
    attributes a reader or a screen reader is shown.

    INVENTED reading. The requirement constrains "what is rendered as a
    fact" and says outright that the identifier "stays in the row's link
    target", so an `href` — and by the same argument an `id` or a
    `data-` attribute, which nothing renders — is deliberately excluded.
    Correction point for a surface that shows a fact some other way.
    """
    shown = [
        value
        for element in (node, *_elements(node))
        for key, value in element.attrs.items()
        if key in ("title", "aria-label", "alt", "value")
    ]
    return " ".join([_all_text(node), *(part.lower() for part in shown)])


# ---------------------------------------------------------------------------
# Controls, and the narrowing bar
# ---------------------------------------------------------------------------


def _is_action_control(node: _Node) -> bool:
    """INVENTED. The sweep
    `test_playbook_admin_presentation_vocabulary.py` established for the
    same vocabulary: a `<button>`, a submitting `<input>`, an `<a>` with
    a destination, or anything carrying `role="button"`."""
    if node.attrs.get("role", "").strip().lower() == "button":
        return True
    if node.tag == "button":
        return True
    if node.tag == "input":
        return (node.attrs.get("type") or "text").lower() in ("submit", "image")
    if node.tag == "a":
        return "href" in node.attrs or any(verb in node.attrs for verb in _HX_VERBS)
    return False


def _action_controls(node: _Node) -> list[_Node]:
    found = [node] if _is_action_control(node) else []
    found.extend(child for child in _elements(node) if _is_action_control(child))
    return found


def _bar(html: str) -> _Node:
    """The one element carrying `narrowing-bar`."""
    bars = [
        element
        for element in _elements(_tree(html))
        if _carries(element, NARROWING_BAR)
    ]
    if not bars:
        rendered = sorted(
            {name for element in _elements(_tree(html)) for name in _classes(element)}
        )
        pytest.fail(
            f"no element on the list carries {NARROWING_BAR!r}, so the "
            "narrowing and the reveal control are not presented as one bar. "
            f"The page carries {rendered}"
        )
    if len(bars) > 1:
        pytest.fail(
            f"{len(bars)} elements carry {NARROWING_BAR!r}; the requirement is "
            "that the narrowing controls and the reveal control sit in *one* bar"
        )
    return bars[0]


def _bar_form(bar: _Node) -> _Node:
    forms = [element for element in _elements(bar) if element.tag == "form"]
    if len(forms) != 1:
        pytest.fail(
            f"the bar holds {len(forms)} forms; exactly one narrowing form is "
            "expected — correct `_bar_form` if the narrowing is submitted "
            "some other way"
        )
    return forms[0]


def _bar_submit(bar: _Node) -> _Node:
    form = _bar_form(bar)
    submits = [
        control
        for control in _action_controls(form)
        if control.tag != "a" or "href" not in control.attrs
    ]
    if not submits:
        pytest.fail(
            "the bar's narrowing form offers no submit control, so the "
            "narrowing cannot be applied at all"
        )
    if len(submits) > 1:
        pytest.fail(
            f"the bar's narrowing form offers {len(submits)} submit-like "
            "controls; exactly one is expected — correct `_bar_submit`"
        )
    return submits[0]


def _bar_controls(bar: _Node) -> list[_Node]:
    """Every control in the bar: its action controls and the fields that
    select a narrowing."""
    fields = [
        element
        for element in _elements(bar)
        if element.tag in ("select", "textarea")
        or (
            element.tag == "input"
            and (element.attrs.get("type") or "text").lower()
            not in ("submit", "image", "hidden")
        )
    ]
    return [*_action_controls(bar), *fields]


def _bar_reveal(bar: _Node) -> _Node:
    """The bar's reveal control: an action control that is not the
    narrowing form's submit."""
    form = _bar_form(bar)
    inside_form = {id(control) for control in _action_controls(form)}
    outside = [
        control for control in _action_controls(bar) if id(control) not in inside_form
    ]
    saying = [
        control
        for control in outside
        if any(
            word in f"{_all_text(control)} {control.attrs.get('href', '').lower()}"
            for word in _WORDS["reveal"]
        )
    ]
    if not saying:
        pytest.fail(
            "the bar carries no control revealing launches no longer in play "
            f"(its action controls outside the narrowing form are "
            f"{[_flat(_all_text(c)) for c in outside]}) — correct "
            "`_WORDS['reveal']` if it is worded differently"
        )
    if len(saying) > 1:
        pytest.fail(
            f"{len(saying)} controls in the bar read as the reveal; exactly "
            "one is expected"
        )
    return saying[0]


def _query_of(node: _Node) -> dict[str, str]:
    return dict(
        parse_qsl(urlsplit(node.attrs.get("href", "")).query, keep_blank_values=True)
    )


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


def _field_named(form: _Node, name: str) -> _Node:
    fields = [
        element
        for element in _elements(form)
        if element.attrs.get("name") == name
        and element.tag in ("select", "input", "textarea")
        and (element.attrs.get("type") or "text").lower() != "hidden"
    ]
    if not fields:
        offered = sorted(
            {
                element.attrs["name"]
                for element in _elements(form)
                if element.attrs.get("name")
            }
        )
        pytest.fail(
            f"the bar's narrowing form offers no control named {name!r}; it "
            f"submits {offered}. The delta fixes this parameter name, so a "
            "narrowing requested under another name changes what a bookmarked "
            "URL means"
        )
    if len(fields) > 1:
        pytest.fail(f"{len(fields)} controls in the bar are named {name!r}")
    return fields[0]


def _state_of(field: _Node) -> str:
    """What the control currently submits: a select's selected option, a
    checkbox's value when checked, otherwise its value."""
    if field.tag == "select":
        return _selected_of(field)
    kind = (field.attrs.get("type") or "text").lower()
    if kind in ("checkbox", "radio"):
        return field.attrs.get("value", "on") if "checked" in field.attrs else ""
    if field.tag == "textarea":
        return " ".join(_texts(field))
    return field.attrs.get("value", "")


def _offers(field: _Node, value: str) -> bool:
    if field.tag == "select":
        return any(
            option.attrs.get("value", "") == value
            for option in _elements(field)
            if option.tag == "option"
        )
    return field.attrs.get("value", "") == value


def _submitted_params(form: _Node, **overrides: str) -> dict[str, str]:
    """The query a browser would send on submitting this GET form."""
    method = (form.attrs.get("method") or "get").lower()
    assert method == "get", (
        f"the narrowing form submits by {method!r}; a narrowing that is not a "
        "GET cannot be bookmarked or shared, which the query contract "
        "presupposes"
    )
    params: dict[str, str] = {}
    for element in _elements(form):
        name = element.attrs.get("name")
        if not name:
            continue
        if element.tag == "select":
            params[name] = _selected_of(element)
        elif element.tag == "input":
            kind = (element.attrs.get("type") or "text").lower()
            if kind in ("submit", "image"):
                continue
            if kind in ("checkbox", "radio"):
                if "checked" in element.attrs:
                    params[name] = element.attrs.get("value", "on")
                continue
            params[name] = element.attrs.get("value", "")
        elif element.tag == "textarea":
            params[name] = " ".join(_texts(element))
    params.update(overrides)
    return params


def _get(surface: _Surface, params: dict[str, str] | None = None) -> str:
    response = surface.client.get(_list_path(surface.module), params=params)
    assert response.status_code == 200, response.text
    return str(response.text)


def _follow(surface: _Surface, node: _Node) -> str:
    """Follow an anchor the page renders."""
    href = node.attrs.get("href", "")
    assert href and href != "#", (
        f"the control {_flat(_all_text(node))!r} offers no destination"
    )
    response = surface.client.get(href.split("#")[0])
    assert response.status_code == 200, response.text
    return str(response.text)


def _live_control_saying(html: str, key: str) -> _Node | None:
    for element in _elements(_tree(html)):
        if not _is_action_control(element):
            continue
        if _inherited(element, _element_disabled):
            continue
        haystack = (
            f"{_all_text(element)} {element.attrs.get('href', '').lower()} "
            f"{_attribute_text(element)}"
        )
        if any(word in haystack for word in _WORDS[key]):
            return element
    return None


# ===========================================================================
# Requirement: The list's narrowing is one bar of peer controls
# ===========================================================================


def test_the_narrowing_renders_as_one_marked_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The narrowing renders as one marked bar.

    WHEN the list is rendered
    THEN its narrowing controls and its reveal control are rendered
    within one element carrying `narrowing-bar`
    AND the bar's submit control and its reveal control each carry
    `row-action`.
    """
    here, elsewhere = (
        _launching("SKU-HERE", "Here widget"),
        _launching("SKU-ELSE", "Elsewhere widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _quiet(here.id), _advance_to(_quiet(elsewhere.id), "listable")
        ),
        catalog=_Catalog(here, elsewhere),
    )

    html = _get(surface)

    bar = _bar(html)
    # SPECIFIED: the narrowing controls are within the bar — the form
    # that submits the gate and the needs-attention narrowings.
    form = _bar_form(bar)
    for name in (GATE_PARAM, ATTENTION_PARAM):
        _field_named(form, name)
    # SPECIFIED: and so is the reveal control.
    reveal = _bar_reveal(bar)
    # SPECIFIED: the bar's submit control and its reveal control each
    # carry `row-action`.
    submit = _bar_submit(bar)
    assert _carries(submit, ROW_ACTION), (
        "the bar's submit carries "
        f"{sorted(_classes(submit))}, not {ROW_ACTION!r} — so it is sized by "
        "whatever the container gives it, which is the defect this "
        "requirement exists to end"
    )
    assert _carries(reveal, ROW_ACTION), (
        f"the reveal control carries {sorted(_classes(reveal))}, not "
        f"{ROW_ACTION!r}, so it is not presented as a peer of the submit"
    )
    # SPECIFIED, from the requirement's prose: "The controls that select
    # a narrowing SHALL NOT carry an action marker, which is what
    # distinguishes them from the controls that act."
    selecting = [
        field
        for field in _elements(form)
        if field.tag == "select"
        or (
            field.tag == "input"
            and (field.attrs.get("type") or "text").lower()
            not in ("submit", "image", "hidden")
        )
    ]
    assert selecting, "the bar offers no control that selects a narrowing"
    marked = [field for field in selecting if _carries(field, ROW_ACTION)]
    assert not marked, (
        f"{len(marked)} control(s) that select a narrowing carry "
        f"{ROW_ACTION!r}, which is the marker distinguishing the controls "
        "that act from the ones that choose"
    )


def test_the_reveal_control_is_distinguished_not_amplified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The reveal control is distinguished, not amplified.

    WHEN the list is rendered
    THEN the control that reveals launches no longer in play carries
    `quiet`
    AND no other control in the bar carries it.
    """
    subject = _launching("SKU-A", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(subject.id)),
        catalog=_Catalog(subject),
    )

    html = _get(surface)

    bar = _bar(html)
    reveal = _bar_reveal(bar)
    # SPECIFIED: the reveal control carries `quiet`.
    assert _carries(reveal, QUIET), (
        f"the reveal control carries {sorted(_classes(reveal))}, not "
        f"{QUIET!r} — it leads the bar and would read as its loudest control"
    )
    # SPECIFIED: and no other control in the bar carries it.
    others = [
        control
        for control in _bar_controls(bar)
        if control is not reveal and _carries(control, QUIET)
    ]
    assert not others, (
        f"{len(others)} other control(s) in the bar carry {QUIET!r}, so the "
        "marker no longer distinguishes the reveal from its peers"
    )


def test_a_gate_narrowing_is_requested_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate narrowing is requested as it was.

    WHEN the list's narrowing is submitted selecting one gate
    THEN the request carries the same gate parameter the surface
    accepted before, and the same rows are narrowed to.
    """
    here, elsewhere = (
        _launching("SKU-HERE", "Here widget"),
        _launching("SKU-ELSE", "Elsewhere widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _advance_to(_quiet(here.id), "listable"), _quiet(elsewhere.id)
        ),
        catalog=_Catalog(here, elsewhere),
    )

    html = _get(surface)
    gate_control = _field_named(_bar_form(_bar(html)), GATE_PARAM)
    assert _offers(gate_control, "listable"), (
        "the bar's gate control offers no way to select the `listable` gate, "
        "so the narrowing cannot be submitted from it at all"
    )
    submitted = _submitted_params(_bar_form(_bar(html)), **{GATE_PARAM: "listable"})

    # SPECIFIED: the request carries the same gate parameter the surface
    # accepted before — `gate`, which the delta names.
    assert submitted.get(GATE_PARAM) == "listable", (
        f"submitting the bar's gate narrowing sends {submitted}, which does "
        f"not carry {GATE_PARAM}=listable — a URL naming a narrowing has "
        "stopped meaning what it meant"
    )
    from_the_bar = _get(surface, params=submitted)
    as_before = _get(surface, params={GATE_PARAM: "listable"})
    # SPECIFIED: and the same rows are narrowed to.
    assert _rendered_ids(from_the_bar, surface.module) == [here.id.value], (
        f"the bar's gate narrowing rendered "
        f"{_rendered_ids(from_the_bar, surface.module)}, not the one launch "
        "standing at that gate"
    )
    assert _rendered_ids(from_the_bar, surface.module) == _rendered_ids(
        as_before, surface.module
    ), "the bar's gate narrowing renders different rows from the bare URL's"


def test_a_needs_attention_narrowing_is_requested_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A needs-attention narrowing is requested as it was.

    WHEN the list's narrowing is submitted selecting launches needing
    attention
    THEN the request carries `attention=1`, and exactly the launches
    needing attention are rendered.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _at_risk(risky.id),
            _awaiting(waiting.id),
            _advance_to(_quiet(quiet.id), "listable"),
        ),
        catalog=_Catalog(risky, waiting, quiet),
    )

    html = _get(surface)
    attention = _field_named(_bar_form(_bar(html)), ATTENTION_PARAM)
    assert _offers(attention, ATTENTION_VALUE), (
        f"the bar's needs-attention control offers no "
        f"{ATTENTION_VALUE!r} value, so the narrowing a bookmarked "
        f"`?{ATTENTION_PARAM}={ATTENTION_VALUE}` requests cannot be "
        "submitted from the bar"
    )
    submitted = _submitted_params(
        _bar_form(_bar(html)), **{ATTENTION_PARAM: ATTENTION_VALUE}
    )

    # SPECIFIED: the request carries `attention=1`.
    assert submitted.get(ATTENTION_PARAM) == ATTENTION_VALUE, (
        f"submitting the bar's needs-attention narrowing sends {submitted}, "
        f"which does not carry {ATTENTION_PARAM}={ATTENTION_VALUE}"
    )
    narrowed = _get(surface, params=submitted)
    # SPECIFIED: exactly the launches needing attention are rendered.
    assert _rendered_ids(narrowed, surface.module) == [
        risky.id.value,
        waiting.id.value,
    ], (
        "the needs-attention narrowing submitted from the bar rendered "
        f"{_rendered_ids(narrowed, surface.module)}, not exactly the at-risk "
        "and awaiting-confirmation launches"
    )


def test_an_empty_narrowing_parameter_narrows_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An empty narrowing parameter narrows nothing.

    WHEN the list is requested with its narrowing parameters present but
    empty
    THEN the rendered rows are those the list renders when the
    parameters are absent altogether.
    """
    risky, waiting, quiet = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-WAIT", "Waiting widget"),
        _launching("SKU-QUIET", "Quiet widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _at_risk(risky.id),
            _awaiting(waiting.id),
            _advance_to(_quiet(quiet.id), "listable"),
        ),
        catalog=_Catalog(risky, waiting, quiet),
    )

    absent = _get(surface)
    empty = _get(surface, params={GATE_PARAM: "", ATTENTION_PARAM: ""})

    # DERIVED guard: the unnarrowed list really renders rows, so the
    # equality below is not two empty lists agreeing.
    assert _rendered_ids(absent, surface.module), "the unnarrowed list is empty"
    # SPECIFIED: the same rows, in the same order.
    assert _rendered_ids(empty, surface.module) == _rendered_ids(
        absent, surface.module
    ), (
        "a narrowing parameter present but empty changed what the list "
        f"renders: {_rendered_ids(empty, surface.module)} against "
        f"{_rendered_ids(absent, surface.module)}. Every select in a GET form "
        "always submits its name, so this is what an unnarrowed submission "
        "sends"
    )
    # SPECIFIED, the reading that makes the equality mean *narrows
    # nothing* rather than *matched nothing*: the empty-narrowing page is
    # not the page a narrowing that matched nothing renders.
    assert not _says(_tree(empty), "matched_nothing"), (
        "the list read an empty narrowing parameter as a narrowing that matched nothing"
    )


def test_the_bar_shows_the_narrowing_it_submitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The bar shows the narrowing it submitted.

    WHEN the list is rendered under a gate narrowing and under the
    needs-attention narrowing
    THEN each narrowing is rendered as the selected state of the control
    that sets it.
    """
    risky, elsewhere = (
        _launching("SKU-RISK", "Risky widget"),
        _launching("SKU-ELSE", "Elsewhere widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _at_risk(risky.id), _advance_to(_quiet(elsewhere.id), "listable")
        ),
        catalog=_Catalog(risky, elsewhere),
    )

    under_gate = _get(surface, params={GATE_PARAM: "listable"})
    under_attention = _get(surface, params={ATTENTION_PARAM: ATTENTION_VALUE})

    # SPECIFIED: the gate narrowing is the state of the control that
    # sets it.
    gate_control = _field_named(_bar_form(_bar(under_gate)), GATE_PARAM)
    assert _state_of(gate_control) == "listable", (
        "under `gate=listable` the bar's gate control reads "
        f"{_state_of(gate_control)!r}, so the bar does not show the narrowing "
        "the list is under — and the next thing submitted from it silently "
        "clears the narrowing"
    )
    # SPECIFIED: and so is the needs-attention narrowing.
    attention = _field_named(_bar_form(_bar(under_attention)), ATTENTION_PARAM)
    assert _state_of(attention) == ATTENTION_VALUE, (
        f"under `{ATTENTION_PARAM}={ATTENTION_VALUE}` the bar's "
        f"needs-attention control reads {_state_of(attention)!r}, so a "
        "narrowed list reads from the bar as an unnarrowed one"
    )
    # DERIVED guard: the control is not simply stuck on that state — it
    # reads unset on an unnarrowed rendering.
    unnarrowed = _get(surface)
    assert _state_of(_field_named(_bar_form(_bar(unnarrowed)), GATE_PARAM)) != (
        "listable"
    ), "the bar's gate control reads `listable` with no narrowing applied"
    assert (
        _state_of(_field_named(_bar_form(_bar(unnarrowed)), ATTENTION_PARAM))
        != ATTENTION_VALUE
    ), "the bar's needs-attention control reads as narrowing with no narrowing applied"


def test_a_narrowing_submitted_from_the_bar_keeps_the_reveal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A narrowing submitted from the bar keeps the reveal.

    WHEN launches no longer in play are revealed, and a narrowing is
    then submitted from the bar
    THEN those launches are still revealed, narrowed within themselves
    and set apart from the rows in play.
    """
    in_play_here = _launching("SKU-IN-HERE", "In-play here")
    in_play_elsewhere = _launching("SKU-IN-ELSE", "In-play elsewhere")
    finished_here = _steady("SKU-OUT-HERE", "Finished here")
    finished_elsewhere = _steady("SKU-OUT-ELSE", "Finished elsewhere")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _advance_to(_quiet(in_play_here.id), "listable"),
            _quiet(in_play_elsewhere.id),
            _advance_to(_quiet(finished_here.id, FINISHED_EARLIER), "listable"),
            _quiet(finished_elsewhere.id, FINISHED_LATER),
        ),
        catalog=_Catalog(
            in_play_here, in_play_elsewhere, finished_here, finished_elsewhere
        ),
    )

    revealed = _follow(surface, _bar_reveal(_bar(_get(surface))))
    # DERIVED guard: the reveal really revealed, so what follows is about
    # a narrowing applied to a revealed list.
    assert finished_here.id.value in _rendered_ids(revealed, surface.module), (
        "the bar's reveal control did not reveal launches no longer in play"
    )
    submitted = _submitted_params(_bar_form(_bar(revealed)), **{GATE_PARAM: "listable"})
    narrowed = _get(surface, params=submitted)

    rendered = set(_rendered_ids(narrowed, surface.module))
    # SPECIFIED: those launches are still revealed, narrowed within
    # themselves — the revealed launch at that gate is rendered and the
    # other revealed one is not.
    assert finished_here.id.value in rendered, (
        "submitting a narrowing from the bar dropped the reveal: the page "
        f"rendered {rendered}. A bar whose two controls each discard the "
        "other's state looks like one control and is not"
    )
    assert rendered == {in_play_here.id.value, finished_here.id.value}, (
        f"the narrowing over a revealed list rendered {rendered}; it should "
        "hold the launch at that gate from each set and neither of the others"
    )
    # SPECIFIED: and set apart from the rows in play.
    assert _set_apart(narrowed, surface.module, {finished_here.id.value}), (
        "under a narrowing submitted from the bar the revealed row is no "
        "longer held apart from the rows in play"
    )


def test_clearing_a_narrowing_keeps_the_reveal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Clearing a narrowing keeps the reveal.

    WHEN launches no longer in play are revealed, a narrowing is applied
    that matches nothing in either set, and the offer to clear that
    narrowing is used
    THEN the narrowing is cleared and those launches are still revealed.
    """
    in_play = _launching("SKU-IN", "In-play widget")
    finished = _steady("SKU-OUT", "Finished widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _quiet(in_play.id), _quiet(finished.id, FINISHED_EARLIER)
        ),
        catalog=_Catalog(in_play, finished),
    )

    revealed = _follow(surface, _bar_reveal(_bar(_get(surface))))
    revealed_ids = _rendered_ids(revealed, surface.module)
    # DERIVED guard: the reveal really revealed.
    assert finished.id.value in revealed_ids

    matched_nothing = _get(
        surface,
        params=_submitted_params(_bar_form(_bar(revealed)), **{GATE_PARAM: "ignition"}),
    )
    # DERIVED guard: the narrowing really matched nothing in either set.
    assert _rendered_ids(matched_nothing, surface.module) == [], (
        "the narrowing chosen for this scenario matched something; it must "
        "match nothing in either set for the clear offer to be made"
    )
    offer = _live_control_saying(matched_nothing, "clear")
    assert offer is not None, (
        "a narrowing that matched nothing offers no control clearing it"
    )

    cleared = _follow(surface, offer)

    # SPECIFIED: the narrowing is cleared...
    assert not _says(_tree(cleared), "matched_nothing"), (
        "using the offer to clear the narrowing left the page still saying "
        "the narrowing matched nothing"
    )
    # ...and those launches are still revealed.
    assert finished.id.value in _rendered_ids(cleared, surface.module), (
        "clearing the narrowing returned an unrevealed default view: the "
        f"page rendered {_rendered_ids(cleared, surface.module)}. The offer "
        "exists so the admin can undo what they just did, not something else "
        "as well"
    )
    assert _rendered_ids(cleared, surface.module) == revealed_ids, (
        "clearing the narrowing did not return the revealed list as it stood: "
        f"{_rendered_ids(cleared, surface.module)} against {revealed_ids}"
    )


def test_the_reveal_control_still_reveals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The reveal control still reveals.

    WHEN the reveal control is used from the bar
    THEN launches no longer in play are rendered, marked and set apart,
    exactly as before.
    """
    in_play = _launching("PX-100", "Widget")
    steady = _steady("PX-200", "Widget")
    retired = _retired("PX-300", "Widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(
            _quiet(in_play.id, FINISHED_EARLIER),
            _quiet(steady.id, FINISHED_EARLIER),
            _quiet(retired.id, FINISHED_EARLIER),
        ),
        catalog=_Catalog(in_play, steady, retired),
    )

    revealed = _follow(surface, _bar_reveal(_bar(_get(surface))))

    rendered = set(_rendered_ids(revealed, surface.module))
    # SPECIFIED: launches no longer in play are rendered.
    assert {steady.id.value, retired.id.value} <= rendered, (
        f"using the bar's reveal control rendered {rendered}, which does not "
        "hold both launches no longer in play"
    )
    # SPECIFIED: marked — and distinguishably, as before.
    steady_row = _row_for(revealed, surface.module, steady.id)
    retired_row = _row_for(revealed, surface.module, retired.id)
    assert _says(steady_row, "steady"), (
        "the steady-state launch's row does not say the product reached "
        f"steady state: {_all_text(steady_row.node)!r}"
    )
    assert _says(retired_row, "retired"), (
        "the retired launch's row does not say the product was retired: "
        f"{_all_text(retired_row.node)!r}"
    )
    # SPECIFIED: and set apart.
    assert _set_apart(revealed, surface.module, {steady.id.value, retired.id.value}), (
        "no element holds the revealed rows and none of the rows in play, so "
        "they are not set apart from the bands"
    )


# ===========================================================================
# Requirement: A row names its product, and falls back to the raw
# identifier only when it must
# ===========================================================================


def test_a_resolved_products_row_carries_no_raw_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A resolved product's row carries no raw identifier.

    WHEN a launch is listed whose catalog product resolves to a name
    THEN its row names the product
    AND does not render the raw product identifier among the facts it
    shows.
    """
    resolved = _launching("SKU-KNOWN", "Known widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(resolved.id)),
        catalog=_Catalog(resolved),
    )

    html = _get(surface)

    row = _row_for(html, surface.module, resolved.id)
    # SPECIFIED: its row names the product.
    assert resolved.name.lower() in _all_text(row.node), (
        f"the row does not name {resolved.name!r}: {_all_text(row.node)!r}"
    )
    # SPECIFIED: and does not render the raw identifier among its facts.
    assert resolved.id.value.lower() not in _rendered_facts(row.node), (
        "a row whose product resolved still prints the raw product "
        f"identifier {resolved.id.value} among its facts: "
        f"{_rendered_facts(row.node)!r}. It is opaque by "
        "`shared-vocabulary`'s own rule, so it is 36 characters an admin can "
        "neither read nor act on"
    )


def test_a_resolved_products_row_still_opens_its_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A resolved product's row still opens its launch.

    WHEN a launch is listed whose catalog product resolves to a name
    THEN its row still offers that launch's detail page in one action.
    """
    resolved = _launching("SKU-KNOWN", "Known widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(resolved.id)),
        catalog=_Catalog(resolved),
    )

    html = _get(surface)

    row = _row_for(html, surface.module, resolved.id)
    # SPECIFIED: in one action — a live anchor, needing no scripting.
    assert _offers_in_one_action(row), (
        "the row offers no live link to its detail page, so removing the "
        "identifier from the row's facts took the way into the launch with it"
    )
    # SPECIFIED: and it is *that launch's* detail page — the identifier
    # stays in the link target, which is how the page addresses a launch.
    assert urlsplit(row.link.attrs["href"]).path == _detail_path(
        surface.module, resolved.id
    )


def test_an_unresolvable_products_row_still_renders_its_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unresolvable product's row still renders its
    identifier.

    WHEN a launch is listed whose catalog product cannot be resolved
    THEN its row renders the raw product identifier, as the fallback
    requirement already obliges
    AND renders it once.
    """
    known = _launching("SKU-KNOWN", "Known widget")
    unknown_id = _unresolvable_product_id()
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(known.id), _quiet(unknown_id)),
        catalog=_Catalog(known),
    )

    html = _get(surface)

    row = _row_for(html, surface.module, unknown_id)
    facts = _rendered_facts(row.node)
    # SPECIFIED: its row renders the raw product identifier.
    assert unknown_id.value.lower() in facts, (
        "the unresolvable launch's row does not carry its raw product "
        f"identifier: {facts!r}. The fallback is the whole of what the "
        "capability requires the identifier for"
    )
    # SPECIFIED: and renders it once — the fallback already names the
    # launch by the identifier, so a second rendering prints the same 36
    # characters twice on precisely the row this exists to make readable.
    assert facts.count(unknown_id.value.lower()) == 1, (
        f"the unresolvable launch's row renders its identifier "
        f"{facts.count(unknown_id.value.lower())} times: {facts!r}"
    )
    # DERIVED guard: the resolvable row is still named, so the page has
    # not fallen back to identifiers wholesale.
    assert known.name.lower() in _all_text(
        _row_for(html, surface.module, known.id).node
    )


def test_a_wholesale_identity_outage_still_renders_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A wholesale identity outage still renders identifiers.

    WHEN the list is rendered and product identities cannot be read at
    all
    THEN every row renders its raw product identifier.
    """
    first, second = (
        _launching("SKU-A", "Alpha widget"),
        _launching("SKU-B", "Beta widget"),
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_quiet(first.id), _quiet(second.id)),
        catalog=_Catalog(first, second, fails=True),
    )

    response = surface.client.get(_list_path(surface.module))

    # DERIVED guard, inherited from the served requirement: the page
    # renders rather than failing, or there is no row to read.
    assert response.status_code == 200, (
        "the list failed when product identities could not be read at all: "
        f"{response.status_code}"
    )
    html = str(response.text)
    assert sorted(_rendered_ids(html, surface.module)) == sorted(
        [first.id.value, second.id.value]
    )
    for product in (first, second):
        row = _row_for(html, surface.module, product.id)
        facts = _rendered_facts(row.node)
        # SPECIFIED: every row renders its raw product identifier.
        assert product.id.value.lower() in facts, (
            f"under a wholesale outage the row for {product.id} renders no "
            f"identifier at all: {facts!r} — the removal reached the fallback "
            "path it was never about"
        )
        # SPECIFIED, from the requirement's prose: a row that falls back
        # to the identifier renders it once.
        assert facts.count(product.id.value.lower()) == 1, (
            f"the row for {product.id} renders its identifier "
            f"{facts.count(product.id.value.lower())} times: {facts!r}"
        )
