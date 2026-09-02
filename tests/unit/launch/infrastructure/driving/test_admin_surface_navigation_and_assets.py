"""The admin header the playbook surfaces carry, and the stylesheet they
load (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/admin-presentation-vocabulary/specs/playbook-admin/spec.md`:

- ADDED *The page carries a header from which the other admin surface is
  reachable* — all four scenarios.
- ADDED *The presentation assets stay behind the admin guard and need no
  build step* — the half of its third scenario that is about the page:
  "the admin surfaces load their stylesheet successfully" with no build
  or asset step run. The other two scenarios, and the committed-bytes
  half of the third, live in
  `tests/unit/shared/infrastructure/driving/test_admin_assets_route.py`,
  which drives the shared route directly.

It also carries one assertion belonging to the *other* capability's
delta — `members-admin`'s ADDED *The page's presentation comes from the
shared admin vocabulary* requires the Team page's presentation to come
from "the same stylesheet the playbook admin surfaces load", and only a
rendering of the playbook surfaces can establish the second half of
that. It rides the stylesheet test below rather than becoming a file of
its own.

The manifest at
`openspec/changes/admin-presentation-vocabulary/test-manifest.md` records
every scenario, every assertion's classification, and the project
questions this file answered by assumption.

**Level.** Both admin routers, plus the shared asset router, mounted in
one app over stores of their own. That is the smallest unit that can
observe a scenario like *Departing from the create surface carries
nothing forward*, whose WHEN starts on a `launch` surface and whose THEN
is that an `access` page is served: neither module's routes alone can
show it. `main.py` mounts exactly these routers, so the composition is
the one the application uses rather than an invention of this file.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- That the header names the admin surfaces the session can reach, that
  the *other* surface is reachable from it in one action, that it
  identifies which surface is currently viewed, and that the create and
  edit surfaces each identify the *playbook* surface as current (delta,
  the requirement's own prose).
- That reachability depends on neither scripting nor the step set.
- That travelling to the Team page is not a write and carries nothing
  forward.
- That the shared asset route lives in
  `commerce_ops.shared.infrastructure.driving.admin_assets`, exposes
  `router`, and takes its guard from a module-level `verify` the
  composition root injects (`tasks.md` 1.2, `design.md` — *The shared
  asset route lives in `shared`, with its guard injected*).

INVENTED, each recorded in the manifest with its correction point:

- How a header is *located*: the smallest element that both links to the
  other admin surface and names this one. A page whose header is not an
  element of its own fails here with that message. Correction point:
  `_header_of`.
- The words by which each surface is named — `_PLAYBOOK_WORDS`,
  `_MEMBERS_WORDS`. The delta fixes that both surfaces are named, not the
  wording.
- How "identifies the surface currently viewed" is read: within the
  header, the current surface is either not rendered as a live link to
  another page, or carries `aria-current` / a `current`-ish class. That
  is the structural reading of "reads as a position rather than as an
  undifferentiated pair of links"; `design.md` chose "the current one
  identified rather than linked", which passes it. Correction point:
  `_identifies_current`.
- The Team page module's seams (`members`, `verify_admin_session`) and
  the members store double, both taken from
  `tests/unit/access/infrastructure/driving/test_members_admin_page.py`.
  Correction point: `_app`.

## What this file deliberately does NOT cover

Nothing about how the header *looks*. `design.md` — Goals confines this
file to what a response establishes; `tasks.md` 7.5 carries the manual
check that both links work in a real browser.

## Expected first-run state

No template carries a header today and no shared asset route exists, so
every test here is expected to fail on a wrong value rather than at
import: the page renders, the header does not, and the stylesheet the
templates link is not served from the shared route. The shared asset
module is resolved by name (`_assets_module`) precisely so that its
absence does not turn the header tests into import errors, which would
establish nothing about their own assertions.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 954 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driving import members_admin as members_module
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

#: The shared asset route this change adds. Imported by name rather than
#: by `import`, so that the header tests below — which do not need it —
#: still fail on a wrong value rather than at import while it is absent.
_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"


def _assets_module() -> ModuleType | None:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError:
        return None


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

_CREATE_HINTS: Final = ("new", "create", "add")
_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}

#: How each admin surface is named in a header. INVENTED — the delta
#: fixes that both are named, not the wording. Correction point for a
#: header that calls them something else.
_PLAYBOOK_WORDS: Final = ("playbook", "step", "steps")
_MEMBERS_WORDS: Final = ("team", "members", "member")

#: Markers by which a header may identify the current surface while still
#: rendering it as a link.
_CURRENT_ATTRIBUTES: Final = ("aria-current", "data-current")
_CURRENT_CLASSES: Final = ("current", "active", "here", "is-current", "is-active")

EDITED: Final = "listing.zeta"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_NAME: Final = "Bohdan Colleague"
CHRIS_DEPARTED: Final = "prs_01HQ8Z6M4C"
CHRIS_NAME: Final = "Chris Departed"

MEMBER_ADMIN_IDENTITY: Final = "U01ALICE"
MEMBER_ADMIN_NAME: Final = "Alice Admin"

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

_HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "sr-only",
    "visually-hidden",
)


# ---------------------------------------------------------------------------
# The step-store double
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
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
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
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


class _Member:
    def __init__(self, member_id: str, display_name: str, *, active: bool) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeMembers:
    def __init__(self) -> None:
        self.members_rows = (
            _Member(ALICE, ALICE_NAME, active=True),
            _Member(BOHDAN, BOHDAN_NAME, active=True),
            _Member(CHRIS_DEPARTED, CHRIS_NAME, active=False),
        )

    async def list_members(self) -> tuple[_Member, ...]:
        return self.members_rows

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


def _seeded_store() -> _FakeStepStore:
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
        _Record(_step(identifier=EDITED, name="Work of listing.zeta"), 20),
        _Record(_step(identifier="listing.alpha", name="Work of listing.alpha"), 30),
    )
    return _FakeStepStore(records)


# ---------------------------------------------------------------------------
# The membership-store double (see test_members_admin_page.py)
# ---------------------------------------------------------------------------


class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


async def _build_members_store() -> _FakeMembersStore:
    store = _FakeMembersStore()
    await create_member(
        members=store,
        principal="the-creating-admin",
        display_name=MEMBER_ADMIN_NAME,
        slack_identity=MEMBER_ADMIN_IDENTITY,
        clickup_user_id=None,
        admin=True,
    )
    return store


def _members_store() -> _FakeMembersStore:
    """Built off the event loop: the tests are synchronous and drive the
    ASGI app through `TestClient`'s own portal, as every driving-adapter
    test in this project does."""
    return asyncio.run(_build_members_store())


# ---------------------------------------------------------------------------
# An HTML tree
# ---------------------------------------------------------------------------


@dataclass
class _Text:
    ordinal: int
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
        self._ordinal = 0

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)

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
            self._ordinal += 1
            self._stack[-1].children.append(_Text(self._ordinal, _flat(data)))


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


def _size(node: _Node) -> int:
    return 1 + sum(1 for _ in _elements(node))


# ---------------------------------------------------------------------------
# The header, read off a response
# ---------------------------------------------------------------------------


def _path_of(href: str) -> str:
    return urlsplit(href).path


def _links_to(root: _Node, path: str) -> list[_Node]:
    """Every anchor whose destination is exactly that page — no query, so
    a narrowing offer pointing back at the list is not mistaken for a
    header link."""
    return [
        element
        for element in _elements(root)
        if element.tag == "a"
        and _path_of(element.attrs.get("href", "")) == path
        and not urlsplit(element.attrs.get("href", "")).query
    ]


def _names(node: _Node, words: tuple[str, ...]) -> bool:
    text = _all_text(node)
    return any(word in text for word in words)


def _header_of(
    root: _Node, *, other_path: str, current_words: tuple[str, ...]
) -> _Node:
    """The page's admin header.

    INVENTED: the smallest element that links to the other admin surface,
    names this one, and is not the page body dressed up as a header — a
    candidate holding the page's own tables or forms is rejected, or the
    step table's "Step" column heading would read as the header naming
    the current surface. A page carrying no such element — a bare link
    with nothing naming where you are — fails here rather than passing a
    weaker assertion. Correction point for a differently shaped header.
    """
    outbound = _links_to(root, other_path)
    if not outbound:
        pytest.fail(
            f"the page renders no link to {other_path!r} at all, so it carries "
            "no header from which the other admin surface is reachable"
        )
    candidates = [
        ancestor
        for link in outbound
        for ancestor in _ancestors(link)
        if _names(ancestor, current_words)
        and ancestor.tag not in ("html", "body", "#document")
        and not any(e.tag in ("table", "form") for e in _elements(ancestor))
    ]
    if not candidates:
        pytest.fail(
            f"the link to {other_path!r} sits in no element that also names "
            f"this surface (looked for {current_words}) without enclosing the "
            "page's own tables or forms, so the header names one surface "
            "rather than the pair — correct `_header_of` or "
            "`_PLAYBOOK_WORDS`/`_MEMBERS_WORDS` to the implemented header"
        )
    return min(candidates, key=_size)


def _offers_in_one_action(header: _Node, path: str) -> bool:
    """The other surface is reachable in one action: a live anchor, which
    needs no scripting."""
    return any(
        not _inherited(link, _element_disabled)
        and not _inherited(link, _element_hidden)
        for link in _links_to(header, path)
    )


def _marked_current(node: _Node) -> bool:
    if any(node.attrs.get(attribute, "").strip() for attribute in _CURRENT_ATTRIBUTES):
        return True
    return bool(_classes(node) & set(_CURRENT_CLASSES))


def _identifies_current(header: _Node, *, words: tuple[str, ...]) -> bool:
    """Whether the header reads as a position rather than as an
    undifferentiated pair of links.

    INVENTED reading: somewhere in the header, the current surface is
    named by something that either carries an explicit current marker or
    is not rendered as a link at all. `design.md` renders the current
    surface "identified rather than linked", which satisfies the second
    branch; `aria-current` on a self-link satisfies the first. A header
    rendering both surfaces as plain unmarked links satisfies neither,
    which is the state the requirement exists to rule out.
    """
    within = [header, *_elements(header)]
    naming = [
        element
        for element in within
        if _names(element, words)
        and not any(_names(child, words) for child in _elements(element))
    ]
    for element in naming:
        chain = [element]
        walker = element.parent
        while walker is not None and walker is not header.parent:
            chain.append(walker)
            walker = walker.parent
        if any(_marked_current(node) for node in chain):
            return True
        if not any(node.tag == "a" for node in chain):
            return True
    return False


def _stylesheet_hrefs(root: _Node) -> list[str]:
    return [
        element.attrs["href"]
        for element in _elements(root)
        if element.tag == "link"
        and "stylesheet" in element.attrs.get("rel", "").lower()
        and element.attrs.get("href")
    ]


# ---------------------------------------------------------------------------
# Submittable controls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Control:
    method: str
    url: str
    fields: tuple[tuple[str, str], ...] = ()
    inert: bool = False

    def data(self) -> dict[str, str]:
        return dict(self.fields)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.fields)

    @property
    def haystack(self) -> str:
        rendered = " ".join(f"{name}={value}" for name, value in self.fields)
        return f"{self.url} {rendered}"


def _texts(node: _Node) -> list[_Text]:
    found: list[_Text] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child)
        else:
            found.extend(_texts(child))
    return found


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


def _form_of(node: _Node) -> tuple[str, str, dict[str, str], list[tuple[str, str]]]:
    method = (node.attrs.get("method") or "get").lower()
    url = node.attrs.get("action", "")
    for verb in _HX_VERBS:
        if verb in node.attrs:
            method = verb.removeprefix("hx-")
            url = node.attrs[verb]
    fields: dict[str, str] = {}
    buttons: list[tuple[str, str]] = []
    for element in _elements(node):
        name = element.attrs.get("name")
        if element.tag == "input":
            kind = (element.attrs.get("type") or "text").lower()
            if not name:
                continue
            if kind in ("submit", "image"):
                buttons.append((name, element.attrs.get("value", "")))
                continue
            if kind in ("checkbox", "radio") and "checked" not in element.attrs:
                continue
            fields[name] = element.attrs.get(
                "value", "on" if kind == "checkbox" else ""
            )
        elif element.tag == "select" and name:
            fields[name] = _selected_of(element)
        elif element.tag == "textarea" and name:
            fields[name] = " ".join(t.text for t in _texts(element))
        elif element.tag == "button":
            if (element.attrs.get("type") or "submit").lower() == "submit":
                buttons.append((name or "", element.attrs.get("value", "")))
    return method, url, fields, buttons


def _controls(html: str) -> list[_Control]:
    found: list[_Control] = []
    for element in _elements(_tree(html)):
        disabled = _inherited(element, _element_disabled)
        if element.tag == "a":
            href = element.attrs.get("href", "")
            found.append(_Control("get", href, (), disabled or href in ("", "#")))
            continue
        if element.tag == "form":
            method, url, fields, buttons = _form_of(element)
            if buttons:
                for name, value in buttons:
                    carried = dict(fields)
                    if name:
                        carried[name] = value
                    found.append(
                        _Control(method, url, tuple(carried.items()), disabled)
                    )
            else:
                found.append(_Control(method, url, tuple(fields.items()), disabled))
            continue
        for verb in _HX_VERBS:
            if verb in element.attrs:
                found.append(
                    _Control(
                        verb.removeprefix("hx-"), element.attrs[verb], (), disabled
                    )
                )
    return found


def _first_control(html: str, *, contains: tuple[str, ...]) -> _Control | None:
    for control in _controls(html):
        if control.inert:
            continue
        if all(part in control.haystack for part in contains):
            return control
    return None


def _require_control(html: str, *, contains: tuple[str, ...]) -> _Control:
    found = _first_control(html, contains=contains)
    if found is None:
        pytest.fail(
            f"no live page control mentioning {contains} was discovered — the "
            "invented control vocabulary in this file's docstring needs "
            "correcting to the implemented page"
        )
    return found


def _authoring_form_of(
    html: str, *, require_discipline: bool = False
) -> _Control | None:
    for control in _controls(html):
        if control.method.upper() == "GET":
            continue
        if not any("name" in name for name in control.names):
            continue
        if not any("anchor" in name for name in control.names):
            continue
        if require_discipline and not any(
            "discipline" in name for name in control.names
        ):
            continue
        return control
    return None


# ---------------------------------------------------------------------------
# App harness: both admin surfaces plus the shared asset route, the way
# `main.py` composes them
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


_MEMBERS_ATTRIBUTES: Final = ("members", "read_members", "members_reader")


def _install_members(monkeypatch: pytest.MonkeyPatch) -> None:
    members = _FakeMembers()
    for name in _MEMBERS_ATTRIBUTES:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, members)
            return
    pytest.fail(
        "the page module exposes no members seam under any of "
        f"{_MEMBERS_ATTRIBUTES} — correct this file's probe to the "
        "implemented name"
    )


@dataclass(frozen=True)
class _Surfaces:
    client: TestClient
    steps: _FakeStepStore
    members: _FakeMembersStore


def _app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    steps: _FakeStepStore | None = None,
    members: _FakeMembersStore | None = None,
) -> _Surfaces:
    step_store = _seeded_store() if steps is None else steps
    members_store = _members_store() if members is None else members

    monkeypatch.setattr(page_module, "steps", step_store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    _install_members(monkeypatch)
    monkeypatch.setattr(members_module, "members", members_store)
    monkeypatch.setattr(members_module, "verify_admin_session", _fake_verify)

    app = FastAPI()
    app.include_router(page_module.router)
    app.include_router(members_module.router)
    assets = _assets_module()
    if assets is not None:
        monkeypatch.setattr(assets, "verify", _fake_verify)
        app.include_router(assets.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return _Surfaces(client, step_store, members_store)


def _shortest_get_route(router: Any) -> str:
    candidates: list[str] = []
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "GET" in methods and "{" not in path:
            candidates.append(path)
    assert candidates, f"{router!r} exposes no parameterless GET route"
    return min(candidates, key=len)


def _page_path() -> str:
    return _shortest_get_route(page_module.router)


def _members_path() -> str:
    return _shortest_get_route(members_module.router)


def _resolve(url: str) -> str:
    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


def _with_query(url: str, extra: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(extra)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _issue(
    client: TestClient,
    control: _Control,
    *,
    data: dict[str, Any] | None = None,
    follow_redirects: bool = True,
) -> Any:
    method = control.method.upper()
    target = _resolve(control.url.split("#")[0])
    payload: Any = control.data() if data is None else data
    if method == "GET":
        if payload:
            target = _with_query(target, dict(payload))
        return client.get(target, follow_redirects=follow_redirects)
    return client.request(
        method, target, data=payload, follow_redirects=follow_redirects
    )


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return response.text


def _open_create(client: TestClient) -> str:
    candidates = [
        control
        for control in _controls(_get_page(client))
        if control.method.upper() == "GET"
        and not control.inert
        and not control.url.startswith(("#", "http://", "https://", "mailto:"))
        and any(hint in control.url.lower() for hint in _CREATE_HINTS)
    ]
    for control in candidates:
        response = _issue(client, control)
        if response.status_code != 200:
            continue
        if _authoring_form_of(response.text, require_discipline=True) is not None:
            return str(response.text)
    pytest.fail(
        "no control on the list led to a create surface carrying the "
        f"authorable form (candidates tried: {[c.url for c in candidates]}) — "
        "correct `_CREATE_HINTS` and `_authoring_form_of` to the implemented page"
    )


def _open_edit(client: TestClient, step_id: str = EDITED) -> str:
    control = _require_control(_get_page(client), contains=(step_id, "edit"))
    response = _issue(client, control)
    assert response.status_code == 200, response.text
    return str(response.text)


def _shared_assets_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An app mounting the shared asset router *alone*, so that a
    stylesheet only `launch`'s own static route serves is distinguishable
    from one the shared route serves."""
    module = _assets_module()
    if module is None:
        pytest.fail(
            f"{_ASSETS_MODULE_NAME} does not exist, so nothing can establish "
            "that both admin surfaces load the same stylesheet"
        )
    monkeypatch.setattr(module, "verify", _fake_verify)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _playbook_header(html: str) -> _Node:
    return _header_of(
        _tree(html), other_path=_members_path(), current_words=_PLAYBOOK_WORDS
    )


# ---------------------------------------------------------------------------
# ADDED requirement: The page carries a header from which the other admin
# surface is reachable
# ---------------------------------------------------------------------------


def test_the_members_page_is_reachable_from_the_step_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The Team page is reachable from the step list.

    WHEN the step list is rendered
    THEN its header offers the Team page in one action
    AND identifies the step list as the surface currently viewed.
    """
    surfaces = _app(monkeypatch)
    listed = _get_page(surfaces.client)

    header = _playbook_header(listed)

    # SPECIFIED: the Team page is offered in one action, and without
    # scripting — a plain anchor.
    assert _offers_in_one_action(header, _members_path()), (
        f"the header renders no live link to {_members_path()!r}, so the "
        "Team page is reachable only by an admin who knows to type the URL"
    )
    # SPECIFIED: and the header identifies the step list as current.
    assert _identifies_current(header, words=_PLAYBOOK_WORDS), (
        "the header does not identify the playbook surface as the one being "
        "viewed, so it reads as an undifferentiated pair of links rather than "
        f"as a position (header: {_flat(_all_text(header))[:300]!r})"
    )
    # SPECIFIED: travelling there really serves the Team page.
    link = _links_to(header, _members_path())[0]
    served = surfaces.client.get(link.attrs["href"])
    assert served.status_code == 200, served.text
    assert MEMBER_ADMIN_IDENTITY in served.text, (
        "the header's members link does not lead to the Team page"
    )


def test_the_header_does_not_depend_on_how_many_steps_are_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The header does not depend on how many steps are shown.

    WHEN the step list is rendered under a narrowing that matches no step
    at all
    THEN the header is still rendered and still offers the Team page.
    """
    surfaces = _app(monkeypatch)
    needle = "no-step-anywhere-carries-this-phrase"

    empty = _get_page(surfaces.client, params={_FILTER_PARAMS["search"]: needle})

    # DERIVED guard: the narrowing really matches nothing, so the header
    # below is being read off an empty list.
    for identifier in ("hold.commit", EDITED, "listing.alpha"):
        assert identifier not in empty, (
            f"the search {needle!r} still renders {identifier}, so this test "
            "does not reach the empty-list case"
        )
    # SPECIFIED: the header is still rendered and still offers the membership.
    header = _playbook_header(empty)
    assert _offers_in_one_action(header, _members_path()), (
        "the header stops offering the Team page once the narrowing "
        "empties the list, so reachability depends on the step set"
    )


def test_the_authoring_surfaces_carry_the_header_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The authoring surfaces carry the header too.

    WHEN the create surface and a step's edit surface are each rendered
    THEN each carries the header offering the Team page
    AND each identifies the playbook surface as the one currently
    viewed.
    """
    surfaces = _app(monkeypatch)

    for what, html in (
        ("create surface", _open_create(surfaces.client)),
        ("edit surface", _open_edit(surfaces.client)),
    ):
        header = _playbook_header(html)
        # SPECIFIED: each carries the header offering the Team page.
        assert _offers_in_one_action(header, _members_path()), (
            f"the {what} carries no live link to {_members_path()!r} in its "
            "header — an admin part-way through authoring is exactly the "
            "member who needs the membership"
        )
        # SPECIFIED: and identifies the playbook surface as current —
        # the authoring surfaces are not named in the header themselves.
        assert _identifies_current(header, words=_PLAYBOOK_WORDS), (
            f"the {what}'s header does not identify the playbook surface as "
            "the one being viewed"
        )


def test_departing_from_the_create_surface_carries_nothing_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Departing from the create surface carries nothing
    forward.

    WHEN the header's members link is taken from the create surface
    THEN the Team page is served
    AND nothing the create surface held is persisted.

    That departing discards what was typed is accepted by the
    requirement, not repaired, so nothing here asserts recovery. What is
    asserted is the other half: taking the link is not a write, and the
    narrowing this capability carries between its own views does not
    travel with it.
    """
    surfaces = _app(monkeypatch)
    # Taken before anything is driven, and compared rather than required to
    # be empty: this file's own members fixture seeds its store *through the
    # write path* (`_build_members_store` calls `create_member`), so the
    # double already carries that one save before a request exists. What the
    # scenario is about is whether *departing* writes anything, which is a
    # difference across the navigation and not an absolute count.
    steps_written = len(surfaces.steps.saves)
    members_written = len(surfaces.members.saves)

    created = _open_create(surfaces.client)
    header = _playbook_header(created)

    link = _links_to(header, _members_path())[0]
    href = link.attrs["href"]
    served = surfaces.client.get(href)

    # SPECIFIED: the Team page is served.
    assert served.status_code == 200, served.text
    assert MEMBER_ADMIN_IDENTITY in served.text, (
        "the header's members link from the create surface does not serve the "
        f"Team page: {served.text[:1000]}"
    )
    # SPECIFIED: and carries nothing forward — the Team page has no
    # narrowing of its own, so the link takes none.
    assert not urlsplit(href).query, (
        f"the header's members link carries {urlsplit(href).query!r} forward "
        "from the create surface, though the Team page has no narrowing of "
        "its own"
    )
    # SPECIFIED: nothing the create surface held is persisted — travelling
    # is not treated as a write, on either side. Opening the create surface
    # is inside the span deliberately: rendering it must write no more than
    # departing from it does.
    assert len(surfaces.steps.saves) == steps_written, (
        "taking the header link from the create surface persisted a step: "
        f"{surfaces.steps.saves[steps_written:]}"
    )
    assert len(surfaces.members.saves) == members_written, (
        "taking the header link from the create surface wrote to the membership: "
        f"{surfaces.members.saves[members_written:]}"
    )


# ---------------------------------------------------------------------------
# ADDED requirement: The presentation assets stay behind the admin guard
# and need no build step — the half about the pages
# ---------------------------------------------------------------------------


def test_the_admin_surfaces_load_their_stylesheet_with_no_build_step_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No build artifact stands between source and response.

    WHEN the repository is checked out and the application is started
    with no build or asset step run
    THEN the admin surfaces load their stylesheet successfully.

    The premise holds by construction: this test process runs no build,
    bundle or asset step — it imports the application and asks for what
    the templates reference. Every stylesheet each playbook surface links
    is then fetched against the running app, which is the only thing that
    catches the silent break `design.md` — Risks names: a moved
    `pico.min.css` leaves every template pointing at a route that no
    longer serves it, and an unstyled page still returns 200.

    A second assertion rides here because it needs the same three
    renderings: every stylesheet these surfaces link is served by the
    **shared** asset route. That is what makes `members-admin`'s "the same
    stylesheet the playbook admin surfaces load" literally true rather
    than true by convention — the membership side asserts its own href is
    served there, and one URL for one file is what joins the two.
    SPECIFIED, by `members-admin`'s ADDED *The page's presentation comes
    from the shared admin vocabulary*, which has no scenario of its own
    for this half.
    """
    surfaces = _app(monkeypatch)
    linked: list[tuple[str, str]] = []

    for what, html in (
        ("step list", _get_page(surfaces.client)),
        ("create surface", _open_create(surfaces.client)),
        ("edit surface", _open_edit(surfaces.client)),
    ):
        hrefs = _stylesheet_hrefs(_tree(html))
        # SPECIFIED: the surface loads a stylesheet at all.
        assert hrefs, f"the {what} links no stylesheet"
        for href in hrefs:
            if href.startswith(("http://", "https://", "//")):
                pytest.fail(
                    f"the {what} loads {href!r} from off the machine, so what "
                    "is served is not what the repository committed"
                )
            response = surfaces.client.get(_resolve(href))
            # SPECIFIED: and loads it successfully.
            assert response.status_code == 200, (
                f"the {what} links {href!r}, which the running application "
                f"answers {response.status_code} for — the page renders "
                "unstyled and still returns 200, so nothing else catches this"
            )
            assert response.content, f"{href!r} is served empty to the {what}"
            linked.append((what, href))

    # SPECIFIED (`members-admin`): and it is the *shared* stylesheet.
    # Asserted after the loop above, so that a checkout where the shared
    # route does not exist yet still reports whether the pages load what
    # they link at all.
    shared = _shared_assets_client(monkeypatch)
    for what, href in linked:
        from_shared = shared.get(_resolve(href))
        assert from_shared.status_code == 200, (
            f"the {what} links {href!r}, which the shared asset route "
            f"answers {from_shared.status_code} for — the two admin "
            "surfaces are not loading the same stylesheet, so a "
            "presentation fix applied to one silently misses the other"
        )
