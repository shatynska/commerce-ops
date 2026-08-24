"""seed playbook steps from the authored v1 definitions

Revision ID: d2f8b3c64e17
Revises: c9d4e7a12f58
Create Date: 2026-08-24

The seed half of `move-playbook-steps-to-postgres`'s Migration Plan, step
2: the authored `v1` step set — transcribed row for row from
`docs/reference/product-launch.md` by earlier changes — becomes the
initial content of `playbook_steps`, exactly once.

The source is this migration's own vendored copy of the authored file,
`alembic/data/playbook_v1.yaml`, parsed here and validated by
constructing the domain's `LaunchPlaybook` over `framework_gates()` —
the same rulebook every load and every write applies, so this migration
cannot insert what the domain would reject. The copy is vendored (a
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


def _as_mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _validate(rows: list[dict[str, object]]) -> None:
    """Construct the served playbook the seed would produce; the domain's
    `InvalidPlaybookError` — every fault at once — aborts the migration."""
    from commerce_ops.launch.domain.launch_playbook import (
        Binding,
        Cadence,
        ExecutionMode,
        Hazard,
        LaunchPlaybook,
        OffsetAnchor,
        OpenEndedAnchor,
        RecurringAnchor,
        Scope,
        StepDefinition,
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
        return RecurringAnchor(cadence=Cadence(raw["cadence"]))

    definitions = tuple(
        StepDefinition(
            identifier=str(row["identifier"]),
            description=str(row["description"]),
            gate=str(row["gate"]),
            discipline=Discipline(str(row["discipline"])),
            scope=Scope(str(row["scope"])),
            timing_anchor=anchor(_as_mapping(row["timing_anchor"])),  # type: ignore[arg-type]
            binding=Binding(str(row["binding"])),
            blocking=bool(row["blocking"]),
            execution=ExecutionMode(str(row["execution"])),
            hazard=Hazard(str(row["hazard"])),
            rule_policy=(
                str(row["rule_policy"]) if row["rule_policy"] is not None else None
            ),
            provenance=(
                str(row["provenance"]) if row["provenance"] is not None else None
            ),
        )
        for row in rows
    )
    LaunchPlaybook(version="seed", gates=framework_gates(), steps=definitions)


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
