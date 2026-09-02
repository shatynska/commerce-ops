"""Driving adapter: the members admin page (`members-admin`).

Server-rendered HTML end to end — a Jinja template and plain forms, the
shape `playbook_admin` established, so the two admin surfaces read the
same way and neither needs JavaScript to work.

Every route rides the same admin-session guard as the playbook page, and
refusal is the app's own 404: an unauthenticated caller cannot tell the
surface exists. Writes go through the `members` capability's use cases —
this module never touches the store directly — so the last-admin refusal
and every identity rule are enforced in one place and merely *rendered*
here.

`members` and `admin_sessions` are injected by `main.py` after the app is
built (the pattern `playbook_admin` uses); absent injection refuses every
request, which is the failing-closed direction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import (
    InvalidMembersError,
    StaleMembersError,
    create_member,
    deactivate_member,
    reactivate_member,
    update_member,
    verify_admin_session,
)
from commerce_ops.shared.infrastructure.driving.admin_assets import TEMPLATES_DIR

__all__ = [
    "PAGE_PATH",
    "admin_sessions",
    "members",
    "router",
]

PAGE_PATH: Final = "/admin/team"

SESSION_COOKIE: Final = "admin_session"

# Own templates first, then the shared ones: the admin header is one
# partial both surfaces include, so neither module owns a copy of it.
_TEMPLATES: Final = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(Path(__file__).parent / "templates"),
            FileSystemLoader(TEMPLATES_DIR),
        ]
    ),
    autoescape=select_autoescape(default=True, default_for_string=True),
)

STALE_NOTICE: Final = (
    "The membership changed underneath this write — nothing was saved. This "
    "page shows the membership as it stands now; redo the change on it."
)

router = APIRouter()

# Injected by `main.py` after the app is built. Resolved at call time.
members: Any = None
admin_sessions: Any = None


async def _require_admin(request: Request) -> str:
    """The one guard every membership route rides. Refusal is the app's own
    404 — identical to an unregistered route, whatever actually failed."""
    session_id = request.cookies.get(SESSION_COOKIE)
    principal: str | None = None
    if session_id:
        principal = await verify_admin_session(
            members,
            admin_sessions,
            session_id=session_id,
            now=datetime.now(UTC),
        )
    if principal is None:
        raise HTTPException(status_code=404)
    return principal


def _faults_of(error: Exception) -> tuple[str, ...]:
    carried = getattr(error, "faults", None)
    if carried:
        return tuple(str(fault) for fault in carried)
    return (str(error),)


async def _render(
    *,
    faults: tuple[str, ...] = (),
    notice: str | None = None,
    submitted: dict[str, str] | None = None,
) -> str:
    """The page as it stands now, plus whatever the last write reported.

    The membership is re-read rather than patched from the write's result, so
    a rejected write renders exactly what is stored — which is what makes
    "the membership is unchanged" visible rather than merely claimed.
    """
    records, _ = await members.load()
    active = [record for record in records if record.member.active]
    deactivated = [record for record in records if not record.member.active]
    template = _TEMPLATES.get_template("team.html")
    return template.render(
        page_path=PAGE_PATH,
        active=active,
        deactivated=deactivated,
        faults=faults,
        notice=notice,
        submitted=submitted or {},
    )


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}


async def _form(request: Request) -> dict[str, str]:
    posted = await request.form()
    return {key: str(value) for key, value in posted.items()}


@router.get(PAGE_PATH, response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render())


@router.post(PAGE_PATH + "/members", response_class=HTMLResponse)
async def create(request: Request) -> Any:
    principal = await _require_admin(request)
    form = await _form(request)
    try:
        await create_member(
            members=members,
            principal=principal,
            display_name=form.get("display_name", ""),
            slack_identity=form.get("slack_identity", ""),
            clickup_user_id=(form.get("clickup_user_id") or "").strip() or None,
            admin=_truthy(form.get("admin")),
        )
    except InvalidMembersError as rejected:
        # The submitted values ride back with the faults: an admin who
        # mistyped one field should not have to retype the others.
        return HTMLResponse(await _render(faults=_faults_of(rejected), submitted=form))
    except StaleMembersError:
        return HTMLResponse(await _render(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)


@router.post(PAGE_PATH + "/{member_id}/edit", response_class=HTMLResponse)
async def edit(member_id: str, request: Request) -> Any:
    principal = await _require_admin(request)
    form = await _form(request)
    try:
        await update_member(
            members=members,
            principal=principal,
            member_id=member_id,
            display_name=form.get("display_name", ""),
            clickup_user_id=(form.get("clickup_user_id") or "").strip() or None,
            admin=_truthy(form.get("admin")),
        )
    except InvalidMembersError as rejected:
        return HTMLResponse(await _render(faults=_faults_of(rejected), submitted=form))
    except StaleMembersError:
        return HTMLResponse(await _render(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)


@router.post(PAGE_PATH + "/{member_id}/deactivate", response_class=HTMLResponse)
async def deactivate(member_id: str, request: Request) -> Any:
    principal = await _require_admin(request)
    try:
        await deactivate_member(
            members=members, principal=principal, member_id=member_id
        )
    except InvalidMembersError as refused:
        # The last-admin refusal lands here, and its own explanation is
        # what the page shows — never a paraphrase of it.
        return HTMLResponse(await _render(faults=_faults_of(refused)))
    except StaleMembersError:
        return HTMLResponse(await _render(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)


@router.post(PAGE_PATH + "/{member_id}/reactivate", response_class=HTMLResponse)
async def reactivate(member_id: str, request: Request) -> Any:
    principal = await _require_admin(request)
    try:
        await reactivate_member(
            members=members, principal=principal, member_id=member_id
        )
    except InvalidMembersError as refused:
        return HTMLResponse(await _render(faults=_faults_of(refused)))
    except StaleMembersError:
        return HTMLResponse(await _render(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)
