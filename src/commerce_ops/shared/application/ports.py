"""Consumer-owned ports `shared.application` exposes to other modules.

`.importlinter`'s `module-layers` contract forbids a business module's
`application` layer from importing `shared.infrastructure` directly.
`clickup_client` (infrastructure) satisfies `ClickUpTaskWriter`
structurally -- its `create_task`/`update_task` functions already match
this Protocol's shape -- so a consumer's application layer can depend on
the capability without either layer importing the other by name. See
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from commerce_ops.shared.domain.clickup import ClickUpTask


class ClickUpTaskWriter(Protocol):
    async def create_task(
        self, list_id: str, name: str, description: str | None = None
    ) -> ClickUpTask: ...

    async def update_task(
        self, task_id: str, fields: Mapping[str, object]
    ) -> ClickUpTask: ...


class MonitoringNotifier(Protocol):
    """Somewhere to report that scheduled work has stopped happening.

    `shared` may not import `products` (`.importlinter`'s `shared-boundary`),
    and the only notifier this deployment has lives in
    `products/infrastructure/driven/slack_notifier.py`. So the overdue check
    depends on this shape rather than on that module, and `worker.py` -- which
    sits outside the `.importlinter` containers -- passes the real one in.

    Satisfied by the `slack_notifier` **module** itself, not by a bare
    function of the same name: a Protocol declaring a method is satisfied by
    an object carrying that attribute, which is what the module is.
    """

    async def post_monitoring_message(self, message: str) -> None: ...
