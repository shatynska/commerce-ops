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
    InvalidRolesError,
    StaleMembersError,
    create_member,
    deactivate_member,
    list_role_records,
    reactivate_member,
    remove_role_holder,
    update_member,
    verify_admin_session,
)
from commerce_ops.shared.infrastructure.driving.admin_assets import TEMPLATES_DIR

__all__ = [
    "PAGE_PATH",
    "admin_sessions",
    "members",
    "roles",
    "router",
]

PAGE_PATH: Final = "/admin/team"

ROLES_PATH: Final = "/admin/roles"
"""The roles surface, as a literal. `members_admin` and `roles_admin` are two
adapters of one module, but writing the import would make each page's path a
thing the other module could move; the shared header already writes both as
literals for the same reason."""

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
# The role collection, so a deactivation blocked by an active role's default
# can be refused with that refusal's own explanation. Optional: absent, the
# membership's own refusals are unaffected.
roles: Any = None


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
) -> str:
    """The Team list as it stands now, plus whatever the last write reported.

    The membership is re-read rather than patched from the write's result, so a
    rejected write renders exactly what is stored — which is what makes "the
    membership is unchanged" visible rather than merely claimed.
    """
    records, _ = await members.load()
    active = [record for record in records if record.member.active]
    deactivated = [record for record in records if not record.member.active]
    template = _TEMPLATES.get_template("team.html")
    return template.render(
        page_path=PAGE_PATH,
        roles_path=ROLES_PATH,
        active=active,
        deactivated=deactivated,
        roles_by_member=await _roles_by_member(),
        faults=faults,
        notice=notice,
    )


async def _roles_by_member() -> dict[str, list[dict[str, Any]]]:
    """Each member's roles, keyed by identifier, for the list.

    Slugs rather than titles here: a row carries several of them, and a run of
    full job titles would outweigh the name that is the row's subject. The
    title is one click away on the role's own page.
    """
    if roles is None:
        return {}
    records = await list_role_records(roles=roles)
    held: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for holder in record.role.holders:
            held.setdefault(holder, []).append(
                {
                    "slug": record.role.slug,
                    "title": record.role.title,
                    "status": record.role.status.value,
                    "is_default": record.role.default_holder == holder,
                }
            )
    return held


async def _render_new(
    *,
    faults: tuple[str, ...] = (),
    submitted: dict[str, str] | None = None,
) -> str:
    template = _TEMPLATES.get_template("member_new.html")
    return template.render(
        page_path=PAGE_PATH,
        faults=faults,
        submitted=submitted or {},
    )


async def _render_member(
    member_id: str,
    *,
    faults: tuple[str, ...] = (),
    notice: str | None = None,
    submitted: dict[str, str] | None = None,
) -> str:
    """One member's own page, where every change to them is made."""
    records, _ = await members.load()
    record = next(
        (r for r in records if r.member.identifier == member_id),
        None,
    )
    if record is None:
        raise HTTPException(status_code=404)
    template = _TEMPLATES.get_template("member.html")
    return template.render(
        page_path=PAGE_PATH,
        roles_path=ROLES_PATH,
        record=record,
        held=await _roles_held_by(member_id),
        faults=faults,
        notice=notice,
        submitted=submitted or {},
    )


async def _roles_held_by(member_id: str) -> list[dict[str, Any]]:
    """Every role this member holds, and whether they are its default.

    Read here rather than left to be inferred from the Roles pages: the roles a
    member holds is the thing that decides whether they can be deactivated at
    all, so the page carrying that refusal should also carry what causes it.
    """
    if roles is None:
        return []
    records = await list_role_records(roles=roles)
    return [
        {
            "slug": r.role.slug,
            "title": r.role.title,
            "status": r.role.status.value,
            "is_default": r.role.default_holder == member_id,
        }
        for r in records
        if member_id in r.role.holders
    ]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}


async def _form(request: Request) -> dict[str, str]:
    posted = await request.form()
    return {key: str(value) for key, value in posted.items()}


@router.get(PAGE_PATH, response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render())


# Registered before `/{member_id}` so the literal wins the match rather than
# being read as a member whose identifier is "new".
@router.get(PAGE_PATH + "/new", response_class=HTMLResponse)
async def new(request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render_new())


@router.post(PAGE_PATH + "/new", response_class=HTMLResponse)
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
        # The submitted values ride back with the faults, and the admin stays
        # on the create page: an admin who mistyped one field should not have
        # to retype the others, nor hunt for the refusal back on the list.
        return HTMLResponse(
            await _render_new(faults=_faults_of(rejected), submitted=form)
        )
    except StaleMembersError:
        return HTMLResponse(await _render(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)


@router.get(PAGE_PATH + "/{member_id}", response_class=HTMLResponse)
async def member_page(member_id: str, request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render_member(member_id))


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
        return HTMLResponse(
            await _render_member(member_id, faults=_faults_of(rejected), submitted=form)
        )
    except StaleMembersError:
        return HTMLResponse(await _render_member(member_id, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{member_id}", status_code=303)


@router.post(PAGE_PATH + "/{member_id}/deactivate", response_class=HTMLResponse)
async def deactivate(member_id: str, request: Request) -> Any:
    principal = await _require_admin(request)
    try:
        await deactivate_member(
            members=members,
            principal=principal,
            member_id=member_id,
            roles=roles,
        )
    except InvalidMembersError as refused:
        # Both refusals land here — the last-admin floor and the active-role
        # default — and each explanation is what the page shows, never a
        # paraphrase. A write blocked by both shows both.
        return HTMLResponse(await _render_member(member_id, faults=_faults_of(refused)))
    except StaleMembersError:
        return HTMLResponse(await _render_member(member_id, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{member_id}", status_code=303)


@router.post(PAGE_PATH + "/{member_id}/reactivate", response_class=HTMLResponse)
async def reactivate(member_id: str, request: Request) -> Any:
    principal = await _require_admin(request)
    try:
        await reactivate_member(
            members=members, principal=principal, member_id=member_id
        )
    except InvalidMembersError as refused:
        return HTMLResponse(await _render_member(member_id, faults=_faults_of(refused)))
    except StaleMembersError:
        return HTMLResponse(await _render_member(member_id, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{member_id}", status_code=303)


@router.post(PAGE_PATH + "/{member_id}/roles/remove", response_class=HTMLResponse)
async def remove_role(member_id: str, request: Request) -> Any:
    """Take a role off this member, from their own page.

    The same use case the role's own page calls, so every rule holds
    identically — an active role's default cannot be removed here either, and
    the refusal explaining that is rendered on this page rather than on the
    role's.
    """
    principal = await _require_admin(request)
    form = await _form(request)
    try:
        await remove_role_holder(
            roles=roles,
            members=members,
            principal=principal,
            slug=(form.get("slug") or "").strip(),
            member_id=member_id,
        )
    except (InvalidRolesError, ValueError) as refused:
        return HTMLResponse(await _render_member(member_id, faults=_faults_of(refused)))
    except StaleMembersError:
        return HTMLResponse(await _render_member(member_id, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{member_id}", status_code=303)
