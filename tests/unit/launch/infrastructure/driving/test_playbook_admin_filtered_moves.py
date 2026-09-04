"""The steps management page under an active narrowing: filters that
survive every write, per-gate positions, and filter-aware reordering
(`playbook-admin`).

Derived strictly from the delta spec
`openspec/changes/reorder-steps-under-filters/specs/playbook-admin/spec.md`
— its ADDED requirement in full, and only the scenarios its two MODIFIED
requirements genuinely add:

- ADDED *The narrowed view survives every write and every move between
  views* — all five scenarios.
- MODIFIED *The step table shows the live set whole* — the added
  scenario *A position is read against the whole gate*. Its four
  reproduced scenarios already have passing tests in
  `test_playbook_admin_page.py` beside this file and are not duplicated.
- MODIFIED *A gate's steps can be reordered from the page* — the ten
  added scenarios. Its two reproduced scenarios (*A move sticks*, *A
  stale move leaves truth on the page*) are likewise already covered
  there.

The manifest at
`openspec/changes/reorder-steps-under-filters/test-manifest.md` records
the already-covered scenarios and every classification below.

Every scenario is stated over the rendered page and the writes made from
it, so the routes over a step-store double are the smallest observing
unit — the same level and the same idiom `test_playbook_admin_page.py`
established: the page module's collaborators substituted with
`monkeypatch.setattr`, and the page driven the way a browser drives it,
by discovering its own controls rather than by pinning its URL surface.

The harness duplicates that file's doubles rather than importing them,
because `tests/unit/launch/infrastructure/driving/` carries no
`__init__.py` — it is not an importable package, and a cross-module test
import would depend on `pytest`'s sys.path insertion order.

## The move rule these tests encode

`design.md` — Decisions fixes the coordinate frame, and every expected
ordering below is derived from the **spec scenarios** within it, never
from the design's worked numbers. Writing `G` for a gate's live steps in
authored order, `V` for the visible subsequence and `G∖S` for `G`
without the moved step `S`:

- come to rest after visible step `P` → `S` is placed at
  `index of P in G∖S` + 1;
- the head of the visible list → at the index in `G∖S` of the first
  element of `V` other than `S`.

The requirement itself supplies the rest: *"Every step other than the
moved one SHALL keep its relative order, steps the filter is hiding
included."* That is what makes each expected full-gate ordering below a
**specified** value rather than an invented one — it is the only
ordering consistent with the scenario's placement clause plus that
invariant.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the filter travels in the query string, on every
form action and every link leaving the list (`design.md` — *One
`_filters_of(request)` helper*); a move names the visible step to come
to rest after, or the head, and carries the set version the page was
rendered from (`design.md` — *The client names a neighbour and a
version*); reordering goes inert under a description search and while
retired steps are shown, and is refused server-side there too.

INVENTED, each recorded in the manifest as an unresolved project
question with its correction point named:

- Query-parameter names for the narrowing: `gate`, `discipline`, `q`,
  `retired` — inherited from `test_playbook_admin_page.py`, which the
  implementation already satisfies. Correction points: `_FILTER_PARAMS`,
  `_RETIRED_PARAM`.
- How a move control is discovered. Two strategies are tried in order:
  the control names its neighbour, so a field value or the URL carries
  that step's identifier (`design.md`'s stated transport); failing that,
  the direction spellings `up`/`top` and `down`/`bottom`
  (`test_playbook_admin_page.py`'s existing vocabulary). Correction
  point: `_move_control`.
- How "the controls are inert" is read off the markup: a control is
  inert if it is absent, or carries `disabled`/`aria-disabled="true"` on
  the form, on a submit button inside it, or on the link. Correction
  point: `_ControlParser`.
- Wording markers on the notices — that a page saying reordering is
  unavailable mentions the reason (`search`, `retired`) and an
  unavailability word. These are DERIVED, as
  `test_playbook_admin_page.py` records for fault wording: correcting a
  substring to the implemented wording is a fixture correction;
  dropping the assertion is not.
- The rendered form of a position, `3 / 7` or `3 of 7`. Correction
  point: `_POSITION_PATTERN`.
- That a step's edit form is reached by following a GET control and is
  its own page carrying a link back to the list. Correction point:
  `_open_edit` and `_back_to_list`.

## Expected first-run state

The page module exists and its routes are live, so these tests do not
fail at import. They exercise behaviour this change ADDS against the
pre-change page, which carries the filter through nothing and reorders
against the whole gate — so each is expected to fail on a **wrong
value** (state 1), not on an absent target, and each therefore
discriminates from the first run.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here). The baseline is scoped to the two tiers
this change's tests are written into.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.application import reorder_step
from commerce_ops.launch.domain.launch_playbook import (
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
from tests.support.fixtures import PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _FakeMember
from tests.support.values import Record as _Record

DISCIPLINES: Final = tuple(Discipline)
#: `_step`'s default discipline, which the seeded holding steps carry —
#: so filtering *to* the other one hides them, as a narrowing must.
HIDDEN_DISCIPLINE: Final = DISCIPLINES[0]
VISIBLE_DISCIPLINE: Final = DISCIPLINES[1]

_FILTER_PARAMS: Final = {
    "gate": "gate",
    "discipline": "discipline",
    "search": "q",
}
_RETIRED_PARAM: Final = "retired"

#: A step's position within its gate, as rendered: "3 / 7" or "3 of 7".
_POSITION_PATTERN: Final = r"{position}\s*(?:/|\bof\b|\bout of\b)\s*{count}\b"

_UNAVAILABLE_WORDS: Final = (
    "unavailable",
    "not available",
    "cannot",
    "can't",
    "can not",
    "disabled",
    "inert",
    "refus",
    "not possible",
)
_REORDER_WORDS: Final = ("reorder", "re-order", "move", "moving", "ordering")


# ---------------------------------------------------------------------------
# Step-store double (the shape test_playbook_reorder.py records)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{"discipline": HIDDEN_DISCIPLINE, "assignees": (ASSIGNEE,), **overrides}
    )


class _FakeStepStore:
    def __init__(self, records: tuple[Any, ...], version: int = 41) -> None:
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

    def supersede(self) -> None:
        """A later accepted write lands on the set: the version moves on.

        The records are left alone deliberately — so that a move applied
        against this newer set would still be *observable* as a save,
        rather than being masked by a set the move can no longer address.
        """
        self.version += 1


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
    """One blocking step per gate, carrying `HIDDEN_DISCIPLINE`, plus the
    given extra records."""
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
                    handler="fixture.holding_check",
                ),
                display_order=10,
            )
            for gate in SPECIFIED_GATE_ORDER
        )
        + extra
    )
    return store_class(records)


def _listable_gate(*spec: tuple[str, bool]) -> tuple[_Record, ...]:
    """`(identifier, visible)` pairs, in authored order, appended to the
    `listable` gate after its holding step.

    `visible` decides only the discipline, so a discipline filter — which
    the requirement fixes as leaving reordering live — is what narrows
    the gate in every move test below.
    """
    return tuple(
        _Record(
            _step(
                identifier=identifier,
                name=f"Work of {identifier}",
                discipline=VISIBLE_DISCIPLINE if visible else HIDDEN_DISCIPLINE,
            ),
            display_order=(index + 2) * 10,
        )
        for index, (identifier, visible) in enumerate(spec)
    )


def _gate_order(store: _FakeStepStore, gate: str) -> list[str]:
    """The gate's live steps in served order — `display_order` with the
    identifier as the deterministic backstop, as
    `test_playbook_reorder.py` records."""
    live = [
        record
        for record in store.records
        if record.definition.gate == gate and _is_active(record)
    ]
    live.sort(key=lambda record: (record.display_order, record.definition.identifier))
    return [record.definition.identifier for record in live]


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


# ---------------------------------------------------------------------------
# HTML discovery: every submit-able control, and whether it is inert
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

    def data(self) -> dict[str, str]:
        return dict(self.fields)

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(value for _, value in self.fields)

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
    buttons: list[tuple[str, str, bool]] = field(default_factory=list)


class _ControlParser(HTMLParser):
    """Collects controls, tracking whether each is rendered inert.

    Inert means: `disabled` or `aria-disabled="true"` on the form, on a
    submit button inside it, or on the link — or a link with no
    destination. Single correction point for how the implemented page
    spells "inert".
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[_Control] = []
        self._form: _FormUnderConstruction | None = None
        self._select: str | None = None
        self._select_done = False
        self._textarea: str | None = None

    @staticmethod
    def _inert(a: dict[str, str]) -> bool:
        return "disabled" in a or a.get("aria-disabled", "").lower() == "true"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {key: value or "" for key, value in attrs}
        inert = self._inert(a)

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
            default = "on" if kind == "checkbox" else ""
            self._form.fields[name] = a.get("value", default)
        elif tag == "button":
            kind = (a.get("type") or "submit").lower()
            if kind == "submit":
                self._form.buttons.append(
                    (a.get("name", ""), a.get("value", ""), inert)
                )
        elif tag == "select":
            self._select = a.get("name")
            self._select_done = False
            if self._select:
                self._form.fields[self._select] = ""
        elif tag == "option" and self._select:
            if "selected" in a or not self._select_done:
                self._form.fields[self._select] = a.get("value", "")
                self._select_done = "selected" in a
        elif tag == "textarea":
            self._textarea = a.get("name")
            if self._textarea:
                self._form.fields[self._textarea] = ""

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea:
            self._form.fields[self._textarea] += data

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
        elif tag == "select":
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _controls(html: str) -> list[_Control]:
    parser = _ControlParser()
    parser.feed(html)
    return parser.controls


def _first_control(
    html: str,
    *,
    contains: tuple[str, ...],
    excludes: tuple[str, ...] = (),
    live_only: bool = True,
) -> _Control | None:
    for control in _controls(html):
        if live_only and control.inert:
            continue
        haystack = control.haystack
        if all(part in haystack for part in contains) and not any(
            part in haystack for part in excludes
        ):
            return control
    return None


def _require_control(
    html: str,
    *,
    contains: tuple[str, ...],
    excludes: tuple[str, ...] = (),
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


# ---------------------------------------------------------------------------
# Reorder-control discovery
# ---------------------------------------------------------------------------

_MOVE_HINTS: Final = (
    "move",
    "reorder",
    "position",
    "/order",
    "up",
    "down",
    "top",
    "bottom",
)
_UP_SPELLINGS: Final = ("up", "top")
_DOWN_SPELLINGS: Final = ("down", "bottom")


def _looks_like_a_move(control: _Control) -> bool:
    surface = (control.url + " " + " ".join(control.names)).lower()
    return any(hint in surface for hint in _MOVE_HINTS)


def _move_controls_mentioning(html: str, step: str) -> list[_Control]:
    return [
        control
        for control in _controls(html)
        if step in control.haystack and _looks_like_a_move(control)
    ]


def _live_move_controls(html: str, step: str) -> list[_Control]:
    return [
        control
        for control in _move_controls_mentioning(html, step)
        if not control.inert
    ]


def _move_control(
    html: str,
    *,
    step: str,
    names: str | None,
    others: tuple[str, ...],
    direction: str,
) -> _Control:
    """The live reorder control by which `step` is moved to come to rest
    after `names` — or, for `names=None`, to the head of the visible
    list.

    Two discovery strategies, in the order this file's docstring records:
    the control carries the named neighbour's identifier (`design.md`'s
    stated transport), else the direction spelling.
    """
    candidates = _live_move_controls(html, step)

    if names is not None:
        naming = [c for c in candidates if names in c.haystack]
    else:
        naming = [
            c
            for c in candidates
            if not any(other in c.haystack for other in others if other != step)
        ]
    if len(naming) == 1:
        return naming[0]

    spellings = _UP_SPELLINGS if direction == "up" else _DOWN_SPELLINGS
    opposite = _DOWN_SPELLINGS if direction == "up" else _UP_SPELLINGS
    by_direction = [
        c
        for c in candidates
        if any(word in c.haystack.lower() for word in spellings)
        and not any(word in c.haystack.lower() for word in opposite)
    ]
    if len(by_direction) == 1:
        return by_direction[0]

    pytest.fail(
        f"could not single out the reorder control moving {step!r} "
        f"{'to the head' if names is None else f'after {names!r}'} "
        f"({len(naming)} named-neighbour candidates, "
        f"{len(by_direction)} {direction} candidates among "
        f"{len(candidates)} live move controls) — correct `_move_control`'s "
        "discovery to the implemented page, per this file's docstring"
    )


def _renaming_the_subject(control: _Control, old: str, new: str) -> _Control:
    """The same control with `old` swapped for `new` wherever it names a
    step — the way a replayed or hand-built submission reaches a move the
    page renders no control for."""
    if old not in control.url and old not in control.values:
        pytest.fail(
            f"the control {control.url!r} names {old!r} nowhere, so the "
            "subject of its move cannot be rewritten — correct this file's "
            "assumption that a move control carries its step's identifier"
        )
    return _Control(
        control.method,
        control.url.replace(old, new),
        tuple((name, new if value == old else value) for name, value in control.fields),
        control.inert,
    )


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


# `redesign-step-fields`: the page reads the membership to offer assignees and
# to validate them, so the fixture supplies one. `ASSIGNEE` is named on
# every step below because an `active` `human` step the write touches must
# name someone active — which is the rule, not a fixture convenience.
ASSIGNEE = "prs_01HQ8Z6M4A"
ASSIGNEE_NAME = "Alice Admin"


class _FakeMembers:
    async def list_members(self) -> tuple[_FakeMember, ...]:
        return (_FakeMember(ASSIGNEE, ASSIGNEE_NAME),)


_fake_verify = fake_verify(PRINCIPAL)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "members", _FakeMembers())
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
    data: dict[str, str] | None = None,
) -> Any:
    method = control.method.upper()
    target = _resolve(control.url if url is None else url)
    payload = control.data() if data is None else data
    if method == "GET":
        if payload:
            target = _with_query(target, payload)
        return client.get(target)
    return client.request(method, target, data=payload)


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


def _row_containing(html: str, needle: str) -> str:
    # A step's own row is the one naming it in its identifier cell. A bare
    # `find` would land on an earlier row instead, because a move control
    # names the visible step it comes to rest after — so a neighbour's
    # identifier is rendered in the row above it. Discovery fixture, per
    # this file's docstring: the assertions below are unchanged.
    at = html.find(f"<code>{needle}</code>")
    if at < 0:
        at = html.find(needle)
    assert at >= 0, f"{needle!r} not rendered"
    start = html.rfind("<tr", 0, at)
    end = html.find("</tr>", at)
    if start == -1 or end == -1:
        return html[max(0, at - 400) : at + 400]
    return html[start : end + len("</tr>")]


def _open_edit(client: TestClient, page_html: str, step_id: str) -> str:
    """The step's edit form as its own page, opened the way the list
    offers it."""
    control = _require_control(page_html, contains=(step_id, "edit"))
    response = _issue(client, control)
    assert response.status_code == 200, response.text
    body = str(response.text)
    has_description_form = any(
        any("description" in name for name in candidate.names)
        for candidate in _controls(body)
    )
    if not has_description_form:
        pytest.fail(
            f"following the edit control for {step_id!r} produced no form with "
            "a description field — correct `_open_edit` to how the implemented "
            "page offers a step's edit form"
        )
    return body


def _edit_form_of(html: str) -> _Control:
    for control in _controls(html):
        if control.method.upper() != "GET" and any(
            "description" in name for name in control.names
        ):
            return control
    pytest.fail("the edit page offers no submittable form carrying a description")


def _back_to_list(client: TestClient, html: str, *, marker: str) -> str:
    """Leave the current view by the first GET control that lands back on
    the step table, identified by `marker` being rendered.

    If the implemented edit page carries more than one link back to the
    list, this takes the first in document order — the correction point
    named in this file's docstring.
    """
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
        "— correct `_back_to_list` to the implemented page's back link"
    )


def _one_action_leads_to(
    client: TestClient,
    html: str,
    *,
    shows: tuple[str, ...] = (),
    hides: tuple[str, ...] = (),
) -> bool:
    """Whether some single GET control on the page reaches a view showing
    everything in `shows` and none of `hides` — "offers to leave the view
    in one action", read behaviourally rather than by link wording."""
    for control in _controls(html):
        if control.method.upper() != "GET" or control.inert:
            continue
        if control.url.startswith(("#", "http://", "https://", "mailto:")):
            continue
        response = _issue(client, control)
        if response.status_code != 200:
            continue
        body = response.text
        if all(needle in body for needle in shows) and not any(
            needle in body for needle in hides
        ):
            return True
    return False


def _states_reordering_unavailable(html: str, *, because: str) -> bool:
    body = html.lower()
    return (
        because in body
        and any(word in body for word in _REORDER_WORDS)
        and any(word in body for word in _UNAVAILABLE_WORDS)
    )


def _retired_view(client: TestClient, base: dict[str, str], listed: str) -> str:
    """The view revealing retired steps, reached from a narrowed list by
    the page's own control where it offers one.

    Reaching it through the rendered control rather than through the
    invented parameter is deliberate: the requirement says the control
    that reveals retired steps carries the narrowing too, so a control
    that drops it produces a view these tests' filter assertions then
    fail on.
    """
    narrowed = _get_page(client, params=base)
    control = _first_control(narrowed, contains=("retired",))
    if control is not None:
        response = _issue(client, control)
        if response.status_code == 200 and listed in response.text:
            return str(response.text)
    return _get_page(client, params={**base, _RETIRED_PARAM: "1"})


# ---------------------------------------------------------------------------
# ADDED requirement: The narrowed view survives every write and every
# move between views
# ---------------------------------------------------------------------------


def test_an_accepted_write_keeps_the_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An accepted write keeps the narrowing.

    WHEN a step is retired while a gate filter and a discipline filter
    are active
    THEN the re-rendered list still applies both filters
    AND shows the same gate and discipline selections as before the
    write.

    Retiring is submitted through the step's edit form now
    (`move-step-actions-into-step-pages`), the same `status` field an
    ordinary field edit uses. An accepted write still ends on the list —
    `save_edit` renders it on success regardless of which field
    changed — so the narrowing-survival assertions below are unchanged.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.aye", True),
            ("listing.bee", True),
            ("listing.other-discipline", False),
        )
    )
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    edit_page = _open_edit(client, narrowed, "listing.aye")
    form = _edit_form_of(edit_page)
    response = _issue(client, form, data=_fill(form.data(), status="retired"))

    assert response.status_code == 200, response.text
    body = response.text
    # The write went through, so what follows is about the *re-render*,
    # not about a refusal.
    assert _is_retired(_record_named(store, "listing.aye"))
    # SPECIFIED: the re-rendered list still applies both filters.
    assert "hold.commit" not in body, "the gate filter was dropped by the write"
    assert "listing.other-discipline" not in body, (
        "the discipline filter was dropped by the write"
    )
    # DERIVED sanity guard: the view is not simply empty, which would
    # satisfy both absences vacuously.
    assert "listing.bee" in body
    # SPECIFIED: the same gate and discipline selections as before.
    assert _rendered_filter(body, _FILTER_PARAMS["gate"]) == "listable"
    assert (
        _rendered_filter(body, _FILTER_PARAMS["discipline"]) == VISIBLE_DISCIPLINE.value
    )


def test_a_rejected_list_level_write_keeps_the_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected list-level write keeps the narrowing.

    WHEN a move is rejected while a description search is active
    THEN the re-rendered list reports why the move did not land
    AND still applies the search term.

    Move is the one write left that renders its own rejection on the
    list (`move-step-actions-into-step-pages`): retiring, un-retiring
    and changing status are submitted through the edit form now, so a
    rejection of any of those renders there instead — covered by `A
    rejected retirement keeps the narrowing without leaving the edit
    form`, below. A search makes reordering unavailable in its own
    right (`Reordering is unavailable under a description search`),
    which is what makes a move submitted under one a rejection this
    scenario can exercise without also needing a stale or coherence-rule
    setup.

    The move is discovered live, under a discipline filter that leaves
    reordering available, and then submitted with the search added —
    exactly the submission the rendered controls under the search do
    not themselves offer.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)
    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=_SPREAD_ORDER,
        direction="down",
    )
    order_before = _gate_order(store, "listable")
    needle = "Work of listing"

    response = _issue(
        client,
        control,
        url=_with_query(control.url, {_FILTER_PARAMS["search"]: needle}),
    )

    body = response.text
    # SPECIFIED: nothing is persisted, and the page says why the move was
    # refused. DERIVED wording markers, as
    # test_reordering_is_unavailable_under_a_description_search records.
    assert store.saves == []
    assert _gate_order(store, "listable") == order_before
    assert any(word in body.lower() for word in _UNAVAILABLE_WORDS), (
        f"the refusal states no reason: {body[:2000]}"
    )
    # SPECIFIED: and still applies the search term.
    assert _rendered_filter(body, _FILTER_PARAMS["search"]) == needle


def test_a_rejected_retirement_keeps_the_narrowing_without_leaving_the_edit_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected retirement keeps the narrowing without
    leaving the edit form.

    WHEN a retirement submitted through the edit form's `status` field
    is rejected while a gate filter is active
    THEN the edit form re-renders with the fault, exactly as any other
    rejected edit does
    AND returning to the list from that form applies the gate filter.

    `hold.stock-ready` is its gate's only blocking step, so retiring it
    is refused — the same fault
    `test_playbook_admin_page.py::test_a_blocked_retirement_explains_itself`
    exercises, here under an active narrowing to prove the narrowing
    survives a *rejected* retirement the way it already does an
    accepted one.
    """
    store = _seeded_store(
        extra=_listable_gate(("listing.aye", True), ("listing.bee", True))
    )
    client = _signed_client(monkeypatch, store)
    # Filtered to `hold.stock-ready`'s own gate, so it stays visible and
    # `listing.aye` (a different gate) does not — the marker the
    # narrowing-survival assertions below read.
    narrowed = _get_page(client, params=_narrowing(gate="stock-ready"))
    assert "listing.aye" not in narrowed  # the gate filter really narrowed

    edit_page = _open_edit(client, narrowed, "hold.stock-ready")
    form = _edit_form_of(edit_page)
    response = _issue(client, form, data=_fill(form.data(), status="retired"))

    rejected = response.text
    # SPECIFIED: the edit form re-renders with the fault — it did not
    # become the list. DERIVED wording marker, as
    # test_playbook_admin_page.py records for the same fault.
    assert store.saves == []
    assert not _is_retired(_record_named(store, "hold.stock-ready"))
    assert "stock-ready" in rejected
    # SPECIFIED: returning to the list from that form applies the gate
    # filter.
    listed = _back_to_list(client, rejected, marker="hold.stock-ready")
    assert "listing.aye" not in listed, (
        "leaving the rejected retirement's edit form widened the list "
        "past the gate filter"
    )


def test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected edit keeps the narrowing without leaving the
    form.

    WHEN an edit is rejected while a gate filter is active
    THEN the edit form re-renders with its faults and the submitted
    values, as the editing requirement requires
    AND returning to the list from that form applies the gate filter.

    The rejection is the two-fault case the editing requirement's own
    test uses: a description spanning two lines on a `lesson`-bound step
    also marked blocking.
    """
    lesson = _Record(
        _step(
            identifier="creative.image-advice",
            name="Advice on the hero image",
            blocking=False,
        ),
        display_order=20,
    )
    store = _seeded_store(
        extra=(lesson,) + _listable_gate(("listing.aye", True)),
    )
    client = _signed_client(monkeypatch, store)
    narrowed = _get_page(client, params=_narrowing(gate="listable"))
    assert "hold.commit" not in narrowed

    edit_page = _open_edit(client, narrowed, "creative.image-advice")
    form = _edit_form_of(edit_page)
    two_line = "Line one of the edited advice\nLine two of it"
    response = _issue(
        client,
        form,
        data=_fill(form.data(), name=two_line, block="on"),
    )

    rejected = response.text
    # SPECIFIED: the edit form re-renders, with its faults and the
    # submitted values — it did not become the list.
    assert store.saves == []
    assert "Line one of the edited advice" in rejected
    assert "description" in rejected.lower()
    # SPECIFIED: returning to the list from that form applies the gate
    # filter.
    listed = _back_to_list(client, rejected, marker="listing.aye")
    assert "hold.commit" not in listed, (
        "leaving the rejected edit form widened the list past the gate filter"
    )
    assert "hold.listable" in listed


def test_opening_and_leaving_an_edit_form_preserves_the_narrowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Opening and leaving an edit form preserves the
    narrowing.

    WHEN a step's edit form is opened from a narrowed list and left
    without saving
    THEN the list re-renders under the same narrowing.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.aye", True),
            ("listing.other-discipline", False),
        )
    )
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    edit_page = _open_edit(client, narrowed, "listing.aye")
    listed = _back_to_list(client, edit_page, marker="listing.aye")

    # SPECIFIED: the list re-renders under the same narrowing — both
    # halves of it, and nothing was written along the way.
    assert store.saves == []
    assert "hold.commit" not in listed
    assert "listing.other-discipline" not in listed
    assert _rendered_filter(listed, _FILTER_PARAMS["gate"]) == "listable"
    assert (
        _rendered_filter(listed, _FILTER_PARAMS["discipline"])
        == VISIBLE_DISCIPLINE.value
    )


def test_un_retiring_keeps_the_retired_steps_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Un-retiring keeps the retired steps visible.

    WHEN a step is un-retired from the view that reveals retired steps
    THEN the re-rendered list still reveals retired steps
    AND still applies whatever gate and discipline filters were active.

    Two retired steps, so that "still reveals retired steps" is
    observable on the one that was *not* un-retired.

    Un-retiring is submitted through the step's edit form now
    (`move-step-actions-into-step-pages`), the same `status` field an
    ordinary field edit uses — the retired step's name still links to
    its edit page, exactly as any other step's does. `unretire_step`
    (`playbook_authoring.py`) always returns a step to `in-development`,
    never `active`, so the edit form is filled with that value here.
    """
    retired = _listable_gate(
        ("listing.retired-one", True),
        ("listing.retired-two", True),
        ("listing.aye", True),
        ("listing.other-discipline", False),
    )
    for record in retired[:2]:
        record.definition = replace(record.definition, status=StepStatus.RETIRED)
        record.retired_by = "olena"
        record.retired_on = "2026-08-01"
    store = _seeded_store(extra=retired)
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    revealed = _retired_view(client, narrowing, "listing.retired-one")
    assert "listing.retired-two" in revealed

    edit_page = _open_edit(client, revealed, "listing.retired-one")
    form = _edit_form_of(edit_page)
    response = _issue(client, form, data=_fill(form.data(), status="in-development"))

    assert response.status_code == 200, response.text
    body = response.text
    assert not _is_retired(_record_named(store, "listing.retired-one"))
    # SPECIFIED: the re-rendered list still reveals retired steps.
    assert "listing.retired-two" in body, (
        "un-retiring returned to a view that hides retired steps"
    )
    # SPECIFIED: and still applies the gate and discipline filters.
    assert "hold.commit" not in body
    assert "listing.other-discipline" not in body


# ---------------------------------------------------------------------------
# MODIFIED requirement: The step table shows the live set whole — the
# per-gate position
# ---------------------------------------------------------------------------


def test_a_position_is_read_against_the_whole_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A position is read against the whole gate.

    WHEN a filter narrows a gate to a subset of its live steps
    THEN each visible live step renders its position among that gate's
    live steps and the gate's live count
    AND those positions are unchanged by the filter.

    The `listable` gate holds seven live steps; the filter leaves two
    visible, at the gate's third and sixth positions. A position read off
    the *narrowed* list would render 1/2 and 2/2.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.hidden-one", False),
            ("listing.aye", True),
            ("listing.hidden-two", False),
            ("listing.hidden-three", False),
            ("listing.bee", True),
            ("listing.hidden-four", False),
        )
    )
    client = _signed_client(monkeypatch, store)
    assert len(_gate_order(store, "listable")) == 7

    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)
    whole = _get_page(client, params=_narrowing(gate="listable"))

    for identifier, position in (("listing.aye", 3), ("listing.bee", 6)):
        pattern = re.compile(_POSITION_PATTERN.format(position=position, count=7))
        row = _row_containing(narrowed, identifier)
        # SPECIFIED: the position among the gate's live steps, with the
        # gate's live count.
        assert pattern.search(row), (
            f"{identifier} renders no position {position} of 7 under the "
            f"filter — its row was {row!r}. If the implemented page spells a "
            "position some other way, `_POSITION_PATTERN` is the correction "
            "point."
        )
        # SPECIFIED: unchanged by the filter — the same reading on the
        # unnarrowed gate.
        assert pattern.search(_row_containing(whole, identifier))


# ---------------------------------------------------------------------------
# MODIFIED requirement: A gate's steps can be reordered from the page —
# filter-aware placement
# ---------------------------------------------------------------------------

#: `G` for the worked gate: `hold.listable` (hidden by the discipline
#: filter) followed by the authored order below.
_SPREAD_GATE: Final = (
    ("listing.aye", True),
    ("listing.hidden-one", False),
    ("listing.hidden-two", False),
    ("listing.bee", True),
    ("listing.hidden-three", False),
    ("listing.cee", True),
)
_SPREAD_ORDER: Final = (
    "hold.listable",
    "listing.aye",
    "listing.hidden-one",
    "listing.hidden-two",
    "listing.bee",
    "listing.hidden-three",
    "listing.cee",
)
_SPREAD_VISIBLE: Final = ("listing.aye", "listing.bee", "listing.cee")


def test_a_filtered_move_lands_against_the_visible_step_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A filtered move lands against the visible step it names.

    WHEN a step is moved to come to rest after a visible step that a
    discipline filter separates from it by hidden steps
    THEN the moved step comes to rest immediately after that visible step
    AND the narrowed view shows the two in the requested order.

    `listing.aye` is moved after `listing.bee`, which two hidden steps
    separate from it. The expected full-gate order is the only one
    consistent with that placement and the requirement's "every step
    other than the moved one keeps its relative order".
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    assert _gate_order(store, "listable") == list(_SPREAD_ORDER)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=_SPREAD_ORDER,
        direction="down",
    )
    response = _issue(client, control)

    assert response.status_code == 200, response.text
    # SPECIFIED: immediately after the visible step it named, with every
    # other step — hidden ones included — holding its relative order.
    assert _gate_order(store, "listable") == [
        "hold.listable",
        "listing.hidden-one",
        "listing.hidden-two",
        "listing.bee",
        "listing.aye",
        "listing.hidden-three",
        "listing.cee",
    ]
    assert len(store.saves) == 1
    # SPECIFIED: the narrowed view shows the two in the requested order.
    seen = _positions(response.text, "listing.bee", "listing.aye")
    assert seen[0] < seen[1]


def test_a_filtered_move_upwards_lands_against_the_visible_step_above(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A filtered move upwards lands against the visible step
    above the one it passes.

    WHEN a step is moved one visible position up, past a visible step
    that hidden steps separate from the visible step above that one
    THEN the moved step comes to rest immediately after the visible step
    above the one it passed
    AND ahead of the hidden steps separating those two, rather than
    immediately above the step it passed.

    `V` is (aye, bee, cee); `listing.cee` moves up past `listing.bee`,
    which two hidden steps separate from `listing.aye`.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.aye", True),
            ("listing.hidden-one", False),
            ("listing.hidden-two", False),
            ("listing.bee", True),
            ("listing.cee", True),
        )
    )
    client = _signed_client(monkeypatch, store)
    gate = (
        "hold.listable",
        "listing.aye",
        "listing.hidden-one",
        "listing.hidden-two",
        "listing.bee",
        "listing.cee",
    )
    assert _gate_order(store, "listable") == list(gate)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    control = _move_control(
        narrowed,
        step="listing.cee",
        names="listing.aye",
        others=gate,
        direction="up",
    )
    response = _issue(client, control)

    assert response.status_code == 200, response.text
    order = _gate_order(store, "listable")
    # SPECIFIED: immediately after the visible step above the one it
    # passed, and ahead of the hidden steps separating those two.
    assert order == [
        "hold.listable",
        "listing.aye",
        "listing.cee",
        "listing.hidden-one",
        "listing.hidden-two",
        "listing.bee",
    ]
    # SPECIFIED, stated as the rejected placement: not immediately above
    # the step it passed.
    assert order.index("listing.cee") + 1 != order.index("listing.bee")
    # SPECIFIED: one visible position up, in the narrowed view.
    seen = _positions(response.text, "listing.aye", "listing.cee", "listing.bee")
    assert seen == sorted(seen)


def test_a_filtered_move_disturbs_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A filtered move disturbs nothing else.

    WHEN a move is made while a filter hides part of the gate
    THEN every step other than the moved one holds its relative order,
    hidden steps included.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    other_gates = [gate for gate in SPECIFIED_GATE_ORDER if gate != "listable"]
    orders_before = {gate: _gate_order(store, gate) for gate in other_gates}
    residual_before = [
        identifier for identifier in _SPREAD_ORDER if identifier != "listing.aye"
    ]
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=_SPREAD_ORDER,
        direction="down",
    )
    response = _issue(client, control)

    assert response.status_code == 200, response.text
    order = _gate_order(store, "listable")
    # SPECIFIED: everything but the moved step holds its relative order,
    # hidden steps included.
    assert [
        identifier for identifier in order if identifier != "listing.aye"
    ] == residual_before
    assert sorted(order) == sorted(_SPREAD_ORDER)
    # DERIVED (the reorder write's own requirement, unchanged here): no
    # other gate is touched.
    for gate in other_gates:
        assert _gate_order(store, gate) == orders_before[gate]


def test_a_move_to_the_head_of_a_narrowed_list_stops_at_the_first_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A move to the head of a narrowed list stops at the first
    visible step.

    WHEN a step is moved to the head of a gate narrowed by a filter, and
    that gate holds hidden steps before the first visible one
    THEN the moved step comes to rest immediately before the first
    visible step
    AND behind those hidden steps.

    `V` is (aye, bee); `listing.bee` moves to the head, and two hidden
    steps — the gate's holding step and `listing.hidden-one` — sit before
    `listing.aye`.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.hidden-one", False),
            ("listing.aye", True),
            ("listing.hidden-two", False),
            ("listing.bee", True),
        )
    )
    client = _signed_client(monkeypatch, store)
    gate = (
        "hold.listable",
        "listing.hidden-one",
        "listing.aye",
        "listing.hidden-two",
        "listing.bee",
    )
    assert _gate_order(store, "listable") == list(gate)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    control = _move_control(
        narrowed,
        step="listing.bee",
        names=None,
        others=gate,
        direction="up",
    )
    response = _issue(client, control)

    assert response.status_code == 200, response.text
    # SPECIFIED: immediately before the first visible step, and behind
    # the hidden steps preceding it — never ahead of them.
    assert _gate_order(store, "listable") == [
        "hold.listable",
        "listing.hidden-one",
        "listing.bee",
        "listing.aye",
        "listing.hidden-two",
    ]
    assert len(store.saves) == 1


def test_a_move_to_the_end_of_a_narrowed_list_stops_at_the_last_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A move to the end of a narrowed list stops at the last
    visible step.

    WHEN a step is moved to come to rest after the last visible step of a
    gate narrowed by a filter, and that gate holds hidden steps after it
    THEN the moved step comes to rest immediately after that last visible
    step
    AND ahead of those hidden steps.

    A hidden step also sits *between* the two visible ones, so the
    landing place the scenario names is not the one an unfiltered
    single-slot move would reach — the assertion discriminates rather
    than coinciding with today's behaviour.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.aye", True),
            ("listing.hidden-between", False),
            ("listing.bee", True),
            ("listing.hidden-one", False),
            ("listing.hidden-two", False),
        )
    )
    client = _signed_client(monkeypatch, store)
    gate = (
        "hold.listable",
        "listing.aye",
        "listing.hidden-between",
        "listing.bee",
        "listing.hidden-one",
        "listing.hidden-two",
    )
    assert _gate_order(store, "listable") == list(gate)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=gate,
        direction="down",
    )
    response = _issue(client, control)

    assert response.status_code == 200, response.text
    # SPECIFIED: immediately after the last visible step, ahead of the
    # hidden steps that follow it.
    assert _gate_order(store, "listable") == [
        "hold.listable",
        "listing.hidden-between",
        "listing.bee",
        "listing.aye",
        "listing.hidden-one",
        "listing.hidden-two",
    ]
    assert len(store.saves) == 1


def test_a_move_that_changes_nothing_persists_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A move that changes nothing persists nothing.

    WHEN a move is submitted that would leave the visible order as it
    already stands
    THEN nothing is persisted and the served order is unchanged.

    `G` is (○, ●aye, ○, ○, ●bee); `V` is (aye, bee). A move of
    `listing.aye` to the head leaves `V` exactly as it stands — and the
    placement rule nonetheless yields a perfectly good index, which would
    slide `listing.aye` past two steps the filter hides. The page renders
    no control for it, both ends of the visible list being inert, so the
    submission is built by renaming the subject of the head-naming
    control the page *does* render — which is how a replayed or
    hand-built move reaches this route, and why the requirement's refusal
    cannot rest on the controls.
    """
    store = _seeded_store(
        extra=_listable_gate(
            ("listing.aye", True),
            ("listing.hidden-one", False),
            ("listing.hidden-two", False),
            ("listing.bee", True),
        )
    )
    client = _signed_client(monkeypatch, store)
    gate = (
        "hold.listable",
        "listing.aye",
        "listing.hidden-one",
        "listing.hidden-two",
        "listing.bee",
    )
    assert _gate_order(store, "listable") == list(gate)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)

    head_move = _move_control(
        narrowed,
        step="listing.bee",
        names=None,
        others=gate,
        direction="up",
    )
    response = _issue(
        client, _renaming_the_subject(head_move, "listing.bee", "listing.aye")
    )

    # SPECIFIED: nothing is persisted and the served order is unchanged.
    assert store.saves == []
    assert _gate_order(store, "listable") == list(gate)
    # DERIVED: the page answers rather than erroring — the refusal is a
    # no-op, not a fault.
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# MODIFIED requirement: A gate's steps can be reordered from the page —
# where reordering has no honest meaning
# ---------------------------------------------------------------------------


def test_reordering_is_unavailable_under_a_description_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Reordering is unavailable under a description search.

    WHEN the list is narrowed by a description search
    THEN the reorder controls are inert
    AND the page states that reordering is unavailable while a search is
    active and offers to clear it in one action.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    needle = "Work of listing"
    searched = _get_page(client, params=_narrowing(search=needle))
    assert "listing.aye" in searched
    assert "hold.commit" not in searched  # the search really narrowed

    # SPECIFIED: the reorder controls are inert — for every step the
    # search leaves visible.
    for identifier in _SPREAD_VISIBLE:
        assert _live_move_controls(searched, identifier) == [], (
            f"a live reorder control for {identifier} is rendered under a "
            "description search"
        )
    # SPECIFIED: the page states why. DERIVED wording markers, per this
    # file's docstring.
    assert _states_reordering_unavailable(searched, because="search"), searched[:2000]
    # SPECIFIED: and offers to clear the search in one action — a single
    # control reaching a view the search was hiding.
    assert _one_action_leads_to(client, searched, shows=("hold.commit",))
    assert store.saves == []


def test_reordering_is_unavailable_while_retired_steps_are_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Reordering is unavailable while retired steps are shown.

    WHEN the control revealing retired steps is engaged
    THEN the reorder controls are inert
    AND the page states that reordering is unavailable while retired
    steps are shown and offers to hide them in one action.
    """
    extras = _listable_gate(
        ("listing.aye", True),
        ("listing.bee", True),
        ("listing.retired-one", True),
    )
    extras[2].definition = replace(extras[2].definition, status=StepStatus.RETIRED)
    extras[2].retired_by = "olena"
    extras[2].retired_on = "2026-08-01"
    store = _seeded_store(extra=extras)
    client = _signed_client(monkeypatch, store)

    revealed = _retired_view(client, {}, "listing.retired-one")
    assert "listing.retired-one" in revealed

    # SPECIFIED: the reorder controls are inert — including for the live
    # steps, which are otherwise perfectly movable.
    for identifier in ("listing.aye", "listing.bee"):
        assert _live_move_controls(revealed, identifier) == [], (
            f"a live reorder control for {identifier} is rendered while "
            "retired steps are shown"
        )
    # SPECIFIED: the page states why. DERIVED wording markers.
    assert _states_reordering_unavailable(revealed, because="retired"), revealed[:2000]
    # SPECIFIED: and offers to hide them in one action.
    assert _one_action_leads_to(
        client,
        revealed,
        shows=("listing.aye",),
        hides=("listing.retired-one",),
    )
    assert store.saves == []


def test_a_move_submitted_where_reordering_is_unavailable_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A move submitted where reordering is unavailable is
    refused.

    WHEN a move is submitted while a description search is active or
    retired steps are shown
    THEN nothing is persisted and the page says why the move was refused.

    The move is a real, live one — discovered under a discipline filter,
    where reordering stays available — and then submitted with the
    search, and separately with the show-retired state, added to what it
    carries. That is exactly the submission the rendered controls do not
    offer, which is what makes it the test of a server-side restriction.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)
    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=_SPREAD_ORDER,
        direction="down",
    )
    order_before = _gate_order(store, "listable")

    for extra, because in (
        ({_FILTER_PARAMS["search"]: "Work of listing"}, "search"),
        ({_RETIRED_PARAM: "1"}, "retired"),
    ):
        response = _issue(client, control, url=_with_query(control.url, extra))

        # SPECIFIED: nothing is persisted.
        assert store.saves == [], f"a move was persisted under {because}"
        assert _gate_order(store, "listable") == order_before
        # SPECIFIED: the page says why the move was refused. DERIVED
        # wording markers, per this file's docstring.
        body = response.text.lower()
        assert any(word in body for word in _UNAVAILABLE_WORDS), (
            f"the refusal under {because} states no reason: {response.text[:2000]}"
        )


# ---------------------------------------------------------------------------
# MODIFIED requirement: A gate's steps can be reordered from the page —
# the version the view was rendered from
# ---------------------------------------------------------------------------


def test_a_move_submitted_from_a_superseded_list_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A move submitted from a superseded list is rejected.

    WHEN a move is submitted from a list that a later accepted write has
    superseded
    THEN nothing is persisted and the page states the set changed
    underneath the move
    AND the move's position is not computed against the newer set.

    The page is rendered, then the set's version moves on beneath it, and
    only then is the rendered move submitted. An implementation that
    passed its own POST-time load version through instead of the one the
    page carried would find the check vacuous, compute the position
    against the newer set and persist it — which `store.saves` catches:
    this store's `save()` refuses nothing on its own.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)
    narrowing = _narrowing(gate="listable", discipline=VISIBLE_DISCIPLINE)
    narrowed = _get_page(client, params=narrowing)
    control = _move_control(
        narrowed,
        step="listing.aye",
        names="listing.bee",
        others=_SPREAD_ORDER,
        direction="down",
    )

    store.supersede()  # a later accepted write lands on the set
    response = _issue(client, control)

    # SPECIFIED: nothing is persisted, and the position is not computed
    # against the newer set — which is what persisting would have been.
    assert store.saves == []
    assert _gate_order(store, "listable") == list(_SPREAD_ORDER)
    # SPECIFIED: the page states the set changed underneath the move.
    # DERIVED wording marker, as test_playbook_admin_page.py records for
    # the stale edit and the stale move.
    assert "changed" in response.text.lower()


# ---------------------------------------------------------------------------
# Not a scenario: the page's ordering and the authoring write's must
# agree (`tasks.md` 3.1, `design.md` — Risks). DERIVED throughout: no
# delta scenario states it, and it exists so that a drift between the
# two sort keys surfaces as a failure rather than as silently misplaced
# steps.
# ---------------------------------------------------------------------------


def test_the_pages_order_agrees_with_the_authoring_writes_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED (tasks.md 3.1): the order the page renders a gate's live
    steps in is the order the authoring reorder write leaves them in.

    The write is made through the application use case directly, against
    the same store the page reads, so the two orderings are compared
    without either being told the other's answer. Moving the gate's last
    step to its first position produces an order that agrees with neither
    the seeded slot order nor identifier order, so an adapter sorting by
    something else fails here.
    """
    store = _seeded_store(extra=_listable_gate(*_SPREAD_GATE))
    client = _signed_client(monkeypatch, store)

    asyncio.run(
        reorder_step(
            steps=store,
            principal=PRINCIPAL,
            step_id="listing.cee",
            target_index=0,
        )
    )

    served = _gate_order(store, "listable")
    assert served[0] == "listing.cee"  # the write landed
    html = _get_page(client, params=_narrowing(gate="listable"))
    rendered = sorted(served, key=lambda identifier: _positions(html, identifier)[0])
    assert rendered == served, (
        "the page renders this gate's live steps in a different order from the "
        "one the authoring reorder write serves them in"
    )
