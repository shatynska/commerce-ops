# Proposed change order

**Status: working queue.** Eight changes were proposed on 2026-09-01 from a
review of the work merged between 2026-08-28 and 2026-09-01. **Three remain**,
one of which was not among the eight. `restore-the-skipped-unit-tests` and
`fix-launch-thread-mentions` were implemented and archived on 2026-09-01, and
`await-the-subcategory-advisors-graph` and `inject-the-thread-anchor-poster`
on 2026-09-02, and `share-the-unit-test-harness` and its first follow-up
`share-the-value-doubles` on 2026-09-04; all six entries were deleted, per the
rule below. `share-the-stateful-fakes` is the second half of that follow-up and
is the entry here that the 2026-09-01 review did not produce. The rest exist as a `proposal.md`
on their own branch and are unimplemented — except where one is in flight,
which this file does not track, since a queue that also tracked progress
would need updating twice. This document records the order
they should be worked in and the dependencies between them, because that
ordering is a real constraint and it lives nowhere else — a proposal states
its own sequencing notes, but nothing reads all of them together.

Entries are renumbered when one is deleted, so **cross-references between them
are by name**, not by number: a number is only a position in the current
queue.

**Delete an entry when its change is archived.** Delete this file when the
last one is. A queue that outlives its work is worse than no queue, which is
`docs/deferred-work.md`'s rule and applies here for the same reason.

Findings from the same review that are **not** changes — a silent finding
drop, the tolerances production code carries for incomplete test doubles, a
hand-invented migration id that must not be corrected, and six one-line
cleanups — are in `docs/deferred-work.md` instead.

Each change lives on a branch named for it, carrying one commit with its
`proposal.md` and `.openspec.yaml`. Nothing is pushed. Per `AGENTS.md`, work
on one means: check out its branch, dispatch
`ai-toolkit:openspec-change-reviewer` against the proposal, write the delta
specs, re-review until approved, then `ai-toolkit:openspec-test-writer`
before any code is applied.

---

## 1. `defer-eager-clickup-convergence`

`converge_launch_eagerly` holds a database connection open across the entire
ClickUp conversation — and `retry-clickup-rate-limits` adds up to ~30 s of
sleep per request on a `429`. Two connections at three of the four sites, out
of a default pool of 15, on the request path, with the correlated failure
being exactly the ClickUp slowdown that motivated the eager path in the first
place. Moves it onto `procrastinate` and collapses the four duplicated
trigger blocks into one.

**Carries a real design decision** — queue, per-product dedup, retry policy,
and whether its runs belong in `scheduled-jobs`' freshness history at all.
Worth `/openspec-explore` before `design.md`.

## 2. `unify-the-launch-advisory-locks`

`launch_advisory_lock.py` and `launch_thread_lock.py` are the same module
twice, differing in one constant — and the load-bearing docstring is already
unsynchronised between them. Merge, with the two namespaces declared together
so "these must not collide" is checkable by reading four lines.

**Order-independent.** Slot it anywhere, except concurrently with
`defer-eager-clickup-convergence`, which changes how long the advance lock is
held and by which process.

## 3. `share-the-stateful-fakes`

The other half: the doubles with behaviour — `_FakeMembers` 43,
`_FakeMembersStore` 38, `_FakeStepStore` 37, `_FakeLaunches` and `_FakePlaybooks`
32 each, and their neighbours. For these `==` is identity, so the proof above is
inexpressible and the weaker substitute applies: `_conforms` typing plus a
per-fake surface-and-behaviour note, which explicitly does *not* catch "same
surface, different behaviour".

**Brings `tests/unit/support/` with it**, for the shared fakes' own behaviour
tests — a deliberate exception to the tier layout, and the only proposed thing
that reaches the same-surface-different-behaviour risk. It is collected, unlike
`tests/support/`, so it is the one slice whose collected count moves.

**`share-the-value-doubles` landed first** (archived 2026-09-04) and supplies
the leaves these stores hold: `Member`, `CatalogProduct`, `Record`,
`TaskMapping`, `PendingRow`, `FakeTask`, `CreatedTask` in
`tests/support/values.py`. A shared store holding *shared* members is
reproducible across files; one holding each file's own is the parent change's
`_hold` problem again. Whether that ordering was worth it is testable rather
than assumed: if these stores still cap at a partial hit rate, partition the
findings on whether the file's leaf migrated — the claim is only about the
migrated partition.

**Conflict-prone**, like its predecessor: it touches many test files, so it does
not run concurrently with anything else that edits `tests/` broadly.

## 4. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow `defer-eager-clickup-convergence`**, which deletes eight of
those globals outright by moving convergence off the four request-path
adapters. Re-scope it on arrival rather
than executing it as written.

**Must also follow `share-the-stateful-fakes`**, and this entry is placed last
for that reason rather than by preference.

The member-identifier half of its warrant is already met.
`share-the-value-doubles` (archived 2026-09-04) gave all 52 member doubles an
`identifier`, so the second and third branches of all six member-identifier
probes are now unreachable from any test — proven there by mutation. What is
*not* yet met is `clickup_sync._members`, which probes three reader shapes and
sits opposite the stateful `FakeMembers` this change must wait for.

Two cautions carried from that work. The probe surface is **ten** `getattr`
shape probes, and `docs/deferred-work.md` now records the measurement *method*
beside them, because every spelling-based sweep of this ground has come back
stale — re-measure structurally, and note that two of the ten are reader shapes
rather than attribute spellings and so fall outside that measurement entirely.
And the six member probes' fall-through branches are currently *untested*
rather than unused: **do not narrow one on the strength of a green suite** until
this change deletes it deliberately.

---

## Not on this list

- **`record-review-findings-as-deferred-work`** — the branch carrying
  `docs/deferred-work.md`'s new entries and this file. Independent of
  everything; merge whenever.
- **The chore commit** — `docs/deferred-work.md`'s "Small cleanups" table,
  now eight rows. One commit, no change process, as that section says.
