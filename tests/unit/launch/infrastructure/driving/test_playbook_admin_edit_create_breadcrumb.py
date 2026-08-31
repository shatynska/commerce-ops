"""The playbook edit and create surfaces' breadcrumb trail back to the
step table, narrowing preserved (`playbook-admin`,
`add-admin-breadcrumb-navigation`).

Derived strictly from the delta spec
`openspec/changes/add-admin-breadcrumb-navigation/specs/playbook-admin/spec.md`
— its second ADDED requirement, all three of its scenarios:

- ADDED *The edit and create surfaces carry a breadcrumb to the step
  table*
  - *The table is reachable from the edit surface, narrowing intact*
  - *The table is reachable from the create surface, narrowing intact*
  - *The edit surface's trail names the step*

The requirement's own prose draws out the asymmetry with the launch
detail page's own breadcrumb, which is deliberate and stated outright:
"The narrowing is carried here deliberately, unlike the launch detail
page's link back to the launch list ... This is the existing behavior of
each surface's own back link, carried forward under the breadcrumb
rather than changed by it." So unlike `test_launch_detail_breadcrumb.py`
and `test_product_dossier_breadcrumb.py`, which assert the offered link
carries **no** query, every assertion here is over the offered link
carrying the **same** narrowing the admin left the table under.

## Level

The playbook router alone, over a step-store double and a roster double
— the harness `test_playbook_admin_page.py` and
`test_playbook_admin_create_page.py` established, reproduced here (this
project shares no test-helper module between test files).

## Expected first-run state

Confirmed by hand against the page as it renders today: the edit
surface's own `Back to the table`/`Cancel` anchor already carries the
narrowing forward (`design.md`'s Context: "`edit.html`'s and `new.html`'s
back/cancel links already carry the admin's active narrowing forward"),
but neither surface renders a breadcrumb sitting *above* its title, and
the edit surface's title is the step's own name with no separate,
un-linked trail segment repeating it. So the narrowing-preservation half
of each scenario may already pass today (the existing control already
does what the breadcrumb is asked to do); what is expected to fail is
the *placement* — an offer rendered above the title, distinct from the
page's title itself — and the third scenario's un-linked "current
segment" naming the step, which does not exist as a separate element
today.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` at this worktree — 1472 passed, 0 failed, on
2026-08-28.

## What is fixed, and what is INVENTED

Fixed by the delta: that the edit surface and the create surface each
carry a breadcrumb trail immediately above their title, naming the step
table as a link and the surface itself as the current, un-linked,
segment; that following the table link carries forward whatever
narrowing was active when the admin left the table; and that the edit
surface's trail names the step being edited.

INVENTED, each with its correction point named in the code:

- How the edit surface is reached from a narrowed table: the first
  control the table offers whose URL mentions the target step's
  identifier and "edit" — the same reading `test_playbook_admin_page.py`
  already uses for a step's inline edit control (`_control`).
  Correction point: `_open_edit_surface`.
- How the create surface is reached: the same `_CREATE_HINTS` reading
  `test_playbook_admin_create_page.py` established — a live GET control
  whose URL mentions "new", "create" or "add". Correction point:
  `_open_create_surface`.
- The breadcrumb locator: an offer (a plain link, to the table's own
  path, carrying the same narrowing query) rendered above the surface's
  `<h1>` and not one of its ancestors, discriminated from the shared
  admin header by the same reading `test_launch_detail_breadcrumb.py`
  uses. Correction points: `_before_title`, `_in_shared_header`,
  `_links_to_path`.
- That "carries forward whatever narrowing was active" is read as: the
  offered link's own query, decoded, equals the narrowing that was
  active on the table before the surface was opened — and, as a DERIVED
  guard, that following it actually re-renders the table under that
  narrowing (present/absent steps, not only the query string).
  Correction point: `_same_narrowing`.
- Every module seam, the step-store double and the roster double — taken
  unchanged from `test_playbook_admin_page.py` and
  `test_playbook_admin_create_page.py`.

Correcting a locator is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: that the table is reachable from each surface, under the exact
narrowing that was active, above the surface's title; and that the edit
surface's trail names the step being edited.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

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

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}
_CREATE_HINTS: Final = ("new", "create", "add")

ASSIGNEE: Final = "prs_01HQ8Z6M4A"
ASSIGNEE_NAME: Final = "Alice Admin"

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
_SCRIPTING_ATTRIBUTES: Final = (*_HX_VERBS, "onclick", "onmousedown", "onkeydown")
_HIDDEN_CLASSES: Final = ("hidden", "is-hidden", "d-none", "sr-only", "visually-hidden")
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
# Step-store double — reproduced from test_playbook_admin_page.py
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
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
    """One blocking step per gate, plus two `listable` steps whose
    authored order disagrees with identifier order — the fixture
    `test_playbook_admin_page.py` uses, so a gate narrowing has both a
    step it keeps and steps at other gates it hides."""
    records = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work of hold.{gate}",
                gate=gate,
                blocking=True,
            ),
            display_order=10,
        )
        for gate in SPECIFIED_GATE_ORDER
    ) + (
        _Record(
            _step(
                identifier="listing.zeta", name="Work of listing.zeta", gate="listable"
            ),
            display_order=20,
        ),
        _Record(
            _step(
                identifier="listing.alpha",
                name="Work of listing.alpha",
                gate="listable",
            ),
            display_order=30,
        ),
    )
    return _FakeStepStore(records)


class _FakePerson:
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_FakePerson, ...]:
        return (_FakePerson(ASSIGNEE, ASSIGNEE_NAME),)


# ---------------------------------------------------------------------------
# HTML discovery: forms and HTMX controls — reproduced from
# test_playbook_admin_page.py
# ---------------------------------------------------------------------------


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.controls: list[tuple[str, str]] = []
        self._form: dict[str, Any] | None = None
        self._select: str | None = None
        self._select_done = False
        self._textarea: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        for verb in _HX_VERBS:
            if verb in a:
                self.controls.append((verb.removeprefix("hx-"), a[verb]))
                if self._form is not None and self._form["url"] == "":
                    self._form["method"] = verb.removeprefix("hx-")
                    self._form["url"] = a[verb]
        if tag == "a" and "href" in a:
            self.controls.append(("get", a["href"]))
        if tag == "form":
            self._form = {
                "method": (a.get("method") or "get").lower(),
                "url": a.get("action", ""),
                "fields": {},
                "hidden": set(),
            }
            for verb in _HX_VERBS:
                if verb in a:
                    self._form["method"] = verb.removeprefix("hx-")
                    self._form["url"] = a[verb]
        elif self._form is not None and tag == "input":
            name = a.get("name")
            if not name:
                return
            kind = (a.get("type") or "text").lower()
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind == "hidden":
                self._form["hidden"].add(name)
            default = "on" if kind == "checkbox" else ""
            self._form["fields"][name] = a.get("value", default)
        elif self._form is not None and tag == "select":
            self._select = a.get("name")
            self._select_done = False
            if self._select:
                self._form["fields"][self._select] = ""
        elif self._form is not None and tag == "option" and self._select:
            if "selected" in a or not self._select_done:
                self._form["fields"][self._select] = a.get("value", "")
                self._select_done = "selected" in a
        elif self._form is not None and tag == "textarea":
            self._textarea = a.get("name")
            if self._textarea:
                self._form["fields"][self._textarea] = ""

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea:
            self._form["fields"][self._textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html)
    return parser


def _control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> tuple[str, str, dict[str, str]] | None:
    parsed = _parse(html)
    for form in parsed.forms:
        haystack = (
            form["url"] + " " + " ".join(f"{k}={v}" for k, v in form["fields"].items())
        )
        if all(part in haystack for part in contains) and not any(
            part in haystack for part in excludes
        ):
            return form["method"], form["url"], dict(form["fields"])
    for method, url in parsed.controls:
        if all(part in url for part in contains) and not any(
            part in url for part in excludes
        ):
            return method, url, {}
    return None


def _require_control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> tuple[str, str, dict[str, str]]:
    found = _control(html, contains=contains, excludes=excludes)
    if found is None:
        pytest.fail(
            f"no page control mentioning {contains} was discovered — the "
            "invented control vocabulary in this file's docstring needs "
            "correcting to the implemented page"
        )
    return found


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "roster", _FakeRoster())
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


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return response.text


def _narrowing(
    *, gate: str | None = None, discipline: Any = None, search: str | None = None
) -> dict[str, str]:
    params: dict[str, str] = {}
    if gate is not None:
        params[_FILTER_PARAMS["gate"]] = gate
    if discipline is not None:
        params[_FILTER_PARAMS["discipline"]] = getattr(discipline, "value", discipline)
    if search is not None:
        params[_FILTER_PARAMS["search"]] = search
    return params


def _resolve(url: str) -> str:
    from urllib.parse import urljoin

    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


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


def _own_text(node: _Node) -> str:
    return " ".join(
        child.text for child in node.children if isinstance(child, _Text)
    ).lower()


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


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


def _element_disabled(node: _Node) -> bool:
    return (
        "disabled" in node.attrs
        or node.attrs.get("aria-disabled", "").lower() == "true"
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


def _live(node: _Node) -> bool:
    return (
        not _inherited(node, _element_disabled)
        and not _inherited(node, _element_hidden)
        and not any(attribute in node.attrs for attribute in _SCRIPTING_ATTRIBUTES)
    )


def _first(root: _Node, tag: str) -> _Node:
    for element in _elements(root):
        if element.tag == tag:
            return element
    pytest.fail(f"the page renders no {tag!r} element at all")


def _before_title(node: _Node, title: _Node) -> bool:
    if node is title:
        return False
    if any(ancestor is title for ancestor in (node, *_ancestors(node))):
        return False
    if any(ancestor is node for ancestor in _ancestors(title)):
        return False
    return node.order < title.order


def _in_shared_header(node: _Node) -> bool:
    for candidate in (node, *_ancestors(node)):
        if candidate.tag == "header":
            return True
        if "admin-header" in _classes(candidate):
            return True
        if "admin-surface" in _classes(candidate):
            return True
        if "admin surfaces" in candidate.attrs.get("aria-label", "").lower():
            return True
    return False


def _links_to_path(root: _Node, path: str) -> list[_Node]:
    """Every anchor whose href *path component* is `path`, regardless of
    query — unlike the launch-detail breadcrumb's link, this one is
    required to carry the active narrowing forward, so a no-query filter
    would reject the very link this file is looking for."""
    found: list[_Node] = []
    for element in _elements(root):
        if element.tag != "a":
            continue
        href = element.attrs.get("href")
        if not href:
            continue
        if urlsplit(_resolve(href)).path == path:
            found.append(element)
    return found


def _current_segment_is(title: _Node, label: str) -> bool:
    """Whether the page's own `<h1>` — the breadcrumb's current, un-linked,
    last segment, since the two are now the same element
    (`.breadcrumb-current` IS the `<h1>`; a page carrying a breadcrumb
    renders no separate title of its own) — names `label` as its own text
    and is not itself, nor via an ancestor, a link.
    """
    return label.lower() in _own_text(title) and not _inherited(
        title, lambda n: n.tag == "a"
    )


def _same_narrowing(href: str, expected: dict[str, str]) -> bool:
    query = dict(parse_qsl(urlsplit(_resolve(href)).query, keep_blank_values=True))
    return all(query.get(key) == value for key, value in expected.items())


def _breadcrumb_table_offer(html: str, title_tag: str = "h1") -> list[_Node]:
    root = _tree(html)
    title = _first(root, title_tag)
    return [
        link
        for link in _links_to_path(root, _page_path())
        if _live(link) and _before_title(link, title) and not _in_shared_header(link)
    ]


# ===========================================================================
# ADDED requirement: The edit and create surfaces carry a breadcrumb to
# the step table
# ===========================================================================


def test_the_table_is_reachable_from_the_edit_surface_narrowing_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The table is reachable from the edit surface, narrowing
    intact.

    WHEN a step's edit surface is rendered under an active narrowing
    THEN its breadcrumb trail offers the step table in one action,
    without scripting
    AND following it renders the table under that same narrowing.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable")
    narrowed = _get_page(client, params=narrowing)
    assert "listing.zeta" in narrowed and "hold.commit" not in narrowed  # DERIVED guard

    _method, url, _fields = _require_control(
        narrowed, contains=("listing.zeta", "edit")
    )
    response = client.get(_resolve(url))
    assert response.status_code == 200, (
        f"opening the edit surface for listing.zeta failed: {response.status_code} "
        f"{response.text[:300]}"
    )
    surface = response.text

    offers = _breadcrumb_table_offer(surface)
    assert offers, (
        "the edit surface offers no plain link to the step table above its "
        f"<h1>, carrying an active narrowing — anchors present: "
        f"{sorted({e.attrs.get('href', '') for e in _elements(_tree(surface)) if e.tag == 'a'})}"
    )
    matching = [
        link for link in offers if _same_narrowing(link.attrs["href"], narrowing)
    ]
    assert matching, (
        f"none of the edit surface's table offers carry the narrowing "
        f"{narrowing!r} forward — offered hrefs: {[o.attrs['href'] for o in offers]}"
    )

    # SPECIFIED: following it renders the table under that same narrowing.
    followed = client.get(_resolve(matching[0].attrs["href"]))
    assert followed.status_code == 200, followed.text
    assert "listing.zeta" in followed.text and "hold.commit" not in followed.text, (
        "following the edit surface's breadcrumb link back to the table does "
        "not reproduce the gate narrowing that was active"
    )


def test_the_table_is_reachable_from_the_create_surface_narrowing_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The table is reachable from the create surface,
    narrowing intact.

    WHEN the create surface is rendered under an active narrowing
    THEN its breadcrumb trail offers the step table in one action,
    without scripting
    AND following it renders the table under that same narrowing.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    needle = "stock-ready"
    narrowing = _narrowing(search=needle)
    narrowed = _get_page(client, params=narrowing)
    assert (
        "hold.stock-ready" in narrowed and "hold.commit" not in narrowed
    )  # DERIVED guard

    create_url = None
    for _method, url in _parse(narrowed).controls:
        if _method != "get":
            continue
        if any(hint in url.lower() for hint in _CREATE_HINTS):
            create_url = url
            break
    if create_url is None:
        pytest.fail(
            "no live GET control on the narrowed table mentions "
            f"{_CREATE_HINTS} — correct `_CREATE_HINTS` to the implemented page"
        )
    response = client.get(_resolve(create_url))
    assert response.status_code == 200, response.text
    surface = response.text

    offers = _breadcrumb_table_offer(surface)
    assert offers, (
        "the create surface offers no plain link to the step table above its "
        "<h1>, carrying an active narrowing"
    )
    matching = [
        link for link in offers if _same_narrowing(link.attrs["href"], narrowing)
    ]
    assert matching, (
        f"none of the create surface's table offers carry the narrowing "
        f"{narrowing!r} forward — offered hrefs: {[o.attrs['href'] for o in offers]}"
    )

    followed = client.get(_resolve(matching[0].attrs["href"]))
    assert followed.status_code == 200, followed.text
    assert "hold.stock-ready" in followed.text and "hold.commit" not in followed.text, (
        "following the create surface's breadcrumb link back to the table "
        "does not reproduce the search narrowing that was active"
    )


def test_the_edit_surfaces_trail_names_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The edit surface's trail names the step.

    WHEN a step's edit surface is rendered
    THEN its breadcrumb trail's last segment names that step and is not a
    link.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    listed = _get_page(client)

    _method, url, _fields = _require_control(listed, contains=("listing.zeta", "edit"))
    response = client.get(_resolve(url))
    assert response.status_code == 200, response.text
    surface = response.text

    root = _tree(surface)
    title = _first(root, "h1")
    assert _current_segment_is(title, "Work of listing.zeta"), (
        "the edit surface's <h1> does not name the step ('Work of "
        f"listing.zeta') as its own, un-linked text ({_own_text(title)!r}) "
        "— correct `_current_segment_is` if the current segment is worded "
        "some other way"
    )
