"""The step form's two multi-valued controls — assignees and the steps a
step waits on (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/pick-steps-and-people-by-checkbox/specs/playbook-admin/spec.md`
— the MODIFIED requirement *The step form carries every authorable
field*, and only the obligations that requirement's own paragraph
beginning "What a response can be asked of these two controls" assigns
to a **response**, plus the two scenarios of that requirement whose
locators this change moves (`tasks.md` 7.1, 7.2).

The filtering of the dependency control is the ADDED requirement's own
subject and is covered in
`test_playbook_admin_dependency_option_filtering.py` in this directory.
The stylesheet-scoping clause of this same requirement is covered in
`test_playbook_admin_picker_vocabulary_scope.py`, which needs the
sibling admin surfaces mounted and so cannot live here.

Every scenario of both requirements is accounted for — covered here, in
one of those two files, or recorded as confirmed by direct inspection of
the rendered page — in the manifest at
`openspec/changes/pick-steps-and-people-by-checkbox/test-manifest.md`.

## What this file deliberately does NOT assert

The requirement's own split is the map. These four are **behaviours and
computed style**, which the requirement designates for direct inspection
of the rendered page:

- that each control's values can be chosen and cleared without a
  modifier key,
- that clearing from `chosen-set` actually clears,
- that a cleared value actually stops being shown,
- that no filtering removes a fault mark.

This repository has three Python test tiers (`AGENTS.md` — *Testing
Strategy*) and nothing that drives a browser; `tasks.md` 7.0 forbids
growing one for this change. So none of the four is asserted here, and
none is asserted through a proxy pretending to be it. What *is* asserted
of the third is the response-level half the requirement names: that the
served stylesheet carries a rule keyed on a control's checked state
reaching the `chosen-set` region, which is as far as a response reaches
toward the toggle trap (`tasks.md` 7.3).

## Level

The playbook-admin router over a step-store double and a membership double,
mounted beside the shared asset router because one obligation is stated
about the **served stylesheet**. The harness is the one
`test_playbook_admin_page.py` established and the sibling admin tests
extend, reproduced here rather than imported: this project keeps its
test files self-contained.

## Fixed by the artifacts

- The literal markers `chosen-set` and `hidden-chosen-notice`, given by
  the delta itself.
- That each control renders a control per value, that `chosen-set` names
  the field it belongs to, that a chip element exists for each chosen
  value, and that the stylesheet carries a checked-state rule reaching
  that region — all four named by the requirement as response-askable.
- That an emptied control still submits its key, and that a submission
  carrying no key is read as the empty set. `design.md` — *An emptied
  control must still submit its key* fixes the mechanism as a hidden
  always-submitted value, and `tasks.md` 3.1-3.4 restates it.
- The exclusions, the identifier-and-name labelling and the grouping of
  the dependency control's options, carried over unchanged from the
  served spec (`tasks.md` 7.2).

## INVENTED, with correction points

- A marker is read as a **class token**, or as the value of any `data-*`
  attribute, or as an element's `id`. The class-token reading is the one
  `test_playbook_admin_write_failure_notice.py` established for
  `write-failure-notice`; the other two are admitted so that a page
  marking another way corrects this file rather than the requirement.
  Correction point: `_carries`.
- That a "control per value" is an `<input type="checkbox">` carrying
  the field's name. No artifact fixes the element — a checkbox is the
  only per-value control that toggles without a modifier, which is what
  the requirement actually asks for. Correction point:
  `_VALUE_INPUT_TYPES`.
- That an option's **row** is the `<label>` bound to that value's input
  and sitting outside every `chosen-set` region, and that a **chip** is
  an element inside a `chosen-set` region naming the value. Correction
  points: `_option_rows`, `_chips_of`.
- That `chosen-set` "names its field" by carrying the field's own
  submitted name, or a word of that field, in an attribute or in its
  text. Correction point: `_NAMES_OF_FIELD`.
- That a fault mark is recognised by a `data-*` attribute whose value is
  the field's name, by an `aria-describedby`/`aria-errormessage`/
  `aria-details` reference from one of the field's inputs, or by a
  marking attribute on one of them — the reading
  `test_playbook_admin_start_fields.py` records in full. Correction
  point: `_fault_texts`.
- The page seams (`steps`, the membership, `verify_admin_session`), the
  session cookie and the edit/create control vocabulary, inherited from
  the sibling admin-page tests.

## Expected first-run state

**The change is not implemented.** Both controls ship today as
`<select multiple>`, so every test in this file executes against a real
rendering and fails on the *value produced* rather than on an absent
target: there is no checkbox per value, no `chosen-set` region, no chip
and no hidden always-submitted key. That is the strongest of the four
failure states and it establishes that these assertions discriminate.

Two exceptions, recorded so a pass is not misread as coverage:

- `test_the_dependency_control_is_grouped_and_self_excluding` and
  `test_assignees_are_chosen_from_the_members_active_members` assert what
  is offered, not how it is drawn. They still fail today, because they
  locate the offered set through the per-value inputs this change
  introduces — which is the relocation `tasks.md` 7.1 and 7.2 ask for.
  What they assert about *what* is offered is unchanged from the served
  spec.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1660 passed, 0 failed — at the worktree root
on 2026-08-29, commit `81e042a`, tree clean but for an untracked
`.claude/worktrees/`.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import ModuleType
from typing import Any, Final
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain.launch_playbook import (
    StepDefinition,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import ALICE, ALICE_NAME, BOHDAN, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member

page_module: ModuleType = importlib.import_module(
    "commerce_ops.launch.infrastructure.driving.playbook_admin"
)

_ASSETS_MODULE_NAME: Final = "commerce_ops.shared.infrastructure.driving.admin_assets"

# ---------------------------------------------------------------------------
# The delta's own literal markers
# ---------------------------------------------------------------------------

CHOSEN_SET: Final = "chosen-set"

#: SPECIFIED. The two fields the requirement calls "these two controls".
ASSIGNEES: Final = "assignees"
AFTER_STEPS: Final = "after_steps"

#: INVENTED. Words either field may be named by in a region's markup —
#: its own submitted name first, then the words the surface may use for
#: it in prose.
_NAMES_OF_FIELD: Final[dict[str, tuple[str, ...]]] = {
    ASSIGNEES: ("assignees", "assignee", "assigned"),
    AFTER_STEPS: ("after_steps", "after", "waits on", "waits-on", "depend"),
}

#: INVENTED. The element a "control per value" is taken to be.
_VALUE_INPUT_TYPES: Final = ("checkbox",)

LISTING: Final = Discipline("listing")
INVENTORY: Final = Discipline("inventory")

BOHDAN_NAME: Final = "Bohdan Builder"
CHRIS: Final = "prs_01HQ8Z6M4C"
CHRIS_NAME: Final = "Chris Departed"
NOT_A_MEMBER: Final = "prs_01HQ8Z6NOPE"

EDITED: Final = "listing.the-step-being-edited"
EDITED_NAME: Final = "Work the author is editing"
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

#: The two dependencies the edited step is stored holding, so
#: `chosen-set` has something to render and the unchosen options have
#: something to be distinguished from.
STORED_DEPENDENCIES: Final = (COMMIT_OPTION, TITLE_OPTION)

#: What the dependency control offers when the edited step's form is
#: opened: every `active` step but the edited one.
OFFERED_STEPS: Final[dict[str, tuple[str, str]]] = {
    COMMIT_OPTION: ("commit", COMMIT_OPTION_NAME),
    TITLE_OPTION: ("listable", TITLE_OPTION_NAME),
    IMAGES_OPTION: ("listable", IMAGES_OPTION_NAME),
    LIVE_OPTION: ("live", LIVE_OPTION_NAME),
    GRADUATED_OPTION: ("graduated", GRADUATED_OPTION_NAME),
}

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
_MARKING_ATTRIBUTES: Final = (
    "title",
    "aria-label",
    "aria-description",
    "data-fault",
    "data-error",
)
_REFERENCE_ATTRIBUTES: Final = (
    "aria-describedby",
    "aria-errormessage",
    "aria-details",
)


# ---------------------------------------------------------------------------
# Step-store double
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": EDITED,
            "name": EDITED_NAME,
            "discipline": LISTING,
            "assignees": (ALICE,),
            "starts_at_gate": None,
            "after_steps": (),
            **overrides,
        }
    )


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


class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (
            _Member(ALICE, ALICE_NAME),
            _Member(BOHDAN, BOHDAN_NAME),
            _Member(CHRIS, CHRIS_NAME, active=False),
        )

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


def _seeded_store() -> _FakeStepStore:
    """The edited step at `listable` waiting on two others, the rest of
    the offered set spread over four gates, plus one `draft` and one
    `retired` step that must never be offered."""
    order = 10
    records: list[_Record] = []

    def add(definition: StepDefinition) -> None:
        nonlocal order
        records.append(_Record(definition, display_order=order))
        order += 10

    add(
        _step(
            identifier=COMMIT_OPTION,
            name=COMMIT_OPTION_NAME,
            gate="commit",
        )
    )
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


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _carries(node: _Node, marker: str) -> bool:
    """INVENTED — see this file's docstring. The single correction point
    for how a marker is recognised on an element."""
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


# ---------------------------------------------------------------------------
# Forms, and the two controls' own shape
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

    def values(self, name: str) -> tuple[str, ...]:
        return tuple(value for key, value in self.pairs if key == name)


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
    """What a browser would post from this form, repeated keys included."""
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
    """The form carrying the step's authorable fields."""
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


def _value_inputs(form: _Form, name: str) -> list[_Node]:
    """The per-value controls the field renders, hidden keys excluded."""
    return [
        element
        for element in _elements(form.node)
        if element.tag == "input"
        and element.attrs.get("name") == name
        and (element.attrs.get("type") or "text").lower() in _VALUE_INPUT_TYPES
    ]


def _offered_values(form: _Form, name: str) -> dict[str, _Node]:
    found: dict[str, _Node] = {}
    for element in _value_inputs(form, name):
        value = element.attrs.get("value", "")
        if value:
            found.setdefault(value, element)
    return found


def _chosen_values(form: _Form, name: str) -> set[str]:
    return {
        element.attrs.get("value", "")
        for element in _value_inputs(form, name)
        if "checked" in element.attrs and element.attrs.get("value")
    }


def _shown_as_chosen(form: _Form, name: str) -> set[str]:
    """What the form shows as chosen for `name`, whatever draws it: a
    per-value control that is checked, or a selected `<option>` of a
    chooser carrying the field's name.

    Both shapes are read deliberately. These are statements about what
    the form *holds*, not about how it is drawn, and a reading that saw
    only this change's own shape would hold vacuously against the
    `<select multiple>` that ships today — a test passing before the
    behaviour exists establishes nothing.
    """
    chosen = set(_chosen_values(form, name))
    for element in _elements(form.node):
        if element.tag == "select" and element.attrs.get("name") == name:
            chosen.update(value for value in _select_values(element) if value)
    return chosen


def _chosen_regions(form: _Form) -> list[_Node]:
    return _marked(form.node, CHOSEN_SET)


def _region_for(form: _Form, name: str) -> _Node:
    """The `chosen-set` region belonging to `name`, by the naming the
    requirement demands of it."""
    regions = _chosen_regions(form)
    if not regions:
        pytest.fail(
            f"the form renders no region marked {CHOSEN_SET!r}, so what is "
            "chosen is not rendered apart from the options at all"
        )
    words = _NAMES_OF_FIELD[name]
    matched = [
        region
        for region in regions
        if any(
            word in f"{_attribute_text(region)} {_flat(region)}".lower()
            for word in words
        )
    ]
    if len(matched) != 1:
        pytest.fail(
            f"{len(matched)} of the {len(regions)} {CHOSEN_SET!r} regions name "
            f"{name!r} (looked for one of {words}); the form carries two such "
            "regions and a marker that cannot tell them apart is one a reader "
            "must fall back to structure to use"
        )
    return matched[0]


def _option_rows(form: _Form, name: str) -> dict[str, _Node]:
    """Each offered value's row among the options: the `<label>` bound to
    that value's own input and sitting outside every `chosen-set` region.

    INVENTED — see this file's docstring."""
    regions = _chosen_regions(form)
    labels = [element for element in _elements(form.node) if element.tag == "label"]
    rows: dict[str, _Node] = {}
    for value, control in _offered_values(form, name).items():
        identifier = control.attrs.get("id", "")
        bound = [
            label
            for label in labels
            if (identifier and label.attrs.get("for") == identifier)
            or _within(control, label)
        ]
        outside = [
            label
            for label in bound
            if not any(_within(label, region) for region in regions)
        ]
        if outside:
            rows[value] = outside[0]
        elif bound:
            rows[value] = bound[0]
    return rows


def _chips_of(form: _Form, name: str) -> dict[str, _Node]:
    """The elements inside `name`'s `chosen-set` region that name a
    value — its identifier, or the display name it is labelled by.

    INVENTED — see this file's docstring."""
    region = _region_for(form, name)
    found: dict[str, _Node] = {}
    for value, label in _labels_of(name).items():
        for element in _elements(region):
            if element.tag == "input":
                continue
            haystack = f"{_attribute_text(element)} {_flat(element)}".lower()
            if value.lower() in haystack or label.lower() in haystack:
                found.setdefault(value, element)
                break
    return found


def _labels_of(name: str) -> dict[str, str]:
    if name == AFTER_STEPS:
        return {value: label for value, (_, label) in OFFERED_STEPS.items()}
    return {ALICE: ALICE_NAME, BOHDAN: BOHDAN_NAME}


def _picker_of(form: _Form, name: str) -> _Node:
    """The smallest element holding every one of `name`'s option rows —
    what the delta calls "anything the options are scrolled within"."""
    rows = _option_rows(form, name)
    if not rows:
        pytest.fail(
            f"the {name!r} control renders no option row, so there is nothing "
            "for a fault mark to be outside of — correct `_option_rows` to "
            "the implemented control"
        )
    return _common_ancestor(list(rows.values()))


# ---------------------------------------------------------------------------
# What the surface says at a control
# ---------------------------------------------------------------------------


def _by_id(root: _Node) -> dict[str, _Node]:
    return {
        element.attrs["id"]: element
        for element in _elements(root)
        if element.attrs.get("id")
    }


def _fault_texts(form: _Form, name: str) -> list[tuple[_Node, str]]:
    """What the surface says *about* the field `name`, with the element
    it says it in.

    INVENTED — the reading `test_playbook_admin_start_fields.py` records
    in full, narrowed to the attributions that survive a control being a
    group of inputs rather than one element."""
    root = form.node
    referenced = _by_id(root)
    found: list[tuple[_Node, str]] = []
    controls = [
        element
        for element in _elements(root)
        if element.attrs.get("name") == name
        and element.tag in ("input", "select", "textarea")
    ]
    for control in controls:
        for attribute in _MARKING_ATTRIBUTES:
            value = control.attrs.get(attribute, "").strip()
            if value:
                found.append((control, " ".join(value.split())))
        for attribute in _REFERENCE_ATTRIBUTES:
            for target in control.attrs.get(attribute, "").split():
                element = referenced.get(target)
                if element is not None:
                    found.extend((element, text) for text in _texts(element))
    for element in _elements(root):
        if element.tag in ("input", "select", "textarea"):
            continue
        if any(
            key.startswith("data-") and value == name
            for key, value in element.attrs.items()
        ):
            found.extend((element, text) for text in _texts(element))
    return found


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
        f"the page module exposes no members seam under any of {_MEMBERS_ATTRIBUTES}"
    )


def _assets_module() -> ModuleType | None:
    try:
        return importlib.import_module(_ASSETS_MODULE_NAME)
    except ModuleNotFoundError:  # pragma: no cover - the module ships today
        return None


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    _install_members(monkeypatch)
    app = FastAPI()
    app.include_router(page_module.router)
    assets = _assets_module()
    if assets is not None:
        monkeypatch.setattr(assets, "verify", _fake_verify)
        app.include_router(assets.router)
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


def _stylesheet(client: TestClient, html: str) -> str:
    hrefs = [
        element.attrs["href"]
        for element in _elements(_tree(html))
        if element.tag == "link"
        and "stylesheet" in element.attrs.get("rel", "").lower()
        and element.attrs.get("href")
    ]
    assert hrefs, "the surface links no stylesheet at all"
    served: list[str] = []
    for href in hrefs:
        response = client.get(_resolve(href.split("?")[0]))
        assert response.status_code == 200, (
            f"the surface links {href!r}, which the app does not serve: "
            f"{response.status_code}"
        )
        served.append(str(response.text))
    return "\n".join(served)


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


def _valid_payload(form: _Form) -> list[tuple[str, str]]:
    """The form's own rendered state, which is a payload the write
    accepts: the edited step is stored valid and nothing is changed."""
    return list(form.pairs)


def _replace(
    pairs: list[tuple[str, str]], name: str, values: tuple[str, ...]
) -> list[tuple[str, str]]:
    kept = [(key, value) for key, value in pairs if key != name]
    return kept + [(name, value) for value in values]


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


def _record_named(store: _FakeStepStore, identifier: str) -> StepDefinition:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record.definition
    pytest.fail(f"the store holds no step named {identifier!r}")


#: A fault concerning neither of these two controls, so a write rejected
#: by it is rejected "for a fault concerning some other field". Proven by
#: `test_playbook_admin_start_fields.py`, which provokes the same rule.
_UNRELATED_FAULT: Final = ("starts_at_gate", "no-such-gate")


def _field_named(form: _Form, fragments: tuple[str, ...], what: str) -> str:
    for name in form.names:
        if any(fragment in name.lower() for fragment in fragments):
            return name
    pytest.fail(
        f"the step form offers no {what} control (looked for a field whose "
        f"name contains one of {fragments}; fields are {sorted(form.names)})"
    )


def _with_unrelated_fault(
    form: _Form, pairs: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    fragment, value = _UNRELATED_FAULT
    name = _field_named(form, (fragment,), "start-gate")
    return _replace(pairs, name, (value,))


# ===========================================================================
# MODIFIED Requirement: The step form carries every authorable field
# — the response half of its multi-value control rules
# ===========================================================================


@pytest.mark.parametrize("field_name", (ASSIGNEES, AFTER_STEPS))
def test_each_multi_valued_control_renders_a_control_per_value(
    monkeypatch: pytest.MonkeyPatch, field_name: str
) -> None:
    """Scenario: A multi-valued control clears without a modifier key —
    the half the requirement assigns to a response.

    WHEN an author clears every value from the assignee control, and from
    the control for the steps a step waits on
    THEN each clears without a modifier key held.

    "That each control renders a control per value" is what the
    requirement names as response-askable; that the values can then be
    chosen and cleared without a modifier is designated for direct
    inspection and is not asserted here.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    offered = _offered_values(form, field_name)

    # SPECIFIED: a control per value.
    assert offered, (
        f"the {field_name!r} control renders no per-value control at all "
        f"(the form's inputs named {field_name!r} are "
        f"{[input_.attrs for input_ in _value_inputs(form, field_name)]}) — a "
        "control that admits more than one value has no plain-click route "
        "back to none unless each value carries its own"
    )
    expected = set(OFFERED_STEPS) if field_name == AFTER_STEPS else {ALICE, BOHDAN}
    # DERIVED complement: the per-value controls really cover what the
    # field offers, so the assertion above is not satisfied by one stray
    # checkbox.
    assert set(offered) == expected, (
        f"the {field_name!r} control renders per-value controls for "
        f"{sorted(offered)}, not for {sorted(expected)}"
    )


def test_what_is_chosen_is_rendered_apart_from_the_options_and_names_its_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: What is chosen is rendered apart from the options and
    names its field.

    WHEN a step waiting on two other steps is opened for editing
    THEN each control's chosen values are in a region marked
    `chosen-set` that names the field it belongs to.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    # SPECIFIED: the form carries two such regions, one per control, each
    # naming its own field — `_region_for` fails loudly where a region
    # cannot be told from its neighbour.
    assignees = _region_for(form, ASSIGNEES)
    dependencies = _region_for(form, AFTER_STEPS)
    assert assignees is not dependencies

    # SPECIFIED: *apart from* the options — the region is not where the
    # options are listed.
    for name, region in ((ASSIGNEES, assignees), (AFTER_STEPS, dependencies)):
        rows = _option_rows(form, name)
        inside = [value for value, row in rows.items() if _within(row, region)]
        assert not inside, (
            f"the {CHOSEN_SET!r} region for {name!r} contains the option rows "
            f"for {sorted(inside)}, so what is chosen is not rendered apart "
            "from what may be chosen"
        )


def test_a_chip_exists_for_each_chosen_value_and_for_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "that a chip element exists for each chosen
    value" — named by the requirement as response-askable, and stated
    over the *chosen* values so that the assertion is not vacuous
    (`design.md` rejects rendering a chip for every offered value for
    exactly that reason).

    The negative half is the response's share of *A cleared value is not
    left shown as chosen*: a value whose control is unchosen is not shown
    in `chosen-set`. What a *cleared* value then does is behaviour, and
    is confirmed by direct inspection instead.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    for name, chosen in (
        (ASSIGNEES, {ALICE}),
        (AFTER_STEPS, set(STORED_DEPENDENCIES)),
    ):
        # DERIVED guard: the fixture really is stored holding these, so
        # the assertion below discriminates.
        assert _shown_as_chosen(form, name) == chosen, (
            f"the {name!r} control shows {sorted(_shown_as_chosen(form, name))} "
            f"as chosen, but the stored step holds {sorted(chosen)}"
        )
        chips = _chips_of(form, name)
        # SPECIFIED: a chip per chosen value.
        assert set(chips) == chosen, (
            f"the {CHOSEN_SET!r} region for {name!r} names {sorted(chips)}; "
            f"the chosen values are {sorted(chosen)}. A region naming more "
            "than what is chosen would leave a value shown that its own "
            "control does not hold"
        )


@pytest.mark.parametrize("field_name", (ASSIGNEES, AFTER_STEPS))
def test_every_value_has_its_own_control_among_the_options(
    monkeypatch: pytest.MonkeyPatch, field_name: str
) -> None:
    """Scenario: Every value has its own control among the options.

    WHEN either control is rendered
    THEN each value it offers has its own control in the list of options,
    so that choosing and clearing need nothing to run.

    SPECIFIED: "**Each value's own control SHALL be rendered among the
    options**, where it is what chooses and unchooses — so clearing needs
    nothing to run and no modifier key".

    This replaces a test of the rule that stood here before, which had the
    value's control living beside its chip and a stylesheet rule hiding a
    chip whose box was unchecked. That arrangement made a chip clickable
    without the enhancement and cost the option rows their own visible
    controls, which is the whole of how a list of ninety-four is read. The
    requirement was amended before it shipped; this asserts what replaced
    it.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    offered = _offered_values(form, field_name)
    assert offered, (
        f"the {field_name!r} control offers no value at all, so this "
        "scenario would hold vacuously"
    )

    regions = _chosen_regions(form)
    outside = {
        value: control
        for value, control in offered.items()
        if not any(_within(control, region) for region in regions)
    }
    # SPECIFIED: among the options, which is to say not inside the region
    # that renders what is chosen.
    assert set(outside) == set(offered), (
        "these values' own controls do not sit among the options: "
        f"{sorted(set(offered) - set(outside))} — a value whose control is "
        "elsewhere cannot be cleared from the list an author is reading"
    )


@pytest.mark.parametrize("field_name", (ASSIGNEES, AFTER_STEPS))
def test_an_emptied_control_still_submits_its_key(
    monkeypatch: pytest.MonkeyPatch, field_name: str
) -> None:
    """Scenario: An emptied control still submits its key.

    WHEN an author clears every value from a multi-valued control and
    submits
    THEN the submission carries that field, present and empty.

    Read from the response as `design.md` — *An emptied control must
    still submit its key* fixes the mechanism and `tasks.md` 3.1
    restates it: the control carries a hidden always-submitted value, so
    that a form with every per-value control unchosen still posts the
    key. A checkbox group with nothing checked posts nothing at all,
    which is the whole hazard.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    always = [
        element
        for element in _elements(form.node)
        if element.tag == "input"
        and element.attrs.get("name") == field_name
        and (element.attrs.get("type") or "text").lower() == "hidden"
        and element.attrs.get("value", "") == ""
        and "disabled" not in element.attrs
    ]
    # SPECIFIED: the key is submitted whatever is chosen.
    assert always, (
        f"the {field_name!r} control carries no always-submitted empty value, "
        "so clearing it posts no key at all and a cleared field is "
        "indistinguishable from one never rendered"
    )

    # DERIVED complement: exactly one such value, so the key is present
    # and empty rather than present several times over.
    assert len(always) == 1, (
        f"the {field_name!r} control carries {len(always)} always-submitted "
        "empty values; one is what makes an emptied control post a "
        "present-and-empty key"
    )


@pytest.mark.parametrize("field_name", (ASSIGNEES, AFTER_STEPS))
def test_a_submission_omitting_the_key_means_the_empty_set(
    monkeypatch: pytest.MonkeyPatch, field_name: str
) -> None:
    """Scenario: A submission omitting the key means the empty set.

    WHEN a submission carries no key for a multi-valued control
    THEN it is read as the empty set for that field, not as a field left
    unsubmitted.

    Read on the **re-render** path, which `tasks.md` 3.2 names as the
    one that needs making true: a submission omitting the key is
    re-rendered holding nothing chosen for that control, rather than
    holding what was stored before.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _authoring_form(_edit_surface(client))

    pairs = [
        (name, value) for name, value in _valid_payload(form) if name != field_name
    ]
    rejected = _post(client, form, _with_unrelated_fault(form, pairs))

    assert store.saves == [], "the submission was persisted rather than rejected"
    reread = _authoring_form(rejected)
    # SPECIFIED: read as the empty set, not as a field left unsubmitted.
    assert _shown_as_chosen(reread, field_name) == set(), (
        f"a submission carrying no {field_name!r} key was re-rendered holding "
        f"{sorted(_shown_as_chosen(reread, field_name))} chosen — an absent "
        "key was read as 'not submitted' and restored what the author had "
        "cleared"
    )


def test_a_submission_omitting_the_dependency_key_saves_the_empty_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario on the **write** path, for the one field whose
    empty set the authoring rules accept unconditionally.

    An `active` `human` step naming no assignee is a state the write
    rules forbid (`playbook-admin` — *Steps that are not active are
    visible to authors and set apart*), so the assignee half of this
    scenario cannot be read through a successful write and is read on the
    re-render path above instead.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _authoring_form(_edit_surface(client))

    pairs = [
        (name, value) for name, value in _valid_payload(form) if name != AFTER_STEPS
    ]
    _post(client, form, pairs)

    # SPECIFIED: the absent key means the empty set.
    assert store.saves, (
        "a submission carrying no dependency key was not persisted at all, so "
        "nothing here establishes how the absent key was read"
    )
    assert tuple(_record_named(store, EDITED).after_steps) == (), (
        "a submission carrying no dependency key saved "
        f"{tuple(_record_named(store, EDITED).after_steps)} — the absent key "
        "was read as 'unsubmitted' and the stored value survived a clearing"
    )


@pytest.mark.parametrize("field_name", (ASSIGNEES, AFTER_STEPS))
def test_a_cleared_control_stays_cleared_when_the_write_is_rejected(
    monkeypatch: pytest.MonkeyPatch, field_name: str
) -> None:
    """Scenario: A cleared control stays cleared when the write is
    rejected.

    WHEN an author clears every value from a multi-valued control and the
    write is rejected for a fault concerning some other field
    THEN the re-rendered form holds that control cleared, and not what
    was stored before.

    The submission carries the key present-and-empty, which is what the
    hidden always-submitted value posts once every per-value control is
    unchosen.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _authoring_form(_edit_surface(client))

    cleared = _replace(_valid_payload(form), field_name, ("",))
    rejected = _post(client, form, _with_unrelated_fault(form, cleared))

    assert store.saves == [], "the rejected write persisted a step set"
    reread = _authoring_form(rejected)
    # SPECIFIED: the control comes back cleared.
    assert _shown_as_chosen(reread, field_name) == set(), (
        "the re-rendered form holds "
        f"{sorted(_shown_as_chosen(reread, field_name))} chosen for "
        f"{field_name!r} after the author cleared it — a rejected write "
        "restored what had just been removed"
    )
    # SPECIFIED complement: the region shows nothing either, so the two
    # renderings of one fact agree.
    assert _chips_of(reread, field_name) == {}, (
        f"the {CHOSEN_SET!r} region for {field_name!r} still names "
        f"{sorted(_chips_of(reread, field_name))} after the control was "
        "cleared"
    )


def test_a_non_empty_choice_still_parses_and_echoes_no_empty_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 3.4: a non-empty choice parses as it did — the hidden
    field adds an empty string to the wire, which the readers filter out
    — and the re-render does not echo that empty value back as a chosen
    one.

    Stated by the requirement as "A submission that carries no such key
    SHALL nonetheless be read as the empty set, by every reader of it":
    the empty string the hidden value contributes is not a value.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _authoring_form(_edit_surface(client))

    chosen = (IMAGES_OPTION, LIVE_OPTION)
    pairs = _replace(_valid_payload(form), AFTER_STEPS, ("", *chosen))
    _post(client, form, pairs)

    assert store.saves, "a well-formed submission was not persisted"
    saved = tuple(_record_named(store, EDITED).after_steps)
    # SPECIFIED: the choice parses, and the empty string is not a value.
    assert set(saved) == set(chosen), (
        f"the write saved {saved} for a submission naming {chosen} alongside "
        "the always-submitted empty value"
    )
    assert "" not in saved


@pytest.mark.parametrize(
    ("field_name", "fault"),
    (
        (ASSIGNEES, (ASSIGNEES, NOT_A_MEMBER)),
        (AFTER_STEPS, (AFTER_STEPS, DRAFTED)),
    ),
    ids=(ASSIGNEES, AFTER_STEPS),
)
def test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within(
    monkeypatch: pytest.MonkeyPatch, field_name: str, fault: tuple[str, str]
) -> None:
    """Scenario: A fault mark cannot be hidden by what the author did to
    the options — the half the requirement assigns to a response.

    WHEN a write is rejected for a fault concerning one of these two
    controls
    THEN the mark renders outside anything the options are scrolled
    within.

    That no *filtering* of the options removes the mark is behaviour and
    is designated for direct inspection; it is not asserted here.

    The two provocations are rules the served spec already carries: a
    dependency naming a step that is not `active`, and an assignee the
    members does not carry. Both are proven to reject by
    `test_playbook_admin_start_fields.py` and
    `test_playbook_admin_writes_reach_the_members.py`.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _edit_surface(client)
    form = _authoring_form(surface)

    name, value = fault
    rejected = _post(client, form, _replace(_valid_payload(form), name, (value,)))
    assert store.saves == [], (
        "the provocation persisted a write rather than rejecting it"
    )

    marked = _authoring_form(rejected)
    clean_said = {text for _, text in _fault_texts(form, field_name)}
    added = [
        (element, text)
        for element, text in _fault_texts(marked, field_name)
        if text not in clean_said
    ]
    # DERIVED guard: the control really is marked, or the assertion below
    # would hold vacuously.
    assert added, (
        f"the rejection left the {field_name!r} control unmarked, so there is "
        "nowhere for this scenario to read a mark — correct `_fault_texts` to "
        "the implemented attribution, or the attribution to the requirement"
    )

    picker = _picker_of(marked, field_name)
    outside = [text for element, text in added if not _within(element, picker)]
    # SPECIFIED: the mark renders outside anything the options are
    # scrolled within.
    assert outside, (
        f"every mark on the {field_name!r} control renders inside the element "
        "its options are listed and scrolled within "
        f"({[text for _, text in added]}), so an author must scroll to "
        "discover it — a mark an author must scroll to find is one the "
        "surface has failed to make"
    )


# ===========================================================================
# The same requirement's two relocated scenarios (`tasks.md` 7.1, 7.2):
# what the controls offer, located on this change's per-value controls
# rather than on `<select>`/`multiple`/`optgroup`
# ===========================================================================


def test_the_dependency_control_is_grouped_and_self_excluding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The dependency control is grouped and self-excluding.

    WHEN the control for the steps a step waits on is opened
    THEN the steps are grouped by gate, each identified by its identifier
    and its name
    AND the step being edited is not among them
    AND no step that is not `active` is among them.

    Reproduced from the served spec unchanged in *what* it asserts;
    only *how* it is located has moved, off `<select>`, `multiple` and
    `optgroup` — that file's own INVENTED locators, which the recorded
    requirement never fixed — and onto the per-value controls and their
    rows (`tasks.md` 7.1, 7.2).
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    offered = _offered_values(form, AFTER_STEPS)

    # SPECIFIED: it admits more than one step.
    assert len(offered) > 1, (
        f"the dependency control offers {sorted(offered)}; `after_steps` is a "
        "set and the control must admit more than one step"
    )
    # SPECIFIED: the step being edited is not among them.
    assert EDITED not in offered
    # SPECIFIED: no step that is not `active` is among them.
    assert DRAFTED not in offered
    assert RETIRED not in offered
    # DERIVED complement: the `active` steps *are* offered, so the
    # exclusions above are not satisfied by an empty control.
    assert set(offered) == set(OFFERED_STEPS), (
        f"the dependency control offers {sorted(offered)}, not the "
        f"`active` steps other than the edited one ({sorted(OFFERED_STEPS)})"
    )

    rows = _option_rows(form, AFTER_STEPS)
    assert set(rows) == set(offered), (
        f"the options {sorted(set(offered) - set(rows))} carry no row a reader "
        "could identify them by — correct `_option_rows` to the implemented "
        "control"
    )
    # SPECIFIED: each option is identified by both its identifier and its
    # name.
    for value, (_, step_name) in OFFERED_STEPS.items():
        said = f"{_attribute_text(rows[value])} {_flat(rows[value])}"
        assert value in said, (
            f"the option for {value!r} does not carry its identifier: {said!r}"
        )
        assert step_name in said, (
            f"the option for {value!r} does not carry its name: {said!r}"
        )

    # SPECIFIED: grouped by the gate they belong to.
    for value, (gate, _) in OFFERED_STEPS.items():
        group = _gate_group_of(form, rows[value])
        assert group == gate, (
            f"the option for {value!r} is grouped under {group!r}, not under "
            f"its own gate {gate!r}"
        )


def _gate_group_of(form: _Form, row: _Node) -> str | None:
    """The gate the group holding this option row is headed by.

    INVENTED locator: walking out from the row, the first ancestor
    carrying text of its own — text outside every option row — that names
    one of the framework's gates. That is what a group heading is,
    whatever element carries it."""
    rows = list(_option_rows(form, AFTER_STEPS).values())
    for ancestor in _ancestors(row):
        heading: list[str] = []
        for element in _elements(ancestor):
            if any(_within(element, other) for other in rows):
                continue
            heading.extend(
                child.text for child in element.children if isinstance(child, _Text)
            )
        said = " ".join(heading).lower()
        for gate in SPECIFIED_GATE_ORDER:
            if gate in said:
                return gate
    return None


def test_assignees_are_chosen_from_the_members_active_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Assignees are chosen from the membership.

    WHEN the assignee control is opened
    THEN it offers the membership's active members by display name, and does
    not accept a free-typed identifier.

    Reproduced from the served spec unchanged in *what* it asserts, and
    relocated off `<select>`/`<option>` onto the per-value controls this
    change introduces (`tasks.md` 7.1, 7.2, 7.6).
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _authoring_form(_edit_surface(client))

    offered = _offered_values(form, ASSIGNEES)
    rows = _option_rows(form, ASSIGNEES)

    # SPECIFIED: chosen, not typed — a control per member, and no free
    # text input carrying the field.
    assert offered, "the assignee control offers no member to choose"
    typed = [
        element
        for element in _elements(form.node)
        if element.tag in ("input", "textarea")
        and element.attrs.get("name") == ASSIGNEES
        and (element.attrs.get("type") or "text").lower() in ("text", "search")
    ]
    assert not typed, (
        "the assignee control accepts a free-typed identifier, which is how an "
        "author names a member who does not exist"
    )
    # SPECIFIED: the membership's *active* members.
    assert set(offered) == {ALICE, BOHDAN}, (
        f"the assignee control offers {sorted(offered)}; the membership's active "
        f"members are {sorted({ALICE, BOHDAN})} and {CHRIS_NAME} is not active"
    )
    # SPECIFIED: identified by display name.
    said = " ".join(f"{_attribute_text(row)} {_flat(row)}" for row in rows.values())
    assert ALICE_NAME in said
    assert BOHDAN_NAME in said
    assert CHRIS_NAME not in said


# ---------------------------------------------------------------------------
# The served stylesheet: parsing and matching
#
# Reproduced from `test_launch_surface_vocabulary_rules.py`, which
# established this reading for `launch-admin`'s own stylesheet
# obligations. Only the subset one obligation here needs is kept: enough
# to decide whether a checked-state rule reaches the `chosen-set` region.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Compound:
    tag: str | None
    classes: frozenset[str]
    identifier: str | None
    attributes: tuple[tuple[str, str, str], ...]
    pseudo_classes: tuple[str, ...]
    pseudo_elements: tuple[str, ...]


@dataclass(frozen=True)
class _Rule:
    selector: str
    declarations: str
    parts: tuple[tuple[str, _Compound], ...]


@dataclass(frozen=True)
class _Vocabulary:
    rules: tuple[_Rule, ...]
    unparsed: tuple[str, ...]


_NESTING_AT_RULES: Final = ("@media", "@supports", "@layer", "@container", "@scope")


def _strip_comments(css: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(css):
        if css.startswith("/*", index):
            closed = css.find("*/", index + 2)
            index = len(css) if closed == -1 else closed + 2
        else:
            out.append(css[index])
            index += 1
    return "".join(out)


def _split_group(selectors: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in selectors:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def _parse_rules(css: str, unparsed: list[str]) -> list[_Rule]:
    rules: list[_Rule] = []
    index = 0
    start = 0
    length = len(css)
    while index < length:
        character = css[index]
        if character == ";" and css[start:index].strip().startswith("@"):
            index += 1
            start = index
            continue
        if character == "{":
            prelude = css[start:index].strip()
            depth = 1
            cursor = index + 1
            while cursor < length and depth:
                if css[cursor] == "{":
                    depth += 1
                elif css[cursor] == "}":
                    depth -= 1
                cursor += 1
            body = css[index + 1 : cursor - 1]
            if prelude.startswith("@"):
                if prelude.split(None, 1)[0].lower() in _NESTING_AT_RULES:
                    rules.extend(_parse_rules(body, unparsed))
            else:
                for selector in _split_group(prelude):
                    parts = _parse_complex(selector)
                    if parts is None:
                        unparsed.append(selector)
                        continue
                    rules.append(_Rule(selector, body, parts))
            index = cursor
            start = cursor
            continue
        index += 1
    return rules


def _identifier_end(text: str, start: int) -> int:
    index = start
    while index < len(text) and (text[index].isalnum() or text[index] in "-_"):
        index += 1
    return index


def _parse_attribute(text: str) -> tuple[str, str, str]:
    for operator in ("~=", "|=", "^=", "$=", "*=", "="):
        if operator in text:
            name, _, value = text.partition(operator)
            return (name.strip().lower(), operator, value.strip().strip("\"'").lower())
    return (text.strip().lower(), "", "")


def _parse_compound(text: str) -> _Compound | None:
    tag: str | None = None
    classes: set[str] = set()
    identifier: str | None = None
    attributes: list[tuple[str, str, str]] = []
    pseudo_classes: list[str] = []
    pseudo_elements: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == ".":
            end = _identifier_end(text, index + 1)
            if end == index + 1:
                return None
            classes.add(text[index + 1 : end])
            index = end
        elif character == "#":
            end = _identifier_end(text, index + 1)
            identifier = text[index + 1 : end]
            index = end
        elif character == "[":
            end = text.find("]", index)
            if end == -1:
                return None
            attributes.append(_parse_attribute(text[index + 1 : end]))
            index = end + 1
        elif character == ":":
            double = text.startswith("::", index)
            offset = index + (2 if double else 1)
            end = _identifier_end(text, offset)
            name = text[offset:end]
            if end < len(text) and text[end] == "(":
                depth = 0
                cursor = end
                while cursor < len(text):
                    if text[cursor] == "(":
                        depth += 1
                    elif text[cursor] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    cursor += 1
                if depth:
                    return None
                end = cursor + 1
            (pseudo_elements if double else pseudo_classes).append(name)
            index = end
        elif character == "*":
            tag = "*"
            index += 1
        elif character.isalpha():
            end = _identifier_end(text, index)
            tag = text[index:end].lower()
            index = end
        else:
            return None
    return _Compound(
        tag=tag,
        classes=frozenset(classes),
        identifier=identifier,
        attributes=tuple(attributes),
        pseudo_classes=tuple(pseudo_classes),
        pseudo_elements=tuple(pseudo_elements),
    )


def _parse_complex(selector: str) -> tuple[tuple[str, _Compound], ...] | None:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for character in selector.strip():
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if depth == 0 and (character.isspace() or character in ">+~"):
            if current:
                tokens.append("".join(current))
                current = []
            if not character.isspace():
                tokens.append(character)
            elif tokens and tokens[-1] != " ":
                tokens.append(" ")
            continue
        current.append(character)
    if current:
        tokens.append("".join(current))
    while tokens and tokens[0] == " ":
        tokens.pop(0)
    while tokens and tokens[-1] == " ":
        tokens.pop()
    parts: list[tuple[str, _Compound]] = []
    combinator = ""
    for token in tokens:
        if token in (" ", ">", "+", "~"):
            combinator = token.strip() or " "
            continue
        compound = _parse_compound(token)
        if compound is None:
            return None
        parts.append((combinator, compound))
        combinator = ""
    return tuple(parts) if parts else None


def _siblings(node: _Node) -> list[_Node]:
    parent = node.parent
    if parent is None:
        return [node]
    return [child for child in parent.children if isinstance(child, _Node)]


def _compound_matches(compound: _Compound, node: _Node) -> bool:
    if compound.tag not in (None, "*") and node.tag != compound.tag:
        return False
    if compound.identifier and node.attrs.get("id") != compound.identifier:
        return False
    if not compound.classes <= _classes(node):
        return False
    for name, operator, value in compound.attributes:
        present = node.attrs.get(name)
        if present is None:
            return False
        present = present.lower()
        if operator == "=" and present != value:
            return False
        if operator == "~=" and value not in present.split():
            return False
        if operator == "^=" and not present.startswith(value):
            return False
        if operator == "$=" and not present.endswith(value):
            return False
        if operator == "*=" and value not in present:
            return False
        if operator == "|=" and not (
            present == value or present.startswith(f"{value}-")
        ):
            return False
    if "root" in compound.pseudo_classes and node.tag != "html":
        return False
    if (
        compound.tag in (None, "*")
        and not compound.classes
        and not compound.identifier
        and not compound.attributes
    ):
        return "root" in compound.pseudo_classes and node.tag == "html"
    return True


def _parts_match(parts: tuple[tuple[str, _Compound], ...], node: _Node) -> bool:
    combinator, compound = parts[-1]
    if not _compound_matches(compound, node):
        return False
    rest = parts[:-1]
    if not rest:
        return True
    candidates: list[_Node] = []
    if combinator in ("", " "):
        candidates = list(_ancestors(node))
    elif combinator == ">":
        parent = node.parent
        candidates = (
            [parent] if parent is not None and parent.tag != "#document" else []
        )
    elif combinator in ("+", "~"):
        siblings = _siblings(node)
        position = siblings.index(node)
        earlier = siblings[:position]
        candidates = earlier[-1:] if combinator == "+" else earlier
    return any(_parts_match(rest, candidate) for candidate in candidates)


def _matches(rule: _Rule, node: _Node) -> bool:
    return _parts_match(rule.parts, node)


def _read(css: str) -> _Vocabulary:
    unparsed: list[str] = []
    rules = _parse_rules(_strip_comments(css), unparsed)
    return _Vocabulary(tuple(rules), tuple(unparsed))


def _readable(vocabulary: _Vocabulary) -> None:
    assert not vocabulary.unparsed, (
        f"{len(vocabulary.unparsed)} selector(s) in the served stylesheet "
        f"could not be read: {list(vocabulary.unparsed)} — correct "
        "`_parse_complex` rather than accepting the gap"
    )
    assert vocabulary.rules, "the served stylesheet carries no rule at all"
