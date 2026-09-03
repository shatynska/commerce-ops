"""The membership's pre-serving seeding step (`members`).

Runs as its own process in the container's start chain, between
`alembic upgrade head` and the server:

    preflight && alembic upgrade head && seed-admin && exec uvicorn

Deliberately *not* part of the serving process's startup. Reading the
members there would make the server open a database connection before its
first request, which `database-session` requires not to happen — and it
does more than break a rule on paper: the connection setting is read once
per process and cached, so an engine built at startup outlives any later
attempt to point the application at a different database.

Failing here also fails better than refusing to start would. An
unadministrable members stops one named preparation step, next to the
migration step an operator already reads, and leaves the previous release
serving — rather than crash-looping a server that would otherwise have
served Slack, the webhooks and the health endpoint perfectly well.

Exit status is the whole interface: zero when the membership holds an active
admin (seeded now or already there), non-zero with the reason on stderr
when it cannot.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from commerce_ops.access.application import seed_bootstrap_admin, seed_roles
from commerce_ops.access.infrastructure.driven.members_repository import (
    PostgresMembers,
)
from commerce_ops.access.infrastructure.driven.roles_repository import PostgresRoles
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.logging import configure_logging

_logger = logging.getLogger(__name__)


async def _seed() -> None:
    try:
        members = PostgresMembers()
        seeded = await seed_bootstrap_admin(members=members)
        # The roles, in the same step: their default holders are members, so
        # the membership must be usable first, and `seed_playbook` — which
        # follows in the container's chain — will come to reference these
        # slugs. `seeded` is the member this run established, where it
        # established one; on an already-administered membership it is None
        # and `seed_roles` resolves the seeding administrator itself.
        added = await seed_roles(
            roles=PostgresRoles(), members=members, seeding_administrator=seeded
        )
    finally:
        # This process opened its own engine; the server that follows in
        # the chain gets a clean one.
        await dispose_engine()
    if seeded is None:
        _logger.info("the membership already holds an active admin; none seeded")
    if added:
        _logger.info("seeded %d role(s)", len(added))
    else:
        _logger.info("every seeded role is already present; none added")


def main() -> int:
    configure_logging()
    try:
        asyncio.run(_seed())
    except Exception as failure:  # noqa: BLE001 — the exit status is the interface
        print(f"admin seeding failed: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
