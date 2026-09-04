"""A write that fails on the playbook admin page is never silent.

Derived strictly from the delta spec
`openspec/changes/restore-admin-step-writes/specs/playbook-admin/spec.md`
(ADDED requirement *A write that fails is never silent* — all nine
scenarios), plus `tasks.md` 5.5, which places the server half of *The
guard's refusal stays indistinguishable* here.

## What this project can and cannot assert

The requirement is half server-observable and half browser behaviour, and
`tasks.md` 5.3 draws the line: this project has three Python test tiers
(`AGENTS.md` — *Testing Strategy*) and **no JavaScript tier**, so nothing
here executes the listener. What a served response can be asked is
whether the page **ships** the listener, the container it renders into,
and the wording it would render — and whether the server goes on
answering its real status. Whether the notice then appears when htmx
raises an event is `tasks.md` 6.3 and 6.4, by hand.

Each test below says which half it carries. The manifest records the
browser halves as uncovered, with this as the reason — they are not
omitted, and they are not asserted through a proxy pretending to be them.

## Fixed by the artifacts, and what is INVENTED

Fixed by the delta and `design.md`: the two literal markers
(`write-failure-notice` for the container's role, `write-failed` only
once a failure has been reported); the three events the listener binds
(`htmx:responseError`, `htmx:sendError`, `htmx:timeout`); that the
enhanced submissions are the step list and the edit surface and **not**
the create surface; that the guard's refusal carries no distinguishing
mark; that what the notice claims is bounded — it must not say nothing
was saved.

INVENTED, recorded in the manifest with correction points named:

- The markers are read as **class tokens** on the container element, the
  reading `test_playbook_admin_presentation_vocabulary.py` already
  established for `just-created`, `row-action` and `danger`. A page
  marking them another way (a `data-` attribute, an `id`) corrects
  `_carries`, not the requirement.
- The enhancement is htmx's `hx-boost`, which `design.md` — *A failed
  write is surfaced on the client* fixes for this page. Correction
  point: `_is_enhanced`.
- Every **phrasing** set: how the notice says a write did not complete,
  that what is shown may be stale, that the admin should reload, and
  that a session ended. The delta fixes what must be said and what must
  not; no artifact fixes the words. Correcting a phrasing set to the
  implemented copy is a fixture correction; dropping one is not.
  Correction points: `_DID_NOT_COMPLETE`, `_MAY_BE_STALE`, `_RELOAD`,
  `_SESSION_ENDED`, `_WAY_BACK`, `_CLAIMS_NOTHING_SAVED`.
- The page seams (`steps`, `members`, `verify_admin_session`) and the
  session cookie, as the sibling admin tests record them.

## What the page already ships, and why it is not enough

The step list — and only the step list — already binds
`htmx:responseError` and, on a `404`, replaces the whole document body
with a *Signed out* message reading "This admin session has ended and
**nothing was saved**". Three things follow, and each is asserted below
rather than assumed:

- It is on `page.html`, not on the shared header partial, so the edit
  surface has nothing at all (`design.md` — *The listener lives in the
  shared header partial*).
- It claims exactly what the delta forbids a report from claiming, so
  *The report does not claim what the page cannot know* has a live
  violation to remove and not merely an absence to fill.
- It binds one of the three events, leaving the deploy-restart case —
  a submission that gets no response — as silent as before.

No existing test asserts any of that copy (searched across
`tests/**/test_*.py` for its wording and for `htmx:responseError`), so
nothing in the suite is superseded by replacing it; the manifest records
that search and its result.

## Expected first-run state

Eleven parametrised cases fail. No admin page carries a
`write-failure-notice` container; the edit surface ships no client
behaviour at all; and the step list's existing listener binds one event
of three and says the forbidden thing. Verified at commit `a9414ba`:
`write-failure` appears nowhere in any rendered admin page.

One parametrised case passes where its sibling fails, and the split is
the point: `test_an_ended_session_says_so[the step list]` passes because
`page.html`'s existing listener already names the guard's `404`, says
"session" and offers a way back, while `[the edit surface]` fails because
that listener was never shared. Recorded in the manifest as
**partly-satisfied**, not as coverage: what the passing case now guards
is that moving the listener into the shared partial does not lose the
session reading on the way.

Four more are expected to **PASS** on their first run and are recorded in
the manifest as regression guards rather than as coverage of new
behaviour:

- `test_a_failed_write_does_not_read_as_a_successful_one` — the server
  already answers its real status and persists nothing. The delta states
  it because the client half of this change is the kind that gets built
  by making the server answer `200` instead (`design.md` rejects exactly
  that alternative), and this is what would catch it.
- `test_the_guards_refusal_stays_indistinguishable` — the guard already
  answers a write route exactly as it answers an unregistered one. The
  delta binds it here on its own account because the client-side session
  reading is a reason someone might mark the refusal to make it easier
  to recognise.
- `test_which_submissions_the_page_enhances_is_fixed` — the list and the
  edit surface boost, the create surface does not. Fixed by the delta so
  that a later change to the set amends the requirement rather than
  silently shrinking what an admin is told.
- `test_a_failure_is_visible_on_a_submission_the_page_does_not_enhance` —
  the create surface is already un-enhanced and a failed create already
  answers a status the browser can render. Both halves are what make the
  browser's own rendering the admin's report on that surface, and either
  could be lost while the enhanced surfaces are being taught to report.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 985 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26, commit `a9414ba`, clean tree).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
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
from tests.support.admin import SESSION_COOKIE as _SESSION_COOKIE
from tests.support.admin import SESSION_VALUE as _SESSION_VALUE
from tests.support.admin import fake_verify
from tests.support.fakes import FakeMembers, FakeStepStore
from tests.support.fixtures import ALICE, ALICE_NAME, PRINCIPAL
from tests.support.html import HX_VERBS as _HX_VERBS
from tests.support.html import Node as _Node
from tests.support.html import classes as _classes
from tests.support.html import elements as _elements
from tests.support.html import flat as _flat
from tests.support.html import texts as _texts
from tests.support.html import tree as _tree
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

# ---------------------------------------------------------------------------
# The delta's two literal markers, and the three events it binds
# ---------------------------------------------------------------------------

WRITE_FAILURE_NOTICE: Final = "write-failure-notice"
WRITE_FAILED: Final = "write-failed"

#: Normalised so a listener bound in a script (`htmx:responseError`) and
#: one bound as an attribute (`hx-on::response-error`) read alike.
RESPONSE_ERROR: Final = "responseerror"
SEND_ERROR: Final = "senderror"
TIMEOUT: Final = "timeout"

_BOUND_EVENTS: Final = (
    ("htmx:responseError", RESPONSE_ERROR),
    ("htmx:sendError", SEND_ERROR),
    ("htmx:timeout", TIMEOUT),
)

# --- Phrasing sets (INVENTED — see the docstring) ---------------------------

#: The notice says the write did not complete.
_DID_NOT_COMPLETE: Final = (
    "did not complete",
    "didn't complete",
    "did not go through",
    "was not completed",
    "could not be completed",
    "not complete",
)
#: … that what is on screen may no longer describe the step set.
_MAY_BE_STALE: Final = (
    "may no longer",
    "might no longer",
    "may not describe",
    "may be out of date",
    "out of date",
    "may not reflect",
)
#: … and directs the admin to reload.
_RELOAD: Final = ("reload", "refresh")
#: An ended session, called by its name.
_SESSION_ENDED: Final = ("session",)
#: … offering the way back. Deliberately generous: the delta requires
#: that a way back is offered, not how it is worded, and the surface's
#: existing signed-out copy already words it a fourth way ("mint a fresh
#: link with the Slack command and reopen the page").
_WAY_BACK: Final = (
    "sign in",
    "sign-in",
    "log in",
    "log-in",
    "start again",
    "again",
    "fresh link",
    "new link",
    "slack",
    "reopen",
)
#: What the notice must never claim.
_CLAIMS_NOTHING_SAVED: Final = (
    "nothing was saved",
    "nothing has been saved",
    "nothing was persisted",
    "no changes were saved",
    "was not saved",
    "were not saved",
    "nothing saved",
)

A_DISCIPLINE: Final = next(iter(Discipline))
EDITED: Final = "listing.zeta"

_CREATE_HINTS: Final = ("new", "create", "add")


# ---------------------------------------------------------------------------
# Step store, records and members double (the sibling admin tests' shapes)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": EDITED, "assignees": (ALICE,), **overrides})


_FakeStepStore = FakeStepStore[_Record]


class _StoreThatCannotPersist(_FakeStepStore):
    """A step store whose persistence fails for a reason the page has no
    fault rendering for — the delta's "a response the page cannot
    render"."""

    async def save(self, records: Any, *, expected_version: int) -> None:
        raise RuntimeError("the step set could not be written")


class _FakeMembers(FakeMembers):
    def __init__(self) -> None:
        super().__init__((_Member(ALICE, ALICE_NAME),))


def _seeded_store(kind: type[_FakeStepStore] = _FakeStepStore) -> _FakeStepStore:
    records = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                blocking=True,
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    ) + (_Record(_step(identifier=EDITED, name="Work of listing.zeta"), 20),)
    return kind(records)


# ---------------------------------------------------------------------------
# An HTML tree, so a marker can be read off the element that carries it
# ---------------------------------------------------------------------------


def _carries(node: _Node, marker: str) -> bool:
    """Whether an element carries a marker (INVENTED reading — a class
    token, as this capability's served vocabulary tests already read
    `just-created`). Correction point for a page marking another way."""
    return marker in _classes(node)


def _marked(html: str, marker: str) -> list[_Node]:
    return [element for element in _elements(_tree(html)) if _carries(element, marker)]


def _scripts(html: str) -> str:
    """Every line of client behaviour the page ships: the contents of its
    `<script>` elements plus any inline event-handler attributes."""
    root = _tree(html)
    parts: list[str] = []
    for element in _elements(root):
        if element.tag == "script":
            parts.extend(_texts(element))
        for name, value in element.attrs.items():
            if name.startswith(("hx-on", "on")):
                parts.append(f"{name} {value}")
    return " ".join(parts)


def _report_copy(html: str) -> str:
    """The wording the failure report itself could show.

    Scoped to the notice container's own subtree and the page's client
    behaviour, rather than to everything the page renders: the report's
    wording has to live where the report is — pre-rendered in the
    container, or in the script that fills it. Reading the whole page
    would let an unrelated table cell satisfy a clause about what the
    notice says, and would fail a clause about what it must not say on
    copy belonging to something else.
    """
    inside = " ".join(
        " ".join(_texts(container)) for container in _marked(html, WRITE_FAILURE_NOTICE)
    )
    return _flat(f"{inside} {_scripts(html)}").lower()


def _normalised(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _says(copy: str, phrasings: tuple[str, ...]) -> bool:
    return any(phrase in copy for phrase in phrasings)


def _ancestors_or_self(node: _Node) -> Iterator[_Node]:
    walker: _Node | None = node
    while walker is not None and walker.tag != "#document":
        yield walker
        walker = walker.parent


def _is_enhanced(node: _Node) -> bool:
    """Whether a submission from this element is progressively enhanced.

    INVENTED as htmx's `hx-boost`, which `design.md` fixes for this page:
    the nearest ancestor-or-self declaring it decides, so the create
    form's own `hx-boost="false"` overrides a boosted body.
    """
    for element in _ancestors_or_self(node):
        declared = element.attrs.get("hx-boost")
        if declared:
            return declared.strip().lower() == "true"
    return False


def _submitting_forms(html: str) -> list[_Node]:
    return [
        element
        for element in _elements(_tree(html))
        if element.tag == "form"
        and (
            element.attrs.get("method", "get").lower() == "post"
            or any(verb in element.attrs for verb in _HX_VERBS)
        )
    ]


# ---------------------------------------------------------------------------
# Controls, so a write can be submitted the way the page offers it
# ---------------------------------------------------------------------------


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


def _selected_of(node: _Node) -> str:
    options = [option for option in _elements(node) if option.tag == "option"]
    for option in options:
        if "selected" in option.attrs:
            return option.attrs.get("value", "")
    return options[0].attrs.get("value", "") if options else ""


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


def _require_control(
    html: str, *, contains: tuple[str, ...], excluding: tuple[str, ...] = ()
) -> _Control:
    for control in _controls(html):
        if control.disabled:
            continue
        haystack = control.haystack
        if all(part.lower() in haystack for part in contains) and not any(
            word.lower() in haystack for word in excluding
        ):
            return control
    pytest.fail(
        f"no live control mentioning {contains} (excluding {excluding}) was "
        "discovered — correct this file's control vocabulary to the "
        "implemented page"
    )


# ---------------------------------------------------------------------------
# App harness
# ---------------------------------------------------------------------------


_fake_verify = fake_verify(PRINCIPAL)


def _app(monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore) -> FastAPI:
    monkeypatch.setattr(page_module, "steps", store)
    monkeypatch.setattr(page_module, "verify_admin_session", _fake_verify)
    monkeypatch.setattr(page_module, "members", _FakeMembers())
    app = FastAPI()
    app.include_router(page_module.router)
    return app


def _client(monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore) -> TestClient:
    return TestClient(_app(monkeypatch, store), raise_server_exceptions=False)


def _signed_client(
    monkeypatch: pytest.MonkeyPatch, store: _FakeStepStore
) -> TestClient:
    client = _client(monkeypatch, store)
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


def _write_routes() -> list[str]:
    """Every POST route the page registers, addressed concretely."""
    found: list[str] = []
    for route in page_module.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and "POST" in methods:
            found.append(path.replace("{step_id}", EDITED))
    assert found, "the page router registers no write route"
    return found


def _resolve(url: str) -> str:
    if not url:
        return _page_path()
    if url.startswith("/"):
        return url
    return urljoin(_page_path() + "/", url)


def _issue(
    client: TestClient, control: _Control, *, data: dict[str, Any] | None = None
) -> Any:
    method = control.method.upper()
    target = _resolve(control.url.split("#")[0])
    payload = control.data() if data is None else data
    if method == "GET":
        return client.get(target, params=payload, follow_redirects=False)
    return client.request(method, target, data=payload, follow_redirects=False)


def _get_page(client: TestClient) -> str:
    response = client.get(_page_path())
    assert response.status_code == 200, response.text
    return str(response.text)


def _edit_surface(client: TestClient) -> str:
    control = _require_control(_get_page(client), contains=(EDITED, "edit"))
    response = _issue(client, control)
    assert response.status_code == 200, response.text
    return str(response.text)


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
        if response.status_code == 200 and _submitting_forms(response.text):
            return str(response.text)
    pytest.fail(
        "no control on the list led to a create surface — correct "
        "`_CREATE_HINTS` to the implemented page"
    )


def _states(html: str) -> dict[str, _Node]:
    found: dict[str, _Node] = {}
    for element in _elements(_tree(html)):
        name = element.attrs.get("name")
        if name and element.tag in ("input", "select", "textarea"):
            found.setdefault(name, element)
    return found


def _options_of(node: _Node) -> tuple[tuple[str, str], ...]:
    return tuple(
        (option.attrs.get("value", ""), _flat(" ".join(_texts(option))))
        for option in _elements(node)
        if option.tag == "option"
    )


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


def _valid_values(html: str, form: _Control, *, name: str) -> dict[str, str]:
    """A payload the authoring write accepts, so a submission reaches the
    persistence that fails rather than being turned back by the rules —
    the same construction `test_playbook_admin_writes_reach_the_members.py`
    uses."""
    values = form.data()
    values[_field(values, "name", excluding=("anchor",))] = name
    values[_field(values, "gate")] = "listable"
    status = _field(values, "status")
    values[status] = _option_matching(html, status, "active")
    kind = _field(values, "kind", excluding=("anchor",))
    values[kind] = _option_matching(html, kind, "human")
    anchor_kind = _field(values, "anchor_kind")
    values[anchor_kind] = _option_matching(html, anchor_kind, "offset")
    values[_field(values, "anchor_days")] = "-7"
    values[_field(values, "assignee")] = ALICE
    for field_name in list(values):
        if "automation_brief" in field_name or field_name.endswith("handler"):
            values[field_name] = ""
    return values


@pytest.fixture()
def surfaces(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The three admin surfaces this page serves, each rendered clean."""
    client = _signed_client(monkeypatch, _seeded_store())
    return {
        "the step list": _get_page(client),
        "the edit surface": _edit_surface(client),
        "the create surface": _create_surface(client),
    }


_ENHANCED_SURFACES: Final = ("the step list", "the edit surface")


# ---------------------------------------------------------------------------
# ADDED requirement: A write that fails is never silent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_the_report_is_observable_in_the_response(
    surfaces: dict[str, str], surface: str
) -> None:
    """Scenario: The report is observable in the response.

    WHEN an admin page the failure report can render into is served
    THEN it carries a container marked `write-failure-notice`, so a
    response can be asked whether there is somewhere for the report to
    appear
    AND that container carries `write-failed` only once a failure has
    been reported into it.

    Both markers are the delta's own literals. The second assertion is
    the distinction the delta draws by name: `write-failure-notice` names
    the container's **role** and is present whether or not anything has
    failed, while a marker asserting an occurrence must not outrun the
    occurrence — so a freshly served page carries the first and not the
    second.

    Wholly server-observable: no listener has to run for a container to
    be in the response.
    """
    html = surfaces[surface]
    containers = _marked(html, WRITE_FAILURE_NOTICE)

    # SPECIFIED: the page carries a container for the report.
    assert containers, (
        f"{surface} carries no element marked {WRITE_FAILURE_NOTICE!r}, so a "
        "listener reporting a failed write would have nowhere to render — "
        "which is silence by another route"
    )
    assert len(containers) == 1, (
        f"{surface} carries {len(containers)} containers marked "
        f"{WRITE_FAILURE_NOTICE!r}; the report has one place to go"
    )
    # SPECIFIED: `write-failed` only once a failure has been reported.
    assert not _marked(html, WRITE_FAILED), (
        f"{surface} was served carrying {WRITE_FAILED!r} with no write having "
        "failed — a marker naming an occurrence has outrun the occurrence, "
        "which is the reading this capability already fixed for `just-created`"
    )


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_an_unanticipated_failure_is_reported(
    surfaces: dict[str, str], surface: str
) -> None:
    """Scenario: An unanticipated failure is reported.

    WHEN a write fails with a response the page has no fault rendering
    for
    THEN the page reports that the write did not complete and directs the
    admin to reload.

    **Server half only.** What a served response can be asked is whether
    the page ships a listener bound to the event htmx raises for a
    response it cannot render, and whether the wording it would render is
    there. That the notice then appears is `tasks.md` 6.3, by hand, and
    is recorded in the manifest as uncovered with that reason.
    """
    html = surfaces[surface]
    behaviour = _normalised(_scripts(html))
    copy = _report_copy(html)

    # SPECIFIED: the page reports a response it cannot render.
    assert RESPONSE_ERROR in behaviour, (
        f"{surface} ships no handler for htmx's response-error event, so a "
        "boosted write answering 4xx or 5xx swaps nothing and the admin sees "
        "no change at all — the defect this requirement exists to remove"
    )
    # SPECIFIED: it says the write did not complete …
    assert _says(copy, _DID_NOT_COMPLETE), (
        f"{surface} carries no wording saying a write did not complete "
        f"(looked for {_DID_NOT_COMPLETE})"
    )
    # … and directs the admin to reload.
    assert _says(copy, _RELOAD), (
        f"{surface} carries no wording directing the admin to reload "
        f"(looked for {_RELOAD})"
    )


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_a_failure_with_no_response_is_reported_too(
    surfaces: dict[str, str], surface: str
) -> None:
    """Scenario: A failure with no response is reported too.

    WHEN a write submitted through the page's progressive enhancement
    receives no response, or none in time
    THEN the page reports it exactly as it reports a failed response,
    rather than remaining as it was.

    Its own test rather than an extra assertion on the one above, because
    this is the clause a listener bound to `htmx:responseError` alone
    silently fails: every merge to `main` restarts the container
    (`AGENTS.md` — *Deployment*), so a write in flight during a deploy
    lands in exactly this case (`design.md` — *It binds three events, not
    one*).

    **Server half only**: that all three events are bound. Whether the
    handler behaves identically when each fires is `tasks.md` 6.3, by
    hand.
    """
    behaviour = _normalised(_scripts(surfaces[surface]))

    for spelling, token in _BOUND_EVENTS:
        # SPECIFIED: all three, not just the first.
        assert token in behaviour, (
            f"{surface} binds nothing for {spelling} — a submission that gets "
            "no response, or none in time, would leave the page exactly as it "
            "was, which is the silence this requirement forbids"
        )


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_the_report_does_not_claim_what_the_page_cannot_know(
    surfaces: dict[str, str], surface: str
) -> None:
    """Scenario: The report does not claim what the page cannot know.

    WHEN any such failure is reported
    THEN the report does not state that nothing was saved.

    The page observes that a submission did not complete; it cannot
    observe whether anything was persisted, because a failure raised
    after the set was written answers the same as one raised before it.
    So the notice says what is on screen may no longer describe the step
    set — and never that nothing was saved, which is "cheap to make and
    wrong exactly when it matters".
    """
    copy = _report_copy(surfaces[surface])

    # SPECIFIED: it does not state that nothing was saved.
    claimed = [phrase for phrase in _CLAIMS_NOTHING_SAVED if phrase in copy]
    assert not claimed, (
        f"{surface} carries the claim {claimed!r}. A failure raised after the "
        "set was written produces the same response as one raised before it, "
        "so this is exactly the assertion the page has no grounds for"
    )
    # SPECIFIED: what it says instead — the set may no longer be as shown.
    assert _says(copy, _MAY_BE_STALE), (
        f"{surface} carries no wording saying what is shown may no longer "
        f"describe the step set (looked for {_MAY_BE_STALE}) — without it the "
        "notice reports a failure and leaves the admin reading a stale table "
        "as though it were current"
    )


def test_a_failed_write_does_not_read_as_a_successful_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed write does not read as a successful one.

    WHEN a write fails before the set is written
    THEN the page does not render as though the write was accepted, and
    the step set is unchanged.

    Server-observable in full. `design.md` rejects two alternatives that
    would break this precisely — swapping an error body into the page,
    and answering `200` for a write that did not happen — and answering
    `200` "lies to everything that is not a browser, the deploy's health
    signals included" (`tasks.md` 4.7).

    Expected to **PASS** on its first run: the server already answers its
    real status. Recorded in the manifest as a regression guard against
    the client half being built by making the server lie.

    Retiring is submitted through the step's edit form now
    (`move-step-actions-into-step-pages`), the same `status` field an
    ordinary field edit uses — not a row-level `retire` control, which
    no longer exists.
    """
    store = _seeded_store(_StoreThatCannotPersist)
    client = _signed_client(monkeypatch, store)
    records_before = store.records

    surface = _edit_surface(client)
    control = _require_control(surface, contains=("status",))
    values = control.data()
    status_field = _field(values, "status")
    values[status_field] = _option_matching(surface, status_field, "retired")
    response = _issue(client, control, data=values)

    # SPECIFIED: the page does not render as though the write was
    # accepted — and the status says so too, since the status is what
    # everything other than a browser reads.
    assert response.status_code >= 400, (
        f"a write that could not be persisted answered {response.status_code}, "
        "which is what an accepted write answers"
    )
    assert not _marked(response.text, "just-created"), (
        "the failed write rendered the marker this page uses to distinguish a "
        "step that was just written"
    )
    # SPECIFIED: and the step set is unchanged.
    assert store.saves == []
    assert store.records == records_before


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_a_failed_write_does_not_read_as_an_unsubmitted_one(
    surfaces: dict[str, str], surface: str
) -> None:
    """Scenario: A failed write does not read as an unsubmitted one.

    WHEN a write submitted through the page's progressive enhancement
    fails
    THEN the page changes in a way the admin can see, rather than
    remaining exactly as it was before submitting.

    **Server half only**, and a narrow one: the page ships both halves of
    the pairing — a handler that reports, and a container it reports
    *into* that the handler actually addresses. `design.md` — *The
    listener lives in the shared header partial* requires the two ship
    together, "because a listener that finds no target is a listener that
    fails silently — which is the whole defect being fixed".

    That the admin then sees the change is `tasks.md` 6.3, by hand.
    """
    html = surfaces[surface]
    behaviour = _scripts(html)

    assert _marked(html, WRITE_FAILURE_NOTICE), (
        f"{surface} ships no notice container for a report to change"
    )
    # SPECIFIED: the page changes visibly — the handler addresses the
    # container and marks it as having a failure in it.
    assert WRITE_FAILURE_NOTICE in behaviour, (
        f"{surface}'s client behaviour never addresses the "
        f"{WRITE_FAILURE_NOTICE!r} container, so a failed submission would "
        "leave the page exactly as it was before it was submitted"
    )
    assert WRITE_FAILED in behaviour, (
        f"{surface}'s client behaviour never applies {WRITE_FAILED!r}, so "
        "nothing in the response distinguishes a page a failure was reported "
        "into from one where nothing was submitted"
    )


@pytest.mark.parametrize("surface", _ENHANCED_SURFACES)
def test_an_ended_session_says_so(surfaces: dict[str, str], surface: str) -> None:
    """Scenario: An ended session says so.

    WHEN a submission from the step list or the edit surface fails
    because the admin's session is no longer live
    THEN the page says the session ended and offers the way back, rather
    than reporting an unexplained failure.

    The delta scopes this to exactly these two surfaces, which is why
    this is parametrised over them and not over the create surface.

    **Server half only**: that the page ships the reading and the wording
    — it recognises the guard's answer (the page's own 404, on a route it
    had just rendered) and offers a way back. Whether the notice appears
    on a live expiry is `tasks.md` 6.3, by hand.
    """
    html = surfaces[surface]
    behaviour = _scripts(html)
    copy = _report_copy(html)

    # SPECIFIED: reached from what the page already knew about the route
    # it posted to — the 404 answering a route the server had just
    # rendered for it.
    assert "404" in behaviour, (
        f"{surface}'s client behaviour never reads the status the guard "
        "answers, so an ended session would be reported as an unexplained "
        "failure — the one case in this class an admin can act on"
    )
    # SPECIFIED: it says the session ended …
    assert _says(copy, _SESSION_ENDED), (
        f"{surface} carries no wording naming an ended session (looked for "
        f"{_SESSION_ENDED})"
    )
    # … and offers the way back.
    assert _says(copy, _WAY_BACK), (
        f"{surface} names an ended session but offers no way back (looked for "
        f"{_WAY_BACK}) — leaving the admin reloading a page that will keep "
        "refusing them"
    )


def test_the_guards_refusal_stays_indistinguishable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The guard's refusal stays indistinguishable.

    WHEN the page distinguishes an ended session from any other failure
    THEN it does so from what it already knew about the route it posted
    to, and the server's refusal is not marked to make it recognisable.

    The server half, which `tasks.md` 5.5 asks for: every write route,
    unauthorised, answers exactly as a request to an unregistered route
    does — status, body and content type alike. The existing served
    suite asserts this for the page's `GET`; the client-side session
    reading is a live reason to mark the *write* routes, which is why the
    delta binds it here on this requirement's own account.

    Expected to **PASS** on its first run, and recorded in the manifest
    as a regression guard.
    """
    client = _client(monkeypatch, _seeded_store())

    def _shape(response: Any) -> tuple[int, bytes, str | None]:
        return (
            response.status_code,
            response.content,
            response.headers.get("content-type"),
        )

    nothing = _shape(client.post("/a-route-that-was-never-registered", data={}))

    for path in _write_routes():
        refused = client.post(path, data={})
        # SPECIFIED: the refusal is not marked to make it recognisable.
        assert _shape(refused) == nothing, (
            f"an unauthorised write to {path} answers {_shape(refused)!r} "
            f"where an unregistered route answers {nothing!r} — the guard's "
            "answer is distinguishable, which makes the write routes probeable"
        )

    # DERIVED sanity guard: a verified session does reach the surface, so
    # the equalities above are not an artifact of a dead router.
    client.cookies.set(_SESSION_COOKIE, _SESSION_VALUE)
    assert client.get(_page_path()).status_code == 200


def test_a_failure_is_visible_on_a_submission_the_page_does_not_enhance(
    monkeypatch: pytest.MonkeyPatch, surfaces: dict[str, str]
) -> None:
    """Scenario: A failure is visible on a submission the page does not
    enhance.

    WHEN a write fails on a submission from the create surface, or on any
    submission where the enhancement is unavailable
    THEN the failure is still visible to the admin, even if less legibly
    presented and without the wording above.

    **Server half only.** An un-enhanced submission reaches the browser,
    which renders the failure itself — nothing this project's tiers can
    execute. What is asserted here is the two things that make that
    outcome true: the create surface really is un-enhanced, so its
    failures are the browser's to show; and the server answers a failure
    the browser can show, rather than a success-shaped response that
    would leave the browser nothing to render. The browser's own
    rendering, and the scripting-off degradation, are `tasks.md` 6.3 and
    6.4, by hand.
    """
    forms = _submitting_forms(surfaces["the create surface"])
    assert forms, "the create surface carries no submitting form"

    # SPECIFIED: this is a submission the page does not enhance.
    assert not any(_is_enhanced(form) for form in forms), (
        "the create surface's submission is enhanced after all. The delta "
        "fixes the enhanced set as the step list and the edit surface, and "
        "this clause of the requirement applies to submissions outside it"
    )

    # SPECIFIED: and a failed one leaves the browser something to show.
    store = _seeded_store(_StoreThatCannotPersist)
    client = _signed_client(monkeypatch, store)
    surface = _create_surface(client)
    form = _form_control(_submitting_forms(surface)[0])
    response = _issue(
        client,
        form,
        data=_valid_values(surface, form, name="Work authored from the create surface"),
    )

    assert response.status_code >= 400, (
        "a failed create answered "
        f"{response.status_code} — an un-enhanced submission is visible only "
        "because the browser renders the failure itself, which a "
        "success-shaped response gives it nothing to do"
    )
    assert store.saves == []


def test_which_submissions_the_page_enhances_is_fixed(
    surfaces: dict[str, str],
) -> None:
    """*A write that fails is never silent*, the clause fixing the
    enhanced set: "as of this change the step list and the edit surface
    are enhanced, and the create surface is not".

    Not a scenario of its own — it is the paragraph two of the scenarios
    turn on (*An ended session says so*, scoped to the two enhanced
    surfaces, and *A failure is visible on a submission the page does not
    enhance*, scoped to the create surface). The delta fixes it here
    rather than leaving the templates to decide, so that "un-boosting a
    form would shrink the guarantee with no test failing and nothing
    recording that it had shrunk". This is that test.

    Expected to **PASS** on its first run and recorded in the manifest as
    a regression guard: the set is already as the delta states it.
    """
    for surface in _ENHANCED_SURFACES:
        forms = _submitting_forms(surfaces[surface])
        assert forms, f"{surface} carries no submitting form"
        # SPECIFIED: the step list and the edit surface are enhanced.
        assert all(_is_enhanced(form) for form in forms), (
            f"a submission on {surface} is not enhanced. Where the delta's "
            "enhanced set really has changed, the requirement is amended "
            "rather than this expectation relaxed — that is what the clause "
            "exists to force"
        )

    # SPECIFIED: and the create surface is not.
    assert not any(
        _is_enhanced(form) for form in _submitting_forms(surfaces["the create surface"])
    ), "the create surface is enhanced, which the delta fixes as it not being"
