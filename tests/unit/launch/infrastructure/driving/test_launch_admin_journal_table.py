"""The launch detail page's journal section, as revised by
`structure-the-launch-journal-table`: a table, each row carrying its
entry's label and a `category-<value>` marker.

Derived strictly from the delta spec
`openspec/changes/structure-the-launch-journal-table/specs/launch-admin/spec.md`
— the one MODIFIED requirement, *A launch's detail page renders its
journal, newest first*, and its four scenarios:

- *An entry names what occurred, when, and what caused it* — REVISED here
  (below).
- *An entry's row shows its label and carries its category marker* — NEW.
- *Entries render newest first* — REVISED here (below).
- *An empty journal says so* — UNCHANGED, and NOT repeated here: it
  constructs no entry at all, so nothing about this delta's entry-shape
  change touches it, and it is already covered by
  `test_launch_admin_detail.py::test_an_empty_journal_says_so`.

## Why the first and third scenarios are REVISED, not left to the
## existing tests that already carry their titles

`test_launch_admin_detail.py` already has
`test_a_journal_entry_names_what_occurred_when_and_what_caused_it` and
`test_journal_entries_render_newest_first`. Both build their fake journal
entries as `type("_Entry", (), {"what": ..., "when": ..., "cause": ...})()`
— carrying none of `kind`, `label` or `category`. That was a faithful
model of the entry shape `launch-journal` handed this page **before**
this change (`JournalEntry(kind, what, when, cause)`, per that file's own
`add-launch-tracking-pages` provenance) — except it omits even `kind`,
which the pre-change shape already carried.

This change adds `label` and `category` to every composed entry
(`launch-journal`'s sibling delta), and this page's `JournalLine` is
required to carry both through. A `_journal_lines` that reads
`entry.label` / `entry.category` off an entry object that carries
neither raises `AttributeError` — so those two existing tests' fixtures
model a shape this change supersedes, and are flagged as candidates for
correction in the report rather than edited here (this pass is additive
only). The tests below re-derive the same two scenarios against an entry
shaped the way a real composed `JournalEntry` reads once this change
lands — `kind`, `what`, `when`, `cause`, `label` and `category` all
present — so they hold both before and after `_journal_lines` starts
reading the two new fields.

## Level

The launch router mounted alone, over fakes for the launch/playbook/
catalog/roster ports and the `read_journal` seam — the same composition
`test_launch_admin_detail.py` uses for its own journal scenarios, pared
to what a journal-only page needs: no step or gate content is exercised
here, so the fixture playbook holds the eight specified gates and no
step at all (the same shape that file's own `EMPTY_PLAYBOOK` is).

## Expected first-run state

**The label/category-marker scenario is expected to fail on absence.**
`_journal_lines` does not yet read `entry.label` / `entry.category`
(confirmed by reading `launch_admin.py` at review time — it constructs
`JournalLine(what=entry.what, when=entry.when, cause=entry.cause)`
only), and the template renders no `category-` marker. Per
`ai-toolkit:testing`, failing here establishes only absence.

**The what/when/cause and newest-first scenarios are not expected to
fail on absence.** Those facts are unchanged by this delta and already
implemented (`add-launch-tracking-pages`) — the assertions below add
`label`/`category` to the fixture shape, not to what is asserted about
`what`/`when`/`cause`/ordering, so they may pass immediately. That is
not a defect in the test: `ai-toolkit:testing` does not require every
test to fail before implementation, only that a test failing on absence
be recognised as establishing absence and nothing more, which is a
different claim from "every test must currently fail".

## What is fixed, and what is INVENTED

Fixed by the artifacts: the four marker tokens `category-progression`,
`category-judgment`, `category-blocked`, `category-admin`, given
literally because "the literal tokens are given because they are what a
test is derived from" (`launch-admin` spec, quoting the base spec's own
rule for `outcome-tag` / `state-*`); that the detail page renders its
journal as a table; that a row's label is shown; and that an empty
journal still states "nothing is recorded".

INVENTED, each with its correction point named at the helper: every
module/port seam (`_SEAMS`, reused verbatim from
`test_launch_admin_detail.py`'s own `_SEAMS`, since both files resolve
the same page module); the fixture gates, product and dates; that a
marker is carried as a token among `class`/`id`/`data-*` attributes
(`_attribute_tokens`, `_carries_marker`) rather than some other
observable, mirroring how `test_launch_admin_detail.py` reads
`outcome-tag`/`state-*`; and the row locator `_journal_row`, which walks
from the smallest element holding an entry's unique `what` text up to
the nearest `<tr>` ancestor — a page not using literal `<tr>` markup for
a table row needs this corrected.
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

from commerce_ops.access.application import create_person, list_people
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    LaunchPlaybook,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching

# ---------------------------------------------------------------------------
# The module under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    return importlib.import_module(_PAGE_MODULE_NAME)


_JOURNAL_SEAM_NAMES: Final = (
    "read_journal",
    "journal",
    "read_launch_journal",
    "journal_entries",
)


def _journal_seam(module: ModuleType) -> str:
    for name in _JOURNAL_SEAM_NAMES:
        if hasattr(module, name):
            return name
    pytest.fail(
        f"{_PAGE_MODULE_NAME} exposes no journal seam under any of "
        f"{_JOURNAL_SEAM_NAMES}"
    )


# ---------------------------------------------------------------------------
# Fixed vocabulary and fixture values
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

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
PRINCIPAL: Final = "U01ALICE"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

#: SPECIFIED (`launch-admin` delta spec, quoting the base spec's rule):
#: the four literal marker tokens a row is required to carry.
CATEGORY_MARKERS: Final[dict[str, str]] = {
    "progression": "category-progression",
    "judgment": "category-judgment",
    "blocked": "category-blocked",
    "admin": "category-admin",
}


#: Gates whose coherence rule requires human confirmation to open
#: (`launch-playbook`) — the same set every sibling test file fixes.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=(
                GateOpening.REQUIRES_CONFIRMATION
                if identifier in CONFIRMATION_GATES
                else GateOpening.AUTOMATIC
            ),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


#: A playbook holding the eight specified gates and no step at all — the
#: journal section renders independently of step/gate content, so this
#: is the same shape `test_launch_admin_detail.py` calls `EMPTY_PLAYBOOK`.
PLAYBOOK: Final = LaunchPlaybook(version="journal-table-v1", gates=_gates(), steps=())


def _launching(sku: str, name: str) -> Product:
    product = Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )
    product.change_stage(Launching(phase=1), confirmed_by="Helen", at=T_REGISTERED)
    return product


def _start(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=LAUNCH_DATE
    )
    return launch


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


async def _roster_with_extra_person(
    display_name: str, *, slack_identity: str
) -> _FakeRosterStore:
    """`_build_roster()`'s usual roster (the admin session's own principal,
    "Alice Admin" — needed for the session to verify and for scope to
    permit the product at all), plus one more named person, for a test
    that needs to know that second person's generated identifier ahead
    of time."""
    store = await _build_roster()
    await create_person(
        roster=store,
        principal="the-seeding-admin",
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=False,
    )
    return store


def _roster_store() -> _FakeRosterStore:
    return asyncio.run(_build_roster())


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
# Installing the page's seams
# ---------------------------------------------------------------------------

#: INVENTED, reused verbatim from `test_launch_admin_detail.py`'s own
#: `_SEAMS` (both files resolve the same page module).
_SEAMS: Final[dict[str, tuple[str, ...]]] = {
    "verify": ("verify_admin_session",),
    "launches": ("launches", "launch_store", "launch_positions", "store"),
    "playbooks": ("playbooks", "playbook_store", "playbook_repository", "playbook"),
    "roster": ("roster", "people", "roster_store", "read_roster"),
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
    pytest.fail(f"{_PAGE_MODULE_NAME} exposes no seam for the day it renders on")


@dataclass(frozen=True)
class _Surface:
    client: TestClient
    module: ModuleType


def _surface(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launches: _FakeLaunchStore,
    catalog: _Catalog,
    journal_entries: tuple[Any, ...] = (),
    roster: Any = None,
) -> _Surface:
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(
        monkeypatch, module, "roster", roster if roster is not None else _roster_store()
    )
    _install(monkeypatch, module, "list_products", catalog.list_products)
    _install(monkeypatch, module, "get_product_by_id", catalog.get_product_by_id)

    async def _journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return journal_entries

    monkeypatch.setattr(module, _journal_seam(module), _journal)
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
    ]
    assert len(candidates) == 1
    return str(candidates[0])


def _detail_path(module: ModuleType, product_id: ProductId) -> str:
    template = _detail_template(module)
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + product_id.value + template[closed + 1 :]


def _detail_html(surface: _Surface, product_id: ProductId) -> str:
    response = surface.client.get(_detail_path(surface.module, product_id))
    assert response.status_code == 200, (
        f"the detail page for {product_id} was not served: "
        f"{response.status_code} {response.text[:400]}"
    )
    return str(response.text)


# ---------------------------------------------------------------------------
# A world every test starts from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    surface: _Surface
    product: Product


def _world(monkeypatch: pytest.MonkeyPatch, journal_entries: tuple[Any, ...]) -> _World:
    product = _launching("PX-200", "Beta widget")
    launch = _start(product.id)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        journal_entries=journal_entries,
    )
    return _World(surface, product)


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


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _all_text(node)


def _renders_date(node: _Node, day: date) -> bool:
    haystack = _all_text(node)
    return day.isoformat() in haystack or (
        str(day.day) in haystack and str(day.year) in haystack
    )


def _attribute_tokens(node: _Node) -> set[str]:
    """Every whitespace-separated token carried in `class`, `id` or a
    `data-*` attribute — INVENTED as where a presentation marker lives,
    mirroring how `test_launch_admin_detail.py` reads `outcome-tag` /
    `state-*`."""
    tokens: set[str] = set()
    for key, value in node.attrs.items():
        if key in ("class", "id") or key.startswith("data-"):
            tokens.update(value.split())
    return tokens


def _carries_marker(node: _Node, marker: str) -> bool:
    return marker in _attribute_tokens(node)


def _journal_row(html: str, mark: str) -> _Node:
    """The row rendering the entry uniquely identified by `mark` (its
    `what` text): the smallest element holding it, walked up to the
    nearest `<tr>` ancestor.

    INVENTED locator; correction point named in the module docstring.
    """
    root = _tree(html)
    candidates = [element for element in _elements(root) if _holds(element, mark)]
    if not candidates:
        pytest.fail(
            f"no element on the detail page holds {mark!r} — the journal "
            f"entry does not appear to be rendered at all"
        )
    holder = min(candidates, key=lambda element: 1 + sum(1 for _ in _elements(element)))
    walker: _Node | None = holder
    while walker is not None and walker.tag not in ("tr", "#document"):
        walker = walker.parent
    if walker is None or walker.tag != "tr":
        pytest.fail(
            f"the element holding {mark!r} has no `<tr>` ancestor, so the "
            "journal is not rendered with literal table-row markup — "
            "correct `_journal_row` if the page expresses a row another way "
            f"(page text: {_flat(_all_text(root))[:400]!r})"
        )
    return walker


def _journal_table(html: str) -> _Node | None:
    """The element rendering the journal as a table.

    INVENTED: the first `<table>` found on the page. The fixture playbook
    (`PLAYBOOK`) holds the eight specified gates and no step at all, so
    nothing else on this page renders as a table — a page that adds one
    needs this corrected to the element actually holding the journal's
    marks.
    """
    root = _tree(html)
    tables = [element for element in _elements(root) if element.tag == "table"]
    return tables[0] if tables else None


# ---------------------------------------------------------------------------
# A fake composed journal entry — the shape a real `JournalEntry` carries:
# `kind`, `what`, `when`, `cause`, `label`, `category`, `subject`,
# `source`, `actor` all present. Updated for
# `structure-the-launch-journal-table`'s follow-on refinement, which
# splits the page's rendered `cause` sentence into raw `subject`/
# `source`/`who` columns; `cause` stays on the fake entry (a real
# `JournalEntry` still carries it) even though the page no longer reads
# it, so a fixture built before that split still shapes a valid entry.
# ---------------------------------------------------------------------------


def _entry(
    *,
    kind: str,
    what: str,
    when: datetime,
    cause: str,
    label: str,
    category: str,
    subject: str | None = None,
    source: str | None = None,
    actor: str | None = None,
) -> Any:
    return type(
        "_Entry",
        (),
        {
            "kind": kind,
            "what": what,
            "when": when,
            "cause": cause,
            "label": label,
            "category": category,
            "subject": subject,
            "source": source,
            "actor": actor,
        },
    )()


# ===========================================================================
# Requirement: A launch's detail page renders its journal, newest first
# ===========================================================================


def test_an_entry_names_what_occurred_when_and_what_caused_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An entry names what occurred, when, and what caused it
    (REVISED twice: first for `label`/`category`, then for the follow-on
    refinement that splits the rendered `cause` sentence into raw
    `subject`/`source`/`who` columns instead — this page no longer reads
    `cause` at all, so "what caused it" is now checked as the source and
    the actor rendering as their own facts).

    WHEN a launch's journal holds an entry
    THEN it is rendered naming what occurred, when it occurred, its
    source, and who recorded it.
    """
    occurred = "the commit gate was approved, uniquely-marked-occurrence"
    when = datetime(2027, 3, 2, 10, 30, tzinfo=UTC)
    source = "slack"
    # An actor not present in `_roster_store()`'s fixture roster (only
    # "Alice Admin" is seeded), so `who` renders this raw value rather
    # than a resolved display name -- resolution itself is exercised by
    # `test_an_entrys_who_column_resolves_a_known_actor_to_their_name`.
    actor = "an-actor-not-on-the-roster"
    entry = _entry(
        kind="gate-approval-recorded",
        what=occurred,
        when=when,
        cause="an approval recorded by Helen in Slack",
        label="Approval",
        category="judgment",
        subject="commit",
        source=source,
        actor=actor,
    )
    world = _world(monkeypatch, journal_entries=(entry,))

    html = _detail_html(world.surface, world.product.id)

    text = _all_text(_tree(html))
    # SPECIFIED: naming what occurred...
    assert occurred in text, f"the journal entry does not name what occurred: {text!r}"
    # ...when it occurred...
    assert _renders_date(_tree(html), when.date()), (
        f"the journal entry does not name when it occurred: {text!r}"
    )
    # ...and what caused it -- now its source and who recorded it, each
    # in their own column rather than a composed sentence.
    assert source in text, f"the journal entry does not name its source: {text!r}"
    assert actor.lower() in text, (
        f"the journal entry does not name who recorded it: {text!r}"
    )


def test_journal_entries_render_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Entries render newest first (REVISED: against entries
    that also carry `label`/`category`).

    WHEN a launch's journal holds several entries
    THEN they are rendered most recent first.
    """
    marks = (
        "the-oldest-table-entry",
        "the-middle-table-entry",
        "the-newest-table-entry",
    )
    moments = (
        datetime(2027, 1, 2, 9, 0, tzinfo=UTC),
        datetime(2027, 2, 3, 9, 0, tzinfo=UTC),
        datetime(2027, 3, 4, 9, 0, tzinfo=UTC),
    )
    # Handed over oldest-first, so passing cannot be arrival order.
    entries = tuple(
        _entry(
            kind="launch-started",
            what=mark,
            when=moment,
            cause="a recorded launch start",
            label="Start",
            category="progression",
        )
        for mark, moment in zip(marks, moments, strict=True)
    )
    world = _world(monkeypatch, journal_entries=entries)

    html = _detail_html(world.surface, world.product.id).lower()

    # SPECIFIED: most recent first.
    positions = [html.index(mark) for mark in reversed(marks)]
    assert positions == sorted(positions), (
        f"the journal renders {marks} in the order they arrived rather than "
        "most recent first"
    )


def test_an_entrys_row_shows_its_label_and_carries_its_category_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An entry's row shows its label and carries its category
    marker.

    WHEN a launch's journal holds an entry
    THEN its row shows the entry's short label, and carries the marker
    `category-` followed by its category.

    Exercised for all four categories at once, exhaustively, since the
    marker vocabulary is closed at four (`design.md`'s table) and a page
    wiring three of the four correctly would still fail an admin scanning
    for the fourth.
    """
    fixtures = (
        ("mark-progression-entry", "Start", "progression"),
        ("mark-judgment-entry", "Attestation", "judgment"),
        ("mark-blocked-entry", "Refusal", "blocked"),
        ("mark-admin-entry", "Date Moved", "admin"),
    )
    entries = tuple(
        _entry(
            kind="launch-started",
            what=mark,
            when=datetime(2027, 5, index + 1, 9, 0, tzinfo=UTC),
            cause="a recorded occurrence",
            label=label,
            category=category,
        )
        for index, (mark, label, category) in enumerate(fixtures)
    )
    world = _world(monkeypatch, journal_entries=entries)

    html = _detail_html(world.surface, world.product.id)

    # SPECIFIED (requirement prose): the journal renders as a table.
    assert _journal_table(html) is not None, (
        "the detail page's journal section does not render as a `<table>` "
        f"element at all: {_flat(_all_text(_tree(html)))[:400]!r}"
    )

    for mark, label, category in fixtures:
        row = _journal_row(html, mark)
        # SPECIFIED: the row shows the entry's short label.
        assert label.lower() in _all_text(row), (
            f"the row for {mark!r} does not show its label {label!r}: "
            f"{_all_text(row)!r}"
        )
        # SPECIFIED: the row carries `category-` followed by its category
        # — the literal token, since "the literal tokens are given
        # because they are what a test is derived from".
        marker = CATEGORY_MARKERS[category]
        assert _carries_marker(row, marker), (
            f"the row for {mark!r} (category {category!r}) does not carry "
            f"the marker {marker!r}: attrs={row.attrs!r}"
        )
        # DERIVED guard: it carries *its own* marker, not one of the
        # other three — a page that marked every row `category-admin`
        # would otherwise pass the assertion above.
        for other_category, other_marker in CATEGORY_MARKERS.items():
            if other_category != category:
                assert not _carries_marker(row, other_marker), (
                    f"the row for {mark!r} (category {category!r}) also "
                    f"carries {other_marker!r}, another category's marker"
                )


def test_an_entrys_who_column_resolves_a_known_actor_to_their_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal table's `Who` column, for a follow-on refinement to
    `structure-the-launch-journal-table`: an entry's `actor` is a roster
    identifier (`Person.identifier`) where it names one, and a reader
    should see the person's name rather than that raw identifier.

    Built against a roster with one extra named person beyond the usual
    admin-session principal (`_roster_with_extra_person`), so that
    person's generated identifier is known ahead of time rather than
    assumed, while the session still verifies and scope still permits
    the product.
    """
    store = asyncio.run(
        _roster_with_extra_person("Olena Approver", slack_identity="U0OLENA")
    )
    people = asyncio.run(list_people(roster=store))
    olena = next(person for person in people if person.display_name == "Olena Approver")
    identifier = olena.identifier

    entry = _entry(
        kind="gate-approval-recorded",
        what="the commit gate was approved",
        when=datetime(2027, 3, 2, 10, 30, tzinfo=UTC),
        cause="an approval recorded by Olena in Slack",
        label="Approval",
        category="judgment",
        subject="commit",
        source="slack",
        actor=identifier,
    )
    product = _launching("PX-201", "Gamma widget")
    launch = _start(product.id)
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(launch),
        catalog=_Catalog(product),
        journal_entries=(entry,),
        roster=store,
    )

    html = _detail_html(surface, product.id)
    text = _all_text(_tree(html))

    # SPECIFIED (this refinement): the actor resolves to the person's name.
    assert "olena approver" in text, (
        f"the journal does not show the resolved actor name: {text!r}"
    )
    # DERIVED guard: the raw roster identifier is not shown in its place
    # -- resolution replaces the raw value rather than accompanying it.
    assert identifier.lower() not in text, (
        f"the journal shows the raw actor identifier {identifier!r} "
        f"instead of (or alongside) the resolved name: {text!r}"
    )
