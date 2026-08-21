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
