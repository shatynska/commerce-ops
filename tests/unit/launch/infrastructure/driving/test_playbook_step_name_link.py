"""A step's name in the playbook steps table opens its edit page
(`playbook-admin`).

Derived from `openspec/specs/playbook-admin/spec.md`'s requirement *A
step's name in the table opens its edit page*, as it stands after
`move-step-actions-into-step-pages`:

- *A step's name opens its edit page*

The requirement was ADDED, additively, by `add-admin-breadcrumb-
navigation` — offered **alongside** the row's then-existing `edit`
action. `move-step-actions-into-step-pages` removed that action (and
every other row-level action but reordering) and modified this
requirement in step: the name is now the row's **only** way into a
step. This file's one test was rewritten to match — it no longer
asserts a second, separate `edit` link exists.

## Level

The playbook router alone, over a step-store double — the harness
`test_playbook_admin_page.py` established, reproduced here (this project
shares no test-helper module between test files).

## Expected first-run state

Confirmed by hand against the page as it renders today: a step's name
renders as plain text (`<td>Blocking work of hold.commit</td>`), not
wrapped in a link, while the row's own `edit` action already exists as
`<a href=".../edit" role="button" class="row-action">edit</a>`. So this
test is expected to fail on the *name-link* half only — the row's
existing `edit` action already passes today, which is exactly what
"alongside, not instead of" requires the test to still find.

Baseline recorded before this test was written: `uv run pytest
tests/unit tests/agents` at this worktree — 1472 passed, 0 failed, on
2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the delta: that an active step's name offers that step's edit
page in one action, and that the row's own `edit` action is still
present and unchanged.

INVENTED, each with its correction point named in the code:

- The row's own container: the element carrying `id="step-<identifier>"`
  — the addressing `id` `test_playbook_admin_create_page.py` already
  established for a step's row (`_ADDRESS_ID`, from `design.md`).
  Correction point: `_row`.
- That "opens that step's edit page in one action" is read as a plain
  anchor, within the row, whose href mentions both "edit" and the step's
  identifier, and whose own visible text is exactly the step's name
  (distinguishing it from the row's `edit`-labelled action, whose own
  text is exactly "edit"). Correction point: `_edit_links`,
  `_name_link`, `_edit_action`.
- Every module seam, the step-store double and the membership double — taken
  unchanged from `test_playbook_admin_page.py`.

Correcting a locator is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what the test
asserts: that the name offers the edit page, and that the pre-existing
`edit` action is untouched and still there beside it.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as page_module,
)
from commerce_ops.shared.domain.discipline import Discipline

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

A_DISCIPLINE: Final = next(iter(Discipline))
ASSIGNEE: Final = "prs_01HQ8Z6M4A"
ASSIGNEE_NAME: Final = "Alice Admin"

STEP_ID: Final = "listing.title-conforms"
STEP_NAME: Final = "Title conforms to marketplace policy"

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


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": STEP_NAME,
        "description": None,
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "assignees": (ASSIGNEE,),
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _Record:
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
    def __init__(self, records: tuple[_Record, ...], version: int = 41) -> None:
        self.records = records
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        self.records = tuple(records)
        self.version += 1


def _seeded_store() -> _FakeStepStore:
    return _FakeStepStore((_Record(_step(), display_order=10),))


class _FakeMember:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeMembers:
    async def list_members(self) -> tuple[_FakeMember, ...]:
        return (_FakeMember(ASSIGNEE, ASSIGNEE_NAME),)


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "members", _FakeMembers())
    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _page_path() -> str:
    candidates: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, "the page router exposes no parameterless GET route"
    return min(candidates, key=len)


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return response.text


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
    return " ".join(part for part in found if part)


def _row(html: str, identifier: str) -> _Node:
    """The step's own row — the element carrying `id="step-<identifier>"`,
    the addressing `id` `test_playbook_admin_create_page.py` already
    established for a step's row."""
    marker = f"step-{identifier}"
    for element in _elements(_tree(html)):
        if element.attrs.get("id") == marker:
            return element
    pytest.fail(
        f"no element on the page carries id={marker!r} — correct `_row` if "
        "the row is addressed some other way"
    )


def _edit_links(row: _Node, identifier: str) -> list[_Node]:
    """Every plain anchor within the row whose href targets that step's
    edit page — mentioning both "edit" and the step's identifier."""
    return [
        element
        for element in _elements(row)
        if element.tag == "a"
        and "edit" in element.attrs.get("href", "").lower()
        and identifier in element.attrs.get("href", "")
    ]


# ===========================================================================
# ADDED requirement: A step's name in the table opens its edit page
# ===========================================================================


def test_a_steps_name_opens_its_edit_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A step's name opens its edit page.

    WHEN any step's row is rendered
    THEN its name offers that step's edit page in one action.

    The row's own separate `edit` action — asserted here alongside the
    name link when this requirement was first added — no longer exists:
    `move-step-actions-into-step-pages` removed it, and the requirement
    was modified in step, dropping the "alongside, not instead of"
    caveat this test's docstring originally quoted. The name link is now
    the row's only way in.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)
    row = _row(html, STEP_ID)
    edit_links = _edit_links(row, STEP_ID)
    assert edit_links, (
        f"the row for {STEP_ID!r} carries no link to its edit page at all — "
        f"row text: {_flat(_all_text(row))!r}"
    )

    # SPECIFIED: the step's *name* offers the edit page — a link whose own
    # text is exactly the step's name.
    name_links = [link for link in edit_links if _all_text(link).strip() == STEP_NAME]
    assert name_links, (
        f"nothing in the row for {STEP_ID!r} wraps the step's name "
        f"({STEP_NAME!r}) in a link to its edit page — the edit-targeting "
        f"links present read {[_all_text(link) for link in edit_links]!r}"
    )

    # DERIVED guard: the name link's target really serves the step's edit
    # page.
    served = client.get(name_links[0].attrs["href"])
    assert served.status_code == 200, (
        f"following the name link to {name_links[0].attrs['href']!r} does "
        f"not serve a page: {served.status_code} {served.text[:300]}"
    )
    assert STEP_NAME in served.text, (
        "the page reached by the name link does not render the step's own "
        "name, so it does not plausibly serve that step's edit page"
    )
