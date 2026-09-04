# Proposed change order

**Status: working queue.** Eight changes were proposed on 2026-09-01 from a
review of the work merged between 2026-08-28 and 2026-09-01. **Three remain.**
`restore-the-skipped-unit-tests` and `fix-launch-thread-mentions` were
implemented and archived on 2026-09-01, and
`await-the-subcategory-advisors-graph` and `inject-the-thread-anchor-poster`
on 2026-09-02, and `share-the-unit-test-harness` on 2026-09-04; all five
entries were deleted, per the rule below. The rest exist as a `proposal.md`
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

## 3. `share-the-test-doubles`

The half of `share-the-unit-test-harness` that was cut from it: **455 fake
declarations across 18 names** — `_Member` (47), `_FakeMembers` (43),
`_FakeMembersStore` (38), `_FakeStepStore` (37), `_CatalogProduct` (40) and
their neighbours. Proposed 2026-09-04 from that change's own implementation,
not from the 2026-09-01 review that produced the rest of this queue.

**Why it was cut rather than finished.** The harness change migrated `_step`
whole (135 of 135) but reached only 31 of 104 `_hold` and 13 of 95 `_playbook`,
because both compose *over* `_step`: a local helper built on a customised step
is not reproducible by a shared one built on the canonical step, however the
deltas are forwarded. The fakes are that problem with less protection —
`FakeStepStore() == FakeStepStore()` is identity, so the per-file equivalence
proof that caught **five** real defects during the harness migration, every one
of them leaving assertions textually identical and the suite green, cannot be
expressed for them at all.

**So its design must start from composition**, not discover it: how a shared
fake held by a shared store held by a shared session stays reproducible, and
what stands in for an equality proof when `==` is identity. `AGENTS.md`'s
"The shared harness" section already records the rules it is held to, including
the same-value invariant that stops a *complete* double redirecting a production
shape probe.

**Conflict-prone**, for the same reason its parent was: it touches many test
files, so it does not run concurrently with anything else that edits `tests/`
broadly. It is **not** order-independent, though its parent's entry said so:
`unify-launch-adapter-dependencies` must follow it, which is why that entry now
sits last. `docs/deferred-work.md`'s tolerance entry does not close behind this
change either — these slices make the deletion safe and
`unify-launch-adapter-dependencies` performs it.

## 4. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow `defer-eager-clickup-convergence`**, which deletes eight of
those globals outright by moving convergence off the four request-path
adapters. Re-scope it on arrival rather
than executing it as written.

**Must also follow `share-the-value-doubles`**, and this entry is placed last
for that reason rather than by preference. Deleting the member-identifier
probe is only safe once every member double supplies `identifier`: measured
2026-09-04, `src/` carries six copies of that probe and all 52 member doubles
in `tests/` spell the field `id` alone, so deleting the `id` branch first
fails them all. `share-the-value-doubles` supplies the spelling and
`share-the-stateful-fakes` finishes the population; this change is what
performs the deletion. The probe surface is ten `getattr` shape probes in
total — `docs/deferred-work.md` records three — and two of the ten are reader
shapes rather than attribute spellings, so re-measure by shape before
deleting anything.

---

## Not on this list

- **`record-review-findings-as-deferred-work`** — the branch carrying
  `docs/deferred-work.md`'s new entries and this file. Independent of
  everything; merge whenever.
- **The chore commit** — `docs/deferred-work.md`'s "Small cleanups" table,
  now eight rows. One commit, no change process, as that section says.
