"""The admin page under the redesigned step: form, table, status control.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/playbook-admin/spec.md`

Covers the three ADDED requirements in full —

- *The step form carries every authorable field* (3 scenarios),
- *Steps that are not active are visible to authors and set apart* (3
  scenarios),
- *A step's status can be changed from the page* (2 scenarios),

the MODIFIED requirement *The step table shows the live set whole* (all 5
scenarios, restated for four statuses and for search over the name as
well as the description), and, from the MODIFIED requirement *A gate's
steps can be reordered from the page*, the scenarios whose rule changed:
*A draft in the gate does not remove reordering*, *Reordering is
unavailable under a description search* (now a search over the name
**or** the description), and the requirement's new sentence that "a move
naming a step that holds no slot SHALL be refused without persisting
anything".

The reorder scenarios this change leaves untouched — the filtered-move
placement rules, the no-op move, the retired-steps mode, the superseded
list — are covered by the existing tests in this directory and are
accounted for against them in `test-manifest.md`. Their fixtures need
migrating to the new field set (`tasks.md` 6.3); that is a fixture
correction and not a licence to weaken what they assert.

**Level.** The routes over a step-store double, driven the way a browser
does: the tests *discover* the page's own controls and submit them,
pinning as little of the URL surface as possible. This is the harness
`test_playbook_admin_page.py` established, reproduced here because this
project keeps its test files self-contained.

## INVENTED, beyond what that harness already records

`test_playbook_admin_page.py`'s docstring records the page module, the
`steps` module attribute substituted with `monkeypatch.setattr`, the
guard seam, the session cookie, the query-parameter names and the
control-discovery vocabulary. This change adds:

- a membership the page reads to offer assignees. `_install_members` sets
  whichever module attribute the page exposes, from a candidate list,
  and fails loudly if none — so the seam is discovered rather than
  assumed into existence.
- `status` as a query parameter and a form field, and the
  status-control vocabulary (a control whose URL or fields mention
  "status" and the step). Correction point: `_status_control`.
- markers for "set apart from the served set" and "carries its status":
  the status *word* appearing near the step's row, and the non-active
  rows rendering outside the gate's orderable list. `_row_marks_status`
  and `_orderable_ids` are the correction points, and both fail loudly
  rather than defaulting.

## Expected first-run state

The page does not carry these fields, and `StepKind`/`StepStatus` do not
exist, so every test here fails at import — the absent-target state; the
assertions have not been exercised.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from html.parser import HTMLParser
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
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as page_module,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER

PRINCIPAL: Final = "helen"
_SESSION_COOKIE: Final = "admin_session"
_SESSION_VALUE: Final = "a-verified-admin-session"

DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]
ANOTHER_DISCIPLINE: Final = DISCIPLINES[1]

_FILTER_PARAMS: Final = {"gate": "gate", "discipline": "discipline", "search": "q"}

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
BOHDAN: Final = "prs_01HQ8Z6M4B"
BOHDAN_NAME: Final = "Bohdan Colleague"
CHRIS_DEPARTED: Final = "prs_01HQ8Z6M4C"
CHRIS_NAME: Final = "Chris Departed"


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


def _seeded_store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    """One `active`, owned, blocking step per gate, plus the extras."""
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


def _record_named(store: _FakeStepStore, identifier: str) -> _Record:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


# ---------------------------------------------------------------------------
# HTML discovery (the harness `test_playbook_admin_page.py` establishes)
# ---------------------------------------------------------------------------

_HX_VERBS: Final = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.controls: list[tuple[str, str]] = []
        self.selects: dict[str, list[tuple[str, str]]] = {}
        self.textareas: set[str] = set()
        self._form: dict[str, Any] | None = None
        self._select: str | None = None
        self._select_done = False
        self._textarea: str | None = None
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
        elif tag == "select":
            self._select = a.get("name")
            self._select_done = False
            if self._select:
                self.selects.setdefault(self._select, [])
                if self._form is not None:
                    self._form["fields"][self._select] = ""
        elif tag == "option" and self._select:
            self._option = (a.get("value", ""), "")
            if self._form is not None and ("selected" in a or not self._select_done):
                self._form["fields"][self._select] = a.get("value", "")
                self._select_done = "selected" in a
        elif tag == "textarea":
            name = a.get("name")
            if name:
                self.textareas.add(name)
                self._textarea = name
                if self._form is not None:
                    self._form["fields"][name] = ""

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea:
            self._form["fields"][self._textarea] += data
        if self._select is not None and self._option is not None:
            value, text = self._option
            self._option = (value, text + data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag == "option" and self._select and self._option is not None:
            self.selects[self._select].append(
                (self._option[0], self._option[1].strip())
            )
            self._option = None
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


_MEMBERS_ATTRIBUTES: Final = ("members", "read_members", "members_reader")


def _install_members(monkeypatch: pytest.MonkeyPatch, members: _FakeMembers) -> None:
    """Substitute the page's members seam (INVENTED — see the docstring).

    Fails loudly rather than creating the attribute, so a page that reads
    the membership by some other route is reported instead of silently
    passing with an unused double.
    """
    for name in _MEMBERS_ATTRIBUTES:
        if hasattr(page_module, name):
            monkeypatch.setattr(page_module, name, members)
            return
    pytest.fail(
        "the page module exposes no members seam under any of "
        f"{_MEMBERS_ATTRIBUTES} — the form must offer the membership's active "
        "members, so it reads the membership somehow; correct this file's "
        "probe to the implemented name"
    )


def _app(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeStepStore,
    members: _FakeMembers | None = None,
) -> TestClient:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    _install_members(monkeypatch, members or _FakeMembers())
    app = FastAPI()
    app.include_router(page_module.router)
    return TestClient(app)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeStepStore,
    members: _FakeMembers | None = None,
) -> TestClient:
    client = _app(monkeypatch, store, members)
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
    """Open the step's form the way the page offers it."""
    found = _control(page_html, contains=(step_id, "edit"))
    if found is not None:
        method, url, fields = found
        if not fields:
            response = _submit(client, method, url, {})
            assert response.status_code == 200, response.text
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


def _status_control(
    client: TestClient, html: str, step_id: str, status: StepStatus
) -> tuple[str, str, dict[str, str]]:
    """The status change, submitted through the step's own edit form
    (`move-step-actions-into-step-pages`) -- retiring, un-retiring and
    changing status all go through the shared `status` field now, not a
    dedicated row control."""
    form = _edit_form(client, html, step_id)
    fields = _fill(form["fields"], status=_status_value(status))
    return form["method"], form["url"], fields


def _status_value(status: StepStatus) -> str:
    """The wire value of a status, however the enum spells it."""
    value = getattr(status, "value", None)
    return str(value) if isinstance(value, str) else status.name.lower()


def _row_of(html: str, step_id: str) -> str:
    """The step's own table row.

    Anchored on the addressing `id` the list renders for each step, rather
    than on the first occurrence of the identifier anywhere in the page. A
    reorder control names the *neighbour* it would come to rest after —
    `<input name="after" value="listing.shared">` sits in the row above —
    so a bare `find` can land in a different step's row and read a window
    that never reaches this one's cells.
    """
    at = html.find(f'id="step-{step_id}"')
    if at < 0:
        return ""
    opened = html.rfind("<tr", 0, at)
    closed = html.find("</tr>", at)
    return html[opened if opened >= 0 else at : closed if closed >= 0 else len(html)]


def _row_marks_status(html: str, step_id: str, status: StepStatus) -> bool:
    """Whether the step's row makes its status legible.

    DERIVED reading of "SHALL make each step's status legible": the
    status's own word appears within the step's own row. Correction point
    for the marker.
    """
    row = _row_of(html, step_id).lower()
    if not row:
        return False
    word = _status_value(status).replace("_", "-")
    return word in row or word.replace("-", " ") in row


def _listable_extras() -> tuple[_Record, ...]:
    """Two active `listable` steps whose authored order disagrees with
    identifier order, so ordered rendering cannot pass by sorting."""
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


# ---------------------------------------------------------------------------
# Requirement: The step form carries every authorable field
# ---------------------------------------------------------------------------


def test_the_form_offers_name_and_description_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The form offers name and description separately.

    WHEN a step's form is opened
    THEN the name and the description are separate inputs, and the
    description accepts line breaks.

    SPECIFIED, with the reason: "a single-line box for a field whose
    whole purpose is to be longer than the name would teach the author
    the opposite of what the two fields are for". The multi-line half is
    asserted as the description being rendered as a `textarea`, which is
    the one control HTML has for the purpose.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    form = _edit_form(client, _get_page(client), "listing.zeta")

    fields = set(form["fields"])
    name_fields = [field for field in fields if "name" in field]
    description_fields = [field for field in fields if "description" in field]
    # SPECIFIED: separate inputs.
    assert name_fields, f"the form offers no name input: {sorted(fields)}"
    assert description_fields, f"the form offers no description input: {sorted(fields)}"
    assert set(name_fields) != set(description_fields)
    # SPECIFIED: the description accepts line breaks.
    textareas = _parse(form["html"]).textareas
    assert any(field in textareas for field in description_fields), (
        f"the description is not a multi-line input: textareas are {sorted(textareas)}"
    )


def test_the_form_offers_every_authorable_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "The step form SHALL offer every field the
    authoring capability accepts: the name, the description, the
    assignees, the kind, whether the result needs confirmation, the
    status, the hazard, and — for an `automated` step — the automation
    brief and the handler, alongside the gate, scope, timing anchor and
    blocking flag it already carries."

    Stated once as a list and in no scenario, and it is the requirement
    the form most easily half-satisfies: the page currently submits
    `binding`, `execution` and `rule_policy`, which cease to exist, so
    every field below has to be built.

    DERIVED: the field *names* are matched by substring, since no
    artifact fixes the form's field naming.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)

    form = _edit_form(client, _get_page(client), "listing.zeta")
    fields = " ".join(sorted(form["fields"]))

    for expected in (
        "name",
        "description",
        "assignee",
        "kind",
        "confirm",
        "status",
        "hazard",
        "gate",
        "scope",
        "block",
    ):
        assert expected in fields, (
            f"the step form offers no field mentioning {expected!r}: {fields}"
        )
    # SPECIFIED: the removed fields are gone from the form — they name
    # nothing the write would accept.
    assert "binding" not in fields
    assert "execution" not in fields
    assert "rule_policy" not in fields


def test_a_form_rejected_by_validation_shows_every_fault_with_the_typed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A form rejected by validation shows every fault with the
    typed values.

    WHEN a submitted step violates two of the new field rules at once
    THEN the re-rendered form reports both faults and still holds what
    was typed, and the step set is unchanged.

    The two faults below are both new: a name spanning lines, and a
    `human` step carrying a handler.
    """
    store = _seeded_store(extra=_listable_extras())
    client = _signed_client(monkeypatch, store)
    page = _get_page(client)
    form = _edit_form(client, page, "listing.zeta")

    typed_name = "A name that\nspans two lines"
    typed_handler = "no.such.registered.use-case"
    submitted = _fill(
        dict(form["fields"]),
        name=typed_name,
        handler=typed_handler,
    )

    response = _submit(client, form["method"], form["url"], submitted)

    assert response.status_code in (200, 422), response.text
    body = response.text
    # SPECIFIED: both faults are reported. DERIVED wording markers.
    lowered = body.lower()
    assert "name" in lowered
    assert "handler" in lowered
    # SPECIFIED: the form still holds what was typed.
    assert typed_handler in body
    assert "A name that" in body
    # SPECIFIED: the step set is unchanged.
    assert store.saves == []


# ---------------------------------------------------------------------------
# Requirement: Steps that are not active are visible to authors and set apart
# ---------------------------------------------------------------------------


def _mixed_status_extras() -> tuple[_Record, ...]:
    return (
        _Record(
            _step(
                identifier="listing.active-one",
                name="Work of listing.active-one",
                status=StepStatus.ACTIVE,
            ),
            display_order=20,
        ),
        _Record(
            _step(
                identifier="listing.drafted",
                name="Work of listing.drafted",
                status=StepStatus.DRAFT,
                assignees=(),
            ),
            display_order=0,
        ),
        _Record(
            _step(
                identifier="listing.building",
                name="Work of listing.building",
                status=StepStatus.IN_DEVELOPMENT,
                assignees=(),
            ),
            display_order=0,
        ),
        _Record(
            _step(
                identifier="listing.retired-one",
                name="Work of listing.retired-one",
                status=StepStatus.RETIRED,
            ),
            display_order=0,
        ),
    )


def test_draft_and_in_development_steps_are_shown_and_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Draft and in-development steps are shown and marked.

    WHEN the page is opened against a set holding a draft and an active
    step in the same gate
    THEN both are shown, each carrying its status, and the draft is set
    apart from the served set
    AND the draft renders no position among the gate's active steps.
    """
    store = _seeded_store(extra=_mixed_status_extras())
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: both are shown...
    assert "listing.active-one" in html
    assert "listing.drafted" in html
    # ...each carrying its status.
    assert _row_marks_status(html, "listing.active-one", StepStatus.ACTIVE)
    assert _row_marks_status(html, "listing.drafted", StepStatus.DRAFT)
    assert _row_marks_status(html, "listing.building", StepStatus.IN_DEVELOPMENT)
    # SPECIFIED: the draft is set apart — it renders outside the gate's
    # orderable list, which is what lets the gate's active steps stay
    # reorderable while a draft sits in the same gate.
    assert (
        _control(html, contains=("listing.drafted", "up")) is None
        and _control(html, contains=("listing.drafted", "top")) is None
        and _control(html, contains=("listing.drafted", "down")) is None
    ), "a draft offers a reorder control, so it is inside the orderable list"
    # SPECIFIED: and it renders no position among the gate's active steps.
    assert _control(html, contains=("listing.active-one", "up")) is not None or (
        _control(html, contains=("listing.active-one", "top")) is not None
    ), "the gate's active steps are not reorderable at all"


def test_retired_steps_stay_behind_their_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Retired steps stay behind their control.

    WHEN the page is opened with no control engaged
    THEN retired steps are not shown, and draft and in-development steps
    are.

    SPECIFIED reason: "retirement is the end of a step's life and does
    not belong in the working view, while a draft is work in progress and
    does".
    """
    store = _seeded_store(extra=_mixed_status_extras())
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    assert "listing.retired-one" not in html
    assert "listing.drafted" in html
    assert "listing.building" in html


def test_assignees_are_visible_on_the_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Assignees are visible on the table.

    WHEN a step naming two assignees is rendered
    THEN both are shown by display name alongside the step.

    SPECIFIED reason: "A `human` step that is `active` and shows no
    assignee is a state the write rules forbid, so showing assignees is
    what makes that rule's effect visible rather than merely enforced."
    """
    shared = _Record(
        _step(
            identifier="listing.shared",
            name="Work of listing.shared",
            assignees=(ALICE, BOHDAN),
        ),
        display_order=20,
    )
    store = _seeded_store(extra=(shared,))
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    row = _row_of(html, "listing.shared")
    assert row, "the list renders no row for listing.shared"
    # SPECIFIED: both, by display name — not by generated identifier.
    assert ALICE_NAME in row
    assert BOHDAN_NAME in row


# ---------------------------------------------------------------------------
# Requirement: A step's status can be changed from the page
# ---------------------------------------------------------------------------


def test_an_activation_from_the_page_lands_and_joins_the_served_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An activation lands and the step joins the served set.

    WHEN an author activates a step carrying everything its kind requires
    THEN the step is shown as active and among the served set.
    """
    ready = _Record(
        _step(
            identifier="listing.ready",
            name="Work of listing.ready",
            status=StepStatus.IN_DEVELOPMENT,
            assignees=(ALICE,),
        ),
        display_order=0,
    )
    store = _seeded_store(extra=(ready,))
    client = _signed_client(monkeypatch, store)

    method, url, fields = _status_control(
        client, _get_page(client), "listing.ready", StepStatus.ACTIVE
    )
    response = _submit(client, method, url, fields)

    assert response.status_code in (200, 204, 302), response.text
    # SPECIFIED: the write landed.
    assert _record_named(store, "listing.ready").definition.status is (
        StepStatus.ACTIVE
    )
    # SPECIFIED: and the page shows it as active.
    assert _row_marks_status(_get_page(client), "listing.ready", StepStatus.ACTIVE)


def test_a_refused_activation_explains_itself_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A refused activation explains itself.

    WHEN an author activates a `human` step naming no active assignee
    THEN the page shows the refusal's explanation and the step's status
    is unchanged.

    SPECIFIED: the refusal carries "the refusal's own explanation" — the
    page does not substitute a generic message, because what the step
    lacks is the only actionable part.
    """
    unowned = _Record(
        _step(
            identifier="listing.unowned",
            name="Work of listing.unowned",
            status=StepStatus.IN_DEVELOPMENT,
            assignees=(),
        ),
        display_order=0,
    )
    store = _seeded_store(extra=(unowned,))
    client = _signed_client(monkeypatch, store)

    method, url, fields = _status_control(
        client, _get_page(client), "listing.unowned", StepStatus.ACTIVE
    )
    # The edit form's parsed fields default an unselected multi-select to
    # its first option (a fixture-parsing artifact, not a real browser's
    # behaviour), which would otherwise name an assignee the step does
    # not actually have and satisfy the very rule this scenario means to
    # provoke. Cleared explicitly so the submission still names none —
    # `posted.getlist("assignees")` (`playbook_admin.py`) drops an empty
    # string, so this reads as "no assignee" server-side.
    fields = _fill(fields, assignees="")
    response = _submit(client, method, url, fields)

    assert response.status_code in (200, 422), response.text
    # SPECIFIED: the refusal's explanation is surfaced. DERIVED wording
    # marker.
    assert "assign" in response.text.lower()
    # SPECIFIED: the set is unchanged.
    assert store.saves == []
    assert _record_named(store, "listing.unowned").definition.status is (
        StepStatus.IN_DEVELOPMENT
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The step table shows the live set whole
# ---------------------------------------------------------------------------


def test_the_whole_authored_set_other_than_retired_is_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The whole live set is one page.

    WHEN the admin page is opened with no filter active
    THEN every step other than the `retired` ones is rendered, grouped by
    gate in gate order
    AND each gate's active steps stand in authored order, with its
    non-active steps outside that order.
    """
    store = _seeded_store(extra=(*_listable_extras(), *_mixed_status_extras()))
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: every step other than the retired ones.
    for record in store.records:
        identifier = record.definition.identifier
        if record.definition.status is StepStatus.RETIRED:
            assert identifier not in html, f"{identifier} is retired and rendered"
        else:
            assert identifier in html, f"{identifier} is not rendered"
    # SPECIFIED: grouped by gate in gate order.
    gate_positions = _positions(
        html, *(f"hold.{gate}" for gate in SPECIFIED_GATE_ORDER)
    )
    assert gate_positions == sorted(gate_positions)
    # SPECIFIED: each gate's active steps in authored order — which here
    # disagrees with identifier order.
    hold_listable, zeta, alpha = _positions(
        html, "hold.listable", "listing.zeta", "listing.alpha"
    )
    assert hold_listable < zeta < alpha


def test_filters_narrow_without_altering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Filters narrow without altering.

    WHEN a gate or discipline filter is applied
    THEN only the matching steps are shown, and the underlying step set
    is unchanged.
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

    assert "listing.alpha" in narrowed
    assert "listing.zeta" not in narrowed
    assert "hold.ignition" not in narrowed
    cleared = _get_page(client)
    for identifier in ("listing.alpha", "listing.zeta", "hold.ignition"):
        assert identifier in cleared
    assert store.saves == []


def test_search_matches_the_name_and_the_description_alike(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Search matches description text.

    WHEN a search term is entered that appears in one step's name and in
    another step's description
    THEN both steps are shown.

    SPECIFIED reason, and the change: "an author who remembers a phrase
    does not remember which of the two fields they wrote it in". An
    implementation that carried the old single-field search forward
    against `name` alone finds one of the two steps below.
    """
    needle = "unmistakable-needle"
    extra = (
        _Record(
            _step(
                identifier="listing.named",
                name=f"Carries the {needle} in its name",
                description="Nothing to see in the description.",
            ),
            display_order=20,
        ),
        _Record(
            _step(
                identifier="listing.described",
                name="An ordinary name",
                description=f"Carries the {needle} in its description.",
            ),
            display_order=30,
        ),
    )
    store = _seeded_store(extra=extra)
    client = _signed_client(monkeypatch, store)

    html = _get_page(client, params={_FILTER_PARAMS["search"]: needle})

    # SPECIFIED: both steps are shown.
    assert "listing.named" in html
    assert "listing.described" in html
    # ...and the search still narrows.
    assert "hold.commit" not in html


def test_retired_steps_are_reachable_but_set_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Retired steps are reachable but set apart.

    WHEN the control that shows retired steps is used
    THEN retired steps are shown marked as retired, and are not
    interleaved with the served set.

    SPECIFIED, and the mechanism this change names: the page "reads the
    authored set by the same path that control already uses, which now
    answers with every status rather than adding a second read".
    """
    store = _seeded_store(extra=_mixed_status_extras())
    client = _signed_client(monkeypatch, store)

    _, url, fields = _require_control(_get_page(client), contains=("retired",))
    response = client.get(url) if not fields else _submit(client, "get", url, fields)
    assert response.status_code == 200, response.text
    html = response.text

    assert "listing.retired-one" in html
    assert _row_marks_status(html, "listing.retired-one", StepStatus.RETIRED)


def test_a_position_is_read_against_the_whole_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A position is read against the whole gate.

    WHEN a filter narrows a gate to a subset of its active steps
    THEN each visible active step renders its position among that gate's
    active steps and the gate's active count
    AND those positions are unchanged by the filter.

    The gate below holds a draft as well, and the draft holds no slot —
    so the count rendered must be of the gate's **active** steps, not of
    everything it carries.
    """
    store = _seeded_store(extra=(*_listable_extras(), *_mixed_status_extras()))
    client = _signed_client(monkeypatch, store)

    unfiltered = _get_page(client)
    narrowed = _get_page(
        client,
        params={
            _FILTER_PARAMS["gate"]: "listable",
            _FILTER_PARAMS["discipline"]: ANOTHER_DISCIPLINE.value,
        },
    )

    # The gate holds four active steps (its holding step, zeta, alpha,
    # active-one) and two non-active ones, so the count that appears must
    # be four.
    def _window(html: str, identifier: str) -> str:
        at = html.find(identifier)
        assert at >= 0, f"{identifier!r} is not rendered"
        return html[at : at + 400]

    assert "4" in _window(unfiltered, "listing.alpha")
    assert "4" in _window(narrowed, "listing.alpha"), (
        "the position is computed against the narrowed view rather than the whole gate"
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A gate's steps can be reordered from the page —
# the rules this change adds
# ---------------------------------------------------------------------------


def test_a_draft_in_the_gate_does_not_remove_reordering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A draft in the gate does not remove reordering.

    WHEN a gate holding a draft and three active steps is rendered in the
    default view
    THEN the gate's active steps can still be reordered, and the draft is
    not a position a move may name.

    SPECIFIED reason: the retired-steps rule is page-wide "because
    revealing retired steps is a deliberate act that puts the page into a
    different mode; drafts appear in the default view, so the same rule
    would remove reordering from any gate anyone is drafting in, which is
    most of them".
    """
    draft = _Record(
        _step(
            identifier="listing.drafted",
            name="Work of listing.drafted",
            status=StepStatus.DRAFT,
            assignees=(),
        ),
        display_order=0,
    )
    store = _seeded_store(extra=(*_listable_extras(), draft))
    client = _signed_client(monkeypatch, store)

    html = _get_page(client)

    # SPECIFIED: the gate's active steps can still be reordered.
    moved = _control(html, contains=("listing.alpha", "up")) or _control(
        html, contains=("listing.alpha", "top")
    )
    assert moved is not None, (
        "a draft in the gate removed reordering from the gate's active steps"
    )
    method, url, fields = moved
    response = _submit(client, method, url, fields)
    assert response.status_code in (200, 204, 302), response.text
    assert len(store.saves) == 1


def test_a_move_naming_a_step_that_holds_no_slot_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "A move naming a step that holds no slot
    SHALL be refused without persisting anything, like any other move
    that cannot be given an honest meaning."

    Stated in the requirement and in no scenario, and it is the
    server-side half `tasks.md` 5.3 names: "refuse server-side a move
    naming a step that holds no slot". A page that merely omits the
    control leaves the rule resting on the rendered controls alone.
    """
    draft = _Record(
        _step(
            identifier="listing.drafted",
            name="Work of listing.drafted",
            status=StepStatus.DRAFT,
            assignees=(),
        ),
        display_order=0,
    )
    store = _seeded_store(extra=(*_listable_extras(), draft))
    client = _signed_client(monkeypatch, store)
    html = _get_page(client)

    # Take a legitimate move control and re-aim it at the draft, which
    # holds no slot — the submission a page's own controls never offer
    # and a client may still make.
    method, url, fields = _require_control(html, contains=("listing.alpha", "up"))
    aimed_at_the_draft = {
        key: ("listing.drafted" if "listing.alpha" in value else value)
        for key, value in fields.items()
    }
    target = url.replace("listing.alpha", "listing.drafted")

    response = _submit(client, method, target, aimed_at_the_draft)

    # SPECIFIED: refused without persisting anything.
    assert response.status_code >= 400 or store.saves == [], (
        "a move naming a step that holds no slot was accepted"
    )
    assert store.saves == []


def test_reordering_is_unavailable_under_a_search_over_either_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Reordering is unavailable under a description search.

    WHEN the list is narrowed by a text search over the name or the
    description
    THEN the reorder controls are inert
    AND the page states that reordering is unavailable while a search is
    active and offers to clear it in one action.

    Restated by this change as "over a step's name or its description
    alike", because the search now spans both — so a rule keyed on the
    old single field would leave a name search reorderable.
    """
    needle = "unmistakable-needle"
    extra = (
        _Record(
            _step(
                identifier="listing.named",
                name=f"Carries the {needle} in its name",
            ),
            display_order=20,
        ),
        _Record(
            _step(
                identifier="listing.described",
                name="An ordinary name",
                description=f"Carries the {needle} in its description.",
            ),
            display_order=30,
        ),
    )
    store = _seeded_store(extra=extra)
    client = _signed_client(monkeypatch, store)

    html = _get_page(client, params={_FILTER_PARAMS["search"]: needle})

    # SPECIFIED: the reorder controls are inert.
    for identifier in ("listing.named", "listing.described"):
        assert _control(html, contains=(identifier, "up")) is None
        assert _control(html, contains=(identifier, "top")) is None
    # SPECIFIED: the page says why, and offers to clear the search in one
    # action.
    lowered = html.lower()
    assert "reorder" in lowered
    assert "search" in lowered
    assert (
        _control(html, contains=("clear",)) is not None
        or _control(html, contains=(_FILTER_PARAMS["search"] + "=",)) is not None
    ), "the page offers no one-action way out of the search"
