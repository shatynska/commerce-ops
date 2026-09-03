"""Driving adapter: the Roles admin pages (`roles-admin`).

Server-rendered HTML end to end — Jinja templates and plain forms, the shape
`playbook_admin` established and `members_admin` follows, so every admin
surface reads the same way and none needs JavaScript to work.

Built to the pattern `move-step-actions-into-step-pages` shipped, from the
start rather than built inline and rebuilt later: the list is read-only and
each role's title links to its own page, where every change to that role is
made. That includes the parts the pattern gained *after* it first shipped —
the breadcrumb back to the list, which the header does not supply because it
identifies the current surface as a position rather than as a link.

Every route rides the same admin-session guard as its neighbours, and refusal
is the app's own 404: an unauthenticated caller cannot tell the surface exists.
Writes go through the `roles` capability's use cases — this module never
touches the store directly — so every lifecycle and holder rule is enforced in
one place and merely *rendered* here.

`roles`, `members` and `admin_sessions` are injected by `main.py` after the app
is built (the pattern the other admin adapters use); absent injection refuses
every request, which is the failing-closed direction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import (
    InvalidRolesError,
    RoleStatus,
    StaleRolesError,
    activate_role,
    add_role_holder,
    create_role,
    list_role_records,
    move_role_default,
    remove_role_holder,
    retire_role,
    update_role,
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

PAGE_PATH: Final = "/admin/roles"

TEAM_PATH: Final = "/admin/team"
"""The members half of the Team surface, as a literal — the shared header
already writes every admin path as one, for the reason recorded there."""

SESSION_COOKIE: Final = "admin_session"

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
    "The role collection changed underneath this write — nothing was saved. "
    "This page shows the collection as it stands now; redo the change on it."
)

router = APIRouter()

# Injected by `main.py` after the app is built. Resolved at call time.
roles: Any = None
members: Any = None
admin_sessions: Any = None


async def _require_admin(request: Request) -> str:
    """The one guard every roles route rides. Refusal is the app's own 404 —
    identical to an unregistered route, whatever actually failed."""
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


async def _membership() -> dict[str, Any]:
    """Every member by identifier, for rendering a holder as a person rather
    than as a `uuid4` nobody can read."""
    if members is None:
        return {}
    rows, _version = await members.load()
    return {row.member.identifier: row.member for row in rows}


async def _render_list(
    *, faults: tuple[str, ...] = (), notice: str | None = None
) -> str:
    """The collection as it stands now, grouped by status.

    Grouped rather than sorted into one run: a draft role and an active one
    differ in exactly one obligation, and a listing that mixed them would leave
    that difference to be inferred from a column.
    """
    records = await list_role_records(roles=roles)
    known = await _membership()
    grouped = {
        status: [r for r in records if r.role.status is status] for status in RoleStatus
    }
    template = _TEMPLATES.get_template("roles.html")
    return template.render(
        page_path=PAGE_PATH,
        team_path=TEAM_PATH,
        active=grouped[RoleStatus.ACTIVE],
        draft=grouped[RoleStatus.DRAFT],
        retired=grouped[RoleStatus.RETIRED],
        members_by_id=known,
        faults=faults,
        notice=notice,
    )


async def _render_new(
    *, faults: tuple[str, ...] = (), submitted: dict[str, str] | None = None
) -> str:
    known = await _membership()
    template = _TEMPLATES.get_template("role_new.html")
    return template.render(
        page_path=PAGE_PATH,
        team_path=TEAM_PATH,
        candidates=[m for m in known.values() if m.active],
        faults=faults,
        submitted=submitted or {},
    )


async def _render_role(
    slug: str,
    *,
    faults: tuple[str, ...] = (),
    notice: str | None = None,
    submitted: dict[str, str] | None = None,
) -> str:
    """One role's own page.

    The collection is re-read rather than patched from a write's result, so a
    rejected write renders exactly what is stored — which is what makes "the
    collection is unchanged" visible rather than merely claimed.
    """
    records = await list_role_records(roles=roles)
    record = next((r for r in records if r.role.slug == slug), None)
    if record is None:
        raise HTTPException(status_code=404)
    known = await _membership()
    template = _TEMPLATES.get_template("role.html")
    return template.render(
        page_path=PAGE_PATH,
        team_path=TEAM_PATH,
        record=record,
        role=record.role,
        members_by_id=known,
        holders=[known.get(h) for h in record.role.holders],
        candidates=[
            m
            for m in known.values()
            if m.active and m.identifier not in record.role.holders
        ],
        movable=[
            known.get(h)
            for h in record.role.holders
            if h != record.role.default_holder and known.get(h) is not None
        ],
        faults=faults,
        notice=notice,
        submitted=submitted or {},
    )


async def _form(request: Request) -> dict[str, str]:
    posted = await request.form()
    return {key: str(value) for key, value in posted.items()}


@router.get(PAGE_PATH, response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render_list())


# Registered before `/{slug}` so the literal wins the match rather than being
# read as a role whose slug is "new".
@router.get(PAGE_PATH + "/new", response_class=HTMLResponse)
async def new(request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render_new())


@router.post(PAGE_PATH + "/new", response_class=HTMLResponse)
async def create(request: Request) -> Any:
    principal = await _require_admin(request)
    form = await _form(request)
    holder = (form.get("default_holder") or "").strip() or None
    try:
        await create_role(
            roles=roles,
            members=members,
            principal=principal,
            slug=(form.get("slug") or "").strip(),
            title=form.get("title", ""),
            status=(form.get("status") or RoleStatus.DRAFT.value).strip(),
            default_holder=holder,
        )
    except (InvalidRolesError, ValueError) as rejected:
        # The submitted values ride back with the faults, and the admin stays
        # on the form that produced them: a refusal is read where the values
        # that caused it are still visible.
        return HTMLResponse(
            await _render_new(faults=_faults_of(rejected), submitted=form)
        )
    except StaleRolesError:
        return HTMLResponse(await _render_list(notice=STALE_NOTICE))
    return RedirectResponse(PAGE_PATH, status_code=303)


@router.get(PAGE_PATH + "/{slug}", response_class=HTMLResponse)
async def role_page(slug: str, request: Request) -> HTMLResponse:
    await _require_admin(request)
    return HTMLResponse(await _render_role(slug))


@router.post(PAGE_PATH + "/{slug}/edit", response_class=HTMLResponse)
async def edit(slug: str, request: Request) -> Any:
    principal = await _require_admin(request)
    form = await _form(request)
    try:
        await update_role(
            roles=roles,
            members=members,
            principal=principal,
            slug=slug,
            title=form.get("title", ""),
        )
    except (InvalidRolesError, ValueError) as rejected:
        return HTMLResponse(
            await _render_role(slug, faults=_faults_of(rejected), submitted=form)
        )
    except StaleRolesError:
        return HTMLResponse(await _render_role(slug, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{slug}", status_code=303)


async def _act(
    slug: str,
    request: Request,
    action: Any,
    form_field: str | None = None,
    **extra: Any,
) -> Any:
    """One shape for every write reached from a role's own page.

    Each refusal is surfaced with the capability's own explanation rather than
    a generic one — activating a draft holding nobody, un-retiring a role whose
    default has since been deactivated, and removing an active role's default
    each explain the specific obligation they failed.
    """
    principal = await _require_admin(request)
    # The body is read only after the guard has run. Parsing it first would
    # buffer an unauthenticated caller's upload before refusing them, which is
    # the one way a 404 meant to reveal nothing still costs something.
    if form_field is not None:
        form = await _form(request)
        extra[form_field] = (form.get(form_field) or "").strip()
    try:
        await action(
            roles=roles, members=members, principal=principal, slug=slug, **extra
        )
    except (InvalidRolesError, ValueError) as refused:
        return HTMLResponse(await _render_role(slug, faults=_faults_of(refused)))
    except StaleRolesError:
        return HTMLResponse(await _render_role(slug, notice=STALE_NOTICE))
    return RedirectResponse(f"{PAGE_PATH}/{slug}", status_code=303)


@router.post(PAGE_PATH + "/{slug}/retire", response_class=HTMLResponse)
async def retire(slug: str, request: Request) -> Any:
    return await _act(slug, request, retire_role)


@router.post(PAGE_PATH + "/{slug}/activate", response_class=HTMLResponse)
async def activate(slug: str, request: Request) -> Any:
    return await _act(slug, request, activate_role)


@router.post(PAGE_PATH + "/{slug}/holders", response_class=HTMLResponse)
async def add_holder(slug: str, request: Request) -> Any:
    return await _act(slug, request, add_role_holder, form_field="member_id")


@router.post(PAGE_PATH + "/{slug}/holders/remove", response_class=HTMLResponse)
async def remove_holder(slug: str, request: Request) -> Any:
    return await _act(slug, request, remove_role_holder, form_field="member_id")


@router.post(PAGE_PATH + "/{slug}/default", response_class=HTMLResponse)
async def move_default(slug: str, request: Request) -> Any:
    return await _act(slug, request, move_role_default, form_field="member_id")
