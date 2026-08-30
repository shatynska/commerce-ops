"""Filtering the dependency control's options (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/pick-steps-and-people-by-checkbox/specs/playbook-admin/spec.md`
— the ADDED requirement *The dependency control's options can be
filtered*, and only the obligations that requirement's own paragraph
beginning "What a response can be asked, and what it cannot" assigns to a
**response**.

The two controls' own rules — the per-value controls, `chosen-set`, the
chips, the emptied key and where a fault mark lands — are the MODIFIED
requirement's subject and are covered in
`test_playbook_admin_multi_value_controls.py` in this directory. The
stylesheet-scoping clause, which the MODIFIED requirement states over
this filtering's selectors as well as over the controls', is covered in
`test_playbook_admin_picker_vocabulary_scope.py`.

Every scenario of the requirement is accounted for — covered here or
recorded as confirmed by direct inspection of the rendered page — in the
manifest at
`openspec/changes/pick-steps-and-people-by-checkbox/test-manifest.md`.

## What this file deliberately does NOT assert

The requirement's own split is the map. These four are **behaviours of
the enhancement**, which the requirement designates for direct
inspection of the rendered page:

- that the filtering *narrows* what is shown,
- that the two mechanisms compose,
- that a chosen option hidden by filtering is still submitted,
- that the hidden-chosen report appears when one is.

Filtering never survives a render, so no response can carry the
occurrence at all — which is why the region's role marker
(`hidden-chosen-notice`) is split from the occurrence marker
(`hidden-chosen`), and why this file asserts the first is present and
the second is not. This repository has three Python test tiers
(`AGENTS.md` — *Testing Strategy*) and nothing that drives a browser;
`tasks.md` 7.0 forbids growing one for this change.

## Level

The playbook-admin router over a step-store double and a roster double,
driven the way a browser drives it. The harness is the one
`test_playbook_admin_page.py` established and the sibling admin tests
extend, reproduced here rather than imported: this project keeps its
test files self-contained.

## Fixed by the artifacts

The three literal markers `option-gate-filter`, `option-filter` and
`hidden-chosen-notice`/`hidden-chosen`, the exclusions the counts are
computed over, and which gate the later-marks are computed against — all
given by the delta itself.

## INVENTED, with correction points

- A marker is read as a **class token**, or as the value of any `data-*`
  attribute, or as an element's `id`. Correction point: `_carries`.
- That an option's **row** is the `<label>` bound to that value's own
  per-value control, and that a **gate group** is the smallest ancestor
  of one gate's rows that names that gate in text of its own.
  Correction points: `_option_rows`, `_gate_group`.
- That a gate's **count** is a number rendered in the filter control's
  own text or attributes. Correction point: `_counts_in`.
- How a gate is **marked as later**: a class or `data-*` token
  containing `later`, or the word in the control's own text. No artifact
  fixes the wording. Correction point: `_marked_later`.
- The phrasing sets for the no-match statement, and the phrases that
  would read as the step's own gate. Correction points:
  `_NO_MATCH_WORDS`, `_OWN_GATE_PHRASES`, `_BLOCKING_WORDS`.
- The page seams, the session cookie and the edit/create control
  vocabulary, inherited from the sibling admin-page tests.

## Expected first-run state

**The change is not implemented.** The dependency control ships today as
a `<select multiple>` with an `<optgroup>` per gate: no filtering
control, no count, no later-gate mark and no hidden-chosen region. Every
test here therefore executes against a real rendering and fails on the
value produced rather than on an absent target.

One test is expected to **pass** and is recorded in the manifest as a
regression guard rather than as coverage of new behaviour:
`test_the_filtering_reaches_no_link_and_no_submission` — there is no
filtering yet, so nothing carries it. It is what would catch the
filtering becoming a second page narrowing by accident (`tasks.md`
4.10), which is the only way that obligation can be broken.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1660 passed, 0 failed — at the worktree root
on 2026-08-29, commit `81e042a`, tree clean but for an untracked
`.claude/worktrees/`.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import parse_qsl, urljoin, urlsplit

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
from commerce_ops.shared.domain.discipline import Discipline

page_module: ModuleType = importlib.import_module(
    "commerce_ops.launch.infrastructure.driving.playbook_admin"
)

# ---------------------------------------------------------------------------
# The delta's own literal markers
# ---------------------------------------------------------------------------

OPTION_FILTER: Final = "option-filter"
OPTION_GATE_FILTER: Final = "option-gate-filter"
HIDDEN_CHOSEN_NOTICE: Final = "hidden-chosen-notice"
HIDDEN_CHOSEN: Final = "hidden-chosen"

AFTER_STEPS: Final = "after_steps"

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

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"

EDITED: Final = "listing.the-step-being-edited"
EDITED_NAME: Final = "Work the author is editing"
EDITED_GATE: Final = "listable"
COMMIT_OPTION: Final = "listing.commitment-agreed"
COMMIT_OPTION_NAME: Final = "Commitment to launch is agreed"
TITLE_OPTION: Final = "listing.title-conforms"
TITLE_OPTION_NAME: Final = "Title conforms to marketplace policy"
IMAGES_OPTION: Final = "listing.images-uploaded"
IMAGES_OPTION_NAME: Final = "Hero and gallery images are uploaded"
LIVE_OPTION: Final = "inventory.units-received"
LIVE_OPTION_NAME: Final = "Units are received into the warehouse"
GRADUATED_OPTION: Final = "inventory.graduation-review"
GRADUATED_OPTION_NAME: Final = "The graduation review is held"
DRAFTED: Final = "listing.a-drafted-step"
RETIRED: Final = "listing.a-retired-step"

STORED_DEPENDENCIES: Final = (COMMIT_OPTION, TITLE_OPTION)

#: Every `active` step, by gate. The edited step is one of the three at
#: `listable`, which is what makes the count for its own gate one short
#: of that gate's true size.
ACTIVE_STEPS: Final[dict[str, tuple[str, str]]] = {
    COMMIT_OPTION: ("commit", COMMIT_OPTION_NAME),
    TITLE_OPTION: ("listable", TITLE_OPTION_NAME),
    IMAGES_OPTION: ("listable", IMAGES_OPTION_NAME),
    EDITED: ("listable", EDITED_NAME),
    LIVE_OPTION: ("live", LIVE_OPTION_NAME),
    GRADUATED_OPTION: ("graduated", GRADUATED_OPTION_NAME),
}

#: What the control offers on the **edit** surface: every `active` step
#: but the one being edited.
EDIT_OFFERED: Final[dict[str, tuple[str, str]]] = {
    value: gate_and_name
    for value, gate_and_name in ACTIVE_STEPS.items()
    if value != EDITED
}

#: … and on the **create** surface, where no step is excluded on that
#: ground.
CREATE_OFFERED: Final[dict[str, tuple[str, str]]] = dict(ACTIVE_STEPS)

#: INVENTED phrasing sets — see this file's docstring.
_NO_MATCH_WORDS: Final = (
    "no step",
    "no steps",
    "nothing matches",
    "nothing matched",
    "no match",
    "no matches",
    "none match",
    "no options",
    "nothing here",
    "no results",
)
_OWN_GATE_PHRASES: Final = (
    "step's gate",
    "steps gate",
    "gate of this step",
    "the gate this step",
    "this step's gate",
)
_BLOCKING_WORDS: Final = ("blocking", "blocked", "blocks")
_LATER_TOKENS: Final = ("later",)
_LATER_WORDS: Final = ("later", "after this gate", "starts after", "downstream")

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
_CREATE_HINTS: Final = ("new", "create", "add")
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
# Step-store double
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": EDITED,
        "name": EDITED_NAME,
        "description": None,
        "gate": EDITED_GATE,
        "discipline": LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
        "starts_at_gate": None,
        "after_steps": (),
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _Record:
    def __init__(self, definition: StepDefinition, display_order: int = 10) -> None:
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


class _Person:
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_Person, ...]:
        return (_Person(ALICE, ALICE_NAME),)

    people = list_people

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


def _seeded_store() -> _FakeStepStore:
    order = 10
    records: list[_Record] = []

    def add(definition: StepDefinition) -> None:
        nonlocal order
        records.append(_Record(definition, display_order=order))
        order += 10

    add(_step(identifier=COMMIT_OPTION, name=COMMIT_OPTION_NAME, gate="commit"))
    add(_step(identifier=TITLE_OPTION, name=TITLE_OPTION_NAME, gate="listable"))
    add(_step(identifier=IMAGES_OPTION, name=IMAGES_OPTION_NAME, gate="listable"))
    add(_step(after_steps=STORED_DEPENDENCIES))
    add(
        _step(
            identifier=DRAFTED,
            name="Drafted work",
            gate="listable",
            status=StepStatus.DRAFT,
            assignees=(),
        )
    )
    add(
        _step(
            identifier=RETIRED,
            name="Retired work",
            gate="listable",
            status=StepStatus.RETIRED,
            assignees=(),
        )
    )
    add(
        _step(
            identifier=LIVE_OPTION,
            name=LIVE_OPTION_NAME,
            gate="live",
            discipline=INVENTORY,
        )
    )
    add(
        _step(
            identifier=GRADUATED_OPTION,
            name=GRADUATED_OPTION_NAME,
            gate="graduated",
            discipline=INVENTORY,
        )
    )
    return _FakeStepStore(tuple(records))


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
            self._stack[-1].children.append(_Text(" ".join(data.split())))


def _tree(html: str) -> _Node:
    parser = _TreeParser()
    parser.feed(html)
    return parser.root


def _elements(node: _Node) -> Iterator[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _elements(child)


def _texts(node: _Node) -> list[str]:
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.extend(_texts(child))
    return found


def _flat(node: _Node) -> str:
    return " ".join(_texts(node))


def _attribute_text(node: _Node) -> str:
    return " ".join(node.attrs.values())


def _said_by(node: _Node) -> str:
    return f"{_attribute_text(node)} {_flat(node)}"


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    """INVENTED — see this file's docstring."""
    if marker in _classes(node):
        return True
    if node.attrs.get("id") == marker:
        return True
    return any(
        key.startswith("data-") and marker in value.split()
        for key, value in node.attrs.items()
    )


def _marked(root: _Node, marker: str) -> list[_Node]:
    return [element for element in _elements(root) if _carries(element, marker)]


def _ancestors(node: _Node) -> Iterator[_Node]:
    walker = node.parent
    while walker is not None:
        yield walker
        walker = walker.parent


def _within(node: _Node, container: _Node) -> bool:
    return node is container or any(walker is container for walker in _ancestors(node))


def _common_ancestor(nodes: list[_Node]) -> _Node:
    chains = [[*reversed([node, *_ancestors(node)])] for node in nodes]
    shared = chains[0]
    for chain in chains[1:]:
        keep: list[_Node] = []
        for left, right in zip(shared, chain, strict=False):
            if left is not right:
                break
            keep.append(left)
        shared = keep
    assert shared, "the nodes share no ancestor, which a parsed document forbids"
    return shared[-1]


def _text_outside(node: _Node, excluded: list[_Node]) -> str:
    """This element's own text, skipping anything inside `excluded` —
    which is how a group's heading is told from its options."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        elif not any(_within(child, other) or child is other for other in excluded):
            found.append(_text_outside(child, excluded))
    return " ".join(part for part in found if part)


def _attributes_outside(node: _Node, excluded: list[_Node]) -> str:
    parts = [_attribute_text(node)]
    for element in _elements(node):
        if any(_within(element, other) for other in excluded):
            continue
        parts.append(_attribute_text(element))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Forms and the dependency control's own shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Form:
    html: str
    node: _Node
    method: str
    url: str
    pairs: tuple[tuple[str, str], ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(name for name, _ in self.pairs))


def _select_values(node: _Node) -> list[str]:
    options = [element for element in _elements(node) if element.tag == "option"]
    chosen = [
        option.attrs.get("value", "")
        for option in options
        if "selected" in option.attrs
    ]
    if chosen:
        return chosen
    if "multiple" in node.attrs:
        return []
    return [options[0].attrs.get("value", "")] if options else []


def _submittable(node: _Node) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for element in _elements(node):
        name = element.attrs.get("name")
        if not name or "disabled" in element.attrs:
            continue
        if element.tag == "input":
            kind = (element.attrs.get("type") or "text").lower()
            if kind in ("submit", "image", "button", "reset"):
                continue
            if kind in ("checkbox", "radio") and "checked" not in element.attrs:
                continue
            default = "on" if kind == "checkbox" else ""
            pairs.append((name, element.attrs.get("value", default)))
        elif element.tag == "select":
            pairs.extend((name, value) for value in _select_values(element))
        elif element.tag == "textarea":
            pairs.append((name, _flat(element)))
        elif (
            element.tag == "button"
            and (element.attrs.get("type") or "submit").lower() == "submit"
        ):
            pairs.append((name, element.attrs.get("value", "")))
    return pairs


def _forms(html: str) -> list[_Form]:
    found: list[_Form] = []
    for element in _elements(_tree(html)):
        if element.tag != "form":
            continue
        method = (element.attrs.get("method") or "get").lower()
        url = element.attrs.get("action", "")
        for verb in _HX_VERBS:
            if verb in element.attrs:
                method = verb.removeprefix("hx-")
                url = element.attrs[verb]
        found.append(_Form(html, element, method, url, tuple(_submittable(element))))
    return found


def _authoring_form(html: str) -> _Form:
    for form in _forms(html):
        names = form.names
        if any("name" in name for name in names) and any(
            "gate" in name for name in names
        ):
            return form
    pytest.fail(
        "no authoring form was discoverable on the surface (forms carry "
        f"{[form.names for form in _forms(html)]}) — correct this file's form "
        "discovery to the implemented page"
    )


def _value_inputs(root: _Node) -> list[_Node]:
    return [
        element
        for element in _elements(root)
        if element.tag == "input"
        and element.attrs.get("name") == AFTER_STEPS
        and (element.attrs.get("type") or "text").lower() == "checkbox"
    ]


def _offered_values(form: _Form) -> dict[str, _Node]:
    found: dict[str, _Node] = {}
    for element in _value_inputs(form.node):
        value = element.attrs.get("value", "")
        if value:
            found.setdefault(value, element)
    return found


def _shown_as_chosen(form: _Form) -> set[str]:
    """What the form shows as chosen, whatever draws it — read across
    both shapes deliberately, so that nothing here holds vacuously
    against the `<select multiple>` that ships today."""
    chosen = {
        element.attrs.get("value", "")
        for element in _value_inputs(form.node)
        if "checked" in element.attrs and element.attrs.get("value")
    }
    for element in _elements(form.node):
        if element.tag == "select" and element.attrs.get("name") == AFTER_STEPS:
            chosen.update(value for value in _select_values(element) if value)
    return chosen


def _option_rows(form: _Form) -> dict[str, _Node]:
    """Each offered value's row: the `<label>` bound to that value's own
    per-value control. INVENTED — see this file's docstring."""
    labels = [element for element in _elements(form.node) if element.tag == "label"]
    rows: dict[str, _Node] = {}
    for value, control in _offered_values(form).items():
        identifier = control.attrs.get("id", "")
        for label in labels:
            if (identifier and label.attrs.get("for") == identifier) or _within(
                control, label
            ):
                rows[value] = label
                break
    return rows


def _require_rows(form: _Form, offered: dict[str, tuple[str, str]]) -> dict[str, _Node]:
    rows = _option_rows(form)
    missing = sorted(set(offered) - set(rows))
    assert not missing, (
        f"the dependency control renders no addressable option row for "
        f"{missing} (it offers {sorted(_offered_values(form))}) — correct "
        "`_option_rows` to the implemented control, or the control to the "
        "requirement"
    )
    return rows


def _gate_group(form: _Form, gate: str, offered: dict[str, tuple[str, str]]) -> _Node:
    """The smallest element holding this gate's option rows, none of
    another gate's, and naming the gate in text of its own."""
    rows = _require_rows(form, offered)
    mine = [row for value, row in rows.items() if offered[value][0] == gate]
    others = [row for value, row in rows.items() if offered[value][0] != gate]
    assert mine, f"no option row belongs to the gate {gate!r}"
    walker: _Node | None = _common_ancestor(mine)
    while walker is not None:
        if any(_within(other, walker) for other in others):
            break
        said = _text_outside(walker, mine).lower()
        if gate in said:
            return walker
        walker = walker.parent
    pytest.fail(
        f"the options at the gate {gate!r} sit in no element naming that gate "
        "outside the options themselves, so they are not grouped by gate — "
        "correct `_gate_group` to the implemented grouping"
    )


def _gate_filters(root: _Node) -> dict[str, _Node]:
    """Each gate the filtering offers, by the control marked
    `option-gate-filter` that offers it."""
    found: dict[str, _Node] = {}
    for control in _marked(root, OPTION_GATE_FILTER):
        said = _said_by(control).lower()
        for gate in SPECIFIED_GATE_ORDER:
            if gate in said:
                found.setdefault(gate, control)
    return found


def _counts_in(node: _Node) -> set[int]:
    """The numbers this control states. INVENTED — see this file's
    docstring."""
    said = _said_by(node)
    return {int(match) for match in re.findall(r"\d+", said)}


def _marked_later(node: _Node, excluded: list[_Node]) -> bool:
    """Whether this control or heading is marked as naming a gate later
    than the one the form was rendered with. INVENTED — see this file's
    docstring."""
    tokens = f"{_attributes_outside(node, excluded)}".lower()
    if any(token in tokens for token in _LATER_TOKENS):
        return True
    said = _text_outside(node, excluded).lower()
    return any(word in said for word in _LATER_WORDS)


def _later_than(gate: str) -> set[str]:
    if gate not in SPECIFIED_GATE_ORDER:
        return set()
    position = SPECIFIED_GATE_ORDER.index(gate)
    return set(SPECIFIED_GATE_ORDER[position + 1 :])


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


_ROSTER_ATTRIBUTES: Final = ("roster", "read_roster", "people", "roster_reader")


def _install_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    roster = _FakeRoster()
    for name in _ROSTER_ATTRIBUTES:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, roster)
            return
    pytest.fail(
        f"the page module exposes no roster seam under any of {_ROSTER_ATTRIBUTES}"
    )


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    _install_roster(monkeypatch)
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
            candidates.append(str(path))
    assert candidates, "the page router exposes no parameterless GET route"
    return min(candidates, key=len)


def _resolve(url: str) -> str:
    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return str(response.text)


def _links(html: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for element in _elements(_tree(html)):
        for verb in _HX_VERBS:
            if verb in element.attrs:
                found.append((verb.removeprefix("hx-"), element.attrs[verb]))
        if element.tag == "a" and element.attrs.get("href"):
            found.append(("get", element.attrs["href"]))
    return found


def _edit_surface(client: TestClient, step_id: str = EDITED) -> str:
    page = _get_page(client)
    for method, url in _links(page):
        if url.rstrip("/").endswith("/edit") and step_id in url:
            response = client.request(method.upper(), _resolve(url))
            assert response.status_code == 200, response.text
            return str(response.text)
    pytest.fail(
        f"no edit affordance for {step_id!r} was discoverable — correct this "
        "file's control vocabulary to the implemented page"
    )


def _create_surface(client: TestClient) -> str:
    page = _get_page(client)
    for method, url in _links(page):
        if method != "get" or url.startswith(("#", "http://", "https://", "mailto:")):
            continue
        if not any(hint in url.lower() for hint in _CREATE_HINTS):
            continue
        response = client.get(_resolve(url))
        if response.status_code != 200:
            continue
        body = str(response.text)
        if any("gate" in form.names for form in _forms(body)):
            return body
    pytest.fail(
        "no control on the list led to a create surface carrying the "
        "authorable form — correct `_CREATE_HINTS` to the implemented page"
    )


def _post(client: TestClient, form: _Form, pairs: list[tuple[str, str]]) -> str:
    payload: dict[str, list[str]] = {}
    for name, value in pairs:
        payload.setdefault(name, []).append(value)
    response = client.request(
        form.method.upper(),
        _resolve(form.url),
        data=payload,
        follow_redirects=False,
    )
    assert response.status_code < 500, response.text
    return str(response.text)


def _replace(
    pairs: list[tuple[str, str]], name: str, values: tuple[str, ...]
) -> list[tuple[str, str]]:
    kept = [(key, value) for key, value in pairs if key != name]
    return kept + [(name, value) for value in values]


def _field_named(form: _Form, fragments: tuple[str, ...], what: str) -> str:
    for name in form.names:
        if any(fragment in name.lower() for fragment in fragments):
            return name
    pytest.fail(
        f"the step form offers no {what} control (looked for a field whose "
        f"name contains one of {fragments}; fields are {sorted(form.names)})"
    )


def _start_gate_field(form: _Form) -> str:
    return _field_named(form, ("starts_at", "start_gate"), "start-gate")


def _own_gate_field(form: _Form) -> str:
    """The step's own gate control — a field mentioning "gate" that is
    not the start-gate control."""
    start = _start_gate_field(form)
    for name in form.names:
        if "gate" in name.lower() and name != start:
            return name
    pytest.fail(
        f"the step form offers no gate control distinct from {start!r} "
        f"(fields: {sorted(form.names)})"
    )


def _gate_held_by(form: _Form) -> str:
    name = _own_gate_field(form)
    values = [value for key, value in form.pairs if key == name]
    assert values, f"the form's gate control {name!r} holds nothing"
    return values[0]


# ===========================================================================
# ADDED Requirement: The dependency control's options can be filtered
# — the response half
# ===========================================================================


def test_the_control_offers_both_ways_of_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The control offers both ways of filtering.

    WHEN the control for the steps a step waits on is opened
    THEN controls marked `option-gate-filter` offer each gate, and one
    marked `option-filter` accepts text.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    filters = _gate_filters(form.node)
    # SPECIFIED: gate filtering, marked, offering the gates.
    assert filters, (
        f"the form renders no control marked {OPTION_GATE_FILTER!r}, so the "
        "one gesture that narrows 63 options to 4 is not offered at all"
    )
    holding = {gate for gate, _ in EDIT_OFFERED.values()}
    assert holding <= set(filters), (
        f"the filtering offers {sorted(filters)}; the gates the control's "
        f"options actually sit at are {sorted(holding)}"
    )

    text_filters = _marked(form.node, OPTION_FILTER)
    # SPECIFIED: one control marked `option-filter`, accepting text.
    assert len(text_filters) == 1, (
        f"the form renders {len(text_filters)} controls marked "
        f"{OPTION_FILTER!r}; the requirement names exactly one"
    )
    control = text_filters[0]
    accepts_text = control.tag == "input" and (
        control.attrs.get("type") or "text"
    ).lower() in ("text", "search")
    if not accepts_text:
        accepts_text = any(
            element.tag == "input"
            and (element.attrs.get("type") or "text").lower() in ("text", "search")
            for element in _elements(control)
        )
    assert accepts_text, (
        f"the control marked {OPTION_FILTER!r} accepts no text, so nothing "
        "finds a step whose gate the author does not remember"
    )


def test_each_gate_states_how_many_options_it_offers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Each gate states how many options it offers.

    WHEN that control is opened while a step is being edited
    THEN each `option-gate-filter` states how many of the offered options
    its gate holds
    AND the count for the edited step's own gate excludes that step.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    filters = _gate_filters(form.node)
    assert filters, f"the form renders no control marked {OPTION_GATE_FILTER!r}"

    offered_per_gate: dict[str, int] = {}
    for gate, _ in EDIT_OFFERED.values():
        offered_per_gate[gate] = offered_per_gate.get(gate, 0) + 1

    for gate, expected in offered_per_gate.items():
        control = filters.get(gate)
        assert control is not None, (
            f"the filtering offers no control for the gate {gate!r}, which "
            f"holds {expected} of the offered options"
        )
        # SPECIFIED: each gate states how many of the offered options it
        # holds.
        assert expected in _counts_in(control), (
            f"the {gate!r} filter states {sorted(_counts_in(control))}, not "
            f"{expected} — the counts are what state the shape of the set "
            "before an author starts scrolling"
        )

    # SPECIFIED: the count for the edited step's own gate excludes that
    # step. `listable` holds three `active` steps and offers two.
    own = filters[EDITED_GATE]
    assert 3 not in _counts_in(own), (
        f"the {EDITED_GATE!r} filter states {sorted(_counts_in(own))}, which "
        "includes the gate's true size; the counts state what the control "
        "*offers*, and the step being edited is not offered"
    )


def test_the_region_for_the_hidden_chosen_report_exists_before_anything_is_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The region for the hidden-chosen report exists before
    anything is hidden.

    WHEN the form is rendered
    THEN it carries a region marked `hidden-chosen-notice`, so a response
    can be asked whether there is somewhere for the report to appear
    AND that region carries `hidden-chosen` only once a chosen option is
    actually hidden.

    Filtering never survives a render, so no response can carry the
    occurrence: the second half is read here as the occurrence marker
    being **absent** from every render, which is the whole of what a
    response can establish. That the report then appears is designated
    for direct inspection.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    regions = _marked(form.node, HIDDEN_CHOSEN_NOTICE)
    # SPECIFIED: the region's role marker is present whether or not
    # anything is hidden.
    assert regions, (
        f"the form carries no region marked {HIDDEN_CHOSEN_NOTICE!r}, so an "
        "author who hides a chosen row is looking at a control that appears "
        "to hold less than it will submit with nowhere for the surface to "
        "say so"
    )
    # SPECIFIED: the occurrence marker never outruns the occurrence, and
    # no render can carry an occurrence at all.
    occurrences = _marked(form.node, HIDDEN_CHOSEN)
    assert not occurrences, (
        f"a rendered form carries {HIDDEN_CHOSEN!r} with nothing hidden — "
        "filtering never survives a render, so a marker asserting the "
        "occurrence has outrun it"
    )


def test_every_option_carries_the_gate_its_text_filtering_matches_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Every option carries the gate its text filtering matches
    on.

    WHEN the form is rendered
    THEN each option carries its step's gate, so that text matching a
    gate's name can match it.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    rows = _require_rows(form, EDIT_OFFERED)
    for value, (gate, _) in EDIT_OFFERED.items():
        said = _said_by(rows[value]).lower()
        # SPECIFIED: the option itself carries its gate.
        assert gate in said, (
            f"the option for {value!r} does not carry its gate {gate!r} "
            f"({said!r}), so text matching that gate's name cannot match it"
        )


def test_a_later_gate_is_marked_against_the_gate_the_form_was_rendered_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A later gate is marked against the gate the form was
    rendered with.

    WHEN the form is rendered carrying the gate `listable`
    THEN the gates after `listable` are offered, and are marked as later,
    in the filtering and in the list.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    assert _gate_held_by(form) == EDITED_GATE, (
        "the edited step's form was rendered holding "
        f"{_gate_held_by(form)!r}, not {EDITED_GATE!r}"
    )
    later = _later_than(EDITED_GATE)

    # SPECIFIED: the form does not withhold them.
    offered = _offered_values(form)
    for value, (gate, _) in EDIT_OFFERED.items():
        if gate in later:
            assert value in offered, (
                f"the option for {value!r} at the later gate {gate!r} is not "
                "offered; the form marks later gates and never withholds them"
            )

    filters = _gate_filters(form.node)
    assert filters, f"the form renders no control marked {OPTION_GATE_FILTER!r}"
    for gate, control in filters.items():
        # SPECIFIED: marked in the filtering, and only where later.
        assert _marked_later(control, []) is (gate in later), (
            f"the {gate!r} filter is "
            f"{'marked' if _marked_later(control, []) else 'unmarked'} as "
            f"later than {EDITED_GATE!r}, which is wrong: the gates after "
            f"{EDITED_GATE!r} are {sorted(later)}"
        )

    rows = _require_rows(form, EDIT_OFFERED)
    for gate in {gate for gate, _ in EDIT_OFFERED.values()}:
        group = _gate_group(form, gate, EDIT_OFFERED)
        mine = [row for value, row in rows.items() if EDIT_OFFERED[value][0] == gate]
        # SPECIFIED: and marked in the list.
        assert _marked_later(group, mine) is (gate in later), (
            f"the {gate!r} group in the list is "
            f"{'marked' if _marked_later(group, mine) else 'unmarked'} as "
            f"later than {EDITED_GATE!r}"
        )


def test_a_create_surface_marks_against_the_gate_it_was_rendered_holding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A create surface marks against the gate it was rendered
    holding.

    WHEN the create surface is rendered holding a gate
    THEN the later-gate marks are computed against that gate, and not
    against a step, there being none.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_create_surface(client))

    held = _gate_held_by(form)
    later = _later_than(held)
    filters = _gate_filters(form.node)
    assert filters, (
        f"the create surface renders no control marked {OPTION_GATE_FILTER!r}"
    )

    for gate, control in filters.items():
        # SPECIFIED: computed against the gate the surface was rendered
        # holding.
        assert _marked_later(control, []) is (gate in later), (
            f"the create surface was rendered holding {held!r} and marks the "
            f"{gate!r} filter "
            f"{'as later' if _marked_later(control, []) else 'as not later'}"
        )

    # SPECIFIED: and not against a step, there being none — every
    # `active` step is offered here, the one the edit surface excludes
    # included.
    offered = _offered_values(form)
    assert set(offered) == set(CREATE_OFFERED), (
        f"the create surface offers {sorted(offered)}; with no step being "
        f"edited every `active` step is offered ({sorted(CREATE_OFFERED)})"
    )


def test_a_gate_naming_none_of_the_sequence_marks_nothing_as_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "Where the gate the form was rendered with
    names no gate of the sequence — which a re-rendered submission can
    carry — no gate SHALL be marked as later, there being nothing to be
    later than."

    Stated in prose and in no scenario of its own; asserted here because
    a submission carrying an unknown gate is the one way the form is
    rendered with nothing to compare against, and an implementation that
    compared positions would mark either everything or nothing by
    accident.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _authoring_form(_edit_surface(client))

    unknown = _replace(list(form.pairs), _own_gate_field(form), ("no-such-gate",))
    rejected = _post(client, form, unknown)

    assert store.saves == [], "a step naming no known gate was persisted"
    reread = _authoring_form(rejected)
    filters = _gate_filters(reread.node)
    assert filters, (
        f"the re-rendered form carries no control marked {OPTION_GATE_FILTER!r}"
    )
    marked = [gate for gate, control in filters.items() if _marked_later(control, [])]
    # SPECIFIED: nothing is marked as later.
    assert not marked, (
        f"the form was re-rendered holding a gate of no sequence and still "
        f"marks {sorted(marked)} as later — there is nothing to be later than"
    )


def test_the_filtering_reaches_no_link_and_no_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The filtering reaches no link and no submission.

    WHEN the form is rendered and submitted
    THEN no link on it carries the filtering, and the submission carries
    no filtering state.

    The filtering is local to one unsaved control: it is neither the page
    *narrowing* this capability requires elsewhere nor the step list's
    own gate and discipline *filters*, and it must not become a second
    page narrowing by accident (`tasks.md` 4.10).
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _edit_surface(client)
    form = _authoring_form(surface)

    controls = [
        *_marked(form.node, OPTION_FILTER),
        *_marked(form.node, OPTION_GATE_FILTER),
    ]
    named = {
        element.attrs["name"]
        for control in controls
        for element in (control, *_elements(control))
        if element.attrs.get("name")
    }

    # SPECIFIED: no filtering state reaches the submission.
    submitted = set(form.names) & named
    assert not submitted, (
        f"the filtering controls {sorted(submitted)} are submitted with the "
        "form, so a transient filter local to one unsaved control reaches the "
        "write"
    )

    # SPECIFIED: no link carries the filtering.
    forbidden = {OPTION_FILTER, OPTION_GATE_FILTER} | named
    for _, url in _links(surface):
        query = {key for key, _ in parse_qsl(urlsplit(url).query)}
        carried = query & forbidden
        assert not carried, (
            f"the link {url!r} carries the filtering as {sorted(carried)}, so "
            "it survives a page it was never meant to leave"
        )

    # SPECIFIED: and it does not survive the write.
    saved = _post(client, form, list(form.pairs))
    for _, url in _links(saved):
        query = {key for key, _ in parse_qsl(urlsplit(url).query)}
        assert not query & forbidden, (
            f"the response to the write carries the filtering on {url!r}"
        )


def test_the_control_is_complete_without_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The control is complete without filtering.

    WHEN the form is rendered where the filtering cannot run
    THEN every option is present, grouped by gate, and what is stored as
    chosen is shown as chosen.

    A server response *is* the unenhanced state: nothing here runs the
    script, so the rendering read is the one an author gets where the
    enhancement cannot run.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    # SPECIFIED: every option is present.
    assert set(_offered_values(form)) == set(EDIT_OFFERED), (
        f"the control offers {sorted(_offered_values(form))}, not the "
        f"complete offered set {sorted(EDIT_OFFERED)}"
    )
    # SPECIFIED: grouped by gate — `_gate_group` fails where a gate's
    # options sit in nothing naming that gate.
    rows = _require_rows(form, EDIT_OFFERED)
    for value, (gate, _) in EDIT_OFFERED.items():
        group = _gate_group(form, gate, EDIT_OFFERED)
        assert _within(rows[value], group), (
            f"the option for {value!r} sits outside its own gate's group"
        )
    # SPECIFIED: what is stored as chosen is shown as chosen.
    assert _shown_as_chosen(form) == set(STORED_DEPENDENCIES), (
        f"the control shows {sorted(_shown_as_chosen(form))} as chosen; the "
        f"stored step waits on {sorted(STORED_DEPENDENCIES)}"
    )


def test_the_no_match_case_carries_a_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "Where the filtering in force matches no
    option the control SHALL say so plainly, rather than showing an empty
    list", which the requirement's own response list carries as "that a
    statement is rendered for the no-match case".

    A response cannot be asked whether the statement *appears* — that
    needs the filtering to run — only whether the surface ships one at
    all. An empty box reads as a failure to load, and an author cannot
    tell one from a filter that happens to match nothing.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    said = _flat(form.node).lower()
    scripts = " ".join(
        _flat(element) for element in _elements(form.node) if element.tag == "script"
    ).lower()
    # SPECIFIED: the statement is rendered for the case, whether it is
    # shown yet or not.
    assert any(word in f"{said} {scripts}" for word in _NO_MATCH_WORDS), (
        "the form carries no statement for the case where the filtering "
        f"matches no option (looked for one of {_NO_MATCH_WORDS}) — an empty "
        "box reads as a failure to load"
    )


def test_neither_the_filtering_controls_nor_the_gate_marks_read_as_the_steps_own_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "Neither the filtering controls nor the
    gate marks SHALL be worded so that they read as the step's own gate",
    which the requirement's response list carries as askable.

    `tasks.md` 5.6 adds the other half this surface already carries:
    both controls stay clear of *blocked* and its inflections, the launch
    surfaces having a `Blocked` outcome of their own. This control now
    renders a row of eight gate names beside the control that does carry
    the step's gate, which is the half of that rule it actively strains.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    filters = _gate_filters(form.node)
    assert filters, f"the form renders no control marked {OPTION_GATE_FILTER!r}"

    rows = _require_rows(form, EDIT_OFFERED)
    regions: list[tuple[str, _Node, list[_Node]]] = [
        (f"the {gate!r} filter", control, []) for gate, control in filters.items()
    ]
    for gate in {gate for gate, _ in EDIT_OFFERED.values()}:
        mine = [row for value, row in rows.items() if EDIT_OFFERED[value][0] == gate]
        regions.append(
            (f"the {gate!r} group heading", _gate_group(form, gate, EDIT_OFFERED), mine)
        )

    for what, node, excluded in regions:
        said = _text_outside(node, excluded).lower()
        # SPECIFIED: not worded as the step's own gate.
        offending = [phrase for phrase in _OWN_GATE_PHRASES if phrase in said]
        assert not offending, (
            f"{what} is worded {offending} — it reads as the step's own gate, "
            "which the control beside it is the one to carry"
        )
        # SPECIFIED (the served requirement, restrained by `tasks.md`
        # 5.6): and never as blocking or blocked.
        blocking = [word for word in _BLOCKING_WORDS if word in said]
        assert not blocking, (
            f"{what} is worded {blocking}; this surface already carries the "
            "step's blocking flag and the launch surfaces carry a `Blocked` "
            "outcome"
        )
