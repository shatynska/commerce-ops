"""SQLAlchemy model for the `products` table.

Maps `launch-instance`'s persisted shape (see
`openspec/changes/add-products-store/specs/launch-instance/spec.md`) to
Postgres. `GATE_IDS` is a deliberate, standalone copy of the eight
`launch-playbook` gate identifiers — see design.md's Decisions section on
why this table does not import `products.domain.launch_playbook`'s `Gate`
enum for it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import CheckConstraint, Date, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

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


class Base(DeclarativeBase):
    pass


_GATE_LIST = ", ".join(f"'{gate}'" for gate in GATE_IDS)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            f"current_gate IN ({_GATE_LIST})",
            name="ck_products_current_gate_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    asin: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
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
