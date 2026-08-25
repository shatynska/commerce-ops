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
wrapper opening its own session per operation), and `directory` /
`admin_sessions`, injected by `main.py` the way `slack_entry`'s catalog
registrar is, because this module may not import the access module's
infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import verify_admin_session
from commerce_ops.launch.application import (
    StaleStepSetError,
    StepSetStore,
    create_step,
    reorder_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    Binding,
    Cadence,
    ExecutionMode,
    Hazard,
    InvalidPlaybookError,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Scope,
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
    "directory",
    "router",
    "steps",
    "verify_admin_session",
]

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
        return not self.q or self.q.lower() in definition.description.lower()


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
# pattern): the loaded principals directory and the access module's session
# store. Resolved at call time; absent injection refuses every request,
# which is the failing-closed direction.
directory: Any = None
admin_sessions: Any = None


async def _require_admin(request: Request) -> str:
    """The one guard every admin route rides. Refusal is the app's own
    404 — identical to an unregistered route, whatever actually failed."""
    session_id = request.cookies.get(SESSION_COOKIE)
    principal: str | None = None
    if session_id:
        principal = await verify_admin_session(
            directory,
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
    return record.retired_by is not None and record.unretired_by is None


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


def _authorable_fields(form: dict[str, str]) -> dict[str, Any]:
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

    fields["description"] = form.get("description", "")
    fields["gate"] = form.get("gate", "")
    fields["scope"] = _enum("scope", Scope, Scope.PRODUCT)
    fields["binding"] = _enum("binding", Binding, Binding.FRAMEWORK)
    fields["blocking"] = _truthy(form.get("blocking"))
    fields["execution"] = _enum(
        "execution", ExecutionMode, ExecutionMode.HUMAN_ATTESTED
    )
    fields["hazard"] = _enum("hazard", Hazard, Hazard.NONE)
    fields["rule_policy"] = (form.get("rule_policy") or "").strip() or None
    fields["timing_anchor"] = _anchor_from_form(form)
    if faults:
        raise InvalidPlaybookError(faults)
    return fields


def _row(record: Any) -> dict[str, Any]:
    definition = record.definition
    return {
        "identifier": definition.identifier,
        "description": definition.description,
        "discipline": definition.discipline.value,
        "gate": definition.gate,
        "blocking": definition.blocking,
        "binding": definition.binding.value,
        "execution": definition.execution.value,
        "retired": _is_retired(record),
    }


def _option_context() -> dict[str, Any]:
    return {
        "page_path": PAGE_PATH,
        "gate_options": GATE_SEQUENCE,
        "discipline_options": [d.value for d in Discipline],
        "scope_options": [s.value for s in Scope],
        "binding_options": [b.value for b in Binding],
        "execution_options": [e.value for e in ExecutionMode],
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
    """`G` — a gate's live steps in served order."""
    return sorted(
        (
            record
            for record in records
            if record.definition.gate == gate and not _is_retired(record)
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


async def _render_page(
    narrowing: _Narrowing,
    *,
    notice: str | None = None,
    faults: tuple[str, ...] = (),
) -> HTMLResponse:
    records, version = await steps.load()

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
        visible_live = [record for record in shown if not _is_retired(record)]
        rows = []
        for record in shown:
            row = _row(record)
            row["position"] = position_of.get(record.definition.identifier)
            row["live_count"] = len(live)
            row["up"] = row["down"] = None
            if narrowing.reorderable and not _is_retired(record):
                row["up"], row["down"] = _move_targets(
                    visible_live, visible_live.index(record)
                )
            rows.append(row)
        gates.append({"identifier": gate, "steps": rows})

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
        **_option_context(),
    )
    return HTMLResponse(html)


def _render_edit(
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
        **_option_context(),
    )
    return HTMLResponse(html)


def _edit_values(record: Any) -> dict[str, Any]:
    definition = record.definition
    anchor = _anchor_form_values(definition.timing_anchor)
    return {
        "description": definition.description,
        "gate": definition.gate,
        "scope": definition.scope.value,
        "binding": definition.binding.value,
        "blocking": "true" if definition.blocking else "false",
        "execution": definition.execution.value,
        "hazard": definition.hazard.value,
        "rule_policy": definition.rule_policy or "",
        "anchor_kind": anchor["kind"],
        "anchor_days": anchor["days"],
        "anchor_start": anchor["start"],
        "anchor_end": anchor["end"],
        "anchor_cadence": anchor.get("cadence", ""),
    }


def _submitted_values(form: dict[str, str]) -> dict[str, Any]:
    """The submitted form, echoed back around a rejection: the spec
    requires the form to still hold what was typed."""
    return {
        "description": form.get("description", ""),
        "gate": form.get("gate", ""),
        "scope": form.get("scope", ""),
        "binding": form.get("binding", ""),
        "blocking": form.get("blocking", "false"),
        "execution": form.get("execution", ""),
        "hazard": form.get("hazard", ""),
        "rule_policy": form.get("rule_policy", ""),
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


async def _form_of(request: Request) -> dict[str, str]:
    posted = await request.form()
    return {key: str(value) for key, value in posted.items()}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get(PAGE_PATH)
async def step_table(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    return await _render_page(_filters_of(request))


@router.get(PAGE_PATH + "/steps/{step_id}/edit")
async def edit_form(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    record = await _find_record(step_id)
    return _render_edit(
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
    form = await _form_of(request)
    record = await _find_record(step_id)
    discipline = record.definition.discipline.value
    try:
        fields = _authorable_fields(form)
        await update_step(steps=steps, principal=principal, step_id=step_id, **fields)
    except InvalidPlaybookError as rejected:
        return _render_edit(
            step_id,
            discipline,
            _submitted_values(form),
            faults=rejected.faults,
            narrowing=narrowing,
        )
    except StaleStepSetError:
        return _render_edit(
            step_id,
            discipline,
            _submitted_values(form),
            notice=STALE_NOTICE,
            narrowing=narrowing,
        )
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/create")
async def create(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    form = await _form_of(request)
    try:
        fields = _authorable_fields(form)
        discipline = Discipline(form.get("discipline") or Discipline.LISTING.value)
        await create_step(
            steps=steps, principal=principal, discipline=discipline, **fields
        )
    except (InvalidPlaybookError, ValueError) as rejected:
        faults = getattr(rejected, "faults", (str(rejected),))
        return await _render_page(narrowing, faults=tuple(faults))
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
    return await _render_page(narrowing)


@router.post(PAGE_PATH + "/steps/{step_id}/retire")
async def retire(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    narrowing = _filters_of(request)
    try:
        await retire_step(steps=steps, principal=principal, step_id=step_id)
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
        await unretire_step(steps=steps, principal=principal, step_id=step_id)
    except InvalidPlaybookError as rejected:
        return await _render_page(narrowing, faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(narrowing, notice=STALE_NOTICE)
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

    form = await _form_of(request)
    records, version = await steps.load()
    if form.get("version", "") != str(version):
        return await _render_page(narrowing, notice=STALE_NOTICE)

    target = next(
        (record for record in records if record.definition.identifier == step_id),
        None,
    )
    if target is None or _is_retired(target):
        return await _render_page(narrowing, notice=STALE_NOTICE)

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
