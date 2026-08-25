"""Driving adapter: the playbook steps management page (`playbook-admin`).

Server-rendered HTML end to end — Jinja templates, plain forms, HTMX as
progressive enhancement (`hx-boost`), vendored assets, no JSON anywhere.
Every write goes through the launch module's public authoring use cases;
no route touches a repository or the domain's coherence rules directly,
and a rejected write renders **every** fault the use case reported, with
the submitted values still in the form.

The sender-rights check is one FastAPI dependency (`_require_admin`),
not page logic: it reads the session cookie, asks the access module's
`verify_admin_session` (imported through that module's public surface),
and refuses everything else with the app's own 404 — the absence shape
`admin-session` requires, produced in one place so it cannot drift
per-route. The vendored static assets sit under the same guard: an
admin surface that does not reveal its own existence cannot leak it
through a stylesheet URL either.

Collaborators are module-level names referenced as bare globals — the
`clickup_webhook.py` pattern that lets tests substitute fakes with
`monkeypatch.setattr`: `steps` (the step-set store; in production a
wrapper opening its own session per operation), and `roster` /
`admin_sessions`, injected by `main.py` the way `slack_entry`'s catalog
registrar is, because this module may not import the access module's
infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import list_people, verify_admin_session
from commerce_ops.launch.application import (
    HANDLERS,
    StaleStepSetError,
    StepSetStore,
    change_step_status,
    create_step,
    reorder_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    Cadence,
    Hazard,
    InvalidPlaybookError,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Scope,
    StepKind,
    StepStatus,
    TimingAnchor,
    WindowAnchor,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.infrastructure.driven.database import session

__all__ = [
    "admin_sessions",
    "roster",
    "router",
    "steps",
    "verify_admin_session",
]

_STATUS_LABELS: Final = {
    StepStatus.DRAFT: "draft",
    StepStatus.IN_DEVELOPMENT: "in development",
    StepStatus.ACTIVE: "active",
    StepStatus.RETIRED: "retired",
}

# Hoisted to module scope so `_submitted_values` can name the same default
# the create template falls back to. Built as a key of `_option_context()`
# it was reachable only from a template.
_DISCIPLINE_OPTIONS: Final = tuple(d.value for d in Discipline)

# Creating never offers `retired`: retirement is the end of a step's life,
# reached through the retire flow that records who ended it. A step created
# straight into it would render behind the control that reveals retired
# steps, where the redirect's fragment addresses nothing and the
# falls-outside-the-narrowing notice cannot help.
_CREATE_STATUS_OPTIONS: Final = tuple(
    (status.value, label)
    for status, label in _STATUS_LABELS.items()
    if status is not StepStatus.RETIRED
)

router = APIRouter()

SESSION_COOKIE: Final = "admin_session"

PAGE_PATH: Final = "/admin/playbook"

_STATIC_DIR: Final = Path(__file__).parent / "static"

_TEMPLATES: Final = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(default=True, default_for_string=True),
)

STALE_NOTICE: Final = (
    "The step set changed underneath this write — nothing was saved. "
    "This page shows the set as it stands now; redo the change on it."
)

SEARCH_INERT_NOTICE: Final = (
    "Reordering is unavailable while a search is active. A search matches "
    "an incidental set of steps, so moving one past the next match can "
    "cross any number of steps the search is hiding. Clear the search to "
    "reorder."
)

NO_SLOT_NOTICE: Final = (
    "That move names a step that holds no position in its gate's order — "
    "only active steps do — so nothing was saved."
)

RETIRED_INERT_NOTICE: Final = (
    "Reordering is unavailable while retired steps are shown. A retired "
    "step holds no position in its gate's order, so it can neither be "
    "moved nor be the step another comes to rest after. Hide retired "
    "steps to reorder."
)


def _inert_notice(narrowing: _Narrowing) -> str:
    """Why reordering is unavailable in the view being rendered. The
    search is named first: it is the narrowing the admin chose, where the
    retired view is one they can simply leave."""
    return SEARCH_INERT_NOTICE if narrowing.q else RETIRED_INERT_NOTICE


@dataclass(frozen=True, slots=True)
class _Narrowing:
    """What the admin has narrowed the list to, read from one place and
    carried by every write, every link that leaves the list, and every
    move — so no route can forget a filter the way each once did.

    `reorderable` is the pair of views where a move cannot be given an
    honest meaning; see the `playbook-admin` spec's reorder requirement.
    """

    gate: str = ""
    discipline: str = ""
    q: str = ""
    retired: bool = False

    @property
    def reorderable(self) -> bool:
        return not self.q and not self.retired

    def _params(self, **overrides: Any) -> dict[str, str]:
        values = {
            "gate": self.gate,
            "discipline": self.discipline,
            "q": self.q,
            "retired": "1" if self.retired else "",
        }
        values.update({key: str(value) for key, value in overrides.items()})
        return {key: value for key, value in values.items() if value}

    def suffix(self, **overrides: Any) -> str:
        """`?gate=…&discipline=…`, or empty — appended to every action and
        every link, so the narrowing survives the round trip."""
        query = urlencode(self._params(**overrides))
        return f"?{query}" if query else ""

    def shows(self, record: Any) -> bool:
        definition = record.definition
        if _is_retired(record) and not self.retired:
            return False
        if self.gate and definition.gate != self.gate:
            return False
        if self.discipline and definition.discipline.value != self.discipline:
            return False
        if not self.q:
            return True
        # Both fields, since they became two: an author who remembers a
        # phrase does not remember which of the two they wrote it in.
        needle = self.q.lower()
        return (
            needle in definition.name.lower()
            or needle in (definition.description or "").lower()
        )


def _filters_of(request: Request) -> _Narrowing:
    """The one place the narrowing is read. Every route renders through
    it, which is what stops a write returning the unfiltered list."""
    params = request.query_params
    return _Narrowing(
        gate=params.get("gate", ""),
        discipline=params.get("discipline", ""),
        q=params.get("q", ""),
        retired=_truthy(params.get("retired")),
    )


class _RequestScopedSteps:
    """The production `StepSetStore`: each operation on its own session.

    The optimistic set-version makes split load/save safe — a save
    against a version another write moved past raises
    `StaleStepSetError`, which the page renders instead of retrying
    silently.
    """

    async def load(self) -> Any:
        async with session() as db:
            return await PlaybookRepository(db).load()

    async def save(self, records: Any, *, expected_version: int) -> None:
        async with session() as db:
            await PlaybookRepository(db).save(
                records, expected_version=expected_version
            )


steps: StepSetStore = _RequestScopedSteps()

# Injected by `main.py` after the app is built (the `register_catalog_product`
# pattern): the roster store and the access module's session store. Resolved
# at call time; absent injection refuses every request, which is the
# failing-closed direction.
roster: Any = None
admin_sessions: Any = None


async def _roster_people() -> tuple[Any, ...]:
    """Everyone the roster carries, however the collaborator is shaped.

    In production `roster` is the roster *store* the composition root
    injects, read through `access`'s public `list_people`; a test
    substitutes a reader answering `list_people()` directly. Both are
    accepted, because the seam is what the page needs of the roster and
    not which object happens to satisfy it."""
    if roster is None:
        return ()
    reader = getattr(roster, "list_people", None)
    if reader is not None:
        return tuple(await reader())
    return tuple(await list_people(roster=roster))


def _person_identifier(person: Any) -> str:
    for name in ("identifier", "id", "person_id"):
        value = getattr(person, name, None)
        if value is not None:
            return str(value)
    raise ValueError(f"a roster person exposes no identifier: {person!r}")


def _people_by_identifier(people: Sequence[Any]) -> dict[str, Any]:
    return {_person_identifier(person): person for person in people}


def _assignee_options(people: Sequence[Any]) -> list[tuple[str, str]]:
    """Who the form offers, by display name.

    Active people only: an author cannot name someone who does not exist,
    and offering a departed colleague would invite a write the rules
    refuse."""
    return [
        (_person_identifier(person), str(person.display_name))
        for person in people
        if getattr(person, "active", True)
    ]


async def _require_admin(request: Request) -> str:
    """The one guard every admin route rides. Refusal is the app's own
    404 — identical to an unregistered route, whatever actually failed."""
    session_id = request.cookies.get(SESSION_COOKIE)
    principal: str | None = None
    if session_id:
        principal = await verify_admin_session(
            roster,
            admin_sessions,
            session_id=session_id,
            now=datetime.now(UTC),
        )
    if principal is None:
        raise HTTPException(status_code=404)
    return principal


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

_ANCHOR_KINDS: Final = ("offset", "window", "open-ended", "recurring")


def _is_retired(record: Any) -> bool:
    return record.definition.status is StepStatus.RETIRED


def _is_active(record: Any) -> bool:
    """Whether the step holds a slot and is served.

    The one question the order, the reorder controls and the served set
    all ask — `draft`, `in-development` and `retired` alike answer no."""
    return record.definition.status is StepStatus.ACTIVE


def _anchor_form_values(anchor: TimingAnchor) -> dict[str, str]:
    if isinstance(anchor, OffsetAnchor):
        return {"kind": "offset", "days": str(anchor.days), "start": "", "end": ""}
    if isinstance(anchor, WindowAnchor):
        return {
            "kind": "window",
            "days": "",
            "start": str(anchor.start),
            "end": str(anchor.end),
        }
    if isinstance(anchor, OpenEndedAnchor):
        return {"kind": "open-ended", "days": "", "start": str(anchor.start), "end": ""}
    assert isinstance(anchor, RecurringAnchor)
    return {
        "kind": "recurring",
        "days": "",
        "start": "",
        "end": "",
        "cadence": anchor.cadence.value,
    }


def _anchor_from_form(form: dict[str, str]) -> TimingAnchor:
    kind = form.get("anchor_kind", "offset")
    try:
        if kind == "offset":
            return OffsetAnchor(days=int(form.get("anchor_days") or 0))
        if kind == "window":
            return WindowAnchor(
                start=int(form.get("anchor_start") or 0),
                end=int(form.get("anchor_end") or 0),
            )
        if kind == "open-ended":
            return OpenEndedAnchor(start=int(form.get("anchor_start") or 0))
        if kind == "recurring":
            return RecurringAnchor(
                cadence=Cadence(form.get("anchor_cadence") or Cadence.WEEKLY.value)
            )
    except ValueError as exc:
        raise InvalidPlaybookError([f"timing anchor: {exc}"]) from exc
    raise InvalidPlaybookError([f"timing anchor: unknown kind '{kind}'"])


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "on", "1", "yes"}


def _authorable_fields(
    form: dict[str, str], assignees: tuple[str, ...] = ()
) -> dict[str, Any]:
    """The authorable shape as one form submission carries it. Enum
    parsing faults are collected, not raised one at a time."""
    faults: list[str] = []
    fields: dict[str, Any] = {}

    def _enum(name: str, enum_type: Any, fallback: Any) -> Any:
        raw = form.get(name)
        if raw is None or raw == "":
            return fallback
        try:
            return enum_type(raw)
        except ValueError:
            faults.append(f"{name}: '{raw}' is not a recognised value")
            return fallback

    kind = _enum("kind", StepKind, StepKind.HUMAN)
    fields["name"] = form.get("name", "")
    # An empty box is *no description*, not an empty one: the field is
    # optional, and the projection writes no task body where a step
    # carries none.
    fields["description"] = (form.get("description") or "").strip() or None
    fields["gate"] = form.get("gate", "")
    fields["scope"] = _enum("scope", Scope, Scope.PRODUCT)
    fields["blocking"] = _truthy(form.get("blocking"))
    fields["kind"] = kind
    fields["needs_confirmation"] = _truthy(form.get("needs_confirmation"))
    fields["status"] = _enum("status", StepStatus, StepStatus.DRAFT)
    fields["hazard"] = _enum("hazard", Hazard, Hazard.NONE)
    fields["assignees"] = assignees
    # Submitted on a `human` step only because the control was left
    # enabled; carried through rather than dropped, so the write reports
    # the rule instead of the page quietly deciding for the author.
    fields["automation_brief"] = (form.get("automation_brief") or "").strip() or None
    fields["handler"] = (form.get("handler") or "").strip() or None
    fields["timing_anchor"] = _anchor_from_form(form)
    if faults:
        raise InvalidPlaybookError(faults)
    return fields


def _row(record: Any, people: Mapping[str, Any]) -> dict[str, Any]:
    definition = record.definition
    return {
        "identifier": definition.identifier,
        "name": definition.name,
        "description": definition.description or "",
        "discipline": definition.discipline.value,
        "gate": definition.gate,
        "blocking": definition.blocking,
        "kind": definition.kind.value,
        "needs_confirmation": definition.needs_confirmation,
        "status": definition.status.value,
        "status_label": _STATUS_LABELS[definition.status],
        # By display name, since an author knows colleagues by name and
        # not by generated identifier. An identifier the roster no longer
        # carries is shown as itself rather than dropped — an assignee
        # nobody can read is still an assignee the write rules see.
        "assignees": [
            getattr(people.get(identifier), "display_name", identifier)
            for identifier in definition.assignees
        ],
        "active": _is_active(record),
        "retired": _is_retired(record),
    }


def _option_context() -> dict[str, Any]:
    return {
        "page_path": PAGE_PATH,
        "gate_options": GATE_SEQUENCE,
        "discipline_options": list(_DISCIPLINE_OPTIONS),
        "scope_options": [s.value for s in Scope],
        "kind_options": [k.value for k in StepKind],
        "status_options": [
            (status.value, label) for status, label in _STATUS_LABELS.items()
        ],
        "hazard_options": [h.value for h in Hazard],
        "cadence_options": [c.value for c in Cadence],
        "anchor_kinds": _ANCHOR_KINDS,
    }


def _slot_key(record: Any) -> tuple[int, str]:
    """The served order of a gate's steps. Equal to
    `playbook_authoring._slot_of` paired with the same tiebreak, and it
    must stay equal: a `target_index` computed here means what the
    authoring write will do with it only while the two agree. Pinned by
    `test_the_pages_order_agrees_with_the_authoring_writes_order`."""
    return (int(getattr(record, "display_order", 0)), record.definition.identifier)


def _gate_live(records: tuple[Any, ...] | Any, gate: str) -> list[Any]:
    """`G` — a gate's **active** steps in served order.

    Only active steps hold a slot, so only they can be moved or be named
    as the step another comes to rest after. A draft sits in the same
    gate and outside this list, which is what lets the gate stay
    reorderable while somebody is drafting in it."""
    return sorted(
        (
            record
            for record in records
            if record.definition.gate == gate and _is_active(record)
        ),
        key=_slot_key,
    )


def _placement(
    live: list[Any], visible: list[Any], step_id: str, after: str
) -> int | None:
    """`target_index` for a move of `step_id` coming to rest after the
    visible step `after` — or, for an empty `after`, at the head of the
    visible list.

    Counted as `reorder_step` counts it: how many of the gate's live
    steps precede the moved step once it has been removed. Returns
    `None` when the move would leave the visible order as it already
    stands, which is no move at all — the test is on that order, not on
    whether a rule yields an index, because for a head move on an
    already-first step it yields a perfectly good one that would slide
    the step past the steps the filter hides.
    """
    remaining = [record for record in live if record.definition.identifier != step_id]
    if after:
        anchor = next(
            (
                at
                for at, record in enumerate(remaining)
                if record.definition.identifier == after
            ),
            None,
        )
        if anchor is None:
            return None
        target = anchor + 1
    else:
        head = next(
            (
                record.definition.identifier
                for record in visible
                if record.definition.identifier != step_id
            ),
            None,
        )
        if head is None:
            return None
        target = next(
            at
            for at, record in enumerate(remaining)
            if record.definition.identifier == head
        )

    moved = next(record for record in live if record.definition.identifier == step_id)
    after_move = remaining[:target] + [moved] + remaining[target:]
    shown = {record.definition.identifier for record in visible}
    before_order = [
        record.definition.identifier
        for record in live
        if record.definition.identifier in shown
    ]
    after_order = [
        record.definition.identifier
        for record in after_move
        if record.definition.identifier in shown
    ]
    return None if before_order == after_order else target


def _move_targets(visible_live: list[Any], at: int) -> tuple[str | None, str | None]:
    """What a step's two reorder controls name, in the one vocabulary the
    rule speaks: the visible step to come to rest after. Down names the
    step below; up names the step two above, or the head of the visible
    list. `None` is an end of the list, where the control is inert.

    The head is spelled `""` — named, but naming nothing to sit after.
    """
    down = (
        visible_live[at + 1].definition.identifier
        if at + 1 < len(visible_live)
        else None
    )
    if at == 0:
        up: str | None = None
    elif at == 1:
        up = ""
    else:
        up = visible_live[at - 2].definition.identifier
    return up, down


def _created_outside(
    records: tuple[Any, ...] | Any, narrowing: _Narrowing, created: str
) -> Any | None:
    """The just-created step, when the narrowing hides it and clearing the
    narrowing would bring it back — otherwise `None`, and no notice.

    The test is what *this page's read* returns, never "the served set":
    the served set is the active steps alone, and a step created as a
    draft is outside it while being exactly the step the notice exists to
    find. The offer clears the gate, discipline and search but not the
    retired control, so a step retired since it was created is correctly
    left alone: clearing what the offer clears would still not reveal it,
    and an offer the admin cannot act on is worse than saying nothing.
    """
    record = next(
        (r for r in records if r.definition.identifier == created),
        None,
    )
    if record is None or narrowing.shows(record):
        return None
    cleared = _Narrowing(retired=narrowing.retired)
    return record if cleared.shows(record) else None


async def _render_page(
    narrowing: _Narrowing,
    *,
    notice: str | None = None,
    faults: tuple[str, ...] = (),
    created: str = "",
) -> HTMLResponse:
    records, version = await steps.load()
    people = _people_by_identifier(await _roster_people())
    outside = _created_outside(records, narrowing, created) if created else None

    gates = []
    for gate in GATE_SEQUENCE:
        live = _gate_live(records, gate)
        # The position is read against the whole gate, before the
        # narrowing, so a move that crosses hidden steps is legible.
        position_of = {
            record.definition.identifier: at for at, record in enumerate(live, start=1)
        }
        shown = sorted(
            (
                record
                for record in records
                if record.definition.gate == gate and narrowing.shows(record)
            ),
            key=_slot_key,
        )
        # Only active steps stand in the orderable list; a draft or an
        # `in-development` step renders outside it, holding no position
        # and offering no control that would name it as a resting place.
        visible_live = [record for record in shown if _is_active(record)]
        rows = []
        pending = []
        for record in shown:
            row = _row(record, people)
            row["live_count"] = len(live)
            row["up"] = row["down"] = None
            if not _is_active(record):
                # Rendered outside the gate's orderable list rather than
                # among it: a step that holds no slot must render no
                # position among the gate's active steps, and no control
                # that would let a move name it as a resting place.
                row["position"] = None
                pending.append(row)
                continue
            row["position"] = position_of.get(record.definition.identifier)
            if narrowing.reorderable:
                row["up"], row["down"] = _move_targets(
                    visible_live, visible_live.index(record)
                )
            rows.append(row)
        gates.append({"identifier": gate, "steps": rows, "pending": pending})

    html = _TEMPLATES.get_template("page.html").render(
        gates=gates,
        narrowing=narrowing,
        version=version,
        reorderable=narrowing.reorderable,
        inert_reason=None if narrowing.reorderable else _inert_notice(narrowing),
        clear_search=narrowing.suffix(q=""),
        hide_retired=narrowing.suffix(retired=""),
        show_retired_link=narrowing.suffix(retired="1"),
        notice=notice,
        faults=faults,
        created=created,
        # Named, so the notice can say which step it means; and the offer
        # keeps carrying `created` plus the fragment, so clearing lands on
        # the step rather than at the top of the whole set.
        created_outside=(
            {
                "identifier": outside.definition.identifier,
                "name": outside.definition.name,
                # Not `clear`: Jinja resolves `mapping.clear` to `dict.clear`,
                # the built-in method, and renders it into the href.
                "clear_url": narrowing.suffix(
                    gate="", discipline="", q="", created=created
                ),
            }
            if outside is not None
            else None
        ),
        assignee_options=_assignee_options(list(people.values())),
        **_option_context(),
    )
    return HTMLResponse(html)


async def _render_new(
    values: dict[str, Any],
    *,
    faults: tuple[str, ...] = (),
    notice: str | None = None,
    narrowing: _Narrowing,
) -> HTMLResponse:
    """The create surface, on its own page. A rejection re-renders *this*,
    not the list — which is what keeps every submitted value, the
    discipline and the named assignees included."""
    context = _option_context()
    context["status_options"] = list(_CREATE_STATUS_OPTIONS)
    html = _TEMPLATES.get_template("new.html").render(
        values=values,
        faults=faults,
        notice=notice,
        narrowing=narrowing,
        assignee_options=_assignee_options(await _roster_people()),
        **context,
    )
    return HTMLResponse(html)


async def _render_edit(
    step_id: str,
    discipline: str,
    values: dict[str, Any],
    *,
    faults: tuple[str, ...] = (),
    notice: str | None = None,
    narrowing: _Narrowing,
) -> HTMLResponse:
    html = _TEMPLATES.get_template("edit.html").render(
        step_id=step_id,
        discipline=discipline,
        values=values,
        faults=faults,
        notice=notice,
        narrowing=narrowing,
        assignee_options=_assignee_options(await _roster_people()),
        **_option_context(),
    )
    return HTMLResponse(html)


def _edit_values(record: Any) -> dict[str, Any]:
    definition = record.definition
    anchor = _anchor_form_values(definition.timing_anchor)
    return {
        "name": definition.name,
        "description": definition.description or "",
        "gate": definition.gate,
        "scope": definition.scope.value,
        "blocking": "true" if definition.blocking else "false",
        "kind": definition.kind.value,
        "needs_confirmation": ("true" if definition.needs_confirmation else "false"),
        "status": definition.status.value,
        "hazard": definition.hazard.value,
        "assignees": list(definition.assignees),
        "automation_brief": definition.automation_brief or "",
        "handler": definition.handler or "",
        "anchor_kind": anchor["kind"],
        "anchor_days": anchor["days"],
        "anchor_start": anchor["start"],
        "anchor_end": anchor["end"],
        "anchor_cadence": anchor.get("cadence", ""),
    }


def _submitted_values(
    form: dict[str, str], assignees: tuple[str, ...] = ()
) -> dict[str, Any]:
    """The submitted form, echoed back around a rejection: the spec
    requires the form to still hold what was typed.

    `discipline` is here for the create surface alone — editing renders it
    as text, because authoring refuses to update it. Without the key a
    rejected create reverted to the first option, and the corrected retry
    generated an identifier carrying the wrong discipline, which
    `update_step` will not correct: retire-and-succeed was the only way
    back. The default is the same one the template falls back to, never
    `""`, which matches no option and leaves the browser showing the first
    one anyway.
    """
    return {
        "discipline": form.get("discipline") or _DISCIPLINE_OPTIONS[0],
        "name": form.get("name", ""),
        "description": form.get("description", ""),
        "gate": form.get("gate", ""),
        "scope": form.get("scope", ""),
        "blocking": form.get("blocking", "false"),
        "kind": form.get("kind", ""),
        "needs_confirmation": form.get("needs_confirmation", "false"),
        "status": form.get("status", ""),
        "hazard": form.get("hazard", ""),
        "assignees": list(assignees),
        "automation_brief": form.get("automation_brief", ""),
        "handler": form.get("handler", ""),
        "anchor_kind": form.get("anchor_kind", "offset"),
        "anchor_days": form.get("anchor_days", ""),
        "anchor_start": form.get("anchor_start", ""),
        "anchor_end": form.get("anchor_end", ""),
        "anchor_cadence": form.get("anchor_cadence", ""),
    }


async def _find_record(step_id: str) -> Any:
    records, _version = await steps.load()
    for record in records:
        if record.definition.identifier == step_id:
            return record
    raise HTTPException(status_code=404)


async def _form_of(request: Request) -> tuple[dict[str, str], tuple[str, ...]]:
    """The submitted form, plus its assignees read as the many values
    they are — a single-valued mapping would keep only the last person a
    step names."""
    posted = await request.form()
    fields = {key: str(value) for key, value in posted.items()}
    assignees = tuple(str(value) for value in posted.getlist("assignees") if str(value))
    return fields, assignees


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get(PAGE_PATH)
async def step_table(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    # `created` is what a fragment cannot be: server-visible. A redirect to
    # `…#step-<id>` tells the browser where to scroll and tells this route
    # nothing, so without the parameter the list could not know a create
    # had happened, let alone that the narrowing hides it.
    return await _render_page(
        _filters_of(request), created=request.query_params.get("created", "")
    )


@router.get(PAGE_PATH + "/steps/new")
async def new_form(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    """Creating on its own surface, reachable from the list without
    traversing the step set — the whole point of the change. Buried at the
    bottom of the list it sat below twenty screens of steps, and an admin
    opening the page concluded there was no way to add one."""
    return await _render_new(
        {"discipline": _DISCIPLINE_OPTIONS[0]}, narrowing=_filters_of(request)
    )


@router.get(PAGE_PATH + "/steps/{step_id}/edit")
async def edit_form(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    record = await _find_record(step_id)
    return await _render_edit(
        step_id,
        record.definition.discipline.value,
        _edit_values(record),
        narrowing=_filters_of(request),
    )


@router.post(PAGE_PATH + "/steps/{step_id}/edit")
async def save_edit(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    form, assignees = await _form_of(request)
    record = await _find_record(step_id)
    discipline = record.definition.discipline.value
    try:
        fields = _authorable_fields(form, assignees)
        await update_step(
            steps=steps,
            principal=principal,
            step_id=step_id,
            roster=roster,
            handlers=HANDLERS,
            **fields,
        )
    except InvalidPlaybookError as rejected:
        return await _render_edit(
            step_id,
            discipline,
            _submitted_values(form, assignees),
            faults=rejected.faults,
            narrowing=narrowing,
        )
    except StaleStepSetError:
        return await _render_edit(
            step_id,
            discipline,
            _submitted_values(form, assignees),
            notice=STALE_NOTICE,
            narrowing=narrowing,
        )
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/create")
async def create(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    form, assignees = await _form_of(request)

    # Two submissions the create surface cannot have produced: its select
    # always submits a discipline, and it never offers `retired`. Neither
    # is a rejection with a half-typed form behind it, so neither renders
    # one — the reordering requirement sets the same pattern, refusing a
    # move submitted where the control was absent rather than trusting the
    # control's absence.
    submitted_discipline = form.get("discipline") or ""
    if not submitted_discipline:
        raise HTTPException(status_code=400, detail="discipline is required")
    if form.get("status") == StepStatus.RETIRED.value:
        raise HTTPException(status_code=400, detail="a step cannot be created retired")

    try:
        fields = _authorable_fields(form, assignees)
        discipline = Discipline(submitted_discipline)
        record = await create_step(
            steps=steps,
            principal=principal,
            discipline=discipline,
            roster=roster,
            handlers=HANDLERS,
            **fields,
        )
    except (InvalidPlaybookError, ValueError) as rejected:
        faults = getattr(rejected, "faults", (str(rejected),))
        return await _render_new(
            _submitted_values(form, assignees),
            faults=tuple(faults),
            narrowing=narrowing,
        )
    except StaleStepSetError:
        return await _render_new(
            _submitted_values(form, assignees),
            notice=STALE_NOTICE,
            narrowing=narrowing,
        )

    # Alone among the writes, a create lands the admin on a *different*
    # page from the one they posted to, so rendering the list here would
    # leave the URL on the create path with a resubmit on refresh. The
    # fragment addresses the created step wherever it renders — among its
    # gate's active steps when created active, among the non-active steps
    # otherwise.
    identifier = record.definition.identifier
    return RedirectResponse(
        f"{PAGE_PATH}{narrowing.suffix(created=identifier)}#step-{identifier}",
        status_code=303,
    )


@router.post(PAGE_PATH + "/steps/{step_id}/retire")
async def retire(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    try:
        await retire_step(
            steps=steps,
            principal=principal,
            step_id=step_id,
            roster=roster,
            handlers=HANDLERS,
        )
    except InvalidPlaybookError as rejected:
        return await _render_page(narrowing, faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/{step_id}/unretire")
async def unretire(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    try:
        await unretire_step(
            steps=steps,
            principal=principal,
            step_id=step_id,
            roster=roster,
            handlers=HANDLERS,
        )
    except InvalidPlaybookError as rejected:
        return await _render_page(narrowing, faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/{step_id}/status")
async def change_status(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    """Move a step to the status the form names.

    The refusal is rendered with the write's **own** explanation, never a
    generic one: what the step lacks is the only actionable part of it.
    Crossing `retired` is the retirement or un-retirement write itself —
    resolved by the authoring use case, not here, so this control cannot
    become a second way out of `retired` that records nobody.
    """
    narrowing = _filters_of(request)
    form, _assignees = await _form_of(request)
    try:
        status = StepStatus(form.get("status", ""))
    except ValueError:
        return await _render_page(
            narrowing,
            faults=(f"status: '{form.get('status', '')}' is not a recognised value",),
        )
    try:
        await change_step_status(
            steps=steps,
            principal=principal,
            step_id=step_id,
            status=status,
            roster=roster,
            handlers=HANDLERS,
        )
    except InvalidPlaybookError as rejected:
        return await _render_page(narrowing, faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
    except ValueError as rejected:
        return await _render_page(narrowing, faults=(str(rejected),))
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/{step_id}/move")
async def move(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    """Move `step_id` to come to rest after the visible step the form
    names — or, for an empty `after`, at the head of the visible list.

    The position is computed here, never submitted: the form names a
    neighbour and the version the page it was made on was rendered from,
    and this route derives the index from the set it reads. The version
    is checked *before* the position is computed, so a move made on a
    list a later write superseded is refused rather than recomputed
    against a set the admin never saw — and the same version is then
    pinned into the write, so the position reaches only the set it was
    computed against.
    """
    narrowing = _filters_of(request)
    if not narrowing.reorderable:
        return await _render_page(narrowing, notice=_inert_notice(narrowing))

    form, _assignees = await _form_of(request)
    records, version = await steps.load()
    if form.get("version", "") != str(version):
        return await _render_page(narrowing, notice=STALE_NOTICE)

    target = next(
        (record for record in records if record.definition.identifier == step_id),
        None,
    )
    # A step that is not `active` holds no slot, so a move naming one
    # cannot be given an honest meaning — refused here and not merely
    # left uncontrolled, so the rule does not rest on the rendered
    # controls alone.
    if target is None or not _is_active(target):
        return await _render_page(narrowing, notice=NO_SLOT_NOTICE)

    live = _gate_live(records, target.definition.gate)
    visible = [record for record in live if narrowing.shows(record)]
    after = form.get("after", "")
    if after and all(record.definition.identifier != after for record in visible):
        return await _render_page(narrowing, notice=STALE_NOTICE)

    target_index = _placement(live, visible, step_id, after)
    if target_index is None:
        return await _render_page(narrowing)

    try:
        await reorder_step(
            steps=steps,
            principal=principal,
            step_id=step_id,
            target_index=target_index,
            expected_version=version,
        )
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
    except (InvalidPlaybookError, ValueError) as rejected:
        faults = getattr(rejected, "faults", (str(rejected),))
        return await _render_page(narrowing, faults=tuple(faults))
    return await _render_page(narrowing)


@router.get("/admin/static/{asset}")
async def static_asset(
    asset: str, principal: str = Depends(_require_admin)
) -> Response:
    path = (_STATIC_DIR / asset).resolve()
    if path.parent != _STATIC_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)
