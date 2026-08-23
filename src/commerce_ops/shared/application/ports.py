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

from collections.abc import Mapping, Sequence
from typing import Protocol

from commerce_ops.shared.domain.clickup import ClickUpTask, ClickUpTaskState


class ClickUpTaskWriter(Protocol):
    async def create_task(
        self, list_id: str, name: str, description: str | None = None
    ) -> ClickUpTask: ...

    async def update_task(
        self, task_id: str, fields: Mapping[str, object]
    ) -> ClickUpTask: ...


class ClickUpListWriter(Protocol):
    """Creating the list a caller's own work is projected into."""

    async def create_list(self, folder_id: str, name: str) -> str: ...


class ClickUpTaskReader(Protocol):
    """Reading a list's tasks back, which is what lets a caller notice
    what changed in ClickUp without a webhook delivery."""

    async def list_tasks(self, list_id: str) -> Sequence[ClickUpTaskState]: ...


class ClickUpWorkspace(
    ClickUpTaskWriter, ClickUpListWriter, ClickUpTaskReader, Protocol
):
    """Every ClickUp operation the launch completion loop needs, in one
    port: it projects a list and its tasks, corrects them, and reads them
    back. The `clickup_client` module satisfies this structurally, as it
    already does `ClickUpTaskWriter`."""


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
