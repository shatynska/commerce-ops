"""A carried finding whose value carries several members, on the launch
detail page (`launch-admin`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/launch-admin/spec.md`

Covers, from the MODIFIED requirement *A carried finding's result is
rendered ahead of its comment*, the three scenarios this change turns on:

- A value of several members renders as those members (**new**)
- A textual value is not rendered as its characters (**new**)
- An empty value renders as readable text (re-exercised for a value
  carrying no *members* rather than an empty string, which is what the
  requirement's new "emptiness outranks member rendering" clause fixes)

`tasks.md` 1.20 and 1.21.

The requirement's other seven scenarios are unchanged in wording and in
normative content by this delta, and are covered by
`tests/unit/launch/infrastructure/driving/test_launch_detail_finding_rendering.py`,
which this pass does not edit and which is not superseded. They are
accounted for against that file in `test-manifest.md` rather than
duplicated here: reproducing a thousand lines of an unedited harness to
re-assert eight identical scenarios would add no evidence and would put
two pins on the same markup.

## Expected first-run state — and why a pass here is the expected result

**Both tests are expected to PASS on the first run.** `design.md`
Decision 8 and `tasks.md` 6.0 say so in as many words: `_render_finding_value`
"already renders a sequence as its members and already refuses to treat a
string as one", and "the expected diff to `launch_admin.py` is empty".

This is the target-exists situation in `ai-toolkit:testing`'s terms, where
a first-run pass is the expected result and establishes that the code
currently behaves as asserted. It is *not* the alarm a first-run pass
would be for an absent target. What these tests are is a **regression
guard on behaviour nothing currently specifies** — the requirement gained
the clause precisely because the behaviour existed and was unstated, and
the first value carrying several members is about to reach this surface.

`tasks.md` 6.0's instruction is repeated here so it survives beside the
tests: *if these fail, the renderer is wrong and the fix belongs in
`launch_admin.py`; do not edit the renderer to make a passing test look
earned.*

One test here **is** expected to fail on an absent target: the whole
fixture path needs a recording that carries a finding, which
`_finding_kwarg()` probes for and fails loudly on where the domain does
not support one. That support exists (`separate-the-result-from-the-comment`),
so in this worktree the probe succeeds.

## Level

The launch router over fakes for the stores and the catalog read — the
level `test_launch_admin_detail.py` established and
`test_launch_detail_finding_rendering.py` reproduced. The scenarios are
stated over *the rendered response*, so nothing below the route can
observe them. The harness is duplicated rather than imported: this
project shares no test-helper module, and `tests/**/test_*.py` is the
only path a test may be written to.

## What is fixed, and what is INVENTED

Fixed by the delta: the marker `finding-result`; that every member
appears, "each readable and separated from the next", with "no bracket,
quotation mark or type name from a collection's programming notation
around them"; that none is "elided, summarised or truncated away"; that a
string is one member and not a sequence of them; and that emptiness
outranks member rendering, an empty value rendering as visible text.

Deliberately **not** fixed by the delta, and therefore not asserted: *how*
members are separated from one another — "the same kind of visual
judgement the requirement already declines to fix for weight and
spacing".

INVENTED, and inherited from `test_launch_detail_finding_rendering.py`'s
own documented assumptions, each recorded in `test-manifest.md`: the
page module and its seams (`_SEAMS`, `_render_on`), the session cookie,
the detail route's discovery, the tree parser, `_row_of`, how a recording
is given a finding (`_FINDING_KWARGS`) and how one is spelled
(`_FINDING_TYPES`), and how a field's wording reaches the page
(`_WORDING_SEAM_NAMES` / `_WORDING_KEYS`).

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from itertools import pairwise
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain import launch_run
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fakes import FakeCatalogPort as _Catalog
from tests.support.fakes import FakeMembersStore as _FakeMembersStore
from tests.support.fakes import StubDate
from tests.support.fixtures import MARKETPLACE
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    return importlib.import_module(_PAGE_MODULE_NAME)


STRATEGY: Final = Discipline("strategy")
PRINCIPAL: Final = "U01ALICE"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RECORDED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)

MEMBERS_STEP: Final = "strategy.several-member-finding"
TEXT_STEP: Final = "strategy.textual-finding"
EMPTY_STEP: Final = "strategy.empty-member-finding"
COMMIT_STEP: Final = "strategy.commitment-agreed"

STEP_NAMES: Final[dict[str, str]] = {
    MEMBERS_STEP: "Work whose finding carries several members",
    TEXT_STEP: "Work whose finding is textual",
    EMPTY_STEP: "Work whose finding carries no members",
    COMMIT_STEP: "Commitment to launch is agreed",
}

EVIDENCE: Final = (
    "Verdict flagged. Screened against the FBA-prohibited hazmat list and "
    "high-compliance categories."
)
RECORDER_NAME: Final = "strategy.compliance_screen"

HAZARD_FIELD: Final = "hazard_categories"
HAZARD_WORDING: Final = "Hazard categories"

#: Three members, each a phrase rather than a single word, so that a
#: rendering joining them without a separator is legible as a failure
#: rather than as an accident of short tokens. `MEMBER_WITH_A_SPACE` is
#: what the authored description's own wording looks like.
MEMBERS: Final = ("supplements", "medical devices", "CO detectors")
MEMBERS_COMMENT: Final = "Each falls under a gated compliance heading."

TEXT_FIELD: Final = "sub_category"
TEXT_WORDING: Final = "Sub-category"
#: A textual value with no internal separator at all, so that "rendered as
#: its characters" is unambiguous when it happens.
TEXT_VALUE: Final = "Kitchen and Dining then Cutting Boards"
TEXT_COMMENT: Final = "Rejected alternative Home Decor which carries no obligation."

EMPTY_COMMENT: Final = "Nothing on the hazardous list applies to this product."

_ABSENT: Final = object()
_UNSET: Final = object()

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

RESULT_MARKER: Final = "finding-result"

#: The delta's own list: "no bracket, quotation mark or type name from a
#: collection's programming notation". The type names are the ones a
#: Python `repr` or `str` of a collection actually produces.
_COLLECTION_NOTATION: Final = ("[", "]", "{", "}", "'", '"')
_COLLECTION_TYPE_NAMES: Final = ("list", "tuple", "set", "frozenset", "dict")


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": STEP_NAMES.get(identifier, "Work this step asks for"),
        "description": None,
        "gate": "listable",
        "discipline": STRATEGY,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": RECORDER_NAME,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _detail_playbook() -> LaunchPlaybook:
    steps = (
        _step(
            COMMIT_STEP,
            gate="commit",
            blocking=True,
            kind=StepKind.HUMAN,
            handler=None,
            timing_anchor=OffsetAnchor(days=365),
        ),
        _step(MEMBERS_STEP),
        _step(TEXT_STEP),
        _step(EMPTY_STEP),
    )
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(
        _step(
            f"hold.{gate}",
            gate=gate,
            blocking=True,
            kind=StepKind.HUMAN,
            handler=None,
            timing_anchor=OffsetAnchor(days=365),
        )
        for gate in SPECIFIED_GATE_ORDER
        if gate not in held
    )
    return LaunchPlaybook(
        version="member-render-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _served_order(playbook: LaunchPlaybook) -> tuple[str, ...]:
    return tuple(
        step.identifier
        for gate in SPECIFIED_GATE_ORDER
        for step in playbook.steps_for_gate(gate)
    )


def _provenance() -> Provenance:
    return Provenance(
        source="automated", who=RECORDER_NAME, when=RECORDED_AT, evidence=EVIDENCE
    )


# ---------------------------------------------------------------------------
# Correction points for the carried finding — inherited
# ---------------------------------------------------------------------------

_FINDING_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_FINDING_TYPES: Final = ("CarriedFinding", "RecordedFinding", "KeptFinding", "Finding")
_WORDING_SEAM_NAMES: Final = (
    "recorders",
    "finding_sinks",
    "sinks",
    "finding_wordings",
    "FIELD_WORDINGS",
)
_WORDING_KEYS: Final = ("reads_as", "wording", "reads", "label")


def _finding_kwarg() -> str:
    accepted = set(inspect.signature(Launch.record_step_outcome).parameters)
    for name in _FINDING_KWARGS:
        if name in accepted:
            return name
    pytest.fail(
        "`Launch.record_step_outcome` accepts no keyword for a carried "
        f"finding among {list(_FINDING_KWARGS)}; its parameters are "
        f"{sorted(accepted)} — correct `_FINDING_KWARGS`"
    )


def _finding_type() -> Any:
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            return found
    return None


def _wording_key() -> str:
    found = _finding_type()
    if found is not None:
        accepted = set(inspect.signature(found).parameters)
        for key in _WORDING_KEYS:
            if key in accepted:
                return key
    return _WORDING_KEYS[0]


def _carry(
    field_name: str, value: Any, comment: Any = _ABSENT, reads_as: str | None = None
) -> Any:
    parts: dict[str, Any] = {"field": field_name, "value": value}
    if comment is not _ABSENT:
        parts["comment"] = comment
    if reads_as is not None:
        parts[_wording_key()] = reads_as
    found = _finding_type()
    if found is not None:
        return found(**parts)
    return parts


def _carries_wording() -> bool:
    found = _finding_type()
    if found is None:
        return False
    accepted = set(inspect.signature(found).parameters)
    return any(key in accepted for key in _WORDING_KEYS)


def _supply_wording(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> bool:
    """Whether a route exists by which a field's wording reaches the page.

    The finding-borne route is the one the previous change took; the
    module-attribute route is checked as well, and installed with a
    mapping keyed by field name where one is found.
    """
    for name in _WORDING_SEAM_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(
                module,
                name,
                {HAZARD_FIELD: HAZARD_WORDING, TEXT_FIELD: TEXT_WORDING},
            )
            return True
    return _carries_wording()


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


def _launching(sku: str, name: str) -> Product:
    product = Product.register(
        sku=Sku(sku), marketplace_id=MARKETPLACE, name=name, registered_at=T_REGISTERED
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


# ---------------------------------------------------------------------------
# Seams — inherited
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


_fake_verify = fake_verify(PRINCIPAL)


class _StubDate(StubDate):
    _today = RENDER_DATE


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


# ---------------------------------------------------------------------------
# An HTML tree — inherited
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
    return " ".join(part.strip() for part in found if part.strip())


def _haystack(node: _Node) -> str:
    attributes = " ".join(
        value
        for element in (node, *_elements(node))
        for value in element.attrs.values()
    )
    return " ".join((_all_text(node), attributes)).lower()


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


def _classes(node: _Node) -> set[str]:
    return set(str(node.attrs.get("class", "")).split())


def _row_of(html: str, step_id: str, served: tuple[str, ...]) -> _Node:
    root = _tree(html)
    others = [other for other in served if other != step_id]
    mine = [
        element
        for element in _elements(root)
        if _holds(element, step_id)
        and not any(_holds(element, other) for other in others)
        and _holds(element, STEP_NAMES[step_id])
    ]
    if not mine:
        pytest.fail(
            f"no element on the detail page holds {step_id!r} and its name "
            "without also holding another served step — correct `_row_of`"
        )
    return min(mine, key=lambda element: len(_haystack(element)))


def _require_marked(row: _Node, marker: str) -> _Node:
    found = [element for element in _elements(row) if marker in _classes(element)]
    if not found:
        carried = sorted(
            {
                name
                for element in _elements(row)
                for name in _classes(element)
                if name.startswith("finding")
            }
        )
        pytest.fail(
            f"the rendered row carries no element marked {marker!r}; the "
            f"`finding-` markers it does carry are {carried or 'none'}"
        )
    assert len(found) == 1, (
        f"the row carries {len(found)} elements marked {marker!r}; the "
        "requirement names one result"
    )
    return found[0]


def _visible(text: str) -> str:
    return re.sub(r"[\s\u00a0\u200b]+", "", text)


# ---------------------------------------------------------------------------
# Rendering one page
# ---------------------------------------------------------------------------


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
    _install(monkeypatch, module, "members", asyncio.run(_build_members()))
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


@dataclass(frozen=True)
class _Rendered:
    html: str
    playbook: LaunchPlaybook
    wording_route: bool

    @property
    def served(self) -> tuple[str, ...]:
        return _served_order(self.playbook)

    def row(self, step_id: str) -> _Node:
        return _row_of(self.html, step_id, self.served)

    def result(self, step_id: str) -> str:
        return _all_text(_require_marked(self.row(step_id), RESULT_MARKER))

    def rendered_field(self, step_id: str) -> str:
        wording = {MEMBERS_STEP: HAZARD_WORDING, TEXT_STEP: TEXT_WORDING}
        names = {MEMBERS_STEP: HAZARD_FIELD, TEXT_STEP: TEXT_FIELD}
        if step_id == EMPTY_STEP:
            return HAZARD_WORDING if self.wording_route else HAZARD_FIELD
        return wording[step_id] if self.wording_route else names[step_id]


def _record(
    launch: Launch, playbook: LaunchPlaybook, *, step_id: str, finding: Any = _UNSET
) -> None:
    kwargs: dict[str, Any] = {
        "step_id": step_id,
        "outcome": Satisfied,
        "provenance": _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg()] = finding
    launch.record_step_outcome(playbook, **kwargs)


@pytest.fixture()
def rendered(monkeypatch: pytest.MonkeyPatch) -> _Rendered:
    playbook = _detail_playbook()
    product = _launching("BCB-2027-02", "Bamboo Cutting Board")
    launch, _ = Launch.start(
        product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    _record(
        launch,
        playbook,
        step_id=MEMBERS_STEP,
        finding=_carry(HAZARD_FIELD, list(MEMBERS), MEMBERS_COMMENT, HAZARD_WORDING),
    )
    _record(
        launch,
        playbook,
        step_id=TEXT_STEP,
        finding=_carry(TEXT_FIELD, TEXT_VALUE, TEXT_COMMENT, TEXT_WORDING),
    )
    _record(
        launch,
        playbook,
        step_id=EMPTY_STEP,
        finding=_carry(HAZARD_FIELD, [], EMPTY_COMMENT, HAZARD_WORDING),
    )

    surface = _surface(monkeypatch, launch, product, playbook)
    route = _supply_wording(monkeypatch, surface.module)
    return _Rendered(
        html=_detail_html(surface, product.id), playbook=playbook, wording_route=route
    )


# ---------------------------------------------------------------------------
# Scenario: A value of several members renders as those members
# ---------------------------------------------------------------------------


def test_every_member_of_a_multi_member_value_appears(rendered: _Rendered) -> None:
    """WHEN the detail page renders a step whose carried finding has a
    value carrying several members
    THEN every member appears in the result.

    SPECIFIED: **every** one — "none SHALL be elided, summarised or
    truncated away, since a category omitted from a compliance result is
    the one a reader most needs". Three members, so an implementation
    rendering the first, or the first and an ellipsis, fails.
    """
    result = rendered.result(MEMBERS_STEP)

    for member in MEMBERS:
        assert member in result, (
            f"the member {member!r} does not appear in the rendered result "
            f"{result!r}; every member the finding carries must"
        )


def test_the_members_are_separated_from_one_another(rendered: _Rendered) -> None:
    """The same scenario's "each readable and separated from the next".

    *How* they are separated is a visual judgement the requirement
    declines to fix, so what is asserted is that something stands between
    them — the rendered text is not the members run together. Asserted on
    the whitespace-stripped text so that a separator made of whitespace
    alone still fails: two members abutting with no visible mark between
    them are not separated for a reader scanning a column.
    """
    result = rendered.result(MEMBERS_STEP)

    for left, right in pairwise(MEMBERS):
        run_together = _visible(left) + _visible(right)
        assert run_together not in _visible(result), (
            f"{left!r} and {right!r} are rendered run together with nothing "
            f"between them: {result!r}"
        )


def test_the_members_carry_no_collection_notation(rendered: _Rendered) -> None:
    """The same scenario's third clause.

    THEN … with no bracket, quotation mark or type name from a
    collection's programming notation around them.

    SPECIFIED, and asserted item by item so the failure names which
    notation leaked. "The result element is prose an admin reads, and the
    surrounding requirement that it lead with the value and nothing else
    forbids decoration around it just as it forbids a label before it."

    A `str()` of a Python list produces `['supplements', ...]`; a `repr()`
    of a tuple adds parentheses; a value that reached the template as a
    set adds braces and, for an empty one, the type name. Each of those is
    a real rendering this clause exists to exclude.
    """
    result = rendered.result(MEMBERS_STEP)

    for notation in _COLLECTION_NOTATION:
        assert notation not in result, (
            f"the rendered result carries {notation!r}, a collection's own "
            f"programming notation: {result!r}"
        )
    lowered = result.lower()
    for type_name in _COLLECTION_TYPE_NAMES:
        assert type_name not in lowered, (
            f"the rendered result carries the type name {type_name!r}: {result!r}"
        )


def test_the_result_still_leads_with_the_field_for_a_multi_member_value(
    rendered: _Rendered,
) -> None:
    """The requirement's standing clause — "the result SHALL lead with the
    field and the value and nothing else" — over the new kind of value.

    Stated here because a member-rendering implementation is the most
    likely place a narrating label ("Categories found: …") gets
    introduced, and the standing clause forbids one.
    """
    result = rendered.result(MEMBERS_STEP).strip()
    leading = rendered.rendered_field(MEMBERS_STEP)

    assert result.startswith(leading), (
        f"the result reads {result[:80]!r}, which does not lead with the "
        f"field {leading!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A textual value is not rendered as its characters
# ---------------------------------------------------------------------------


def test_a_textual_value_is_rendered_as_one_value(rendered: _Rendered) -> None:
    """WHEN the detail page renders a step whose carried finding has a
    textual value
    THEN that text is rendered as one value, not as its characters
    separated from one another.

    SPECIFIED. "A string is one member, not a sequence of them, and this
    is stated because the two are the same kind of thing to most languages
    and not to a reader" — a sub-category rendered as its letters,
    separated, would satisfy a naive reading of the member clause above.

    Asserted as the text appearing **contiguously**, which is what a
    character-wise rendering destroys and what a mere `in` check on a
    single letter would not catch.
    """
    result = rendered.result(TEXT_STEP)

    assert TEXT_VALUE in result, (
        f"the textual value does not appear whole in the rendered result: {result!r}"
    )
    # And the characters are not additionally strewn about: a rendering
    # that emitted both would pass the clause above.
    strewn = " ".join(TEXT_VALUE.replace(" ", ""))
    assert strewn not in result, (
        f"the textual value is also rendered as its separated characters: {result!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: An empty value renders as readable text — emptiness outranks
# member rendering
# ---------------------------------------------------------------------------


def test_an_empty_membered_value_renders_as_readable_text(
    rendered: _Rendered,
) -> None:
    """WHEN the detail page renders a step whose carried finding has an
    empty value
    THEN the result carries visible text standing for emptiness.

    Re-exercised here for a value carrying **no members** rather than an
    empty string, which is what the requirement's new clause fixes:
    "emptiness outranks member rendering — a value carrying no members is
    governed by the empty-value clause above and renders as text standing
    for emptiness, never as nothing at all".

    The clause names its own failures — blank, whitespace, an element
    carrying a class and no text, or an omitted result — so the assertion
    is on *text*, and on text beyond the field's own wording. This is the
    row the `lp.strategy.006` clear verdict will actually land on.
    """
    result = rendered.result(EMPTY_STEP)
    leading = rendered.rendered_field(EMPTY_STEP)

    assert _visible(result), "the result element carries a class and no text"
    remainder = result.replace(leading, "", 1)
    assert _visible(remainder), (
        f"the result reads {result!r} — nothing beyond the field's own name, "
        "so a reader cannot see that the answer was 'none'"
    )
    for notation in _COLLECTION_NOTATION:
        assert notation not in result, (
            f"the empty value is rendered in a collection's own notation "
            f"({notation!r}): {result!r}"
        )


def test_an_empty_membered_value_is_distinguishable_from_a_flagged_one(
    rendered: _Rendered,
) -> None:
    """The pair the whole change turns on, read off one page: a finding
    carrying no members and one carrying several must not render alike.

    DERIVED from the requirement's own structure — the empty clause and
    the member clause are separate obligations — rather than from a single
    scenario, and asserted so that a renderer satisfying both by rendering
    nothing for either is caught.
    """
    assert _visible(rendered.result(EMPTY_STEP)) != _visible(
        rendered.result(MEMBERS_STEP)
    )
