"""Shared test arrangement, imported by all three tiers.

Deliberately empty. Modules here are imported by path --
`from tests.support.playbook import SPECIFIED_GATE_ORDER` -- and never
re-exported from this file, so the package cannot become one namespace
everything pulls from and a reader can tell what a test arranges with by
reading its imports.

`tests/support/` is imported, never run: `testpaths` names the three tiers, as
do every pre-commit hook and CI step, so nothing collects this directory. The
shared fakes' own behaviour tests live in `tests/unit/support/`, which is
collected.
"""
