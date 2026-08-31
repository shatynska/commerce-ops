"""backfill the redesigned step fields over the seeded set

Revision ID: b8e5c04a1d39
Revises: c3a1f74d8b26
Create Date: 2026-08-25

Step 2 of `redesign-step-fields`'s Migration Plan, written as that plan
states it rather than as the obvious column-for-column mapping would.
Three of its decisions are not mechanical, and each is here on purpose:

- `name` <- `description`, and `description` <- null. The reference row's
  text is one line stating the work, which is what a name is; a
  description is what an author adds later when the line is not enough.
  Copying the text into both would double every projected task's body.

- `status`: `active` for live `human` rows, so the served set is what it
  was; `in-development` for the two `automated` rows, because no runtime
  registers a handler for them and `active` would claim something
  resolves them; `retired` wherever the attribution records a retirement,
  since the status is now the single answer to "is this step in play".
  Neither automated row blocks a gate, so the gate-holding floor — which
  now counts only `active` blocking steps — is unaffected.

- `automation_brief` <- `rule_policy` **only for rows becoming
  `automated`**, and null on `human` rows. Copying it unconditionally
  would leave 95 human steps carrying a brief, which the coherence rules
  forbid: the result would not load at all.

`assignees` is left empty deliberately. The 95 migrated human steps are
active and unowned, and the readiness report says so; backfilling the
roster's only person would make that report claim the work is owned when
nobody has accepted it, which is the honest signal this change exists to
produce.

The result is validated by constructing the domain's `LaunchPlaybook`
over `framework_gates()` — the same rulebook every load and every write
applies. That validation lives here rather than in the seed revision
because this is the first point at which the rows carry the fields the
domain judges; see that revision's `_validate` for why a migration must
not otherwise depend on live domain code.

Downgrade clears the backfilled columns and restores each row's text to
`description`, which is where the still-present `binding` / `execution` /
`rule_policy` columns leave the previous image able to read it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e5c04a1d39"
down_revision: str | Sequence[str] | None = "c3a1f74d8b26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL = """
UPDATE playbook_steps
SET name = description,
    description = NULL,
    kind = CASE
        WHEN execution = 'human-attested' THEN 'human'
        ELSE 'automated'
    END,
    needs_confirmation = (execution = 'ai-assisted'),
    status = CASE
        WHEN retired_by IS NOT NULL AND unretired_by IS NULL THEN 'retired'
        WHEN execution = 'human-attested' THEN 'active'
        ELSE 'in-development'
    END,
    automation_brief = CASE
        WHEN execution = 'human-attested' THEN NULL
        ELSE rule_policy
    END,
    handler = NULL,
    assignees = '[]'::jsonb
WHERE name IS NULL
"""

# A step holds a slot only while it is `active`; the two rows dropping to
# `in-development` give theirs up, and a retired row never held one.
_CLEAR_SLOTS = """
UPDATE playbook_steps SET display_order = 0 WHERE status <> 'active'
"""

_REQUIRED = ("name", "kind", "needs_confirmation", "status", "assignees")


def upgrade() -> None:
    op.execute(_BACKFILL)
    op.execute(_CLEAR_SLOTS)
    for column in _REQUIRED:
        op.alter_column("playbook_steps", column, nullable=False)
    _validate_backfilled_set()


def downgrade() -> None:
    op.execute(
        """
        UPDATE playbook_steps
        SET description = name
        WHERE description IS NULL
        """
    )
    for column in _REQUIRED:
        op.alter_column("playbook_steps", column, nullable=True)
    op.execute(
        """
        UPDATE playbook_steps
        SET name = NULL,
            kind = NULL,
            needs_confirmation = NULL,
            status = NULL,
            assignees = NULL,
            automation_brief = NULL,
            handler = NULL
        """
    )


def _validate_backfilled_set() -> None:
    """Construct the playbook the backfill produced; the domain's
    `InvalidPlaybookError` — every fault at once — aborts the migration
    rather than leaving a set nothing can serve."""
    from commerce_ops.launch.domain.launch_playbook import (
        Cadence,
        Hazard,
        LaunchPlaybook,
        OffsetAnchor,
        OpenEndedAnchor,
        RecurringAnchor,
        Scope,
        StepDefinition,
        StepKind,
        StepStatus,
        WindowAnchor,
        framework_gates,
    )
    from commerce_ops.shared.domain.discipline import Discipline

    def as_int(value: object) -> int:
        assert isinstance(value, int)
        return value

    def anchor(raw: dict[str, object]) -> object:
        kind = raw["kind"]
        if kind == "offset":
            return OffsetAnchor(days=as_int(raw["days"]))
        if kind == "window":
            return WindowAnchor(start=as_int(raw["start"]), end=as_int(raw["end"]))
        if kind == "open-ended":
            return OpenEndedAnchor(start=as_int(raw["start"]))
        return RecurringAnchor(cadence=Cadence(str(raw["cadence"])))

    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT identifier, name, description, gate, discipline, scope,
                       timing_anchor, blocking, kind, needs_confirmation,
                       status, hazard, assignees, automation_brief, handler,
                       provenance
                FROM playbook_steps
                """
            )
        )
        .mappings()
        .all()
    )
    definitions = tuple(
        StepDefinition(
            identifier=row["identifier"],
            name=row["name"],
            description=row["description"],
            gate=row["gate"],
            discipline=Discipline(row["discipline"]),
            scope=Scope(row["scope"]),
            timing_anchor=anchor(row["timing_anchor"]),  # type: ignore[arg-type]
            blocking=row["blocking"],
            kind=StepKind(row["kind"]),
            status=StepStatus(row["status"]),
            hazard=Hazard(row["hazard"]),
            assignees=tuple(row["assignees"] or ()),
            handler=row["handler"],
            provenance=row["provenance"],
        )
        for row in rows
    )
    LaunchPlaybook(version="backfill", gates=framework_gates(), steps=definitions)
