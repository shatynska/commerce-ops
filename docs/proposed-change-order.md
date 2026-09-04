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

## 3. `share-the-value-doubles`

**In flight, largely landed.** The value half of the doubles: 166 of 186 local
declarations across seven names — `_Member` 47 and its twin `_FakeMember` 5,
`_CatalogProduct` 40, `_Record` 30, `_TaskMapping` 19, `_PendingRow` 16,
`_FakeTask` 15, `_CreatedTask` 14 — replaced by shared types in
`tests/support/values.py`.

It took this half first because the equivalence proof that caught the parent
change's defects **is** expressible here: a double with no behaviour is a value
wearing a class, and comparing two of them field-by-field is that proof written
against fields rather than `==`. It caught one real disagreement, in two files
whose `clickup_user_id` the design had recorded wrongly.

Values also come first for composition: these seven are the leaves the stateful
fakes hold, so sharing a store before sharing the member it holds would repeat
the parent change's `_hold` failure exactly.

## 4. `share-the-stateful-fakes`

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

**Must follow `share-the-value-doubles`**, which supplies the leaves its stores
hold.

**Conflict-prone**, like its predecessor: it touches many test files, so it does
not run concurrently with anything else that edits `tests/` broadly.

## 5. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow `defer-eager-clickup-convergence`**, which deletes eight of
those globals outright by moving convergence off the four request-path
adapters. Re-scope it on arrival rather
than executing it as written.

**Must also follow `share-the-value-doubles`, and `share-the-stateful-fakes`**, and this entry is placed last
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
