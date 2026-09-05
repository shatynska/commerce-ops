"""A metric step reads as a step on the journal page.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-admin/spec.md`

Covers, from the ADDED requirement *A launch's journal page renders every
entry as a row, newest first*, the scenario this change writes:

- *A metric step reads as a step*,

together with the paragraph it replaces the old exception with: "Every
journal kind now names either a gate or a step as its subject, so the
gate/step column is empty only where an occurrence names no subject at
all. A metric obligation reaches this page as an ordinary step, its
threshold being the step's own description, and needs no exception to the
columns' meaning."

The requirement's twelve other scenarios carry the same words as the
REMOVED requirement it replaces and stay covered by
`tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py`.
Nothing here edits that file; its
`test_metric_atteseds_condition_is_not_a_gate_or_step` — whose whole
subject is the exception this delta deletes — is recorded in
`test-manifest.md` as an obsolete-test candidate (`tasks.md` 5.6).

## Level

The launch router mounted alone over fakes for the launch/playbook/
catalog/members ports and the `read_journal` seam — the composition
`test_launch_admin_journal_table.py` records, pared to what a journal-only
page needs. The scenario is about what a rendered row's columns carry, so
the route is the smallest unit that observes it.

## What is fixed, and what is INVENTED

Fixed by the artifacts: that the page renders the journal as a table with
a gate/step column and a detail column, that the gate/step column carries
the entry's subject where that subject names a gate or a step, and that
the detail phrase does not restate a subject that has its own column.

INVENTED, reused verbatim from `test_launch_admin_journal_table.py` and
recorded there: the page module and its seams (`_SEAMS`), the fake
composed entry's field set (`_entry`), the row locator (`_journal_row`),
and the marker reading. Reproduced here because this project keeps its
test files self-contained.

**The composed entry deliberately carries no `gate_id`.** `tasks.md` 5.5
deletes that field with the only kind that populated it, so a page still
reading `entry.gate_id` raises `AttributeError` against this fixture —
which is the point: the fixture models the entry shape as it will be, not
as it is.

## Expected first-run state

The page still composes a `metric-attested` branch that reads
`entry.gate_id` (`tasks.md` 5.6), so this test is expected to **fail on a
wrong value or an AttributeError** rather than on an absent target: the
page exists and renders. Per `ai-toolkit:testing` an `AttributeError`
raised from the page under test is the code being wrong for this
fixture, not the test being broken — the fixture is the specified shape.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fakes import FakeCatalogPort as _Catalog
from tests.support.fakes import FakeMembersStore as _FakeMembersStore
from tests.support.fakes import FakePlaybooks, StubDate
from tests.support.fixtures import MARKETPLACE
from tests.support.html import Node as _Node
from tests.support.html import all_text as _all_text
from tests.support.html import elements as _elements
from tests.support.html import tree as _tree
from tests.support.playbook import gates as _gates

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


PRINCIPAL: Final = "U01ALICE"
RENDER_DATE: Final = date(2027, 4, 1)
LAUNCH_DATE: Final = date(2027, 4, 15)
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

#: The metric step's own name — what the served playbook gave it, and so
#: what `launch-journal` requires the entry to be labelled with. Marked
#: uniquely so the row locator cannot land elsewhere.
METRIC_STEP_NAME: Final = (
    "INVENTORY GATE: 60-80+ units fulfillable, uniquely-marked-metric-step"
)


PLAYBOOK: Final = LaunchPlaybook(version="journal-metric-v1", gates=_gates(), steps=())


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


class _FakePlaybooks(FakePlaybooks):
    """The shared store, adapted: this file's call sites pass nothing."""

    def __init__(self) -> None:
        super().__init__(PLAYBOOK)


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
# Installing the page's seams (INVENTED, reused verbatim)
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
    journal_entries: tuple[Any, ...],
) -> _Surface:
    module = _page_module()
    _install(monkeypatch, module, "verify", _fake_verify)
    _install(monkeypatch, module, "launches", launches)
    _install(monkeypatch, module, "playbooks", _FakePlaybooks())
    _install(monkeypatch, module, "members", _members_store())
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


def _journal_template(module: ModuleType) -> str:
    candidates = [
        str(route.path)
        for route in module.router.routes
        if getattr(route, "path", None)
        and "GET" in (getattr(route, "methods", None) or set())
        and "{" in route.path
        and "journal" in route.path.lower()
    ]
    assert len(candidates) == 1
    return str(candidates[0])


def _journal_path(module: ModuleType, product_id: ProductId) -> str:
    template = _journal_template(module)
    opened = template.index("{")
    closed = template.index("}", opened)
    return template[:opened] + product_id.value + template[closed + 1 :]


def _journal_html(surface: _Surface, product_id: ProductId) -> str:
    response = surface.client.get(_journal_path(surface.module, product_id))
    assert response.status_code == 200, (
        f"the journal page for {product_id} was not served: "
        f"{response.status_code} {response.text[:400]}"
    )
    return str(response.text)


# ---------------------------------------------------------------------------
# An HTML tree (INVENTED, reused verbatim)
# ---------------------------------------------------------------------------


def _holds(node: _Node, needle: str) -> bool:
    return needle.lower() in _all_text(node)


def _journal_row(html: str, mark: str) -> _Node:
    root = _tree(html)
    candidates = [element for element in _elements(root) if _holds(element, mark)]
    if not candidates:
        pytest.fail(
            f"no element on the journal page holds {mark!r} — the entry does "
            "not appear to be rendered at all"
        )
    holder = min(candidates, key=lambda element: 1 + sum(1 for _ in _elements(element)))
    walker: _Node | None = holder
    while walker is not None and walker.tag not in ("tr", "#document"):
        walker = walker.parent
    if walker is None or walker.tag != "tr":
        pytest.fail(
            f"the element holding {mark!r} has no `<tr>` ancestor — correct "
            "`_journal_row` if the page expresses a row another way"
        )
    return walker


# ---------------------------------------------------------------------------
# A fake composed journal entry — the shape a real `JournalEntry` carries
# **after this change**: `gate_id` is gone with its only populator
# (`tasks.md` 5.5).
# ---------------------------------------------------------------------------


def _entry(
    *,
    kind: str,
    when: datetime,
    label: str,
    category: str,
    subject: str | None = None,
    source: str | None = None,
    actor: str | None = None,
    playbook_version: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    evidence: str | None = None,
    decision: str | None = None,
    posture: str | None = None,
    standing_at: str | None = None,
    previous_date: str | None = None,
    new_date: str | None = None,
    unsatisfied: tuple[str, ...] = (),
) -> Any:
    return type(
        "_Entry",
        (),
        {
            "kind": kind,
            "when": when,
            "label": label,
            "category": category,
            "subject": subject,
            "source": source,
            "actor": actor,
            "playbook_version": playbook_version,
            "outcome": outcome,
            "reason": reason,
            "evidence": evidence,
            "decision": decision,
            "posture": posture,
            "standing_at": standing_at,
            "previous_date": previous_date,
            "new_date": new_date,
            "unsatisfied": unsatisfied,
        },
    )()


# ===========================================================================
# Requirement (ADDED): A launch's journal page renders every entry as a
# row, newest first
# ===========================================================================


def test_a_metric_step_reads_as_a_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A metric step reads as a step.

    WHEN a launch's journal holds a `step-outcome-recorded` entry for a
    blocking step declaring a metric identifier
    THEN its row's gate/step column carries that step, exactly as for any
    other step, and its detail column carries the entry's own facts.

    "Exactly as for any other step" is what makes the assertion pair
    meaningful: the subject is in its own column *and* the detail phrase
    does not restate it, which is the rule the removed `metric-attested`
    exception broke. An entry carrying a metric obligation is no longer
    distinguishable, on this page, from any other step outcome — the page
    is not told the step names a metric at all.
    """
    product = _launching("PX-200", "Beta widget")
    entry = _entry(
        kind="step-outcome-recorded",
        when=datetime(2027, 3, 2, 10, 30, tzinfo=UTC),
        label="Outcome",
        category="progression",
        subject=METRIC_STEP_NAME,
        source="clickup",
        actor="an-actor-who-is-not-a-member",
        outcome="Satisfied",
        evidence="72 fulfillable units confirmed in Seller Central",
    )
    surface = _surface(
        monkeypatch,
        launches=_FakeLaunchStore(_start(product.id)),
        catalog=_Catalog(product),
        journal_entries=(entry,),
    )

    html = _journal_html(surface, product.id)
    row = _journal_row(html, METRIC_STEP_NAME)

    cells = [element for element in _elements(row) if element.tag in ("td", "th")]
    assert cells, "the journal row renders no cells"
    # SPECIFIED: the gate/step column carries that step — the step's name
    # occupies a cell of its own rather than being folded into another.
    subject_cells = [cell for cell in cells if _holds(cell, METRIC_STEP_NAME)]
    assert subject_cells, (
        f"no cell of the row carries the step: {[_all_text(c) for c in cells]!r}"
    )
    # SPECIFIED: the detail column carries the entry's own facts, and does
    # not restate the subject.
    detail_cells = [cell for cell in cells if "detail" in cell.attrs.get("class", "")]
    assert detail_cells, (
        "the journal row renders no detail column; correct this file's "
        "column reading to the implemented page"
    )
    for cell in detail_cells:
        assert METRIC_STEP_NAME.lower() not in _all_text(cell), (
            f"the detail column restates the subject: {_all_text(cell)!r}"
        )
    assert any("satisfied" in _all_text(cell) for cell in detail_cells), (
        "the detail column does not carry the entry's own facts: "
        f"{[_all_text(c) for c in detail_cells]!r}"
    )
