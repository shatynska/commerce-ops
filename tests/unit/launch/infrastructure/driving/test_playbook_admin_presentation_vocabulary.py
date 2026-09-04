"""The playbook admin surface's presentation vocabulary
(`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/admin-presentation-vocabulary/specs/playbook-admin/spec.md`
— the three requirements whose scenarios are about the step list and the
authoring surfaces:

- ADDED *A step's actions are presented as one affordance vocabulary* —
  all four scenarios, plus the one sentence of its prose that carries
  past the scenarios ("Every action a step's row offers", not only an
  active step's).
- ADDED *The vocabulary never suppresses a marked control's fault* — its
  one scenario.
- ADDED *A created step is distinguished on the row the list lands on* —
  all four scenarios, plus the requirement prose's narrowing-hides case,
  which has no scenario of its own.

The two remaining requirements of that delta are covered elsewhere:
*The page carries a header…* by
`test_admin_surface_navigation_and_assets.py`, and *The presentation
assets stay behind the admin guard and need no build step* by
`tests/unit/shared/infrastructure/driving/test_admin_assets_route.py`.
The manifest at
`openspec/changes/admin-presentation-vocabulary/test-manifest.md` records
every scenario, every assertion's classification, and the project
questions this file answered by assumption.

**Level.** The page's routes over a step-store double, driven the way a
browser drives them: the tests *discover* the page's own controls and
read the response's markup. This is the harness
`test_playbook_admin_page.py` established and
`test_playbook_admin_create_page.py` and
`test_playbook_admin_fault_attribution.py` extended; it is reproduced
here rather than imported because this directory carries no
`__init__.py` and this project keeps its test files self-contained.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The literal marker tokens `row-action`, `danger` and `just-created`.
  The delta gives them "because they are what a test is derived from",
  so nothing here keys on wording, colour or layout.
- That the destructive action on a step's row is *retire*, and that
  un-retire is not destructive (delta, scenarios 2 and 3).
- That marking a control never changes whether it is offered, and that a
  `human` step carrying an automation brief is refused for the pair and
  marks both halves — the served requirement *A rejected write names the
  fields its faults concern*, which `test_playbook_admin_fault_
  attribution.py` already covers and this file only leans on.
- That the created step's identity reaches the list as a request
  parameter and that a step's row carries `id="step-<identifier>"`
  (`design.md` — Context; `test_playbook_admin_create_page.py`).

INVENTED, each recorded in the manifest with its correction point:

- That "carries the marker `X`" is read as a **class token** on the
  element. `design.md` — *Actions become one row of same-weight
  controls, marked in the response* fixes `class="row-action"` and
  `class="row-action danger"`, but the delta says only "marker".
  Correction point: `_carries`.
- What counts as an **action control**: an `<a>` offering a
  destination, a `<button>`, an `<input type=submit|image>`, or any
  element carrying `role="button"`. A `<select>` that submits itself
  through an `hx-*` attribute would not be swept — an under-reach, not a
  false pass. Correction point: `_action_controls`.
- How a row is located (`id="step-<identifier>"`, else the one `<tr>`
  naming the step) and how one action is told from another (the
  enclosing form's action and hidden fields, plus the control's own
  href, name, value and text). Correction points: `_row_of`,
  `_control_haystack`.
- The page module and its seams, the session cookie, the membership double,
  the create-surface discovery and the valid-create payload — all
  inherited from the sibling admin-page tests, which the implementation
  already satisfies. Correction points: `_install_members`, `_CREATE_HINTS`,
  `_authoring_form_of`, `_valid_values`.

## What this file deliberately does NOT cover

`design.md` — Goals names two components of these requirements as having
no server-observable proxy at all, and `tasks.md` 7.6 and 7.7 make each a
manual verification step:

- the row's action **layout** — that the controls sit on one line, share
  one weight, and that retire is not the most prominent. The markers
  below pass for any stylesheet, including one leaving retire loudest.
- the **legibility** half of the fault requirement — a dim is a computed
  style, and no server response carries one. Only "not displayed" is
  asserted here.

Writing an assertion that pretended to cover either would be worse than
the gap, so neither is written.

## Expected first-run state

The page renders no `row-action`, `danger` or `just-created` marker
today, so every marker test is expected to fail on a wrong value, not at
import: the module, the routes and both surfaces exist.

One exception, deliberate: *A fault on a disabled automation control is
not suppressed* is expected to **pass** on its first run. The marking it
reads already ships (`attribute-faults-to-fields`, archived 2026-08-26)
and nothing dims the automation fieldset yet, so this test is a
regression guard against the dim this change introduces becoming a hide
— not evidence that anything was implemented. It is recorded in the
manifest as such rather than counted as coverage of new behaviour.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 954 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as page_module,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import ALICE, ALICE_NAME, BOHDAN, BOHDAN_NAME, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step

# ---------------------------------------------------------------------------
# The vocabulary's literal tokens — the delta gives these on purpose
# ---------------------------------------------------------------------------

ROW_ACTION: Final = "row-action"
DANGER: Final = "danger"
JUST_CREATED: Final = "just-created"

DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

_CREATE_HINTS: Final = ("new", "create", "add")
_CREATED_PARAM: Final = "created"
_ADDRESS_ID: Final = "step-{identifier}"
_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}
_RETIRED_PARAM: Final = "retired"

#: How the page spells each action, read off the control's own URL,
#: hidden fields, name, value and text. Correction point for the
#: implemented page's action vocabulary.
_MOVE_HINTS: Final = ("move", "reorder", "position", "/order", "up", "down", "top")

_A_HANDLER: Final = "no.such.registered.use-case"

CHRIS_DEPARTED: Final = "prs_01HQ8Z6M4C"
CHRIS_NAME: Final = "Chris Departed"

_HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "sr-only",
    "visually-hidden",
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

#: The step every edit-surface test edits: active, human, non-blocking,
#: and the middle of its gate's three active steps, so it offers the full
#: set of actions — both reorder directions included.
EDITED: Final = "listing.zeta"
TOP_OF_GATE: Final = "hold.listable"
BOTTOM_OF_GATE: Final = "listing.alpha"


# ---------------------------------------------------------------------------
# Step-store double (the shape the sibling admin tests record)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"assignees": (ALICE,), **overrides})


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


def _seeded_store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    """One `active`, blocking step per gate, plus two ordinary `listable`
    steps — so gate `listable` holds three active steps and its middle
    one offers both reorder directions."""
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
        _Record(_step(identifier=BOTTOM_OF_GATE, name="Work of listing.alpha"), 30),
    )
    return _FakeStepStore(records + extra)


def _identifiers(store: _FakeStepStore) -> set[str]:
    return {record.definition.identifier for record in store.records}


def _record_named(store: _FakeStepStore, identifier: str) -> _Record:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _the_one_created(store: _FakeStepStore, before: set[str]) -> _Record:
    created = [r for r in store.records if r.definition.identifier not in before]
    assert len(created) == 1, (
        f"the create flow did not go through the write: {len(created)} new records"
    )
    return created[0]


# ---------------------------------------------------------------------------
# An HTML tree, so a marker can be read off the element that carries it
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
    """A forgiving tree builder: an unclosed tag is closed by whatever
    end tag eventually matches an open ancestor, as the sibling admin
    tests' parsers already do."""

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


def _is_control(node: _Node) -> bool:
    """A named control a member types into or chooses from."""
    name = node.attrs.get("name")
    if not name:
        return False
    if node.tag == "input":
        kind = (node.attrs.get("type") or "text").lower()
        return kind not in ("submit", "image", "button", "reset", "hidden")
    return node.tag in ("select", "textarea")


def _controls_within(node: _Node) -> list[_Node]:
    found = [node] if _is_control(node) else []
    found.extend(child for child in _elements(node) if _is_control(child))
    return found


def _region_of(control: _Node) -> _Node:
    """The largest element containing this control and no other."""
    region = control
    walker = control.parent
    while walker is not None and walker.tag != "#document":
        if len(_controls_within(walker)) != 1:
            break
        region = walker
        walker = walker.parent
    return region


def _texts(node: _Node) -> list[_Text]:
    """Every text fragment in this subtree, never descending into a
    control: a `<select>`'s option labels and a `<textarea>`'s contents
    are submitted values, not something the surface says."""
    found: list[_Text] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child)
        elif not _is_control(child):
            found.extend(_texts(child))
    return found


def _all_text(node: _Node) -> str:
    """Every text fragment in this subtree, controls included — used only
    to recognise which step a region is about."""
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
    """Whether an element carries a vocabulary marker.

    INVENTED: read as a class token, per `design.md` — *Actions become
    one row of same-weight controls, marked in the response*, which
    fixes `class="row-action"` and `class="row-action danger"`. The
    delta itself says only "marker". Correction point for a page that
    marks some other way.
    """
    return marker in _classes(node)


def _element_hidden(node: _Node) -> bool:
    attrs = node.attrs
    if "hidden" in attrs and attrs["hidden"].lower() != "false":
        return True
    if attrs.get("aria-hidden", "").lower() == "true":
        return True
    style = attrs.get("style", "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if any(name in _HIDDEN_CLASSES for name in attrs.get("class", "").lower().split()):
        return True
    return node.tag == "input" and attrs.get("type", "").lower() == "hidden"


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


def _nearest(node: _Node, tag: str) -> _Node | None:
    return next((a for a in _ancestors(node) if a.tag == tag), None)


# ---------------------------------------------------------------------------
# Action controls: the affordances a row offers, and how one is told from
# another
# ---------------------------------------------------------------------------


def _in_action_cell(node: _Node) -> bool:
    """Whether `node` sits in one of the row's *action* cells — `reorder`
    or `actions` — rather than one of its plain content cells (identity,
    name, assignees, discipline).

    Correction point, added after `add-admin-breadcrumb-navigation`: a
    step's name is now itself a plain `<a href>` to the same edit page the
    row's own `edit` action reaches (`playbook-admin`'s ADDED requirement
    *A step's name in the table opens its edit page*), so a plain `<a
    href>` is no longer sufficient on its own to recognise a *row action*
    — this vocabulary's own concern, and explicitly not one that
    requirement's own text changes ("nothing here changes which actions a
    row offers"). The name link is content, addressed at what the row
    names rather than what it does to it, and the two cell classes
    `step_cells`/`row_actions` already write are what tells them apart
    structurally rather than by wording.
    """
    cell = _nearest(node, "td")
    return cell is not None and bool(_classes(cell) & {"reorder", "actions"})


def _is_action_control(node: _Node) -> bool:
    """An affordance a member clicks *to act on the row*, as opposed to
    one that merely navigates to read or edit what the row names.

    INVENTED — see this file's docstring. A `<select>` submitting itself
    through an `hx-*` attribute is not swept; that is an under-reach, not
    a false pass. Correction point for the implemented page's controls.
    """
    if node.attrs.get("role", "").lower() == "button":
        return True
    if node.tag == "button":
        return True
    if node.tag == "input":
        return (node.attrs.get("type") or "text").lower() in ("submit", "image")
    if node.tag == "a":
        if any(verb in node.attrs for verb in _HX_VERBS):
            return True
        return "href" in node.attrs and _in_action_cell(node)
    return False


def _action_controls(node: _Node) -> list[_Node]:
    found = [node] if _is_action_control(node) else []
    found.extend(child for child in _elements(node) if _is_action_control(child))
    return found


def _links(node: _Node) -> list[_Node]:
    return [
        child for child in _elements(node) if child.tag == "a" and "href" in child.attrs
    ]


def _control_haystack(node: _Node) -> str:
    """Everything naming what this control does: its own destination,
    label and text, plus its enclosing form's action and hidden fields.

    A `<select>`'s option labels are excluded, so a status control
    offering a `retired` option is not mistaken for the retire action.
    """
    parts: list[str] = [
        node.attrs.get(key, "")
        for key in ("href", "formaction", "name", "value", "aria-label", "title")
    ]
    parts.extend(node.attrs.get(verb, "") for verb in _HX_VERBS)
    parts.append(_flat(" ".join(t.text for t in _texts(node))))
    form = _nearest(node, "form")
    if form is not None:
        parts.append(form.attrs.get("action", ""))
        parts.extend(form.attrs.get(verb, "") for verb in _HX_VERBS)
        for element in _elements(form):
            if element.tag == "input" and element.attrs.get("type", "").lower() == (
                "hidden"
            ):
                parts.append(element.attrs.get("name", ""))
                parts.append(element.attrs.get("value", ""))
    return " ".join(part for part in parts if part).lower()


def _matching(controls: list[_Node], hints: tuple[str, ...]) -> list[_Node]:
    return [c for c in controls if any(hint in _control_haystack(c) for hint in hints)]


def _row_of(root: _Node, identifier: str) -> _Node:
    """The step's own row.

    Preferred by the addressing `id` the list already renders
    (`design.md` — Context); else the one `<tr>` naming the step.
    """
    wanted = _ADDRESS_ID.format(identifier=identifier)
    for element in _elements(root):
        if element.attrs.get("id") == wanted:
            return element
    rows = [
        element
        for element in _elements(root)
        if element.tag == "tr" and identifier in _all_text(element)
    ]
    if len(rows) == 1:
        return rows[0]
    pytest.fail(
        f"the list renders no row for {identifier!r} carrying id {wanted!r}, and "
        f"{len(rows)} table rows name it — correct `_row_of` to the "
        "implemented page"
    )


def _distinguished(root: _Node) -> list[_Node]:
    return [element for element in _elements(root) if _carries(element, JUST_CREATED)]


# ---------------------------------------------------------------------------
# Submittable controls, and each named input's rendered state
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


@dataclass(frozen=True)
class _State:
    name: str
    tag: str
    kind: str
    value: str
    hidden: bool
    disabled: bool
    options: tuple[tuple[str, str], ...] = ()


def _options_of(node: _Node) -> tuple[tuple[str, str], ...]:
    return tuple(
        (option.attrs.get("value", ""), " ".join(t.text for t in _texts(option)))
        for option in _elements(node)
        if option.tag == "option"
    )


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


def _states(html: str) -> dict[str, _State]:
    found: dict[str, _State] = {}
    for element in _elements(_tree(html)):
        name = element.attrs.get("name")
        if not name or element.tag not in ("input", "select", "textarea"):
            continue
        kind = (element.attrs.get("type") or element.tag).lower()
        if element.tag == "input" and kind in ("submit", "image", "button", "reset"):
            continue
        hidden = _inherited(element, _element_hidden)
        disabled = _inherited(element, _element_disabled)
        if element.tag == "select":
            found[name] = _State(
                name,
                "select",
                "select",
                _selected_of(element),
                hidden,
                disabled,
                _options_of(element),
            )
        elif element.tag == "textarea":
            found[name] = _State(
                name,
                "textarea",
                "textarea",
                " ".join(t.text for t in _texts(element)),
                hidden,
                disabled,
            )
        else:
            default = "on" if kind == "checkbox" else ""
            found[name] = _State(
                name,
                "input",
                kind,
                element.attrs.get("value", default),
                hidden,
                disabled,
            )
    return found


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


def _field_name(
    names: dict[str, Any], fragment: str, *, excluding: tuple[str, ...] = ()
) -> str:
    matches = [
        name
        for name in names
        if fragment in name and not any(word in name for word in excluding)
    ]
    if len(matches) != 1:
        pytest.fail(
            f"{len(matches)} fields mention {fragment!r} (excluding {excluding}): "
            f"{matches} among {sorted(names)} — correct this file's "
            "field-addressing to the implemented form"
        )
    return matches[0]


def _fill(fields: dict[str, str], **by_substring: str) -> dict[str, str]:
    filled = dict(fields)
    for fragment, value in by_substring.items():
        matches = [name for name in filled if fragment in name]
        if not matches:
            pytest.fail(
                f"the form offers no field whose name contains {fragment!r} "
                f"(fields: {sorted(filled)}) — correct this file's "
                "field-addressing to the implemented form"
            )
        for name in matches:
            filled[name] = value
    return filled


def _without(values: dict[str, str], fragment: str) -> dict[str, str]:
    remaining = {name: value for name, value in values.items() if fragment not in name}
    if len(remaining) == len(values):
        pytest.fail(
            f"the form carries no field mentioning {fragment!r} to drop "
            f"(fields: {sorted(values)})"
        )
    return remaining


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


_fake_verify = fake_verify(PRINCIPAL)


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


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    _install_members(monkeypatch)
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
    url: str | None = None,
    data: dict[str, Any] | None = None,
    follow_redirects: bool = True,
) -> Any:
    method = control.method.upper()
    target = _resolve((control.url if url is None else url).split("#")[0])
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


def _retired_view(client: TestClient, listed: str) -> str:
    """The view revealing retired steps, reached through the page's own
    control where it offers one, else through the invented parameter."""
    default_view = _get_page(client)
    control = _first_control(default_view, contains=("retired",))
    if control is not None:
        response = _issue(client, control)
        if response.status_code == 200 and listed in response.text:
            return str(response.text)
    return _get_page(client, params={_RETIRED_PARAM: "1"})


def _status_value(status: StepStatus) -> str:
    value = getattr(status, "value", None)
    return str(value) if isinstance(value, str) else status.name.lower()


def _kind_value(kind: StepKind) -> str:
    value = getattr(kind, "value", None)
    return str(value) if isinstance(value, str) else kind.name.lower()


# ---------------------------------------------------------------------------
# The two authoring surfaces
# ---------------------------------------------------------------------------


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


@dataclass(frozen=True)
class _Surface:
    """One authoring surface, as rendered clean and ready to submit."""

    html: str
    form: _Control

    @property
    def states(self) -> dict[str, _State]:
        return _states(self.html)


def _open_edit(client: TestClient, step_id: str = EDITED) -> _Surface:
    control = _require_control(_get_page(client), contains=(step_id, "edit"))
    response = _issue(client, control)
    assert response.status_code == 200, response.text
    body = str(response.text)
    form = _authoring_form_of(body)
    if form is None:
        pytest.fail(
            f"following the edit control for {step_id!r} produced no authoring "
            "form carrying the step's fields — correct `_open_edit` to how the "
            "implemented page offers a step's edit form"
        )
    return _Surface(body, form)


def _open_create(client: TestClient, list_html: str | None = None) -> _Surface:
    page = _get_page(client) if list_html is None else list_html
    candidates = [
        control
        for control in _controls(page)
        if control.method.upper() == "GET"
        and not control.inert
        and not control.url.startswith(("#", "http://", "https://", "mailto:"))
        and any(hint in control.url.lower() for hint in _CREATE_HINTS)
    ]
    for control in candidates:
        response = _issue(client, control)
        if response.status_code != 200:
            continue
        form = _authoring_form_of(response.text, require_discipline=True)
        if form is not None:
            return _Surface(str(response.text), form)
    pytest.fail(
        "no control on the list led to a create surface carrying the "
        f"authorable form (candidates tried: {[c.url for c in candidates]}) — "
        "correct `_CREATE_HINTS` and `_authoring_form_of` to the implemented page"
    )


def _anchor_kind_field(states: dict[str, _State]) -> _State:
    for name, state in states.items():
        if "anchor" in name and "kind" in name:
            return state
    pytest.fail(
        f"the surface renders no anchor kind control (fields: {sorted(states)}) "
        "— correct `_anchor_kind_field` to the implemented form"
    )


def _anchor_kind_value(states: dict[str, _State], hint: str) -> str:
    selector = _anchor_kind_field(states)
    for value, label in selector.options:
        if hint in value.lower() or hint in label.lower():
            return value
    pytest.fail(
        f"the anchor kind control offers nothing mentioning {hint!r} "
        f"(options: {selector.options}) — correct this file's anchor kinds to "
        "the implemented ones"
    )


def _valid_values(
    surface: _Surface,
    *,
    name: str,
    gate: str = "listable",
    status: StepStatus = StepStatus.ACTIVE,
) -> dict[str, str]:
    """A payload the authoring write accepts: a `human`, non-blocking
    step naming an active assignee, on an offset anchor, carrying neither
    an automation brief nor a handler."""
    states = surface.states
    values = _fill(
        surface.form.data(),
        name=name,
        gate=gate,
        status=_status_value(status),
        assignee=ALICE,
        anchor_days="-7",
    )
    values[_field_name(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, "offset")
    values[_field_name(values, "scope")] = Scope.PRODUCT.value
    values[_field_name(values, "hazard")] = Hazard.NONE.value
    for key in list(values):
        if "handler" in key:
            values[key] = ""
    if any("blocking" in key for key in values):
        values = _without(values, "blocking")
    return values


def _submit(client: TestClient, surface: _Surface, values: dict[str, str]) -> str:
    response = _issue(client, surface.form, data=values, follow_redirects=False)
    assert response.status_code < 500, response.text
    body = str(response.text)
    if _authoring_form_of(body) is None:
        pytest.fail(
            "the rejected write did not re-render an authoring form, so there "
            f"is no field marking to read: {body[:2000]}"
        )
    return body


def _land(client: TestClient, response: Any) -> str:
    """The list a landed create lands on."""
    assert response.status_code in (302, 303, 307, 308), (
        "a create that lands SHALL return to the step list, so the create "
        f"POST answers a redirect — it answered {response.status_code}: "
        f"{response.text[:1500]}"
    )
    followed = client.get(_resolve(str(response.headers["location"])))
    assert followed.status_code == 200, followed.text
    return str(followed.text)


def _create(
    client: TestClient,
    store: _FakeStepStore,
    *,
    name: str,
    gate: str = "listable",
    status: StepStatus = StepStatus.ACTIVE,
) -> tuple[str, str]:
    """Author one step through the create surface; answer its generated
    identifier and the list it lands on."""
    before = _identifiers(store)
    surface = _open_create(client)
    values = _valid_values(surface, name=name, gate=gate, status=status)
    response = _issue(client, surface.form, data=values, follow_redirects=False)
    listed = _land(client, response)
    return _the_one_created(store, before).definition.identifier, listed


# ---------------------------------------------------------------------------
# ADDED requirement: A step's actions are presented as one affordance
# vocabulary
# ---------------------------------------------------------------------------


def test_a_rows_actions_share_one_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A row's actions share one vocabulary.

    WHEN an active step's row that can move is rendered
    THEN each move control carries `row-action`
    AND no action is rendered as an unmarked link among marked controls.

    `listing.zeta` is the middle of its gate's three active steps, so its
    row offers both reorder directions — the row's only actions now
    (`move-step-actions-into-step-pages`): editing, changing status,
    retiring and un-retiring all moved to the step's own edit page.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    row = _row_of(_tree(_get_page(client)), EDITED)
    controls = _action_controls(row)

    # DERIVED vacuity guard: a row rendering no control at all would
    # satisfy the sweep below while offering nothing to speak a
    # vocabulary about.
    assert controls, (
        f"the row for {EDITED!r} offers no action control at all, so the "
        "sweep below asserts nothing — correct `_is_action_control` to the "
        "implemented page"
    )
    # SPECIFIED: every action control carries `row-action`.
    unmarked = [c for c in controls if not _carries(c, ROW_ACTION)]
    assert unmarked == [], (
        f"{len(unmarked)} of {len(controls)} action controls on the row for "
        f"{EDITED!r} carry no {ROW_ACTION!r} marker: "
        f"{[(c.tag, _control_haystack(c)[:60]) for c in unmarked]}"
    )
    # SPECIFIED: and no action is rendered as an unmarked link among
    # marked controls — the `edit` link is the one the delta is about.
    # Scoped to the row's action cells, the same distinction
    # `_is_action_control` now draws: the step's own name is a plain
    # content link outside them, added by `add-admin-breadcrumb-navigation`
    # and not itself a row action this vocabulary governs.
    unmarked_links = [
        a for a in _links(row) if _in_action_cell(a) and not _carries(a, ROW_ACTION)
    ]
    assert unmarked_links == [], (
        "the row renders a link among its marked controls that carries no "
        f"{ROW_ACTION!r} marker: "
        f"{[a.attrs.get('href', '') for a in unmarked_links]}"
    )


def test_a_non_active_steps_row_speaks_the_same_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The requirement's prose, which carries past its scenarios: "Every
    action a step's row offers … SHALL be presented as a control of the
    same weight as its siblings" — a step's row, not only an active
    step's.

    `page.html` renders a step row at two sites — the served table and
    the one for steps that are not served at this gate (`tasks.md` 4.2) —
    and a draft's row is the second site. Without this, that second site
    could keep offering an action the served table's row no longer does,
    while every scenario above still passed.

    A draft holds no slot, so it was never movable there either — the
    second site's rows carry no action control at all now
    (`move-step-actions-into-step-pages`), the same as a retired step's
    row (`A retired step's only action speaks the same vocabulary`).

    SPECIFIED by the requirement's prose; it carries no scenario of its
    own, which is why it is a test of its own rather than a clause folded
    into one.
    """
    draft = _Record(
        _step(
            identifier="listing.drafted",
            name="Work written down before it is ready",
            status=StepStatus.DRAFT,
        ),
        display_order=40,
    )
    store = _seeded_store(extra=(draft,))
    client = _signed_client(monkeypatch, store)

    row = _row_of(_tree(_get_page(client)), "listing.drafted")
    controls = _action_controls(row)

    assert controls == [], (
        f"the draft's row offers {len(controls)} action control(s): "
        f"{[(c.tag, _control_haystack(c)[:60]) for c in controls]} — the "
        "second row site kept an action the served table's row no longer "
        "offers"
    )


def test_the_destructive_action_is_distinguished_not_amplified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The destructive action is distinguished, not amplified.

    WHEN any step's row is rendered, active or retired
    THEN no control on that row carries `danger`.

    Retiring, the row's one destructive action, moved to the step's edit
    page (`move-step-actions-into-step-pages`) — distinguishing it on
    the row is no longer a question the row's own markup can answer,
    since it no longer carries the control at all.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    row = _row_of(_tree(_get_page(client)), EDITED)
    marked_danger = [c for c in _action_controls(row) if _carries(c, DANGER)]

    assert marked_danger == [], (
        f"{len(marked_danger)} controls on {EDITED!r}'s row carry {DANGER!r}: "
        f"{[(c.tag, _control_haystack(c)[:60]) for c in marked_danger]} — "
        "retiring is no longer a row action, so nothing on the row should "
        "claim the destructive marker"
    )


def test_a_retired_steps_only_action_speaks_the_same_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A retired step's only action speaks the same vocabulary.

    WHEN a retired step's row is rendered from the view that reveals
    retired steps
    THEN it carries no control marked `row-action` at all — retired
    steps hold no slot to reorder, and every other action moved to the
    step's edit page (`move-step-actions-into-step-pages`), so there is
    no longer an "only action" for the row to offer, only the marker's
    continued absence.
    """
    retired = _Record(
        _step(
            identifier="listing.retired-work",
            name="Retired work",
            status=StepStatus.RETIRED,
        ),
        display_order=40,
    )
    retired.retired_by = "olena"
    retired.retired_on = "2026-08-01"
    store = _seeded_store(extra=(retired,))
    client = _signed_client(monkeypatch, store)

    revealed = _retired_view(client, "listing.retired-work")
    assert "listing.retired-work" in revealed, (
        "the view revealing retired steps does not render the retired step, "
        "so there is no row to read a vocabulary off"
    )
    row = _row_of(_tree(revealed), "listing.retired-work")
    controls = _action_controls(row)

    assert controls == [], (
        f"a retired step's row offers {len(controls)} action control(s): "
        f"{[(c.tag, _control_haystack(c)[:60]) for c in controls]} — retired "
        "steps hold no slot to reorder, and every other action moved to "
        "the step's edit page"
    )


def test_the_vocabulary_does_not_change_which_actions_are_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The vocabulary does not change which actions are
    offered.

    WHEN a step that cannot be moved further up is rendered
    THEN its move control is still rendered inert, exactly as before
    AND carries `row-action` like every other action.

    "Exactly as before" is read differentially, since no test can render
    the page as it stood before the change: the head-of-gate row offers
    the *same number* of move controls as a row in the middle of the same
    gate, and the difference between them is that one of the head row's
    is inert while none of the middle row's is. That is the state the
    served suite already relies on — "both ends of the visible list being
    inert" (`test_playbook_admin_filtered_moves.py`).
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    root = _tree(_get_page(client))

    head = _row_of(root, TOP_OF_GATE)
    middle = _row_of(root, EDITED)
    head_moves = _matching(_action_controls(head), _MOVE_HINTS)
    middle_moves = _matching(_action_controls(middle), _MOVE_HINTS)

    # SPECIFIED: the move control is still *rendered* — the vocabulary
    # removed no action.
    assert head_moves, (
        f"the head-of-gate row for {TOP_OF_GATE!r} renders no move control at "
        "all, so an action it offered has gone"
    )
    assert len(head_moves) == len(middle_moves), (
        f"the head-of-gate row offers {len(head_moves)} move controls where "
        f"the middle row offers {len(middle_moves)} — which actions a row "
        "offers changed"
    )
    # SPECIFIED: rendered *inert*.
    inert_at_head = [c for c in head_moves if _inherited(c, _element_disabled)]
    assert inert_at_head, (
        f"no move control on {TOP_OF_GATE!r}'s row is rendered inert, though "
        "it cannot be moved further up"
    )
    # DERIVED guard: the middle row's moves are live, so the inertness
    # above is about the head of the gate and not about a page whose
    # reorder controls are all dead.
    assert not [c for c in middle_moves if _inherited(c, _element_disabled)], (
        f"the middle row for {EDITED!r} renders inert move controls too, so "
        "the assertion above says nothing about the head of the gate"
    )
    # SPECIFIED: and carries `row-action` like every other action.
    unmarked = [c for c in head_moves if not _carries(c, ROW_ACTION)]
    assert unmarked == [], (
        f"{len(unmarked)} inert move controls carry no {ROW_ACTION!r} marker: "
        f"{[(c.tag, _control_haystack(c)[:60]) for c in unmarked]} — an "
        "action a row cannot take is still an action it offers"
    )


# ---------------------------------------------------------------------------
# ADDED requirement: The vocabulary never suppresses a marked control's
# fault
# ---------------------------------------------------------------------------


def test_a_fault_on_a_disabled_automation_control_is_not_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A fault on a disabled automation control is not
    suppressed.

    WHEN a `human` step carrying a handler is rejected for the pair
    THEN the mark carrying that fault is rendered
    AND the handler control is still disabled
    AND neither that mark, nor the fieldset holding it, is rendered as
    not displayed.

    The mark is located differentially rather than by class: it is the
    text the rejection renders in the handler control's own region that a
    clean render of the same region does not. That is the reading
    `test_playbook_admin_fault_attribution.py` established, and it
    survives the fault being reworded.

    The requirement's other half — that the mark is not rendered *less
    legible* than the surface's ordinary text — is a computed style no
    response carries. It is `tasks.md` 7.6's manual check and is
    deliberately not asserted here.

    This test is a regression guard and is expected to PASS on its first
    run: the marking already ships and nothing dims the fieldset yet. It
    is recorded in the manifest as a guard rather than as coverage of new
    behaviour.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)

    values = _valid_values(surface, name="Work this step asks for")
    values[_field_name(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values = _fill(values, handler=_A_HANDLER)
    rejected = _submit(client, surface, values)

    handler_field = _field_name(values, "handler")
    clean_region = _region_of(_control_named(_tree(surface.html), handler_field))
    rejected_root = _tree(rejected)
    handler = _control_named(rejected_root, handler_field)
    region = _region_of(handler)

    already = {fragment.text for fragment in _texts(clean_region)}
    fresh = [fragment for fragment in _texts(region) if fragment.text not in already]

    # SPECIFIED: the mark carrying that fault is rendered.
    assert fresh, (
        "the rejection renders nothing new in the handler's own region, so "
        "the fault it was marked with is not there to suppress — the served "
        "requirement *A rejected write names the fields its faults concern* "
        "is what this leans on"
    )
    # SPECIFIED: the handler control is still disabled — the treatment
    # changed no control's offer.
    assert _inherited(handler, _element_disabled), (
        "the handler is no longer rendered disabled on a `human` step, so "
        "the presentation changed which controls are offered"
    )
    # SPECIFIED: neither that mark, nor the fieldset holding it, is
    # rendered as not displayed.
    marks = _elements_carrying(region, {f.text for f in fresh})
    assert marks, (
        "the fault text is rendered by no element of its own, so the mark "
        f"cannot be located: {[f.text for f in fresh]}"
    )
    for mark in marks:
        assert not _inherited(mark, _element_hidden), (
            f"the mark carrying {_flat(' '.join(t.text for t in _texts(mark)))!r} "
            "is rendered as not displayed, or sits inside something that is — "
            "dimming the automation fieldset became hiding it, which removes a "
            "fault the surface is required to render"
        )
        fieldset = _nearest(mark, "fieldset")
        if fieldset is not None:
            assert not _element_hidden(fieldset), (
                "the fieldset holding the fault is rendered as not displayed"
            )
    assert store.saves == []


def _control_named(root: _Node, name: str) -> _Node:
    for element in _elements(root):
        if _is_control(element) and element.attrs.get("name") == name:
            return element
    pytest.fail(f"the surface renders no control named {name!r}")


def _elements_carrying(region: _Node, wanted: set[str]) -> list[_Node]:
    """Every element in the region whose own direct text is one of
    `wanted` — the innermost thing rendering the fault."""
    return [
        element
        for element in _elements(region)
        if any(
            isinstance(child, _Text) and child.text in wanted
            for child in element.children
        )
    ]


# ---------------------------------------------------------------------------
# ADDED requirement: A created step is distinguished on the row the list
# lands on
# ---------------------------------------------------------------------------


def test_the_created_steps_row_is_distinguished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The created step's row is distinguished.

    WHEN a create lands and the list is rendered naming the created step,
    with no narrowing hiding it
    THEN that step's row carries `just-created`
    AND no other row carries it.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    identifier, listed = _create(
        client, store, name="Work authored from the create surface"
    )

    root = _tree(listed)
    row = _row_of(root, identifier)
    distinguished = _distinguished(root)

    # SPECIFIED: that step's row carries `just-created`.
    assert _carries(row, JUST_CREATED), (
        f"the created step {identifier!r} is addressed but not distinguished: "
        f"its row carries {sorted(_classes(row))}, so an admin lands somewhere "
        "in the table with nothing saying which row was the point"
    )
    # SPECIFIED: and no other row carries it.
    assert distinguished == [row], (
        f"{len(distinguished)} elements carry {JUST_CREATED!r} where exactly "
        "one row should: "
        f"{[(e.tag, e.attrs.get('id', '')) for e in distinguished]}"
    )


def test_a_step_created_as_a_draft_is_distinguished_where_it_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step created as a draft is distinguished where it
    renders.

    WHEN a step is created as a `draft` and the list is rendered naming
    it, with no narrowing hiding it
    THEN its row among the non-active steps carries `just-created`
    AND no row among the served steps carries it.

    This is the second of `page.html`'s two row sites (`tasks.md` 4.5): a
    draft renders in the non-active table, so a marker applied at the
    served site alone would pass the scenario above and fail this one.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    identifier, listed = _create(
        client,
        store,
        name="Work written down before it is ready",
        status=StepStatus.DRAFT,
    )
    # DERIVED guard: the create really landed as a draft, so the row read
    # below is the non-active site rather than the served one.
    assert _record_named(store, identifier).definition.status is StepStatus.DRAFT

    root = _tree(listed)
    row = _row_of(root, identifier)
    distinguished = _distinguished(root)

    # SPECIFIED: its row among the non-active steps carries
    # `just-created`.
    assert _carries(row, JUST_CREATED), (
        f"the created draft {identifier!r} renders undistinguished among the "
        f"non-active steps (classes: {sorted(_classes(row))})"
    )
    # SPECIFIED: and no row among the served steps carries it — which,
    # since exactly one row is the created one, is the same count.
    assert distinguished == [row], (
        f"{len(distinguished)} elements carry {JUST_CREATED!r} where exactly "
        "the created draft's row should: "
        f"{[(e.tag, e.attrs.get('id', '')) for e in distinguished]}"
    )


def test_a_list_not_naming_a_created_step_distinguishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A list not naming a created step distinguishes nothing.

    WHEN the list is rendered without naming a created step
    THEN no row carries `just-created`.

    A row highlighted on a page that is not the result of a create would
    be a claim about a step nobody just created.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    plain = _tree(_get_page(client))
    narrowed = _tree(_get_page(client, params={_FILTER_PARAMS["gate"]: "listable"}))

    # SPECIFIED: no row carries it on a plain list …
    assert _distinguished(plain) == [], (
        "a list rendered without naming a created step distinguishes "
        f"{len(_distinguished(plain))} rows"
    )
    # … nor on a narrowed one, which is the same list under a filter.
    assert _distinguished(narrowed) == [], (
        "a narrowed list rendered without naming a created step "
        f"distinguishes {len(_distinguished(narrowed))} rows"
    )


def test_a_named_step_the_list_does_not_render_distinguishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A named step the list does not render distinguishes
    nothing.

    WHEN the list is rendered naming a created step that its own read
    does not return
    THEN the list renders as it would without that name
    AND no row carries `just-created`.

    "Renders as it would" is read the way the served suite already reads
    it for *A step named as created but not there is ignored*: the same
    steps render, step by step.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    absent = "mg.listing.no-such-step-was-ever-created"

    plain = _get_page(client)
    named = _get_page(client, params={_CREATED_PARAM: absent})

    # SPECIFIED: the list renders as it would without that name.
    for identifier in _identifiers(store):
        assert (identifier in named) == (identifier in plain), (
            f"naming an absent created step changed whether {identifier} renders"
        )
    assert absent not in named, "the list names a step its own read never returned"
    # SPECIFIED: and no row carries `just-created`.
    distinguished = _distinguished(_tree(named))
    assert distinguished == [], (
        f"{len(distinguished)} rows are distinguished for a created step the "
        "list does not render, which claims a step nobody can see was just "
        "created"
    )


def test_a_created_step_the_narrowing_hides_distinguishes_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The requirement's prose, which names a case its scenarios do not:
    "names one it does not render — a step the narrowing hides … — no row
    SHALL be distinguished."

    The served requirement already fixes what this view looks like: the
    list names the created step and offers to clear the narrowing (*A
    create the narrowing would hide is not left looking lost*). The
    distinction must not outrun the addressing, so naming the step in a
    notice is not distinguishing a row.

    SPECIFIED by the requirement's prose; it carries no scenario of its
    own.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    listed = _get_page(
        client,
        params={
            _FILTER_PARAMS["gate"]: "order",
            _CREATED_PARAM: EDITED,
        },
    )

    # DERIVED guard: the narrowing really hides the named step, so the
    # absence below is about the rule and not about an unfiltered page.
    root = _tree(listed)
    assert not [
        element
        for element in _elements(root)
        if element.attrs.get("id") == _ADDRESS_ID.format(identifier=EDITED)
    ], (
        f"the gate filter does not hide {EDITED!r}'s row, so this test does "
        "not reach the case it was written for"
    )
    # SPECIFIED: no row is distinguished.
    distinguished = _distinguished(root)
    assert distinguished == [], (
        f"{len(distinguished)} rows are distinguished under a narrowing that "
        "hides the named step — the distinction outran the addressing"
    )
