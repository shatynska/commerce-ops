"""SQLAlchemy model for the catalog-owned `products` table.

Maps `product-catalog`'s persisted shape (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`)
to Postgres. The table keeps its pre-split name and primary keys — design.md
Decision 7: catalog takes over `products`; the launch-position fields moved
to the `products` module's `launch_positions` table.

The lifecycle stage is stored as three columns — `stage` (the kind),
`launching_phase`, `posture` — because the stage is a sum type whose two
parametrized variants each carry one value; `stage_confirmed_by` is nullable
(absent until the first stage change, per the registration-provenance rule).
The stage-to-columns mapping lives in the repository, next to the only code
that reads or writes it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from commerce_ops.shared.infrastructure.driven.orm import Base

STAGE_KINDS: Final[tuple[str, ...]] = (
    "development",
    "launching",
    "steady-state",
    "retired",
)

_STAGE_LIST = ", ".join(f"'{kind}'" for kind in STAGE_KINDS)


class CatalogProduct(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            f"stage IN ({_STAGE_LIST})",
            name="ck_products_stage_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    marketplace_id: Mapped[str] = mapped_column(String, nullable=False)
    asin: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    launching_phase: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    posture: Mapped[str | None] = mapped_column(String, nullable=True)
    stage_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    stage_confirmed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
