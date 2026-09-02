"""Rename the roster tables to members.

`rename-the-roster-to-members`: the people directory's vocabulary settles on
`members`, and the two tables follow it.

A rename, not a drop-and-recreate. `docs/playbook-program.md` licenses
dropping tables outright -- production data is test data -- and this change
declines the licence: these `ALTER`s are exactly reversible, read and move no
row, and read in the migration as what they are. Dropping and recreating
would be a larger, less reversible operation performing a rename, and would
make this the one change in the program that destroys data without needing
to (`design.md` section 4).

Rollback is ordered: run the downgrade BEFORE deploying the reverted image.
Taken the other way round, the reverted image no longer carries this file,
the database sits at a revision the tree cannot resolve, `alembic upgrade
head` fails at container start and the container never becomes healthy --
the shape of the 2026-08 `BOOTSTRAP_ADMIN_IDENTITY` failure `AGENTS.md`
records.

Revision ID: f4b7c1e09d52
Revises: c04d95ba6e31
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f4b7c1e09d52"
down_revision: str | Sequence[str] | None = "c04d95ba6e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("roster_people", "members")
    op.rename_table("roster_set", "members_set")
    # Postgres renames neither the constraints a table carries nor the
    # sequence it owns when the table is renamed, so a schema left here would
    # hold `roster_people_pkey` ON a table called `members` -- the same
    # vocabulary mismatch as the `<h1>Users</h1>` over a `roster` spec that
    # this change exists to end, one layer down. Nothing in the application
    # names any of these (SQLAlchemy declares only the check constraint), so
    # renaming them is free and finishes the job.
    op.execute(
        "ALTER TABLE members_set "
        "RENAME CONSTRAINT ck_roster_set_singleton TO ck_members_set_singleton"
    )
    op.execute(
        "ALTER TABLE members RENAME CONSTRAINT roster_people_pkey TO members_pkey"
    )
    op.execute(
        "ALTER TABLE members "
        "RENAME CONSTRAINT roster_people_slack_identity_key "
        "TO members_slack_identity_key"
    )
    op.execute(
        "ALTER TABLE members_set RENAME CONSTRAINT roster_set_pkey TO members_set_pkey"
    )
    op.execute("ALTER SEQUENCE roster_set_id_seq RENAME TO members_set_id_seq")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE members_set_id_seq RENAME TO roster_set_id_seq")
    op.execute(
        "ALTER TABLE members_set RENAME CONSTRAINT members_set_pkey TO roster_set_pkey"
    )
    op.execute(
        "ALTER TABLE members "
        "RENAME CONSTRAINT members_slack_identity_key "
        "TO roster_people_slack_identity_key"
    )
    op.execute(
        "ALTER TABLE members RENAME CONSTRAINT members_pkey TO roster_people_pkey"
    )
    op.execute(
        "ALTER TABLE members_set "
        "RENAME CONSTRAINT ck_members_set_singleton TO ck_roster_set_singleton"
    )
    op.rename_table("members_set", "roster_set")
    op.rename_table("members", "roster_people")
