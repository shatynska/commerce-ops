"""The one list of job and handler modules, called by both composition roots.

A sibling of `main.py`, `preflight.py` and `worker.py`, deliberately outside
`.importlinter`'s containers: it names modules in both `products` and
`shared`, which no module inside either container may do.

**One list, not two per-root lists.** Importing a job module is what registers
its schedule and its tolerance, so a root that imports a different set sees a
different registry. The failure is silent and asymmetric: `main.py` omitting
the overdue-check module would leave the freshness endpoint with no worker
liveness to report, while every non-emptiness test still passed. See
design.md, "Schedules and tolerances live in one registry".

Nothing here may read configuration at import. This module pulls the job
modules into `main.py`'s import graph, and `runtime-configuration`'s
"Importing And Starting The Application Do Not Require Configuration To Be
Present" is enforced by a fresh-interpreter guard that would fail
(tasks.md 1.4a).
"""

from __future__ import annotations

from types import ModuleType

# Imported for the imports' own sake: importing a module that holds a job
# definition is what registers it. These look unused, which is exactly the
# kind of import a later cleanup removes -- a test runs each composition root
# in a fresh interpreter and compares the registries to catch that.
from commerce_ops.briefing.infrastructure.driving import (
    daily_briefing_job as _daily_briefing_job,
)
from commerce_ops.launch.infrastructure.driving import (
    automation_pass as _automation_pass,
)
from commerce_ops.launch.infrastructure.driving import (
    clickup_sync_job as _clickup_sync_job,
)
from commerce_ops.shared.infrastructure.driving import (
    overdue_check as _overdue_check,
)

# Step handlers register the same way jobs do -- by being imported -- and
# carry the same asymmetric failure. Activation is validated against the
# registry in the process serving the admin surface; the automation pass
# needs the handler in the worker. A handler imported into only one root
# leaves `check_step_handlers` reporting it registered while an admin's
# activation is refused as naming an unknown handler
# (`introduce-automation-runtime`).
from commerce_ops.subcategory_advisor.application import (
    handler as _subcategory_advisor,
)

__all__ = ["HANDLER_MODULES", "JOB_MODULES", "register_all"]

JOB_MODULES: tuple[ModuleType, ...] = (
    _daily_briefing_job,
    _automation_pass,
    _clickup_sync_job,
    _overdue_check,
)


HANDLER_MODULES: tuple[ModuleType, ...] = (_subcategory_advisor,)


def register_all() -> None:
    """Ensure every job module in the one list has registered itself.

    Registration happens as each module is imported, so by the time this is
    called the work is done; the call exists so that both roots state the
    dependency explicitly rather than relying on an import whose only effect
    is a side effect.

    Safe to call twice in one process -- both roots may be imported in a
    single test -- because registration is idempotent per identifier and a
    conflicting re-registration raises rather than silently overwriting
    (tasks.md 1.4b).
    """
    for module in (*JOB_MODULES, *HANDLER_MODULES):
        assert module is not None
