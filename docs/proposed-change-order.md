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

## 3. `share-the-aggregate-fakes` (not yet proposed)

**The third slice, and it has no proposal yet.**
`share-the-stateful-fakes` (2026-09-04) took nine names — 175 of 191
declarations across 103 files — and left **291 of the 482 declarations in the 27
recurring names** untouched. The largest group is the launch, playbook and
catalog stores: `_FakePlaybooks` 32, `_FakeLaunches` 32, `_FakeCatalog` 29,
`_FakeLaunchStore` 26, `_FakePlaybookRepository` 10.

**They are blocked on the same rule that ordered the first two slices**: share
the base before the composer. Each returns a per-file aggregate built by a local
`_playbook()` or `_hold()` helper, of which `share-the-unit-test-harness`
reproduced 13 of 95 and 31 of 104 — so a shared store would have to be told what
to serve, at call sites the migration may not edit. **Sharing `_playbook()` and
`_hold()` is the prerequisite, and no proposed change owns it.**

That rule was tested rather than assumed, and it held: of the 175 migrated
declarations, the one whose lockstep pairing failed for a leaf reason —
`test_launch_report_step_facts.py` — is the one file that kept its own `_Record`
instead of the shared one.

`tests/unit/support/` already exists, with 46 tests, so this slice inherits a
place for contract tests rather than an argument about whether they belong.

**Conflict-prone**, like both predecessors: it will touch many test files, so it
does not run concurrently with anything else that edits `tests/` broadly.

## 4. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow `defer-eager-clickup-convergence`**, which deletes eight of
those globals outright by moving convergence off the four request-path
adapters. Re-scope it on arrival rather
than executing it as written.

**No longer waits on the fakes.** `share-the-stateful-fakes` archived on
2026-09-04, so both halves of its warrant are now met as far as they can be by
sharing doubles; what remains open is stated in the cautions below and is a
matter for this change's own mutation work, not for another slice.

The member-identifier half of its warrant is already met.
`share-the-value-doubles` (archived 2026-09-04) gave all 52 member doubles an
`identifier`, so the second and third branches of all six member-identifier
probes are now unreachable from any test — proven there by mutation. What is
*not* yet met is `clickup_sync._members`, which probes three reader shapes and
sits opposite the stateful `FakeMembers` this change must wait for.

Three cautions carried from that work. The probe surface is **ten** `getattr`
shape probes **plus five sites a spelling sweep cannot see at all** —
`docs/deferred-work.md` records all fifteen and, more usefully, the measurement
*method* for each kind, because every spelling-based sweep of this ground has
come back stale.

And the narrowing `share-the-stateful-fakes` delivered is uneven, deliberately.
**The handler-name side is closed from `tests/`**: all 20 doubles present
`names()` alone, established by mutating every local `__iter__` to raise and
finding the commit tier still green. **The members side is not.** 41 of 43
`_FakeMembers` present `list_members()` alone, but 23 module-level `_members()`
functions, five `_ReaderMembers`, `_StoreShapedMembers`, `_Members`,
`_FailingMembers`, two `_PlaybookMembers` and two keeps still supply the callable
and iterable conventions. So `clickup_sync._members` and
`activation_readiness._members_of` keep all three branches reachable.

The standing rule applies to every one of the fifteen: the fall-through branches
are *untested* rather than unused, and **do not narrow one on the strength of a
green suite** until this change deletes it deliberately.

---

## Not on this list

- **`record-review-findings-as-deferred-work`** — the branch carrying
  `docs/deferred-work.md`'s new entries and this file. Independent of
  everything; merge whenever.
- **The chore commit** — `docs/deferred-work.md`'s "Small cleanups" table,
  now eight rows. One commit, no change process, as that section says.
