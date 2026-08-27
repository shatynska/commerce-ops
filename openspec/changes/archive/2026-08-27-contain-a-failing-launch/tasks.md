## 1. Review and tests, before any code

- [x] 1.1 Have the change specification independently reviewed and revise until it is approved (AGENTS.md — spec-driven development and spec review).
- [x] 1.2 Derive tests from the delta spec's scenarios, working from the specification rather than from `clickup_sync_job.py` (AGENTS.md — test design before implementation). Most scenarios are drivable at the job's own level with a fake ClickUp and an in-memory mapping store, as the existing `tests/unit/launch/infrastructure/driven/` fakes already show. Two are not. The cancellation scenario needs the walk interrupted mid-flight. The database-fault scenario needs more than a store that raises: a fake that merely raises reproduces the exception but not the failed transaction state the rollback exists for, so a test built on one passes whether or not 2.3 was implemented. Drive it either in the integration tier against a real session, or against a fake that refuses every write after it raises until `rollback()` has been called — so omitting 2.3 makes it red. The partial-projection scenario has the mirror-image problem and needs the same care: an in-memory store that models no transaction passes it whether or not the writes committed, which is the property 2.3's unconditional rollback depends on. Drive that one against a real session too, asserting the associations recorded before the failure are readable in a fresh session after the rollback.
- [x] 1.3 Confirm the derived tests fail against the current code before anything is implemented, and that they fail for the stated reason — a launch after a failing one going unconverged — rather than on a fixture fault.

## 2. Contain the failure in the pass

- [x] 2.1 In `reconcile_clickup_completions`, wrap each launch's `converge_launch` + `reconcile_launch` pair so that an `Exception` from either is caught, the launch's own reconciliation is skipped where projection raised, and the walk continues to the next launch.
- [x] 2.2 Log each contained failure against the launch it belongs to — naming its product identifier and carrying the traceback — as it happens.
- [x] 2.3 Roll the shared session back after a contained failure, before the next launch is attempted, so a database fault cannot poison the launches behind it. Where the rollback itself raises, catch it, end the walk there, and raise the aggregate below chained to it (design.md — A contained failure rolls the session back).
- [x] 2.4 Collect the failed launches and, once the walk ends — whether it finished or ended early on 2.3 — raise a single error naming every one of them by product identifier; a walk in which nothing failed raises nothing and the run is recorded as succeeded.
- [x] 2.5 Keep the readiness read and its stand-down above the loop, where they are today, so a stand-down is never reached as a per-launch failure (design.md — Context).
- [x] 2.6 Leave `clickup_sync.py`'s two passes, the mapping store and the ClickUp client untouched — the diff belongs to the driving adapter alone (design.md — Containment lives in the job's loop).

## 3. Verification

- [x] 3.1 `uv run pytest tests/unit tests/agents` green, the new tests included.
- [x] 3.2 `ruff check`, `ruff format --check` and `mypy` clean (the pre-commit hooks run all three).
- [x] 3.3 `uv run pytest tests/integration` green at pre-push.

## 4. Ship

- [ ] 4.1 Commit the work in small, reviewable commits, running the relevant verification before each (AGENTS.md — small, reviewable commits).
- [ ] 4.2 `openspec archive contain-a-failing-launch --yes` as the last commit before the merge.
- [ ] 4.3 Open the pull request and merge; merging to `main` is what deploys.

## 5. Observe it on the deployment, after the merge

The launch whose ClickUp list was deleted is deliberately left broken as the fixture that makes this change's effect visible (proposal.md — What Changes). It is what turns "the walk continues" from a unit-test claim into an observed one. This group runs after the merge, so nothing here is recorded in this change's own archived artifacts — 5.4 carries the observation into the follow-up change instead, rather than editing an archived change on `main`.

- [ ] 5.1 Read the next completion pass's log: it starts over the same active launches, the launch whose list was deleted still fails with `404` on list `901220624358` — named in the failure by its product identifier — and the walk continues past it.
- [ ] 5.2 Confirm in ClickUp that the launches previously starved behind it — the product started on 2026-08-27 among them — now have lists in folder `901213226043`, each carrying the tasks its active steps imply.
- [ ] 5.3 Confirm `/health/scheduled-runs` still reports the completion pass as failing. Containment must not have turned the broken launch green; this is the check that would catch the change having swallowed the fault. Expect Slack to stay quiet about it — `scheduled-jobs` reports a continuing outage once (design.md — Risks).
- [ ] 5.4 Propose the follow-up change for healing a launch whose ClickUp list was deleted, carrying what 5.1–5.3 established into its proposal as the evidence for it. The fixture is owed this: until that change lands, this work never records a success and the deployment stays unhealthy by design.
