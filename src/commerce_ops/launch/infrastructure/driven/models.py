"""SQLAlchemy models for the launch-instance tables.

Maps `launch-instance`'s persisted shape (as reshaped by
`introduce-launch-aggregate`) to Postgres: the `launch_positions` spine —
a launch record referencing a catalog product by identifier — plus the
two child tables holding the aggregate's recorded state: step progress
(outcome + recording provenance) and gate approvals, each keyed by the
launch's product id with cascade delete.
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
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    submitter: Mapped[str | None] = mapped_column(String, nullable=True)
    slack_thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
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

PROVENANCE_SOURCES: Final[tuple[str, ...]] = ("clickup", "automated")

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
    #: The finding this recording carries, or `NULL` where it carries
    #: none. One column rather than three: an empty *value* lives inside
    #: a finding that exists, and `NULL` is the whole of "carries
    #: nothing" (`launch-instance`).
    finding: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


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
    would overwrite a recorded outcome with `InProgress` on the next pass.
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
    # `move-playbook-steps-to-postgres`: the name and body the system last
    # composed for the task — the key of conditional wording-healing. Null
    # on rows predating the change (adopt-if-matching on first observation)
    # and wherever the system has not written that field.
    retained_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    retained_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # `redesign-step-fields`: the ClickUp users the system last assigned,
    # retained for the same reason the name and body are. Null on rows
    # predating the change, which is read as "last set to nobody" — an
    # unassigned task is the failure the projection exists to fix, so
    # silence there is the system's own doing rather than a member's edit.
    retained_assignees: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


LAUNCH_JOURNAL_KINDS: Final[tuple[str, ...]] = (
    "launch-started",
    "step-outcome-recorded",
    "gate-approval-recorded",
    "gate-opened",
    "launch-graduated",
    "launch-date-moved",
    "advance-refused",
)

_JOURNAL_KIND_LIST = ", ".join(f"'{kind}'" for kind in LAUNCH_JOURNAL_KINDS)


class LaunchJournalEntry(Base):
    """One occurrence in a launch's append-only journal.

    `launch-journal`: every command the launch context accepts appends
    exactly one row here, and a refused advance appends one too. Rows are
    **appended, never replaced or deleted** — a second recording against
    the same step is a second row, which is the whole difference between
    this table and the state it records.

    `sequence` is the primary key because this table is about *order*
    while every other launch table is about what it holds. Two entries
    routinely name the same moment — a reconciliation pass recording
    several steps with one timestamp is the ordinary case — so "most
    recent first" has to be total, and a monotonic sequence gives that
    for free.

    `occurred_at` is the moment the entry *names*, not the moment of the
    append: a recording's `Provenance.when`, or an approval's `when`.
    The five kinds whose command carries no
    timestamp are stamped here from the database clock, because the
    application layer holds no clock.

    `details` is JSONB for the reason `playbook_steps.timing_anchor` is:
    what every entry has in common is columns, and what distinguishes one
    kind from another differs per kind and is read only by the composer
    that already knows the kind.
    """

    __tablename__ = "launch_journal_entries"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_JOURNAL_KIND_LIST})",
            name="ck_launch_journal_entries_kind_valid",
        ),
        Index("ix_launch_journal_entries_product_id", "product_id"),
    )

    sequence: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_launch_journal_entries_product_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class AutomatedStepBackoff(Base):
    """One automated step that has stopped making progress.

    `launch-step-automation`: a handler repeating the non-terminal outcome
    its step already carries is asked no further questions for a
    cool-off, and the step is reported once. **One row carries both
    decisions** — they key on the same thing and are lifted by the same
    event, and two tables would need the same writes and could disagree.

    `noted_kind` is what makes lifting *lazy*. A row whose kind is not
    that of the step's currently recorded outcome governs nothing, so
    nothing has to remember to delete it — which is what lets
    `automation_confirmation`, which also records outcomes for these
    steps, stay untouched. Every recording surface gets this right by
    doing nothing.

    The kind, not the outcome: `Blocked` carries a reason, and an
    LLM-backed handler rewords it on every call, so a value comparison
    would find no two blocks alike and the cool-off would engage never.

    `reported_at` is stamped only after a report has actually been
    delivered — the `clickup_field_gap_suppression` discipline, for the
    same reason: this row is lifted by the step *moving*, not by Slack
    recovering, so stamping before delivery would silence the step for
    exactly as long as it stays stuck.
    """

    __tablename__ = "automated_step_backoff"
    __table_args__ = (
        CheckConstraint(
            f"noted_kind IN ({_OUTCOME_LIST})",
            name="ck_automated_step_backoff_noted_kind_valid",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_automated_step_backoff_product_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    step_id: Mapped[str] = mapped_column(String, primary_key=True)
    noted_kind: Mapped[str] = mapped_column(String, nullable=False)
    noted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlaybookStep(Base):
    """One stored step of the live launch playbook.

    `move-playbook-steps-to-postgres` moved the step set here from the
    repo-authored YAML; the framework (gates, coherence rules) stays in
    code. The definition columns mirror `StepDefinition`; the attribution
    columns carry who created, updated, retired, or un-retired the row.
    A retired row persists (retire, never delete): since
    `redesign-step-fields` what excludes it from the served playbook is
    its `status`, not the attribution — one answer to "is this step in
    play" rather than two that can disagree, while `retired_by` and its
    siblings go on recording who moved the step and when.
    `timing_anchor` is the anchor's JSON shape (`{"kind": ..., ...}`),
    exactly as the seed's source format spelled it; `assignees` is a JSON
    array of the membership's generated identifiers, never of names.
    `starts_at_gate` and `after_steps` say when the step may start
    (`let-a-step-say-when-it-starts`) and are shaped to mirror the two
    columns they most resemble: the first nullable like `handler`, since
    absent is the meaningful value "starts immediately"; the second a
    non-null JSON array defaulting to `[]` like `assignees`, since empty
    and "no dependency" are one fact and a nullable column would give
    them two spellings.
    `display_order` is the authored within-gate slot
    (`add-playbook-admin-ui`), held only by an `active` step: serving
    reads gate position, then slot, then identifier.
    """

    __tablename__ = "playbook_steps"

    identifier: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate: Mapped[str] = mapped_column(String, nullable=False)
    discipline: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(String, nullable=False)
    timing_anchor: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    hazard: Mapped[str] = mapped_column(String, nullable=False)
    assignees: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    starts_at_gate: Mapped[str | None] = mapped_column(String, nullable=True)
    after_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    handler: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmer: Mapped[str | None] = mapped_column(String, nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_id: Mapped[str | None] = mapped_column(String, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_by: Mapped[str | None] = mapped_column(String, nullable=True)
    retired_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unretired_by: Mapped[str | None] = mapped_column(String, nullable=True)
    unretired_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AutomatedStepResult(Base):
    """One result an automated step's handler produced, and what became of it.

    `launch-step-automation`: a terminal proposal on a step that needs
    confirmation is held here rather than recorded, until a member accepts
    or rejects it. A non-terminal proposal never reaches this table — it is
    recorded directly, because there is nothing in it for a member to
    accept.

    **Settled rows are kept, never deleted**, the same retire-never-delete
    discipline `playbook_steps` follows: what a member accepted, and when,
    is the record of a compliance-adjacent decision.

    `state` carries four values, and `voided` is its own rather than a
    flavour of `rejected`. A decision arriving for a step the served
    playbook no longer defines is refused and the row voided; recording
    that as a rejection would misattribute a refused decision to the member
    who made it, and — since the cool-off keys on the most recent
    *rejection* — would park the step for a further day once it returned.

    The partial unique index is the concurrency guarantee, not an
    optimisation: it is what makes "at most one pending result per step"
    true against two overlapping passes rather than only inside one pass's
    read-then-write.
    """

    __tablename__ = "automated_step_results"
    __table_args__ = (
        Index(
            "uq_automated_step_results_one_pending",
            "product_id",
            "step_id",
            unique=True,
            postgresql_where=text("state = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "launch_positions.product_id",
            name="fk_automated_step_results_product_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String, nullable=False)
    handler: Mapped[str] = mapped_column(String, nullable=False)
    proposed_outcome: Mapped[str] = mapped_column(String, nullable=False)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: The finding written when the handler ran, carried across the wait
    #: for a confirmer and onto the recording acceptance makes.
    finding: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlaybookStepSet(Base):
    """The single optimistic set-version serializing every step write.

    One row, ever: each accepted write persists conditionally on the
    version it loaded and bumps it, and the served playbook's version
    identifier derives from it — so "which definition era did this launch
    start under" moves with every accepted write.
    """

    __tablename__ = "playbook_step_set"
    __table_args__ = (CheckConstraint("id = 1", name="ck_playbook_step_set_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class LaunchGateAskSuppression(Base):
    """When a launch's gate was last asked about, or last decided against.

    At most one row per (launch, gate). It means "this gate has been put to
    a member, and the day it was put has not yet elapsed" — the whole of
    what `launch-gate-progression`'s once-a-day rule reads.

    Two writers, deliberately, where `clickup_field_gap_suppression` has
    one: a **delivery**, written only after the ask reaches Slack, and a
    **rejection**, which delivers nothing but must start the day running
    from the decision rather than from the ask that prompted it. So the
    column is named for the moment, not for the delivery — a row may
    record either.

    A table rather than process state, for the reason its predecessor
    records: a restart must not resume the flood the row exists to
    prevent.

    Not cascaded from `launch_positions` by choice. A launch deleted by
    hand — this deployment does that (`delete-test-launches.sql`) — leaves
    a row that no read can reach, since every read is keyed by a product
    the walk found; a foreign key would instead make the deletion fail or
    silently rewrite this table, and neither is worth a row nobody sees.
    """

    __tablename__ = "launch_gate_ask_suppression"
    __table_args__ = (
        CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_gate_ask_suppression_gate_valid",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    gate_id: Mapped[str] = mapped_column(String, primary_key=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
