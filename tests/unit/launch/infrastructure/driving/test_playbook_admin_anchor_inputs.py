"""A timing anchor offers only the inputs its own kind uses
(`playbook-admin`).

Derived strictly from the ADDED requirement *A timing anchor offers only
the inputs its own kind uses* of the delta spec
`openspec/changes/add-step-page/specs/playbook-admin/spec.md` — all four
of its scenarios, plus the normative sentence no scenario states on its
own: inputs rendered as not offered SHALL retain their values and SHALL
still be submitted.

The requirement binds *authoring surfaces*, not creating alone, so it is
covered here rather than in `test_playbook_admin_create_page.py`: the
first scenario is read off a fresh edit form, which is the surface the
shared `_fields.html` partial reaches second and the one `tasks.md` 4.7
asks to be verified.

**Level.** The routes over a step-store double, driven the way a browser
drives them — the harness `test_playbook_admin_page.py` established,
reproduced here because this directory carries no `__init__.py` and this
project keeps its test files self-contained.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- Which inputs each anchor kind uses: `offset` → days; `window` → start
  and end; `open-ended` → start; `recurring` → cadence. `anchor_start`
  is the one input two kinds share (`tasks.md` 4.1, 4.6).
- "Not offered" means **hidden, not disabled**: the requirement demands
  the value be retained *and still submitted*, and a disabled input
  submits nothing (`design.md` — *Anchor inputs*, `tasks.md` 4.3). This
  file therefore asserts both halves — not presented, and not disabled —
  rather than either alone.
- The state is rendered **server-side** from the anchor kind the surface
  was rendered with, which is what makes both scenarios observable in a
  response body at all (`design.md` — *Anchor inputs*).
- A value submitted for a kind the surface was not rendered with is
  ignored by the write (`design.md` — Context; `tasks.md` 4.5, which
  also fixes that the scenario asserts the *written step*, not the
  rendered form).

INVENTED, each recorded in the manifest as an unresolved project
question with its correction point named:

- The page module and its seams, the session cookie, the roster — all
  inherited from the sibling admin-page tests, which the implementation
  already satisfies. Correction point: `_install_roster`.
- How an input's field name is recognised: a form field whose name
  mentions `anchor` and the input's own word (`days`, `start`, `end`,
  `cadence`), and the anchor kind selector as the one mentioning
  `anchor` and `kind`. Correction point: `_ANCHOR_INPUT_WORDS` and
  `_anchor_field`.
- How "rendered as not offered" is read off the markup: the input, or an
  ancestor of it, carries `hidden`, `aria-hidden="true"`,
  `display:none`/`visibility:hidden`, a hidden-ish class, or is an
  `input type="hidden"`. Correction point: `_HIDDEN_CLASSES` and
  `_ElementState`.
- Plausible values for the window anchor's own inputs, chosen from the
  rendered control (a select's own option, else a value matching the
  input's `type`), so that a rejection under `window` comes from the
  field fault this file intends and not from an unparseable anchor.
  Correction point: `_plausible_value`.
- The fault used to provoke a rejection: an `automation_brief` on a
  `human` step — the fault `test_playbook_admin_step_fields.py` already
  uses for the same purpose.

## Expected first-run state

`_fields.html` renders the anchor kind selector plus all four value
inputs unconditionally, and the create surface does not exist yet, so
these tests are expected to fail on a wrong value — every input offered
under every kind — or on an undiscoverable create surface, not at
import.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 821 passed, 81 skipped, 0 failed. The
`tests/integration` tier skipped throughout: it needs a live Postgres
and `DATABASE_URL` is unset here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"

_CREATE_HINTS: Final = ("new", "create", "add")
_A_BRIEF: Final = "A brief no human step may carry"

#: The word each anchor input's field name carries, beyond `anchor`.
_ANCHOR_INPUT_WORDS: Final = ("days", "start", "end", "cadence")

#: Which inputs each anchor kind uses. `start` is the one input two
#: kinds share, which is why the grouping is per input and not per kind.
_ANCHOR_KIND_INPUTS: Final = {
    "offset": ("days",),
    "window": ("start", "end"),
    "open": ("start",),
    "recur": ("cadence",),
}

#: Class names that read as "not presented". Correction point.
_HIDDEN_CLASSES: Final = (
    "hidden",
    "is-hidden",
    "d-none",
    "visually-hidden",
    "sr-only",
)

#: Elements that never open a scope, so they never push onto the stack.
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
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
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


def _seeded_store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = (
        tuple(
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
        )
        + extra
    )
    return _FakeStepStore(records)


def _offset_step() -> tuple[_Record, ...]:
    """One `listable` step whose timing anchor is an offset — so a fresh
    edit of it is "a surface rendered with the anchor kind `offset`"."""
    return (
        _Record(
            _step(
                identifier="listing.zeta",
                name="Work of listing.zeta",
                timing_anchor=OffsetAnchor(days=-7),
            ),
            display_order=20,
        ),
    )


def _identifiers(store: _FakeStepStore) -> set[str]:
    return {record.definition.identifier for record in store.records}


def _the_one_created(store: _FakeStepStore, before: set[str]) -> _Record:
    created = [r for r in store.records if r.definition.identifier not in before]
    assert len(created) == 1, (
        f"the create flow did not go through the write: {len(created)} new records"
    )
    return created[0]


# ---------------------------------------------------------------------------
# HTML discovery: controls, and each named input's offered/submitted state
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


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
class _ElementState:
    """A named form control, as a browser would treat it.

    `hidden` — the control, or an ancestor of it, is rendered as not
    presented. `disabled` — the control, or an ancestor `fieldset`, is
    disabled, which is what would stop a browser submitting it.
    """

    name: str
    tag: str
    kind: str
    value: str
    hidden: bool
    disabled: bool
    options: tuple[tuple[str, str], ...] = ()


@dataclass
class _FormUnderConstruction:
    method: str
    url: str
    inert: bool
    fields: dict[str, str] = field(default_factory=dict)
    buttons: list[tuple[str, str, bool]] = field(default_factory=list)


def _element_hidden(tag: str, a: dict[str, str]) -> bool:
    if "hidden" in a and a["hidden"].lower() != "false":
        return True
    if a.get("aria-hidden", "").lower() == "true":
        return True
    style = a.get("style", "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    classes = a.get("class", "").lower().split()
    if any(name in _HIDDEN_CLASSES for name in classes):
        return True
    return tag == "input" and a.get("type", "").lower() == "hidden"


def _element_disabled(a: dict[str, str]) -> bool:
    return "disabled" in a or a.get("aria-disabled", "").lower() == "true"


class _SurfaceParser(HTMLParser):
    """Collects submittable controls and, tracking the open-element
    stack, each named input's offered and submitted state."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[_Control] = []
        self.states: dict[str, _ElementState] = {}
        self._stack: list[tuple[str, bool, bool]] = []
        self._form: _FormUnderConstruction | None = None
        self._select: tuple[str, bool, bool] | None = None
        self._select_done = False
        self._selected: str | None = None
        self._options: list[tuple[str, str]] = []
        self._option: tuple[str, str] | None = None
        self._textarea: tuple[str, bool, bool] | None = None
        self._text = ""

    @property
    def _hidden_here(self) -> bool:
        return any(hidden for _tag, hidden, _disabled in self._stack)

    @property
    def _disabled_here(self) -> bool:
        return any(disabled for _tag, _hidden, disabled in self._stack)

    def _record(self, state: _ElementState) -> None:
        self.states[state.name] = state

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        hidden = self._hidden_here or _element_hidden(tag, a)
        disabled = self._disabled_here or _element_disabled(a)

        if tag == "form":
            method = (a.get("method") or "get").lower()
            url = a.get("action", "")
            for verb in _HX_VERBS:
                if verb in a:
                    method = verb.removeprefix("hx-")
                    url = a[verb]
            self._form = _FormUnderConstruction(
                method=method, url=url, inert=_element_disabled(a)
            )
        elif tag == "a":
            href = a.get("href", "")
            self.controls.append(
                _Control("get", href, (), disabled or href in ("", "#"))
            )
        else:
            for verb in _HX_VERBS:
                if verb in a:
                    carried = tuple(self._form.fields.items()) if self._form else ()
                    self.controls.append(
                        _Control(verb.removeprefix("hx-"), a[verb], carried, disabled)
                    )

        if tag == "input":
            name = a.get("name")
            kind = (a.get("type") or "text").lower()
            if name:
                if kind in ("submit", "image"):
                    if self._form is not None:
                        self._form.buttons.append((name, a.get("value", ""), disabled))
                else:
                    value = a.get("value", "on" if kind == "checkbox" else "")
                    self._record(
                        _ElementState(name, tag, kind, value, hidden, disabled)
                    )
                    if self._form is not None and not (
                        kind in ("checkbox", "radio") and "checked" not in a
                    ):
                        self._form.fields[name] = value
        elif tag == "button":
            if (a.get("type") or "submit").lower() == "submit" and self._form:
                self._form.buttons.append(
                    (a.get("name", ""), a.get("value", ""), disabled)
                )
        elif tag == "select":
            name = a.get("name")
            if name:
                self._select = (name, hidden, disabled)
                self._select_done = False
                self._selected = None
                self._options = []
                if self._form is not None:
                    self._form.fields[name] = ""
        elif tag == "option" and self._select is not None:
            self._option = (a.get("value", ""), "")
            if "selected" in a:
                self._selected = a.get("value", "")
            if self._form is not None and ("selected" in a or not self._select_done):
                self._form.fields[self._select[0]] = a.get("value", "")
                self._select_done = "selected" in a
        elif tag == "textarea":
            name = a.get("name")
            if name:
                self._textarea = (name, hidden, disabled)
                self._text = ""
                if self._form is not None:
                    self._form.fields[name] = ""

        if tag not in _VOID_TAGS:
            self._stack.append((tag, hidden, disabled))

    def handle_data(self, data: str) -> None:
        if self._textarea is not None:
            self._text += data
        if self._select is not None and self._option is not None:
            value, text = self._option
            self._option = (value, text + data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            form = self._form
            self._form = None
            if form.buttons:
                for name, value, button_inert in form.buttons:
                    fields = dict(form.fields)
                    if name:
                        fields[name] = value
                    self.controls.append(
                        _Control(
                            form.method,
                            form.url,
                            tuple(fields.items()),
                            form.inert or button_inert,
                        )
                    )
            else:
                self.controls.append(
                    _Control(
                        form.method, form.url, tuple(form.fields.items()), form.inert
                    )
                )
        elif tag == "option" and self._option is not None:
            self._options.append((self._option[0], self._option[1].strip()))
            self._option = None
        elif tag == "select" and self._select is not None:
            name, hidden, disabled = self._select
            value = (
                self._selected
                if self._selected is not None
                else (self._options[0][0] if self._options else "")
            )
            self._record(
                _ElementState(
                    name,
                    "select",
                    "select",
                    value,
                    hidden,
                    disabled,
                    tuple(self._options),
                )
            )
            self._select = None
        elif tag == "textarea" and self._textarea is not None:
            name, hidden, disabled = self._textarea
            self._record(
                _ElementState(
                    name, "textarea", "textarea", self._text, hidden, disabled
                )
            )
            if self._form is not None:
                self._form.fields[name] = self._text
            self._textarea = None

        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break


def _parse(html: str) -> _SurfaceParser:
    parser = _SurfaceParser()
    parser.feed(html)
    return parser


def _controls(html: str) -> list[_Control]:
    return _parse(html).controls


def _first_control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> _Control | None:
    for control in _controls(html):
        if control.inert:
            continue
        haystack = control.haystack
        if all(part in haystack for part in contains) and not any(
            part in haystack for part in excludes
        ):
            return control
    return None


def _require_control(
    html: str, *, contains: tuple[str, ...], excludes: tuple[str, ...] = ()
) -> _Control:
    found = _first_control(html, contains=contains, excludes=excludes)
    if found is None:
        pytest.fail(
            f"no live page control mentioning {contains} was discovered — the "
            "invented control vocabulary in this file's docstring needs "
            "correcting to the implemented page"
        )
    return found


def _field_named(
    values: dict[str, str], fragment: str, *, excluding: tuple[str, ...] = ()
) -> str:
    """The one field name mentioning `fragment` and none of `excluding`."""
    matches = [
        name
        for name in values
        if fragment in name and not any(word in name for word in excluding)
    ]
    if len(matches) != 1:
        pytest.fail(
            f"{len(matches)} fields mention {fragment!r} (excluding {excluding}): "
            f"{matches} among {sorted(values)} — correct this file's "
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


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


_ROSTER_ATTRIBUTES: Final = ("roster", "read_roster", "people", "roster_reader")


def _install_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ROSTER_ATTRIBUTES:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, _FakeRoster())
            return
    pytest.fail(
        "the page module exposes no roster seam under any of "
        f"{_ROSTER_ATTRIBUTES} — correct this file's probe to the "
        "implemented name"
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
    data: dict[str, str] | None = None,
    follow_redirects: bool = True,
) -> Any:
    method = control.method.upper()
    target = _resolve(control.url.split("#")[0])
    payload = control.data() if data is None else data
    if method == "GET":
        if payload:
            target = _with_query(target, payload)
        return client.get(target, follow_redirects=follow_redirects)
    return client.request(
        method, target, data=payload, follow_redirects=follow_redirects
    )


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return response.text


def _status_value(status: StepStatus) -> str:
    value = getattr(status, "value", None)
    return str(value) if isinstance(value, str) else status.name.lower()


def _kind_value(kind: StepKind) -> str:
    value = getattr(kind, "value", None)
    return str(value) if isinstance(value, str) else kind.name.lower()


# ---------------------------------------------------------------------------
# Authoring surfaces, and the anchor inputs on them
# ---------------------------------------------------------------------------


def _authoring_form_of(
    html: str, *, require_discipline: bool = False
) -> _Control | None:
    for control in _controls(html):
        if control.method.upper() == "GET":
            continue
        if not any("name" in name for name in control.names):
            continue
        if require_discipline and not any(
            "discipline" in name for name in control.names
        ):
            continue
        if any("anchor" in name for name in control.names):
            return control
    return None


def _open_edit(
    client: TestClient, list_html: str, step_id: str
) -> tuple[str, _Control]:
    control = _require_control(list_html, contains=(step_id, "edit"))
    response = _issue(client, control)
    assert response.status_code == 200, response.text
    body = str(response.text)
    form = _authoring_form_of(body)
    if form is None:
        pytest.fail(
            f"following the edit control for {step_id!r} produced no authoring "
            "form carrying the anchor inputs — correct `_open_edit` to how the "
            "implemented page offers a step's edit form"
        )
    return body, form


def _open_create_surface(client: TestClient, list_html: str) -> tuple[str, _Control]:
    candidates = [
        control
        for control in _controls(list_html)
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
            return str(response.text), form
    pytest.fail(
        "no control on the list led to a create surface carrying the anchor "
        f"inputs (candidates tried: {[c.url for c in candidates]}) — correct "
        "`_CREATE_HINTS` and `_authoring_form_of` to the implemented page"
    )


def _anchor_kind_field(states: dict[str, _ElementState]) -> _ElementState:
    for name, state in states.items():
        if "anchor" in name and "kind" in name:
            return state
    pytest.fail(
        f"the surface renders no anchor kind control (fields: {sorted(states)}) "
        "— correct `_anchor_kind_field` to the implemented form"
    )


def _anchor_field(states: dict[str, _ElementState], word: str) -> _ElementState:
    for name, state in states.items():
        if "anchor" in name and word in name and "kind" not in name:
            return state
    pytest.fail(
        f"the surface renders no anchor input mentioning {word!r} "
        f"(fields: {sorted(states)}) — correct `_ANCHOR_INPUT_WORDS` to the "
        "implemented form"
    )


def _anchor_kind_value(states: dict[str, _ElementState], hint: str) -> str:
    selector = _anchor_kind_field(states)
    for value, label in selector.options:
        if hint in value.lower() or hint in label.lower():
            return value
    pytest.fail(
        f"the anchor kind control offers nothing mentioning {hint!r} "
        f"(options: {selector.options}) — correct `_ANCHOR_KIND_INPUTS` to the "
        "implemented anchor kinds"
    )


def _assert_anchor_offering(
    states: dict[str, _ElementState], kind_hint: str, *, where: str
) -> None:
    """The requirement, read off one rendered surface: the inputs the
    kind uses are offered, the ones belonging only to other kinds are
    not — and a not-offered one is still submitted, which `hidden` gives
    and `disabled` would take away."""
    used = _ANCHOR_KIND_INPUTS[kind_hint]
    for word in _ANCHOR_INPUT_WORDS:
        state = _anchor_field(states, word)
        if word in used:
            assert not state.hidden, (
                f"{where}: the {word!r} input is not offered, though the "
                f"{kind_hint!r} anchor kind uses it"
            )
        else:
            assert state.hidden, (
                f"{where}: the {word!r} input is offered, though it belongs "
                f"only to anchor kinds other than {kind_hint!r}"
            )
            assert not state.disabled, (
                f"{where}: the {word!r} input is disabled rather than merely "
                "not offered, so its value would not be submitted and an "
                "anchor kind reconsidered would lose what was entered"
            )
    # The control that selects the anchor kind is always offered.
    assert not _anchor_kind_field(states).hidden, (
        f"{where}: the anchor kind control itself is not offered"
    )


def _plausible_value(state: _ElementState, *, ordinal: int) -> str:
    """A value the surface's own control could carry, so a rejection
    comes from the field fault this file intends and not from an anchor
    the write cannot parse."""
    if state.options:
        return state.options[-1][0]
    if state.kind == "date":
        return ("2026-09-01", "2026-09-30")[ordinal]
    if state.kind == "datetime-local":
        return ("2026-09-01T09:00", "2026-09-30T09:00")[ordinal]
    return ("-7", "-3")[ordinal]


def _valid_create_values(
    states: dict[str, _ElementState], form: _Control, *, name: str
) -> dict[str, str]:
    """A create payload the authoring write accepts: a `human` step
    naming an active assignee, with no automation brief or handler."""
    values = _fill(
        form.data(),
        name=name,
        gate="listable",
        status=_status_value(StepStatus.ACTIVE),
        assignee=ALICE,
        anchor_days="-7",
    )
    # The step's kind and the anchor's kind both mention "kind", so each
    # is addressed by its own field rather than by substring.
    values[_field_named(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, "offset")
    for key in list(values):
        if "automation_brief" in key or "handler" in key:
            values[key] = ""
    return values


def _rejected_under(
    client: TestClient,
    surface: str,
    form: _Control,
    kind_hint: str,
    *,
    extra: dict[str, str] | None = None,
) -> str:
    """Submit a create the write refuses, carrying the given anchor kind;
    answer the re-rendered surface.

    The refusal is a field fault — an automation brief on a `human` step
    — so the anchor plays no part in *why* it was rejected, which is what
    makes the re-render's anchor state attributable to the submitted
    anchor kind alone.
    """
    states = _parse(surface).states
    values = _valid_create_values(states, form, name="Work whose create is refused")
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, kind_hint)
    values = _fill(values, automation_brief=_A_BRIEF)
    for word, ordinal in (("start", 0), ("end", 1)):
        values = _fill(
            values,
            **{
                _anchor_field(states, word).name: _plausible_value(
                    _anchor_field(states, word), ordinal=ordinal
                )
            },
        )
    if extra:
        values = {**values, **extra}
    response = _issue(client, form, data=values, follow_redirects=False)
    assert response.status_code < 500, response.text
    body = str(response.text)
    assert _authoring_form_of(body, require_discipline=True) is not None, (
        "a rejected create did not re-render the create surface, so there is "
        f"no anchor state to read: {body[:2000]}"
    )
    return body


# ---------------------------------------------------------------------------
# ADDED requirement: A timing anchor offers only the inputs its own kind
# uses
# ---------------------------------------------------------------------------


def test_only_the_selected_anchor_kinds_inputs_are_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Only the selected anchor kind's inputs are offered.

    WHEN an authoring surface is rendered with the anchor kind `offset`
    THEN the inputs the `offset` kind uses are rendered as offered
    AND the inputs belonging only to the other anchor kinds are rendered
    as not offered.

    A fresh edit of a step whose own anchor is an offset is "a surface
    rendered with the anchor kind `offset`" without anything having to be
    submitted first — and it is the surface `_fields.html` reaches
    second, which `tasks.md` 4.7 asks to be verified.
    """
    store = _seeded_store(extra=_offset_step())
    client = _signed_client(monkeypatch, store)

    surface, form = _open_edit(client, _get_page(client), "listing.zeta")

    states = _parse(surface).states
    # DERIVED guard: the surface really is rendered with `offset`, so
    # what follows is about that kind and not about a default.
    assert _anchor_kind_field(states).value == _anchor_kind_value(states, "offset"), (
        "the fresh edit form does not render the step's own anchor kind"
    )
    # SPECIFIED: only the `offset` kind's inputs are offered; the others'
    # are not — and are still submittable.
    _assert_anchor_offering(states, "offset", where="a fresh edit of an offset step")
    assert any("anchor" in name for name in form.names)


def test_a_rejection_re_renders_against_the_submitted_anchor_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejection re-renders against the submitted anchor kind.

    WHEN a write submitting the anchor kind `window` is rejected
    THEN the re-rendered surface offers the inputs the `window` kind uses
    AND the inputs belonging only to the other anchor kinds are rendered
    as not offered
    AND the values submitted for those other kinds are retained.
    """
    store = _seeded_store(extra=_offset_step())
    client = _signed_client(monkeypatch, store)
    surface, form = _open_create_surface(client, _get_page(client))
    states = _parse(surface).states
    days_field = _anchor_field(states, "days").name
    cadence = _anchor_field(states, "cadence")
    typed_cadence = _plausible_value(cadence, ordinal=0)

    body = _rejected_under(
        client,
        surface,
        form,
        "window",
        extra={days_field: "-21", cadence.name: typed_cadence},
    )

    rerendered = _parse(body).states
    # SPECIFIED: the re-render follows the *submitted* anchor kind.
    assert _anchor_kind_field(rerendered).value == _anchor_kind_value(
        rerendered, "window"
    ), "the rejection re-rendered against some other anchor kind"
    # SPECIFIED: `window`'s inputs offered, the other kinds' not.
    _assert_anchor_offering(rerendered, "window", where="a rejection under `window`")
    # SPECIFIED: the values submitted for those other kinds are retained,
    # so an anchor kind reconsidered does not discard what was entered.
    assert _anchor_field(rerendered, "days").value == "-21", (
        "the rejection discarded the value submitted for the `offset` kind's "
        "input, which is exactly what rendering it disabled would cost"
    )
    assert _anchor_field(rerendered, "cadence").value == typed_cadence, (
        "the rejection discarded the value submitted for the `recurring` kind's input"
    )
    assert store.saves == []


def test_an_input_two_anchor_kinds_share_stays_offered_for_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An input two anchor kinds share stays offered for both.

    WHEN an authoring surface is rendered with each of the two anchor
    kinds that share an input
    THEN that input is rendered as offered under both.

    The shared input is the anchor's start, which `window` and
    `open-ended` both use — the reason the grouping is per input rather
    than per anchor kind.
    """
    store = _seeded_store(extra=_offset_step())
    client = _signed_client(monkeypatch, store)
    surface, form = _open_create_surface(client, _get_page(client))

    for kind_hint in ("window", "open"):
        body = _rejected_under(client, surface, form, kind_hint)

        rerendered = _parse(body).states
        assert _anchor_kind_field(rerendered).value == _anchor_kind_value(
            rerendered, kind_hint
        ), f"the rejection did not re-render against {kind_hint!r}"
        # SPECIFIED: the shared input stays offered under both kinds.
        assert not _anchor_field(rerendered, "start").hidden, (
            f"the anchor's start input is not offered under {kind_hint!r}, "
            "though both kinds sharing it use it"
        )
        _assert_anchor_offering(
            rerendered, kind_hint, where=f"a rejection under {kind_hint!r}"
        )
    assert store.saves == []


def test_a_value_carried_by_a_not_offered_input_does_not_reach_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A value carried by a not-offered input does not reach the
    step.

    WHEN a write is submitted carrying a value in an input the submitted
    anchor kind does not use
    THEN the written step's timing anchor is the one its kind describes,
    unaffected by that value.

    This is what makes retaining a not-offered input's value safe rather
    than merely tidy: the value is submitted, and the write ignores it.
    The assertion is on the *written step*, not on the rendered form.
    """
    store = _seeded_store(extra=_offset_step())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    surface, form = _open_create_surface(client, _get_page(client))
    states = _parse(surface).states

    stray_field = _anchor_field(states, "end")
    stray = _plausible_value(stray_field, ordinal=1)
    values = _valid_create_values(
        states, form, name="Work whose anchor is an offset alone"
    )
    values[_anchor_kind_field(states).name] = _anchor_kind_value(states, "offset")
    values = _fill(values, anchor_days="-21")
    values[stray_field.name] = stray

    response = _issue(client, form, data=values, follow_redirects=False)

    assert response.status_code < 500, response.text
    created = _the_one_created(store, before)
    anchor = created.definition.timing_anchor
    # SPECIFIED: the written anchor is the one its kind describes.
    assert isinstance(anchor, OffsetAnchor), (
        f"the written step's anchor is {anchor!r}, not the offset its "
        "submitted kind describes"
    )
    assert anchor.days == -21
    # SPECIFIED: unaffected by the value the submitted kind does not use.
    assert stray not in repr(anchor), (
        f"the value {stray!r}, submitted in an input the `offset` kind does "
        f"not use, reached the written anchor {anchor!r}"
    )
