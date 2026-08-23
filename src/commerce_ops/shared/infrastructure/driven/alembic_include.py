"""Driven adapter: the autogenerate exclusion for the job runner's schema.

`alembic/env.py` sets `target_metadata = Base.metadata`, and that metadata
describes this project's own models only. The runner's tables exist in the
database and in no metadata, so without a filter the next
`alembic revision --autogenerate` -- run months from now, for an unrelated
feature -- emits `op.drop_table` for every one of them, destroying the run
history that `scheduled-jobs` requires to survive its process.

This predicate lives here rather than in `alembic/env.py` because that file
has no package around it and calls `context.config` in its module body, so a
predicate defined there could not be unit-tested. `env.py` already imports
from `commerce_ops`, so the precedent exists. See design.md, "a hazard that
neither branch avoids", and tasks.md 1.6a.
"""

from __future__ import annotations

from typing import Any

from alembic.runtime.environment import NameFilterParentNames, NameFilterType

# Every table the runner creates carries this prefix. A prefix rather than a
# transcribed list, so a runner upgrade that adds a table is excluded the
# moment it is installed rather than the next time someone remembers.
RUNNER_TABLE_PREFIX = "procrastinate_"


def include_name(
    name: str | None,
    type_: NameFilterType,
    parent_names: NameFilterParentNames,
) -> bool:
    """Alembic's name filter: False excludes a name from the comparison.

    Only tables are filtered. Autogenerate compares tables, columns, indexes
    and constraints -- it does not emit drops for functions, triggers or enum
    types -- so excluding the runner's tables and what hangs off them covers
    the whole hazard. That is also the criterion for reading tasks.md 1.8's
    empirical run as clean.
    """
    return not (
        type_ == "table" and name is not None and name.startswith(RUNNER_TABLE_PREFIX)
    )


def include_object(
    object_: Any,
    name: str | None,
    type_: NameFilterType,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """The same exclusion under Alembic's other filter hook.

    Offered so `env.py` may pass either one; both are acceptable per
    design.md. Kept a thin delegation so the two cannot disagree.
    """
    return include_name(name, type_, {})
