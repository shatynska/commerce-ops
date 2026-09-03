"""A rejected authoring write names the fields its faults concern
(`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/attribute-faults-to-fields/specs/playbook-admin/spec.md`
— the scenarios `tasks.md` 2.1 scopes to this pass:

- ADDED *A rejected write names the fields its faults concern* — all
  seven scenarios.
- ADDED *Every rule an authoring write can provoke attributes its fault*
  — its one scenario, as a parametrised sweep over the inventory in
  `design.md` — *The inventory*.
- MODIFIED *A step can be edited in place* — only its two new scenarios,
  *Faults from different sources arrive together* and *A create wrong in
  a field and in its discipline reports both*. The other three are
  reproduced verbatim from the served spec and are covered by
  `test_playbook_admin_step_fields.py`.
- MODIFIED *Steps can be created, retired and un-retired from the page*
  — only its new scenario *A rejected create does not name the step it
  did not persist*. Every other scenario in that block is reproduced
  unchanged and is covered by `test_playbook_admin_create_page.py`.

The manifest at
`openspec/changes/attribute-faults-to-fields/test-manifest.md` records
every scenario, every assertion's classification, and the project
questions this file had to answer by assumption.

**Level.** The routes over a step-store double, driven the way a browser
drives them: the tests *discover* the page's own controls and submit
them. This is the harness `test_playbook_admin_page.py` established and
`test_playbook_admin_create_page.py` and `test_playbook_admin_anchor_inputs.py`
extended; it is reproduced here rather than imported because this
directory carries no `__init__.py` and this project keeps its test files
self-contained.

## How "marks a field" is read off a response

The requirement fixes the observable itself — *"the field's own control
carries the fault text it was marked with"* — but not the markup. So
this file reads marking **differentially**: it renders the same surface
twice, once clean and once rejected, and treats the text that appears in
a field's own region on the rejection and not on the clean render as
what that field was marked with. Nothing is keyed on fault wording,
which is what lets these tests survive the rewordings `design.md` warns
the text-keyed half of the mapping is exposed to.

"A field's own region" is INVENTED and is this file's single largest
assumption. It is the largest element that contains that control **and
no other control**, plus anything the control points at explicitly
(`aria-describedby`, `aria-errormessage`, `aria-details`, `title`,
`aria-label`, `data-fault`, `data-error`) and any element carrying a
`data-*` attribute whose value is the control's name. Text inside the
control itself — a `<select>`'s option labels, a `<textarea>`'s
contents — is excluded everywhere, because that is a submitted *value*
and not something the surface says. Correction point: `_marking_of`.

Two consequences worth naming rather than discovering:

- A fault rendered into a wrapper shared by two controls attributes to
  neither. That is deliberate: *An unparseable anchor value marks the
  input it came from* requires telling `anchor_start` from
  `anchor_end`, and a wrapper holding both cannot.
- The page-level fault list attributes to nothing, because the element
  enclosing it holds either no control or many. That is what makes
  *A fault about the step set marks no field* and *Attribution never
  shortens the fault list* assertable at all.

## What else is fixed, and what is INVENTED

Fixed by the artifacts:

- The three treatments — one field, a combination, the step set or a
  gate — and that attribution is additional to the fault list, never a
  filter (delta, the ADDED requirement's own prose).
- That a marked control may be one the surface does not offer, and that
  marking does not change whether it is offered (delta; `design.md` —
  *Marking is a third axis*).
- The rule inventory the exhaustiveness sweep provokes, its field sets,
  the single recognised page-level fault, and the seven rules no write
  can provoke and which are therefore outside it (`design.md` — *The
  inventory*; `tasks.md` 3.6).
- That the leading `step '<identifier>' ` alone is removed from a
  step-level fault a create reports (delta; `design.md` — *Stripping the
  generated identifier*).

INVENTED, each recorded in the manifest with its correction point:

- The page module and its seams, the session cookie, the membership, the
  control vocabulary and the create-surface discovery — all inherited
  from the sibling admin-page tests, which the implementation already
  satisfies. Correction points: `_install_members`, `_CREATE_HINTS`,
  `_authoring_form_of`.
- The field region, above. Correction point: `_marking_of`.
- `mg.` as the namespace a generated identifier carries, taken from
  `test_playbook_admin_create_page.py`, which asserts it of a landed
  create. Correction point: `_GENERATED_NAMESPACE`.
- The garbage values used to provoke the adapter's own parse failures
  (`_NOT_A_VALUE`, `_NOT_A_NUMBER`). Nothing is asserted about how they
  are echoed back; they only have to be values no enum and no `int()`
  accepts.

## What this file does NOT cover

`tasks.md` 3.7 asks for it in the test, so it is here rather than only
in the manifest: the exhaustiveness sweep catches a rule **reworded**,
not a rule **added**. Nothing enumerates the rule set mechanically, so a
coherence rule added to the domain later is simply absent from
`_PROVOCATIONS` and nothing goes red. The structural half of the
attribution — the eleven adapter-raised faults — is exempt from that
limit only because `tasks.md` 1.3a makes the fields a required argument
of the carrier, so mypy refuses a new adapter fault that decides none.

## Expected first-run state

The page attributes no fault to any field today — `InvalidPlaybookError`
carries a tuple of plain strings and `_fields.html` renders no marking —
so every test asserting a marking is expected to fail on a wrong value,
not at import: the module, the routes and both surfaces exist.

Two exceptions, both deliberate:

- *A fault about the step set marks no field* is expected to **pass** on
  its first run, because nothing is marked yet and the gate-holding
  fault already renders at page level. It is a regression guard against
  attribution over-reaching onto a fault that concerns no control, not
  evidence that anything was implemented. Recorded in the manifest as
  such rather than counted as coverage of new behaviour.
- *A rejected create does not name the step it did not persist* is
  expected to fail on a wrong value: the create route generates the
  identifier before validating and the fault names it today.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 921 passed, 0 failed, 0 skipped, the integration
tier included.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.playbook import SPECIFIED_GATE_ORDER

PRINCIPAL: Final = "helen"
DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

_CREATE_HINTS: Final = ("new", "create", "add")

#: The namespace a generated identifier carries, per
#: `test_playbook_admin_create_page.py`'s landed-create assertion.
_GENERATED_NAMESPACE: Final = "mg."

#: Values no enum and no `int()` accepts. Nothing is asserted about how
#: they are echoed back — only that submitting them is refused.
_NOT_A_VALUE: Final = "not-an-offered-value"
_NOT_A_NUMBER: Final = "soon"

_A_HANDLER: Final = "no.such.registered.use-case"
_NOT_A_MEMBER: Final = "prs_00NOBODYATALL"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_NAME: Final = "Bohdan Colleague"
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

#: Attributes on a control whose own value could carry the fault text.
_MARKING_ATTRIBUTES: Final = (
    "title",
    "aria-label",
    "aria-description",
    "data-fault",
    "data-error",
)
#: Attributes on a control naming, by id, an element carrying the text.
_REFERENCE_ATTRIBUTES: Final = (
    "aria-describedby",
    "aria-errormessage",
    "aria-details",
)


def _enum_member(enum_type: type[Enum], hint: str) -> Enum:
    """The member of an enum whose value mentions `hint`.

    Resolved rather than spelled, so a renamed value fails here with its
    own message instead of silently provoking no rule at all.
    """
    for member in enum_type:
        if hint in str(member.value).lower():
            return member
    pytest.fail(
        f"{enum_type.__name__} carries no member mentioning {hint!r} "
        f"(values: {[m.value for m in enum_type]}) — the provocation this "
        "backs cannot be built"
    )


PROHIBITED_TACTIC: Final = _enum_member(Hazard, "prohibit")


# ---------------------------------------------------------------------------
# Step-store double (the shape the sibling admin tests record)
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


#: The step every edit-surface test edits: active, human, non-blocking,
#: so editing it provokes only the rule the test provokes.
EDITED: Final = "listing.zeta"


def _seeded_store() -> _FakeStepStore:
    """One `active`, blocking step per gate, plus two ordinary `listable`
    steps an edit can be aimed at without touching a gate's hold."""
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
# An HTML tree, so a fault's text can be attributed to a control by
# containment rather than by proximity in the source
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
    tests' flat parsers already do."""

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
    """A named control a member types into or chooses from.

    `input type=hidden` is excluded: it is a routing value a browser
    posts and nobody types, so it is not something a fault can be said
    to concern — and counting it would split the field groups this
    file's attribution rests on.
    """
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


def _by_id(root: _Node) -> dict[str, list[_Text]]:
    return {
        element.attrs["id"]: _texts(element)
        for element in _elements(root)
        if element.attrs.get("id")
    }


def _marking_of(root: _Node, name: str) -> list[_Text]:
    """What the surface says *at* the control named `name`.

    INVENTED — see this file's docstring. Correction point for how a
    marked control is recognised.
    """
    found: list[_Text] = []
    referenced = _by_id(root)
    ordinal = -1
    for control in _elements(root):
        if not _is_control(control) or control.attrs.get("name") != name:
            continue
        found.extend(_texts(_region_of(control)))
        for attribute in _MARKING_ATTRIBUTES:
            value = control.attrs.get(attribute, "").strip()
            if value:
                found.append(_Text(ordinal, _flat(value)))
                ordinal -= 1
        for attribute in _REFERENCE_ATTRIBUTES:
            for target in control.attrs.get(attribute, "").split():
                found.extend(referenced.get(target, []))
    for element in _elements(root):
        explicit = any(
            key.startswith("data-") and value == name
            for key, value in element.attrs.items()
        )
        if explicit and not _is_control(element):
            found.extend(_texts(element))
    return found


def _control_names(root: _Node) -> list[str]:
    seen: list[str] = []
    for element in _elements(root):
        if _is_control(element):
            name = element.attrs["name"]
            if name not in seen:
                seen.append(name)
    return seen


def _unattributed(root: _Node) -> list[_Text]:
    """Every fragment the page renders that no control's own region
    carries — the page-level rendering, the fault list included."""
    attributed = {
        fragment.ordinal
        for name in _control_names(root)
        for fragment in _marking_of(root, name)
    }
    return [fragment for fragment in _texts(root) if fragment.ordinal not in attributed]


def _added(rejected: list[_Text], clean: list[_Text]) -> tuple[str, ...]:
    """The text a rejection renders in a region that a clean render of
    the same region does not — the fault, whatever it says.

    Compared by text rather than by ordinal, because the two renderings
    number their fragments independently.
    """
    already = {fragment.text for fragment in clean}
    fresh: list[str] = []
    for fragment in rejected:
        if fragment.text not in already and fragment.text not in fresh:
            fresh.append(fragment.text)
    return tuple(fresh)


def _marks(rejected: str, clean: str, name: str) -> tuple[str, ...]:
    return _added(_marking_of(_tree(rejected), name), _marking_of(_tree(clean), name))


def _page_level(rejected: str, clean: str) -> tuple[str, ...]:
    return _added(_unattributed(_tree(rejected)), _unattributed(_tree(clean)))


# ---------------------------------------------------------------------------
# Submittable controls and each named input's rendered state
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
    # An exact field name wins outright. Since
    # `let-a-step-say-when-it-starts` the form carries two gate-valued
    # controls — the step's own `gate` and its `starts_at_gate` — so a
    # bare substring search for "gate" is ambiguous where addressing the
    # named field is not.
    if fragment in names:
        return fragment
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


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return response.text


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


def _open_create(client: TestClient) -> _Surface:
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


def _valid_values(surface: _Surface, *, name: str) -> dict[str, str]:
    """A payload the authoring write accepts: an `active`, `human`,
    non-blocking step naming an active assignee, on an offset anchor,
    carrying neither an automation brief nor a handler."""
    states = surface.states
    values = _fill(
        surface.form.data(),
        name=name,
        gate="listable",
        status=_status_value(StepStatus.ACTIVE),
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
        if "automation_brief" in key or "handler" in key:
            values[key] = ""
    if any("blocking" in key for key in values):
        values = _without(values, "blocking")
    return values


def _valid_edit_values(surface: _Surface) -> dict[str, str]:
    return _valid_values(surface, name="Work this step asks for")


def _valid_create_values(surface: _Surface) -> dict[str, str]:
    return _valid_values(surface, name="Work authored from the create surface")


def _submit(client: TestClient, surface: _Surface, values: dict[str, str]) -> str:
    """Submit the surface's own form and answer the re-rendered surface.

    Fails loudly where the surface did not re-render: there is then no
    marking to read, and reporting that is more useful than an assertion
    about an empty region.
    """
    response = _issue(client, surface.form, data=values, follow_redirects=False)
    assert response.status_code < 500, response.text
    body = str(response.text)
    if _authoring_form_of(body) is None:
        pytest.fail(
            "the rejected write did not re-render an authoring form, so there "
            f"is no field marking to read: {body[:2000]}"
        )
    return body


def _reported(
    client: TestClient, surface: _Surface, values: dict[str, str]
) -> tuple[str, ...]:
    """What a submission adds to the surface's page-level rendering.

    Used to compare one rejection's fault list against another's. A
    rejection persists nothing, so the same surface can be submitted
    several times over the same store.
    """
    return _page_level(_submit(client, surface, values), surface.html)


def _marked_fields(rejected: str, clean: str) -> dict[str, tuple[str, ...]]:
    """Every control the rejection marked, and what it was marked with."""
    return {
        name: marks
        for name in _control_names(_tree(rejected))
        if (marks := _marks(rejected, clean, name))
    }


# ---------------------------------------------------------------------------
# ADDED requirement: A rejected write names the fields its faults concern
# ---------------------------------------------------------------------------


def test_a_fault_about_one_field_marks_that_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A fault about one field marks that field.

    WHEN a write is rejected because a step's name is empty
    THEN the re-rendered surface marks the name field with that fault
    AND no other field is marked with it.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)

    values = _fill(_valid_edit_values(surface), name="")
    rejected = _submit(client, surface, values)

    name_field = _field_name(values, "name")
    marked = _marked_fields(rejected, surface.html)
    # SPECIFIED: the name field is marked with the fault.
    assert marked.get(name_field), (
        f"the rejected edit marked no fault on {name_field!r}; it marked "
        f"{ {k: v for k, v in marked.items()} } — an admin still has to "
        "translate the fault list back into a control"
    )
    # SPECIFIED: and no other field is marked with it. One fault was
    # provoked, so any other marked field is that same fault spreading.
    assert set(marked) == {name_field}, (
        f"a fault about the name alone also marked {sorted(set(marked) - {name_field})}"
    )
    # SPECIFIED (the requirement's own prose): attribution is additional,
    # never a filter — the fault is still in the surface's fault list.
    assert _page_level(rejected, surface.html), (
        "the fault was attributed to a field and dropped from the page-level "
        "fault list, so attribution filtered rather than added"
    )
    assert store.saves == []


def test_a_fault_about_a_combination_marks_every_field_in_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A fault about a combination marks every field in it.

    WHEN a write is rejected because a `human` step carries a handler
    THEN the re-rendered surface marks both the kind field and the
    handler field with that fault.

    The requirement's own prose is asserted alongside the scenario: the
    automation controls render un-offered on a `human` step, and marking
    SHALL NOT change whether a control is offered.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)

    values = _valid_edit_values(surface)
    values[_field_name(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values = _fill(values, handler=_A_HANDLER)
    rejected = _submit(client, surface, values)

    kind_field = _field_name(values, "kind", excluding=("anchor",))
    handler_field = _field_name(values, "handler")
    marked = _marked_fields(rejected, surface.html)
    # SPECIFIED: both fields in the combination are marked — neither
    # value is wrong on its own, and either is a valid thing to change.
    assert marked.get(kind_field), (
        f"the refused pair marked nothing on {kind_field!r} (marked: "
        f"{sorted(marked)}), so the admin is told to change the handler alone"
    )
    assert marked.get(handler_field), (
        f"the refused pair marked nothing on {handler_field!r} (marked: "
        f"{sorted(marked)}), so half the refused pair is left unexplained"
    )
    # SPECIFIED: marking renders the fault adjacent to a control the
    # surface does not offer, just as for any other, and does not change
    # whether it is offered.
    handler_state = _states(rejected)[handler_field]
    assert handler_state.disabled, (
        "marking made the handler offered on a `human` step, so it changed "
        "whether the control is offered rather than only saying the "
        "submitted value was refused"
    )
    assert store.saves == []


def test_a_fault_about_the_step_set_marks_no_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A fault about the step set marks no field.

    WHEN a write is rejected because a gate would be left with no active
    blocking step
    THEN the re-rendered surface reports that fault at page level
    AND marks no field with it.

    Expected to pass on its first run — nothing is marked yet — and kept
    as the guard that attribution does not later reach a fault which
    concerns no control the form carries. Recorded as such in the
    manifest rather than counted as coverage of new behaviour.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    # The gate's only blocking step: unblocking it leaves the gate held
    # by nothing.
    surface = _open_edit(client, "hold.listable")

    values = _valid_values(surface, name="Blocking work of hold.listable")
    values = _fill(values, gate="listable")
    rejected = _submit(client, surface, values)

    # SPECIFIED: the fault is reported at page level.
    assert _page_level(rejected, surface.html), (
        "unblocking a gate's only blocking step reported nothing at page "
        "level, so the provocation did not reach the rule it was written for"
    )
    # SPECIFIED: and marks no field.
    marked = _marked_fields(rejected, surface.html)
    assert marked == {}, (
        f"a fault about the step set marked {sorted(marked)} — it concerns no "
        "control the form in front of the admin carries"
    )
    assert store.saves == []


def test_attribution_never_shortens_the_fault_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Attribution never shortens the fault list.

    WHEN a write is rejected reporting one fault the surface attributes
    and one it does not
    THEN both faults are rendered in the surface's fault list
    AND the one it attributes is additionally marked on its field.

    An empty name is attributed to the name field; a gate left with no
    active blocking step is not attributed to anything. Both are provoked
    by the one submission.

    "Both are rendered" is read by comparing that rejection's fault list
    against the list each fault produces on its own, rather than by
    counting fragments: a list carries its own heading, and a count would
    be satisfied by one fault plus that heading.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client, "hold.listable")

    held = _fill(
        _valid_values(surface, name="Blocking work of hold.listable"),
        gate="listable",
    )
    held = _block(surface.states, held)
    name_only = _fill(dict(held), name="")
    gate_only = _unblock(surface.states, dict(held))
    both = _unblock(surface.states, dict(name_only))

    reported_name_only = _reported(client, surface, name_only)
    reported_gate_only = _reported(client, surface, gate_only)
    rejected = _submit(client, surface, both)

    name_field = _field_name(held, "name")
    page = _page_level(rejected, surface.html)
    marks = _marks(rejected, surface.html, name_field)
    # SPECIFIED: both faults are rendered in the surface's fault list —
    # the attributed one is *still* there, so attribution added rather
    # than filtered.
    assert set(reported_name_only) <= set(page), (
        f"the empty-name fault is in the list when it is the only fault "
        f"({reported_name_only}) but not when it is also attributed ({page}) "
        "— attribution filtered the list rather than adding to it"
    )
    assert set(reported_gate_only) <= set(page), (
        f"the unattributed fault ({reported_gate_only}) is missing from the "
        f"list ({page})"
    )
    # SPECIFIED: the one it attributes is *additionally* marked on its
    # field. Matched by containment, so removing a `step '<id>' ` prefix
    # or wrapping the text still counts as the same fault.
    assert marks, f"the empty-name fault was not marked on {name_field!r}"
    assert any(mark in fault or fault in mark for mark in marks for fault in page), (
        f"what marks {name_field!r} ({marks}) appears nowhere in the page-level "
        f"fault list ({page}) — a fault moved onto a field instead of also "
        "being rendered in full"
    )
    assert store.saves == []


def test_a_field_two_faults_concern_carries_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A field two faults concern carries both.

    WHEN a write is rejected by two faults that both concern the kind
    field
    THEN the kind field is marked once
    AND carries both faults.

    The two: an `active` `human` step names no active assignee, and a
    `human` step cannot name a handler. Both name `kind`, so `kind` is
    the field more than one fault concerns.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)

    values = _valid_edit_values(surface)
    kind_field = _field_name(values, "kind", excluding=("anchor",))
    values[kind_field] = _kind_value(StepKind.HUMAN)
    no_assignee_only = _without(dict(values), "assignee")
    handler_only = _fill(dict(values), handler=_A_HANDLER)
    both = _fill(_without(dict(values), "assignee"), handler=_A_HANDLER)

    marks_brief = _marks(
        _submit(client, surface, no_assignee_only), surface.html, kind_field
    )
    marks_handler = _marks(
        _submit(client, surface, handler_only), surface.html, kind_field
    )
    rejected = _submit(client, surface, both)

    # SPECIFIED: marked once — the surface renders one kind control, not
    # one per fault.
    rendered = [
        element
        for element in _elements(_tree(rejected))
        if _is_control(element) and element.attrs.get("name") == kind_field
    ]
    assert len(rendered) == 1, (
        f"the re-rendered surface carries {len(rendered)} controls named "
        f"{kind_field!r} — a field two faults concern is marked once"
    )
    # SPECIFIED: and carries both faults, not only the first rule that
    # named it. Read against what each rule marks on its own, so nothing
    # is keyed on either fault's wording and a rendering that merely
    # repeats one fault cannot satisfy it.
    marks = _marks(rejected, surface.html, kind_field)
    separately = set(marks_brief) | set(marks_handler)
    assert len(separately) >= 2, (
        f"the two rules mark {separately} on {kind_field!r} when provoked one "
        "at a time, so this test cannot tell a field carrying both from one "
        "carrying the first"
    )
    assert separately <= set(marks), (
        f"{kind_field!r} carries {marks} where the two rules mark "
        f"{separately} separately — the field was attributed to only the "
        "first rule that named it"
    )
    assert store.saves == []


def test_an_unparseable_anchor_value_marks_the_input_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unparseable anchor value marks the input it came from.

    WHEN a write is rejected because one of the timing anchor's numeric
    inputs cannot be read as a number
    THEN the re-rendered surface marks that input with the fault
    AND marks neither of the anchor's other numeric inputs.

    Provoked under the `window` kind, whose two numeric inputs are both
    offered at once: that is the pair a fault naming no field cannot tell
    apart, and the pair this scenario exists to separate.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)
    states = surface.states

    values = _valid_edit_values(surface)
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, "window")
    start = _field_name(values, "anchor_start")
    end = _field_name(values, "anchor_end")
    days = _field_name(values, "anchor_days")
    values[start] = _NOT_A_NUMBER
    values[end] = "-3"
    rejected = _submit(client, surface, values)

    # SPECIFIED: the input the value came from is marked.
    assert _marks(rejected, surface.html, start), (
        f"an unparseable value in {start!r} marked nothing on it, so which box "
        "was wrong is still not in the response"
    )
    # SPECIFIED: and neither of the anchor's other numeric inputs is.
    assert not _marks(rejected, surface.html, end), (
        f"the fault from {start!r} also marked {end!r}, which held a value the "
        "surface could read"
    )
    assert not _marks(rejected, surface.html, days), (
        f"the fault from {start!r} also marked {days!r}, which the submitted "
        "anchor kind does not even use"
    )
    assert store.saves == []


def test_both_authoring_surfaces_attribute_alike(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Both authoring surfaces attribute alike.

    WHEN an edit and a create are each rejected by a fault about one
    field
    THEN each surface marks that field on its own rendering.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)

    edit = _open_edit(client)
    edit_values = _fill(_valid_edit_values(edit), name="")
    edit_rejected = _submit(client, edit, edit_values)

    create = _open_create(client)
    create_values = _fill(_valid_create_values(create), name="")
    create_rejected = _submit(client, create, create_values)

    # SPECIFIED: each surface marks that field on its own rendering. The
    # requirement binds both surfaces that carry the authorable form, so
    # one honouring it is not the requirement being met.
    edit_field = _field_name(edit_values, "name")
    create_field = _field_name(create_values, "name")
    assert _marks(edit_rejected, edit.html, edit_field), (
        "the edit surface marked no field for a fault about one field"
    )
    assert _marks(create_rejected, create.html, create_field), (
        "the create surface marked no field for a fault about one field, "
        "though the edit surface did — the requirement binds both"
    )
    assert store.saves == []


# ---------------------------------------------------------------------------
# MODIFIED requirement: A step can be edited in place — its two new
# scenarios only
# ---------------------------------------------------------------------------


def test_faults_from_different_sources_arrive_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Faults from different sources arrive together.

    WHEN a submitted write carries both an unrecognised value in a field
    the surface parses and an unparseable timing anchor
    THEN the rejection reports both faults
    AND neither source's faults are dropped in favour of the other's.

    "Both" is read against what each source reports on its own, so
    nothing depends on either fault's wording and a list carrying its own
    heading cannot pass for two faults.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_edit(client)
    states = surface.states

    values = _valid_edit_values(surface)
    kind_field = _field_name(values, "kind", excluding=("anchor",))
    days = _field_name(values, "anchor_days")
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, "offset")
    enum_only = {**values, kind_field: _NOT_A_VALUE}
    anchor_only = {**values, days: _NOT_A_NUMBER}
    both = {**values, kind_field: _NOT_A_VALUE, days: _NOT_A_NUMBER}

    reported_enum = _reported(client, surface, enum_only)
    reported_anchor = _reported(client, surface, anchor_only)
    rejected = _submit(client, surface, both)

    # SPECIFIED: the rejection reports both faults. Read off the page's
    # own fault list, which renders every fault whether attributed or not.
    page = _page_level(rejected, surface.html)
    assert set(reported_enum) <= set(page), (
        f"the enum fault ({reported_enum}) is missing from a rejection that "
        f"also carried an unparseable anchor ({page}) — the anchor's raise "
        "discarded the faults gathered beside it"
    )
    assert set(reported_anchor) <= set(page), (
        f"the anchor fault ({reported_anchor}) is missing from the rejection ({page})"
    )
    # SPECIFIED: neither source's faults are dropped in favour of the
    # other's — each is still attributed to its own control.
    assert _marks(rejected, surface.html, kind_field), (
        f"the unrecognised value in {kind_field!r} was dropped in favour of "
        "the anchor's fault"
    )
    assert _marks(rejected, surface.html, days), (
        f"the unparseable {days!r} was dropped in favour of the enum fault"
    )
    assert store.saves == []


def test_a_create_wrong_in_a_field_and_in_its_discipline_reports_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A create wrong in a field and in its discipline reports
    both.

    WHEN a create carries both an unrecognised value in a field the
    surface parses and an unrecognised discipline
    THEN the rejection reports both faults
    AND each marks its own control.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    surface = _open_create(client)

    values = _valid_create_values(surface)
    kind_field = _field_name(values, "kind", excluding=("anchor",))
    discipline_field = _field_name(values, "discipline")
    field_only = {**values, kind_field: _NOT_A_VALUE}
    discipline_only = {**values, discipline_field: _NOT_A_VALUE}
    both = {**values, kind_field: _NOT_A_VALUE, discipline_field: _NOT_A_VALUE}

    reported_field = _reported(client, surface, field_only)
    reported_discipline = _reported(client, surface, discipline_only)
    rejected = _submit(client, surface, both)

    # SPECIFIED: the rejection reports both faults, read against what
    # each reports on its own.
    page = _page_level(rejected, surface.html)
    assert set(reported_field) <= set(page), (
        f"the field fault ({reported_field}) is missing from a create that "
        f"was also wrong in its discipline ({page})"
    )
    assert set(reported_discipline) <= set(page), (
        f"the discipline fault ({reported_discipline}) is missing from the "
        f"rejection ({page}) — the discipline is parsed after the shared "
        "helper has already raised, and a create wrong in both must report "
        "both"
    )
    # SPECIFIED: and each marks its own control.
    assert _marks(rejected, surface.html, kind_field), (
        f"the unrecognised value in {kind_field!r} marked nothing"
    )
    assert _marks(rejected, surface.html, discipline_field), (
        f"the unrecognised discipline marked nothing on {discipline_field!r}"
    )
    assert store.saves == []


# ---------------------------------------------------------------------------
# MODIFIED requirement: Steps can be created, retired and un-retired from
# the page — its one new scenario only
# ---------------------------------------------------------------------------


def test_a_rejected_create_does_not_name_the_step_it_did_not_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected create does not name the step it did not
    persist.

    WHEN a create is rejected by a fault about the step being created
    THEN the reported fault does not identify that step by a generated
    identifier
    AND no step carrying that identifier is in the served set.

    A `human` step carrying a handler: a step-level fault, so it opens
    with the `step '<identifier>' ` the delta says is removed.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    before = store.records
    surface = _open_create(client)

    values = _valid_create_values(surface)
    values[_field_name(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values = _fill(values, handler=_A_HANDLER)
    rejected = _submit(client, surface, values)

    reported = _page_level(rejected, surface.html)
    assert reported, "the rejected create reported no fault at all"
    # SPECIFIED: the fault does not identify the step by a generated
    # identifier. Nothing was persisted, so any `mg.` identifier a
    # *reported fault* carries names a step that does not exist.
    #
    # Asserted over the reported faults and not over the whole response
    # body, which is what this line read first: the create surface's own
    # help text spells the generated shape — `mg.<discipline>.<seq>` —
    # on a clean render too, so a whole-body scan fails on a page
    # carrying no fault at all and cannot tell the two apart. The
    # scenario is worded over the reported fault, and so is this.
    assert not any(_GENERATED_NAMESPACE in fault for fault in reported), (
        "the rejected create renders a generated identifier, sending the "
        "admin looking for a step that was never persisted"
    )
    # SPECIFIED: exactly the leading `step '<identifier>' ` is removed
    # and the remainder rendered as reported — so no fault still opens
    # with it.
    assert not any(fault.startswith("step '") for fault in reported), (
        f"a fault reported by a create still opens `step '`: {reported}"
    )
    # SPECIFIED: no step carrying that identifier is in the served set.
    assert store.saves == []
    assert store.records == before
    assert not any(
        record.definition.identifier.startswith(_GENERATED_NAMESPACE)
        for record in store.records
    )


# ---------------------------------------------------------------------------
# ADDED requirement: Every rule an authoring write can provoke attributes
# its fault
# ---------------------------------------------------------------------------


_Mutate = Callable[[dict[str, _State], dict[str, str]], dict[str, str]]


@dataclass(frozen=True)
class _Provocation:
    """One rule an edit or a create can provoke, and the fields
    `design.md` — *The inventory* says its fault concerns."""

    rule: str
    surface: str
    fields: tuple[str, ...]
    mutate: _Mutate


def _set(name_fragment: str, value: str, *, excluding: tuple[str, ...] = ()) -> _Mutate:
    def mutate(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
        values = dict(values)
        values[_field_name(values, name_fragment, excluding=excluding)] = value
        return values

    return mutate


def _compose(*mutations: _Mutate) -> _Mutate:
    def mutate(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
        for mutation in mutations:
            values = mutation(states, values)
        return values

    return mutate


def _anchor(hint: str) -> _Mutate:
    def mutate(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
        values = dict(values)
        values[_anchor_kind_field(states).name] = _anchor_kind_value(states, hint)
        return values

    return mutate


def _drop(fragment: str) -> _Mutate:
    def mutate(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
        return _without(values, fragment)

    return mutate


def _block(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
    """Tick the blocking checkbox, which an unchecked box does not submit
    and so is absent from the form's own payload."""
    values = dict(values)
    values[_field_name(states, "blocking")] = "on"
    return values


def _unblock(states: dict[str, _State], values: dict[str, str]) -> dict[str, str]:
    return {name: value for name, value in values.items() if "blocking" not in name}


_AUTOMATED: Final = _set("kind", _kind_value(StepKind.AUTOMATED), excluding=("anchor",))
_HUMAN: Final = _set("kind", _kind_value(StepKind.HUMAN), excluding=("anchor",))
_ACTIVE: Final = _set("status", _status_value(StepStatus.ACTIVE))


#: The inventory of `design.md`, one entry per rule an authoring write
#: can provoke: eleven adapter-raised, eleven crossing as prose, and the
#: one recognised page-level fault. The seven rules no write can provoke
#: are deliberately absent — see `tasks.md` 3.6.
_PROVOCATIONS: Final = (
    # --- Structurally attributed, adapter-raised (11) ------------------
    _Provocation(
        "unrecognised scope", "create", ("scope",), _set("scope", _NOT_A_VALUE)
    ),
    _Provocation(
        "unrecognised kind",
        "create",
        ("kind",),
        _set("kind", _NOT_A_VALUE, excluding=("anchor",)),
    ),
    _Provocation(
        "unrecognised status", "create", ("status",), _set("status", _NOT_A_VALUE)
    ),
    _Provocation(
        "unrecognised hazard", "create", ("hazard",), _set("hazard", _NOT_A_VALUE)
    ),
    _Provocation(
        "unrecognised discipline",
        "create",
        ("discipline",),
        _set("discipline", _NOT_A_VALUE),
    ),
    _Provocation(
        "unparseable anchor_days",
        "create",
        ("anchor_days",),
        _compose(_anchor("offset"), _set("anchor_days", _NOT_A_NUMBER)),
    ),
    _Provocation(
        "unparseable anchor_start",
        "create",
        ("anchor_start",),
        _compose(
            _anchor("window"),
            _set("anchor_start", _NOT_A_NUMBER),
            _set("anchor_end", "-3"),
        ),
    ),
    _Provocation(
        "unparseable anchor_end",
        "create",
        ("anchor_end",),
        _compose(
            _anchor("window"),
            _set("anchor_start", "-7"),
            _set("anchor_end", _NOT_A_NUMBER),
        ),
    ),
    _Provocation(
        "unrecognised cadence",
        "create",
        ("anchor_cadence",),
        _compose(_anchor("recurring"), _set("cadence", _NOT_A_VALUE)),
    ),
    _Provocation(
        "unknown anchor kind",
        "create",
        ("anchor_kind",),
        _set("anchor_kind", _NOT_A_VALUE),
    ),
    _Provocation(
        "window end precedes start",
        "create",
        ("anchor_start", "anchor_end"),
        _compose(
            _anchor("window"),
            _set("anchor_start", "-3"),
            _set("anchor_end", "-7"),
        ),
    ),
    # --- Text-keyed, crossing from the domain or the application (11) --
    _Provocation(
        "declares unknown gate", "create", ("gate",), _set("gate", "no-such-gate")
    ),
    _Provocation("has an empty name", "create", ("name",), _set("name", "")),
    _Provocation(
        "name spanning more than one line",
        "create",
        ("name",),
        _set("name", "A name that\nspans two lines"),
    ),
    _Provocation(
        "prohibited-tactic cannot block its gate",
        "create",
        ("hazard", "blocking"),
        _compose(_set("hazard", str(PROHIBITED_TACTIC.value)), _block),
    ),
    _Provocation(
        "automated and active but names no handler",
        "create",
        ("kind", "status", "handler"),
        _compose(_AUTOMATED, _ACTIVE, _set("handler", "")),
    ),
    _Provocation(
        "human step cannot name a handler",
        "create",
        ("kind", "handler"),
        _compose(_HUMAN, _set("handler", _A_HANDLER)),
    ),
    _Provocation(
        "names assignee the membership does not carry",
        "create",
        ("assignees",),
        _compose(
            _set("status", _status_value(StepStatus.DRAFT)),
            _set("assignee", _NOT_A_MEMBER),
        ),
    ),
    _Provocation(
        "active human step names no active assignee",
        "create",
        ("kind", "status", "assignees"),
        _compose(_HUMAN, _ACTIVE, _drop("assignee")),
    ),
    _Provocation(
        "names handler no registered use case answers to",
        "create",
        ("handler",),
        _compose(_AUTOMATED, _ACTIVE, _set("handler", _A_HANDLER)),
    ),
    _Provocation(
        "names its sole assignee as its confirmer",
        "create",
        ("assignees", "confirmer"),
        _set("confirmer", ALICE),
    ),
    _Provocation(
        "names confirmer the membership does not carry",
        "create",
        ("confirmer",),
        _set("confirmer", _NOT_A_MEMBER),
    ),
    _Provocation(
        "active automated step names confirmer not active on the membership",
        "create",
        ("confirmer",),
        _compose(
            _AUTOMATED,
            _ACTIVE,
            _set("handler", _A_HANDLER),
            _set("confirmer", CHRIS_DEPARTED),
        ),
    ),
    # --- Recognised, held at page level, provokable by a write (1) -----
    # Only an edit can reach it: a create adds a step to a gate, it never
    # takes the gate's last blocking step away.
    _Provocation("a gate left with no active blocking step", "edit", (), _unblock),
)

#: The fields each provocation's fault concerns, addressed by substring
#: rather than by the implemented field name.
_FIELD_EXCLUSIONS: Final = {"kind": ("anchor",)}
_FIELD_FRAGMENTS: Final = {"assignees": "assignee", "anchor_cadence": "cadence"}


@pytest.mark.parametrize(
    "provocation", _PROVOCATIONS, ids=[p.rule for p in _PROVOCATIONS]
)
def test_no_rule_an_authoring_write_can_provoke_is_unattributed_by_accident(
    monkeypatch: pytest.MonkeyPatch, provocation: _Provocation
) -> None:
    """Scenario: No rule an authoring write can provoke is unattributed by
    accident.

    WHEN every rule an edit or a create can provoke is provoked in turn
    THEN each resulting fault is either attributed to the fields it
    concerns, or concerns no control the authorable form carries
    AND no fault falls through unrecognised.

    The one rule with no fields is the recognised page-level entry
    `design.md` names — a gate left with no active blocking step. Every
    other case asserts the fields the inventory records, so a rule that
    stops matching because its message was reworded goes red here rather
    than degrading silently to page level.

    **This sweep catches a rule reworded, not a rule added.** Nothing
    enumerates the rule set mechanically, so a coherence rule introduced
    later is simply missing from `_PROVOCATIONS`. The eleven
    adapter-raised faults are exempt only because `tasks.md` 1.3a makes
    the fields a required argument of the carrier that raises them.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    if provocation.surface == "create":
        surface = _open_create(client)
        values = _valid_create_values(surface)
    else:
        surface = _open_edit(client, "hold.listable")
        values = _fill(
            _valid_values(surface, name="Blocking work of hold.listable"),
            gate="listable",
        )
        values = _block(surface.states, values)

    rejected = _submit(client, surface, provocation.mutate(surface.states, values))

    # The provocation reached a rule at all: something is reported that a
    # clean render does not carry. Without this a mis-built payload would
    # read as an attribution failure.
    page = _page_level(rejected, surface.html)
    marked = _marked_fields(rejected, surface.html)
    assert page or marked, (
        f"provoking {provocation.rule!r} produced no fault at all — the "
        "payload no longer reaches that rule, and this case is asserting "
        "nothing"
    )
    assert store.saves == [], (
        f"provoking {provocation.rule!r} persisted a write instead of rejecting it"
    )

    if not provocation.fields:
        # SPECIFIED: a fault concerning no control the form carries is
        # held at page level — recognised, not fallen through.
        assert page, f"{provocation.rule!r} reported nothing at page level"
        assert marked == {}, (
            f"{provocation.rule!r} concerns no control the authorable form "
            f"carries, yet it marked {sorted(marked)}"
        )
        return

    # SPECIFIED: attributed to the fields it concerns — every one of
    # them, since a combination fault marks each field in the combination.
    for wanted in provocation.fields:
        fragment = _FIELD_FRAGMENTS.get(wanted, wanted)
        name = _field_name(
            surface.states, fragment, excluding=_FIELD_EXCLUSIONS.get(wanted, ())
        )
        assert marked.get(name), (
            f"{provocation.rule!r} left {name!r} unmarked (marked: "
            f"{sorted(marked)}) — the fault either fell through unrecognised "
            "or was attributed to fewer fields than it concerns"
        )
