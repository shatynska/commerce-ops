"""The launch detail page renders a carried finding's result ahead of its
comment (`launch-admin`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-admin/spec.md`

Covers its one ADDED requirement *A carried finding's result is rendered
ahead of its comment* and all eight of its scenarios (`tasks.md`
1.15-1.20):

- The field and value lead the outcome (1.15)
- The result carries no leading prose (1.15)
- The field reads as an admin's words (1.16)
- A field with no supplied wording still renders (1.16)
- An empty value renders as readable text (1.17)
- The distinction survives without colour (1.18)
- A recording with no carried finding is rendered unchanged (1.19)
- The evidence and provenance are still rendered (1.20)

See `test-manifest.md` at the change root for the full accounting of all
28 scenarios in this change.

## Level

The launch router over fakes for the stores and the catalog read — the
level and the seam-installing harness `test_launch_admin_detail.py`
established and `test_launch_admin_start_marks.py` reproduced, duplicated
here again rather than imported because this project shares no
test-helper module between test files, and `tests/**/test_*.py` is the
only path a test may be written to.

## How the assertions are made falsifiable

Four of the clauses below were written because a weaker test would pass a
wrong implementation, and each is asserted in the shape that excludes it:

- **Ordering by position, not by presence** (1.15, 1.18). The result and
  the comment are located as elements and compared by their place in the
  row's document order, with a check that neither is nested inside the
  other. Asserting only that two class names appear would pass a
  rendering whose only difference is a `color` declaration — which is
  exactly what the requirement forbids.
- **The stylesheet, not only the markup** (`read-a-finding-as-two-paragraphs`).
  Block-level markup does not entail stacked layout: three block-level
  children of a flex row rendered as three narrow columns in production
  while every markup assertion here passed. The layout obligation, the
  block-ness of the two parts, and the file's own brace balance are
  therefore asserted over the served stylesheet.
- **Visible text, not an element** (1.17). An empty value's result must
  carry readable characters beyond the field's own wording. "An element
  carrying a class and no text" is the failure the clause names by name.
- **A pinned common path** (1.19). The outcome cell of a recording that
  carries no finding is compared against a literal capture of what this
  page renders *today*, taken at this worktree's `9d0ba21` before any
  implementation existed. That is the majority of rows and the first
  place a regression lands.
- **No leading prose** (1.15). The result's text must *start with* the
  field's wording, not merely contain it.

## What is fixed, and what is INVENTED

Fixed by the delta: the two literal markers `finding-result` and
`finding-comment`; the bounded container's marker `evidence-clamp`; that
the result leads with the field and the value and nothing else; that the
field renders as an admin's words and, where a sink supplies none, as the
field's own name; that an empty value renders as visible text; that the
result and comment are separate block-level elements; that a recording
carrying no finding renders unchanged; and that the evidence and
provenance are still rendered.

Deliberately **not** fixed by the delta, and therefore not asserted:
weight, spacing, which token is used, and the wording an empty value
renders as. `design.md` records those as visual judgements settled by
looking at the running page (`tasks.md` 3.7).

INVENTED, each with its correction point named below and recorded in
`test-manifest.md`:

- **How the field's wording reaches the page.** This is the one place the
  artifacts leave a real gap: the delta requires the wording be supplied
  alongside the sink registration, `tasks.md` 2.5 fixes the stored payload
  as `{"field", "value", "comment"}` — carrying no wording — and nothing
  states how `launch_admin.py` learns it. `_supply_wording()` installs a
  mapping on the page module under `_WORDING_SEAM_NAMES`, keyed by both
  step identifier and field name, and falls back to a wording carried on
  the finding itself. It fails loudly naming both routes rather than
  letting the wording scenarios pass on the field name alone. Reported to
  the dispatcher as an unresolved question, not resolved here.
- How a recording is given a finding (`_FINDING_KWARGS`) and how one is
  spelled (`_FINDING_TYPES`) — the same correction points as
  `tests/unit/launch/domain/test_recorded_finding.py`.
- Which tags count as block-level (`_BLOCK_TAGS`). The delta says "block
  level" of the rendered response, and a test over HTML can read that
  only from the tag. A `<span>` given `display: block` by the stylesheet
  would fail here; correcting `_BLOCK_TAGS` is the fixture correction if
  that is the shape chosen.
- The page module, `_SEAMS`, `_render_on`, the session cookie, the detail
  route's discovery, the tree parser and `_row_of` — inherited unchanged
  from `test_launch_admin_start_marks.py`'s own documented assumptions.
- The fixture playbook, gates, step identifiers, dates and evidence text.

## Expected first-run state — two halves

- **Expected to FAIL on an absent target**: every scenario stated over a
  recording that *carries* a finding (1.15, 1.16, 1.17, 1.18, 1.20). No
  recording can carry one today, so each fails through
  `_finding_kwarg()`'s loud probe.
- **Expected to PASS on first run**: *A recording with no carried finding
  is rendered unchanged* (1.19), and its companion asserting that no
  `finding-` marker appears on such a row. Per `ai-toolkit:testing` a
  first-run pass in the target-exists situation is the expected result,
  not an alarm: the behaviour being asserted is what the page already
  does, and the test's job is to keep it doing it. A **failure** there
  after implementation is a regression on the common path.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pathlib
import re
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
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    return importlib.import_module(_PAGE_MODULE_NAME)


LISTING: Final = Discipline("listing")
MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")

PRINCIPAL: Final = "U01ALICE"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
RECORDED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)

#: Four steps at one gate, differing only in what their recording carries.
WORDED_STEP: Final = "listing.worded-finding"
BARE_STEP: Final = "listing.unworded-finding"
EMPTY_STEP: Final = "listing.empty-value-finding"
PLAIN_STEP: Final = "listing.no-finding-at-all"
COMMIT_STEP: Final = "strategy.commitment-agreed"

STEP_NAMES: Final[dict[str, str]] = {
    WORDED_STEP: "Work whose finding has a wording",
    BARE_STEP: "Work whose finding has no wording",
    EMPTY_STEP: "Work whose finding is empty",
    PLAIN_STEP: "Work carrying no finding",
    COMMIT_STEP: "Commitment to launch is agreed",
}

EVIDENCE: Final = (
    "Home and Kitchen then Kitchen and Dining then Cutting Boards. "
    "Demands an FDA food-contact declaration."
)
RECORDER_NAME: Final = "listing.subcategory_advisor"

WORDED_FIELD: Final = "sub_category"
WORDED_WORDING: Final = "Sub-category"
WORDED_VALUE: Final = "Kitchen and Dining then Cutting Boards"
WORDED_COMMENT: Final = "Rejected alternative Home Decor which carries no obligation."

BARE_FIELD: Final = "hazard_screen_raw"
BARE_VALUE: Final = "no hazardous categories"
BARE_COMMENT: Final = "Checked aerosols lithium cells pressurised containers."

EMPTY_FIELD: Final = "hazard_categories"
EMPTY_WORDING: Final = "Hazard categories"
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

#: INVENTED reading of "block-level element" over a rendered response: a
#: test can read that only from the tag. Correction point for a rendering
#: that reaches block-level some other way.
_BLOCK_TAGS: Final = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)

RESULT_MARKER: Final = "finding-result"
COMMENT_MARKER: Final = "finding-comment"


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
        _step(WORDED_STEP),
        _step(BARE_STEP),
        _step(EMPTY_STEP),
        _step(PLAIN_STEP),
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
        version="finding-render-v1", gates=_gates(), steps=(*steps, *fillers)
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
# Correction points for the carried finding
# ---------------------------------------------------------------------------

_FINDING_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_FINDING_TYPES: Final = (
    "CarriedFinding",
    "RecordedFinding",
    "KeptFinding",
    "Finding",
)
#: Where the page might learn a field's wording from.
_WORDING_SEAM_NAMES: Final = (
    "recorders",
    "finding_sinks",
    "sinks",
    "finding_wordings",
    "FIELD_WORDINGS",
)
#: A wording carried on the finding itself, if that is the route taken.
_WORDING_KEYS: Final = ("reads_as", "wording", "reads", "label")
_SINK_MODULES: Final = (
    "commerce_ops.launch.application",
    "commerce_ops.launch.application.ports",
)
_SINK_NAMES: Final = ("FindingSink", "Sink", "FindingRegistration")


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


def _carry(
    field_name: str,
    value: Any,
    comment: Any = _ABSENT,
    reads_as: str | None = None,
) -> Any:
    parts: dict[str, Any] = {"field": field_name, "value": value}
    if comment is not _ABSENT:
        parts["comment"] = comment
    if reads_as is not None:
        # Corrected during implementation: the wording route taken is a
        # wording carried on the finding itself (`_WORDING_KEYS`), which
        # `_supply_wording` declared but never exercised. Set under
        # whichever of those keys the finding type accepts.
        parts[_wording_key()] = reads_as
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            return found(**parts)
    return parts


def _sink_class() -> Any:
    for module_name in _SINK_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover
            continue
        for name in _SINK_NAMES:
            found = getattr(module, name, None)
            if isinstance(found, type):
                return found
    return None


async def _noop_record(product_id: Any, value: Any) -> object:  # pragma: no cover
    return object()


def _wording_entries() -> dict[str, Any]:
    """A mapping the page can read a wording out of, keyed by field name
    *and* by step identifier.

    INVENTED, and this file's largest assumption — see the module
    docstring. Field names map to the wording string; step identifiers map
    to a sink registration carrying it, where `FindingSink` exists. A
    page looking up either key finds something usable.
    """
    entries: dict[str, Any] = {
        WORDED_FIELD: WORDED_WORDING,
        EMPTY_FIELD: EMPTY_WORDING,
    }
    sink_type = _sink_class()
    if sink_type is not None:
        for step_id, field_name, wording in (
            (WORDED_STEP, WORDED_FIELD, WORDED_WORDING),
            (EMPTY_STEP, EMPTY_FIELD, EMPTY_WORDING),
            (BARE_STEP, BARE_FIELD, None),
        ):
            try:
                entries[step_id] = sink_type(_noop_record, field_name, wording)
            except TypeError:  # pragma: no cover - a differently shaped sink
                entries[step_id] = sink_type(
                    record=_noop_record, field=field_name, reads_as=wording
                )
    return entries


def _carries_wording() -> bool:
    """Whether the finding type takes a wording at all — the finding-borne
    route being available is the same question."""
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            accepted = set(inspect.signature(found).parameters)
            return any(key in accepted for key in _WORDING_KEYS)
    return False


def _wording_key() -> str:
    """The key a carried finding takes its wording under.

    Prefers whichever of `_WORDING_KEYS` the domain's finding type
    accepts, so the fixture follows the implementation rather than
    fixing it.
    """
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            accepted = set(inspect.signature(found).parameters)
            for key in _WORDING_KEYS:
                if key in accepted:
                    return key
    return _WORDING_KEYS[0]


def _supply_wording(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> bool:
    """Install whichever wording route the page exposes. Answers whether
    one was found.

    Two routes, and the finding-borne one is checked first because it is
    the one the change took: a wording carried on the recording needs no
    registry on this surface at all, which is what `launch-instance`
    requires of a page served by a different composition root from the
    one the sink is registered in.
    """
    for name in _WORDING_SEAM_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, _wording_entries())
            return True
    return _carries_wording()


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
# Seams — inherited from test_launch_admin_start_marks.py
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


# ---------------------------------------------------------------------------
# An HTML tree — inherited from test_launch_admin_start_marks.py
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
    """The smallest element holding that step's identifier and its name and
    no other served step.

    INVENTED locator, taken from `test_launch_admin_detail.py`. Fails
    loudly rather than returning the document, which would make every
    within-row assertion below vacuous.
    """
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


def _outcome_cell(row: _Node) -> _Node:
    """The row's outcome column — the cell this requirement is about.

    Located by the class the template already gives it, with a fallback to
    the cell holding the evidence text. Fails loudly.
    """
    for element in _elements(row):
        if "evidence" in _classes(element) or "outcome" in _classes(element):
            return element
    for element in _elements(row):
        if element.tag == "td" and _holds(element, EVIDENCE[:24]):
            return element
    pytest.fail(
        "the step's row carries no outcome cell (no element classed "
        "`evidence` or `outcome`, and none holding the evidence text) — "
        "correct `_outcome_cell`"
    )


def _marked(row: _Node, marker: str) -> _Node | None:
    found = [element for element in _elements(row) if marker in _classes(element)]
    if not found:
        return None
    assert len(found) == 1, (
        f"the row carries {len(found)} elements marked {marker!r}; the "
        "requirement names one result, one comment and one divide"
    )
    return found[0]


def _require_marked(row: _Node, marker: str) -> _Node:
    found = _marked(row, marker)
    if found is None:
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
    return found


def _order(row: _Node) -> list[_Node]:
    return list(_elements(row))


def _position(row: _Node, node: _Node) -> int:
    for index, element in enumerate(_order(row)):
        if element is node:
            return index
    raise AssertionError("the element is not inside the row")


def _is_inside(inner: _Node, outer: _Node) -> bool:
    node = inner.parent
    while node is not None:
        if node is outer:
            return True
        node = node.parent
    return False


def _visible(text: str) -> str:
    """The characters a reader can actually see: no whitespace of any kind,
    no non-breaking space."""
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

    def cell(self, step_id: str) -> _Node:
        return _outcome_cell(self.row(step_id))


def _record(
    launch: Launch,
    playbook: LaunchPlaybook,
    *,
    step_id: str,
    finding: Any = _UNSET,
) -> None:
    kwargs: dict[str, Any] = {
        "step_id": step_id,
        "outcome": Satisfied,
        "provenance": _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg()] = finding
    launch.record_step_outcome(playbook, **kwargs)


def _render(monkeypatch: pytest.MonkeyPatch, *, with_findings: bool) -> _Rendered:
    """One detail page.

    `with_findings=False` records only the finding-less step, so the
    common-path scenarios never touch the absent target and run against
    the page as it stands today.
    """
    playbook = _detail_playbook()
    product = _launching("BCB-2027-01", "Bamboo Cutting Board")
    launch, _ = Launch.start(
        product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    _record(launch, playbook, step_id=PLAIN_STEP)
    if with_findings:
        _record(
            launch,
            playbook,
            step_id=WORDED_STEP,
            finding=_carry(WORDED_FIELD, WORDED_VALUE, WORDED_COMMENT, WORDED_WORDING),
        )
        _record(
            launch,
            playbook,
            step_id=BARE_STEP,
            finding=_carry(BARE_FIELD, BARE_VALUE, BARE_COMMENT),
        )
        _record(
            launch,
            playbook,
            step_id=EMPTY_STEP,
            finding=_carry(EMPTY_FIELD, [], EMPTY_COMMENT, EMPTY_WORDING),
        )

    surface = _surface(monkeypatch, launch, product, playbook)
    route = _supply_wording(monkeypatch, surface.module) if with_findings else False
    return _Rendered(
        html=_detail_html(surface, product.id),
        playbook=playbook,
        wording_route=route,
    )


@pytest.fixture()
def rendered(monkeypatch: pytest.MonkeyPatch) -> _Rendered:
    """A page whose recordings carry findings — the absent target."""
    return _render(monkeypatch, with_findings=True)


@pytest.fixture()
def rendered_without_findings(monkeypatch: pytest.MonkeyPatch) -> _Rendered:
    """A page with one recording, carrying nothing — the common path,
    renderable today."""
    return _render(monkeypatch, with_findings=False)


# ---------------------------------------------------------------------------
# Scenario: The field and value lead the outcome (tasks.md 1.15)
# ---------------------------------------------------------------------------


def test_the_field_and_value_lead_the_outcome(rendered: _Rendered) -> None:
    """WHEN the detail page renders a step whose recording carries a
    finding THEN the finding's field and value are rendered ahead of the
    comment, the result element carrying `finding-result` and the comment
    element `finding-comment`.
    """
    row = rendered.row(WORDED_STEP)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    assert WORDED_VALUE in _all_text(result)
    assert WORDED_COMMENT in _all_text(comment)
    # SPECIFIED: ahead of — asserted by position, not by both being present.
    assert _position(row, result) < _position(row, comment)
    assert not _is_inside(comment, result)
    assert not _is_inside(result, comment)


def test_the_result_carries_no_leading_prose(rendered: _Rendered) -> None:
    """WHEN the detail page renders a carried finding's result THEN what
    precedes the field in that result is nothing — no introductory
    sentence and no narrating label.

    Asserted as "starts with", which a rendering carrying a lead-in fails
    and a rendering that merely *contains* the field would pass.
    """
    result = _require_marked(rendered.row(WORDED_STEP), RESULT_MARKER)
    rendered_field = WORDED_WORDING if rendered.wording_route else WORDED_FIELD

    text = _all_text(result).strip()
    assert text.startswith(rendered_field), (
        f"the result reads {text[:80]!r}, which does not lead with the "
        f"field {rendered_field!r}"
    )


def test_the_result_leads_the_comment_in_the_outcome_cell(
    rendered: _Rendered,
) -> None:
    """The requirement's "the result and comment lead the cell": both sit
    inside the outcome column, and the result is first inside it."""
    row = rendered.row(WORDED_STEP)
    cell = _outcome_cell(row)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    assert _is_inside(result, cell)
    assert _is_inside(comment, cell)
    assert _position(cell, result) < _position(cell, comment)


# ---------------------------------------------------------------------------
# Scenario: The field reads as an admin's words (tasks.md 1.16)
# ---------------------------------------------------------------------------


def test_the_field_reads_as_an_admins_words(rendered: _Rendered) -> None:
    """WHEN the detail page renders a carried finding whose sink supplies
    a wording for its field THEN that wording is rendered rather than the
    storage identifier.
    """
    if not rendered.wording_route:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} exposes no route a field's wording could "
            f"reach it by: none of {list(_WORDING_SEAM_NAMES)} is a module "
            "attribute, and the stored finding carries only field, value "
            "and comment (`tasks.md` 2.5). The delta requires the wording "
            "be supplied alongside the sink registration and rendered here "
            "— correct `_WORDING_SEAM_NAMES` to the implemented route"
        )
    result = _require_marked(rendered.row(WORDED_STEP), RESULT_MARKER)

    text = _all_text(result)
    assert WORDED_WORDING in text
    assert WORDED_FIELD not in text, (
        f"the storage identifier {WORDED_FIELD!r} is rendered; this "
        "capability requires an admin's words, not a snake_case token"
    )


def test_a_field_with_no_supplied_wording_still_renders(
    rendered: _Rendered,
) -> None:
    """WHEN the detail page renders a carried finding whose sink supplies
    no wording THEN the field's own name is rendered rather than nothing.

    "An unrendered fact is the failure this surface exists to prevent."
    """
    result = _require_marked(rendered.row(BARE_STEP), RESULT_MARKER)

    text = _all_text(result)
    assert BARE_FIELD in text, (
        f"a field with no supplied wording rendered as {text[:80]!r}; its "
        "own name is what must be rendered rather than nothing"
    )
    assert BARE_VALUE in text


# ---------------------------------------------------------------------------
# Scenario: An empty value renders as readable text (tasks.md 1.17)
# ---------------------------------------------------------------------------


def test_an_empty_value_renders_as_visible_text(rendered: _Rendered) -> None:
    """WHEN the detail page renders a step whose carried finding has an
    empty value THEN the result carries visible text standing for
    emptiness.

    The clause names its own failures: "rendering it as blank, as
    whitespace, as an element carrying a class and no text, or by omitting
    the result SHALL NOT satisfy this". So the assertion is on *text*, and
    on text beyond the field's own wording.
    """
    result = _require_marked(rendered.row(EMPTY_STEP), RESULT_MARKER)
    rendered_field = EMPTY_WORDING if rendered.wording_route else EMPTY_FIELD

    text = _all_text(result)
    assert _visible(text), "the result element carries a class and no text"
    remainder = text.replace(rendered_field, "", 1)
    assert _visible(remainder), (
        f"the result reads {text!r} — nothing beyond the field's own name, "
        "so a reader cannot see that the answer was 'none'"
    )


def test_an_empty_value_is_distinguishable_from_no_finding_at_all(
    rendered: _Rendered,
) -> None:
    """The scenario's second clause: "distinguishable from a step whose
    recording carries no finding at all".

    This is `tasks.md` 1.3's assertion at the page — the one the whole
    change turns on, read by a person rather than off a column.
    """
    empty_cell = rendered.cell(EMPTY_STEP)
    plain_cell = rendered.cell(PLAIN_STEP)

    assert _marked(rendered.row(EMPTY_STEP), RESULT_MARKER) is not None
    assert _marked(rendered.row(PLAIN_STEP), RESULT_MARKER) is None
    assert _visible(_all_text(empty_cell)) != _visible(_all_text(plain_cell))


# ---------------------------------------------------------------------------
# Scenario: The distinction survives without colour (tasks.md 1.18)
# ---------------------------------------------------------------------------


def test_the_distinction_survives_without_colour(rendered: _Rendered) -> None:
    """WHEN a carried finding's result and comment are rendered THEN they
    are separate block-level elements, neither containing the other, so
    that a rendering whose only difference is a colour declaration does
    not satisfy this.

    The separating element this scenario used to require is gone with
    `read-a-finding-as-two-paragraphs`: the break between two blocks is
    the separation. What is asserted is therefore the break itself --
    two distinct elements, ordered, neither nested in the other -- which
    a single element carrying two colours cannot satisfy.
    """
    row = rendered.row(WORDED_STEP)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    assert result is not comment
    assert _position(row, result) < _position(row, comment)
    assert not _is_inside(comment, result)
    assert not _is_inside(result, comment)


def test_no_separating_element_is_required(rendered: _Rendered) -> None:
    """WHEN a carried finding's result and comment are rendered with no
    element between them THEN the rendering satisfies this requirement,
    the break between the two blocks being the separation.

    This is the assertion that fails against the superseded spec, which
    required an element carrying `finding-divide` to sit between them.
    Written to fail against the live markup before being kept.
    """
    row = rendered.row(WORDED_STEP)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    parent = result.parent
    assert parent is not None and parent is comment.parent, (
        "the result and the comment do not share a parent, so nothing can "
        "be said about what sits between them"
    )
    siblings = [child for child in parent.children if isinstance(child, _Node)]
    between = siblings[siblings.index(result) + 1 : siblings.index(comment)]
    assert between == [], (
        "an element sits between the result and the comment; the separation "
        f"is the block break and needs no element: {[n.tag for n in between]}"
    )


def test_the_whole_outcome_is_bounded_together(rendered: _Rendered) -> None:
    """WHEN the detail page renders a step whose recording carries a
    finding THEN the result, the comment, the verbatim evidence and the
    provenance are all within one container carrying `evidence-clamp`,
    none of them bounded independently of the others.

    A reader pressing the control expects the cell to open, not a portion
    of it. Written to fail against the live markup, where the two parts
    sit outside that container entirely.
    """
    row = rendered.row(WORDED_STEP)
    clamp = _marked(row, "evidence-clamp")
    assert clamp is not None, (
        "the row carries no element marked `evidence-clamp`, so nothing "
        "bounds the outcome"
    )
    for marker in (
        RESULT_MARKER,
        COMMENT_MARKER,
        "evidence-text",
        "outcome-provenance",
    ):
        part = _require_marked(row, marker)
        assert _is_inside(part, clamp), (
            f"{marker!r} sits outside the bounded container, so the "
            "disclosure opens a portion of the cell rather than the cell"
        )


def test_the_result_and_comment_are_separate_block_level_elements(
    rendered: _Rendered,
) -> None:
    """The same requirement's first half, asserted on its own.

    **No tag is asserted.** The delta fixes no tag literal for these two,
    deliberately: `<p>` is invalid inside the `<span>` that bounds them
    and a `<div>` container would be invalid inside `<summary>`, so both
    are spans carried to block by the stylesheet. A test demanding a tag
    would enforce more than the requirement supports. That the two are
    laid out one below the other is asserted over the stylesheet instead,
    which is where the failure actually lives -- see
    `test_no_rule_lays_the_finding_out_in_a_row`.
    """
    row = rendered.row(WORDED_STEP)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    assert result is not comment
    assert result.parent is comment.parent


def test_the_two_markers_are_carried_by_different_elements(
    rendered: _Rendered,
) -> None:
    """The markers are "a necessary and not a sufficient condition": two
    class names on one element would satisfy a naive reading and separate
    nothing."""
    row = rendered.row(WORDED_STEP)
    result = _require_marked(row, RESULT_MARKER)
    comment = _require_marked(row, COMMENT_MARKER)

    assert COMMENT_MARKER not in _classes(result)
    assert RESULT_MARKER not in _classes(comment)


# ---------------------------------------------------------------------------
# Scenario: The evidence and provenance are still rendered (tasks.md 1.20)
# ---------------------------------------------------------------------------


def test_the_evidence_and_provenance_are_still_rendered(
    rendered: _Rendered,
) -> None:
    """WHEN the detail page renders a step whose recording carries a
    finding THEN the verbatim evidence and the recording's provenance are
    rendered as well, the result and comment leading rather than replacing
    them.

    "A presentation that dropped it in favour of a tidier rendering would
    lose the only account of what was actually read."
    """
    row = rendered.row(WORDED_STEP)
    cell = _outcome_cell(row)

    text = _all_text(cell)
    assert EVIDENCE in " ".join(text.split()), (
        "the verbatim evidence is no longer rendered for a step whose "
        "recording carries a finding"
    )
    assert RECORDER_NAME in text
    assert "automated" in text.lower()
    assert "2027-01-06" in text

    # ... and they follow the result and comment rather than preceding them.
    result = _require_marked(row, RESULT_MARKER)
    evidence_holders = [
        element
        for element in _elements(cell)
        if EVIDENCE in " ".join(_all_text(element).split())
    ]
    assert evidence_holders, "no element inside the outcome cell holds the evidence"
    innermost = min(evidence_holders, key=lambda node: len(_all_text(node)))
    assert _position(cell, result) < _position(cell, innermost)


# ---------------------------------------------------------------------------
# Scenario: A recording with no carried finding is rendered unchanged
# (tasks.md 1.19) — the common path, and expected to pass on first run
# ---------------------------------------------------------------------------

#: A literal capture of what this page renders today for a recording that
#: carries no finding, taken at `9d0ba21` before any implementation
#: existed, normalised for whitespace. Not a fixture to be regenerated: it
#: is the pin, and a diff against it is the regression this scenario
#: exists to catch.
PINNED_OUTCOME_CELL: Final = (
    '<td class="evidence">'
    '<details class="evidence-disclosure">'
    '<summary class="evidence-summary">'
    '<span class="evidence-clamp">'
    '<span class="evidence-text">'
    "Home and Kitchen then Kitchen and Dining then Cutting Boards. "
    "Demands an FDA food-contact declaration."
    "</span>"
    '<span class="outcome-provenance">'
    "recorded by listing.subcategory_advisor (automated) at "
    "2027-01-06 09:30 UTC"
    "</span>"
    "</span>"
    "</summary>"
    "</details>"
    "</td>"
)


def _cell_html(html: str, step_id: str, served: tuple[str, ...]) -> str:
    """The outcome cell's own markup, normalised for whitespace.

    Read out of the raw response rather than re-serialised from the tree,
    so the pin is a statement about what the page actually sends.
    """
    _row_of(html, step_id, served)  # fails loudly if the row is absent
    # Sliced out of *this step's* raw `<tr>`, not searched for across the
    # page. Corrected during implementation: every served step shares one
    # `Provenance`, and so one evidence string, which makes a page-wide
    # search for "the cell holding the evidence" match every recorded step
    # and never exactly one. Still read out of the raw response, so the
    # pin remains a statement about what the page actually sends.
    rows = [
        candidate
        for candidate in re.findall(r"<tr\b.*?</tr>", html, flags=re.DOTALL)
        if step_id in candidate
    ]
    assert len(rows) == 1, (
        f"expected one rendered row for {step_id!r}, found {len(rows)}"
    )
    cells = re.findall(r'<td class="evidence">.*?</td>', rows[0], flags=re.DOTALL)
    assert len(cells) == 1, (
        f"expected one outcome cell in the row for {step_id!r}, found {len(cells)}"
    )
    return re.sub(r">\s+<", "><", " ".join(cells[0].split()))


def test_a_recording_with_no_carried_finding_is_rendered_unchanged(
    rendered_without_findings: _Rendered,
) -> None:
    """WHEN the detail page renders a step whose recording carries no
    finding THEN its outcome renders as it did before this capability
    existed.

    Pinned against a literal capture rather than described, because
    "unchanged" is not otherwise assertable. This is the great majority of
    rows — every recording made before this capability and every recording
    by a handler reporting no finding — and the first place a regression
    lands.
    """
    actual = _cell_html(
        rendered_without_findings.html, PLAIN_STEP, rendered_without_findings.served
    )

    assert actual == PINNED_OUTCOME_CELL


def test_a_recording_with_no_carried_finding_carries_no_finding_markers(
    rendered_without_findings: _Rendered,
) -> None:
    """The same scenario read from the markers: none of the three appears
    on a row whose recording carries nothing.

    Stated separately from the pin because it survives a legitimate
    unrelated change to the cell's markup, and the pin does not."""
    row = rendered_without_findings.row(PLAIN_STEP)

    for marker in (RESULT_MARKER, COMMENT_MARKER):
        assert _marked(row, marker) is None, (
            f"a recording carrying no finding rendered a {marker!r} element"
        )


def test_the_common_path_is_undisturbed_on_a_page_that_also_carries_findings(
    rendered: _Rendered,
) -> None:
    """The regression this scenario is really about: a page rendering both
    kinds of row must leave the finding-less one exactly as it was.

    Runs against the absent target today and fails with the rest; once the
    implementation lands it is the row that catches a rendering change
    that leaked onto every step."""
    actual = _cell_html(rendered.html, PLAIN_STEP, rendered.served)

    assert actual == PINNED_OUTCOME_CELL


# ---------------------------------------------------------------------------
# Scenarios: No rule lays the two out in a row · The bound is not a count of
# lines (tasks.md 1.3a)
#
# Asserted over the served stylesheet, in the idiom this capability already
# uses for stylesheet obligations. These are the assertions that would have
# caught the columns defect: block-level markup does not entail stacked
# layout, and every markup-level assertion in this file passed against a
# rendering that read as three narrow columns.
# ---------------------------------------------------------------------------

_VOCABULARY = (
    pathlib.Path(__file__).resolve().parents[5]
    / "src/commerce_ops/shared/infrastructure/driving/static/vocabulary.css"
)


def _rules_reaching(css: str, selector_fragment: str) -> list[str]:
    """Every rule block whose selector mentions the fragment."""
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    return [body for selector, body in blocks if selector_fragment in selector]


def test_no_rule_lays_the_finding_out_in_a_row() -> None:
    """WHEN the served stylesheet is read THEN no rule reaching the
    container of a carried finding's result and comment lays its children
    out in a row.
    """
    css = _VOCABULARY.read_text()
    for body in _rules_reaching(css, "evidence-clamp"):
        # Flex and grid put children in a row by different defaults, so
        # they are asked different questions. Corrected after
        # `/code-review`: one branch had been written for both, which
        # accepted `grid-auto-flow: column` -- grid's *side by side* --
        # and rejected a plain `display: grid`, which stacks.
        if re.search(r"display:\s*(inline-)?flex", body):
            assert re.search(r"flex-direction:\s*column", body), (
                "a rule reaching the bounded container makes it a flex "
                "container with no column direction, which lays its "
                "children out in a row -- how a carried finding's parts "
                f"came to render as three narrow columns: {body.strip()[:120]!r}"
            )
        if re.search(r"display:\s*(inline-)?grid", body):
            assert not re.search(r"grid-auto-flow:\s*column", body), (
                "a rule reaching the bounded container flows its grid "
                "items by column, which places them side by side: "
                f"{body.strip()[:120]!r}"
            )


def test_the_bound_is_not_a_count_of_lines() -> None:
    """WHEN the served stylesheet is read THEN the rule bounding the
    container carrying `evidence-clamp` does not bound it by a count of
    lines.

    A line-count bound is defined over inline content; the parts of a
    carried finding are blocks, and bounding blocks that way is undefined
    across browsers.
    """
    css = _VOCABULARY.read_text()
    for body in _rules_reaching(css, "evidence-clamp"):
        assert "line-clamp" not in body, (
            "the bounded container is bounded by a count of lines, which "
            "is defined over inline content and not over the blocks it "
            f"now holds: {body.strip()[:120]!r}"
        )


def test_a_rule_makes_the_finding_s_two_parts_blocks() -> None:
    """The stylesheet half of *The distinction survives without colour*.

    The delta states the two are separate **block-level** elements, and
    both are spans — so the block-ness lives entirely in the stylesheet,
    and nothing in this file asserted it. Added after `/code-review`,
    which found an unclosed rule earlier in the file that nested these
    two: they still matched by accident, and would have been discarded
    outright by any engine without relaxed nesting, leaving the fact and
    the account run together on one line with the distinction carried by
    nothing at all. Every other assertion here passed against that.
    """
    css = _VOCABULARY.read_text()
    for marker in (RESULT_MARKER, COMMENT_MARKER):
        bodies = _rules_reaching(css, marker)
        assert bodies, f"no rule in the served stylesheet reaches .{marker}"
        assert any(re.search(r"display:\s*block", body) for body in bodies), (
            f".{marker} is never made block-level by the served stylesheet, "
            "so the two run together on one line and the distinction rests "
            "on colour alone"
        )


def test_the_served_stylesheet_is_brace_balanced() -> None:
    """Not a scenario: a guard on the file the two tests above read.

    An unclosed rule silently nests everything after it, so a rule can be
    present, matched by these tests, and still not apply. That is what
    happened — a merge resolution dropped one closing brace, and it
    reached production. Cheap to assert, and it fails at the file rather
    than at whichever rule happens to be downstream of the break.
    """
    css = re.sub(r"/\*.*?\*/", "", _VOCABULARY.read_text(), flags=re.DOTALL)
    depth = css.count("{") - css.count("}")
    assert depth == 0, (
        f"the served stylesheet has {depth} unclosed rule(s); everything "
        "after the break is nested inside it and may not apply at all"
    )
