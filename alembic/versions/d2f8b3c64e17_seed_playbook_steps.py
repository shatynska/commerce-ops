"""seed playbook steps from the authored v1 definitions

Revision ID: d2f8b3c64e17
Revises: c9d4e7a12f58
Create Date: 2026-08-24

The seed half of `move-playbook-steps-to-postgres`'s Migration Plan, step
2: the authored `v1` step set — transcribed row for row from
`docs/reference/product-launch.md` by earlier changes — becomes the
initial content of `playbook_steps`, exactly once.

The source is this migration's own vendored copy of the authored file,
`alembic/data/playbook_v1.yaml`, parsed here and checked structurally.
It used to be validated by constructing the domain's `LaunchPlaybook`;
`redesign-step-fields` moved that validation to the backfill revision
that rewrites these rows into the current field set — see `_validate`
below for why a migration must not depend on live domain code. The copy
is vendored (a
deliberate refinement of the change's design) because the source-tree
YAML and its loader are removed once the database owns the steps, and a
fresh environment must still be able to run this migration afterwards.

**The seed runs once.** Alembic's revision tracking is the first guard;
the emptiness check is the second: a `playbook_steps` table that already
holds rows — authored edits included — is never re-seeded and never
overwritten, so re-running the migration machinery against a populated
database changes nothing.

Seeded rows carry no authoring attribution (`created_by` et al. stay
null): their provenance is the reference-row citation each definition
already carries, and attribution begins with the first authored write.

Downgrade empties the step tables back to the schema migration's state
(version 0, no rows) — losing authored edits with the seed, the recorded
data-loss of the change's rollback plan.
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
import yaml

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f8b3c64e17"
down_revision: str | Sequence[str] | None = "c9d4e7a12f58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "playbook_v1.yaml"

_steps_table = sa.table(
    "playbook_steps",
    sa.column("identifier", sa.String),
    sa.column("description", sa.Text),
    sa.column("gate", sa.String),
    sa.column("discipline", sa.String),
    sa.column("scope", sa.String),
    sa.column("timing_anchor", sa.JSON),
    sa.column("binding", sa.String),
    sa.column("blocking", sa.Boolean),
    sa.column("execution", sa.String),
    sa.column("hazard", sa.String),
    sa.column("rule_policy", sa.Text),
    sa.column("provenance", sa.Text),
)


def _authored_rows() -> list[dict[str, object]]:
    """The authored step rows, validated through the domain before a
    single row is written."""
    document: dict[str, list[dict[str, object]]] = yaml.safe_load(
        _SEED_FILE.read_text(encoding="utf-8")
    )
    rows: list[dict[str, object]] = []
    for step in document["steps"]:
        rows.append(
            {
                "identifier": str(step["identifier"]),
                "description": str(step["description"]),
                "gate": str(step["gate"]),
                "discipline": str(step["discipline"]),
                "scope": str(step["scope"]),
                "timing_anchor": step["timing_anchor"],
                "binding": str(step["binding"]),
                "blocking": bool(step["blocking"]),
                "execution": str(step["execution"]),
                "hazard": str(step.get("hazard", "none")),
                "rule_policy": step.get("rule_policy"),
                "provenance": step.get("provenance"),
            }
        )
    _validate(rows)
    return rows


def _validate(rows: list[dict[str, object]]) -> None:
    """Structural checks only, and deliberately so.

    This validation used to construct the domain's `LaunchPlaybook` over
    the seeded rows, so that "this migration cannot insert what the
    domain would reject". A migration pinned to live domain code cannot
    survive that code changing, and `redesign-step-fields` is where it
    stopped surviving: the fields these rows carry — `binding`,
    `execution`, `rule_policy` — no longer exist on `StepDefinition`, so
    the import alone would break every fresh environment's
    `alembic upgrade head`, seeded years of history and all.

    The guarantee is not dropped, it moves: the backfill revision that
    rewrites these rows into the current field set validates the result
    through the domain, which is the first point at which the rows carry
    the fields the domain actually judges. What stays here is what a
    migration can check without reaching outside itself — that every row
    carries the keys this insert names, and that no identifier repeats.
    """
    required = (
        "identifier",
        "description",
        "gate",
        "discipline",
        "scope",
        "timing_anchor",
        "binding",
        "blocking",
        "execution",
        "hazard",
    )
    seen: set[str] = set()
    for row in rows:
        missing = [key for key in required if row.get(key) in (None, "")]
        if missing:
            raise ValueError(
                f"seed row {row.get('identifier')!r} is missing: {', '.join(missing)}"
            )
        identifier = str(row["identifier"])
        if identifier in seen:
            raise ValueError(f"seed row {identifier!r} appears twice")
        seen.add(identifier)


def upgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text("SELECT COUNT(*) FROM playbook_steps")
    ).scalar()
    if populated:
        # The seed runs once: a populated set — authored edits included —
        # is never re-seeded and never overwritten.
        return
    op.bulk_insert(_steps_table, _authored_rows())
    connection.execute(
        sa.text("UPDATE playbook_step_set SET version = version + 1 WHERE id = 1")
    )


def downgrade() -> None:
    op.execute("DELETE FROM playbook_steps")
    op.execute("UPDATE playbook_step_set SET version = 0 WHERE id = 1")
