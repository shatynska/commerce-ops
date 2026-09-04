"""Shared test arrangement, imported by all three tiers.

Deliberately empty. Modules here are imported by path --
`from tests.support.playbook import SPECIFIED_GATE_ORDER` -- and never
re-exported from this file, so the package cannot become one namespace
everything pulls from and a reader can tell what a test arranges with by
reading its imports.

`tests/support/` is imported, never run: `testpaths` names the three tiers, as
do every pre-commit hook and CI step, so nothing collects this directory.

**The shared fakes are not here yet.** This package carries the gate
specification, the HTML harness, the admin session, the fixed fixtures and the
step builder. The fakes -- `FakeMembers`, `FakeStepStore` and their neighbours,
455 local declarations across the suite -- were cut from
`share-the-unit-test-harness` to a follow-up, because their `==` is identity and
the equality proof the value builders were migrated under cannot be expressed
for them. When they land they bring `tests/unit/support/` with them, for their
own behaviour tests, which must be collected.
"""
