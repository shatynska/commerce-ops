"""Reports `active` steps this deployment cannot resolve (`launch-playbook`).

Runs as its own process in the container's start chain, after
`alembic upgrade head` and beside the roster seed:

    preflight && alembic upgrade head && seed-admin && check-step-handlers
        && exec uvicorn

An `automated` step names a handler; the deployed code registers handlers
under names. That a handler is *present* on a step is a property of the
step set and is checked whenever the playbook is constructed. That this deployment
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
violates no contract — and, for the same reason, `registrations`.

It **registers the handlers it reports on**, at module scope, as the two
composition roots do. Registering a handler is an import side effect, so
a process that never imports the handler modules holds an empty registry
— and a report drawn from one names every `active` `automated` step as
unresolvable, answering identically whether or not this deployment
registers a step's handler. That report establishes nothing about either,
which is why the registration belongs here rather than in the caller.

Reads the **authored** set, through the authoring read rather than the
serving one. That is what it always wanted — it reports on every step that
names a handler, whatever its status — and since
`serve-only-a-ready-playbook` it also matters: the serving read refuses a
playbook that cannot hold a launch, so taking it here would suppress this
report in exactly the state the change makes reachable, an unregistered
handler going unmentioned for the whole of a bootstrap.

One consequence to know: this step no longer constructs the aggregate, so
an incoherent stored set no longer aborts the container start chain here.
No accepted write can persist one, but a hand-edit or a rollback could.
"""

from __future__ import annotations

import asyncio
import logging

from commerce_ops.launch.application import (
    HANDLERS,
    authored_definitions,
    report_unregistered_handlers,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.database import dispose_engine, session
from commerce_ops.shared.infrastructure.logging import configure_logging

_logger = logging.getLogger(__name__)

# At module scope, as in `main.py` and `worker.py`, and load-bearing here:
# the guard reads each root by import alone, so a call deferred into
# `main()` would leave an importer of this module looking unregistered.
register_all()


async def _report() -> None:
    try:
        async with session() as db_session:
            records, _ = await PlaybookRepository(db_session).load()
        faults = report_unregistered_handlers(
            steps=authored_definitions(records), handlers=HANDLERS
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
