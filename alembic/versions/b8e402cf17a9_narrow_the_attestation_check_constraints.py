"""narrow the two check constraints attestation widened

Revision ID: b8e402cf17a9
Revises: f3a71c58b0d2
Create Date: 2026-09-01

`replace-metric-conditions-with-steps` removes metric attestation. Two
CHECK constraints still name it, and neither follows from the model
definition alone -- a constraint on an existing table changes only by an
`ALTER`:

- `launch_step_progress.source` admits `attestation`, which
  `PROVENANCE_SOURCES` no longer lists. A source names the channel an
  outcome arrived through, and that channel no longer exists.
- `launch_journal_entries.kind` admits `metric-attested`, which
  `LAUNCH_JOURNAL_KINDS` no longer lists. No entry of that kind was ever
  appended, the command having had no surface.

Narrowing rather than leaving them permissive: a constraint wider than
the code is a constraint that stops describing the table, and the whole
point of holding these lists in one place is that the schema and the
model agree about what a column may hold.

**This migration will fail if either value is still stored.** That is
deliberate and is the safety property: a row carrying `attestation` as
its source is a recorded outcome this change has no account of, and
discovering it by a refused migration is better than discovering it by
its absence from a later report. Rows written by the integration tier
count -- a local database seeded by test fixtures has to be cleaned, or
recreated, before it will take this.

Downgrade re-widens both constraints, restoring exactly the values that
were admitted before.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e402cf17a9"
down_revision: str | Sequence[str] | None = "f3a71c58b0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOURNAL_KINDS_AFTER = (
    "launch-started",
    "step-outcome-recorded",
    "gate-approval-recorded",
    "gate-opened",
    "launch-graduated",
    "launch-date-moved",
    "advance-refused",
)
_JOURNAL_KINDS_BEFORE = (
    *_JOURNAL_KINDS_AFTER[:2],
    "metric-attested",
    *_JOURNAL_KINDS_AFTER[2:],
)

_SOURCES_AFTER = ("clickup", "automated")
_SOURCES_BEFORE = (*_SOURCES_AFTER, "attestation")


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace(table: str, name: str, column: str, values: Sequence[str]) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"{column} IN ({_in_list(values)})")


def upgrade() -> None:
    _replace(
        "launch_step_progress",
        "ck_launch_step_progress_source_valid",
        "source",
        _SOURCES_AFTER,
    )
    _replace(
        "launch_journal_entries",
        "ck_launch_journal_entries_kind_valid",
        "kind",
        _JOURNAL_KINDS_AFTER,
    )


def downgrade() -> None:
    _replace(
        "launch_step_progress",
        "ck_launch_step_progress_source_valid",
        "source",
        _SOURCES_BEFORE,
    )
    _replace(
        "launch_journal_entries",
        "ck_launch_journal_entries_kind_valid",
        "kind",
        _JOURNAL_KINDS_BEFORE,
    )
