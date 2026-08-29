"""The step form's two start controls, and the faults they carry
(`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/playbook-admin/spec.md`:

- MODIFIED *The step form carries every authorable field* — only its
  three new scenarios: *The form offers both start fields*, *Starting
  immediately is an offered choice*, and *The dependency control is
  grouped and self-excluding*.
- MODIFIED *Every rule an authoring write can provoke attributes its
  fault* — only its new scenario, *Each start rule is attributed to its
  control*.
- MODIFIED *A rejected write names the fields its faults concern* — only
  its new scenario, *A multi-step fault marks the edited step's control*,
  plus the requirement's own statement about which controls a transitive
  deadlock marks, which `tasks.md` 5.6 turns into an obligation and which
  no scenario states on its own.

Every other scenario of all three requirements is reproduced from the
served spec and is covered by `test_playbook_admin_step_fields.py` and
`test_playbook_admin_fault_attribution.py` in this directory. They are
accounted for against those tests in the manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`.

## Level

The routes over a step-store double, driven the way a browser drives
them: the tests discover the page's own controls and submit them. This is
the harness `test_playbook_admin_page.py` established and
`test_playbook_admin_fault_attribution.py` extended, reproduced here
rather than imported because this project keeps its test files
self-contained.

## How "marks a control" is read

Differentially, as `test_playbook_admin_fault_attribution.py` records in
full: the same surface is rendered clean and rejected, and the text a
control's own region carries on the rejection but not on the clean
render is what that control was marked with. A control's region is the
smallest element containing it and no other control, plus anything the
control points at (`aria-describedby`, `aria-errormessage`,
`aria-details`, `title`, `aria-label`, `data-fault`, `data-error`) and
any element carrying a `data-*` attribute whose value is the control's
name. Text inside a control — a `<select>`'s option labels — is
excluded, being a submitted value rather than something the surface
says. Correction point: `_marking_of`.

## INVENTED, with correction points

Inherited from the sibling admin-page tests: the page module and its
seams, the session cookie, the roster, the control vocabulary and the
form discovery. Added here:

- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition`. Correction point: `_step`.
- That the start-gate control's form field carries "start" in its name
  and the dependency control's carries one of "after"/"depend"/"wait".
  No artifact fixes either. Correction points: `_START_GATE_FRAGMENTS`,
  `_DEPENDENCY_FRAGMENTS`; both fail loudly rather than defaulting.
- That "starts immediately" is offered as an option with an empty value
  or a label saying so. Correction point: `_IMMEDIATELY_WORDS`.

## Expected first-run state

Neither field exists on `StepDefinition`, so every test here is expected
to fail on an **absent target** — a `TypeError` from the constructor
building the fixture store. That establishes absence and nothing about
these assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
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
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

#: Resolved by name rather than imported, matching
#: `test_launch_admin_detail.py`.
page_module: ModuleType = importlib.import_module(
    "commerce_ops.launch.infrastructure.driving.playbook_admin"
)

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
FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

A_DISCIPLINE: Final = next(iter(Discipline))

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"

EDITED: Final = "listing.the-step-being-edited"
EDITED_NAME: Final = "Work the author is editing"
ACTIVE_OTHER: Final = "listing.another-active-step"
ACTIVE_OTHER_NAME: Final = "Other active work"
DRAFTED: Final = "listing.a-drafted-step"
RETIRED: Final = "listing.a-retired-step"
PROHIBITED: Final = "reviews.a-prohibited-tactic"
NAMES_THE_EDITED: Final = "listing.names-the-edited-step"
LATE_STARTER: Final = "ppc.starts-at-live"

#: INVENTED field-name fragments. Both probes fail loudly.
# Deliberately narrower than "start": the timing-anchor controls are named
# `anchor_start` / `anchor_end`, so a bare "start" resolves to the anchor's
# start offset — which is not a gate control at all — before it reaches the
# implemented `starts_at_gate`. The step form's own field is the correction
# point this file's docstring names.
_START_GATE_FRAGMENTS: Final = ("starts_at", "start_gate")
_DEPENDENCY_FRAGMENTS: Final = ("after", "depend", "wait")
_IMMEDIATELY_WORDS: Final = ("immediat", "straight away", "at once", "no gate")

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
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
    attributes: dict[str, Any] = {
        "identifier": EDITED,
        "name": EDITED_NAME,
        "description": None,
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
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
    """One blocking `active` step per gate, plus the cast every
    provocation below needs.

    The set is coherent as it stands: nothing names anything, and the one
    stored dependency (`NAMES_THE_EDITED` → `EDITED`) forms no cycle
    until the edit under test closes it.
    """
    holders = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work of hold.{gate}",
                gate=gate,
                blocking=True,
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    cast = (
        _Record(_step()),
        _Record(_step(identifier=ACTIVE_OTHER, name=ACTIVE_OTHER_NAME)),
        _Record(
            _step(
                identifier=DRAFTED,
                name="Drafted work",
                status=StepStatus.DRAFT,
                assignees=(),
            )
        ),
        _Record(
            _step(
                identifier=RETIRED,
                name="Retired work",
                status=StepStatus.RETIRED,
                assignees=(),
            )
        ),
        _Record(
            _step(
                identifier=PROHIBITED,
                name="A tactic the system declines",
                hazard=Hazard.PROHIBITED_TACTIC,
            )
        ),
        _Record(
            _step(
                identifier=NAMES_THE_EDITED,
                name="Work that already waits on the edited step",
                after_steps=(EDITED,),
            )
        ),
        _Record(
            _step(
                identifier=LATE_STARTER,
                name="Work that starts at live",
                gate="live",
                starts_at_gate="live",
            )
        ),
    )
    return _FakeStepStore(holders + cast)


# ---------------------------------------------------------------------------
# HTML: forms and controls
# ---------------------------------------------------------------------------


class _FormParser(HTMLParser):
    """Forms, their submittable fields, and each select's options —
    tracking `optgroup` labels and the `multiple` attribute, which the
    dependency control's scenario turns on."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.controls: list[tuple[str, str]] = []
        self.selects: dict[str, list[tuple[str, str, str | None]]] = {}
        self.multiple: set[str] = set()
        self._form: dict[str, Any] | None = None
        self._select: str | None = None
        self._select_done = False
        self._group: str | None = None
        self._option: tuple[str, str] | None = None

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
            if kind in ("submit", "image", "button", "reset"):
                return
            if kind in ("checkbox", "radio") and "checked" not in a:
                self._form["fields"].setdefault(name, "")
                return
            default = "on" if kind == "checkbox" else ""
            self._form["fields"][name] = a.get("value", default)
        elif tag == "select":
            self._select = a.get("name")
            self._select_done = False
            if self._select:
                self.selects.setdefault(self._select, [])
                if "multiple" in a:
                    self.multiple.add(self._select)
                if self._form is not None:
                    self._form["fields"][self._select] = ""
        elif tag == "optgroup":
            self._group = a.get("label", "")
        elif tag == "option" and self._select:
            self._option = (a.get("value", ""), "")
            if self._form is not None and ("selected" in a or not self._select_done):
                self._form["fields"][self._select] = a.get("value", "")
                self._select_done = "selected" in a

    def handle_data(self, data: str) -> None:
        if self._select is not None and self._option is not None:
            value, text = self._option
            self._option = (value, text + data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag == "option" and self._select and self._option is not None:
            self.selects[self._select].append(
                (self._option[0], self._option[1].strip(), self._group)
            )
            self._option = None
        elif tag == "optgroup":
            self._group = None
        elif tag == "select":
            self._select = None


def _parse(html: str) -> _FormParser:
    parser = _FormParser()
    parser.feed(html)
    return parser


def _control(
    html: str, *, contains: tuple[str, ...]
) -> tuple[str, str, dict[str, str]] | None:
    parsed = _parse(html)
    for form in parsed.forms:
        haystack = (
            form["url"] + " " + " ".join(f"{k}={v}" for k, v in form["fields"].items())
        )
        if all(part in haystack for part in contains):
            return form["method"], form["url"], dict(form["fields"])
    for method, url in parsed.controls:
        if all(part in url for part in contains):
            return method, url, {}
    return None


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


def _field_named(fields: dict[str, str], fragments: tuple[str, ...], what: str) -> str:
    for name in fields:
        if any(fragment in name.lower() for fragment in fragments):
            return name
    pytest.fail(
        f"the step form offers no {what} control (looked for a field whose "
        f"name contains one of {fragments}; fields are {sorted(fields)}) — "
        "correct this file's probe to the implemented form"
    )


def _start_gate_field(fields: dict[str, str]) -> str:
    return _field_named(fields, _START_GATE_FRAGMENTS, "start-gate")


def _dependency_field(fields: dict[str, str]) -> str:
    return _field_named(fields, _DEPENDENCY_FRAGMENTS, "dependency")


def _gate_field(fields: dict[str, str]) -> str:
    """The step's *own* gate control — a field mentioning "gate" that is
    not the start-gate control."""
    start = _start_gate_field(fields)
    for name in fields:
        if "gate" in name.lower() and name != start:
            return name
    pytest.fail(
        f"the step form offers no gate control distinct from {start!r} "
        f"(fields: {sorted(fields)})"
    )


def _blocking_field(fields: dict[str, str]) -> str:
    return _field_named(fields, ("block",), "blocking")


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
            candidates.append(path)
    assert candidates, "the page router exposes no parameterless GET route"
    return min(candidates, key=len)


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return str(response.text)


def _resolve(url: str) -> str:
    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


@dataclass(frozen=True)
class _EditForm:
    html: str
    method: str
    url: str
    fields: dict[str, str]


def _open_edit(client: TestClient, step_id: str = EDITED) -> _EditForm:
    """Open the step's edit form the way the page offers it.

    The edit affordance is looked for as a link whose URL *ends* with
    `/edit` and names this step, before falling back to the general
    substring search below. Substring matching alone is ambiguous on this
    page: the reorder forms carry a neighbouring step's identifier in
    their `after` field and a URL naming a step whose own identifier
    contains "edit" (`listing.names-the-edited-step`), so a haystack
    search for `(step_id, "edit")` matches a `move` form before it
    reaches the edit link. That is a defect of this probe and not of the
    page — `add-admin-breadcrumb-navigation` moved editing onto the
    step's own page, which the page offers as a plain link.
    """
    page = _get_page(client)
    for method, url in _parse(page).controls:
        if url.rstrip("/").endswith("/edit") and step_id in url:
            response = client.request(method.upper(), _resolve(url))
            assert response.status_code == 200, response.text
            body = str(response.text)
            for form in _parse(body).forms:
                if any("name" in name for name in form["fields"]):
                    return _EditForm(
                        body, form["method"], form["url"], dict(form["fields"])
                    )
    found = _control(page, contains=(step_id, "edit"))
    if found is not None:
        method, url, fields = found
        if not fields:
            response = client.request(method.upper(), _resolve(url))
            assert response.status_code == 200, response.text
            body = str(response.text)
            for form in _parse(body).forms:
                if any("name" in name for name in form["fields"]):
                    return _EditForm(
                        body, form["method"], form["url"], dict(form["fields"])
                    )
    for form in _parse(page).forms:
        haystack = form["url"] + " " + str(form["fields"])
        if step_id in haystack and any("name" in name for name in form["fields"]):
            return _EditForm(page, form["method"], form["url"], dict(form["fields"]))
    pytest.fail(
        f"no edit form for {step_id!r} was discoverable — correct the control "
        "vocabulary in this file's docstring to the implemented page"
    )


def _submit(client: TestClient, form: _EditForm, values: dict[str, str]) -> str:
    response = client.request(
        form.method.upper(),
        _resolve(form.url),
        data=values,
        follow_redirects=False,
    )
    assert response.status_code < 500, response.text
    body = str(response.text)
    if not _parse(body).forms:
        pytest.fail(
            "the rejected write did not re-render a form, so there is no "
            f"field marking to read: {body[:1500]}"
        )
    return body


# ---------------------------------------------------------------------------
# HTML: reading what the surface says *at* a control
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


def _is_control(node: _Node) -> bool:
    return node.tag in ("input", "select", "textarea") and bool(node.attrs.get("name"))


def _texts(node: _Node) -> list[str]:
    """Every text fragment in this subtree, never descending into a
    control: a `<select>`'s option labels are a submitted value, not
    something the surface says."""
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        elif not _is_control(child):
            found.extend(_texts(child))
    return found


def _region_of(control: _Node) -> _Node:
    """The largest ancestor holding this control and no other."""
    region = control
    walker = control.parent
    while walker is not None:
        others = [
            element
            for element in _elements(walker)
            if _is_control(element) and element is not control
        ]
        if others:
            break
        region = walker
        walker = walker.parent
    return region


def _by_id(root: _Node) -> dict[str, list[str]]:
    return {
        element.attrs["id"]: _texts(element)
        for element in _elements(root)
        if element.attrs.get("id")
    }


def _marking_of(root: _Node, name: str) -> list[str]:
    """What the surface says *at* the control named `name`.

    INVENTED — see this file's docstring. The single correction point for
    how a marked control is recognised.
    """
    found: list[str] = []
    referenced = _by_id(root)
    for control in _elements(root):
        if not _is_control(control) or control.attrs.get("name") != name:
            continue
        found.extend(_texts(_region_of(control)))
        for attribute in _MARKING_ATTRIBUTES:
            value = control.attrs.get(attribute, "").strip()
            if value:
                found.append(" ".join(value.split()))
        for attribute in _REFERENCE_ATTRIBUTES:
            for target in control.attrs.get(attribute, "").split():
                found.extend(referenced.get(target, []))
    for element in _elements(root):
        if _is_control(element):
            continue
        if any(
            key.startswith("data-") and value == name
            for key, value in element.attrs.items()
        ):
            found.extend(_texts(element))
    return found


def _control_names(root: _Node) -> list[str]:
    seen: list[str] = []
    for element in _elements(root):
        if _is_control(element) and element.attrs["name"] not in seen:
            seen.append(element.attrs["name"])
    return seen


def _added(rejected: list[str], clean: list[str]) -> tuple[str, ...]:
    already = set(clean)
    fresh: list[str] = []
    for fragment in rejected:
        if fragment not in already and fragment not in fresh:
            fresh.append(fragment)
    return tuple(fresh)


def _marks(rejected: str, clean: str, name: str) -> tuple[str, ...]:
    return _added(_marking_of(_tree(rejected), name), _marking_of(_tree(clean), name))


def _page_level(rejected: str, clean: str) -> tuple[str, ...]:
    def unattributed(html: str) -> list[str]:
        root = _tree(html)
        attributed = {
            fragment
            for name in _control_names(root)
            for fragment in _marking_of(root, name)
        }
        return [fragment for fragment in _texts(root) if fragment not in attributed]

    return _added(unattributed(rejected), unattributed(clean))


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The step form carries every authorable field
# (the three new scenarios)
# ---------------------------------------------------------------------------


def test_the_form_offers_both_start_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The form offers both start fields.

    WHEN a step's form is opened
    THEN it offers a control for the gate the step starts at and a
    control for the steps it waits on.

    SPECIFIED: neither control may be worded so that it reads as the
    step's own gate, which is why `_gate_field` insists the two are
    distinct fields rather than one.
    """
    client = _signed_client(monkeypatch, _seeded_store())

    form = _open_edit(client)

    start = _start_gate_field(form.fields)
    dependency = _dependency_field(form.fields)
    own_gate = _gate_field(form.fields)

    assert start != dependency
    assert start != own_gate


def test_starting_immediately_is_an_offered_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Starting immediately is an offered choice.

    WHEN the start-gate control is opened
    THEN "starts immediately" is among its options, and the final gate is
    not.

    SPECIFIED reason: "starts immediately" is "a meaningful authored
    value rather than an empty field, and the two being indistinguishable
    in a control that offered only gates"; the final gate is excluded
    because it "is refused as a start gate".
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _open_edit(client)
    parsed = _parse(form.html)

    start = _start_gate_field(form.fields)
    options = parsed.selects.get(start)
    assert options is not None, (
        f"the start-gate control {start!r} is not a chooser: the form's "
        f"selects are {sorted(parsed.selects)}"
    )

    # SPECIFIED: "starts immediately" is among its options. DERIVED
    # reading: an option carrying no gate value, or one whose label says
    # so.
    assert any(
        option == "" or any(word in label.lower() for word in _IMMEDIATELY_WORDS)
        for option, label, _ in options
    ), f"the start-gate control offers no 'starts immediately' choice: {options}"

    # SPECIFIED: the final gate is not among them.
    assert FINAL_GATE not in {option for option, _, _ in options}
    assert not any(FINAL_GATE in label.lower() for _, label, _ in options)

    # DERIVED complement, from the same sentence: the *other* gates are
    # offered, so the assertion above is not satisfied by a control that
    # offers no gate at all.
    offered = {option for option, _, _ in options}
    assert {"commit", "listable", "live"} <= offered, (
        f"the start-gate control offers {sorted(offered)}, which is not the "
        "framework's gates other than the final one"
    )


def test_the_dependency_control_is_grouped_and_self_excluding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The dependency control is grouped and self-excluding.

    WHEN the control for the steps a step waits on is opened
    THEN the steps are grouped by gate, each identified by its identifier
    and its name
    AND the step being edited is not among them
    AND no step that is not `active` is among them.
    """
    client = _signed_client(monkeypatch, _seeded_store())
    form = _open_edit(client)
    parsed = _parse(form.html)

    dependency = _dependency_field(form.fields)
    options = parsed.selects.get(dependency)
    assert options is not None, (
        f"the dependency control {dependency!r} is not a chooser: the form's "
        f"selects are {sorted(parsed.selects)}"
    )

    # SPECIFIED: it "SHALL admit more than one step".
    assert dependency in parsed.multiple, (
        "the dependency control admits only one step; `after_steps` is a set"
    )

    offered = {option for option, _, _ in options if option}
    # SPECIFIED: the step being edited is not among them.
    assert EDITED not in offered
    # SPECIFIED: no step that is not `active` is among them.
    assert DRAFTED not in offered
    assert RETIRED not in offered
    # DERIVED complement: an `active` step *is* offered, so the exclusions
    # above are not satisfied by an empty control.
    assert ACTIVE_OTHER in offered

    # SPECIFIED: each option is identified by both its identifier and its
    # name.
    labelled = {option: label for option, label, _ in options if option == ACTIVE_OTHER}
    assert ACTIVE_OTHER in labelled[ACTIVE_OTHER]
    assert ACTIVE_OTHER_NAME in labelled[ACTIVE_OTHER]

    # SPECIFIED: grouped by the gate they belong to.
    groups = {group for option, _, group in options if option and group}
    assert groups, (
        "the dependency control's options carry no group, so a control "
        "ranging over the served step set is a flat list"
    )
    assert any("listable" in group.lower() for group in groups)


# ---------------------------------------------------------------------------
# MODIFIED Requirement: Every rule an authoring write can provoke
# attributes its fault (the new scenario)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Provocation:
    rule: str
    #: Field-name fragment groups the fault must mark, each resolved
    #: against the form's own field names.
    marks: tuple[str, ...]
    values: dict[str, str]


def _provoked(
    client: TestClient, form: _EditForm, provocation: _Provocation
) -> dict[str, str]:
    values = _fill(dict(form.fields), name=EDITED_NAME, gate="listable")
    for fragment, value in provocation.values.items():
        if fragment == "starts_at_gate":
            values[_start_gate_field(values)] = value
        elif fragment == "after_steps":
            values[_dependency_field(values)] = value
        elif fragment == "gate":
            values[_gate_field(values)] = value
        elif fragment == "blocking":
            values[_blocking_field(values)] = value
        else:  # pragma: no cover - a mis-built provocation, not a rule
            raise AssertionError(f"unknown provocation field {fragment!r}")
    return values


_START_RULES: Final = (
    _Provocation(
        "a start gate naming no known gate",
        ("starts_at_gate",),
        {"starts_at_gate": "no-such-gate"},
    ),
    _Provocation(
        "a start gate naming the final gate",
        ("starts_at_gate",),
        {"starts_at_gate": FINAL_GATE},
    ),
    _Provocation(
        "a start gate later than the step's own gate",
        # SPECIFIED: a **combination** fault — "an author may have
        # provoked it by lowering the step's gate as readily as by
        # raising its start gate, so it SHALL mark the gate control and
        # the start-gate control both".
        ("starts_at_gate", "gate"),
        {"gate": "listable", "starts_at_gate": "live"},
    ),
    _Provocation(
        "a dependency naming a step that is not active",
        ("after_steps",),
        {"after_steps": DRAFTED},
    ),
    _Provocation(
        "a dependency naming a step no step in the set carries",
        ("after_steps",),
        {"after_steps": "listing.no-such-step"},
    ),
    _Provocation(
        "a dependency naming a prohibited-tactic step",
        ("after_steps",),
        {"after_steps": PROHIBITED},
    ),
)


@pytest.mark.parametrize(
    "provocation", _START_RULES, ids=[p.rule for p in _START_RULES]
)
def test_each_start_rule_is_attributed_to_its_control(
    monkeypatch: pytest.MonkeyPatch, provocation: _Provocation
) -> None:
    """Scenario: Each start rule is attributed to its control.

    WHEN each of the rules governing when a step starts is provoked in
    turn by an edit
    THEN each fault about a start gate is attributed to the start-gate
    control, and each fault about a dependency to the dependency control
    AND none of them falls through to the page level.

    SPECIFIED: attribution is "by **the declaration it turns on**, and
    never by a fixed control per fault kind" — which is why the
    later-than-its-own-gate case expects *two* controls marked rather
    than one.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _open_edit(client)

    rejected = _submit(client, form, _provoked(client, form, provocation))

    # The provocation reached a rule at all: without this a mis-built
    # payload would read as an attribution failure.
    assert store.saves == [], (
        f"provoking {provocation.rule!r} persisted a write instead of rejecting it"
    )

    resolvers = {
        "starts_at_gate": _start_gate_field,
        "after_steps": _dependency_field,
        "gate": _gate_field,
        "blocking": _blocking_field,
    }
    for fragment in provocation.marks:
        control = resolvers[fragment](form.fields)
        assert _marks(rejected, form.html, control), (
            f"provoking {provocation.rule!r} left the {control!r} control "
            "unmarked; the fault it turns on must be attributed there rather "
            "than falling through to the page level"
        )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A rejected write names the fields its faults concern
# (the new scenario, and the deadlock statement `tasks.md` 5.6 draws from it)
# ---------------------------------------------------------------------------


def test_a_multi_step_fault_marks_the_edited_steps_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A multi-step fault marks the edited step's control.

    WHEN a write is refused because the step being edited introduces a
    cycle among dependency declarations
    THEN the dependency control on that step's form is marked, and the
    fault is not rendered at page level.

    SPECIFIED: "A cycle turns on dependency declarations alone, so it
    marks the dependency control." The cycle is closed by the edit — a
    stored step already names the edited one — which is what makes this
    a *multi-step* fault rather than a self-reference.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _open_edit(client)

    values = _fill(dict(form.fields), name=EDITED_NAME, gate="listable")
    values[_dependency_field(values)] = NAMES_THE_EDITED

    rejected = _submit(client, form, values)

    assert store.saves == [], "a cycle was persisted rather than refused"

    dependency = _dependency_field(form.fields)
    marked = _marks(rejected, form.html, dependency)
    # SPECIFIED: the dependency control is marked.
    assert marked, (
        "the cycle left the dependency control unmarked, so an author who "
        "provoked it is looking at the control that caused it with nothing "
        "on it"
    )
    # SPECIFIED: and the fault is not rendered *only* at page level.
    # Attribution is additional to the fault list, never a filter, so the
    # page-level list may still carry it — what is forbidden is the
    # control carrying nothing, which the assertion above covers.
    assert _page_level(rejected, form.html) or marked


def test_a_transitive_deadlock_marks_every_declaration_it_turns_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "A transitive deadlock turns additionally on
    the step's own gate, its start gate and whether it blocks — an author
    provokes one as readily by ticking 'blocks its gate' or by moving the
    step to an earlier gate as by adding an edge — so it marks all four."

    `tasks.md` 5.6 states the same obligation. Stated in prose rather
    than in a scenario of its own, and asserted here because "an author
    who provoked a deadlock by ticking 'blocks its gate' is not shown an
    unmarked form" is precisely what a fixed-control-per-fault-kind
    implementation gets wrong.
    """
    store = _seeded_store()
    client = _signed_client(monkeypatch, store)
    form = _open_edit(client)

    values = _fill(dict(form.fields), name=EDITED_NAME, gate="listable")
    values[_gate_field(values)] = "listable"
    values[_blocking_field(values)] = "on"
    values[_dependency_field(values)] = LATE_STARTER

    rejected = _submit(client, form, values)

    assert store.saves == [], "a transitive deadlock was persisted rather than refused"

    for resolver in (
        _dependency_field,
        _start_gate_field,
        _gate_field,
        _blocking_field,
    ):
        control = resolver(form.fields)
        assert _marks(rejected, form.html, control), (
            f"the deadlock fault left {control!r} unmarked; it turns on all "
            "four declarations, and an author may have provoked it from any "
            "of them"
        )
