"""The detail page's outcome tags and state markers, and what a launch's
marks are about (`launch-admin`,
`tidy-the-launch-pages-presentation`).

Derived strictly from the delta spec
`openspec/changes/tidy-the-launch-pages-presentation/specs/launch-admin/spec.md`
— the requirement *A step's outcome is rendered as a tag carrying its
state* and all seven of its scenarios:

- *An outcome renders as a tag carrying its state*
- *Unrecorded stays distinguishable from not started*
- *A mark names what it is about*
- *A recording time keeps its zone*
- *An outcome renders as words, not as its token*
- *An unknown outcome still renders*
- *Long evidence is bounded, not truncated*

Two of the requirement's claims are **not** scenarios and are not tested
here, because its own text sends them elsewhere: that the evidence's
measure is bounded, and that the tag and the edge are legible, "SHALL be
confirmed by direct inspection of the rendered page" (`tasks.md` 6.4).
No response carries either. What *is* read here is the half a response
does carry — that the whole of a long evidence is present and
untruncated.

## Level

The launch router mounted in an app of its own, over fakes for the
stores and the catalog read — the level and harness
`test_launch_admin_detail.py` established for the same page, duplicated
rather than imported because this project shares no test-helper module
between test files and `tests/**/test_*.py` is the only path a test may
be written to here. Six scenarios are stated about the detail page and
one about the list; both are served by this one router, so no wider
composition is needed and nothing narrower can observe them.

## The unknown outcome, and how it is reached

*An unknown outcome still renders* carries a note saying the vocabulary
is closed at six members, "so this case is not reachable through the
domain today. It is stated as an obligation on the page's own mapping —
exercised at the mapping, not through a launch."

It is exercised here by recording an outcome the vocabulary does not
hold (`_Postponed`) straight onto the aggregate. `record_step_outcome`
restricts only which *terminal* outcomes a hazard permits, so an
out-of-vocabulary class is stored as given: the launch is a fixture
carrying a value the domain will not produce, and what the test observes
is the page's mapping meeting one. That is the mapping being exercised
rather than the domain being extended — no member is added to
`StepOutcome`, and nothing outside this fixture can reach the state.

## Expected first-run state

**The target already exists.** This change's implementation is in the
working tree ahead of these tests, which reverses this project's usual
order (`design.md` — Decision 8). Per `ai-toolkit:testing`, a pass on
the first run is therefore the expected result and establishes that the
page currently behaves as asserted — it is *not* the fourth failure
state. What a pass does not establish is that these assertions
discriminate; that was established separately, by re-running each
predicate against the same responses with the marker, the tag, the words
or the evidence removed, and is recorded in the manifest.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1427 passed, 0
failed, 2 xfailed, on 2026-08-28. Scoped to the two commit-time tiers,
which are the tiers this file joins; the integration tier was not run
(no database configured here).

## What is fixed, and what is INVENTED

Fixed by the delta, which gives the literal tokens "because they are
what a test is derived from":

- `outcome-tag` on the element the outcome is rendered within.
- `state-` followed by the outcome's own name lowercased, on the element
  holding the step — computed here from the domain classes
  (`_state_marker`) rather than restated, so the expectation cannot
  drift from the vocabulary.
- `state-unrecorded` for a step carrying no recorded outcome, and that
  it is never the same marker as the recorded not-started one.
- That the two also differ in the **words** they render.
- That a member the page does not know renders under its own name.
- That each of the launch's marks names the thing it is a fact about —
  the gate for awaiting confirmation, the launch date for its own mark
  — rather than naming the state alone.
- That a recording time is rendered no coarser than the minute and
  carries the zone it is read in.
- That the whole of a long evidence is present in the response.

INVENTED, each with its correction point named in the code:

- That "carries the marker `X`" is read as a **class token**, the
  reading `test_playbook_admin_presentation_vocabulary.py` established
  for this same vocabulary. Correction point: `_carries`.
- That "the element holding the step" is the step's own row, or the
  nearest ancestor of it that holds no *other* served step. An ancestor
  holding two steps could not carry one step's state. Correction point:
  `_state_element`.
- The **words** each outcome may be rendered as. The delta fixes that
  they are words rather than the vocabulary's tokens, never which
  words. Correction point: `_WORDING`.
- The reading of "carries the zone it is read in": a zone designator —
  `UTC`, `Z`, an offset, an abbreviation or an IANA name — rendered on
  the element carrying the time or on its parent. Correction point:
  `_ZONE`, `_time_and_zone`.
- Every module seam, the render date's injection, and how a step row, a
  launch row and a gate group are located — inherited from
  `test_launch_admin_detail.py` and `test_launch_admin_list.py`.
  Correction points: `_SEAMS`, `_render_on`, `_step_row`, `_rows`.
- The fixture's dates, recording instants, gates and step identifiers.

Correcting a seam, a wording constant or a locator is a fixture
correction (failure state 3 in `ai-toolkit:testing`). What must survive
unweakened is what each test asserts: which marker each state carries,
that two states never share one, that an unknown member still reaches
the page, and that no evidence is cut short.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from tests.support.html import Node as _Node
from tests.support.html import Text as _Text
from tests.support.html import ancestors as _ancestors
from tests.support.html import attribute_text as _attribute_text
from tests.support.html import classes as _classes
from tests.support.html import elements as _elements
from tests.support.html import flat as _flat
from tests.support.html import size as _size
from tests.support.html import tree as _tree
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook

# ---------------------------------------------------------------------------
# The module under test, resolved by name
# ---------------------------------------------------------------------------

_PAGE_MODULE_NAME: Final = "commerce_ops.launch.infrastructure.driving.launch_admin"


def _page_module() -> ModuleType:
    try:
        return importlib.import_module(_PAGE_MODULE_NAME)
    except ModuleNotFoundError as absent:
        pytest.fail(
            f"{_PAGE_MODULE_NAME} does not exist ({absent}), so neither launch "
            "surface is served — the absent-target state, which establishes "
            "nothing about the assertions in this test"
        )


# ---------------------------------------------------------------------------
# The delta's literal markers
# ---------------------------------------------------------------------------

#: SPECIFIED. "the outcome's tag carries the marker `outcome-tag`".
OUTCOME_TAG: Final = "outcome-tag"

#: SPECIFIED. "the element holding the step carries `state-` followed by
#: the outcome's own name lowercased".
STATE_PREFIX: Final = "state-"

#: SPECIFIED. "a step carrying no recorded outcome carrying
#: `state-unrecorded`".
UNRECORDED_MARKER: Final = "state-unrecorded"


def _state_marker(outcome: type) -> str:
    """The marker an outcome's own name yields, computed from the domain
    class rather than restated — `Satisfied` gives `state-satisfied`."""
    return f"{STATE_PREFIX}{outcome.__name__.lower()}"


# ---------------------------------------------------------------------------
# Fixed vocabulary and DERIVED fixture values
# ---------------------------------------------------------------------------

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")
PRINCIPAL: Final = "U01ALICE"
RECORDER: Final = "Nadia Recorder"
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

RENDER_DATE: Final = date(2027, 4, 1)
#: A launch date whose -30-day anchored steps are already overdue as of
#: RENDER_DATE, which is what puts the launch's date at risk.
AT_RISK_DATE: Final = date(2027, 4, 15)
HEALTHY_DATE: Final = date(2027, 12, 1)

RECORDED_AT: Final = datetime(2027, 3, 2, 11, 47, tzinfo=UTC)

HOLD_STEP: Final = "hold.commit"
TITLE_STEP: Final = "listing.title-conforms"
IMAGES_STEP: Final = "listing.images-uploaded"
UNITS_STEP: Final = "inventory.units-received"
BRIEF_STEP: Final = "strategy.brief-signed-off"
EVIDENCE_STEP: Final = "listing.keyword-coverage-checked"
PROHIBITED_STEP: Final = "listing.no-incentivised-reviews"
NOT_STARTED_STEP: Final = "listing.recorded-not-started"
UNTOUCHED_STEP: Final = "listing.nobody-has-touched-this"

STEP_NAMES: Final[dict[str, str]] = {
    HOLD_STEP: "Blocking work holding the commit gate",
    TITLE_STEP: "Title conforms to marketplace policy",
    IMAGES_STEP: "Hero and gallery images are uploaded",
    UNITS_STEP: "Units are received into the warehouse",
    BRIEF_STEP: "The launch brief is signed off",
    EVIDENCE_STEP: "Keyword coverage is checked by the automation",
    PROHIBITED_STEP: "No incentivised reviews are solicited",
    NOT_STARTED_STEP: "Work recorded as not started",
    UNTOUCHED_STEP: "Work nobody has touched",
}

#: A several-sentence evidence, of the shape an automated handler writes.
#: The comparison it serves is made against the *parsed* text of the
#: response, with character references converted, so a page escaping the
#: apostrophe -- which this one does -- is compared on what a reader
#: sees rather than on how the escape was spelled.
LONG_EVIDENCE: Final = (
    "The automated pass read every keyword group the listing was briefed "
    "against and found four of the five covered by the current copy. The "
    "fifth group, the one naming the competitor's own brand term, was left "
    "out deliberately because marketplace policy forbids it and the handler "
    "is configured to refuse rather than to warn. The remaining coverage was "
    "measured at ninety one percent, which clears the threshold the brief "
    "set, so the step is recorded as satisfied with this note attached."
)

#: INVENTED wording. The delta fixes that the outcomes render as words
#: rather than as the vocabulary's tokens, never which words.
_WORDING: Final[dict[str, tuple[str, ...]]] = {
    "Satisfied": ("satisfied", "done", "complete", "met"),
    "InProgress": ("in progress", "under way", "underway", "being worked"),
    "Blocked": ("blocked", "held", "waiting on"),
    "Refused": ("refused", "declined", "rejected"),
    "NotApplicable": ("not applicable", "n/a", "does not apply", "inapplicable"),
    "NotStarted": ("not started", "not yet started", "untouched", "unstarted"),
}

#: INVENTED wording for the two states the third and fifth scenarios turn
#: on, and for the launch marks the mark-wording scenario reads.
_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "unrecorded": (
        "nothing recorded",
        "unrecorded",
        "no outcome",
        "not recorded",
        "no record",
    ),
    "awaiting": (
        "awaiting confirmation",
        "awaits confirmation",
        "needs confirmation",
        "confirmation",
    ),
    "at_risk": ("at risk", "at-risk"),
    #: The things those two marks are facts *about*, which is what the
    #: scenario requires each mark to name.
    "the_gate": ("gate",),
    "the_date": ("date",),
}


#: INVENTED. A time rendered to the minute carries an `H:MM` token.
_TIME_TOKEN: Final = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

#: INVENTED. A zone designator, in any of the forms a rendered time
#: plausibly carries one: `UTC`/`GMT`, a bare `Z`, a numeric offset, an
#: abbreviation ending in `T` (`EET`, `CEST`, `PST`), or an IANA name.
#: Correction point for a page naming the zone some other way.
_ZONE: Final = re.compile(
    r"\bUTC\b|\bGMT\b|\bZ\b|[+-]\d{2}:?\d{2}\b|\b[A-Z]{2,4}T\b"
    r"|\b[A-Za-z]{3,}/[A-Za-z_]{3,}\b"
)


class _Postponed:
    """An outcome the vocabulary does not hold.

    `StepOutcome` is closed at six members, so the page can only meet
    this through a fixture — which is the point: the scenario is stated
    as an obligation on the page's mapping, "exercised at the mapping,
    not through a launch".
    """


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
    """Steps at three gates, so a gate group is distinguishable from the
    gate sequence, and every outcome in the vocabulary has a step whose
    hazard permits it."""
    return _build_playbook(
        *(
            _step(
                HOLD_STEP,
                gate="commit",
                blocking=True,
                kind=StepKind.AUTOMATED,
                handler="fixture.holding_check",
                timing_anchor=OffsetAnchor(days=365),
            ),
            _step(TITLE_STEP, gate="listable"),
            _step(IMAGES_STEP, gate="listable"),
            _step(UNITS_STEP, gate="listable", discipline=INVENTORY, blocking=True),
            _step(BRIEF_STEP, gate="listable"),
            _step(
                EVIDENCE_STEP,
                gate="listable",
                kind=StepKind.AUTOMATED,
                handler="fixture.keyword_coverage",
            ),
            _step(PROHIBITED_STEP, gate="ignition", hazard=Hazard.PROHIBITED_TACTIC),
            _step(NOT_STARTED_STEP, gate="ignition"),
            _step(UNTOUCHED_STEP, gate="ignition"),
        ),
        version="outcome-tags-v1",
        fill_unheld=False,
    )


PLAYBOOK: Final = _playbook()

SERVED_ORDER: Final = tuple(
    step.identifier
    for gate in SPECIFIED_GATE_ORDER
    for step in PLAYBOOK.steps_for_gate(gate)
)

#: SPECIFIED by scenario 1, applied to every member of the vocabulary the
#: fixture can record: the step, and the outcome recorded on it.
RECORDED: Final[tuple[tuple[str, Any, type], ...]] = (
    (TITLE_STEP, Satisfied, Satisfied),
    (IMAGES_STEP, InProgress, InProgress),
    (UNITS_STEP, Blocked(reason="the freight forwarder has it"), Blocked),
    (
        BRIEF_STEP,
        NotApplicable(reason="this marketplace asks for no brief"),
        NotApplicable,
    ),
    (PROHIBITED_STEP, Refused, Refused),
    (NOT_STARTED_STEP, NotStarted, NotStarted),
)


def _provenance(
    when: datetime = RECORDED_AT, evidence: str | None = None
) -> Provenance:
    return Provenance(
        source="clickup",
        who=RECORDER,
        when=when,
        evidence=evidence or "screenshot in the launch Slack thread",
    )


def _start(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=PLAYBOOK, launch_date=launch_date
    )
    return launch


def _record(
    launch: Launch, step_id: str, outcome: Any, *, evidence: str | None = None
) -> None:
    launch.record_step_outcome(
        PLAYBOOK,
        step_id=step_id,
        outcome=outcome,
        provenance=_provenance(evidence=evidence),
    )


def _spread(product_id: ProductId, launch_date: date | None = HEALTHY_DATE) -> Launch:
    """A launch carrying one recording of each outcome the vocabulary
    holds, one step recorded with a several-sentence evidence, and one
    step left with nothing recorded at all."""
    launch = _start(product_id, launch_date)
    for step_id, outcome, _kind in RECORDED:
        _record(launch, step_id, outcome)
    _record(launch, EVIDENCE_STEP, Satisfied, evidence=LONG_EVIDENCE)
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
    "read_journal": ("read_journal", "journal", "journal_entries"),
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

    # Stubbed empty, so the surface stays hermetic. `read_journal` was
    # `None` when this file was written and reached nothing; it is wired
    # to a real store now, so a detail page rendered without this reaches
    # for a database.
    async def _no_journal(*_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        return ()

    _install(monkeypatch, module, "read_journal", _no_journal)
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


def _detail_html(surface: _Surface, product_id: ProductId) -> str:
    template = _detail_template(surface.module)
    opened = template.index("{")
    closed = template.index("}", opened)
    path = template[:opened] + product_id.value + template[closed + 1 :]
    response = surface.client.get(path)
    assert response.status_code == 200, (
        f"the detail page for {product_id.value} was not served: "
        f"{response.status_code} {response.text[:400]}"
    )
    return str(response.text)


def _list_html(surface: _Surface) -> str:
    response = surface.client.get(_list_path(surface.module))
    assert response.status_code == 200, (
        f"the list was not served: {response.status_code} {response.text[:400]}"
    )
    return str(response.text)


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


def _raw_text(node: _Node) -> str:
    """The element's rendered text, case preserved — which is what the
    "words, not the token" scenario has to be read against."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.append(_raw_text(child))
    return " ".join(part for part in found if part)


def _all_text(node: _Node) -> str:
    return _raw_text(node).lower()


def _haystack(node: _Node) -> str:
    return f"{_all_text(node)} {_attribute_text(node)}"


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _haystack(node)


def _carries(node: _Node, marker: str) -> bool:
    """INVENTED: a marker is read as a class token, the reading
    `test_playbook_admin_presentation_vocabulary.py` established for this
    same vocabulary."""
    return marker in _classes(node)


def _says(node: _Node, key: str) -> bool:
    return any(word in _haystack(node) for word in _WORDS[key])


def _within(node: _Node) -> list[_Node]:
    return [node, *_elements(node)]


# ---------------------------------------------------------------------------
# The detail page's step rows
# ---------------------------------------------------------------------------


def _step_row(html: str, step_id: str) -> _Node:
    """The smallest element holding that step's identifier **and** its
    name, and no other served step — the locator
    `test_launch_admin_detail.py` established."""
    root = _tree(html)
    others = [other for other in SERVED_ORDER if other != step_id]
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
            f"without also holding another served step, so the step's own "
            f"facts cannot be read off one row — correct `_step_row` "
            f"(page text: {_flat(_all_text(root))[:400]!r})"
        )
    return min(mine, key=_size)


def _state_element(html: str, step_id: str) -> _Node | None:
    """The element holding the step that carries a `state-` marker.

    INVENTED reading of "the element holding the step": the step's own
    row, or the nearest ancestor of it that still holds no *other*
    served step. An ancestor holding two steps could not carry one
    step's state, so the walk stops there.
    """
    others = [other for other in SERVED_ORDER if other != step_id]
    for candidate in (row := _step_row(html, step_id), *_ancestors(row)):
        if any(_holds(candidate, other) for other in others):
            return None
        if any(name.startswith(STATE_PREFIX) for name in _classes(candidate)):
            return candidate
    return None


def _state_markers(html: str, step_id: str) -> set[str]:
    element = _state_element(html, step_id)
    if element is None:
        return set()
    return {name for name in _classes(element) if name.startswith(STATE_PREFIX)}


def _outcome_tag(html: str, step_id: str) -> _Node:
    row = _step_row(html, step_id)
    tags = [element for element in _within(row) if _carries(element, OUTCOME_TAG)]
    if not tags:
        pytest.fail(
            f"the step row for {step_id!r} carries no element marked "
            f"{OUTCOME_TAG!r}, so its outcome is not rendered as a tag: the "
            f"row carries {sorted({c for e in _within(row) for c in _classes(e)})}"
        )
    assert len(tags) == 1, (
        f"the step row for {step_id!r} carries {len(tags)} elements marked "
        f"{OUTCOME_TAG!r}; a step has one outcome and so one tag"
    )
    return tags[0]


# ---------------------------------------------------------------------------
# The list's rows and marks
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


def _row_for(surface: _Surface, html: str, product_id: ProductId) -> _Row:
    for row in _rows(html, surface.module):
        if row.product_id == product_id.value:
            return row
    pytest.fail(
        f"no row for {product_id.value} was rendered; the page rendered "
        f"{[row.product_id for row in _rows(html, surface.module)]}"
    )


def _mark_stating(row: _Row, key: str) -> _Node:
    """The smallest element within the row whose own text states that
    fact — the mark itself, rather than the row that holds it."""
    stating = [element for element in _within(row.node) if _says(element, key)]
    if not stating:
        pytest.fail(
            f"the row states nothing matching {list(_WORDS[key])} at all, so "
            f"its {key!r} mark is not rendered: {_flat(_raw_text(row.node))!r} "
            f"— correct `_WORDS[{key!r}]` if the page words it differently"
        )
    return min(stating, key=_size)


# ---------------------------------------------------------------------------
# Times and zones
# ---------------------------------------------------------------------------


def _time_and_zone(region: _Node) -> tuple[_Node, bool] | None:
    """The smallest element within `region` rendering a time to the
    minute, and whether that element or its parent names a zone.

    INVENTED reading of "carries the zone it is read in": a page
    rendering the zone as a sibling of the time still carries it, so the
    parent counts; a page rendering it in a different region of the page
    does not. Correction point for a page that pairs them some other
    way.
    """
    bearing = [
        element for element in _within(region) if _TIME_TOKEN.search(_raw_text(element))
    ]
    if not bearing:
        return None
    smallest = min(bearing, key=_size)
    scopes = [smallest] + ([smallest.parent] if smallest.parent is not None else [])
    return smallest, any(_ZONE.search(_raw_text(scope)) for scope in scopes)


# ===========================================================================
# Requirement: A step's outcome is rendered as a tag carrying its state
# ===========================================================================


def test_an_outcome_renders_as_a_tag_carrying_its_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An outcome renders as a tag carrying its state.

    WHEN a launch's detail page renders a step with a recorded outcome
    THEN the outcome is rendered within an element carrying `outcome-tag`
    AND the element holding that step carries `state-` followed by the
    outcome's own name lowercased.

    Read over every member of the vocabulary the fixture can record, not
    over one: the marker is derived from the outcome's own name, so a
    page carrying it for the two states it was looked at with and a
    fixed marker for the rest would satisfy a single-outcome test.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_spread(product.id)),
        catalog=_Catalog(product),
    )

    html = _detail_html(surface, product.id)

    for step_id, _outcome, kind in RECORDED:
        tag = _outcome_tag(html, step_id)
        # SPECIFIED: the outcome is rendered within that element.
        assert _raw_text(tag).strip(), (
            f"the tag on {step_id!r} is empty, so the outcome is marked but "
            "not rendered"
        )
        assert any(word in _all_text(tag) for word in _WORDING[kind.__name__]), (
            f"the tag on {step_id!r} reads {_flat(_raw_text(tag))!r}, which "
            f"names none of {list(_WORDING[kind.__name__])} — correct "
            f"`_WORDING[{kind.__name__!r}]` if the page words it differently"
        )
        # SPECIFIED: the element holding the step carries the state
        # marker its own name yields.
        assert _state_marker(kind) in _state_markers(html, step_id), (
            f"the element holding {step_id!r} carries "
            f"{sorted(_state_markers(html, step_id))} rather than "
            f"{_state_marker(kind)!r}, so the step's state is not readable by "
            "treatment before it is read by word"
        )


def test_unrecorded_stays_distinguishable_from_not_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Unrecorded stays distinguishable from not started.

    WHEN a detail page renders a step recorded as not started and a step
    with nothing recorded
    THEN the two render different words
    AND the first carries `state-notstarted` while the second carries
    `state-unrecorded`.

    "A single grey shared by both would satisfy neither" — so the two
    markers are asserted to differ as well as to be the two the delta
    names, and the words are compared against each other rather than
    against a wording list.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_spread(product.id)),
        catalog=_Catalog(product),
    )

    html = _detail_html(surface, product.id)
    recorded = _outcome_tag(html, NOT_STARTED_STEP)
    nothing = _outcome_tag(html, UNTOUCHED_STEP)

    # SPECIFIED: the two render different words.
    assert _flat(_raw_text(recorded)).strip() and _flat(_raw_text(nothing)).strip(), (
        "one of the two steps renders no outcome words at all: "
        f"{_flat(_raw_text(recorded))!r} / {_flat(_raw_text(nothing))!r}"
    )
    assert _flat(_all_text(recorded)) != _flat(_all_text(nothing)), (
        "a step recorded as not started and a step with nothing recorded "
        f"render the same words ({_flat(_raw_text(recorded))!r}), so the two "
        "are no longer distinguishable"
    )
    # SPECIFIED: and carry the two markers the delta names, never one
    # shared marker.
    assert _state_marker(NotStarted) in _state_markers(html, NOT_STARTED_STEP), (
        f"the step recorded as not started carries "
        f"{sorted(_state_markers(html, NOT_STARTED_STEP))} rather than "
        f"{_state_marker(NotStarted)!r}"
    )
    assert UNRECORDED_MARKER in _state_markers(html, UNTOUCHED_STEP), (
        f"the step with nothing recorded carries "
        f"{sorted(_state_markers(html, UNTOUCHED_STEP))} rather than "
        f"{UNRECORDED_MARKER!r}"
    )
    assert _state_markers(html, NOT_STARTED_STEP) != _state_markers(
        html, UNTOUCHED_STEP
    ), (
        "both steps carry the same state markers, which is the one shared marker the delta forbids"
    )


def test_a_mark_names_what_it_is_about(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A mark names what it is about.

    WHEN the list renders a launch whose gate awaits confirmation and
    whose date is at risk
    THEN each mark names the thing it is a fact about, rather than
    naming the state alone.

    "Awaiting confirmation" is a fact about the launch's current
    **gate**; the other is a fact about the launch **date**. Read bare
    beside a step recorded `Blocked`, the first was reported as a
    contradiction — so the assertion is that the mark's own text names
    whose fact it is.
    """
    product = _launching("PX-100", "Alpha widget")
    launch = _start(product.id, AT_RISK_DATE)
    _record(launch, HOLD_STEP, Satisfied)
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(launch), catalog=_Catalog(product)
    )

    row = _row_for(surface, _list_html(surface), product.id)

    awaiting = _mark_stating(row, "awaiting")
    at_risk = _mark_stating(row, "at_risk")
    # SPECIFIED: the awaiting mark names the gate it is a fact about.
    assert _says(awaiting, "the_gate"), (
        f"the mark reads {_flat(_raw_text(awaiting))!r} and names no gate, so "
        "it states the state alone — which beside a step recorded as blocked "
        "reads as a contradiction"
    )
    # SPECIFIED: and the launch date's own mark names the date.
    assert _says(at_risk, "the_date"), (
        f"the mark reads {_flat(_raw_text(at_risk))!r} and names no date, so "
        "it states the state alone"
    )


def test_a_recording_time_keeps_its_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A recording time keeps its zone.

    WHEN either page renders the time an outcome was recorded
    THEN that time is rendered no coarser than the minute and carries
    the zone it is read in.

    Both pages, because the scenario says "either page": the detail
    page's provenance and the list's last-completed column are the two
    places a recording time is rendered. "Dropping the zone changes
    which day an instant near a boundary belongs to, which is a fact and
    not a precision."
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_spread(product.id)),
        catalog=_Catalog(product),
    )

    regions = {
        "the detail page's step row": _step_row(
            _detail_html(surface, product.id), TITLE_STEP
        ),
        "the list's row": _row_for(surface, _list_html(surface), product.id).node,
    }

    for where, region in regions.items():
        found = _time_and_zone(region)
        # SPECIFIED: rendered no coarser than the minute.
        assert found is not None, (
            f"{where} renders no time to the minute at all, so the recording "
            f"time is coarser than the minute: {_flat(_raw_text(region))!r} — "
            "correct `_TIME_TOKEN` if the page renders one some other way"
        )
        element, zoned = found
        # SPECIFIED: and carries the zone it is read in.
        assert zoned, (
            f"{where} renders the time {_flat(_raw_text(element))!r} with no "
            "zone on it or beside it, so an instant near a day boundary reads "
            "as the wrong day — correct `_ZONE` if the page names the zone "
            "some other way"
        )


def test_an_outcome_renders_as_words_not_as_its_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An outcome renders as words, not as its token.

    WHEN a detail page renders a step whose outcome is `NotStarted`
    THEN the rendered outcome reads as words rather than as the
    vocabulary's token.

    The token is a class name and reads as code. The assertion is over
    the page's **text**, case preserved, so the `state-notstarted`
    marker — which is an attribute and is required to be there — cannot
    satisfy or defeat it.
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_spread(product.id)),
        catalog=_Catalog(product),
    )

    html = _detail_html(surface, product.id)
    row = _step_row(html, NOT_STARTED_STEP)
    tag = _outcome_tag(html, NOT_STARTED_STEP)

    # SPECIFIED: the vocabulary's token is not what the page renders.
    assert NotStarted.__name__ not in _raw_text(row), (
        f"the step row renders the vocabulary's token "
        f"{NotStarted.__name__!r} verbatim: {_flat(_raw_text(row))!r}"
    )
    # SPECIFIED: it reads as words.
    assert any(word in _all_text(tag) for word in _WORDING[NotStarted.__name__]), (
        f"the outcome reads {_flat(_raw_text(tag))!r}, which is none of "
        f"{list(_WORDING[NotStarted.__name__])} — correct `_WORDING` if the "
        "page words it differently"
    )


def test_an_unknown_outcome_still_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An unknown outcome still renders.

    WHEN the page is asked to render an outcome for which it holds no
    wording
    THEN the outcome is rendered under its own name rather than omitted.

    The vocabulary is closed at six, so the outcome is put on the
    aggregate by this fixture rather than reached through the domain —
    see the file docstring. "A blank where an outcome belongs is the
    failure this surface exists to prevent", so the tag being empty
    fails as loudly as the page dropping the step.
    """
    product = _launching("PX-100", "Alpha widget")
    launch = _start(product.id)
    _record(launch, TITLE_STEP, _Postponed)
    surface = _surface(
        monkeypatch, launches=_FakeLaunchStore(launch), catalog=_Catalog(product)
    )

    html = _detail_html(surface, product.id)
    tag = _outcome_tag(html, TITLE_STEP)

    # SPECIFIED: rendered under its own name, rather than omitted.
    assert _Postponed.__name__ in _raw_text(tag), (
        f"an outcome the page holds no wording for renders as "
        f"{_flat(_raw_text(tag))!r} rather than under its own name "
        f"{_Postponed.__name__!r} — a blank where an outcome belongs is the "
        "failure this surface exists to prevent"
    )
    # SPECIFIED, by the same requirement's first scenario: the state
    # marker is derived from the outcome's own name, and the rule it
    # states carries no exception for a member the page does not know.
    assert _state_marker(_Postponed) in _state_markers(html, TITLE_STEP), (
        f"the element holding the step carries "
        f"{sorted(_state_markers(html, TITLE_STEP))} rather than "
        f"{_state_marker(_Postponed)!r}"
    )


def test_long_evidence_is_bounded_not_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Long evidence is bounded, not truncated.

    WHEN a detail page renders a step whose evidence runs to several
    sentences
    THEN the whole of that evidence is present in the response.

    Only that half is testable. That the evidence is laid out *within a
    bounded measure* is a rendered width, which no response carries, and
    the requirement sends it to direct inspection (`tasks.md` 6.4). The
    half asserted here is the one the requirement is emphatic about: "an
    ellipsis on the one field explaining why a step was refused
    suppresses exactly the fact a reader came for".
    """
    product = _launching("PX-100", "Alpha widget")
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_spread(product.id)),
        catalog=_Catalog(product),
    )

    html = _detail_html(surface, product.id)
    row = _step_row(html, EVIDENCE_STEP)

    # SPECIFIED: the whole of the evidence is present.
    assert _flat(LONG_EVIDENCE) in _flat(_raw_text(row)), (
        "the step's evidence is not present in full on its row; the row reads "
        f"{_flat(_raw_text(row))!r}"
    )
    # SPECIFIED: and is not truncated — an ellipsis standing where the
    # rest of it should be is the failure the requirement names.
    assert "…" not in _raw_text(row) and "..." not in _raw_text(row), (
        "the step's row renders an ellipsis, so the evidence is cut short "
        f"somewhere: {_flat(_raw_text(row))!r}"
    )
