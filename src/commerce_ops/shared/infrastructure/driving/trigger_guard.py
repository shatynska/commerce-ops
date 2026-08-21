"""Driving-adapter guard: restricts a route to callers holding `TRIGGER_SECRET`.

Implements the `internal-trigger` capability
(`openspec/changes/add-product-agent-daily-digest/specs/internal-trigger/spec.md`).
Lives in `shared.infrastructure.driving`, not a business module, since it
carries no business logic and calls into no module -- any module's own
driving adapter attaches it via `Depends()` (the Shared Kernel exception:
`infrastructure` -> any of `shared`'s layers).
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException

_BEARER_PREFIX = "Bearer "


async def require_trigger_secret(
    authorization: str | None = Header(default=None),
) -> None:
    configured = os.environ.get("TRIGGER_SECRET")
    if not configured:
        raise HTTPException(status_code=401, detail="trigger secret is not configured")

    if authorization is None or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=401, detail="missing or malformed Authorization header"
        )

    presented = authorization[len(_BEARER_PREFIX) :]
    if not secrets.compare_digest(presented, configured):
        raise HTTPException(status_code=401, detail="invalid trigger secret")
