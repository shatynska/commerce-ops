"""The admin surface's session harness.

Forty-five files stand a verified admin session up the same way: one cookie
name, one session value, and a stand-in for the real session verification that
answers a principal when it sees that value and `None` otherwise.

`fake_verify` is a **factory**, not the stand-in itself, because the principal
is not uniform: of the 45 files, 28 verify as `"helen"` and 17 as `"U01ALICE"`.
A shared closure over one of them would silently answer the wrong principal in
the other 17 — the migration would look mechanical and change what a third of
the files exercise. Each file binds its own::

    _fake_verify = fake_verify(PRINCIPAL)

The session value *is* uniform across all 45, so it is a default rather than a
parameter the caller has to remember.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final

#: The cookie the admin surface carries its session in.
SESSION_COOKIE: Final = "admin_session"

#: A session value the stand-in below treats as verified.
SESSION_VALUE: Final = "a-verified-admin-session"

#: The Slack identity the seeded admin holds.
ADMIN_IDENTITY: Final = "U01ALICE"


def fake_verify(
    principal: str, session_value: str = SESSION_VALUE
) -> Callable[..., Awaitable[str | None]]:
    """A session verifier answering `principal` for `session_value` alone.

    Accepts any call shape: the real verifier has been called positionally and
    by keyword at different sites, and the stand-in should not care which. It
    searches the stringified arguments rather than naming a parameter, which is
    what every local copy of this did.
    """

    async def verify(*args: Any, **kwargs: Any) -> str | None:
        haystack = " ".join(str(value) for value in (*args, *kwargs.values()))
        return principal if session_value in haystack else None

    return verify
