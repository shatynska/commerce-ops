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
from dataclasses import dataclass
from typing import Any, Protocol

from commerce_ops.launch.application.journal import JournalOccurrence
from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import LifecycleStage


class LaunchStore(Protocol):
    """The persistence port the launch use cases speak."""

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None: ...

    async def save(self, launch: Launch) -> None: ...

    async def list_all(self) -> Sequence[Launch]: ...


class LaunchJournal(Protocol):
    """The append-only record of what happened to a launch.

    Separate from `LaunchStore` on purpose: that port persists the
    launch's *current state*, this one its history, and keeping the two
    apart is the distinction `launch-journal` exists to draw. Every
    journaled command takes one, required rather than defaulted, so that
    a composing adapter cannot omit journaling silently (design.md
    Decision 1).

    `rollback` is part of the port because containment needs it: a
    failed append leaves the session unusable for the work that follows
    the command, and catching the exception without unwinding would let
    the journal break a graduation (design.md Decision 3).
    """

    async def append(self, occurrence: JournalOccurrence) -> None: ...

    async def read(self, product_id: ProductId) -> Sequence[JournalOccurrence]: ...

    async def rollback(self) -> None: ...


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


@dataclass(frozen=True, slots=True)
class FindingSink:
    """Where a step's supported finding is written, and how that field
    reads once it is.

    One value rather than two mappings keyed by the same step: a step
    could otherwise acquire a sink and no field name, or a field name and
    no sink, and neither is a state worth being able to represent.

    `reads_as` travels with the finding onto the recording rather than
    being resolved by whoever renders it. The registration lives in the
    composition root of the process running the automation pass, and the
    surface that renders it is served by another; a second registry on
    that side is the drift `registrations.py` exists to prevent
    (`launch-instance`).
    """

    record: Any
    field: str
    reads_as: str | None = None


class FindingRecorder(Protocol):
    """Records a handler's supported finding against a product — the
    recording use case's shape minus the store, so the launch module never
    sees catalog internals. Satisfied by a partial application of whichever
    `catalog.application` use case the sink writes through, wired at the
    composition root the same way `SteadyStateStamper` is.

    **The value is deliberately untyped, and that is the honest
    declaration rather than a gap.** This one port stands for every sink,
    and what a sink writes is a property of the sink: `lp.listing.007`
    writes a sub-category string, `lp.strategy.006` a sequence of hazard
    categories, and a third would write a third thing. There is no type
    that is true of all of them and narrower than this one.

    It replaces `SubCategoryRecorder`, which named one field in its own
    signature. That was accurate while one sink existed;
    `separate-the-result-from-the-comment` left it deliberately, recording
    that widening it belonged to the change adding a second sink with a
    different value type. This is that port.
    """

    async def __call__(self, product_id: ProductId, value: Any) -> object: ...
