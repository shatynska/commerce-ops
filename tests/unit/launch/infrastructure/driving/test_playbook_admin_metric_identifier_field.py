"""The step form's metric-identifier input.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/playbook-admin/spec.md`

Covers the MODIFIED requirement *The step form carries every authorable
field* — its new scenario *The form offers the metric identifier*, and
the paragraph the delta adds with it:

    The metric identifier's input SHALL accept any value the shared
    vocabulary accepts and SHALL NOT constrain the author to a list:
    nothing defines metrics, so a control offering choices would have
    none to offer. It SHALL be clearable, absent being the value almost
    every step carries.

The requirement's fourteen other scenarios are unchanged by this delta
and stay covered by this directory's existing files
(`test_playbook_admin_step_fields.py`,
`test_playbook_admin_multi_value_controls.py`,
`test_playbook_admin_start_fields.py`). Nothing here edits them.

## Level

The playbook-admin router mounted alone over a step-store double, driven
the way a browser does: the test *discovers* the form and reads its
fields. The scenario is about what the rendered form offers, so the
route is the smallest unit that observes it — the harness
`test_playbook_admin_page.py` established and
`test_playbook_admin_step_fields.py` records.

## What is fixed, and what is INVENTED

Fixed by the artifacts: that the form offers an input for the metric
identifier; that it is free-typed rather than chosen from a list; that
it is clearable.

INVENTED, each with its correction point:

- The page module, the `steps` module attribute, the guard seam, the
  session cookie and the control-discovery vocabulary — all as
  `test_playbook_admin_step_fields.py`'s docstring records them, and
  reproduced here because this project keeps its test files
  self-contained.
- That the field's form name **contains** `metric` — matched by
  substring, since no artifact fixes the form's field naming. Correction
  point: `_METRIC_FIELD_FRAGMENT`.
- "Free-typed rather than chosen from a list" read as: the control is not
  a `<select>`. That is the only control HTML has for constraining an
  author to a list, and the requirement's own reason ("a control offering
  choices would have none to offer") is about exactly that.
- "Clearable" read as: the input carries no `required` attribute and its
  rendered value for a step declaring none is empty. A `required` input
  cannot be submitted empty, which is what clearing it would mean.

## Expected first-run state

`StepDefinition` takes no `metric_id` and the form offers no such input,
so the tests here are expected to fail on an absent target — `TypeError`
from the fixture, before the page is reached. Per `ai-toolkit:testing`
that establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain.launch_playbook import (
    StepDefinition,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as page_module,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fixtures import ALICE, ALICE_NAME, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

#: INVENTED — see the module docstring. The single correction point for
#: how the metric identifier's input is addressed.
_METRIC_FIELD_FRAGMENT: Final = "metric"

METRIC_STEP: Final = "lp.inventory.040"
ORDINARY_STEP: Final = "listing.zeta"
STOCK_METRIC: Final = MetricId("units-fulfillable")


# ---------------------------------------------------------------------------
# Step-store double
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{"identifier": ORDINARY_STEP, "assignees": (ALICE,), **overrides}
    )


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
        return (_Member(ALICE, ALICE_NAME),)

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


def _store() -> _FakeStepStore:
    """One `active` blocking step per gate, plus two `listable` steps: one
    declaring a metric identifier and one declaring none, so the form can
    be opened on each."""
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
    )
    extras = (
        _Record(
            _step(identifier=ORDINARY_STEP, name="Work of listing.zeta"),
            display_order=20,
        ),
        _Record(
            _step(
                identifier=METRIC_STEP,
                name="INVENTORY GATE: 60-80+ units fulfillable before going live",
                metric_id=STOCK_METRIC,
            ),
            display_order=30,
        ),
    )
    return _FakeStepStore(records + extras)


# ---------------------------------------------------------------------------
# HTML discovery (the harness `test_playbook_admin_page.py` establishes)
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.controls: list[tuple[str, str]] = []
        self.selects: dict[str, list[str]] = {}
        self.textareas: set[str] = set()
        self.required: set[str] = set()
        self._form: dict[str, Any] | None = None
        self._select: str | None = None
        self._textarea: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
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
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if "required" in a:
                self.required.add(name)
            default = "on" if kind == "checkbox" else ""
            self._form["fields"][name] = a.get("value", default)
        elif tag == "select":
            self._select = a.get("name")
            if self._select:
                self.selects.setdefault(self._select, [])
                if "required" in a:
                    self.required.add(self._select)
                if self._form is not None:
                    self._form["fields"][self._select] = ""
        elif tag == "option" and self._select:
            self.selects[self._select].append(a.get("value", ""))
        elif tag == "textarea":
            name = a.get("name")
            if name:
                self.textareas.add(name)
                self._textarea = name
                if "required" in a:
                    self.required.add(name)
                if self._form is not None:
                    self._form["fields"][name] = ""

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


def _control(html: str, *, contains: tuple[str, ...]) -> tuple[str, str] | None:
    parsed = _parse(html)
    for method, url in parsed.controls:
        if all(part in url for part in contains):
            return method, url
    return None


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


_fake_verify = fake_verify(PRINCIPAL)


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


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return response.text


def _edit_form(client: TestClient, page_html: str, step_id: str) -> dict[str, Any]:
    """Open the step's form the way the page offers it."""
    found = _control(page_html, contains=(step_id, "edit"))
    if found is not None:
        method, url = found
        target = url if url.startswith("/") else urljoin(_page_path() + "/", url)
        response = client.request(method.upper(), target)
        if response.status_code == 200:
            for form in _parse(response.text).forms:
                if any("name" in field for field in form["fields"]):
                    return {**form, "html": response.text}
    for form in _parse(page_html).forms:
        haystack = form["url"] + " " + str(form["fields"])
        if step_id in haystack and any("name" in field for field in form["fields"]):
            return {**form, "html": page_html}
    pytest.fail(
        f"no edit form for {step_id!r} was discoverable — correct the "
        "control vocabulary in this file's docstring to the implemented page"
    )


def _metric_fields(form: dict[str, Any]) -> list[str]:
    return [name for name in form["fields"] if _METRIC_FIELD_FRAGMENT in name]


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The step form carries every authorable field
# ---------------------------------------------------------------------------


def test_the_form_offers_the_metric_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The form offers the metric identifier.

    WHEN the step form is rendered
    THEN it offers an input for the metric identifier, free-typed rather
    than chosen from a list, and clearable.

    "A field the authoring capability accepts and the form omits is a
    field nobody can set" — which is why this is a scenario of its own
    rather than an item in the requirement's list.
    """
    store = _store()
    client = _signed_client(monkeypatch, store)

    form = _edit_form(client, _get_page(client), METRIC_STEP)
    parsed = _parse(form["html"])
    fields = _metric_fields(form)

    # SPECIFIED: the form offers an input for the metric identifier.
    assert fields, (
        "the step form offers no field whose name mentions "
        f"{_METRIC_FIELD_FRAGMENT!r}: {sorted(form['fields'])}"
    )
    for name in fields:
        # SPECIFIED: free-typed rather than chosen from a list — "nothing
        # defines metrics, so a control offering choices would have none
        # to offer".
        assert name not in parsed.selects, (
            f"the metric identifier is offered as a list ({name}); the "
            "requirement forbids constraining the author to one"
        )
        # SPECIFIED: clearable — a required input cannot be submitted
        # empty, which is what clearing it means.
        assert name not in parsed.required, (
            f"the metric identifier's input ({name}) is required; absent is "
            "the value almost every step carries"
        )


def test_the_metric_input_carries_what_the_step_declares_and_nothing_where_none_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: the form offers "every field the authoring
    capability accepts", and the metric identifier's input "SHALL be
    clearable, absent being the value almost every step carries".

    DERIVED from the requirement statement rather than a named scenario,
    and paired with the scenario above: a form that rendered the input but
    never populated it would satisfy "offers an input" while making the
    field unreadable and, on submission, silently clearing whatever the
    step carried.
    """
    store = _store()
    client = _signed_client(monkeypatch, store)
    page = _get_page(client)

    declaring = _edit_form(client, page, METRIC_STEP)
    declaring_values = {
        name: declaring["fields"][name] for name in _metric_fields(declaring)
    }
    assert declaring_values, "no metric field was rendered on the declaring step"
    assert STOCK_METRIC.value in " ".join(declaring_values.values()), (
        f"the form does not carry the step's declared identifier: {declaring_values!r}"
    )

    absent = _edit_form(client, page, ORDINARY_STEP)
    absent_values = {name: absent["fields"][name] for name in _metric_fields(absent)}
    assert absent_values, "no metric field was rendered on the step declaring none"
    for name, value in absent_values.items():
        assert value.strip() == "", (
            f"the form pre-fills {name} with {value!r} for a step declaring "
            "no metric identifier"
        )
