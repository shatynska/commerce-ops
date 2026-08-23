"""SQLAlchemy model for the `launch_positions` table.

Maps `launch-instance`'s reshaped persisted shape (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/launch-instance/spec.md`)
to Postgres: a launch-position record referencing a catalog product by
identifier. Product identity lives in the catalog-owned `products` table
(design.md Decision 7). `GATE_IDS` is a deliberate, standalone copy of the
eight `launch-playbook` gate identifiers — the reasoning recorded by
`add-products-store`'s design.md for not importing the domain model's gate
sequence here carries over unchanged.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from commerce_ops.shared.infrastructure.driven.orm import Base

GATE_IDS: Final[tuple[str, ...]] = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)


_GATE_LIST = ", ".join(f"'{gate}'" for gate in GATE_IDS)


class LaunchPosition(Base):
    __tablename__ = "launch_positions"
    __table_args__ = (
        CheckConstraint(
            f"current_gate IN ({_GATE_LIST})",
            name="ck_launch_positions_current_gate_valid",
        ),
    )

    # The product reference is the primary key: at most one launch position
    # per product, by construction.
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", name="fk_launch_positions_product_id"),
        primary_key=True,
    )
    playbook_version: Mapped[str] = mapped_column(String, nullable=False)
    current_gate: Mapped[str] = mapped_column(String, nullable=False)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
