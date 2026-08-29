"""backfill when each stored step may start

Revision ID: d5f83b1e04a7
Revises: b4e21f9a76c8
Create Date: 2026-08-29

Step 3 of `let-a-step-say-when-it-starts`'s Migration Plan, and the one that
changes behaviour. `b4e21f9a76c8` added the columns and left every row at
"starts immediately"; this gives each stored step a start gate, which is what
stops a launch's ClickUp list opening with the whole playbook in it and stops
a handler running several gates before its work can be done.

**It covers every stored step, whatever its status, and the drafts are the
point rather than an afterthought.** Most of the stored set is `draft`
awaiting activation, and activation is a single authoring action. A draft
left declaring nothing becomes, the day someone activates it, a step eligible
in every launch at once — the exact behaviour this change removes, re-entering
by the one route a served-set-only backfill would leave open.

**The default is the step's own gate, with two exceptions.**

*A step belonging to the final gate takes `ignition`.* Its own gate is
refused as a start gate by the domain's load rules — every consumer stands
down once a launch reaches it, so a step released only there is released
where nothing will ever act on it, and the `graduated` gate's own blocking
step would make graduation impossible. Applying the plain default to those
rows would therefore produce a set the loader rejects, and no launch would be
served at all until a corrective migration. Two gates back rather than one
because gate progression advances a launch as far as its recorded state
permits within a single pass, so a one-gate window can be crossed between two
runs of the passes that act on steps. Two gates is a margin, not a guarantee.

*Seven reviewed steps take the earlier gate their calendar anchor implies.*
Their anchors fall before their own gate can plausibly be reached, which is a
disagreement between the authored calendar and the gate sequence rather than
anything a rule can derive — so each is named here with the reason. The same
measure flags sixteen more, all of them `draft`; those take the default,
because choosing a start gate for a step nobody has reviewed is an authoring
judgement made once, at activation, by a person who can see it. A too-late
value fails silently — an unreleased step is passed over without a report,
not projected, and not marked overdue — which is why this migration does not
make sixteen of them in bulk.

**Applied only where the column is null**, and keyed on identifier, so a
value an author has already set is never overwritten and a row this
migration does not know about is left alone rather than guessed at.

Downgrade returns every `starts_at_gate` to null, which is "starts
immediately" — the behaviour that stood before this change. A rollback
therefore cannot strand a launch: it can only return the system to asking for
everything at once. Authored values set after this ran are lost with it, the
same data loss the seed revision's rollback already records.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f83b1e04a7"
down_revision: str | Sequence[str] | None = "b4e21f9a76c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FINAL_GATE = "graduated"

# Two gates before the final one. Spelled as a literal rather than computed
# from the gate sequence: a migration states what it did on the day it ran,
# and must keep doing exactly that if the sequence is ever changed.
_FINAL_GATE_START = "ignition"

# The seven steps whose anchor falls before their own gate can be reached.
# Each is an authored judgement, not a derivation — see the module docstring.
_REVIEWED: dict[str, str] = {
    # `stock-ready` is not reachable before T-7; goods must be ordered
    # before they can be stocked.
    "lp.inventory.019": "order",  # first-order sizing, T-30
    "lp.inventory.008": "order",  # pre-shipment inspection, T-30
    "lp.inventory.018": "order",  # barcode TOS, T-30
    # Campaign preparation deliberately precedes going live.
    "lp.ppc.001": "listable",  # naming convention, T-14
    "lp.ppc.002": "listable",  # keyword bucketing, T-14
    "lp.ppc.004": "listable",  # search-volume ceiling, T-14
    # `listable` is itself reachable only by T-60, so releasing this one
    # there would leave it no margin against its own anchor. `order` is
    # reachable by T-90.
    "lp.ppc.003": "order",  # never-keywords list, T-60
}


def upgrade() -> None:
    connection = op.get_bind()

    # The default, and the final-gate exception, in one statement each.
    # `WHERE starts_at_gate IS NULL` is what makes this safe to re-run and
    # what protects a value an author has already chosen.
    connection.execute(
        sa.text(
            "UPDATE playbook_steps SET starts_at_gate = gate "
            "WHERE starts_at_gate IS NULL AND gate <> :final"
        ),
        {"final": _FINAL_GATE},
    )
    connection.execute(
        sa.text(
            "UPDATE playbook_steps SET starts_at_gate = :start "
            "WHERE starts_at_gate IS NULL AND gate = :final"
        ),
        {"start": _FINAL_GATE_START, "final": _FINAL_GATE},
    )

    # The reviewed exceptions last, so each overrides the default it would
    # otherwise have taken. Still guarded on the identifier existing: a row
    # this migration names and the database does not carry is skipped, not
    # invented.
    for identifier, start_gate in _REVIEWED.items():
        connection.execute(
            sa.text(
                "UPDATE playbook_steps SET starts_at_gate = :start "
                "WHERE identifier = :identifier"
            ),
            {"start": start_gate, "identifier": identifier},
        )


def downgrade() -> None:
    op.execute("UPDATE playbook_steps SET starts_at_gate = NULL")
