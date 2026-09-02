## Context

See `proposal.md` — Why. What follows is what running the tier actually
established, because this change's whole subject is a claim about tests that
was asserted rather than measured, and repeating that mistake in the fix
would be the worst available outcome.

**Everything below was measured on the rebased tree** (this branch on top of
`main` at `125d92a`, 2026-09-01), not on the tree the proposal was first
written against. That distinction turned out to matter: `main` has since
merged `fix-launch-thread-mentions`, and it changed one of the numbers the
proposal reported. The corrections are folded into `proposal.md` and traced
in Decision 1 below.

### The baseline

`uv run pytest tests/unit tests/agents -p no:randomly`, unmodified:

```
1979 passed, 44 skipped
```

All 44 skips carry a reason naming a database. They come from two autouse
fixtures that match on *filename*, so a file's every test is skipped whether
or not it touches a database:

- `tests/unit/conftest.py:8-29` — the file's only content.
- `tests/unit/launch/infrastructure/driving/conftest.py:58-77` — the same
  seven filenames again, in a file whose other two members (`slack_asgi_app`
  and `_DrainsDeferredListeners`) are unrelated and correct.

### What is actually behind the skips

Both fixtures deleted, nothing else changed:

| | count | where |
|---|---|---|
| pass | **19** | spread across all seven files; in the backoff file, 2 of its 26 |
| fail | **24** | all in `test_automation_pass_repeat_backoff.py` |
| fail | **1** | `test_slack_entry_ack_and_failure_visibility.py::test_a_slow_transaction_does_not_miss_the_acknowledgement_window` |

**Not one of the 44 requires a database.** The recorded reason is false for
all of them, not for 42 of them — see Decision 1. One of the 19, however,
passes only because a database error is swallowed; see Decision 2's second
half.

**One limit on every measurement in this document.** `pytest-randomly` is
**not** installed in this project — it is in neither `pyproject.toml`'s dev
group nor `uv.lock`. The `-p no:randomly` flags used here are inert (pytest
accepts `-p no:<name>` for an absent plugin silently), so every number below
was obtained in one fixed collection order. Nothing here establishes
order-independence, which is why task 5.2 checks it by explicit permutation
rather than by a flag.

The three distinct causes, each established by running the failure to its
source rather than inferred from the message:

**Cause A — a collaborator the harness was never told about (17 tests).**
`run_automation_pass` (`automation_pass.py:246-259`) takes a required
keyword-only `establish_thread`. It is a properly injected port, documented
in that function's own docstring as "threaded as an argument like every other
collaborator here, not a module global, which is what lets this pass be
exercised without a database". `_run_pass` (`:1146-1183`) was never told, so
every call is `TypeError: run_automation_pass() missing 1 required
keyword-only argument: 'establish_thread'` — a failure on the way in, before
any assertion runs.

**Cause B — the stuck-step report path reaches two things the harness does
not model (7 tests).** These are the remainder of the 24, and they survive
Cause A's correction. Both are in `_report_stuck_step`
(`automation_pass.py:596-676`):

- `launches_channel()` (`slack_notifier.py:44`) reads
  `os.environ["PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"]` directly. Unset in this
  tier, so it raises `KeyError`, which `_report_stuck_step`'s own
  `except Exception` swallows into a warning — the report is simply never
  delivered and `world.messages` stays empty.
- `_FakeNotifier.post_monitoring_message` (`:770`) takes one positional
  `message`. Production calls it `post_monitoring_message(channel=…, text=…,
  thread_ts=…)`, so once the channel resolves it is
  `TypeError: got an unexpected keyword argument 'channel'` — swallowed by
  the same handler, with the same empty result.

That both faults are absorbed by a `try/except` and surface only as a missing
message is why this file reads as "needs a database" to anyone who does not
run it: the failure names nothing.

**Cause C — a seam that closed under the test (1 test).**
`test_a_slow_transaction_does_not_miss_the_acknowledgement_window` fails with
`RuntimeError: DATABASE_URL is not set`, raised inside
`launch_thread_delivery.establish_thread_and_resolve_mention`
(`launch_thread_delivery.py:82`), which opens its own `transaction()`. The
file already substitutes `slack_entry.transaction` in an autouse `sessionless`
fixture (`:268-271`) — that substitution simply does not reach a second
module's own import of the same name. The test did not move; the seam did.

This is the one skip whose stated reason is *nearly* right, and it is still
wrong in the way that matters: the test does not require a database, it
requires one collaborator to be substitutable, and that collaborator's own
module docstring says it is (`launch_thread_delivery.py:19-22`, "Imported at
module level by every call site rather than reached for inside each function
… that is what lets a unit test substitute it with `monkeypatch.setattr`").

### What the corrections cost, measured

Both fixtures deleted and the four harness corrections applied — prototyped
on 2026-09-01 to establish the number, then reverted:

```
2023 passed
```

1979 + 44 = 2023, and nothing is skipped. No assertion in any of the seven
files was changed to reach that.

Two things this number does **not** establish, both added after review rather
than claimed here first. It was obtained in one fixed collection order, for
the reason given above, so it says nothing about order-independence — task
5.2's business. And it predates the `test_slack_entry_unready_playbook.py`
substitution (Decision 2, second half), which changes *how* one already-passing
test passes without changing the total: 2023 stays 2023. The check that it did
something is **positive** — that test producing two `chat.postMessage` calls,
both to the launches channel, the second carrying a `thread_ts` (task 5.1).
Not the disappearance of the swallowed `RuntimeError`: a partly-applied fix
merely turns that exception into `KeyError: 'ts'`, keeps the fallback DM, and
satisfies a check written that way.

### How this was arrived at, and why that is recorded

`1c25b12` → `ecf4904` → `3cdfb4b` → `1267062` → `8f88d12`: five commits in one
afternoon, each adding filenames to the list. `pyproject.toml`'s
`addopts = "-rs"` was reporting all 44 on every run, with the reason attached,
the whole time — it exists precisely so a skip cannot hide, and it worked. The
gap was not instrumentation. That is what Decision 3 is aimed at.

## Goals / Non-Goals

**Goals:**

- Every one of the 44 runs, at the tier it is already in, on every commit and
  in CI.
- No assertion in any of the seven files changes. A test that fails on the way
  in has not been evaluated, so nothing about what it checks is in question
  here — only whether it is reached.
- A blanket skip cannot silently take a file out of the commit-time tier
  again. Stated as what a mechanism enforces rather than as a convention, for
  the reason this change exists: the convention already existed, in both
  `AGENTS.md` and the `testing` standard, and it was bypassed five times in an
  afternoon without anything objecting.

**Non-Goals:**

- Rewriting, splitting or reducing any of the seven files.
- Anything in `src/`. Three of this change's four seams are places where
  production code reaches for a global (`launch_thread_delivery`'s own
  `transaction()`, `thread_establishment`'s `lru_cache`d `AsyncWebClient`,
  `launches_channel`'s direct `os.environ` read). Every one is
  `inject-the-thread-anchor-poster`'s scope, and correcting them here would
  make this change a redesign of the adapter layer rather than a restoration
  of a suite.
- The shared-harness duplication that turned one added keyword argument into a
  24-test outage — `share-the-unit-test-harness`, which the change order puts
  after this one and for which this one is a stated precondition.
- The incomplete doubles this change corrects are corrected *only* far enough
  to reach their tests: two `api_call` responses gaining a `ts`, `_FakeNotifier`
  gaining a call shape, and two fake launch stores. None of that is a general
  repair of any of them — that is `share-the-unit-test-harness`, and the
  duplication these five corrections walk through is itself evidence for it.

## Decisions

### Decision 1 — The claim is "none of the 44 needs a database", not "42 of 44"

`proposal.md` as first written recorded **2** genuinely database-bound tests.
On the rebased tree there is **1**, and it is not database-bound either — it
is `establish_thread_and_resolve_mention` not being substituted (Cause C).

The second one the proposal named,
`test_slack_entry_unready_playbook.py::test_a_start_against_a_ready_playbook_is_unaffected`,
passes today — and an earlier draft of this document stopped there, which was
the same mistake in miniature. Running it shows the pass is not a repair:

```
ERROR commerce_ops…slack_entry could not post confirmation to thread
RuntimeError: DATABASE_URL is not set …
1 passed
```

The file substitutes only `slack_entry.transaction` (`:302-304`) and sets no
launches channel (`:307-312`), so `establish_thread_and_resolve_mention` still
raises on every run; `slack_entry.py:579` swallows it; the direct-message
fallback that `main` gained in `c48a70f` posts; and the test's
`assert slack_api.posts` (`:565`) is satisfied by that DM. The test does not
exercise the threaded delivery `launch-entry` specifies at all.

This is dealt with rather than noted — see Decision 2's second half. A change
whose stated purpose is to stop tests being green for reasons nobody checked
cannot ship one of its own restored tests in exactly that state.

**The correction is load-bearing and not cosmetic.** "42 of 44 reasons are
false" leaves the skip mechanism partly justified and invites a smaller fix
that keeps two entries in the list. "44 of 44" does not: there is no residue,
both fixtures go entirely, and `tests/unit/conftest.py`'s skip content has no
successor. It also matters that the number moved *while the proposal sat on a
branch* — which is the argument for re-measuring at implementation time
(task 1.1) rather than trusting this document, exactly as this document
declines to trust the proposal.

### Decision 2 — Restore the one thread-bound test by substituting the seam beneath the preamble, not the preamble itself

Three routes, and the choice is decided by which of them can be taken without
weakening an assertion.

**Rejected: substitute `slack_entry.establish_thread_and_resolve_mention`.**
This is the cheapest route and it is the convention two sibling files already
follow — `test_automation_confirmation_delivery.py:204` and
`test_automation_confirmation_to_thread_reply.py:192` both declare
`_THREAD_NAMES: Final = ("establish_thread_and_resolve_mention",)` and
`monkeypatch.setattr` it. It fails here for a reason specific to this test.
The anchor message is posted *inside* `ensure_launch_thread`
(`thread_establishment.py:84`), so substituting the whole preamble means the
anchor is never posted, and this test asserts on **two** posts:

```python
assert len(slack_api.posts) == 2, (
    "expected an anchor message and a threaded confirmation reply once "
    f"the slow persistence completed, observed: {slack_api.posts}"
)
anchor, reply = slack_api.posts
```

Taking this route means changing that to one post. The assertion is
spec-derived — `thread-launch-slack-notifications` made a started launch's
confirmation an anchor plus a tagged reply, and the file's docstring records
the manifest entry it came from — so weakening it is exactly the move the
`testing` standard forbids and exactly the move that produced the defect this
change is repairing. Rejected on that ground alone, not on taste.

**Chosen: substitute `launch_thread_delivery`'s own three collaborators** —
`transaction`, `LaunchRepository` and
`hold_launch_thread_establishment_lock` — extending the `sessionless` autouse
fixture that already substitutes `slack_entry.transaction` in the same file.
The real `ensure_launch_thread` then runs: it takes the (no-op) lock, reads a
launch with no thread yet, composes the anchor, posts it, and records the
thread reference. Both posts happen, both are observed, and every assertion
holds as written.

The anchor is observable because the file's `slack_api` fixture patches
`AsyncWebClient.api_call` on the **class** (`:364`), not on an instance — so
it catches `thread_establishment`'s own `lru_cache`d client as well as
`post_monitoring_message`'s, without that module needing to be reachable or
reset. That is a property of the existing fixture, verified by running it, not
a change this makes.

**One double must be completed for this to work, and the gap is worth
naming.** `_RecordingSlackApi.api_call` returns `_FakeSlackResponse({"ok":
True})`. `ensure_launch_thread` reads `response["ts"]` (`:87`), so the double
raises `KeyError: 'ts'` — which `slack_entry`'s `except Exception` swallows
into the DM fallback, and the test then observes two posts of which the second
is a DM. Adding `ts` to the fake response is a double modelling its subject
more completely; it weakens nothing.

**The same substitution goes to `test_slack_entry_unready_playbook.py`.** Its
failing test is not among the 25 — it *passes* — but it passes through the
swallowed `RuntimeError` shown in Decision 1, so restoring the tier without
touching it would leave one of the 44 unable to observe the delivery it is
nominally about. The remedy is the same three module attributes in the same
directory with the same launches-channel `setenv`, and no assertion changes, so
it is the chosen route applied twice rather than new scope — **and it is the
whole route, not its first step.** That file carries its own `api_call`
returning no `ts` and its own cached-factory list, so the substitution alone
merely trades one swallowed exception (`RuntimeError: DATABASE_URL is not
set`) for another (`KeyError: 'ts'`), leaves the fallback DM answering the
assertion, and looks fixed. Both double completions travel with it. The
scope-control
objection was weighed and rejected on the ground that `tasks.md` 1.3 already
requires an unexplained *failure* to stop the work: a *pass* produced by a
swallowed database error deserves no less.

**Rejected: move the test to `tests/integration/launch/`.** The file's
docstring points at `tests/integration/launch/test_slack_entry_start.py` for
the DB-backed scenario, so there is a real precedent for the split. But what
this test uniquely measures is that the acknowledgement returns before a
deliberately slow collaborator does — a wall-clock proxy the file's own
docstring calls inherently sensitive to scheduler contention. Moving it to a
tier that runs at `pre-push` behind real Postgres makes that proxy strictly
noisier while removing the check from the commit-time gate, which is the one
place an ack-window regression would be caught early. Kept available as the
fallback if the chosen route proves unstable (task 5.3).

### Decision 3 — The commit-time tier tolerates no skips at all

The obligation from `proposal.md` is that a skip must name an individual test
and carry a reason true of it. Three mechanisms could enforce something like
that.

**Rejected: fail when every test in a file is skipped.** It is the precise
shape of what happened, and it is fragile under selection: run one test from a
file with `-k` and legitimately skip it, and the rule fires. A guard that
misfires under normal use is one that gets deleted.

**Rejected: inspect skip reasons for a filename match.** Unenforceable in any
robust way — the mechanism is a string comparison against
`request.node.fspath`, and there is no reliable signature for it in the report.

**Chosen: no skipped test in `tests/unit` or `tests/agents` fails the run.**
Four properties recommend it:

- It is **satisfied on this machine**, measured: 2023 passed, 0 skipped. That
  is weaker than "true today", and the difference is the decision's one real
  cost — see the inventory immediately below.
- It **cannot be satisfied by widening a list**, which is precisely how the
  defect grew across five commits. There is no list.
- It is **checkable by reading it**. The guard is a `pytest_sessionfinish`
  hook that collects skipped reports under those two paths, names each one,
  and fails the session. Nothing about it requires understanding a fixture's
  match logic.
- The tier's own charter already implies it. `tests/unit` and `tests/agents`
  are defined in `AGENTS.md` as fast and mocked, carrying "no network/IO
  cost". A test that cannot run in that tier does not belong in it, which is
  what the deleted fixtures' own docstrings said while doing the opposite.

**Two conditional skips already exist in this tier, and the rule is adopted
knowing what it does to them.** A first draft of this decision called a
legitimate skip a future hypothetical; it is not:

- `tests/unit/shared/infrastructure/driving/test_admin_assets_route.py:339`
  — skips when `git` is not on `PATH`.
- `tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py:159`
  — skips when the trigger object it inspects is absent.

Neither fires on this machine, which is exactly why "0 skipped" was mistaken
for "no skips exist". Both are kept, and the rule is kept, because neither can
fire where the rule is actually enforced: the commit-time gate runs inside a
`pre-commit` hook, which runs inside a git checkout, and CI reaches the tier
through `actions/checkout` — both of which guarantee `git`.

**Task 4.6 forced the case rather than resting on that reasoning, and the
guard does fire.** Run with `git` stripped from `PATH`,
`test_admin_assets_route.py`'s two skips trip the guard and fail the tier
(exit 1, measured). An earlier form of this decision said the guard would then
gain a narrow allowance naming that one test. **It does not, and that
instruction was wrong:**

- An allowance is a list, and a list is the mechanism that grew across five
  commits into this defect. That it would be a list of *test names* rather
  than *filenames* makes it smaller, not different in kind.
- It buys nothing where the rule is enforced. Neither `pre-commit` nor CI can
  produce this skip, so the allowance would protect only a hand-run on a
  machine without `git` — while permanently costing the guard the property
  that makes it legible, which is that it admits no exceptions at all.

**The consequence is accepted and recorded instead:** a developer hand-running
the commit-time tier with no `git` on `PATH` gets a tier-level failure naming
two asset tests they cannot act on. The remedy is to put `git` on `PATH` —
which every enforced path already guarantees — not to carve a hole in the
guard. This is the one place the change was invited to admit an exception to
its own rule and declined; a change about not quietly admitting exceptions
should not open with one.

The remaining cost is stated rather than discovered: a future
genuinely-conditional skip in this tier becomes a deliberate act requiring the
guard to be amended in the same commit, in view of a reviewer. That is the
property that was missing, so it is the point rather than a side effect.

**`xfail` is not a skip for this purpose.** `TestReport.skipped` is also true
for an `xfail`ed test, so the hook must distinguish them or it bans a marker
nobody proposed banning. No `xfail` marker exists anywhere under `tests/`
today, but three file docstrings still record "2 xfailed" from 2026-08-28, so
the shape is one this repository has used.

**Where it lives.** The guard must cover `tests/agents` as well as `tests/unit`, and `tests/agents`
has no `conftest.py`. An earlier draft put the hook in `tests/unit/conftest.py`
and rejected a new `tests/conftest.py` on the ground that it would also sit
above `tests/integration`, where skips are legitimate and specified
(`AGENTS.md`: "tests needing a database skip and say why"). **That reasoning
does not survive**: the path filter the guard needs anyway already excludes
`tests/integration`, so it does not distinguish the two placements — while the
`tests/unit/` placement has a defect the other does not. A conftest is loaded
only for the paths collected, so `uv run pytest tests/agents` on its own loads
no `tests/unit/conftest.py`, registers no hook, and runs the agents tier
unguarded and silently. That is the vacuous-guard failure this very decision
warns about, in the placement it had chosen.

**So the hook goes in a new `tests/conftest.py`, keeping the path filter.** It
is then loaded for any invocation under `tests/`, and the filter — not the
file's location — is what keeps `tests/integration` out. Both real gates pass
both paths together (`.pre-commit-config.yaml:36`,
`.github/workflows/ci.yml:69`), so this changes nothing about the gate; it
closes the hand-run case.

**And it reaches the single-file hand-run too**, which is the case a developer
meets first. `confcutdir` defaults to the rootdir, fixed here by
`pyproject.toml`, so pytest walks the ancestor chain down to each argument's
directory: `uv run pytest tests/unit/…/test_slack_entry_modal_contract.py` and
a bare nodeid both load `tests/conftest.py` — and so does `cd tests/agents &&
uv run pytest .`, since rootdir resolution does not depend on cwd. No
invocation under `tests/` escapes it **except by deliberate flag**:
`--noconftest`, or a `--confcutdir` below `tests/`. Both are deliberate acts,
which is the standard this decision already applies to skips. The property
depends on `pyproject.toml` keeping its `[tool.pytest.ini_options]` table — it
holds `testpaths` and `addopts`, so it is not going anywhere — and on nobody
adding `--confcutdir` to `addopts`; named so the next reader can check the
claim rather than believe it. The consequence to state plainly is that on a
git-less machine a developer running `test_admin_assets_route.py` alone now
fails rather than skips — the same exposure this decision already accepts and
task 4.6 forces, reaching one case further than "whole tiers" suggests.

`tests/unit/conftest.py` therefore goes after all, exactly as
`proposal.md`'s Impact section first said: with the skip fixture removed and
the guard placed one level up, it has no remaining content. The file count is
unchanged — one deleted, one added.

**It observes reports, not collection.** The skips being guarded against
happen during *setup*, when an autouse fixture calls `pytest.skip` — not at
collection, so `pytest_collection_modifyitems` cannot see them. This is the
same lesson `isolate-tests-from-the-shared-runner`'s Decision 1 recorded for
its own guard, arrived at independently here: a guard placed where the
condition is not observable passes vacuously.

**And it must read two kinds of report, which a first draft of this decision
missed.** Writing the guard's test surfaced a gap between this decision's goal
and its mechanism, measured on pytest 9.1.1:

| whole-file skip | what it emits | hook that sees it |
|---|---|---|
| `pytestmark = pytest.mark.skip` | one `TestReport` per test | `pytest_runtest_logreport` |
| `pytest.skip(…, allow_module_level=True)` | **no `TestReport` at all** — only a `CollectReport` | `pytest_collectreport` |

A guard reading `TestReport`s alone — which is what this decision first said,
and only that — is blind to the second, while pytest's own summary still counts
it as skipped. The tier could therefore lose an entire file to a one-line
module-level skip and the guard would report the session clean: the precise
outcome Goal 3 exists to prevent, reached by the one route the mechanism did
not cover. Both hooks are read and merged. Verified on a synthetic two-file
tree where each shape is caught by exactly one hook and neither hook catches
both.

That this was found by writing the guard's test, rather than by review or by
this document's own reasoning, is worth recording: it is the argument for the
test existing at all, against tasks 4.5-4.7's manual procedures, which would
have exercised only the shape their author had in mind.

## Risks / Trade-offs

- **The commit-time gate gets slower.** 44 more tests, measured at roughly
  +13s on this machine (46s → 59s for `tests/unit` + `tests/agents`). Accepted;
  it is the point. `test_automation_pass_repeat_backoff.py` alone is 26 tests
  over 2,345 lines covering every backoff, cool-off and stuck-step rule
  `launch-step-automation` states, and it runs in 0.13s — the tier's cost is
  overwhelmingly elsewhere.
- **44 tests that have not run since they were written may be wrong.** The
  measured 2023-passing run says they are not wrong *today*, but they were
  authored against specs, skipped almost immediately, and have never had a
  chance to catch a regression. Any that turns out to assert something false is
  a finding to raise, not a licence to edit it inside this change — `AGENTS.md`'s
  scope-control rule and `proposal.md`'s own exclusion.
- **The zero-skip guard forbids a legitimate future skip.** → See Decision 3;
  it converts an invisible act into a visible one, which is the whole intent.
  If a genuine need arises, the guard is amended in the same commit as the
  skip, where a reviewer sees both.
- **Three of the four corrected seams are production code reaching for a
  global, and this change leaves all three standing.** →
  `inject-the-thread-anchor-poster` is the change that removes them, and the
  change order puts it immediately after this one for that reason. What this
  change adds is a measured account of exactly which three and what each costs
  a test — which is better input to that change than it had.
- **`AGENTS.md`'s ordering — test-writer before implementation — does not fit
  this change, and saying so is better than pretending it does.** The
  `openspec-test-writer` binding derives new tests from delta specs and never
  edits an existing test. This change has no delta specs (`skip_specs: true`)
  and its entire subject is existing tests. The obligation the binding exists
  to serve — that what a change must satisfy is fixed before the change is
  made — is met differently and more strictly here: the pass/fail state of all
  44 is measured and recorded in this document *before* any correction, and
  task 1.1 requires re-measuring it rather than inheriting these numbers.
  **One qualification**, because "its entire subject is existing tests" is
  slightly overbroad: section 4's guard is new behaviour, not an existing
  test. What substitutes for the binding there is not measurement but task
  4.5/4.7's two-directional verification — the guard must be shown to fire on
  a skip and not to fire on `tests/integration`'s legitimate ones, which is
  the same discipline `isolate-tests-from-the-shared-runner` applied to its
  own guard.

## Migration Plan

No schema change, no deployed behaviour, no `src/` change. `tests/` only, and
revertible as a code change alone.

## Open Questions

None. The two the proposal deferred — which route restores the thread-bound
test, and what mechanism guards against a repeat — are settled in Decisions 2
and 3 against measured results rather than left to implementation.
