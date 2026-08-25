## Why

Running the integration tier intermittently **hangs forever**, and the same
mechanism makes `pytest` defer and execute this application's **real
production jobs** against whatever database the tier is pointed at. Both
follow from one fact: `runner_app` is a process-wide singleton, and any test
module that calls `register_all()` arms its periodic registry for every
worker run in the same pytest process.

The hang was recorded in `docs/deferred-work.md` as unexplained, with three
hypotheses each falsified by experiment. It is now identified, reproduced and
isolated to a single call — see `design.md` for the captured await chain and
the A/B result.

## What Changes

- The runner tests stop driving the application's shared periodic registry.
  `tests/integration/shared/test_scheduled_run_history.py` and
  `tests/integration/shared/test_periodic_defer_dedup.py` run a worker whose
  periodic deferrer sees an empty registry, as they did before any sibling
  module called `register_all()`.
- `tests/integration/conftest.py` gains a guard that fails loudly if any test
  starts a worker against a non-empty shared registry — so the rule holds for
  tests nobody has written yet, not only for the two files that exhibit the
  defect today.
- `_drain()` gains a ceiling, so a future wedge in the runner fails the test
  that caused it instead of hanging the session. A bound, not a cure — kept
  because a suite that can hang indefinitely is not a suite.
- The junk this defect has already written is removed: the rows in
  `procrastinate_jobs` for `briefing.daily`,
  `launch.clickup.completion_pass`, `shared.scheduled_runs.overdue_check` and
  `products.monitoring.daily`, which distort a developer-local
  `last_successful_run`. Procrastinate's schema records no deferring process,
  so the justification is what these rows do, not who wrote them — see
  `design.md` Decision 3.
- `docs/deferred-work.md`'s entry on the hang is rewritten with the confirmed
  mechanism (already done, in this change's first commit, under the heading
  "The integration tier hangs intermittently — cause identified 2026-08-25"),
  and is deleted on merge along with "Tests defer and run production jobs",
  since both stop being true when this ships. "The upstream properties this
  depends on" survives them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/` and `docs/`, and performs a one-off deletion
in a developer's database; it changes nothing in `src/`. No requirement in
`scheduled-jobs`, `deploy-pipeline` or any other capability describes
behaviour that changes here: the application's own deferring, running,
recording and retrying of recurring work is correct and stays as specified.
What is wrong is that the tests exercise it through a shared global they do
not own. `.openspec.yaml` therefore sets `skip_specs: true`.

Stated explicitly because the temptation runs the other way: it would be easy
to invent a requirement such as "production recurring work is only deferred
by the deployment's worker" in order to have a delta to write. Nothing in
`src/` violates that today — only the tests do — so the requirement would
describe a defect that does not exist in the system being specified.

## Impact

- `tests/integration/shared/test_scheduled_run_history.py` — the file the
  stall lands in.
- `tests/integration/shared/test_periodic_defer_dedup.py` — same exposure
  through `runner_app.run_worker_async()`, not yet observed to stall.
- `tests/integration/conftest.py` — gains the tier-level guard.
- The four integration modules whose import arms the registry
  (`test_known_work_anchor.py`, `test_overdue_report_suppression_store.py`,
  `test_scheduled_runs_freshness_cache.py`,
  `test_scheduled_runs_freshness_unreachable.py`) are **not** changed. Their
  `register_all()` call is correct for what each of them tests; the defect is
  that a *different* file inherits its effect.
- `docs/deferred-work.md`.
- **The developer's database**, one-off and irreversible: the
  `procrastinate_jobs` rows for the four production task names, and their
  `procrastinate_events` / `procrastinate_periodic_defers` children, are
  deleted. The database is the one the tier resolves — `DATABASE_URL`, else
  `.env.test`, else `.env` — named explicitly before anything is deleted.
  **Not** the deployment's database, whose rows for those names are genuine
  runs.
- No change to `src/`, to the schema, or to any deployed behaviour.
- CI: the `timeout-minutes: 15` ceiling `verify-the-integration-tier` added
  stays. It was a mitigation for this defect and remains worth having.
