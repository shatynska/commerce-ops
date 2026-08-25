"""Reports `active` steps this deployment cannot resolve (`launch-playbook`).

Runs as its own process in the container's start chain, after
`alembic upgrade head` and beside the roster seed:

    preflight && alembic upgrade head && seed-admin && check-step-handlers
        && exec uvicorn

An `automated` step names a handler; the deployed code registers handlers
under names. That a handler is *present* on a step is a property of the
step set and is checked whenever the playbook loads. That this deployment
**registers** it is not — the registry changes without the step set
changing — so it is checked when a step is activated, and never again at
load. A rename in the registry must fail a deployment, not take every
launch down to report a deployment fault.

This step is where that report belongs. It is **advisory**: it logs and
exits zero. Refusing to start would turn one unresolvable step into a
full outage, which is the trade `runtime-configuration` already settles
the same way — and unlike an unadministrable roster, an unresolved
automated step leaves everything else in the launch working.

Lives beside `main.py`, outside the containers `.importlinter` layers, so
naming both the launch module's public surface and its repository here
violates no contract.
"""

from __future__ import annotations

import asyncio
import logging

from commerce_ops.launch.application import (
    HANDLERS,
    report_unregistered_handlers,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.infrastructure.driven.database import dispose_engine, session
from commerce_ops.shared.infrastructure.logging import configure_logging

_logger = logging.getLogger(__name__)


async def _report() -> None:
    try:
        async with session() as db_session:
            playbook = await PlaybookRepository(db_session).get("startup")
        faults = report_unregistered_handlers(
            steps=playbook.authored_steps, handlers=HANDLERS
        )
    finally:
        # This process obtained a session, so it closes the pool before
        # exiting — the obligation `database-session` places on any
        # process that did, not only on the HTTP one.
        await dispose_engine()

    if not faults:
        _logger.info(
            "step handlers: every active automated step names a handler this "
            "deployment registers (%d registered)",
            len(HANDLERS),
        )
        return
    for fault in faults:
        _logger.error("step handlers: %s", fault)
    _logger.error(
        "step handlers: %d active step(s) name a handler this deployment does "
        "not register; they will not resolve until the handler is registered "
        "or the step is moved out of 'active'",
        len(faults),
    )


def main() -> int:
    configure_logging()
    asyncio.run(_report())
    # Advisory: an unresolvable step is a fault worth naming, never a
    # reason to leave the previous release serving.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
