"""The playbook steps management page (`playbook-admin`), plus the
absence-shaped guard on its routes (`admin-session`, fourth requirement).

Derived strictly from the delta specs:
`openspec/changes/add-playbook-admin-ui/specs/playbook-admin/spec.md`
(all five requirements, all twelve scenarios) and
`.../specs/admin-session/spec.md` (*Admin access fails closed and
absence-shaped* — the response-shape halves; the directory-revocation
verification halves live in
`tests/unit/access/application/test_admin_session_use_cases.py`).

Every `playbook-admin` scenario is stated over the rendered page and the
writes made from it, so the routes over a step-store double are the
smallest observing unit. The page is HTML end to end (`proposal.md` —
"Not in this change ... any JSON API"), so these tests drive it the way
a browser does: they *discover* the page's own controls (forms,
`hx-get`/`hx-post`/... attributes) and submit them, pinning as little of
the URL surface as possible.

## What is fixed, and what is INVENTED

Fixed by the artifacts: admin routes and templates in
`launch/infrastructure/driving/` (`proposal.md` Impact); the page
consumes only the launch public application surface; every write goes
through the authoring use cases; a failed guard yields the app's own
404 shape produced by one dependency (`design.md` Decision 7); reorder
rides up/down buttons (`design.md` Decision 8).

INVENTED, recorded in the manifest as unresolved project questions,
correction points named:

- The module `commerce_ops.launch.infrastructure.driving.playbook_admin`
  exposing `router`. Correction point: the import and `_app` below.
- The step store as a module-level `steps` name, substituted with
  `monkeypatch.setattr` (raising) — the `test_clickup_webhook.py`
  convention. Its protocol and record shape are the ones
  `test_playbook_reorder.py` records (`load`/`save`, `definition`,
  `display_order`, attribution fields); the files correct together.
- The guard consumes `verify_admin_session` imported into the page
  module from the access public surface (`design.md` Decision 6);
  monkeypatched here with a fake that answers the principal only for
  one known session value, whatever the call shape. The *response
  shape* on refusal is real page code and is what the guard tests
  assert. Correction point: `_fake_verify`.
- The session cookie's name: `admin_session`. Correction point:
  `_SESSION_COOKIE`.
- Query-parameter names for narrowing: `gate`, `discipline`, `q`
  (search), `retired` (reveal retired). The retired control is first
  discovered from the page itself (a control whose URL mentions
  "retired"); the parameter is the fallback. Correction points:
  `_FILTER_PARAMS`, `_retired_view`.
- Control-discovery vocabulary: an edit control's URL mentions the step
  and "edit"; retire/un-retire mention "retire"/"unretire"; the upward
  reorder control mentions "up" or "top" (`design.md` fixes up/down
  buttons; the spelling is the guess). Correction point: `_control`.
- Fault-wording markers on rejected writes are DERIVED, as
  `test_playbook_authoring.py` records for the same faults: substrings
  distinguish the two faults, and correcting them to the implemented
  wording is a fixture correction; collapsing to one fault is not.

## Expected first-run state

The page module does not exist, so every test fails at import — the
absent-target state; the assertions have not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin

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
ANOTHER_DISCIPLINE: Final = DISCIPLINES[1]

_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}


# ---------------------------------------------------------------------------
# Step-store double (the shape test_playbook_reorder.py records)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "assignees": (ASSIGNEE,),
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": None,
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


def _is_retired(record: Any) -> bool:
    """Read off the *status*, not the attribution.

    `redesign-step-fields` (design.md Decision 2) made the status the one
    answer to "is this step in play"; the attribution columns stay,
    recording who moved the step and when."""
    return record.definition.status is StepStatus.RETIRED


def _is_active(record: Any) -> bool:
    """Whether the step is served — and so whether it holds a slot."""
    return record.definition.status is StepStatus.ACTIVE


def _seeded_store(
    extra: tuple[_Record, ...] = (),
    store_class: type[_FakeStepStore] = _FakeStepStore,
) -> _FakeStepStore:
    """One blocking step per gate (descriptions carry the identifier, so
    a table rendering either is locatable by the same substring), plus
    the given extra records."""
    records = (
        tuple(
            _Record(
                _step(
                    identifier=f"hold.{gate}",
                    name=f"Blocking work of hold.{gate}",
                    gate=gate,
                    blocking=True,
                    kind=StepKind.AUTOMATED,
                    status=StepStatus.ACTIVE,
                    automation_brief="Held until the automated check reports green.",
                    handler="fixture.holding_check",
                ),
                display_order=10,
            )
            for gate in SPECIFIED_GATE_ORDER
        )
        + extra
    )
    return store_class(records)


def _listable_extras() -> tuple[_Record, ...]:
    """Two non-blocking `listable` steps whose authored order disagrees
    with identifier order (`zeta` before `alpha`), so ordered rendering
    cannot pass by sorting identifiers."""
    return (
        _Record(
            _step(
                identifier="listing.zeta",
                name="Work of listing.zeta",
                discipline=A_DISCIPLINE,
            ),
            display_order=20,
        ),
        _Record(
            _step(
                identifier="listing.alpha",
                name="Work of listing.alpha",
                discipline=ANOTHER_DISCIPLINE,
            ),
            display_order=30,
        ),
    )


def _record_named(store: _FakeStepStore, identifier: str) -> _Record:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


# ---------------------------------------------------------------------------
# HTML discovery: forms and HTMX controls, the way a browser sees them
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


class _PageParser(HTMLParser):
    """Collects submit-able things: forms (with their fields) and any
    element carrying an `hx-*` request attribute or an `href`."""

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
    """The first form or control whose URL (plus, for forms, its
    serialized fields) mentions every `contains` substring."""
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


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


# `redesign-step-fields`: the page reads the roster to offer assignees and
# to validate them, so the fixture supplies one. `ASSIGNEE` is named on
# every step below because an `active` `human` step the write touches must
# name someone active — which is the rule, not a fixture convenience.
ASSIGNEE = "prs_01HQ8Z6M4A"
ASSIGNEE_NAME = "Alice Admin"


class _FakePerson:
    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_FakePerson, ...]:
        return (_FakePerson(ASSIGNEE, ASSIGNEE_NAME),)


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    """Answers the principal only for the one known session value,
    whatever the verification call shape is."""
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _app(monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "roster", _FakeRoster())
    app = FastAPI()
    app.include_router(page_module.router)
    return TestClient(app)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    client = _app(monkeypatch, store)
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    return client


def _page_path() -> str:
    """The step-table page: the shortest parameterless GET route the
    page router exposes."""
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


def _submit(client: TestClient, method: str, url: str, data: dict[str, str]) -> Any:
    if not url:
        target = _page_path()
    elif url.startswith("/"):
        target = url
    else:
        target = urljoin(_page_path() + "/", url)
    return client.request(method.upper(), target, data=data)


def _positions(html: str, *needles: str) -> list[int]:
    positions = []
    for needle in needles:
        at = html.find(needle)
        assert at >= 0, f"{needle!r} not rendered"
        positions.append(at)
    return positions


def _edit_form(client: TestClient, page_html: str, step_id: str) -> dict[str, Any]:
    """Open the step's inline edit form the way the page offers it.

    Answers the parsed form: `method`, `url`, `fields`, and `hidden`
    (the names of hidden inputs — routing values a browser posts but no
    one types into).
    """
    found = _control(page_html, contains=(step_id, "edit"))
    if found is not None:
        method, url, fields = found
        if not fields:  # a control that fetches the form fragment
            response = _submit(client, method, url, {})
            assert response.status_code == 200, response.text
            for form in _parse(response.text).forms:
                if any("description" in name for name in form["fields"]):
                    return form
    for form in _parse(page_html).forms:  # inline form already on the page
        haystack = form["url"] + " " + str(form["fields"])
        if step_id in haystack and any(
            "description" in name for name in form["fields"]
        ):
            return form
    pytest.fail(
        f"no edit form for {step_id!r} was discoverable — correct the "
        "control vocabulary in this file's docstring to the implemented page"
    )


# ---------------------------------------------------------------------------
# admin-session: Admin access fails closed and absence-shaped
# ---------------------------------------------------------------------------


def _shape(response: Any) -> tuple[int, bytes, str | None]:
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
    )


def test_no_session_means_no_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: No session means no surface — with the response-shape
    halves of the expired/revoked-session scenarios, whose verification
    halves are use-case-tier: any request `verify_admin_session` refuses
    takes the same shape as one bearing no session at all.

    WHEN an admin route is requested without a session, and with a
    session verification refuses
    THEN each response is identical in shape to requesting a route that
    does not exist.
    """
    client = _app(monkeypatch, _seeded_store())
    nothing = _shape(client.get("/a-route-that-was-never-registered"))

    without_session = client.get(_page_path())
    client.cookies.set(_SESSION_COOKIE, "a-session-verification-refuses")
    with_refused_session = client.get(_page_path())

    # SPECIFIED: the absence shape, revealing neither the surface nor
    # the reason — and the two refusals are indistinguishable.
    assert _shape(without_session) == nothing
    assert _shape(with_refused_session) == nothing
    # DERIVED sanity guard: a verified session does see the surface, so
    # the equalities above are not an artifact of a dead router.
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    assert client.get(_page_path()).status_code == 200


# ---------------------------------------------------------------------------
# Requirement: The step table shows the live set whole
# ---------------------------------------------------------------------------


def test_the_whole_live_set_is_one_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The whole live set is one page.

    WHEN the admin page is opened with no filter active
    THEN every live step is rendered, grouped by gate in gate order,
    each gate's steps in authored order.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: every live step is rendered.
    for record in store.records:
        assert record.definition.identifier in html or (
            record.definition.name in html
        ), f"{record.definition.identifier} is not rendered"
    # SPECIFIED: grouped by gate in gate order — every earlier gate's
    # steps precede every later gate's.
    gate_positions = _positions(
        html, *(f"hold.{gate}" for gate in SPECIFIED_GATE_ORDER)
    )
    assert gate_positions == sorted(gate_positions)
    listable = _positions(html, "listing.zeta", "listing.alpha")
    before_gate = html.find("hold.order")
    after_gate = html.find("hold.stock-ready")
    assert all(before_gate < at < after_gate for at in listable)
    # SPECIFIED: within the gate, the authored order — which here
    # disagrees with identifier order, so an identifier sort fails.
    hold_listable = html.find("hold.listable")
    assert hold_listable < listable[0] < listable[1]


def test_filters_narrow_without_altering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Filters narrow without altering.

    WHEN a gate filter and a discipline filter are applied together
    THEN only live steps matching both remain visible
    AND clearing the filters shows the full set unchanged.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    narrowed = _get_page(
        client,
        params={
            _FILTER_PARAMS["gate"]: "listable",
            _FILTER_PARAMS["discipline"]: ANOTHER_DISCIPLINE.value,
        },
    )

    # SPECIFIED: only steps matching both filters.
    assert "listing.alpha" in narrowed  # listable + ANOTHER_DISCIPLINE
    assert "listing.zeta" not in narrowed  # right gate, wrong discipline
    assert "hold.ignition" not in narrowed  # wrong gate
    # SPECIFIED: clearing shows the full set unchanged.
    cleared = _get_page(client)
    for identifier in ("listing.alpha", "listing.zeta", "hold.ignition"):
        assert identifier in cleared
    assert len(store.saves) == 0  # narrowing never wrote anything


def test_search_matches_description_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Search matches description text.

    WHEN a search term is entered
    THEN only steps whose description contains the term remain visible.
    """
    needle = "unmistakable-needle"
    extra = (
        _Record(
            _step(
                identifier="listing.sought",
                name=f"Carries the {needle} in its wording",
            ),
            display_order=20,
        ),
    )
    store = _seeded_store(extra=extra)
    client = _signed_client(monkeypatch, store)

    html = _get_page(client, params={_FILTER_PARAMS["search"]: needle})

    assert "listing.sought" in html
    assert "hold.commit" not in html
    assert "hold.ignition" not in html


def test_retired_steps_are_reachable_but_set_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Retired steps are reachable but set apart.

    WHEN the control revealing retired steps is engaged
    THEN retired steps render visibly marked as retired
    AND they are absent from the default view.
    """
    retired = _Record(
        _step(
            identifier="listing.retired-work",
            name="Retired work",
            status=StepStatus.RETIRED,
        ),
        display_order=20,
    )
    retired.retired_by = "olena"
    retired.retired_on = "2026-08-01"
    store = _seeded_store(extra=(retired,))
    client = _signed_client(monkeypatch, store)
    default_view = _get_page(client)

    # SPECIFIED: absent from the default view.
    assert "listing.retired-work" not in default_view

    # SPECIFIED: reachable through an explicit control on the page.
    control = _control(default_view, contains=("retired",))
    if control is not None:
        method, url, fields = control
        response = _submit(client, method, url, fields)
        assert response.status_code == 200
        revealed = response.text
    else:  # fallback: the invented query parameter
        revealed = _get_page(client, params={"retired": "1"})

    assert "listing.retired-work" in revealed
    # DERIVED marking: "retired" appears as the visible marking's
    # wording; the spec fixes that the step is *visibly marked*, not the
    # word.
    assert "retired" in revealed.lower()


# ---------------------------------------------------------------------------
# Requirement: A step can be edited in place
# ---------------------------------------------------------------------------


def test_a_clean_edit_lands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A clean edit lands.

    WHEN an edit with valid values is saved
    THEN the step re-renders with the new values.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    form = _edit_form(client, _get_page(client), "listing.zeta")

    reworded = "Work of listing.zeta, reworded on the page"
    response = _submit(
        client, form["method"], form["url"], _fill(form["fields"], name=reworded)
    )

    assert response.status_code == 200, response.text
    # SPECIFIED: re-rendered with the new values.
    assert reworded in response.text
    # SPECIFIED: saved through the authoring update write.
    assert _record_named(store, "listing.zeta").definition.name == reworded


def test_a_rejected_edit_shows_every_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A rejected edit shows every fault.

    WHEN a submitted edit violates two coherence rules at once
    THEN the re-rendered form reports both faults
    AND the submitted values are still in the form
    AND the served step set is unchanged.

    The two faults: a description spanning two lines, and a blocking
    flag on a `lesson`-bound step — both coherence rules of the
    launch-playbook spec.
    """
    lesson = _Record(
        _step(
            identifier="creative.image-advice",
            name="Advice on the hero image",
            blocking=False,
        ),
        display_order=20,
    )
    store = _seeded_store(extra=(lesson,))
    client = _signed_client(monkeypatch, store)
    records_before = store.records
    form = _edit_form(client, _get_page(client), "creative.image-advice")

    two_line = "Line one of the edited advice\nLine two of it"
    response = _submit(
        client,
        form["method"],
        form["url"],
        _fill(form["fields"], name=two_line, block="on"),
    )

    body = response.text
    # SPECIFIED: every fault is reported. DERIVED wording markers, per
    # the docstring: one fault about the description, one about
    # lesson/blocking.
    assert "creative.image-advice" in body
    assert "description" in body.lower()
    assert "lesson" in body.lower() or "block" in body.lower()
    # SPECIFIED: the submitted values are still in the form.
    assert "Line one of the edited advice" in body
    # SPECIFIED: the served step set is unchanged.
    assert store.saves == []
    assert store.records == records_before


def test_a_stale_edit_is_surfaced_not_silently_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stale edit is surfaced, not silently dropped.

    WHEN an edit is submitted after another write has changed the step
    set
    THEN nothing is persisted and the page states the set changed
    underneath the edit.
    """
    store = _seeded_store(extra=_listable_extras(), store_class=_StaleStepStore)
    client = _signed_client(monkeypatch, store)
    form = _edit_form(client, _get_page(client), "listing.zeta")

    response = _submit(
        client,
        form["method"],
        form["url"],
        _fill(form["fields"], name="A rewording that is stale"),
    )

    # SPECIFIED: nothing is persisted (the conditional save refused).
    assert store.saves == []
    assert (
        _record_named(store, "listing.zeta").definition.name == "Work of listing.zeta"
    )
    # SPECIFIED: the page says so. DERIVED wording marker: the statement
    # mentions the set having "changed"; correcting the substring to the
    # implemented wording is a fixture correction.
    assert "changed" in response.text.lower()


# ---------------------------------------------------------------------------
# Requirement: Steps can be created, retired and un-retired from the page
# ---------------------------------------------------------------------------


# `test_a_created_step_appears_in_its_gate` was removed by `add-step-page`.
# It submitted the create form with the default status — `draft` since
# `redesign-step-fields` — and asserted the step rendered last in its gate.
# It kept passing only because a draft renders in the *Not served at this
# gate* block below the gate's table, so it was asserting text position
# rather than gate order, while its docstring still reproduced the
# pre-change scenario. The revised scenario, which creates an `active`
# step and requires the list to address it, is covered by
# `test_playbook_admin_create_page.py`.


def test_a_blocked_retirement_explains_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A blocked retirement explains itself.

    WHEN retiring a step is rejected because its gate would be left with
    no blocking step
    THEN the page renders the fault naming that gate and the step
    remains live.

    `hold.stock-ready` is its gate's only blocking step; the gate name
    is distinctive enough to assert on without false positives.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    page = _get_page(client)
    method, url, fields = _require_control(
        page, contains=("hold.stock-ready", "retire"), excludes=("unretire",)
    )

    response = _submit(client, method, url, fields)

    # SPECIFIED: the fault names the gate that would be left unheld.
    assert "stock-ready" in response.text
    # SPECIFIED: the step remains live.
    assert not _is_retired(_record_named(store, "hold.stock-ready"))
    assert store.saves == []


# ---------------------------------------------------------------------------
# Requirement: A gate's steps can be reordered from the page
# ---------------------------------------------------------------------------


def test_a_move_sticks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A move sticks.

    WHEN a step is moved to the top of its gate on the page
    THEN the page shows it first in its gate
    AND a fresh page load shows the same order.

    `listing.zeta` holds the gate's second slot; one press of its upward
    control makes it the gate's first step.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    page = _get_page(client)
    found = _control(page, contains=("listing.zeta", "up")) or _control(
        page, contains=("listing.zeta", "top")
    )
    assert found is not None, (
        "no upward reorder control for listing.zeta was discovered — "
        "design.md fixes up/down buttons; correct the control vocabulary "
        "in this file's docstring to the implemented page"
    )
    method, url, fields = found

    response = _submit(client, method, url, fields)

    # SPECIFIED: the new order is visible immediately after the move.
    assert response.status_code == 200, response.text
    swapped = response.text
    if "hold.listable" in swapped:  # a fragment may re-render only the gate
        assert swapped.find("listing.zeta") < swapped.find("hold.listable")
    # SPECIFIED: a fresh page load shows the same order.
    reloaded = _get_page(client)
    assert reloaded.find("listing.zeta") < reloaded.find("hold.listable")
    assert reloaded.find("hold.listable") < reloaded.find("listing.alpha")
    # The write went through the reorder use case's store path.
    assert len(store.saves) == 1


def test_a_stale_move_leaves_truth_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stale move leaves truth on the page.

    WHEN a reorder is rejected because the step set changed underneath
    it
    THEN the page re-renders the served order and states why the move
    did not land.
    """
    store = _seeded_store(extra=_listable_extras(), store_class=_StaleStepStore)
    client = _signed_client(monkeypatch, store)
    page = _get_page(client)
    found = _control(page, contains=("listing.zeta", "up")) or _control(
        page, contains=("listing.zeta", "top")
    )
    assert found is not None, "no upward reorder control was discovered"
    method, url, fields = found

    response = _submit(client, method, url, fields)

    # SPECIFIED: nothing persisted; the rendered order matches the
    # served set.
    assert store.saves == []
    reloaded = _get_page(client)
    assert reloaded.find("hold.listable") < reloaded.find("listing.zeta")
    # SPECIFIED: and says why. DERIVED wording marker, as in the stale
    # edit above.
    assert "changed" in response.text.lower()


# ---------------------------------------------------------------------------
# Requirement: What authoring refuses to update renders read-only
# ---------------------------------------------------------------------------


def test_the_identifier_cannot_be_typed_into(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The identifier cannot be typed into.

    WHEN a step's inline edit form is opened
    THEN the identifier and discipline render as text, not as inputs.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    form = _edit_form(client, _get_page(client), "listing.zeta")

    # SPECIFIED: no *editable* input carries the identifier or the
    # discipline — their submission would only ever be refused. Hidden
    # inputs are routing values a browser posts but nobody types into,
    # so they are excluded.
    editable = [name for name in form["fields"] if name not in form["hidden"]]
    offending = [
        name
        for name in editable
        if "identifier" in name or "discipline" in name or name in ("id", "step_id")
    ]
    assert offending == [], (
        f"the edit form offers editable inputs for {offending} — the "
        "authoring capability refuses updates to these, so they must "
        "render as text"
    )
    # The form still has something editable (a description), so the
    # emptiness above is not a parsing artifact.
    assert any("description" in name for name in editable)
