# Proposed change order

**Status: working queue.** Eight changes were proposed on 2026-09-01 from a
review of the work merged between 2026-08-28 and 2026-09-01. Each exists as a
`proposal.md` on its own branch and **none is implemented**. This document
records the order they should be worked in and the dependencies between them,
because that ordering is a real constraint and it lives nowhere else — a
proposal states its own sequencing notes, but nothing reads all eight
together.

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

## 1. `fix-launch-thread-mentions`

Three live defects shipped by `thread-launch-slack-notifications`:

- `resolve_mention_target` returns `step.confirmer` — a roster identifier,
  generated as a `uuid4` — where every caller interpolates it as `<@…>`.
  Pending-result asks and stuck-step reports therefore notify nobody. It must
  resolve through the roster to `Person.slack_identity`. The gate ask is
  unaffected: it passes `step=None` and falls through to `launch.submitter`,
  which genuinely is a Slack identity.
- `str(product_id)` renders `ProductId(value='…')` into the thread anchor
  (`automation_confirmation.py:166`, `automation_pass.py:595`), and
  `launch-instance` requires the anchor never to be re-posted — so it is
  permanent.
- A started launch's confirmation is now thread-only, inside a swallowing
  `except`. A thread failure leaves the submitter told nothing, while the
  *failure* path still always reaches them.

**First**, because it is the only item on this list where the harm is
happening now.

## 2. `restore-the-skipped-unit-tests`

Two duplicated autouse fixtures skip seven whole files — 44 tests — under the
reason *"Unit test requires database"*, which is false for 42 of them. Of the
44: **18 pass untouched**, **24** fail only because
`test_automation_pass_repeat_backoff.py`'s `_run_pass` (`:1146-1183`) was
never told about the `establish_thread` argument, and **2** genuinely reach a
database.

**Second**, because every later change on this list is verified by this
suite, and right now the whole of `launch-step-automation`'s backoff and
stuck-step behaviour — and Slack request-signature verification, which is in
the passing 18 — runs unchecked on every commit and in CI.

## 3. `inject-the-thread-anchor-poster`

`launch/application/thread_establishment.py` builds its own
`slack_sdk.AsyncWebClient`, reads a credential from the environment, and
types a parameter `AsyncSession` — while the module beneath it documents that
the application layer takes its collaborators as ports for exactly that
reason. `import-linter` passes because its contracts govern edges inside
`commerce_ops`, not third-party imports. Also moves anchor composition out of
the four call sites that each assemble it from whatever they happen to hold.

**Third**, because it retires the last 2 skips from #2 and removes the
*class* of defect that #1 patches instance by instance.

## 4. `await-the-subcategory-advisors-graph`

`advise_sub_category` is `async def`, and calls LangGraph's **synchronous**
`invoke` underneath — so the only shipped handler blocks the worker's event
loop for the whole OpenAI round-trip. Adds the obligation to
`launch-step-automation` so the next handler cannot reintroduce it, since the
`StepHandler` type cannot express it and `ruff`'s `ASYNC` rules do not catch
it.

**Fourth**, but genuinely order-independent — it touches nothing the others
touch. Move it earlier if a small, self-contained one is wanted.

## 5. `defer-eager-clickup-convergence`

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

## 6. `unify-launch-adapter-dependencies`

One dependencies object per process, replacing 11 mutable module globals, 5
verbatim copies of `_launch_folder_id`, and 6 of `_read_product_or_fail`
carrying 4 different signatures for the same narrowing.

**Must follow #5**, which deletes eight of those globals outright by moving
convergence off the four request-path adapters. Re-scope it on arrival rather
than executing it as written.

## 7. `unify-the-launch-advisory-locks`

`launch_advisory_lock.py` and `launch_thread_lock.py` are the same module
twice, differing in one constant — and the load-bearing docstring is already
unsynchronised between them. Merge, with the two namespaces declared together
so "these must not collide" is checkable by reading four lines.

**Order-independent.** Slot it anywhere, except concurrently with #5, which
changes how long the advance lock is held and by which process.

## 8. `share-the-unit-test-harness`

162,335 lines of tests against 23,629 of source, across 272 test files and
**four** `conftest.py` files. Eleven separate `_FakeSession` classes. This is
what turned one added keyword argument into the 24-test outage #2 cleans up,
and it is why production code carries `getattr` tolerances for doubles that
model less than their subject.

**Last**, because it touches nearly every test file and will conflict with
anything else in flight. Needs #2 landed first — migrating a file nobody has
seen run is not a migration.

---

## Not on this list

- **`record-review-findings-as-deferred-work`** — the branch carrying
  `docs/deferred-work.md`'s new entries and this file. Independent of
  everything; merge whenever.
- **The chore commit** — `docs/deferred-work.md`'s "Small cleanups" table,
  now eight rows. One commit, no change process, as that section says.
