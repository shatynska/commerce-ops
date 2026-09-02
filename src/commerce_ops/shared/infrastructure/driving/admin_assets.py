"""Driving adapter: the admin surfaces' presentation assets.

One route, `GET /admin/assets/{asset}`, serving the stylesheet both admin
surfaces load from `static/` beside this module. Both surfaces reach it on
equal terms, so "the same stylesheet" is literally one URL for one file
rather than a convention two modules are trusted to keep.

It lives in `shared` because that is the only place `launch.infrastructure`
and `access.infrastructure` may both reach without relaxing an
`import-linter` contract. `shared` may not import a business module, so
this module cannot ask `access` whether a caller holds an admin session;
the composition root, which may know both, hands it `verify` after the app
is built — the idiom `members_admin` and `playbook_admin` already use for
their own collaborators, resolved at call time.

This module knows nothing about what an "admin" is. It was handed a
callable that either answers a principal or answers nothing; the word is
in its route path and its filename, not in its dependencies.

An **un-injected** `verify` refuses. A route defaulting to serving when
the composition root forgot to wire it would answer 200 to an anonymous
caller while every other admin path answered 404 — an existence oracle for
the admin surface, and a contradiction of `admin-session`'s requirement
that the principal resolve admin-capable at the time of the request. Absent
a guard is not the same as passing one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

__all__ = [
    "ASSET_PATH",
    "router",
    "verify",
]

SESSION_COOKIE: Final = "admin_session"

ASSET_PATH: Final = "/admin/assets/{asset}"

STATIC_DIR: Final = Path(__file__).parent / "static"

TEMPLATES_DIR: Final = Path(__file__).parent / "templates"

router = APIRouter()

# Injected by `main.py` after the app is built. Resolved at call time, and
# left `None` here so a mis-wired composition root fails closed.
verify: Any = None


async def _require_admin(request: Request) -> str:
    """The one guard this route rides. Refusal is the app's own 404 —
    identical to an unregistered route, whatever actually failed, an
    un-injected `verify` included."""
    session_id = request.cookies.get(SESSION_COOKIE)
    principal: str | None = None
    if verify is not None and session_id:
        principal = await verify(session_id=session_id)
    if principal is None:
        raise HTTPException(status_code=404)
    return principal


@router.get(ASSET_PATH)
async def admin_asset(asset: str, request: Request) -> Response:
    await _require_admin(request)
    # The traversal guard `playbook_admin.static_asset` already carries,
    # copied rather than reinvented: a resolved path whose parent is not
    # this directory is not something this route serves.
    path = (STATIC_DIR / asset).resolve()
    if path.parent != STATIC_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404)
    # `no-cache` is "revalidate before reusing", not "do not store": the
    # response still carries an ETag, so an unchanged file costs a 304 and
    # no bytes. Without it a browser serves the stylesheet it already has
    # while the templates come fresh from the server every request, which
    # presents as markup that changed and styling that did not — a fault
    # nobody can find by reading the diff.
    return FileResponse(path, headers={"Cache-Control": "no-cache"})
