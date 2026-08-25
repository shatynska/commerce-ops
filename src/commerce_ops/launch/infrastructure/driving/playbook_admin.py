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

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

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
    "roster",
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


async def _render_page(
    *,
    gate_filter: str = "",
    discipline_filter: str = "",
    q: str = "",
    show_retired: bool = False,
    notice: str | None = None,
    faults: tuple[str, ...] = (),
) -> HTMLResponse:
    records, _version = await steps.load()

    def _visible(record: Any) -> bool:
        definition = record.definition
        if _is_retired(record) and not show_retired:
            return False
        if gate_filter and definition.gate != gate_filter:
            return False
        if discipline_filter and definition.discipline.value != discipline_filter:
            return False
        return not q or q.lower() in definition.description.lower()

    by_gate: dict[str, list[Any]] = {gate: [] for gate in GATE_SEQUENCE}
    for record in records:
        if _visible(record) and record.definition.gate in by_gate:
            by_gate[record.definition.gate].append(record)
    gates = []
    for gate in GATE_SEQUENCE:
        ordered = sorted(
            by_gate[gate],
            key=lambda record: (
                getattr(record, "display_order", 0),
                record.definition.identifier,
            ),
        )
        gates.append({"identifier": gate, "steps": [_row(r) for r in ordered]})

    html = _TEMPLATES.get_template("page.html").render(
        gates=gates,
        gate_filter=gate_filter,
        discipline_filter=discipline_filter,
        q=q,
        show_retired=show_retired,
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
) -> HTMLResponse:
    html = _TEMPLATES.get_template("edit.html").render(
        step_id=step_id,
        discipline=discipline,
        values=values,
        faults=faults,
        notice=notice,
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
    params = request.query_params
    return await _render_page(
        gate_filter=params.get("gate", ""),
        discipline_filter=params.get("discipline", ""),
        q=params.get("q", ""),
        show_retired=_truthy(params.get("retired")),
    )


@router.get(PAGE_PATH + "/steps/{step_id}/edit")
async def edit_form(step_id: str, principal: str = Depends(_require_admin)) -> Response:
    record = await _find_record(step_id)
    return _render_edit(
        step_id, record.definition.discipline.value, _edit_values(record)
    )


@router.post(PAGE_PATH + "/steps/{step_id}/edit")
async def save_edit(
    step_id: str, request: Request, principal: str = Depends(_require_admin)
) -> Response:
    form = await _form_of(request)
    record = await _find_record(step_id)
    discipline = record.definition.discipline.value
    try:
        fields = _authorable_fields(form)
        await update_step(steps=steps, principal=principal, step_id=step_id, **fields)
    except InvalidPlaybookError as rejected:
        return _render_edit(
            step_id, discipline, _submitted_values(form), faults=rejected.faults
        )
    except StaleStepSetError:
        return _render_edit(
            step_id, discipline, _submitted_values(form), notice=STALE_NOTICE
        )
    return await _render_page()


@router.post(PAGE_PATH + "/steps/create")
async def create(
    request: Request, principal: str = Depends(_require_admin)
) -> Response:
    form = await _form_of(request)
    try:
        fields = _authorable_fields(form)
        discipline = Discipline(form.get("discipline") or Discipline.LISTING.value)
        await create_step(
            steps=steps, principal=principal, discipline=discipline, **fields
        )
    except (InvalidPlaybookError, ValueError) as rejected:
        faults = getattr(rejected, "faults", (str(rejected),))
        return await _render_page(faults=tuple(faults))
    except StaleStepSetError:
        return await _render_page(notice=STALE_NOTICE)
    return await _render_page()


@router.post(PAGE_PATH + "/steps/{step_id}/retire")
async def retire(step_id: str, principal: str = Depends(_require_admin)) -> Response:
    try:
        await retire_step(steps=steps, principal=principal, step_id=step_id)
    except InvalidPlaybookError as rejected:
        return await _render_page(faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(notice=STALE_NOTICE)
    return await _render_page()


@router.post(PAGE_PATH + "/steps/{step_id}/unretire")
async def unretire(step_id: str, principal: str = Depends(_require_admin)) -> Response:
    try:
        await unretire_step(steps=steps, principal=principal, step_id=step_id)
    except InvalidPlaybookError as rejected:
        return await _render_page(show_retired=True, faults=rejected.faults)
    except StaleStepSetError:
        return await _render_page(show_retired=True, notice=STALE_NOTICE)
    return await _render_page(show_retired=True)


async def _move(step_id: str, principal: str, *, offset: int) -> Response:
    records, _version = await steps.load()
    target = None
    for record in records:
        if record.definition.identifier == step_id:
            target = record
            break
    if target is None or _is_retired(target):
        raise HTTPException(status_code=404)
    gate = target.definition.gate
    ordered = sorted(
        (
            record
            for record in records
            if record.definition.gate == gate and not _is_retired(record)
        ),
        key=lambda record: (
            getattr(record, "display_order", 0),
            record.definition.identifier,
        ),
    )
    index = next(
        at
        for at, record in enumerate(ordered)
        if record.definition.identifier == step_id
    )
    target_index = min(max(index + offset, 0), len(ordered) - 1)
    try:
        await reorder_step(
            steps=steps,
            principal=principal,
            step_id=step_id,
            target_index=target_index,
        )
    except StaleStepSetError:
        return await _render_page(notice=STALE_NOTICE)
    except (InvalidPlaybookError, ValueError) as rejected:
        faults = getattr(rejected, "faults", (str(rejected),))
        return await _render_page(faults=tuple(faults))
    return await _render_page()


@router.post(PAGE_PATH + "/steps/{step_id}/up")
async def move_up(step_id: str, principal: str = Depends(_require_admin)) -> Response:
    return await _move(step_id, principal, offset=-1)


@router.post(PAGE_PATH + "/steps/{step_id}/down")
async def move_down(step_id: str, principal: str = Depends(_require_admin)) -> Response:
    return await _move(step_id, principal, offset=1)


@router.get("/admin/static/{asset}")
async def static_asset(
    asset: str, principal: str = Depends(_require_admin)
) -> Response:
    path = (_STATIC_DIR / asset).resolve()
    if path.parent != _STATIC_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)
