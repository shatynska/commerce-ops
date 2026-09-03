"""Creating a step from its own surface (`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/add-step-page/specs/playbook-admin/spec.md` — the
scenarios that change carries:

- MODIFIED *Steps can be created, retired and un-retired from the page*
  — every scenario except *A blocked retirement explains itself*, which
  the delta reproduces with only the word "live" retired and which
  `test_playbook_admin_page.py` already covers.
- MODIFIED *The narrowed view survives every write and every move
  between views* — only its two new scenarios, *A rejected creation
  keeps the narrowing without leaving the create surface* and *Opening
  and leaving the create surface preserves the narrowing*. The other
  five belong to `reorder-steps-under-filters` and are covered by
  `test_playbook_admin_filtered_moves.py`.

Its ADDED requirement *A timing anchor offers only the inputs its own
kind uses* is covered beside this file, in
`test_playbook_admin_anchor_inputs.py`, because it binds both authoring
surfaces rather than creating alone.

The manifest at `openspec/changes/add-step-page/test-manifest.md`
records every scenario, every classification, and the project questions
this file had to answer by assumption.

**Level.** The routes over a step-store double, driven the way a browser
drives them: the tests *discover* the page's own controls and submit
them, pinning as little of the URL surface as possible. This is the
harness `test_playbook_admin_page.py` established and
`test_playbook_admin_filtered_moves.py` extended; it is reproduced here
rather than imported because this directory carries no `__init__.py` and
this project keeps its test files self-contained.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- Creating lives on its own surface, reached from the list by a control
  rendered ahead of the gate tables (delta, first scenario;
  `tasks.md` 3.3, 5.2).
- A create that lands answers a redirect whose target carries the active
  narrowing, the created step's identity as a query parameter, and a
  fragment addressing it (`design.md` — *Success redirects; rejection
  renders*, which names the redirect's `Location` fragment and the row's
  `id` as the two assertable markers of "addresses that step directly",
  precisely so this file invents neither).
- Where a created step renders depends on the status it was created
  with — an `active` step last in its gate's active steps, a `draft`
  outside that order (delta; `design.md` — *Where a created step
  lands*).

INVENTED, each recorded in the manifest as an unresolved project
question with its correction point named:

- The page module, the `steps` and members seams substituted with
  `monkeypatch.setattr`, the guard seam, the session cookie and the
  narrowing query-parameter names — all inherited from
  `test_playbook_admin_page.py` and `test_playbook_admin_step_fields.py`,
  which the implementation already satisfies. Correction points:
  `_FILTER_PARAMS`, `_RETIRED_PARAM`, `_install_members`.
- How the create control is recognised on the list: a live GET control
  whose URL mentions `new`, `create` or `add`, which answers a page
  carrying a form with both a name and an editable discipline field —
  the discipline being the one field only the create surface offers.
  Correction point: `_CREATE_HINTS` and `_create_form_of`.
- The created step's identity travelling as the query parameter
  `created` (`design.md` states the redirect shape
  `?<narrowing>&created=<identifier>#step-<identifier>`; the spelling is
  the guess). Correction point: `_CREATED_PARAM` — and the create tests
  assert the redirect carries it, so a rename surfaces there first.
- The row's addressing `id` reading `step-<identifier>`, named in
  `design.md`. Correction point: `_ADDRESS_ID`.
- The notice's wording — that a page saying the created step falls
  outside the narrowing mentions the step and an outside-ness word.
  DERIVED, as `test_playbook_admin_page.py` records for fault wording:
  correcting a substring to the implemented wording is a fixture
  correction; dropping the assertion is not. The notice's *offer*, by
  contrast, is read behaviourally — a control carrying the `created`
  parameter, which `tasks.md` 3.12/3.14 make the offer's signature.
- The two faults used to provoke a rejection: a `handler` on a `human`
  step (the fault the sibling test `test_playbook_admin_step_fields.py`
  already uses) together with an `active` `human` step naming no
  assignee. Both are field rules of the served
  `playbook-authoring`/`playbook-admin` specs, not invented rules; the
  *wording markers* asserted on them are DERIVED.

## Expected first-run state

`GET {PAGE_PATH}/steps/new` and `templates/new.html` do not exist, and
the create `POST` answers a rejection by re-rendering the *list*, so
every test here is expected to fail against a live route rather than at
import — a wrong value or an undiscoverable control, not an absent
module. Each therefore discriminates from the first run.

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

from commerce_ops.launch.application import StaleStepSetError
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
from tests.support.playbook import SPECIFIED_GATE_ORDER

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

DISCIPLINES: Final = tuple(Discipline)
#: `_step`'s default discipline, and the first option the create surface
#: offers — so `ANOTHER_DISCIPLINE` is "a discipline other than the first
#: offered", which the rejection scenario needs.
A_DISCIPLINE: Final = DISCIPLINES[0]
ANOTHER_DISCIPLINE: Final = DISCIPLINES[1]

_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}
_RETIRED_PARAM: Final = "retired"

#: The created step's identity, as the success redirect carries it.
_CREATED_PARAM: Final = "created"
#: The addressing `id` a step's row carries, per `design.md`.
_ADDRESS_ID: Final = "step-{identifier}"

_CREATE_HINTS: Final = ("new", "create", "add")

#: Wording markers for the notice that a created step falls outside the
#: active narrowing. DERIVED — see this file's docstring.
_OUTSIDE_WORDS: Final = (
    "outside",
    "not shown",
    "not visible",
    "hidden",
    "does not match",
    "doesn't match",
    "filter",
    "search",
    "narrow",
)

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_NAME: Final = "Bohdan Colleague"
CHRIS_DEPARTED: Final = "prs_01HQ8Z6M4C"
CHRIS_NAME: Final = "Chris Departed"


# ---------------------------------------------------------------------------
# Step-store double (the shape test_playbook_reorder.py records)
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


class _StaleStepStore(_FakeStepStore):
    async def save(self, records: Any, *, expected_version: int) -> None:
        raise StaleStepSetError("the step set changed underneath this write")


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


def _seeded_store(
    extra: tuple[_Record, ...] = (),
    store_class: type[_FakeStepStore] = _FakeStepStore,
) -> _FakeStepStore:
    """One `active`, blocking step per gate, plus the given extras."""
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
    return store_class(records)


def _listable_extras() -> tuple[_Record, ...]:
    """Two active `listable` steps whose authored order disagrees with
    identifier order, so ordered rendering cannot pass by sorting."""
    return (
        _Record(
            _step(identifier="listing.zeta", name="Work of listing.zeta"),
            display_order=20,
        ),
        _Record(
            _step(identifier="listing.alpha", name="Work of listing.alpha"),
            display_order=30,
        ),
    )


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
# HTML discovery: every submit-able control, plus ids, options and
# selections
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


@dataclass(frozen=True)
class _Control:
    """One thing a browser can submit: a link, an `hx-*` element, or a
    form together with one of its submit buttons."""

    method: str
    url: str
    fields: tuple[tuple[str, str], ...] = ()
    inert: bool = False
    hidden_names: tuple[str, ...] = ()
    #: The options and the selected values of *this form's own* selects.
    #: Read per form rather than per page, so a surface rendering two
    #: selects of the same name cannot be mistaken for one.
    options: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    selections: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def data(self) -> dict[str, str]:
        return dict(self.fields)

    def options_of(self, name: str) -> tuple[tuple[str, str], ...]:
        return dict(self.options).get(name, ())

    def selected_of(self, name: str) -> tuple[str, ...]:
        return dict(self.selections).get(name, ())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.fields)

    @property
    def haystack(self) -> str:
        rendered = " ".join(f"{name}={value}" for name, value in self.fields)
        return f"{self.url} {rendered}"


@dataclass
class _FormUnderConstruction:
    method: str
    url: str
    inert: bool
    fields: dict[str, str] = field(default_factory=dict)
    hidden_names: set[str] = field(default_factory=set)
    buttons: list[tuple[str, str, bool]] = field(default_factory=list)
    options: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    selections: dict[str, list[str]] = field(default_factory=dict)


class _PageParser(HTMLParser):
    """Collects controls, element ids, and each select's offered options
    and selected values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[_Control] = []
        self.ids: set[str] = set()
        self.options: dict[str, list[tuple[str, str]]] = {}
        self.selected: dict[str, list[str]] = {}
        self._form: _FormUnderConstruction | None = None
        self._select: str | None = None
        self._select_done = False
        self._textarea: str | None = None
        self._option: tuple[str, str] | None = None

    @staticmethod
    def _inert(a: dict[str, str]) -> bool:
        return "disabled" in a or a.get("aria-disabled", "").lower() == "true"

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        inert = self._inert(a)
        if "id" in a:
            self.ids.add(a["id"])

        if tag == "form":
            method = (a.get("method") or "get").lower()
            url = a.get("action", "")
            for verb in _HX_VERBS:
                if verb in a:
                    method = verb.removeprefix("hx-")
                    url = a[verb]
            self._form = _FormUnderConstruction(method=method, url=url, inert=inert)
            return

        if tag == "a":
            href = a.get("href", "")
            self.controls.append(_Control("get", href, (), inert or href in ("", "#")))
            return

        for verb in _HX_VERBS:
            if verb in a:
                carried = tuple(self._form.fields.items()) if self._form else ()
                self.controls.append(
                    _Control(verb.removeprefix("hx-"), a[verb], carried, inert)
                )

        if tag == "select":
            self._select = a.get("name")
            self._select_done = False
            if self._select:
                self.options.setdefault(self._select, [])
                self.selected.setdefault(self._select, [])
                if self._form is not None:
                    self._form.fields[self._select] = ""
                    self._form.options.setdefault(self._select, [])
                    self._form.selections.setdefault(self._select, [])
            return

        if tag == "option" and self._select:
            self._option = (a.get("value", ""), "")
            if "selected" in a:
                self.selected[self._select].append(a.get("value", ""))
                if self._form is not None:
                    self._form.selections[self._select].append(a.get("value", ""))
            if self._form is not None and ("selected" in a or not self._select_done):
                self._form.fields[self._select] = a.get("value", "")
                self._select_done = "selected" in a
            return

        if self._form is None:
            return

        if tag == "input":
            name = a.get("name")
            if not name:
                return
            kind = (a.get("type") or "text").lower()
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind in ("submit", "image"):
                self._form.buttons.append((name, a.get("value", ""), inert))
                return
            if kind == "hidden":
                self._form.hidden_names.add(name)
            if kind == "checkbox":
                # A checked checkbox is a selected value of its field, the
                # same fact a selected `<option>` carries. Recorded here so
                # `selected_of` reads a multi-valued control whichever way
                # the surface draws it — this form's assignee and dependency
                # controls became checkbox groups in
                # `pick-steps-and-people-by-checkbox`, and the scenarios
                # asserting what a rejection keeps are unchanged by that.
                self._form.selections.setdefault(name, []).append(a.get("value", ""))
            default = "on" if kind == "checkbox" else ""
            self._form.fields[name] = a.get("value", default)
        elif tag == "button":
            kind = (a.get("type") or "submit").lower()
            if kind == "submit":
                self._form.buttons.append(
                    (a.get("name", ""), a.get("value", ""), inert)
                )
        elif tag == "textarea":
            self._textarea = a.get("name")
            if self._textarea:
                self._form.fields[self._textarea] = ""

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea:
            self._form.fields[self._textarea] += data
        if self._select is not None and self._option is not None:
            value, text = self._option
            self._option = (value, text + data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            form = self._form
            self._form = None
            hidden = tuple(sorted(form.hidden_names))
            options = tuple(
                (name, tuple(values)) for name, values in form.options.items()
            )
            selections = tuple(
                (name, tuple(values)) for name, values in form.selections.items()
            )
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
                            hidden,
                            options,
                            selections,
                        )
                    )
            else:
                self.controls.append(
                    _Control(
                        form.method,
                        form.url,
                        tuple(form.fields.items()),
                        form.inert,
                        hidden,
                        options,
                        selections,
                    )
                )
        elif tag == "option" and self._select and self._option is not None:
            option = (self._option[0], self._option[1].strip())
            self.options[self._select].append(option)
            if self._form is not None:
                self._form.options.setdefault(self._select, []).append(option)
            self._option = None
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
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


def _fill(fields: dict[str, str], **by_substring: str) -> dict[str, str]:
    """Override form fields addressed by name substring; fail loudly if
    an addressed field has no match, so nothing is submitted vacuously."""
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
    """The payload with every field mentioning `fragment` dropped — the
    submission a hand-built request makes and the surface never does."""
    remaining = {name: value for name, value in values.items() if fragment not in name}
    if len(remaining) == len(values):
        pytest.fail(
            f"the create form carries no field mentioning {fragment!r} to drop "
            f"(fields: {sorted(values)})"
        )
    return remaining


def _field_named(
    values: dict[str, str], fragment: str, *, excluding: tuple[str, ...] = ()
) -> str:
    """The one field name mentioning `fragment` and none of `excluding`.

    `excluding` exists because two of this form's fields share a word:
    the step's `kind` and the anchor's `kind`. Addressing either by bare
    substring would set both.
    """
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


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


_MEMBERS_ATTRIBUTES: Final = ("members", "read_members", "members_reader")


def _install_members(monkeypatch: pytest.MonkeyPatch, members: _FakeMembers) -> None:
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
    _install_members(monkeypatch, _FakeMembers())
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
    # A value may be a list where the field is submitted more than once —
    # assignees. httpx2 form-encodes that; a list of pairs it does not.
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


def _narrowing(
    *,
    gate: str | None = None,
    discipline: Discipline | None = None,
    search: str | None = None,
    retired: bool = False,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if gate is not None:
        params[_FILTER_PARAMS["gate"]] = gate
    if discipline is not None:
        params[_FILTER_PARAMS["discipline"]] = discipline.value
    if search is not None:
        params[_FILTER_PARAMS["search"]] = search
    if retired:
        params[_RETIRED_PARAM] = "1"
    return params


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return response.text


def _positions(html: str, *needles: str) -> list[int]:
    found = []
    for needle in needles:
        at = html.find(needle)
        assert at >= 0, f"{needle!r} not rendered"
        found.append(at)
    return found


def _rendered_filter(html: str, param: str) -> str | None:
    """What the re-rendered page's own controls carry for a narrowing
    parameter — the filter as the page still shows it."""
    for control in _controls(html):
        for name, value in control.fields:
            if name == param:
                return value
    return None


def _status_value(status: StepStatus) -> str:
    value = getattr(status, "value", None)
    return str(value) if isinstance(value, str) else status.name.lower()


def _kind_value(kind: StepKind) -> str:
    value = getattr(kind, "value", None)
    return str(value) if isinstance(value, str) else kind.name.lower()


# ---------------------------------------------------------------------------
# The create surface: reaching it, filling it, and reading what it says
# ---------------------------------------------------------------------------


def _create_form_of(html: str) -> _Control | None:
    """A submittable form carrying both a name and an *editable*
    discipline field.

    The discipline is the one field only the create surface offers — the
    edit surface renders it read-only, because `update_step` refuses
    discipline changes (`playbook-admin`, *What authoring refuses to
    update renders read-only*). So this predicate recognises the create
    form and nothing else the page renders.
    """
    for control in _controls(html):
        if control.method.upper() == "GET":
            continue
        editable = [name for name in control.names if name not in control.hidden_names]
        if any("name" in name for name in editable) and any(
            "discipline" in name for name in editable
        ):
            return control
    return None


def _open_create_surface(
    client: TestClient, list_html: str
) -> tuple[_Control, str, _Control]:
    """Follow the list's create control; answer the control, the create
    surface's HTML, and the create form on it."""
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
        form = _create_form_of(response.text)
        if form is not None:
            return control, str(response.text), form
    pytest.fail(
        "no control on the list led to a create surface — the list SHALL "
        "offer a control opening it, reachable without traversing the step "
        f"set (candidates tried: {[c.url for c in candidates]}); correct "
        "`_CREATE_HINTS` and `_create_form_of` to the implemented page"
    )


def _anchor_kind_value(html: str, hint: str) -> str:
    """The wire value of the anchor kind whose option mentions `hint`."""
    parsed = _parse(html)
    for name, options in parsed.options.items():
        if "anchor" not in name or "kind" not in name:
            continue
        for value, label in options:
            if hint in value.lower() or hint in label.lower():
                return value
    pytest.fail(
        f"the surface offers no anchor kind mentioning {hint!r} "
        f"(selects: { {k: v for k, v in parsed.options.items() if 'anchor' in k} }) "
        "— correct `_anchor_kind_value` to the implemented form"
    )


def _valid_create_values(
    surface: str,
    form: _Control,
    *,
    name: str,
    gate: str,
    status: StepStatus,
    discipline: Discipline | None = None,
) -> dict[str, str]:
    """A create payload the authoring write accepts: a `human` step
    naming an active assignee, with an offset anchor and no handler."""
    values = _fill(
        form.data(),
        name=name,
        gate=gate,
        status=_status_value(status),
        assignee=ALICE,
        anchor_days="-7",
    )
    # The step's kind and the anchor's kind both mention "kind", so each
    # is addressed by its own field rather than by substring.
    values[_field_named(values, "kind", excluding=("anchor",))] = _kind_value(
        StepKind.HUMAN
    )
    values[_field_named(values, "anchor_kind")] = _anchor_kind_value(surface, "offset")
    if discipline is not None:
        values = _fill(values, discipline=discipline.value)
    for key in list(values):
        if "handler" in key:
            values[key] = ""
    return values


def _rejecting(values: dict[str, str]) -> dict[str, str]:
    """The same payload with two field faults at once: an `active`
    `human` step naming no assignee, and a `human` step carrying a
    handler."""
    rejected = _fill(dict(values), handler=_A_HANDLER)
    return _without(rejected, "assignee")


_A_HANDLER: Final = "no.such.registered.use-case"


def _land(client: TestClient, response: Any) -> tuple[str, str]:
    """A landed create's redirect target, and the list it lands on."""
    assert response.status_code in (302, 303, 307, 308), (
        "a create that lands SHALL return to the step list, so the create "
        f"POST answers a redirect — it answered {response.status_code}: "
        f"{response.text[:1500]}"
    )
    location = str(response.headers["location"])
    followed = client.get(_resolve(location))
    assert followed.status_code == 200, followed.text
    return location, str(followed.text)


def _addresses(html: str, identifier: str) -> bool:
    """Whether the list addresses the step directly — its row carries the
    `id` the redirect's fragment names (`design.md`)."""
    return _ADDRESS_ID.format(identifier=identifier) in _parse(html).ids


def _fragment_addresses(location: str, identifier: str) -> bool:
    return location.split("#")[-1] == _ADDRESS_ID.format(identifier=identifier)


def _clear_offer(html: str, identifier: str) -> _Control | None:
    """The notice's offer to clear the narrowing: the one control
    carrying the created step's identity forward (`tasks.md` 3.12, 3.14
    — only that offer carries it)."""
    for control in _controls(html):
        if control.inert or control.method.upper() != "GET":
            continue
        query = dict(parse_qsl(urlsplit(control.url).query, keep_blank_values=True))
        if query.get(_CREATED_PARAM) == identifier:
            return control
    return None


def _names_the_step_as_outside(html: str, identifier: str) -> bool:
    lowered = html.lower()
    return identifier in html and any(word in lowered for word in _OUTSIDE_WORDS)


def _back_to_list(client: TestClient, html: str, *, marker: str) -> str:
    """Leave the current view by the first GET control landing back on a
    step table that renders `marker`."""
    for control in _controls(html):
        if control.method.upper() != "GET" or control.inert:
            continue
        if control.url.startswith(("#", "http://", "https://", "mailto:")):
            continue
        response = _issue(client, control)
        if response.status_code == 200 and marker in response.text:
            return str(response.text)
    pytest.fail(
        f"no GET control on this view led back to a list rendering {marker!r} "
        "— the create surface SHALL offer leaving it for the list; correct "
        "`_back_to_list` to the implemented page's cancel link"
    )


def _gate_tables_start(html: str) -> int:
    at = html.lower().find("<table")
    if at < 0:
        at = html.find("hold.commit")
    assert at >= 0, "the list renders no gate tables at all"
    return at


def _reorder_control_for(html: str, identifier: str) -> _Control | None:
    for spelling in ("up", "top", "down", "bottom"):
        found = _first_control(html, contains=(identifier, spelling))
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# MODIFIED requirement: Steps can be created, retired and un-retired from
# the page
# ---------------------------------------------------------------------------


def test_creating_is_reachable_regardless_of_how_large_the_set_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Creating is reachable regardless of how large the set is.

    WHEN the admin page is opened with the full step set rendered
    THEN a control opening the create surface is rendered ahead of the
    gate tables
    AND no create form is rendered within or after the gate tables.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: a control opening the create surface exists at all, and
    # opening it reaches a surface carrying the create form.
    control, _surface, _form = _open_create_surface(client, html)
    # SPECIFIED: rendered *ahead of* the gate tables — reaching it does
    # not depend on how many steps are shown.
    tables_at = _gate_tables_start(html)
    control_at = html.find(control.url)
    if control_at < 0:
        control_at = html.find(control.url.split("?")[0])
    assert control_at >= 0, (
        f"the create control's target {control.url!r} is not rendered verbatim "
        "— correct this file's position probe to the implemented markup"
    )
    assert control_at < tables_at, (
        "the create control is rendered within or after the gate tables, so "
        "reaching it depends on how many steps are shown"
    )
    # SPECIFIED: and no create form is rendered within or after them.
    assert _create_form_of(html[tables_at:]) is None, (
        "a create form is still rendered within or after the gate tables"
    )


def test_a_created_active_step_appears_in_its_gate_and_is_addressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A created step appears in its gate.

    WHEN a step is created from the create surface as `active` with valid
    fields, with no narrowing active
    THEN the step list is shown again with the created step rendered as
    the last step of its gate's active steps, carrying its generated
    identifier
    AND the list addresses that step directly, so a browser lands on it
    rather than at the top.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    _control, surface, form = _open_create_surface(client, _get_page(client))

    values = _valid_create_values(
        surface,
        form,
        name="Work authored from the create surface",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    location, listed = _land(client, response)
    created = _the_one_created(store, before)
    identifier = created.definition.identifier
    # SPECIFIED: the identifier is generated, never asked for.
    assert identifier.startswith("mg."), identifier
    assert not any("identifier" in name for name in form.names)
    # SPECIFIED: created `active`, so it holds the last slot of its gate's
    # active steps.
    assert created.definition.status is StepStatus.ACTIVE
    assert identifier in listed
    order = _positions(
        listed, "hold.listable", "listing.zeta", "listing.alpha", identifier
    )
    assert order == sorted(order), (
        "the created step is not rendered last among its gate's active steps"
    )
    assert listed.find(identifier) < listed.find("hold.stock-ready")
    # SPECIFIED: the list addresses that step directly. DERIVED markers,
    # named in `design.md`: the redirect's fragment and the row's `id`.
    assert _fragment_addresses(location, identifier), (
        f"the redirect {location!r} addresses no step, so a browser lands at "
        "the top of the list"
    )
    assert _CREATED_PARAM in dict(parse_qsl(urlsplit(location).query)), (
        f"the redirect {location!r} does not carry the created step's identity "
        f"as the {_CREATED_PARAM!r} parameter — a fragment alone never reaches "
        "the server"
    )
    assert _addresses(listed, identifier), (
        "the created step's row carries no addressing id, so the fragment "
        "lands on nothing"
    )


def test_a_step_created_as_a_draft_is_addressed_where_it_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step created as a draft is addressed where it renders.

    WHEN a step is created from the create surface as a `draft`, with no
    narrowing active
    THEN the step list is shown again with the created step rendered
    among the non-active steps, set apart from the served set and holding
    no position in its gate's order
    AND the list addresses that step directly.

    "Set apart, holding no position" is read the way the served
    requirement *Steps that are not active are visible to authors and set
    apart* already fixes it, and the way its own test reads it: the step
    renders outside the gate's orderable list, so no reorder control
    names it, while the gate's active steps stay reorderable.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    _control, surface, form = _open_create_surface(client, _get_page(client))

    values = _valid_create_values(
        surface,
        form,
        name="Work written down before it is ready",
        gate="listable",
        status=StepStatus.DRAFT,
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    location, listed = _land(client, response)
    created = _the_one_created(store, before)
    identifier = created.definition.identifier
    # SPECIFIED: created as a draft, and rendered.
    assert created.definition.status is StepStatus.DRAFT
    assert identifier in listed
    # SPECIFIED: set apart from the served set — outside the gate's
    # orderable list, holding no position in its order.
    assert _reorder_control_for(listed, identifier) is None, (
        "the created draft offers a reorder control, so it was placed inside "
        "the gate's served order"
    )
    # DERIVED sanity guard: the gate's active steps *are* reorderable, so
    # the absence above is about the draft and not about a page that
    # reorders nothing.
    assert _reorder_control_for(listed, "listing.zeta") is not None, (
        "the gate's active steps are not reorderable at all"
    )
    # SPECIFIED: the list addresses that step directly — wherever it
    # rendered, which is not the served order.
    assert _fragment_addresses(location, identifier), location
    assert _addresses(listed, identifier), (
        "a created draft is addressed nowhere, so the addressing assumes the "
        "created step joined the served order"
    )


def test_a_created_step_the_narrowing_keeps_visible_is_still_identified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A created step the narrowing keeps visible is still
    identified.

    WHEN a step is created under a narrowing the created step matches
    THEN the step list is shown under that narrowing with the created
    step rendered
    AND the list addresses that step directly.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    narrowing = _narrowing(gate="listable")
    narrowed = _get_page(client, params=narrowing)
    assert "hold.commit" not in narrowed  # the narrowing really narrowed
    _control, surface, form = _open_create_surface(client, narrowed)

    values = _valid_create_values(
        surface,
        form,
        name="Work created under a filter it matches",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    location, listed = _land(client, response)
    identifier = _the_one_created(store, before).definition.identifier
    # SPECIFIED: the list is shown under that narrowing.
    assert "hold.commit" not in listed, (
        "the create widened the list past the gate filter that was active"
    )
    assert _rendered_filter(listed, _FILTER_PARAMS["gate"]) == "listable"
    # SPECIFIED: with the created step rendered, and addressed directly.
    assert identifier in listed
    assert _fragment_addresses(location, identifier), location
    assert _addresses(listed, identifier)
    # SPECIFIED: the notice is rendered *only* where clearing the
    # narrowing would reveal the named step — here it is already
    # revealed, so no offer to clear is made.
    assert _clear_offer(listed, identifier) is None, (
        "the list offers to clear a narrowing that is already showing the created step"
    )


def test_a_create_the_narrowing_would_hide_is_not_left_looking_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A create the narrowing would hide is not left looking
    lost.

    WHEN a step is created while a search is active that matches neither
    the created step's name nor its description
    THEN the step list is shown under that search
    AND names the created step and states that it falls outside the
    active narrowing, offering to clear the narrowing
    AND taking that offer shows the list with the narrowing cleared,
    still addressing the created step rather than the top of the set.

    The search term matches one seeded step and nothing else, so the
    narrowed list is neither empty nor whole — and it matches neither the
    created step's name nor its (absent) description.
    """
    needle = "unmistakable-needle"
    sought = _Record(
        _step(
            identifier="listing.sought",
            name=f"Carries the {needle} in its wording",
        ),
        display_order=20,
    )
    store = _seeded_store(extra=(*_listable_extras(), sought))
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    narrowed = _get_page(client, params=_narrowing(search=needle))
    assert "listing.sought" in narrowed
    assert "hold.commit" not in narrowed  # the search really narrowed
    _control, surface, form = _open_create_surface(client, narrowed)

    values = _valid_create_values(
        surface,
        form,
        name="Work the active search does not match",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    _location, listed = _land(client, response)
    identifier = _the_one_created(store, before).definition.identifier
    # SPECIFIED: the list is shown under that search — the narrowing wins.
    assert "hold.commit" not in listed, "the create cleared the active search"
    assert _rendered_filter(listed, _FILTER_PARAMS["search"]) == needle
    # SPECIFIED: it names the created step and says it falls outside the
    # narrowing. DERIVED wording markers, per this file's docstring.
    assert _names_the_step_as_outside(listed, identifier), (
        "the list neither names the created step nor says it falls outside "
        f"the narrowing, so the create looks lost: {listed[:2000]}"
    )
    # SPECIFIED: offering to clear the narrowing.
    offer = _clear_offer(listed, identifier)
    assert offer is not None, (
        "the list makes no offer carrying the created step forward, so "
        "clearing the narrowing would land at the top of the whole set"
    )
    # SPECIFIED: taking that offer clears the narrowing and still
    # addresses the created step.
    taken = _issue(client, offer)
    assert taken.status_code == 200, taken.text
    cleared = str(taken.text)
    assert "hold.commit" in cleared, "taking the offer did not clear the search"
    assert identifier in cleared
    assert _addresses(cleared, identifier)
    assert _fragment_addresses(offer.url, identifier), (
        f"the offer {offer.url!r} carries no fragment addressing the created "
        "step, so clearing the narrowing lands at the top of the set"
    )


def test_a_step_named_as_created_but_not_there_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A step named as created but not there is ignored.

    WHEN the list is requested naming a created step that the page's read
    does not return at all
    THEN the list renders as it would without that name
    AND states nothing about a step falling outside the narrowing.

    A narrowing is active throughout, and a *live* step's name is
    requested first: the requirement's rule is "render the notice only
    where clearing the narrowing it offers to clear would reveal the
    named step", so a page obeying it renders the offer for the live
    step and withholds it for the absent one. Without that first half
    the absence asserted below would be satisfied by a page that renders
    no notice at all — the state this capability is in before the change
    lands, and not evidence of the rule.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    absent = "mg.listing.no-such-step-was-ever-created"
    narrowing = _narrowing(gate="order")

    present = _get_page(client, params={**narrowing, _CREATED_PARAM: "listing.zeta"})
    plain = _get_page(client, params=narrowing)
    named = _get_page(client, params={**narrowing, _CREATED_PARAM: absent})

    # SPECIFIED (the rule's positive half): a named step this narrowing
    # hides, and clearing it would reveal, does get the offer.
    assert "listing.zeta" not in plain  # the narrowing really hides it
    assert _clear_offer(present, "listing.zeta") is not None, (
        "the list makes no offer for a named step the narrowing hides, so "
        "the absence below is a page that never renders the notice rather "
        "than one applying the rule"
    )
    # SPECIFIED: the list renders as it would without that name — the
    # same steps, in the same order.
    for identifier in _identifiers(store):
        assert (identifier in named) == (identifier in plain), (
            f"naming an absent created step changed whether {identifier} renders"
        )
    # SPECIFIED: and states nothing about a step falling outside the
    # narrowing — it neither names the absent step nor offers to clear.
    assert absent not in named, "the list names a step its own read never returned"
    assert _clear_offer(named, absent) is None


def test_a_draft_the_narrowing_would_hide_is_named_like_any_other_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A draft the narrowing would hide is named like any other
    step.

    WHEN a step is created as a `draft` while a gate filter is active
    that its gate does not match
    THEN the step list is shown under that filter
    AND names the created step and offers to clear the filter, exactly as
    it would for a step created `active`.

    The trap this closes: a notice keyed on the *served* set would
    suppress itself for every non-active create, which is exactly the
    create the notice exists to find.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    narrowed = _get_page(client, params=_narrowing(gate="order"))
    assert "hold.order" in narrowed
    assert "hold.listable" not in narrowed  # the filter really narrowed
    _control, surface, form = _open_create_surface(client, narrowed)

    values = _valid_create_values(
        surface,
        form,
        name="A draft written into a gate the filter hides",
        gate="listable",
        status=StepStatus.DRAFT,
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    _location, listed = _land(client, response)
    created = _the_one_created(store, before)
    identifier = created.definition.identifier
    assert created.definition.status is StepStatus.DRAFT
    # SPECIFIED: the list is shown under that filter.
    assert "hold.listable" not in listed, "the create cleared the gate filter"
    assert _rendered_filter(listed, _FILTER_PARAMS["gate"]) == "order"
    # SPECIFIED: naming the created step and offering to clear the
    # filter — exactly as for an `active` create.
    assert _names_the_step_as_outside(listed, identifier), (
        f"a created draft the filter hides is left looking lost: {listed[:2000]}"
    )
    assert _clear_offer(listed, identifier) is not None, (
        "the list offers no clear for a created draft, so the notice is keyed "
        "on the served set rather than on what the page's read returns"
    )


def test_a_named_step_the_offer_could_not_reveal_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A named step the offer could not reveal is ignored.

    WHEN the list is requested naming a created step that has since been
    retired, from a view that does not reveal retired steps
    THEN the list renders as it would without that name
    AND does not offer to clear a narrowing that would not reveal it.

    A retired step *is* still returned by the page's own read — the
    retired-steps control filters it out afterwards — so a naive
    "returned but hidden" test would fire here and offer a clear that
    reveals nothing.
    """
    retired = _Record(
        _step(
            identifier="listing.retired-since",
            name="Work retired since it was created",
            status=StepStatus.RETIRED,
        ),
        display_order=20,
    )
    retired.retired_by = "olena"
    retired.retired_on = "2026-08-01"
    store = _seeded_store(extra=(*_listable_extras(), retired))
    client = _signed_client(monkeypatch, store)

    named = _get_page(client, params={_CREATED_PARAM: "listing.retired-since"})

    # DERIVED sanity guard: the page's read *does* return the step — it
    # is the retired-steps control that hides it, which is what makes
    # this the case the rule is written for.
    revealed = _get_page(client, params={_RETIRED_PARAM: "1"})
    assert "listing.retired-since" in revealed
    # SPECIFIED (the rule's positive half): a named step a *clearable*
    # narrowing hides does get the offer, so the absence asserted below
    # is the rule applied and not a page that renders no notice at all.
    hidden_by_a_filter = _get_page(
        client,
        params={**_narrowing(gate="order"), _CREATED_PARAM: "listing.zeta"},
    )
    assert _clear_offer(hidden_by_a_filter, "listing.zeta") is not None, (
        "the list makes no offer for a named step a clearable narrowing "
        "hides, so the absence below establishes nothing about the rule"
    )
    # SPECIFIED: the list renders as it would without that name.
    assert "listing.retired-since" not in named, (
        "the list names a retired step that clearing the narrowing it offers "
        "would not reveal"
    )
    # SPECIFIED: and offers no clear that would reveal nothing.
    assert _clear_offer(named, "listing.retired-since") is None


def test_a_rejected_create_keeps_every_submitted_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected create keeps every submitted value.

    WHEN a submitted create is rejected by validation
    THEN the re-rendered create surface reports every fault the write
    reported
    AND every submitted value, the timing anchor's included, is still in
    the form
    AND the served step set is unchanged.

    Two faults at once, so "every fault" is not vacuously satisfied by
    one: an `active` `human` step naming no assignee, and a `human` step
    carrying an automation brief.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = store.records
    _control, surface, form = _open_create_surface(client, _get_page(client))

    values = _valid_create_values(
        surface,
        form,
        name="Work whose create is refused",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    values = _fill(values, anchor_days="-21")
    submitted = _rejecting(values)
    response = _issue(client, form, data=submitted, follow_redirects=False)

    assert response.status_code < 500, response.text
    body = str(response.text)
    # SPECIFIED: the *create surface* re-renders — not the list.
    rerendered = _create_form_of(body)
    assert rerendered is not None, (
        f"a rejected create did not re-render the create surface: {body[:2000]}"
    )
    # SPECIFIED: every fault the write reported. DERIVED wording markers.
    lowered = body.lower()
    assert "handler" in lowered, "the handler fault is not reported"
    assert "assignee" in lowered or "member" in lowered, (
        "the missing-assignee fault is not reported"
    )
    # SPECIFIED: every submitted value, the timing anchor's included, is
    # still in the form. Hidden inputs are excluded: they are routing
    # values a browser posts and nobody types.
    held = rerendered.data()
    for name, value in submitted.items():
        if name in rerendered.hidden_names:
            continue
        assert held.get(name) == value, (
            f"the re-rendered create surface lost the submitted {name!r}: "
            f"{held.get(name)!r} instead of {value!r}"
        )
    assert held.get(_field_named(submitted, "anchor_days")) == "-21"
    # SPECIFIED: the served step set is unchanged.
    assert store.saves == []
    assert store.records == before


def test_a_rejected_create_keeps_every_assignee_that_was_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected create keeps every assignee that was named.

    WHEN a create naming two assignees is rejected by validation
    THEN the re-rendered create surface still shows both of them named
    AND neither is dropped nor replaced by the other.

    Two is the narrowest case distinguishing "holds what was typed" from
    "holds one of what was typed" — a flat `dict[str, str]` keeps only
    the last value under a repeated key.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    _control, surface, form = _open_create_surface(client, _get_page(client))

    values = _valid_create_values(
        surface,
        form,
        name="Work two colleagues share",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    values = _fill(values, handler=_A_HANDLER)  # the one fault
    assignee_field = _field_named(values, "assignee")
    # A dict whose value is a list, not a list of pairs: httpx2 refuses to
    # form-encode a sequence of tuples — it treats the sequence as raw
    # content and the request arrives carrying no fields at all. This is
    # the only shape that actually puts a repeated key on the wire, which
    # is the whole point of the scenario.
    payload: dict[str, Any] = {
        name: value for name, value in values.items() if name != assignee_field
    }
    payload[assignee_field] = [ALICE, BOHDAN]

    response = _issue(client, form, data=payload, follow_redirects=False)

    assert response.status_code < 500, response.text
    body = str(response.text)
    rerendered = _create_form_of(body)
    assert rerendered is not None, (
        f"a rejected create did not re-render the create surface: {body[:2000]}"
    )
    # SPECIFIED: both are still named, and neither was dropped nor
    # replaced by the other.
    selected = rerendered.selected_of(assignee_field)
    assert set(selected) == {ALICE, BOHDAN}, (
        f"the re-rendered create surface names {selected} where two members "
        "were submitted — a set of named members is exactly what a rejection "
        "must not lose"
    )
    assert store.saves == []


def test_a_rejected_create_keeps_the_submitted_discipline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected create keeps the submitted discipline.

    WHEN a create submitting a discipline other than the first offered is
    rejected by validation
    THEN the re-rendered create surface still shows the submitted
    discipline selected
    AND a corrected resubmission generates an identifier carrying that
    discipline.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = _identifiers(store)
    _control, surface, form = _open_create_surface(client, _get_page(client))

    discipline_field = _field_named(form.data(), "discipline")
    offered = form.options_of(discipline_field)
    assert offered, f"the create surface offers no discipline options: {offered}"
    assert offered[0][0] != ANOTHER_DISCIPLINE.value, (
        f"{ANOTHER_DISCIPLINE.value!r} is the first discipline offered, so this "
        "test would not distinguish a kept value from a silent default — "
        "correct `ANOTHER_DISCIPLINE` to one that is not first"
    )

    values = _valid_create_values(
        surface,
        form,
        name="Work of another discipline",
        gate="listable",
        status=StepStatus.ACTIVE,
        discipline=ANOTHER_DISCIPLINE,
    )
    values = _fill(values, handler=_A_HANDLER)  # the one fault
    response = _issue(client, form, data=values, follow_redirects=False)

    assert response.status_code < 500, response.text
    body = str(response.text)
    rerendered = _create_form_of(body)
    assert rerendered is not None, (
        f"a rejected create did not re-render the create surface: {body[:2000]}"
    )
    # SPECIFIED: the submitted discipline is still selected — not
    # reverted to the first option.
    assert rerendered.data().get(discipline_field) == ANOTHER_DISCIPLINE.value, (
        "the rejected create reverted the discipline, so the corrected "
        "resubmission would generate an identifier that cannot be corrected"
    )
    # SPECIFIED: a corrected resubmission generates an identifier
    # carrying that discipline.
    corrected = _fill(rerendered.data(), handler="", assignee=ALICE)
    landed = _issue(client, rerendered, data=corrected, follow_redirects=False)
    _land(client, landed)
    identifier = _the_one_created(store, before).definition.identifier
    assert ANOTHER_DISCIPLINE.value in identifier.split("."), (
        f"the generated identifier {identifier!r} carries a discipline the "
        "resubmission did not name"
    )


def test_a_create_naming_no_discipline_is_refused_not_defaulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A create naming no discipline is refused, not defaulted.

    WHEN a create is submitted carrying no discipline at all
    THEN it is refused without a create surface being rendered, and
    nothing is persisted
    AND no step is created carrying a discipline the submission did not
    name.

    The surface's own selector always submits a discipline, so this is a
    request only a hand-built one can make — and there is no half-typed
    form to hand back.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = store.records
    _control, surface, form = _open_create_surface(client, _get_page(client))

    values = _valid_create_values(
        surface,
        form,
        name="Work naming no discipline",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    response = _issue(
        client, form, data=_without(values, "discipline"), follow_redirects=False
    )

    # SPECIFIED: nothing is persisted, and no step carries a discipline
    # the submission did not name.
    assert store.saves == [], "a create naming no discipline was persisted"
    assert store.records == before
    # SPECIFIED: refused *without a create surface being rendered* —
    # there is no admin mid-edit whose values must survive.
    assert _create_form_of(str(response.text)) is None, (
        "the refusal rendered a create surface, inventing a session that never existed"
    )
    # DERIVED: a refusal that neither renders a form nor persists reads
    # as an error status; the binding halves are the two above.
    assert response.status_code >= 400, (
        f"the create was answered {response.status_code} rather than refused: "
        f"{response.text[:1000]}"
    )


def test_a_create_naming_a_retired_status_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A create naming a retired status is refused.

    WHEN a create is submitted naming `retired` as the status
    THEN it is refused without a create surface being rendered, and
    nothing is persisted
    AND the create surface offers no such status to begin with.

    Leaving this to the rendered control alone would rest the rule on
    markup, which this capability already declines to do for reordering.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    before = store.records
    _control, surface, form = _open_create_surface(client, _get_page(client))

    # SPECIFIED: the surface offers no `retired` status to begin with.
    status_field = _field_named(form.data(), "status")
    offered = form.options_of(status_field)
    assert offered, f"the create surface offers no status options: {offered}"
    retired = _status_value(StepStatus.RETIRED)
    assert all(value != retired for value, _label in offered), (
        f"the create surface offers {retired!r} among the statuses a step can "
        f"be created with: {offered}"
    )

    values = _valid_create_values(
        surface,
        form,
        name="Work created straight into retirement",
        gate="listable",
        status=StepStatus.ACTIVE,
    )
    response = _issue(
        client,
        form,
        data=_fill(values, status=retired),
        follow_redirects=False,
    )

    # SPECIFIED: refused server-side too, without a create surface, and
    # nothing persisted.
    assert store.saves == [], "a create naming `retired` was persisted"
    assert store.records == before
    assert _create_form_of(str(response.text)) is None, (
        "the refusal rendered a create surface, inventing a session that never existed"
    )
    assert response.status_code >= 400, (
        f"the create was answered {response.status_code} rather than refused: "
        f"{response.text[:1000]}"
    )


def test_a_stale_create_is_surfaced_not_silently_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stale create is surfaced, not silently dropped.

    WHEN a create is submitted after another write has changed the step
    set
    THEN nothing is persisted and the surface states the set changed
    underneath the create
    AND the submitted values are still in the form.
    """
    store = _seeded_store(extra=_listable_extras(), store_class=_StaleStepStore)
    client = _signed_client(monkeypatch, store)
    before = store.records
    _control, surface, form = _open_create_surface(client, _get_page(client))

    typed = "Work whose set moved underneath it"
    values = _valid_create_values(
        surface, form, name=typed, gate="listable", status=StepStatus.ACTIVE
    )
    response = _issue(client, form, data=values, follow_redirects=False)

    assert response.status_code < 500, response.text
    body = str(response.text)
    # SPECIFIED: nothing is persisted.
    assert store.saves == []
    assert store.records == before
    # SPECIFIED: the surface says the set changed underneath the create.
    # DERIVED wording marker, as the stale edit and the stale move record.
    assert "changed" in body.lower(), body[:2000]
    # SPECIFIED: the submitted values are still in the form.
    rerendered = _create_form_of(body)
    assert rerendered is not None, (
        f"a stale create did not re-render the create surface: {body[:2000]}"
    )
    assert typed in body
    held = rerendered.data()
    for name, value in values.items():
        if name in rerendered.hidden_names:
            continue
        assert held.get(name) == value, (
            f"the re-rendered create surface lost the submitted {name!r}: "
            f"{held.get(name)!r} instead of {value!r}"
        )


# ---------------------------------------------------------------------------
# MODIFIED requirement: The narrowed view survives every write and every
# move between views — the two scenarios this change adds
# ---------------------------------------------------------------------------


def test_a_rejected_creation_keeps_the_narrowing_without_leaving_the_create_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected creation keeps the narrowing without leaving
    the create surface.

    WHEN a creation is rejected while a text search is active
    THEN the create surface re-renders with its faults and the submitted
    values, as the creation requirement requires
    AND returning to the list from that surface applies the search term.

    The search term matches one seeded step's name and no other, so the
    narrowing is unmistakable in what the list does and does not hold.
    """
    needle = "stock-ready"
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    narrowed = _get_page(client, params=_narrowing(search=needle))
    assert "hold.stock-ready" in narrowed
    assert "hold.commit" not in narrowed  # the search really narrowed
    _control, surface, form = _open_create_surface(client, narrowed)

    typed = "Work rejected under an active search"
    values = _valid_create_values(
        surface, form, name=typed, gate="listable", status=StepStatus.ACTIVE
    )
    response = _issue(client, form, data=_rejecting(values), follow_redirects=False)

    assert response.status_code < 500, response.text
    rejected = str(response.text)
    # SPECIFIED: the create surface re-renders with its faults and the
    # submitted values — it did not become the list.
    assert store.saves == []
    assert _create_form_of(rejected) is not None, (
        f"the rejection left the create surface: {rejected[:2000]}"
    )
    assert typed in rejected
    assert "handler" in rejected.lower()
    # SPECIFIED: returning to the list from that surface applies the
    # search term.
    listed = _back_to_list(client, rejected, marker="hold.stock-ready")
    assert "hold.commit" not in listed, (
        "leaving the rejected create surface widened the list past the search"
    )
    assert _rendered_filter(listed, _FILTER_PARAMS["search"]) == needle


def test_opening_and_leaving_the_create_surface_preserves_the_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Opening and leaving the create surface preserves the
    narrowing.

    WHEN the create surface is opened from a narrowed list and left
    without creating
    THEN the list re-renders under the same narrowing.
    """
    other_discipline = _Record(
        _step(
            identifier="listing.other-discipline",
            name="Work of listing.other-discipline",
            discipline=ANOTHER_DISCIPLINE,
        ),
        display_order=40,
    )
    store = _seeded_store(extra=(*_listable_extras(), other_discipline))
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=A_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)
    assert "hold.commit" not in narrowed
    assert "listing.other-discipline" not in narrowed

    _control, surface, _form = _open_create_surface(client, narrowed)
    listed = _back_to_list(client, surface, marker="listing.zeta")

    # SPECIFIED: the list re-renders under the same narrowing — both
    # halves of it, and nothing was written along the way.
    assert store.saves == []
    assert "hold.commit" not in listed, (
        "leaving the create surface widened the list past the gate filter"
    )
    assert "listing.other-discipline" not in listed, (
        "leaving the create surface widened the list past the discipline filter"
    )
    assert _rendered_filter(listed, _FILTER_PARAMS["gate"]) == "listable"
    assert _rendered_filter(listed, _FILTER_PARAMS["discipline"]) == A_DISCIPLINE.value
