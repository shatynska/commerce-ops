# Proposed change order

**Status: working queue.** Eight changes were proposed on 2026-09-01 from a
review of the work merged between 2026-08-28 and 2026-09-01. **Four remain.**
`restore-the-skipped-unit-tests` and `fix-launch-thread-mentions` were
implemented and archived on 2026-09-01, and
`await-the-subcategory-advisors-graph` and `inject-the-thread-anchor-poster`
on 2026-09-02; all four entries were deleted, per the rule below. The rest exist as a `proposal.md`
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

## 2. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow `defer-eager-clickup-convergence`**, which deletes eight of
those globals outright by moving convergence off the four request-path
adapters. Re-scope it on arrival rather
than executing it as written.

## 3. `unify-the-launch-advisory-locks`

`launch_advisory_lock.py` and `launch_thread_lock.py` are the same module
twice, differing in one constant — and the load-bearing docstring is already
unsynchronised between them. Merge, with the two namespaces declared together
so "these must not collide" is checkable by reading four lines.

**Order-independent.** Slot it anywhere, except concurrently with
`defer-eager-clickup-convergence`, which changes how long the advance lock is
held and by which process.

## 4. `share-the-unit-test-harness`

162,335 lines of tests against 23,629 of source, across 272 test files and
**four** `conftest.py` files. Eleven separate `_FakeSession` classes. This is
what turned one added keyword argument into the 24-test outage
`restore-the-skipped-unit-tests` cleaned up, and it is why production code
carries `getattr` tolerances for doubles that model less than their subject.

**Last**, because it touches nearly every test file and will conflict with
anything else in flight. Its precondition — `restore-the-skipped-unit-tests`
landed, so no file being migrated is one nobody has seen run — is now met.

---

## Not on this list

- **`record-review-findings-as-deferred-work`** — the branch carrying
  `docs/deferred-work.md`'s new entries and this file. Independent of
  everything; merge whenever.
- **The chore commit** — `docs/deferred-work.md`'s "Small cleanups" table,
  now eight rows. One commit, no change process, as that section says.
