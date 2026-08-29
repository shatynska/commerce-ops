"""Every write on the playbook admin page reaches the roster the page
reads.

Derived strictly from the delta spec
`openspec/changes/restore-admin-step-writes/specs/playbook-admin/spec.md`
(ADDED requirement *Every write is judged against the same roster the
page reads* — all three scenarios), plus the **surface half** of
`.../specs/playbook-authoring/spec.md`'s case 3, which `tasks.md` 5.4
places here: a mis-wired collaborator's refusal is not rendered among the
page's coherence faults.

## The arrangement that reproduces the production fault

Every roster double in `tests/unit/launch/` answers `list_people()`, so
the suite has only ever handed the page a *reader*. Production injects a
`RosterStore` — `load()` / `save()` and nothing else — and the five write
routes pass it straight through. `_RosterStore` below is that shape, and
its rows are built by driving `access`'s own `create_person` use case, so
they are the real rows the page's read path adapts rather than a guess at
their shape.

Confirmed against this arrangement at commit `a9414ba`: the page renders
(the read path adapts the store correctly), every write answers `500`,
and nothing is persisted — `proposal.md` — *Why*, reproduced.

## Fixed by the artifacts, and what is INVENTED

Fixed: the five write routes (`create`, `save_edit`, `retire`,
`unretire`, `change_status`); the injected collaborator stays the store
because `_require_admin` needs one (`design.md` — *The page adapts the
store*); the page's read path already reaches the roster through
`access`'s `list_people`.

INVENTED, recorded in the manifest with correction points named:

- The page module's seams: `steps`, `roster`, `verify_admin_session`,
  substituted with a raising `monkeypatch.setattr` — the convention the
  sibling admin tests established. Correction point: `_signed_client`.
- The session cookie's name, `admin_session`. Correction point:
  `_SESSION_COOKIE`.
- Control-discovery vocabulary: a control's URL, hidden fields and text
  name the action it takes ("edit", "retire", "unretire", "status",
  "create"). Correction point: the `_*_HINTS` constants.
- Fault wording. The refusal's phrasing is not fixed by any artifact;
  what is asserted is that the fault names the person, which the delta
  does fix. Correction point: `_names_the_person`.

## Expected first-run state

Every test in this file fails, and each fails on the same thing: the
write answers `500` and persists nothing, because the store-shaped
collaborator reaches `playbook_authoring._read_people` unadapted. That
is the fault the change removes.

One exception, deliberate:
`test_a_mis_wired_collaborator_is_not_rendered_as_a_fault_of_the_submission`
is expected to **PASS** on its first run. A collaborator the page cannot
adapt already fails loudly rather than being rendered as a rejection of
what the admin submitted, and the delta's case 3 requires that it goes
on doing so once the page starts adapting the store itself. It is
recorded in the manifest as a regression guard, not as coverage of new
behaviour.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 985 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26, commit `a9414ba`, clean tree).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.access.application import create_person
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

A_DISCIPLINE: Final = next(iter(Discipline))

EDITED: Final = "listing.zeta"
RETIRED_ALREADY: Final = "listing.omega"
UNOWNED: Final = "listing.unowned"

#: An identifier no roster in this file carries, and which the page
#: therefore never offers.
NOBODY: Final = "prs_00000000-never-on-any-roster"

_CREATE_HINTS: Final = ("new", "create", "add")
_RETIRED_PARAM: Final = "retired"

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


# ---------------------------------------------------------------------------
# Step store, records and definitions (the shape the sibling admin tests
# record)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": EDITED,
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
        "assignees": (),
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


def _seeded_store(*, person: str) -> _FakeStepStore:
    """One `active` blocking step per gate — so nothing here leaves a
    gate unheld — the step the edit and status tests touch, one already
    retired for the un-retire write, and one draft naming somebody the
    roster does not carry."""
    holding = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                blocking=True,
                assignees=(person,),
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return _FakeStepStore(
        holding
        + (
            _Record(
                _step(
                    identifier=EDITED, name="Work of listing.zeta", assignees=(person,)
                ),
                20,
            ),
            _Record(
                _step(
                    identifier=RETIRED_ALREADY,
                    name="Work of listing.omega",
                    status=StepStatus.RETIRED,
                ),
                30,
            ),
            _Record(
                _step(
                    identifier=UNOWNED,
                    name="Work nobody on the roster owns",
                    status=StepStatus.DRAFT,
                    assignees=(NOBODY,),
                ),
                40,
            ),
        )
    )


def _record_named(store: _FakeStepStore, identifier: str) -> _Record:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _identifiers(store: _FakeStepStore) -> set[str]:
    return {record.definition.identifier for record in store.records}


# ---------------------------------------------------------------------------
# The roster collaborator production actually injects
# ---------------------------------------------------------------------------


class _RosterStore:
    """`PostgresRoster`'s shape: `load()` / `save()` and nothing else.

    The shape `tests/unit/access/application/test_roster_writes.py`
    records for `access`'s own roster writes — which is what makes it the
    right double here: it is the object `main.py` injects, not an
    invented stand-in.
    """

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
        self.version += 1


def _roster_carrying(*people: tuple[str, str]) -> tuple[_RosterStore, tuple[str, ...]]:
    """A roster store holding real `access` rows, and their identifiers.

    Driven through `access`'s own `create_person` rather than assembled
    by hand, so the rows are the ones the page's read path adapts — the
    row shape is `access`'s to own (`design.md` — *The page adapts the
    store*, rejected alternative).
    """
    store = _RosterStore()

    async def _fill() -> tuple[str, ...]:
        made: list[str] = []
        for position, (display_name, slack_identity) in enumerate(people):
            await create_person(
                roster=store,
                principal=PRINCIPAL,
                display_name=display_name,
                slack_identity=slack_identity,
                clickup_user_id=f"clickup-{slack_identity}",
                # `access` refuses a roster left without an active admin,
                # so the first person carries the authority. Incidental to
                # everything asserted here.
                admin=position == 0,
            )
            made.append(_identifier_of(store, slack_identity))
        return tuple(made)

    return store, asyncio.run(_fill())


def _identifier_of(store: _RosterStore, slack_identity: str) -> str:
    """The generated identifier of a stored row, read the way the sibling
    tests read one: through whichever attribute carries it, failing
    loudly rather than defaulting."""
    for row in store.rows:
        for target in (row, getattr(row, "person", None)):
            if target is None:
                continue
            spelling = next(
                (
                    name
                    for name in ("slack_identity", "slack_user_id", "slack_id")
                    if hasattr(target, name)
                ),
                None,
            )
            if spelling is None or str(getattr(target, spelling)) != slack_identity:
                continue
            for name in ("identifier", "id", "person_id"):
                if hasattr(target, name):
                    return str(getattr(target, name))
    pytest.fail(
        f"no stored roster row carries the Slack identity {slack_identity!r} "
        "under any known spelling — correct `_identifier_of` to `access`'s "
        "stored row"
    )


# ---------------------------------------------------------------------------
# An HTML tree, and the controls a page offers
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
            self._stack[-1].children.append(_Text(_flat(data)))


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


def _texts(node: _Node) -> list[str]:
    found: list[str] = []
    for child in node.children:
        if isinstance(child, _Text):
            found.append(child.text)
        else:
            found.extend(_texts(child))
    return found


def _all_text(html: str) -> str:
    return _flat(" ".join(_texts(_tree(html))))


def _options_of(node: _Node) -> tuple[tuple[str, str], ...]:
    return tuple(
        (option.attrs.get("value", ""), _flat(" ".join(_texts(option))))
        for option in _elements(node)
        if option.tag == "option"
    )


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


@dataclass(frozen=True)
class _Control:
    method: str
    url: str
    fields: tuple[tuple[str, str], ...] = ()
    disabled: bool = False

    def data(self) -> dict[str, str]:
        return dict(self.fields)

    @property
    def haystack(self) -> str:
        rendered = " ".join(f"{name}={value}" for name, value in self.fields)
        return f"{self.url} {rendered}".lower()


def _form_control(node: _Node) -> _Control:
    method = (node.attrs.get("method") or "get").lower()
    url = node.attrs.get("action", "")
    for verb in _HX_VERBS:
        if verb in node.attrs:
            method = verb.removeprefix("hx-")
            url = node.attrs[verb]
    fields: dict[str, str] = {}
    disabled = True
    for element in _elements(node):
        name = element.attrs.get("name")
        if element.tag == "input":
            kind = (element.attrs.get("type") or "text").lower()
            if kind in ("submit", "image"):
                disabled = disabled and "disabled" in element.attrs
                if name:
                    fields[name] = element.attrs.get("value", "")
                continue
            if not name:
                continue
            if kind in ("checkbox", "radio") and "checked" not in element.attrs:
                continue
            fields[name] = element.attrs.get(
                "value", "on" if kind == "checkbox" else ""
            )
        elif element.tag == "select" and name:
            fields[name] = _selected_of(element)
        elif element.tag == "textarea" and name:
            fields[name] = _flat(" ".join(_texts(element)))
        elif (
            element.tag == "button"
            and (element.attrs.get("type") or "submit").lower() == "submit"
        ):
            disabled = disabled and "disabled" in element.attrs
            if name:
                fields[name] = element.attrs.get("value", "")
    return _Control(method, url, tuple(fields.items()), disabled)


def _controls(html: str) -> list[_Control]:
    found: list[_Control] = []
    for element in _elements(_tree(html)):
        if element.tag == "form":
            found.append(_form_control(element))
        elif element.tag == "a" and "href" in element.attrs:
            href = element.attrs["href"]
            found.append(_Control("get", href, (), href in ("", "#")))
    return found


def _first_control(
    html: str, *, contains: tuple[str, ...], excluding: tuple[str, ...] = ()
) -> _Control | None:
    for control in _controls(html):
        if control.disabled:
            continue
        haystack = control.haystack
        if all(part.lower() in haystack for part in contains) and not any(
            word.lower() in haystack for word in excluding
        ):
            return control
    return None


def _require_control(
    html: str, *, contains: tuple[str, ...], excluding: tuple[str, ...] = ()
) -> _Control:
    found = _first_control(html, contains=contains, excluding=excluding)
    if found is None:
        pytest.fail(
            f"no live control mentioning {contains} (excluding {excluding}) was "
            "discovered on this surface — correct this file's control "
            "vocabulary to the implemented page"
        )
    return found


def _states(html: str) -> dict[str, _Node]:
    found: dict[str, _Node] = {}
    for element in _elements(_tree(html)):
        name = element.attrs.get("name")
        if name and element.tag in ("input", "select", "textarea"):
            found.setdefault(name, element)
    return found


def _field(
    fields: dict[str, str], fragment: str, *, excluding: tuple[str, ...] = ()
) -> str:
    # An exact field name wins outright. Since
    # `let-a-step-say-when-it-starts` the form carries two gate-valued
    # controls — the step's own `gate` and its `starts_at_gate` — so a
    # bare substring search for "gate" is ambiguous where addressing the
    # named field is not. Substring matching still covers every field
    # whose spelling this file does not fix.
    if fragment in fields:
        return fragment
    matches = [
        name
        for name in fields
        if fragment in name and not any(word in name for word in excluding)
    ]
    if len(matches) != 1:
        pytest.fail(
            f"{len(matches)} submitted fields mention {fragment!r} (excluding "
            f"{excluding}): {matches} among {sorted(fields)} — correct this "
            "file's field addressing to the implemented form"
        )
    return matches[0]


def _option_matching(html: str, field_name: str, hint: str) -> str:
    control = _states(html).get(field_name)
    if control is None:
        pytest.fail(f"the surface renders no control named {field_name!r}")
    for value, label in _options_of(control):
        if hint.lower() in value.lower() or hint.lower() in label.lower():
            return value
    pytest.fail(
        f"the control {field_name!r} offers no option mentioning {hint!r} "
        f"(options: {_options_of(control)})"
    )


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


async def _fake_verify(*args: Any, **kwargs: Any) -> str | None:
    haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
    return PRINCIPAL if _SESSION_VALUE in haystack else None


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore, roster: Any
) -> TestClient:
    """The page, wired as `main.py` wires it: the roster seam holds the
    **store**, which `_require_admin` needs for `verify_admin_session`."""
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "roster", roster)
    app = FastAPI()
    app.include_router(page_module.router)
    client = TestClient(app, raise_server_exceptions=False)
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


def _issue(
    client: TestClient,
    control: _Control,
    *,
    data: dict[str, Any] | None = None,
) -> Any:
    method = control.method.upper()
    target = _resolve(control.url.split("#")[0])
    payload = control.data() if data is None else data
    if method == "GET":
        return client.get(target, params=payload, follow_redirects=False)
    return client.request(method, target, data=payload, follow_redirects=False)


def _get_page(client: TestClient, params: dict[str, str] | None = None) -> str:
    response = client.get(_page_path(), params=params)
    assert response.status_code == 200, response.text
    return str(response.text)


def _open(client: TestClient, control: _Control) -> str:
    response = _issue(client, control)
    assert response.status_code == 200, (
        f"following {control.url!r} answered {response.status_code}: "
        f"{response.text[:800]}"
    )
    return str(response.text)


def _edit_surface(client: TestClient, step_id: str = EDITED) -> str:
    return _open(
        client, _require_control(_get_page(client), contains=(step_id, "edit"))
    )


def _create_surface(client: TestClient) -> str:
    page = _get_page(client)
    for control in _controls(page):
        if control.method.upper() != "GET" or control.disabled:
            continue
        if not any(hint in control.url.lower() for hint in _CREATE_HINTS):
            continue
        if control.url.startswith(("#", "http://", "https://", "mailto:")):
            continue
        response = _issue(client, control)
        if response.status_code == 200 and "name" in _states(response.text):
            return str(response.text)
    pytest.fail(
        "no control on the list led to a create surface carrying the "
        "authorable form — correct `_CREATE_HINTS` to the implemented page"
    )


def _retired_view(client: TestClient) -> str:
    control = _first_control(_get_page(client), contains=("retired",))
    if control is not None:
        response = _issue(client, control)
        if response.status_code == 200 and RETIRED_ALREADY in response.text:
            return str(response.text)
    return _get_page(client, params={_RETIRED_PARAM: "1"})


def _authoring_form(html: str) -> _Control:
    for control in _controls(html):
        if control.method.upper() == "GET" or control.disabled:
            continue
        names = [name for name, _ in control.fields]
        if any("name" in n for n in names) and any("anchor" in n for n in names):
            return control
    pytest.fail(
        "this surface carries no authoring form (a submittable control with a "
        "name field and a timing anchor) — correct `_authoring_form` to the "
        "implemented page"
    )


def _valid_values(html: str, *, person: str, **overrides: str) -> dict[str, str]:
    """A payload the authoring write accepts: an `active`, `human`,
    non-blocking step naming an assignee the surface itself offers, on an
    offset anchor, carrying neither an automation brief nor a handler."""
    form = _authoring_form(html)
    values = form.data()
    values[_field(values, "name", excluding=("anchor",))] = "Work this step asks for"
    values[_field(values, "gate")] = "listable"
    values[_field(values, "status")] = _option_matching(
        html, _field(values, "status"), "active"
    )
    values[_field(values, "kind", excluding=("anchor",))] = _option_matching(
        html, _field(values, "kind", excluding=("anchor",)), "human"
    )
    anchor_kind = _field(values, "anchor_kind")
    values[anchor_kind] = _option_matching(html, anchor_kind, "offset")
    values[_field(values, "anchor_days")] = "-7"
    values[_field(values, "assignee")] = person
    for name in list(values):
        if "automation_brief" in name or name.endswith("handler"):
            values[name] = ""
    for fragment, value in overrides.items():
        values[_field(values, fragment)] = value
    return values


def _names_the_person(html: str, person: str) -> bool:
    """Whether the rendered refusal names the person it concerns.

    DERIVED reading of "the refusal concerns people the page displayed or
    offered": the identifier the write named appears in what the page
    says. Correction point if the page names people by display name
    instead — a refusal naming the person some other way still satisfies
    the delta, and this predicate is what would need widening.
    """
    return person in _all_text(html)


# ---------------------------------------------------------------------------
# ADDED requirement: Every write is judged against the same roster the
# page reads
# ---------------------------------------------------------------------------


def test_a_write_names_a_person_the_page_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A write names a person the page offered.

    WHEN an author saves a step naming an assignee the page offered them
    in the assignee control
    THEN the write is judged on the rules, not refused for being unable
    to read the roster
    AND the step is saved naming that person.

    The person is not supplied to the submission from outside: it is read
    off the assignee control the page itself rendered, which is what ties
    "the page offered" to "the write named". A page that offers people it
    cannot then be written against fails here rather than passing on a
    fixture both halves were handed.
    """
    roster, (alice,) = _roster_carrying(("Alice Admin", "U01ALICE"))
    store = _seeded_store(person=alice)
    client = _signed_client(monkeypatch, store, roster)

    surface = _edit_surface(client)
    offered = [value for value, _ in _options_of(_states(surface)["assignees"])]

    # DERIVED guard: the control really offers the roster's person, so
    # the submission below names somebody the page offered.
    assert alice in offered, (
        f"the assignee control offers {offered}, which does not include the "
        f"roster's own person {alice!r} — the read path is not reaching the "
        "roster either, and this test would be asserting nothing"
    )

    values = _valid_values(surface, person=alice, name="Work of listing.zeta, reworded")
    response = _issue(client, _authoring_form(surface), data=values)

    # SPECIFIED: judged on the rules, not refused for being unable to
    # read the roster.
    assert response.status_code < 500, (
        "the write answered "
        f"{response.status_code} naming a person the page had just offered — "
        "the page reads the roster one way and writes against it another: "
        f"{response.text[:400]}"
    )
    # SPECIFIED: and the step is saved naming that person.
    assert len(store.saves) == 1, (
        "the write persisted nothing, so the step naming a person the page "
        f"offered was not saved: {_all_text(response.text)[:500]}"
    )
    saved = _record_named(store, EDITED).definition
    assert tuple(saved.assignees) == (alice,)
    assert saved.name == "Work of listing.zeta, reworded"


@pytest.mark.parametrize(
    "write",
    ("create", "save_edit", "retire", "unretire", "change_status"),
)
def test_each_write_reaches_the_roster(
    monkeypatch: pytest.MonkeyPatch, write: str
) -> None:
    """Scenario: Each write reaches the roster.

    WHEN a create, an edit, a status change, a retirement or an
    un-retirement is submitted from the page
    THEN each one evaluates its roster preconditions against the roster
    the page reads.

    Parametrised over all five because the delta names all five and the
    fault is in all five: a fix applied to one route would pass a
    single-write test and leave the other four answering `500`.

    This half establishes that each write reaches *a* roster it can read
    — it completes and persists, rather than failing on the collaborator.
    That it is *the page's own* roster is the other half, established by
    `test_a_roster_refusal_is_explicable_from_the_page` and by
    `test_a_write_names_a_person_the_page_offered`, which read the person
    off the page and write against it.

    Retiring, un-retiring and changing status are submitted through the
    step's edit form now (`move-step-actions-into-step-pages`), the same
    `status` field an ordinary field edit uses — not a dedicated row
    control, which no longer exists. `unretire_step`
    (`playbook_authoring.py`) always returns a step to `in-development`,
    never `active`, so that is the value the `unretire` case submits.
    """
    roster, (alice,) = _roster_carrying(("Alice Admin", "U01ALICE"))
    store = _seeded_store(person=alice)
    client = _signed_client(monkeypatch, store, roster)
    before = _identifiers(store)

    if write == "create":
        surface = _create_surface(client)
        values = _valid_values(surface, person=alice, name="Brand new listable work")
        response = _issue(client, _authoring_form(surface), data=values)
    elif write == "save_edit":
        surface = _edit_surface(client)
        values = _valid_values(surface, person=alice, name="Work of listing.zeta again")
        response = _issue(client, _authoring_form(surface), data=values)
    elif write == "retire":
        surface = _edit_surface(client, EDITED)
        control = _authoring_form(surface)
        values = control.data()
        values[_field(values, "status")] = _option_matching(
            surface, "status", "retired"
        )
        response = _issue(client, control, data=values)
    elif write == "unretire":
        # A retired step's name is not on the default list view (retired
        # steps are hidden there), so its edit surface is reached from
        # the view that reveals them rather than through `_edit_surface`.
        surface = _open(
            client,
            _require_control(_retired_view(client), contains=(RETIRED_ALREADY, "edit")),
        )
        control = _authoring_form(surface)
        values = control.data()
        values[_field(values, "status")] = _option_matching(
            surface, "status", "in-development"
        )
        response = _issue(client, control, data=values)
    else:
        surface = _edit_surface(client, EDITED)
        control = _authoring_form(surface)
        values = control.data()
        values[_field(values, "status")] = _option_matching(surface, "status", "draft")
        response = _issue(client, control, data=values)

    # SPECIFIED: the write evaluates its preconditions against the roster
    # the page reads — so it reaches a roster it can read at all.
    assert response.status_code < 500, (
        f"the {write} write answered {response.status_code} against the roster "
        "collaborator the page is given, so it never got as far as evaluating "
        f"anything: {response.text[:400]}"
    )
    assert len(store.saves) == 1, (
        f"the {write} write persisted nothing and reported "
        f"{response.status_code}: {_all_text(response.text)[:500]}"
    )
    if write == "create":
        assert _identifiers(store) - before, "the create landed without a new step"


def test_a_roster_refusal_is_explicable_from_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A roster refusal is explicable from the page.

    WHEN a write is refused on roster grounds
    THEN the refusal concerns people the page displayed or offered, and
    never the page's inability to read the roster at all.

    The write names somebody the page never offered, which is the one way
    to provoke a refusal that really is about people. The assertions then
    separate the two refusals the admin cannot currently tell apart: one
    naming a person, and one that is the page failing to read the roster
    — which today is the only one there is.
    """
    roster, (alice,) = _roster_carrying(("Alice Admin", "U01ALICE"))
    store = _seeded_store(person=alice)
    client = _signed_client(monkeypatch, store, roster)

    surface = _edit_surface(client)
    offered = [value for value, _ in _options_of(_states(surface)["assignees"])]
    assert NOBODY not in offered, (
        "the page offers the very person this test relies on it never having "
        "offered, so the refusal below would be explicable after all"
    )

    values = _valid_values(surface, person=NOBODY)
    response = _issue(client, _authoring_form(surface), data=values)

    # SPECIFIED: never the page's inability to read the roster at all —
    # a refusal the admin can act on is rendered, not an error.
    assert response.status_code < 500, (
        "the write naming an unknown person answered "
        f"{response.status_code} rather than a refusal the page can render, so "
        "an admin cannot tell a person who is not on the roster from a page "
        f"that cannot read one: {response.text[:400]}"
    )
    # SPECIFIED: the refusal concerns people the page displayed or
    # offered — it names the person the write named.
    assert _names_the_person(response.text, NOBODY), (
        "the refusal does not name the person it concerns: "
        f"{_all_text(response.text)[:600]}"
    )
    assert store.saves == [], "a refused write persisted a step set"
    # SPECIFIED corollary: the write that *is* judged on the rules is the
    # same write, so the refusal above is about the person and not about
    # the collaborator.
    accepted = _issue(
        client, _authoring_form(surface), data=_valid_values(surface, person=alice)
    )
    assert accepted.status_code < 500 and len(store.saves) == 1, (
        "the same write naming a person the page offered was not accepted, so "
        "the refusal above cannot be attributed to the person it named"
    )


# ---------------------------------------------------------------------------
# playbook-authoring, case 3 — the surface half (`tasks.md` 5.4)
# ---------------------------------------------------------------------------


def test_a_mis_wired_collaborator_is_not_rendered_as_a_fault_of_the_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`playbook-authoring` — *A mis-wiring is not reported as a
    rejection of the submission*, read on the surface (`tasks.md` 5.4).

    WHEN the page is given a roster collaborator it cannot read
    THEN the refusal is not rendered among the page's coherence faults,
    and the submission is not presented back as a rejected one.

    "A surface that renders coherence faults SHALL NOT be able to present
    it as one" — because at `200`, with the submitted values back in the
    form and a fault beside them, nothing distinguishes a broken
    deployment from an edit the rules refused.

    Expected to **PASS** on its first run: an unreadable collaborator
    already fails loudly. The delta requires that it goes on doing so
    once the page starts adapting the store itself, which is the change
    that could quietly turn it into a rendered fault. Recorded in the
    manifest as a regression guard.
    """

    class _AnswersNothing:
        """Neither the store the page adapts nor a reader it could use."""

    roster, (alice,) = _roster_carrying(("Alice Admin", "U01ALICE"))
    store = _seeded_store(person=alice)

    # The surface is opened against a readable roster — the mis-wiring is
    # introduced at the write, so the form under test is a real one.
    client = _signed_client(monkeypatch, store, roster)
    surface = _edit_surface(client)
    values = _valid_values(surface, person=alice, name="Work of listing.zeta, reworded")

    monkeypatch.setattr(page_module, "roster", _AnswersNothing())
    response = _issue(client, _authoring_form(surface), data=values)

    # SPECIFIED: not presented as a rejection of what was submitted.
    assert response.status_code >= 500, (
        "the page answered "
        f"{response.status_code} for a collaborator it cannot read, which is "
        "the status a rejected-but-rendered write answers — a mis-wiring that "
        "answers success-shaped statuses is invisible to everything that is "
        "not a browser"
    )
    assert _authoring_form_absent(response), (
        "the mis-wiring re-rendered the authoring form with the submitted "
        "values, which is this surface's rendering of a rejected submission"
    )
    # SPECIFIED: and nothing was persisted.
    assert store.saves == []


def _authoring_form_absent(response: Any) -> bool:
    body = response.text
    if "<form" not in body:
        return True
    return all(
        control.method.upper() == "GET"
        or not any("anchor" in n for n, _ in control.fields)
        for control in _controls(body)
    )
