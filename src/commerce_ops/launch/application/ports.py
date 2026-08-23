"""Consumer-owned ports `launch.application` depends on.

`.importlinter`'s `module-layers` contract forbids `launch.application`
from importing `launch.infrastructure` directly. `LaunchRepository`
(infrastructure) satisfies `LaunchStore` structurally; the playbook port
is satisfied by a thin wrapper over the shipped-playbook loader; the
stamping port is satisfied by a partial application of
`catalog.application.change_stage` over the catalog store — so graduation
crosses the module boundary only through catalog's public surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import LifecycleStage


class LaunchStore(Protocol):
    """The persistence port the launch use cases speak."""

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None: ...

    async def save(self, launch: Launch) -> None: ...

    async def list_all(self) -> Sequence[Launch]: ...


class Playbooks(Protocol):
    """Resolves a pinned playbook version to its loaded definition."""

    def get(self, version: str) -> LaunchPlaybook: ...


class SteadyStateStamper(Protocol):
    """Stamps a catalog product's stage on graduation — `change_stage`'s
    shape minus the store, so the launch module never sees catalog
    internals."""

    async def __call__(
        self, product_id: ProductId, stage: LifecycleStage, *, confirmed_by: str
    ) -> object: ...
