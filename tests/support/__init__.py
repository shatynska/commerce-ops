"""Shared test arrangement, imported by all three tiers.

Deliberately empty. Modules here are imported by path --
`from tests.support.playbook import SPECIFIED_GATE_ORDER` -- and never
re-exported from this file, so the package cannot become one namespace
everything pulls from and a reader can tell what a test arranges with by
reading its imports.

`tests/support/` is imported, never run: `testpaths` names the three tiers, as
do every pre-commit hook and CI step, so nothing collects this directory.

**The value doubles are here; the stateful fakes are not.**
`share-the-value-doubles` (2026-09-04) landed `values.py` -- `Member`,
`MemberValue`, `CatalogProduct`, `Record`, `TaskMapping`, `PendingRow`,
`FakeTask`, `CreatedTask` -- replacing 166 local declarations.

What remains deferred to `share-the-stateful-fakes` is the doubles with
*behaviour*: `FakeMembers`, `FakeStepStore`, `FakeMembersStore` and their
neighbours, ~355 declarations. Their `==` is identity, so the equivalence proof
the value builders were migrated under cannot be expressed for them. **That
reason is specific to them and was once stated of the whole population, which
was wrong**: a double with no behaviour is a value wearing a class, and
comparing two of them field-by-field is the same proof written against fields
rather than `==`. It is what the value doubles migrated under, and it caught a
real disagreement two files carried.

When the stateful fakes land they bring `tests/unit/support/` with them, for
their own behaviour tests, which must be collected.
"""
