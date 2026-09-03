"""The product dossier (`product-dossier`, requirements two to ten).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/product-dossier/spec.md`
— every ADDED requirement stated over the dossier itself:

- *The dossier is addressed by product identifier* — all three scenarios
- *The dossier renders the product as the catalog holds it* — all three
- *The dossier renders every retained result for the product, newest
  first* — all three
- *A result's fate is rendered, and a voided result is never shown as
  rejected* — all five
- *A decider is rendered as recorded, not resolved afresh* — both
- *An entry names its step where the playbook can name it, and never
  hides which step it was* — all three
- *The produced record states what it does not cover* — both
- *The dossier exists for a product with no results and for one with no
  launch* — all three
- *Both pages are read-only* — both, the second over both pages
- *The produced text is rendered as the text it is* — its one scenario

The index's own requirement is in `test_product_index_page.py`; the
guard, the header and the shared stylesheet are in
`test_product_surfaces_header_and_presentation.py`. `test-manifest.md` at
the change root records every scenario, every assertion's
classification, and the project questions this file answered by
assumption.

## Level

The page's routes over doubles for its collaborators. Every scenario
above is stated over *the rendered page* — what it carries, what it
refuses, what order it renders in — so the routes are the smallest unit
that can observe them, and no database is needed to see any of it. It is
the harness `test_playbook_admin_page.py` established for this module's
other admin surface.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The nine literal markers, exactly as spelled: `result-pending`,
  `result-accepted`, `result-rejected`, `result-withdrawn`,
  `step-unnamed`, `not-recorded`, `retained-for-decision`,
  `nothing-produced`, and — on the index — `product-retired`
  (`design.md` — Decision 11; `tasks.md` 5.2, 5.2a). `result-withdrawn`
  deliberately does **not** match the stored state spelling `voided`;
  a synonym for any of them is a failing test, not a stylistic choice.
- That an unknown identifier and an out-of-scope product are refused
  **identically**, in the shape of a route that does not exist
  (`tasks.md` 4.2), and that a SKU arriving at this address is one more
  identifier naming no product (`tasks.md` 4.4).
- That the page turns on the product and never on a launch (`tasks.md`
  4.3).
- That the page renders in the order the read answered and reorders
  nothing, and that the ordering *tiebreak* is asserted at the read
  rather than here, because the record the read exposes carries no row
  identifier (`tasks.md` 8.4a).
- That the decider is rendered as recorded and never re-resolved
  (`tasks.md` 2.7; `design.md` — Decision 6).
- That a step the playbook no longer defines, and a playbook that cannot
  be read at all, both fall back to the raw identifier and neither may
  fail the page (`tasks.md` 5.4).
- That read-only is asserted **negatively**: no form, and no element
  carrying `row-action` (`tasks.md` 8.4b).

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a **class token**, on the
  element or on something inside it. Correction point: `_carries`.
- How an entry is located: the largest ancestor of the element naming
  this result's text that names no other result's, stopping at the
  record's container. Correction point: `_entry_of`.
- The record shape the read answers — `_RetainedResult`, spelled as the
  stored row is in `test_automation_pass.py`'s `_PendingRow`, which is
  the shape `tasks.md` 2.4's field list mirrors. Correcting a spelling
  is a fixture correction; dropping a field is not.
- The page module's seams, installed by name through `_install`, which
  fails loudly naming the candidates rather than defaulting. Correction
  points: the `_*_NAMES` tuples.
- How a moment is rendered (`_renders_moment`). No artifact fixes a
  date format; several plausible ones are accepted and the failure names
  them.
- That the served playbook reaches the page through a store answering
  `load()` — the shape `playbook_admin.py` uses, which `design.md` says
  this adapter is shaped after. Correction point: `_FakeSteps`.

## Expected first-run state

`commerce_ops.launch.infrastructure.driving.product_dossier` does not
exist, so every test here is expected to fail at **import** — the
absent-target state, which establishes absence and nothing about the
assertions themselves.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27).
"""

from __future__ import annotations

import asyncio
import html as html_module
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Final, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.catalog.application import record_asin
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driving import (
    product_dossier as page_module,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching, Retired

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_MOVED: Final = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
CONFIRMER: Final = "Helen Shatynska"

SKU: Final = "BCB-2027-01"
NAME: Final = "Bamboo Cutting Board"
ASIN: Final = "B0EXAMPLE1"
OTHER_SKU: Final = "OTH-2027-02"
OTHER_NAME: Final = "Somebody Else's Widget"

# The literal markers the delta fixes (`design.md` — Decision 11).
RESULT_PENDING: Final = "result-pending"
RESULT_ACCEPTED: Final = "result-accepted"
RESULT_REJECTED: Final = "result-rejected"
RESULT_WITHDRAWN: Final = "result-withdrawn"
STATE_MARKERS: Final = (
    RESULT_PENDING,
    RESULT_ACCEPTED,
    RESULT_REJECTED,
    RESULT_WITHDRAWN,
)
STEP_UNNAMED: Final = "step-unnamed"
NOT_RECORDED: Final = "not-recorded"
RETAINED_FOR_DECISION: Final = "retained-for-decision"
NOTHING_PRODUCED: Final = "nothing-produced"
ROW_ACTION: Final = "row-action"

SERVED_STEP: Final = "listing.sub-category"
SERVED_STEP_NAME: Final = "Choose the sub-category node"
UNSERVED_STEP: Final = "listing.a-step-no-longer-served"
RETIRED_STEP: Final = "listing.a-retired-step"
RETIRED_STEP_NAME: Final = "Work nobody does any more"
HANDLER: Final = "listing.subcategory_advisor"

ALICE: Final = "Alice Admin"
ALICE_RENAMED: Final = "Alicia Administrator"
BOHDAN: Final = "Bohdan Colleague"

OLDEST_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
MIDDLE_AT: Final = datetime(2027, 1, 7, 9, 30, tzinfo=UTC)
NEWEST_AT: Final = datetime(2027, 1, 8, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 9, 11, 15, tzinfo=UTC)

ACCEPTED_TEXT: Final = "TOKENACCEPTED Home and Kitchen, Cutting Boards."
REJECTED_TEXT: Final = "TOKENREJECTED Sports and Outdoors, Cookware."
VOIDED_TEXT: Final = "TOKENVOIDED Toys and Games, Puzzles."
PENDING_TEXT: Final = "TOKENPENDING Garden and Outdoor, Planters."
TOKENS: Final = ("TOKENACCEPTED", "TOKENREJECTED", "TOKENVOIDED", "TOKENPENDING")

#: Model output stored verbatim, spanning lines. Carries angle brackets
#: on purpose and no quotes at all, so the escaped form Jinja produces is
#: exactly `html.escape`'s and the assertion needs no allowance.
MULTILINE_TEXT: Final = (
    "TOKENACCEPTED Recommended node:\n"
    "  Home > Kitchen > Cutting Boards\n"
    "Demands: <b>FDA food-contact declaration</b>\n"
    "Rejected alternative: Home > Home Decor"
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

_DECISION_WORDS: Final = (
    "accept",
    "reject",
    "approve",
    "decline",
    "decide",
)

#: Launch reads the page must not hold, named rather than scanned for as
#: a substring so an unrelated import cannot fail the assertion.
_LAUNCH_SEAMS: Final = (
    "launches",
    "launch_store",
    "launch_repository",
    "LaunchRepository",
    "read_launch",
    "read_launches",
)


# ---------------------------------------------------------------------------
# An HTML tree, in document order
# ---------------------------------------------------------------------------


@dataclass
class _Text:
    text: str


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None
    order: int
    children: list[_Node | _Text] = field(default_factory=list)


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {}, None, 0)
        self._stack: list[_Node] = [self.root]
        self._order = 0

    def _open(self, tag: str, attrs: list[tuple[str, str | None]]) -> _Node:
        self._order += 1
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1], self._order)
        self._stack[-1].children.append(node)
        return node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = self._open(tag, attrs)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].children.append(_Text(" ".join(data.split())))


def _tree(page: str) -> _Node:
    parser = _TreeParser()
    parser.feed(page)
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
    return " ".join(part for part in found if part)


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    """A vocabulary marker, read as a class token on the element or on
    something inside it — `playbook-admin`'s established reading."""
    if marker in _classes(node):
        return True
    return any(marker in _classes(child) for child in _elements(node))


def _page_carries(page: str, marker: str) -> bool:
    return any(marker in _classes(element) for element in _elements(_tree(page)))


def _marked(page: str, marker: str) -> list[_Node]:
    return [
        element for element in _elements(_tree(page)) if marker in _classes(element)
    ]


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _smallest_naming(root: _Node, needle: str) -> _Node:
    naming = [element for element in _elements(root) if needle in _all_text(element)]
    if not naming:
        pytest.fail(f"nothing on the page names {needle!r}")
    return min(naming, key=lambda element: len(_all_text(element)))


def _entry_of(root: _Node, token: str, others: tuple[str, ...] = TOKENS) -> _Node:
    """One result's entry.

    INVENTED: the largest ancestor of the element naming this result
    that names no *other* result and is not the record's own container.
    Tag-agnostic on purpose — the delta fixes what an entry carries, not
    what element it is. Correction point for a differently shaped entry.
    """
    node = _smallest_naming(root, token)
    rival = tuple(other for other in others if other != token)
    best = node
    for ancestor in _ancestors(node):
        if ancestor.tag in ("body", "html", "main"):
            break
        if RETAINED_FOR_DECISION in _classes(ancestor):
            break
        if any(other in _all_text(ancestor) for other in rival):
            break
        best = ancestor
    return best


def _links(node: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(node)
        if element.tag == "a" and element.attrs.get("href")
    ]


def _forms(page: str) -> list[_Node]:
    return [element for element in _elements(_tree(page)) if element.tag == "form"]


def _is_control(node: _Node) -> bool:
    """An affordance a member clicks — the reading
    `test_playbook_admin_presentation_vocabulary.py` records."""
    if node.attrs.get("role", "").lower() == "button":
        return True
    if node.tag in ("button", "form"):
        return True
    if node.tag == "input":
        return (node.attrs.get("type") or "text").lower() in ("submit", "image")
    if node.tag == "a":
        return "href" in node.attrs
    return any(verb in node.attrs for verb in _HX_VERBS)


def _control_haystack(node: _Node) -> str:
    """Everything naming what a control does — its destination, label
    and text. The `class` attribute is excluded on purpose: an entry's
    own state marker (`result-accepted`) is not a control's name."""
    parts = [
        node.attrs.get(key, "")
        for key in ("href", "formaction", "name", "value", "aria-label", "title")
    ]
    parts.extend(node.attrs.get(verb, "") for verb in _HX_VERBS)
    parts.append(_all_text(node))
    return " ".join(part for part in parts if part).lower()


def _positions(page: str, *needles: str) -> list[int]:
    found = []
    for needle in needles:
        at = page.find(needle)
        assert at >= 0, f"{needle!r} is not rendered at all"
        found.append(at)
    return found


#: DERIVED: no artifact fixes a date format, so several plausible ones
#: are accepted and a failure names every one that was tried.
def _moment_forms(moment: datetime) -> tuple[str, ...]:
    return (
        moment.date().isoformat(),
        moment.strftime("%d %b %Y"),
        moment.strftime("%b %d, %Y"),
        moment.strftime("%d.%m.%Y"),
        moment.strftime("%d/%m/%Y"),
    )


def _renders_moment(text: str, moment: datetime) -> bool:
    return any(form in text for form in _moment_forms(moment))


def _require_moment(text: str, moment: datetime, what: str) -> None:
    assert _renders_moment(text, moment), (
        f"{what} does not render {moment.isoformat()} in any of "
        f"{_moment_forms(moment)} — correct `_moment_forms` to the "
        f"implemented format (rendered: {text[:300]!r})"
    )


def _labels_near(page: str, marker: str) -> list[str]:
    """The text around each element carrying `marker`, so a marked field
    can be told from another marked field without pinning the page's
    structure."""
    found: list[str] = []
    for element in _marked(page, marker):
        chain = [element, *list(_ancestors(element))[:3]]
        found.append(" ".join(_all_text(node) for node in chain).lower())
    return found


# ---------------------------------------------------------------------------
# The record the read answers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RetainedResult:
    """INVENTED shape for `tasks.md` 2.4's frozen record, spelled as the
    stored row is in `test_automation_pass.py`'s `_PendingRow`. No row
    identifier: `tasks.md` 8.4a is explicit that the page never sees the
    one the ordering tiebreak turns on."""

    step_id: str
    handler: str
    proposed_outcome: str
    result_text: str
    produced_at: datetime
    state: str
    decided_by: str | None = None
    decided_at: datetime | None = None


def _result(**overrides: Any) -> _RetainedResult:
    attributes: dict[str, Any] = {
        "step_id": SERVED_STEP,
        "handler": HANDLER,
        "proposed_outcome": "Satisfied",
        "result_text": ACCEPTED_TEXT,
        "produced_at": OLDEST_AT,
        "state": "pending",
    }
    attributes.update(overrides)
    return _RetainedResult(**attributes)


def _accepted(**overrides: Any) -> _RetainedResult:
    defaults: dict[str, Any] = {
        "result_text": ACCEPTED_TEXT,
        "produced_at": NEWEST_AT,
        "state": "accepted",
        "decided_by": ALICE,
        "decided_at": DECIDED_AT,
    }
    defaults.update(overrides)
    return _result(**defaults)


def _rejected(**overrides: Any) -> _RetainedResult:
    defaults: dict[str, Any] = {
        "result_text": REJECTED_TEXT,
        "produced_at": MIDDLE_AT,
        "state": "rejected",
        "decided_by": BOHDAN,
        "decided_at": DECIDED_AT,
    }
    defaults.update(overrides)
    return _result(**defaults)


def _voided(**overrides: Any) -> _RetainedResult:
    """`void` leaves `decided_by` untouched, so a voided row carries no
    decider (`design.md` — Context; `tasks.md` 2.6)."""
    defaults: dict[str, Any] = {
        "result_text": VOIDED_TEXT,
        "produced_at": OLDEST_AT,
        "state": "voided",
        "decided_by": None,
        "decided_at": DECIDED_AT,
    }
    defaults.update(overrides)
    return _result(**defaults)


def _pending(**overrides: Any) -> _RetainedResult:
    return _result(
        result_text=PENDING_TEXT,
        produced_at=MIDDLE_AT,
        state="pending",
        decided_by=None,
        decided_at=None,
        **overrides,
    )


#: The read answers newest first (`launch-step-automation`), so a page
#: fixture that did not would be feeding the page something the read
#: never produces.
def _newest_first() -> tuple[_RetainedResult, ...]:
    return (_accepted(), _rejected(), _voided())


# ---------------------------------------------------------------------------
# The served playbook
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": SERVED_STEP,
        "name": SERVED_STEP_NAME,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "confirmer": "prs_confirmer",
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": HANDLER,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _StepRecord:
    """The store record shape `test_playbook_admin_page.py` records."""

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


class _FakeSteps:
    """The served-playbook source, in the `load()` shape
    `playbook_admin.py` uses — the adapter `design.md` says this one is
    shaped after."""

    def __init__(self, *definitions: StepDefinition, unreadable: bool = False) -> None:
        self.records = tuple(
            _StepRecord(definition, (index + 1) * 10)
            for index, definition in enumerate(definitions)
        )
        self.unreadable = unreadable

    async def load(self) -> tuple[tuple[Any, ...], int]:
        if self.unreadable:
            raise RuntimeError("the served playbook cannot be read")
        return self.records, 7

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        if self.unreadable:
            raise RuntimeError("the served playbook cannot be read")
        return tuple(record.definition for record in self.records)


def _served_steps(**overrides: Any) -> _FakeSteps:
    return _FakeSteps(
        _step(),
        _step(
            identifier=RETIRED_STEP,
            name=RETIRED_STEP_NAME,
            status=StepStatus.RETIRED,
        ),
        **overrides,
    )


# ---------------------------------------------------------------------------
# The page module's seams
# ---------------------------------------------------------------------------

_VERIFY_NAMES: Final = ("verify_admin_session", "verify")
_SCOPE_NAMES: Final = ("resolve_scope",)
_LIST_NAMES: Final = ("list_products",)
_GET_PRODUCT_NAMES: Final = ("get_product_by_id",)
_RETAINED_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)
_STEPS_NAMES: Final = (
    "steps",
    "playbook",
    "playbooks",
    "step_store",
    "playbook_store",
    "read_playbook",
    "served_playbook",
)
#: Optional: the requirement is that the decider is *not* re-resolved, so
#: a page with no members seam satisfies it structurally. Where one
#: exists, a contradicting membership is installed so "as recorded" is a
#: comparison rather than an absence.
_MEMBERS_NAMES: Final = ("members", "read_members", "members_reader")


def _install(
    monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...], value: Any, what: str
) -> str:
    for name in names:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, value)
            return name
    pytest.fail(
        f"the product surfaces expose no {what} seam under any of {names} — "
        "correct this file's probe to the implemented name"
    )


def _install_if_present(
    monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...], value: Any
) -> bool:
    for name in names:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, value)
            return True
    return False


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _scope_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AccessScope:
    for value in (*args, *kwargs.values()):
        if isinstance(value, AccessScope):
            return value
    pytest.fail(
        "the page made a scoped read without an access scope, so the "
        "caller's scope never reaches it (`tasks.md` 3.3, 5.1a)"
    )


def _product_id_in(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    for value in (*args, *kwargs.values()):
        if isinstance(value, ProductId):
            return value
    for value in (*args, *kwargs.values()):
        if isinstance(value, str) and value not in ("", PRINCIPAL):
            return value
    return None


class _FakeScopeResolution:
    def __init__(self, scope: AccessScope) -> None:
        self.scope = scope

    async def __call__(self, *args: Any, **kwargs: Any) -> AccessScope:
        return self.scope


class _FakeCatalog:
    def __init__(self, *products: Product) -> None:
        self.products = tuple(products)

    async def list_products(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        scope = _scope_in(args, kwargs)
        return tuple(product for product in self.products if scope.permits(product.id))

    async def get_product_by_id(self, *args: Any, **kwargs: Any) -> Product | None:
        scope = _scope_in(args, kwargs)
        wanted = _product_id_in(args, kwargs)
        for product in self.products:
            if str(product.id) == str(wanted) and scope.permits(product.id):
                return product
        return None


class _FakeRetainedRead:
    def __init__(self, *records: _RetainedResult) -> None:
        self.records = tuple(records)
        self.scopes: list[AccessScope] = []
        self.product_ids: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.scopes.append(_scope_in(args, kwargs))
        self.product_ids.append(_product_id_in(args, kwargs))
        return self.records


class _Member:
    def __init__(self, display_name: str, *, active: bool = True) -> None:
        self.id = "prs_01HQ8Z6M4A"
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeMembers:
    def __init__(self, *members: _Member) -> None:
        self._members = members

    async def list_members(self) -> tuple[_Member, ...]:
        return self._members


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class _AsinStore:
    """The smallest catalog store `record_asin` needs, so the ASIN a
    product carries is set through the use case rather than by reaching
    into the aggregate."""

    def __init__(self, product: Product) -> None:
        self.product = product

    async def get_by_id(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get_by_product_id(
        self, product_id: Any, *args: Any, **kwargs: Any
    ) -> Product:
        return self.product

    async def save(self, product: Product) -> None:
        self.product = product


def _product(sku: str = SKU, name: str = NAME) -> Product:
    """A freshly registered product: `Development`, no ASIN, and — by
    `product-catalog`'s own definition — no stage confirmer."""
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )


#: The two catalog-written facts the dossier's automation region renders.
#: A non-empty hazard set rather than an empty one, so that "fully
#: populated" means a value is present rather than a screening merely
#: having run.
SUB_CATEGORY: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
HAZARD_CATEGORIES: Final = ("supplements",)


def _fully_populated() -> Product:
    """Every field the dossier renders, populated: an ASIN, a stage
    entered by a human decision, and therefore a stage confirmer, and the
    two facts automated steps write to the catalog.

    The last two were added by `screen-for-hazard-categories`, which gave
    the dossier a region rendering the product's recorded sub-category and
    hazard categories. This fixture's name is its contract, and the
    page-wide `not-recorded` assertion in
    `test_a_products_identity_is_rendered_whole` depends on it: leaving
    either field unrecorded would make that assertion fail for a reason
    that has nothing to do with identity, and scoping the assertion
    instead would weaken it.
    """
    product = _product()
    product.change_stage(Launching(phase=1), confirmed_by=CONFIRMER, at=T_MOVED)
    product.record_sub_category(SUB_CATEGORY)
    product.record_hazard_categories(HAZARD_CATEGORIES)
    store = _AsinStore(product)
    # `_AsinStore` carries only the two membership `record_asin` reaches
    # for; the cast keeps the rest of `CatalogStore` out of a fixture
    # that never uses it, rather than stubbing a port this file does
    # not test.
    asyncio.run(record_asin(cast(Any, store), product.id, Asin(ASIN)))
    return store.product


def _retired_product() -> Product:
    product = _product()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_MOVED)
    return product


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


@dataclass
class _Surface:
    client: TestClient
    catalog: _FakeCatalog
    retained: _FakeRetainedRead
    product: Product
    members_installed: bool


def _app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    product: Product | None = None,
    others: tuple[Product, ...] = (),
    results: tuple[_RetainedResult, ...] = (),
    steps: _FakeSteps | None = None,
    scope: AccessScope | None = None,
    members: _FakeMembers | None = None,
    signed_in: bool = True,
) -> _Surface:
    subject = _fully_populated() if product is None else product
    catalog = _FakeCatalog(subject, *others)
    retained = _FakeRetainedRead(*results)
    resolution = _FakeScopeResolution(
        AccessScope.unrestricted() if scope is None else scope
    )

    _install(monkeypatch, _VERIFY_NAMES, _fake_verify, "admin-session")
    _install(monkeypatch, _SCOPE_NAMES, resolution, "scope-resolution")
    _install(monkeypatch, _LIST_NAMES, catalog.list_products, "product listing")
    _install(monkeypatch, _GET_PRODUCT_NAMES, catalog.get_product_by_id, "product read")
    _install(monkeypatch, _RETAINED_NAMES, retained, "retained-results read")
    _install(
        monkeypatch,
        _STEPS_NAMES,
        _served_steps() if steps is None else steps,
        "served-playbook",
    )
    members_installed = False
    if members is not None:
        members_installed = _install_if_present(monkeypatch, _MEMBERS_NAMES, members)

    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    if signed_in:
        client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surface(client, catalog, retained, subject, members_installed)


def _index_path() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the product router exposes no parameterless GET route"
    return min(candidates, key=len)


def _dossier_template() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and path.count("{") == 1:
            candidates.append(path)
    assert len(candidates) == 1, (
        "expected exactly one GET route taking a single path parameter — "
        f"the dossier's address — and found {candidates}"
    )
    return candidates[0]


def _dossier_path(value: Any) -> str:
    # Unwrapped, because `str(ProductId(...))` is the dataclass repr and
    # not the identifier: interpolating it builds a URL naming no product.
    value = getattr(value, "value", value)
    template = _dossier_template()
    opening = template.index("{")
    closing = template.index("}")
    return f"{template[:opening]}{value}{template[closing + 1 :]}"


def _get_dossier(surface: _Surface, value: Any | None = None) -> str:
    target = surface.product.id if value is None else value
    response = surface.client.get(_dossier_path(target))
    assert response.status_code == 200, response.text
    return str(response.text)


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def _absence(surface: _Surface) -> tuple[int, bytes, str | None]:
    return _shape(surface.client.get("/a-route-that-was-never-registered"))


def _permitting(*product_ids: ProductId) -> AccessScope:
    return AccessScope.permitting(product_ids)


# ---------------------------------------------------------------------------
# Requirement: The dossier is addressed by product identifier
# ---------------------------------------------------------------------------


def test_an_unknown_product_is_refused_as_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unknown product is refused as absence.

    WHEN the dossier is requested for an identifier no registered
    product carries
    THEN the response is identical in shape to requesting a route that
    does not exist.
    """
    surface = _app(monkeypatch)

    refused = surface.client.get(_dossier_path(uuid.uuid4()))

    # SPECIFIED: identical in shape to a route that does not exist.
    assert _shape(refused) == _absence(surface)
    # DERIVED guard: a registered product does render, so the equality
    # above is not an artifact of a dead route.
    assert surface.client.get(_dossier_path(surface.product.id)).status_code == 200


def test_an_out_of_scope_product_is_refused_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An out-of-scope product is refused identically.

    WHEN the dossier is requested for a registered product the caller's
    scope does not permit
    THEN the response is identical to the refusal for a product that
    does not exist, and reveals nothing about the product.
    """
    subject = _fully_populated()
    surface = _app(monkeypatch, product=subject, scope=_permitting())

    refused = surface.client.get(_dossier_path(subject.id))
    unknown = surface.client.get(_dossier_path(uuid.uuid4()))

    # SPECIFIED: identical to the refusal for a product that does not
    # exist — asserted against that refusal, not against a literal.
    assert _shape(refused) == _shape(unknown)
    assert _shape(refused) == _absence(surface)
    # SPECIFIED: and reveals nothing about the product.
    assert SKU not in refused.text
    assert NAME not in refused.text


def test_a_sku_is_not_an_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A SKU is not an address.

    WHEN the dossier is requested using a product's SKU rather than its
    identifier
    THEN it is refused as absence, exactly as any other identifier
    naming no product is.

    `design.md` — Decision 2: one canonical URL per product, and a SKU
    arriving here is one more identifier naming nothing.
    """
    surface = _app(monkeypatch)

    by_sku = surface.client.get(_dossier_path(SKU))
    by_nonsense = surface.client.get(_dossier_path(uuid.uuid4()))

    # SPECIFIED: refused as absence, exactly as any other identifier
    # naming no product is.
    assert _shape(by_sku) == _shape(by_nonsense)
    assert _shape(by_sku) == _absence(surface)


# ---------------------------------------------------------------------------
# Requirement: The dossier renders the product as the catalog holds it
# ---------------------------------------------------------------------------


def test_a_products_identity_is_rendered_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A product's identity is rendered whole.

    WHEN the dossier is rendered for a product the catalog holds with
    every field populated
    THEN the page presents its SKU, name, marketplace, ASIN, lifecycle
    stage, stage-entry moment and stage confirmer.
    """
    surface = _app(monkeypatch)

    page = _get_dossier(surface)
    text = _all_text(_tree(page))

    # SPECIFIED: all seven.
    assert SKU in page
    assert NAME in page
    assert MARKETPLACE.value in page
    assert ASIN in page
    assert "launching" in text.lower(), (
        "the dossier renders no lifecycle stage naming `Launching` "
        f"(rendered: {text[:300]!r})"
    )
    _require_moment(page, T_MOVED, "the dossier's stage-entry field")
    assert CONFIRMER in page
    # SPECIFIED, negatively: nothing is `not-recorded` on a product whose
    # fields are all populated, or the marker would say nothing when it
    # appears.
    assert not _page_carries(page, NOT_RECORDED)


def test_an_absent_asin_is_stated_not_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An absent ASIN is stated, not blank.

    WHEN the dossier is rendered for a product registered without an
    ASIN
    THEN its ASIN field is rendered carrying `not-recorded`, and is not
    left blank.
    """
    registered = _product()
    surface = _app(monkeypatch, product=registered)

    page = _get_dossier(surface)

    # SPECIFIED: the marker is carried...
    assert _page_carries(page, NOT_RECORDED), (
        f"the dossier carries no {NOT_RECORDED!r}, so an absent ASIN is "
        "indistinguishable from data the page failed to load"
    )
    # ...and it is the ASIN field that carries it.
    assert any("asin" in label for label in _labels_near(page, NOT_RECORDED)), (
        f"nothing carrying {NOT_RECORDED!r} sits near an ASIN label — "
        f"marked fields read as {_labels_near(page, NOT_RECORDED)}"
    )


def test_a_product_with_no_stage_confirmer_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A product with no stage confirmer says so.

    WHEN the dossier is rendered for a freshly registered product still
    in `Development`
    THEN its stage-confirmer field is rendered carrying `not-recorded`,
    rather than presenting an empty confirmer.

    `Product.register` leaves `stage_confirmed_by` as `None` for every
    product still in `Development` (`tasks.md` 4.5), so this is the
    common case rather than the edge one.
    """
    registered = _product()
    assert registered.stage_confirmed_by is None  # DERIVED precondition
    surface = _app(monkeypatch, product=registered)

    page = _get_dossier(surface)

    labels = _labels_near(page, NOT_RECORDED)
    # SPECIFIED: the confirmer field carries the marker.
    assert any("confirm" in label for label in labels), (
        f"nothing carrying {NOT_RECORDED!r} sits near a stage-confirmer "
        f"label — marked fields read as {labels}"
    )


# ---------------------------------------------------------------------------
# Requirement: The dossier renders every retained result for the
# product, newest first
# ---------------------------------------------------------------------------


def test_results_are_ordered_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Results are ordered newest first.

    WHEN the dossier is rendered for a product carrying results produced
    at different moments
    THEN they appear ordered by the moment produced, most recent first.

    The read answers them newest-first, which is what
    `launch-step-automation` requires of it; the page's own guarantee is
    that it renders them in that order. The *tiebreak* that makes the
    order total is asserted at the read and not here, because the record
    the page receives carries no row identifier (`tasks.md` 8.4a).
    """
    surface = _app(monkeypatch, results=_newest_first())

    page = _get_dossier(surface)

    # SPECIFIED: most recent first.
    positions = _positions(page, "TOKENACCEPTED", "TOKENREJECTED", "TOKENVOIDED")
    assert positions == sorted(positions), (
        "the entries are not rendered newest first — rendered order is "
        f"{positions}, and the produced moments descend "
        f"{[r.produced_at.isoformat() for r in _newest_first()]}"
    )


def test_an_entry_carries_what_produced_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An entry carries what produced it.

    WHEN a retained result is rendered
    THEN its entry presents the step, the handler, the proposed outcome,
    the produced text and the moment it was produced.
    """
    surface = _app(monkeypatch, results=(_accepted(),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")
    text = _all_text(entry)

    # SPECIFIED: the step (named, since the served playbook defines it).
    assert SERVED_STEP_NAME in text or SERVED_STEP in text
    # SPECIFIED: the handler.
    assert HANDLER in text
    # SPECIFIED: the proposed outcome.
    assert "Satisfied" in text
    # SPECIFIED: the produced text.
    assert "TOKENACCEPTED" in text
    # SPECIFIED: the moment it was produced.
    _require_moment(text, NEWEST_AT, "the entry's produced-moment field")


def test_the_page_renders_in_the_order_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The page renders in the order it was given.

    WHEN the dossier is rendered for a product whose retained results
    the read answers in a given order
    THEN the entries appear in that order, and the page reorders
    nothing.

    The read is made to answer in an order that is *not* newest-first,
    so a page sorting by anything of its own — the produced moment, the
    step, the state — is caught here. Together with the test above this
    is what "renders in the order the read answered and reorders
    nothing" means; neither assertion alone establishes it.
    """
    answered = (_voided(), _accepted(), _rejected())
    surface = _app(monkeypatch, results=answered)

    page = _get_dossier(surface)

    # DERIVED precondition: this order really is not the newest-first
    # one, so the assertion below is not satisfiable by re-sorting.
    assert [record.produced_at for record in answered] != sorted(
        (record.produced_at for record in answered), reverse=True
    )
    # SPECIFIED: the entries appear in the order the read answered.
    positions = _positions(page, "TOKENVOIDED", "TOKENACCEPTED", "TOKENREJECTED")
    assert positions == sorted(positions), (
        "the page reordered the entries the read answered — rendered "
        f"positions {positions}"
    )


# ---------------------------------------------------------------------------
# Requirement: A result's fate is rendered, and a voided result is never
# shown as rejected
# ---------------------------------------------------------------------------


def test_an_accepted_result_names_its_decider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An accepted result names its decider.

    WHEN an entry for an accepted result is rendered
    THEN it carries `result-accepted` and presents who decided it and
    when.
    """
    surface = _app(monkeypatch, results=(_accepted(),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")

    # SPECIFIED: the marker, exactly as the delta spells it.
    assert _carries(entry, RESULT_ACCEPTED), (
        f"the accepted entry carries no {RESULT_ACCEPTED!r} "
        f"(classes present: {sorted(_classes(entry))})"
    )
    # SPECIFIED: who decided it, and when.
    assert ALICE in _all_text(entry)
    _require_moment(_all_text(entry), DECIDED_AT, "the accepted entry")


def test_a_rejected_result_names_its_decider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected result names its decider.

    WHEN an entry for a rejected result is rendered
    THEN it carries `result-rejected` and presents who decided it and
    when.
    """
    surface = _app(monkeypatch, results=(_rejected(),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENREJECTED")

    # SPECIFIED: the marker, and the decider with the moment.
    assert _carries(entry, RESULT_REJECTED)
    assert BOHDAN in _all_text(entry)
    _require_moment(_all_text(entry), DECIDED_AT, "the rejected entry")


def test_a_voided_result_is_withdrawn_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A voided result is withdrawn, not rejected.

    WHEN an entry for a voided result is rendered
    THEN it carries `result-withdrawn`, does not carry `result-rejected`,
    and presents no decider.

    This is the one rendering rule on the page where a wrong label
    misattributes a decision to a member, which is why the delta fixes
    the literal form — and why `result-withdrawn` deliberately does not
    match the stored state spelling `voided`.
    """
    surface = _app(monkeypatch, results=(_voided(), _rejected()))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENVOIDED")

    # SPECIFIED: it carries `result-withdrawn`.
    assert _carries(entry, RESULT_WITHDRAWN), (
        f"the voided entry carries no {RESULT_WITHDRAWN!r} — note that the "
        "marker names what the page says, and deliberately does not match "
        "the stored state `voided`"
    )
    # SPECIFIED: and does not carry `result-rejected`.
    assert not _carries(entry, RESULT_REJECTED), (
        "the voided entry is labelled as a rejection, attributing to the "
        "member who tried to decide a judgement they never made"
    )
    # SPECIFIED: and presents no decider. Bohdan decided the *rejected*
    # entry on the same page, so this is a per-entry claim rather than a
    # page-wide absence.
    assert BOHDAN not in _all_text(entry)
    assert ALICE not in _all_text(entry)


def test_a_pending_result_is_shown_as_awaiting_a_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A pending result is shown as awaiting a decision.

    WHEN an entry for a result no member has decided is rendered
    THEN it carries `result-pending` and presents no decider.
    """
    surface = _app(monkeypatch, results=(_pending(), _accepted()))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENPENDING")

    # SPECIFIED: it carries `result-pending`...
    assert _carries(entry, RESULT_PENDING)
    # ...and is not presented as though it had been settled.
    assert not _carries(entry, RESULT_ACCEPTED)
    assert not _carries(entry, RESULT_REJECTED)
    assert not _carries(entry, RESULT_WITHDRAWN)
    # SPECIFIED: and presents no decider.
    assert ALICE not in _all_text(entry)
    assert BOHDAN not in _all_text(entry)


def test_an_entry_carries_one_state_and_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An entry carries one state and no other.

    WHEN any entry in the produced record is rendered
    THEN it carries exactly one of `result-pending`, `result-accepted`,
    `result-rejected` and `result-withdrawn`.
    """
    surface = _app(
        monkeypatch, results=(_accepted(), _rejected(), _voided(), _pending())
    )

    page = _get_dossier(surface)
    root = _tree(page)

    for token, expected in (
        ("TOKENACCEPTED", RESULT_ACCEPTED),
        ("TOKENREJECTED", RESULT_REJECTED),
        ("TOKENVOIDED", RESULT_WITHDRAWN),
        ("TOKENPENDING", RESULT_PENDING),
    ):
        entry = _entry_of(root, token)
        carried = [marker for marker in STATE_MARKERS if _carries(entry, marker)]
        # SPECIFIED: exactly one, and the one the state calls for.
        assert carried == [expected], (
            f"the entry for {token} carries {carried}, not exactly [{expected!r}]"
        )


# ---------------------------------------------------------------------------
# Requirement: A decider is rendered as recorded, not resolved afresh
# ---------------------------------------------------------------------------


def test_a_renamed_decider_keeps_the_recorded_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A renamed decider keeps the recorded name.

    WHEN the dossier renders an entry decided by a member whose membership
    display name has since changed
    THEN the entry presents the name recorded with the decision, not the
    membership's current one.

    A membership carrying the *new* name is installed where the page has a
    members seam at all, so "as recorded" is a comparison rather than an
    absence; where it has none, the requirement holds structurally and
    the recorded name is still asserted.
    """
    surface = _app(
        monkeypatch,
        results=(_accepted(),),
        members=_FakeMembers(_Member(ALICE_RENAMED)),
    )

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")

    # SPECIFIED: the name recorded with the decision.
    assert ALICE in _all_text(entry)
    # SPECIFIED: not the membership's current one.
    assert ALICE_RENAMED not in page, (
        "the dossier renders the decider's *current* members name, so a "
        "record of past decisions re-renders itself as its subjects change"
    )


def test_a_deactivated_decider_still_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A deactivated decider still appears.

    WHEN the dossier renders an entry decided by a member whose membership
    entry has since been deactivated
    THEN the entry still presents that decider and the moment of the
    decision.
    """
    surface = _app(
        monkeypatch,
        results=(_accepted(),),
        members=_FakeMembers(_Member(ALICE, active=False)),
    )

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")

    # SPECIFIED: the decider, and the moment of the decision.
    assert ALICE in _all_text(entry)
    _require_moment(_all_text(entry), DECIDED_AT, "the entry")


# ---------------------------------------------------------------------------
# Requirement: An entry names its step where the playbook can name it,
# and never hides which step it was
# ---------------------------------------------------------------------------


def test_a_served_step_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A served step is named.

    WHEN an entry is rendered for a step the served playbook defines
    THEN the entry presents that step's name and does not carry
    `step-unnamed`.
    """
    surface = _app(monkeypatch, results=(_accepted(step_id=SERVED_STEP),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")

    # SPECIFIED: the step's name.
    assert SERVED_STEP_NAME in _all_text(entry)
    # SPECIFIED: and no fallback marker.
    assert not _carries(entry, STEP_UNNAMED)


@pytest.mark.parametrize(
    "step_id",
    [UNSERVED_STEP, RETIRED_STEP],
    ids=["absent-from-the-playbook", "moved-out-of-active"],
)
def test_a_step_the_playbook_no_longer_serves_still_renders(
    step_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A step the playbook no longer serves still renders.

    WHEN an entry is rendered for a step the served playbook no longer
    defines
    THEN the entry still renders, identified by the step's identifier
    and carrying `step-unnamed`.

    Both ways a step stops being served are exercised: gone from the
    step set entirely, and present but moved out of `active`. The
    requirement names the second outright — "a step retired or moved out
    of `active` is exactly the circumstance that voids a proposal" — and
    only `active` steps are served anywhere in this system.
    """
    surface = _app(monkeypatch, results=(_accepted(step_id=step_id),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENACCEPTED")

    # SPECIFIED: it still renders, identified by the step's identifier.
    assert step_id in _all_text(entry)
    # SPECIFIED: carrying `step-unnamed`.
    assert _carries(entry, STEP_UNNAMED), (
        f"the entry for {step_id!r} carries no {STEP_UNNAMED!r}, so a "
        "fallback is indistinguishable from a step whose authored name "
        "happens to be its identifier"
    )
    if step_id == RETIRED_STEP:
        # SPECIFIED: it is the *served* playbook that can name a step,
        # and a retired step is not served.
        assert RETIRED_STEP_NAME not in page


def test_an_unreadable_playbook_does_not_fail_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unreadable playbook does not fail the page.

    WHEN the dossier is rendered while the served playbook cannot be
    read
    THEN the page still renders every entry, each identified by its step
    identifier and carrying `step-unnamed`.

    `design.md` — Decision 7: the record is the page's reason to exist;
    a name is an improvement on it, and an improvement that can fail the
    page is a worse page.
    """
    surface = _app(
        monkeypatch,
        results=_newest_first(),
        steps=_FakeSteps(_step(), unreadable=True),
    )

    response = surface.client.get(_dossier_path(surface.product.id))

    # SPECIFIED: the page still renders.
    assert response.status_code == 200, response.text
    page = str(response.text)
    root = _tree(page)
    # SPECIFIED: every entry, by its step identifier, carrying the marker.
    for token in ("TOKENACCEPTED", "TOKENREJECTED", "TOKENVOIDED"):
        entry = _entry_of(root, token)
        assert SERVED_STEP in _all_text(entry)
        assert _carries(entry, STEP_UNNAMED)
    assert SERVED_STEP_NAME not in page


# ---------------------------------------------------------------------------
# Requirement: The produced record states what it does not cover
# ---------------------------------------------------------------------------


def test_the_record_is_labelled_for_what_it_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The record is labelled for what it holds.

    WHEN the dossier's produced record is rendered
    THEN its container carries `retained-for-decision`.
    """
    surface = _app(monkeypatch, results=_newest_first())

    page = _get_dossier(surface)

    # SPECIFIED: the container carries the marker.
    assert _page_carries(page, RETAINED_FOR_DECISION), (
        f"the produced record carries no {RETAINED_FOR_DECISION!r}, so the "
        "qualification can be dropped by a later edit to the prose without "
        "any test noticing"
    )
    # SPECIFIED by the requirement's own statement: what carries the
    # marker really is the record's container — the entries sit inside
    # it.
    containers = _marked(page, RETAINED_FOR_DECISION)
    assert any(
        all(token in _all_text(container) for token in ("TOKENACCEPTED",))
        for container in containers
    ), (
        f"nothing carrying {RETAINED_FOR_DECISION!r} contains the record's "
        "entries, so the marker is not on the record's container"
    )


def test_the_qualification_is_present_on_an_empty_record_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The qualification is present on an empty record too.

    WHEN the dossier is rendered for a product carrying no retained
    results
    THEN the record's container still carries `retained-for-decision`.

    The requirement is "most wrong precisely for the products whose
    steps need no confirmation" — which is exactly the empty case.
    """
    surface = _app(monkeypatch, results=())

    page = _get_dossier(surface)

    # SPECIFIED: still carried.
    assert _page_carries(page, RETAINED_FOR_DECISION)


# ---------------------------------------------------------------------------
# Requirement: The dossier exists for a product with no results and for
# one with no launch
# ---------------------------------------------------------------------------


def test_a_product_that_never_launched_has_a_dossier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A product that never launched has a dossier.

    WHEN the dossier is rendered for a product with no launch position
    at all
    THEN the page renders the product's identity and its record carries
    `nothing-produced`.

    Nothing about a launch reaches this page — `tasks.md` 4.3 turns it
    on the product — so a product with no launch position is one whose
    retained record is empty by construction (`design.md` — Risks), and
    the empty read below is exactly that state.
    """
    surface = _app(monkeypatch, results=())

    response = surface.client.get(_dossier_path(surface.product.id))

    # SPECIFIED: the page renders.
    assert response.status_code == 200, response.text
    page = str(response.text)
    # SPECIFIED: the product's identity.
    assert SKU in page
    assert NAME in page
    # SPECIFIED: and the record carries `nothing-produced`.
    assert _page_carries(page, NOTHING_PRODUCED)


def test_a_graduated_launch_does_not_remove_the_dossier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A graduated launch does not remove the dossier.

    WHEN the dossier is rendered for a product whose launch has reached
    `graduated`
    THEN the page renders the product's identity and every result
    retained for it.

    The page is given no launch at all, which is `tasks.md` 4.3's
    requirement rather than a convenience: a page that read one could
    condition itself on its gate. That the read itself keeps answering
    after graduation is asserted against a real launch in
    `tests/integration/launch/test_retained_results_read_live.py`.
    """
    surface = _app(monkeypatch, results=_newest_first())

    page = _get_dossier(surface)

    # SPECIFIED: the product's identity, and every retained result.
    assert SKU in page
    assert NAME in page
    for token in ("TOKENACCEPTED", "TOKENREJECTED", "TOKENVOIDED"):
        assert token in page

    # SPECIFIED, structurally: no launch read reaches the page, so no
    # launch state can make the dossier appear or disappear. Named
    # spellings rather than a substring scan, so an unrelated import
    # does not fail this for the wrong reason.
    reached = [name for name in _LAUNCH_SEAMS if hasattr(page_module, name)]
    assert reached == [], (
        f"the product surfaces reach for a launch under {reached}, so the "
        "dossier can be conditioned on one (`tasks.md` 4.3)"
    )


def test_an_empty_record_is_stated_not_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An empty record is stated, not blank.

    WHEN the dossier is rendered for a product carrying no retained
    results
    THEN its record carries `nothing-produced`, rather than presenting
    an empty record region.
    """
    surface = _app(monkeypatch, results=())

    page = _get_dossier(surface)

    # SPECIFIED: the marker is carried...
    assert _page_carries(page, NOTHING_PRODUCED), (
        f"an empty produced record carries no {NOTHING_PRODUCED!r}, so a "
        "blank region reads as a page that failed to load"
    )
    # ...and it is stated inside the record, not somewhere unrelated.
    marked = _marked(page, NOTHING_PRODUCED)
    assert marked, "no element carries the marker"
    assert any(_all_text(element).strip() for element in marked), (
        f"the {NOTHING_PRODUCED!r} element states nothing at all, which is "
        "the blank region the requirement exists to forbid"
    )


# ---------------------------------------------------------------------------
# Requirement: Both pages are read-only
# ---------------------------------------------------------------------------


def test_a_pending_entry_offers_no_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A pending entry offers no decision.

    WHEN the dossier renders an entry awaiting a decision
    THEN it offers no control that accepts or rejects it, and the entry
    contains no form.

    Accepting and rejecting keep their Slack path: the decision flow's
    once-only settlement, members checks and refusals are all specified
    against it, and a second door would put them behind something
    nothing has specified.
    """
    surface = _app(monkeypatch, results=(_pending(),))

    page = _get_dossier(surface)
    entry = _entry_of(_tree(page), "TOKENPENDING")

    # SPECIFIED: the entry contains no form.
    assert [element for element in _elements(entry) if element.tag == "form"] == [], (
        "the pending entry contains a form, so it offers a write"
    )
    # SPECIFIED: and no control that accepts or rejects it.
    offers = [
        _control_haystack(element)
        for element in (entry, *_elements(entry))
        if _is_control(element)
        and any(word in _control_haystack(element) for word in _DECISION_WORDS)
    ]
    assert offers == [], (
        "the pending entry offers a decision control on the page, putting "
        f"the Slack path's guarantees behind a second door: {offers}"
    )


def test_neither_page_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Neither page writes.

    WHEN either page is rendered
    THEN its response contains no form and no element carrying
    `row-action`.

    Asserted over both pages here — the index is asserted again in
    `test_product_index_page.py`, whose fixture holds retired products
    the index would set apart. `tasks.md` 8.4b: the assertion is the
    *absence* of a form and of the marker, which on a page with no
    action controls is the whole claim.
    """
    surface = _app(monkeypatch, results=(_pending(), _accepted()))

    dossier = _get_dossier(surface)
    index = surface.client.get(_index_path())
    assert index.status_code == 200, index.text

    for label, page in (("dossier", dossier), ("index", str(index.text))):
        # SPECIFIED: no form.
        assert _forms(page) == [], f"the {label} renders a form"
        # SPECIFIED: no element carrying `row-action`.
        assert not _page_carries(page, ROW_ACTION), (
            f"the {label} carries {ROW_ACTION!r}, the marker every action "
            "control on an admin page must carry"
        )


# ---------------------------------------------------------------------------
# Requirement: The produced text is rendered as the text it is
# ---------------------------------------------------------------------------


def test_produced_text_renders_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Produced text renders as written.

    WHEN an entry whose produced text spans several lines is rendered
    THEN the text appears with its line structure intact and is not
    interpreted as markup.

    Asserted against the escaped-but-otherwise-verbatim form, which is
    the one string that is true only when *both* halves hold: the
    newlines survive (line structure preserved by styling, not by
    markup — `tasks.md` 5.7) and the angle brackets do not (Jinja's
    autoescaping — `design.md` — Risks). The fixture text carries no
    quotes, so `html.escape`'s output is exactly Jinja's.
    """
    surface = _app(monkeypatch, results=(_accepted(result_text=MULTILINE_TEXT),))

    page = _get_dossier(surface)

    # SPECIFIED: with its line structure intact, and not interpreted as
    # markup.
    assert html_module.escape(MULTILINE_TEXT) in page, (
        "the produced text is not rendered verbatim-with-escaping: either "
        "its newlines were replaced by markup, or its angle brackets were "
        "not escaped, or its wording was altered"
    )
    # SPECIFIED, stated the other way for a legible failure: the injected
    # markup did not become markup.
    assert "<b>FDA food-contact declaration</b>" not in page
    assert not any(element.tag == "b" for element in _elements(_tree(page))), (
        "the produced text was interpreted as markup"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The ordering *tiebreak*. `tasks.md` 8.4a forbids asserting it here:
#   the record `tasks.md` 2.4 exposes carries no row identifier, so the
#   page cannot see what it turns on. It is asserted at the read, in
#   `tests/integration/launch/test_retained_results_read_live.py`.
# - How the produced text *looks* — that `white-space: pre-wrap` (or
#   whatever `vocabulary.css` gains) actually renders the newlines as
#   lines. That is a computed style, which no server response carries;
#   `tasks.md` 9.2 and 9.3 carry the by-hand checks.
# - `delivered_at`. `tasks.md` 5.3 says not to render it, but the delta
#   states no requirement about it, so asserting its absence would pin a
#   task's instruction as though it were specified behaviour.
# ---------------------------------------------------------------------------
