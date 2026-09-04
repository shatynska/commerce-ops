"""Shared test arrangement, imported by all three tiers.

Deliberately empty. Modules here are imported by path --
`from tests.support.playbook import SPECIFIED_GATE_ORDER` -- and never
re-exported from this file, so the package cannot become one namespace
everything pulls from and a reader can tell what a test arranges with by
reading its imports.

`tests/support/` is imported, never run: `testpaths` names the three tiers, as
do every pre-commit hook and CI step, so nothing collects this directory.

**Both kinds are here.** `values.py` holds the doubles that only carry fields
-- `Member`, `MemberValue`, `CatalogProduct`, `Record`, `TaskMapping`,
`PendingRow`, `FakeTask`, `CreatedTask`, from `share-the-value-doubles`
(2026-09-04), replacing 166 local declarations. `fakes.py` holds the ones with
behaviour -- `FakeMembers`, `FakeMembersStore`, `FakeStepStore`,
`FakeCatalogPort`, `FakeHandlers`, `FakeHandlerRegistry`, `FakeSlackResponse`,
`StubDate`, `InertBackoff`, from `share-the-stateful-fakes` (2026-09-04),
replacing 175 of 191 declarations across 103 files.

**The two were migrated under different proofs, for a reason worth keeping.**
A value double's equivalence is expressible field-wise; a stateful fake's is
not, since `FakeStepStore() == FakeStepStore()` is identity. So the fakes were
migrated under a *lockstep pairing* instead -- local and shared driven side by
side, comparing return value, exception and state on every executed call --
which reached 115 of the 175 declarations. `AGENTS.md`'s harness section records
the four things such a proof cannot see, and they are worth reading before the
next fake is shared.

**~291 declarations in the recurring names are still local**, mostly the launch,
playbook and catalog stores. They are blocked on the same rule that ordered
these two changes: share the base before the composer, and `_playbook()` and
`_hold()` are not shared yet.

`tests/unit/support/` holds these fakes' own behaviour tests and *is* collected,
unlike this package.
"""
