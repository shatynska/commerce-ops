"""SQLAlchemy models for the launch-instance tables.

Maps `launch-instance`'s persisted shape (as reshaped by
`introduce-launch-aggregate`) to Postgres: the `launch_positions` spine —
a launch record referencing a catalog product by identifier — plus the
three child tables holding the aggregate's recorded state: step progress
(outcome + recording provenance), gate approvals, and metric
attestations, each keyed by the launch's product id with cascade delete.
Product identity lives in the catalog-owned `products` table (the
catalog split's design.md Decision 7). `GATE_IDS` is a deliberate,
standalone copy of the eight `launch-playbook` gate identifiers — the
reasoning recorded by `add-products-store`'s design.md for not importing
the domain model's gate sequence here carries over unchanged.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
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


OUTCOME_KINDS: Final[tuple[str, ...]] = (
    "not-started",
    "in-progress",
    "satisfied",
    "blocked",
    "refused",
    "not-applicable",
)

PROVENANCE_SOURCES: Final[tuple[str, ...]] = ("clickup", "automated", "attestation")

APPROVAL_DECISIONS: Final[tuple[str, ...]] = ("approving", "rejecting")

_OUTCOME_LIST = ", ".join(f"'{kind}'" for kind in OUTCOME_KINDS)
_SOURCE_LIST = ", ".join(f"'{source}'" for source in PROVENANCE_SOURCES)
_DECISION_LIST = ", ".join(f"'{decision}'" for decision in APPROVAL_DECISIONS)


class LaunchStepProgress(Base):
    """One recorded step outcome with its recording provenance — at most
    one row per (launch, step): a later recording replaces the stored
    outcome, per the launch-instance spec."""

    __tablename__ = "launch_step_progress"
    __table_args__ = (
        CheckConstraint(
            f"outcome_kind IN ({_OUTCOME_LIST})",
            name="ck_launch_step_progress_outcome_kind_valid",
        ),
        CheckConstraint(
            f"source IN ({_SOURCE_LIST})",
            name="ck_launch_step_progress_source_valid",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_step_progress_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    step_id: Mapped[str] = mapped_column(String, primary_key=True)
    outcome_kind: Mapped[str] = mapped_column(String, nullable=False)
    outcome_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    who: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence: Mapped[str] = mapped_column(String, nullable=False)


class LaunchGateApproval(Base):
    """One recorded confirmation decision per (launch, gate). The posture
    is present exactly on a graduation approval."""

    __tablename__ = "launch_gate_approvals"
    __table_args__ = (
        CheckConstraint(
            f"decision IN ({_DECISION_LIST})",
            name="ck_launch_gate_approvals_decision_valid",
        ),
        CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_gate_approvals_gate_id_valid",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_gate_approvals_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    gate_id: Mapped[str] = mapped_column(String, primary_key=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    approver: Mapped[str] = mapped_column(String, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    posture: Mapped[str | None] = mapped_column(String, nullable=True)


class LaunchClickUpList(Base):
    """The ClickUp list a launch's work is projected into — one per
    launch, which is what makes "a launch whose list already exists SHALL
    NOT get a second one" checkable (`launch-clickup-sync`)."""

    __tablename__ = "launch_clickup_lists"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_clickup_lists_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    list_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class LaunchClickUpTask(Base):
    """The ClickUp task standing for one step of one launch.

    Unique on both sides by design: the primary key gives a step exactly
    one task, and the unique constraint on `task_id` gives a task exactly
    one step — webhook intake arrives holding only a task identifier, so
    a task resolving to two steps would record against the wrong one.

    `last_observed_closed` is the whole basis of the transition rule
    (`launch-clickup-sync`, and design.md's "Recording is transition-based,
    keyed on the last observed state"): every observation writes it, and an
    outcome is recorded only when a fresh reading differs from it. It is
    deliberately *not* the step's recorded outcome — comparing against that
    would overwrite an attestation with `InProgress` on the next pass.
    """

    __tablename__ = "launch_clickup_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_launch_clickup_tasks_task_id"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_clickup_tasks_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    step_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    last_observed_closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class LaunchMetricAttestation(Base):
    """One recorded human attestation per (launch, gate, metric)."""

    __tablename__ = "launch_metric_attestations"
    __table_args__ = (
        CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_metric_attestations_gate_id_valid",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_metric_attestations_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    gate_id: Mapped[str] = mapped_column(String, primary_key=True)
    metric_id: Mapped[str] = mapped_column(String, primary_key=True)
    attester: Mapped[str] = mapped_column(String, nullable=False)
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence: Mapped[str] = mapped_column(String, nullable=False)
