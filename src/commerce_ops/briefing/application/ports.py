"""Consumer-owned ports `briefing.application` depends on.

Every one of these is satisfied by a callable the composition root closes
over — `worker.py` builds them from launch's and catalog's public
surfaces plus their repositories, the way `clickup_sync_job.read_product`
already is. Briefing never imports another module's infrastructure, and
`.importlinter` holds it to that.

`LaunchReports` is typed loosely on purpose: its element is launch's own
`LaunchReport`, and naming that type here would make briefing's ports
depend on launch's application module for a type alone. The report is
read through the attributes `launch-instance` specifies, so a structural
port is the honest description of what briefing actually requires.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol

from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import LifecycleStage


class LaunchReports(Protocol):
    """Every launch position, reported as of a date."""

    async def __call__(self, *, as_of: date) -> Sequence[Any]: ...


class CatalogProduct(Protocol):
    """The three facts briefing needs about a product: how to name it,
    and whether its launch is still live."""

    @property
    def name(self) -> str: ...

    @property
    def sku(self) -> Sku: ...

    @property
    def stage(self) -> LifecycleStage: ...


class ProductReader(Protocol):
    """Resolves a product, or reports that it cannot — absence is `None`,
    never an exception, because an unresolvable product must not cost the
    briefing its item."""

    async def __call__(self, product_id: ProductId) -> CatalogProduct | None: ...


class BriefingNotifier(Protocol):
    """Delivers the briefing. `MonitoringNotifier`'s shape, declared here
    so briefing owns the port it depends on."""

    async def post_monitoring_message(self, message: str) -> None: ...
