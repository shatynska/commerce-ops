## 1. Review and tests, before any code

- [x] 1.1 Have the change specification independently reviewed and revise until it is approved (AGENTS.md — spec-driven development and spec review).
- [x] 1.2 Derive tests from `specs/launch-step-automation/spec.md`'s scenarios, working from the specification rather than from `automation_pass.py` (AGENTS.md — test design before implementation). Four constraints the delta spec implies but a test can silently miss:
  - **The differently-worded repeat is the load-bearing test.** A fake handler returning `Blocked` with the *same* reason twice would pass against an implementation that compares reason text, which design.md Decision 2 says must never ship. Drive the repeat with two different reason strings, and assert the step still cools off.
  - **The first non-terminal outcome must NOT cool the step off.** A test that only ever checks "eventually stops calling" passes against an implementation that backs off immediately — the behaviour this change explicitly rejected in favour of not slowing progressing handlers. Assert the second invocation happens.
  - **The undelivered report must leave nothing suppressed.** A fake notifier that silently succeeds cannot distinguish "wrote the row after delivering" from "wrote the row regardless". Drive a failing delivery and assert the next pass reports again.
  - **The backoff-store fault needs a fake that models a poisoned session**, not one that merely raises — the same trap `contain-a-failing-launch` recorded and `add-launch-journal` inherited. A store that raises without leaving the session unusable passes whether or not the restoration was written. Assert that outcomes for the *remaining* steps and launches are still persisted after the fault.
- [x] 1.3 Confirm the derived tests fail against the current code before anything is implemented, and that each fails for its stated reason — the handler being invoked on every pass — rather than on a fixture fault.

## 2. The stored shape

- [x] 2.1 Add the backoff record's model, keyed on the **composite primary key `(product_id, step_id)`** — which is what makes the note an upsert rather than an accumulating log — carrying the repeated outcome kind, when the repeat was noted, and when it was reported (null until delivery succeeds). Its own table, on the `clickup_field_gap_suppression` precedent (design.md — Decisions 3 and 4).
- [x] 2.2 Foreign-key it to `launch_positions.product_id` with `ON DELETE CASCADE`, as every other per-launch table is.
- [x] 2.3 Write the Alembic revision on top of whatever head `main` carries when the work starts — check with `alembic heads` first and re-parent if `main` has moved, since a second head fails `alembic upgrade head` outright and takes the deploy down. (This bit `add-launch-journal`; see its `fix(launch): re-parent the journal migration onto main's head`.)
- [x] 2.4 Run the migration up and down against a real database.

## 3. The backoff

- [x] 3.1 Add the driven accessors beside `field_gap_suppression.py` — read the row for a (launch, step), note a repeat (upsert), and record a report as delivered. **Noting a repeat against a different outcome kind than the row carries must clear the reported stamp** — a plain `SET outcome=…, noted_at=…` leaves it, and silently suppresses the report a step that moved and got stuck again is owed. **Reach `run_automation_pass` as an argument**, the way `results` and `deliver` already do: that module's docstring makes collaborators arguments precisely so the pass can be exercised without a database, and `run_automation_pass` takes no session to reach for.
- [x] 3.2 Define the cool-off as its own module constant, distinct from `COOL_OFF`, at 24 hours (design.md — Decision 6). Export it the way `COOL_OFF` is.
- [x] 3.3 Extend `_is_open` with the fourth condition: a noted repeat inside the cool-off closes the step. Keep it beside the other three — that function is the one place invocation is decided.
- [x] 3.4 In `_settle`'s non-terminal path, compare the proposed outcome against the one the step already carries — **the outcome kind only, never the reason** — and note the repeat when they match (design.md — Decision 2). Note `Blocked`'s dataclass equality *includes* `reason`, so a bare `==` is the wrong comparison and would silently never match.
- [x] 3.5 Make lifting **lazy, not swept** (design.md — Decision 4): the row records which outcome it was noted against, and a row whose noted outcome **kind** is not that of the step's currently recorded outcome governs neither the cool-off nor the report suppression. Compare on kind here too, for 3.4's reason — a `Blocked` re-recorded with different wording is the same kind, and a value comparison would lift the cool-off every time the rejection path re-records one. Do **not** teach the recording surfaces to delete it — `automation_confirmation` records for these steps too and the proposal leaves it untouched, so a delete-on-change rule would be owed by every present and future recorder.
- [x] 3.6 Contain every backoff-record access, and restore the shared store before the walk continues (design.md — Decision 5). Honour the **split degrade**: a failed access leaves the step eligible for invocation *and* delivers no report for it on that pass — one row, two decisions, opposite directions. Where the restore itself fails, end the walk and fail the run, as `_restore_after_store_fault` already judges. Why this matters more here than at the precedent: that record is read once ahead of the walk, this one is touched per step *inside* it, where a poisoned session makes every later `record_outcome` in the pass fail while the run still reports success — `c8bca97`'s fault in a worse place.
- [x] 3.7 Do not read `launch_journal_entries` for any of this (design.md — Decision 3). The journal stays cheap to lose exactly because no behaviour depends on it.
- [x] 3.8 **Two existing harnesses break the moment the new collaborators are required** — established during the test pass, not predicted. `test_automation_pass.py::_run_pass` and `test_retained_record_boundary.py` build a fixed keyword set and assert no *unknown* keys; they do not supply missing required ones, so a required parameter is a `TypeError` on every test in both files. Add the collaborators to those two helpers — a fixture correction, and no assertion in either file may be relaxed to reach green. Do **not** take the cheap way out and default the parameters: a mis-wire would then silently disable the feature, which is the `BOOTSTRAP_ADMIN_IDENTITY` class of fault this project has already paid for once (AGENTS.md — Deployment and configuration), and the reason `add-launch-journal` made its own port required.
- [x] 3.9 Re-attribute, do not delete, `test_automation_pass.py::test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass`. Its docstring transcribes the served spec's WHEN verbatim, which this change narrows, and its body drives the *same* outcome twice — the repeat case, not the changed-outcome case. It is **not** expected to go red: its recorder never writes to the launch, so both passes are the first-non-terminal-outcome case, which the delta still requires to re-invoke. What is superseded is its attribution, not its assertion. Narrow the docstring and fix the module docstring's "both scenarios" alongside it.

## 4. The report

- [x] 4.1 Compose the report naming the launch, the step and **what the handler produced as its result** — which for `Blocked` is also its reason — quoted as what the handler said rather than asserted as fact. Not "the outcome's reason": a repeated `InProgress` or `NotStarted` carries none, and only `Blocked` does.
- [x] 4.2 Deliver it through the monitoring notifier, on `_deliver_configuration_report`'s shape: return whether delivery actually happened, and log at error where no notifier is configured. Reach the pass as an argument, per 3.1 — not as a module global, which is the older adapters' shape and not this module's.
- [x] 4.3 Write the reported stamp **only after** a successful delivery (design.md — Decision 7). A failed delivery leaves the step eligible to be reported next pass.
- [x] 4.4 Contain a delivery failure: log it, continue the walk, and let the pass still be recorded as a successful run. One launch's fault must not starve the ones behind it (`contain-a-failing-launch`).

## 5. Verification

- [x] 5.1 `uv run pytest tests/unit tests/agents` green, the new tests included.
- [x] 5.2 `ruff check`, `ruff format --check`, `mypy` and `lint-imports` clean.
- [x] 5.3 `uv run pytest tests/integration` green at pre-push, with the migration applied.
- [x] 5.4 `openspec validate cool-off-a-repeatedly-blocked-step --strict` clean.

## 6. Ship

- [ ] 6.1 Commit in small, reviewable commits, running the relevant verification before each. Note that the pre-commit hooks run `mypy .` and the whole `tests/unit` tree, so a tests-only commit cannot be green — tests and implementation land together, as `add-launch-journal` recorded.
- [ ] 6.2 `openspec archive cool-off-a-repeatedly-blocked-step --yes` as the last commit before the merge.
- [ ] 6.3 Open the pull request and merge; merging to `main` is what deploys.

## 7. Observe it on the deployment, after the merge

The two products blocking every fifteen minutes are the fixture that makes this change's effect visible. This group runs after the merge, so nothing here is recorded in this change's own archived artifacts.

- [ ] 7.1 Read the journal an hour after the deploy: each stuck step should have at most one further `step-outcome-recorded` entry, then nothing. Before the change the same hour produced eight.
- [ ] 7.2 Confirm exactly one report per stuck step arrived in the monitoring channel, not one per pass.
- [ ] 7.3 Confirm `/health/scheduled-runs` still reports the automation pass as succeeding — backing off must not have turned a working pass into a failing one.
- [ ] 7.4 Twenty-four hours on, confirm the cool-off expired and each step was asked exactly once more, and that **no second report arrived**. Reporting is lifted by the step moving, not by the cool-off expiring — a step stuck for a week is one message, not seven. A second report here is a defect, not a success.
