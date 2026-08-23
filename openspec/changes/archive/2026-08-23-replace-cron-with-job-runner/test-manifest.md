# Test manifest — `replace-cron-with-job-runner`

Not an OpenSpec-schema artifact: `openspec instructions apply` will not list
this file among its context files. Read it on purpose before implementing —
`ai-toolkit`'s `rules/` fragment also directs the implementer here, but that
import path is machine-local, so this pointer (and the one in the dispatch
report) are the two ways to actually reach it.

**This pass adds tests and never subtracts.** No existing test was weakened,
deleted, or disabled, and no implementation code was written. tasks.md 4.4
("Delete `test_internal_trigger_guard.py` and the retired routes' tests") and
4.5 ("Amend, do not delete, the four `runtime-configuration` regression
guards") were read as *findings about the change*, not as instructions to
this pass — the tests they name are recorded in the obsolete list below.
(The implementer has since carried 4.4 and most of 4.5 out; the list records
what is done and what is left.)

## This manifest is a replacement, not a merge

**Written on a second pass** (2026-08-23), after the delta specs and tasks
were revised through three review rounds. It replaces the first pass's
manifest wholesale rather than merging into it, because a manifest states
the change as it now stands. Where an entry below is unchanged from the
first pass it was re-checked against the revised delta specs, not copied on
trust.

The second pass covered four gaps the revisions opened (tasks.md 5.5a, 5.7's
extension, 5.14, 5.15) plus one piece of test infrastructure the implementer
reported. It did **not** re-derive the first pass's tests.

### What is different about the second pass's situation

The first pass wrote against an absent target: nothing it wrote could
execute. By the time of the second pass, sections 1–4 were largely
implemented, so `commerce_ops.worker`, `job_history.py` and the daily job
definition all exist. Per `ai-toolkit:testing`'s "Which situation you are
in", that reverses what a first-run pass means: for the four tests added
here a pass is the expected result and establishes that the code currently
behaves as asserted — it is *not* the alarm it would have been in the first
pass. Each new test was therefore additionally checked for discriminating
power, and the check is recorded with it below.

The implementation was **not read** while deriving these tests. The bound
was crossed in exactly one place, deliberately and narrowly, and it is
recorded under "Findings" below.

## Scenario accounting

The five delta specs declare **28** `#### Scenario:` blocks (re-counted
against the revised specs: `scheduled-jobs` 14, `product-monitoring` 8,
`deploy-pipeline` 3, `runtime-configuration` 3, `internal-trigger` 0). All
28 are accounted for below — 25 covered, 3 uncovered with reason. A further
**7** scenarios reached through this change's REMOVED deltas are accounted
for at the end.

One requirement outside those 28 is also covered here — `application-logging`'s
"Logging Is Configured From Every Entrypoint", which no delta in this change
touches but which binds `worker.py` the moment tasks.md 2.8 creates it. It
has its own section.

Test files added by these passes:

- `tests/unit/products/infrastructure/driving/test_daily_digest_job.py`
- `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py`
- `tests/unit/shared/infrastructure/driven/test_alembic_runner_schema_guard.py`
- `tests/unit/shared/application/test_trigger_secret_is_no_longer_declared.py`
- `tests/unit/test_no_external_cadence_trigger.py`
- `tests/unit/test_http_serves_without_a_worker.py`
- `tests/unit/test_compose_worker_service.py`
- `tests/integration/shared/test_scheduled_run_history.py`
- **`tests/integration/shared/test_periodic_defer_dedup.py`** (second pass)

Existing files **appended to** on the second pass — no existing test in any
of them was edited, only new tests and their helpers added:

- `tests/integration/shared/test_scheduled_run_history.py` — the
  "A run spans its retries" sibling test, plus the engine-disposal fixture
  described under "Findings".
- `tests/unit/test_compose_worker_service.py` — the `app_db` membership test.
- `tests/unit/shared/infrastructure/test_logging_process_boundary.py` — the
  two worker-entrypoint logging tests.

No `__init__.py` or `conftest.py` was added: both fall outside the dispatched
test-path glob (`tests/**/test_*.py`). The `anyio_backend` fixture each async
file needs is defined in the file itself.

### `scheduled-jobs` — Requirement: Recurring Work Runs On Its Declared Schedule

| Scenario | Test |
|---|---|
| Work runs when its schedule is due | `tests/unit/products/infrastructure/driving/test_daily_digest_job.py::test_the_daily_cadence_has_a_declared_schedule` and `::test_the_declared_schedule_becomes_due_once_a_day_at_06_00` |
| Work with no declared schedule does not run | `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py::test_exactly_one_piece_of_recurring_work_is_scheduled`; `::test_an_unimplemented_cadence_has_no_declared_schedule` (parametrized over weekly, biweekly, monthly, quarterly) |
| The schedule's timezone does not depend on the host | `test_daily_digest_job.py::test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone` |

### `scheduled-jobs` — Requirement: A Window Missed While No Worker Was Available Is Run Once On Return

| Scenario | Test |
|---|---|
| A single missed window is run on return | `test_job_runner_schedules.py::test_a_single_missed_window_is_run_on_return`; and, for the restart reading of "once", `tests/integration/shared/test_periodic_defer_dedup.py::test_a_tick_that_already_ran_is_not_run_again_after_a_restart` |
| Several missed windows produce one run | `test_job_runner_schedules.py::test_several_missed_windows_produce_one_run` (plus the DERIVED `::test_the_run_performed_on_return_is_the_most_recent_missed_window`) |

**Why the second pass added a test here** (tasks.md 5.5a). `max_delay` is
now `float("inf")` (task 2.5), so *every* worker start re-offers the most
recent past tick, and this deployment restarts the worker on every merge to
`main` — a redeploy at 09:00 re-offers a 06:00 tick that already ran. The
two unit tests above see only what one deferrer does; the guarantee that a
re-offered tick produces no second run is in the database, per design.md's
"a third path, which is what makes \"once\" true across restarts". The new
integration test is the only thing standing between a future schema change
and a second digest after every afternoon redeploy.

### `scheduled-jobs` — Requirement: Scheduled Work Is Not Reachable From Outside The Deployment

| Scenario | Test |
|---|---|
| No external interface starts scheduled work | `tests/unit/test_no_external_cadence_trigger.py::test_no_route_exists_for_starting_a_cadence`; `::test_a_request_to_a_retired_cadence_path_finds_nothing` (parametrized over the five retired paths) |

### `scheduled-jobs` — Requirement: A Failed Run Is Retried With Increasing Delay

| Scenario | Test |
|---|---|
| A failing run is retried | `test_daily_digest_job.py::test_a_failing_run_is_retried` |
| Successive retries wait longer | `test_daily_digest_job.py::test_successive_retries_wait_longer` |
| Retries stop at the declared maximum | `test_daily_digest_job.py::test_retries_stop_at_the_declared_maximum` |
| A retried run that succeeds is recorded as succeeded | `tests/integration/shared/test_scheduled_run_history.py::test_a_retried_run_that_succeeds_is_recorded_as_succeeded` (the outcome half) and `::test_a_retried_run_is_one_record_spanning_its_attempts` (the start/end half) |

### `scheduled-jobs` — Requirement: Every Run's Outcome Is Recorded And Can Be Asked About Afterwards

| Scenario | Test |
|---|---|
| A completed run is recorded | `test_scheduled_run_history.py::test_a_completed_run_is_recorded` (parametrized over `succeeded` and `failed`; asserts all four recorded facts — which work, start, end, outcome). The requirement's added "A run spans its retries" paragraph is covered by `::test_a_retried_run_is_one_record_spanning_its_attempts`, which asserts one record, its start taken from the first attempt, and its end from the outcome that stopped it. |
| A run's record outlives the process | `test_scheduled_run_history.py::test_a_runs_record_outlives_the_process` |
| The most recent successful run can be identified | `test_scheduled_run_history.py::test_the_most_recent_successful_run_can_be_identified`; `::test_work_that_has_never_succeeded_is_reported_as_such`; plus the DERIVED `::test_a_failed_run_does_not_count_as_a_success` |

**Why the second pass extended this** (tasks.md 5.7, and 2.10's
precondition). The requirement now states "Its start is the first attempt's
start, its end is the moment of the outcome that stopped it". The existing
retry test asserted only the outcome. A history that records the right
outcome against the *successful attempt's* start would have passed it while
telling `report-overdue-scheduled-runs` the wrong thing about when a run
began. Written as a sibling rather than as extra assertions inside the
existing test, so the two halves fail separately.

### `scheduled-jobs` — Requirement: A Worker Failure Does Not Prevent The Application From Serving

| Scenario | Test |
|---|---|
| HTTP is served while no worker is running | `tests/unit/test_http_serves_without_a_worker.py::test_http_is_served_while_no_worker_is_running`; `::test_the_http_process_does_not_import_the_worker_entry_point`; `tests/unit/test_compose_worker_service.py::test_the_worker_is_a_service_of_its_own`; `::test_the_application_service_does_not_depend_on_the_worker` |

### `product-monitoring` — ADDED: The Daily Cadence Runs On A Schedule

| Scenario | Test |
|---|---|
| The daily cadence runs when its schedule is due | `test_daily_digest_job.py::test_the_daily_cadence_has_a_declared_schedule`; `::test_the_declared_schedule_becomes_due_once_a_day_at_06_00` |
| The daily cadence cannot be started from outside the deployment | `test_no_external_cadence_trigger.py::test_no_route_exists_for_starting_a_cadence`; `::test_a_request_to_a_retired_cadence_path_finds_nothing[/products/monitoring/daily]` |

### `product-monitoring` — MODIFIED: Daily Cadence Lists Existing Product Names

| Scenario | Test |
|---|---|
| Daily trigger lists product names | `test_daily_digest_job.py::test_daily_trigger_lists_product_names` |
| No products exist | `test_daily_digest_job.py::test_no_products_exist_posts_a_message_rather_than_nothing` |

### `product-monitoring` — MODIFIED: Report Delivery Failure Is Decoupled From The Trigger

| Scenario | Test |
|---|---|
| Slack post fails | `test_daily_digest_job.py::test_slack_post_failure_leaves_the_run_succeeded_and_unretried` |

### `product-monitoring` — MODIFIED: Database Read Failure Is Surfaced, Not Treated Like A Delivery Failure

| Scenario | Test |
|---|---|
| Database read fails | `test_daily_digest_job.py::test_database_read_failure_on_the_final_attempt_fails_and_posts` |
| An intermediate failed attempt does not post | `test_daily_digest_job.py::test_an_intermediate_failed_attempt_does_not_post`; `::test_every_intermediate_attempt_stays_silent_and_the_last_one_posts` |
| A database read failure is retried | `test_daily_digest_job.py::test_a_failing_run_is_retried` |

### `deploy-pipeline` — MODIFIED: Compose File Provisions a Persistent, Network-Isolated Postgres Service

| Scenario | Test |
|---|---|
| Postgres data survives a redeploy | `tests/unit/test_compose_worker_service.py::test_postgres_data_is_stored_in_a_named_volume` — **covered in part.** The declaration the outcome rests on is asserted; the redeploy itself is **UNCOVERED**, see below. |
| Postgres is unreachable from the public-facing network | `test_compose_worker_service.py::test_postgres_is_not_on_the_network_app_receives_public_traffic_on` |
| The network Postgres is reachable on is not external | `test_compose_worker_service.py::test_the_network_postgres_is_on_is_not_external` (not external; every attached service is one this file defines) **and** `::test_the_members_of_the_network_postgres_is_on_are_this_applications_own` (the membership set itself — `app`, `postgres`, `worker`) |

**Why the second pass added the second test** (tasks.md 5.15). The existing
test already asserted the non-external clause and that every attached service
is defined in this file — both true by construction while `app_db` had two
members. The clause earns its keep once a second service joins, so the new
test states *which* services those are. It is the point at which "does this
service belong on Postgres' network?" becomes a decision rather than an
assumption.

### `runtime-configuration` — MODIFIED: Every Variable The Runtime Requires Is Declared In One Place

| Scenario | Test |
|---|---|
| Every declared variable is discoverable from one definition | **UNCOVERED by a new test**, see below — the existing `tests/unit/shared/application/test_settings.py` already is this scenario's coverage. The change-specific instance is `tests/unit/shared/application/test_trigger_secret_is_no_longer_declared.py::test_the_removed_variable_is_not_declared`. |
| A variable read by the application but not declared is detected | **UNCOVERED by a new test**, see below — the existing `test_settings_env_drift.py` *is* the detection mechanism this scenario requires. |
| A declared variable the application does not read carries a recorded reason | `test_trigger_secret_is_no_longer_declared.py::test_the_removed_variable_is_not_parked_in_the_exemption_table` |

### `application-logging` (existing capability, no delta here) — Requirement: Logging Is Configured From Every Entrypoint

Covered on the second pass, per tasks.md 5.14. Not one of the 28 scenarios
above: this requirement is already published under `openspec/specs/` and is
unchanged by this change. It binds the worker because tasks.md 2.8 creates a
third entrypoint, and no test author working only from this change's deltas
would derive it.

| Scenario / clause | Test |
|---|---|
| "Every entrypoint ... SHALL configure logging **before performing its own work**" | `tests/unit/shared/infrastructure/test_logging_process_boundary.py::test_the_worker_entrypoint_configures_logging_before_its_own_work` |
| Scenario: A non-HTTP entrypoint emits records | `::test_a_record_emitted_after_the_worker_entrypoint_ran_reaches_stderr` (the same scenario `::test_a_non_http_entrypoint_emits_records` asserts of `preflight`) |

How the worker is started there, and what is stubbed, is documented in the
file's own section header. In short: the module is run under
`runpy.run_module(..., run_name="__main__")`, matching
`docker-compose.yml`'s `python -m commerce_ops.worker`, with
`App.run_worker` / `App.run_worker_async` replaced by a stub standing in for
"the entrypoint's own work" and the connector replaced by procrastinate's
in-memory one. The stub *prints* one marker and *logs* another, so an
entrypoint that never started its worker is distinguishable from one that
started it with logging unconfigured.

## Uncovered scenarios, with reasons

1. **`deploy-pipeline` / "Postgres data survives a redeploy" — the runtime
   half.** A `docker compose pull && up -d` cycle against a running stack
   with existing data cannot be observed from any test tier this project
   has. What a test *can* observe — that the data is in a volume this
   compose file names — is asserted. The runtime half is assigned to the
   change's own verification steps (tasks.md 6.4, 6.5).
2. **`runtime-configuration` / "Every declared variable is discoverable
   from one definition"** and **3. "A variable read by the application but
   not declared is detected".** Both scenarios' text is unchanged by this
   MODIFIED delta, and both are already covered by existing tests this pass
   may not edit (`test_settings.py`, `test_settings_env_drift.py`). A new
   test for either would create a *second* transcription of the declared-
   variable set — the very thing that makes the existing guards need
   amending when a variable is removed.

## Scenarios superseded by this change's REMOVED deltas

Accounted for as uncovered, with the removal itself as the reason. Removed
behaviour is not to be tested, and no new test covers any of these.

| Capability | Requirement removed | Superseded scenarios |
|---|---|---|
| `internal-trigger` | Trigger Secret Is Required | Missing secret is rejected; Incorrect secret is rejected |
| `internal-trigger` | Correct Secret Is Accepted | Matching secret is accepted |
| `internal-trigger` | Secret Comparison Is Constant-Time | Comparison uses constant-time equality |
| `internal-trigger` | Guard Fails Closed When Unconfigured | Trigger secret is not configured |
| `product-monitoring` | Each Cadence Has Its Own Guarded Trigger Endpoint | A cadence endpoint rejects an unguarded request |
| `product-monitoring` | Non-Daily Cadences Acknowledge Their Trigger Without Reporting | A non-daily cadence is triggered |

Seven scenarios; the tests that covered them are in the obsolete list below.

## DERIVED tests, not themselves a `#### Scenario:` block

Each is labelled `DERIVED` in its own docstring, with the artifact it traces
to, so an invented constraint is reviewable as one.

First pass:

- `test_job_runner_schedules.py::test_the_run_performed_on_return_is_the_most_recent_missed_window` — the missed-window requirement's own reason clause. The scenario fixes the *count*; this fixes *which*.
- `test_job_runner_schedules.py::test_a_worker_that_never_went_away_defers_nothing_extra` — same requirement, applied to a running worker rather than a returning one.
- `test_daily_digest_job.py::test_the_declared_schedule_becomes_due_once_a_day_at_06_00` — the 06:00 hour and daily recurrence come from tasks.md 2.4.
- `test_daily_digest_job.py::test_every_intermediate_attempt_stays_silent_and_the_last_one_posts` — the "one outage, one message" reason clause.
- `test_daily_digest_job.py::test_the_registry_this_file_reads_is_the_one_the_worker_defers_from` — design.md's registration-by-import point.
- `test_scheduled_run_history.py::test_a_failed_run_does_not_count_as_a_success` — the last-success scenario read strictly.
- `test_no_external_cadence_trigger.py::test_the_application_still_serves_its_remaining_routes`.
- All of `test_alembic_runner_schema_guard.py` — tasks.md 1.1a, 1.6, 1.6b, 1.7 and design.md's autogenerate hazard.
- `test_compose_worker_service.py`'s labelled group: `::test_the_cron_service_and_its_network_are_gone`, `::test_the_worker_runs_the_same_image_as_the_application`, `::test_the_workers_inherited_http_healthcheck_is_disabled`, `::test_the_worker_waits_for_both_postgres_and_the_migrating_app`, `::test_the_worker_has_no_public_http_surface`, `::test_the_schedule_reading_services_declare_their_timezone`.
- `test_trigger_secret_is_no_longer_declared.py::test_the_direct_read_permission_no_longer_cites_the_removed_guard` — tasks.md 4.3a.

Second pass:

- `test_periodic_defer_dedup.py::test_the_deduplication_key_is_the_tick_itself` — design.md's named mechanism (`UNIQUE (task_name, periodic_id, defer_timestamp)`), asserted against the database catalogue. No scenario asks for it; it exists so that a schema change dropping the constraint fails with the reason rather than only with a second digest six hours later. The behavioural test beside it is the specified one.
- `test_compose_worker_service.py::test_the_members_of_the_network_postgres_is_on_are_this_applications_own` — **partly derived.** The non-external requirement and the every-attached-service clause are specified; the membership *set* (`app`, `postgres`, `worker`) comes from tasks.md 3.2 and 3.4, not from a scenario. A service added to `app_db` later fails this test on purpose.

## Assertion classification

Per `ai-toolkit:testing`'s specified / derived / deliberately-untested rule,
marked inline in each file with `SPECIFIED` / `DERIVED` / `DELIBERATELY
UNTESTED` comments. Summary:

- **Specified** — every assertion in the covered-scenario tests listed in the
  tables above, except where a docstring says otherwise.
- **Derived** — the tests listed under "DERIVED tests" above; plus, inside
  otherwise-specified tests: reading "the run is recorded as failed" as *the
  job body raises* and "recorded as succeeded / not retried" as *it returns
  normally*; reading "logged" as at least one record at `WARNING` or above;
  reading "nothing is there to start the work" as HTTP 404; reading the
  reported last-success time as bounded by the run rather than equal to a
  named timestamp; reading the distinct never-succeeded result as `None`.
  Second pass adds: reading "one run, not several" as one row in the run
  history carrying the marker that deferral used; reading "its end is the
  moment of the outcome that stopped it" as *at or after the last attempt's
  start* rather than as an exact timestamp (nothing fixes a clock source);
  and reading "configures logging before performing its own work" as *an
  informational record emitted at the moment the entrypoint begins its work
  reaches stderr* — that being the only observation a process boundary
  offers.
- **Deliberately untested** — the exact wording of the "no products exist"
  message and of the database-read-failure message; which timezone the
  schedule is configured *in*, beyond the single 06:00-UTC assertion; the
  retry maximum and backoff base themselves. Second pass adds: **the number
  of attempts a retried run makes** (the span test asserts "more than one"
  and takes the first and last, so changing the retry maximum does not
  touch it); and **which physical timestamp the run history should expose as
  a run's start** through an accessor — no accessor for it exists in this
  change, so the test asserts the history *carries* the shape, not that
  something reads it out.

## Obsolete tests — candidates for human confirmation

**Every entry below is a candidate, not a conclusion.** No entry was acted
on by either pass. The search was bounded to the dispatched test-path glob
(`tests/**/test_*.py`), by grepping it for `TRIGGER_SECRET`, the five cadence
paths, `trigger_guard`, `cron` and `internal-trigger`. The second pass
additionally re-ran that search and re-checked each entry's present state.
The first pass had no earlier `test-manifest.md` to draw on; the second pass
used the first pass's, which is how the entries below survive intact.

### Superseded outright — the behaviour under test is removed

| Test | Superseded by | Evidence | State as of the second pass |
|---|---|---|---|
| `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py` (whole file) | `internal-trigger` REMOVED — all four requirements | Exercises `require_trigger_secret` from the module the REMOVED delta's Migration note deletes; its four test groups map one-to-one onto the four removed requirements. | **Deleted by the implementer** (tasks.md 4.4). |
| `tests/unit/products/infrastructure/driving/test_monitoring_routes.py` (whole file) | `product-monitoring` REMOVED "Each Cadence Has Its Own Guarded Trigger Endpoint" and "Non-Daily Cadences Acknowledge Their Trigger Without Reporting"; and, for its four remaining tests, the three MODIFIED requirements that replace a response status with a run outcome | Two of its tests cite the removed requirements' scenarios by name; the other four cover behaviour the change keeps but through the endpoint it removes. Their substance is re-covered in `test_daily_digest_job.py`. | **Deleted by the implementer** (tasks.md 4.1/4.4). |
| `tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py::test_route_is_registered` (5 parametrizations) | `scheduled-jobs` ADDED "Scheduled Work Is Not Reachable From Outside The Deployment"; `product-monitoring` ADDED "The daily cadence cannot be started from outside the deployment" | Asserts each cadence path is mounted (`!= 404`); the new requirement asserts none is. Direct contradiction with `test_no_external_cadence_trigger.py::test_a_request_to_a_retired_cadence_path_finds_nothing`. | **Done** — the file remains, its cadence-path assertions gone. |

**Not obsolete in that file:** `test_main_monitoring_wiring.py`'s other two
tests are `deploy-pipeline` regression guards whose subject survives. They
belong to the amendment group below, not the deletion group.

### Stale transcription — amend, do not delete

Each tests the configuration declaration rather than the trigger guard, and
transcribes `TRIGGER_SECRET` into a set that must stay in step with
`Settings`.

| Test file | Line(s) | State as of the second pass |
|---|---|---|
| `tests/unit/shared/application/test_settings.py` | 62 | Amended. |
| `tests/unit/shared/application/test_settings_env_drift.py` | 60 | Amended. |
| `tests/unit/test_preflight.py` | 66, 195 | Amended, with another required variable substituted at the three-variable case per tasks.md 4.5a — the count is still three. |
| `tests/unit/test_startup_without_configuration.py` | 57 | Amended. |
| `tests/unit/shared/infrastructure/test_logging_process_boundary.py` | 62 | Amended (tasks.md 4.5b — the fifth file, named by neither proposal.md nor 4.5). |
| **`tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py`** | **51** | **Still transcribes `TRIGGER_SECRET`.** A candidate, not a conclusion: it is stale rather than breaking (`Settings` sets `extra="ignore"`), and tasks.md 4.7's grep is what would otherwise surface it. |

Two further live hits the same grep finds, recorded so the implementer can
judge them rather than discover them at 4.7:
`tests/unit/test_no_external_cadence_trigger.py:61` and
`tests/unit/test_http_serves_without_a_worker.py:106`. Both are this
change's *own* new tests, which name `TRIGGER_SECRET` as a variable to
**withhold** from an environment; whether they should still name a variable
that no longer exists is a judgement about the fixture, not about the
assertion, and neither breaks either way.

### Nothing found, stated explicitly

- **No test was found bearing on the run history's start/end shape** beyond
  `test_scheduled_run_history.py` itself. The requirement's "A run spans its
  retries" paragraph is new in this revision, and nothing predates it. This
  is "no such test exists", not "none was found".
- **No test was found bearing on `app_db`'s membership.** The only test in
  the project that reads `docker-compose.yml` at all is this change's own
  `test_compose_worker_service.py`. "No such test exists."
- **No test was found bearing on the worker entrypoint's logging.**
  `test_logging_process_boundary.py` covered `preflight` and the HTTP path;
  the worker did not exist. "No such test exists."
- **No obsolete test arises from the four second-pass gaps.** All four are
  additions: `scheduled-jobs`' recording requirement gained a paragraph,
  `deploy-pipeline` gained a scenario, and 5.14 comes from an unchanged
  requirement in another capability. Nothing existing asserted the opposite
  of any of them.

## Unresolved project questions

Recorded rather than resolved: this pass has no channel to ask on. Each names
the assumption taken and the tests that depend on it.

**Resolved since the first pass** (recorded so the trail is readable): the
runner application object is
`commerce_ops.shared.infrastructure.driven.job_runner.app`; the last-success
accessor is `...driven.job_history.last_successful_run(task_name) -> datetime
| None` returning `None` for never; the autogenerate filter is
`...driven.alembic_include.include_name`. All three were assumptions in the
first pass and are now facts of the implemented code, so the tests that
depended on them execute rather than erroring.

Open:

1. **How the daily job module names its collaborators.** **Assumed:** it
   imports `run_daily_digest`, `post_monitoring_message` and `session` by
   name into its own namespace. **Depends on it:** the behaviour tests in
   `test_daily_digest_job.py`, via `monkeypatch.setattr(..., raising=True)`.
2. **Which async test plugin this project standardizes on.** No convention
   file records one. **Assumed:** `anyio`, pinned to the asyncio backend,
   matching every existing async test file. **Depends on it:** every async
   test file this change adds.
3. **Where the worker entrypoint's "own work" begins.** **Assumed:**
   `procrastinate.App.run_worker` / `run_worker_async` — the seam a stub can
   stand in for, and the only one a test can name without reading
   `worker.py`. **Depends on it:** both worker tests in
   `test_logging_process_boundary.py`. If the entrypoint does substantial
   work *after* that call, this test does not see it; if it is restructured
   so the worker is started some other way, the stub stops standing in and
   the printed precondition marker fails first, naming the reason.
4. **Whether `app_db`'s membership set is meant to be closed.** tasks.md
   3.2/3.4 put exactly `app`, `postgres` and `worker` on it, and the delta
   requires every member to be a service this file defines. **Assumed:**
   closed — a fourth member is a decision to be made, not a detail. **Depends
   on it:** `test_the_members_of_the_network_postgres_is_on_are_this_applications_own`.
   If a later change adds a legitimate fourth service, that test is the
   place the decision gets recorded; updating it then is a change to a
   derived assertion, recorded as one, not a weakening.
5. **No bundled skill matches this stack.** `ai-toolkit:testing` (the floor)
   and `python` (pytest idiom) were loaded; there is no skill for
   `procrastinate`, SQLAlchemy, Docker Compose or FastAPI testing. Recorded
   per the dispatch contract; both passes proceeded on the floor plus
   `python`.
6. **Whether "the run is recorded as failed" may be asserted at the job
   body's level at all.** **Assumed:** yes — a job body's only outcome signal
   is raising or returning. **Depends on it:** `test_daily_digest_job.py`'s
   database-failure and Slack-failure tests.

## Findings that belong to the change's artifacts, not to this pass

Reported rather than acted on; neither pass edits `proposal.md`, `design.md`,
`tasks.md` or the delta specs.

Carried forward from the first pass, still standing:

1. **The `TRIGGER_SECRET` amendment list was one file short** — the fifth was
   `test_logging_process_boundary.py:62`, now amended under tasks.md 4.5b.
   A sixth live transcription remains at
   `test_main_monitoring_wiring.py:51`; see the obsolete list.
2. **"Per run" in the run-history requirement is "per job" in the runner.**
   `procrastinate_jobs` carries one row per job with the final `status`;
   `procrastinate_events` carries `started` / `succeeded` / `failed` /
   `deferred_for_retry` rows, accumulating across retries. Confirmed again on
   the second pass against a live retried run: one job row (`attempts = 2`)
   and events `deferred, started, scheduled, deferred_for_retry, started,
   succeeded`. Both the first attempt's start and the stopping outcome are
   readable, which is what tasks.md 2.10 makes a precondition — and the query
   has to *choose*, which is why the requirement's new paragraph matters.

New on the second pass:

3. **A cross-test event-loop defect in the integration tier, now fixed in
   test infrastructure.** `last_successful_run` reads through the
   application's cached session provider (tasks.md 2.10a), which binds one
   asyncpg pool to whichever event loop first uses it — correct for a worker
   that runs one loop for its life, wrong for `pytest.mark.anyio`, which
   gives each test its own. Two tests in `test_scheduled_run_history.py`
   passed alone and failed as a file with "got Future attached to a
   different loop". Fixed by an autouse fixture in that file calling the
   provider's own `dispose_engine()` on both sides of each test. This is a
   property of the tests, not of the provider, and **no assertion was
   weakened to achieve it** — per `ai-toolkit:testing` this was a
   broken-fixture failure (state 3), which establishes nothing about the
   code either way until repaired. The fixture lives in the test file rather
   than in a `conftest.py` because a `conftest.py` falls outside the
   dispatched test-path glob.
4. **Three of the first pass's own test files fail `ruff check`** with
   `I001` (import block un-sorted): `test_daily_digest_job.py:70`,
   `test_alembic_runner_schema_guard.py:43`,
   `test_job_runner_schedules.py:53`. This project sorts `commerce_ops`
   imports into their own first-party block after third-party; those three
   interleave them. `uv run ruff check tests/ --fix` resolves all three and
   changes nothing but import order. Left for the implementer rather than
   fixed here, because the additive-only rule binds the second pass to the
   first pass's files exactly as it binds it to anyone else's. Files touched
   on the second pass are clean under both `ruff check` and `ruff format
   --check`.
5. **One first-pass file fails `mypy`**: `test_daily_digest_job.py:116`
   (`Missing type arguments for generic type "PeriodicTask"`), plus two
   pre-existing `no-any-return` errors at `test_compose_worker_service.py:67`
   and `:72`. Same reasoning as above. (`alembic/env.py:59` and `:72` also
   fail `mypy` against the installed Alembic's `include_name` signature —
   that is implementation, and tasks.md 6.1 will surface it.)
6. **The implementation bound was crossed once, narrowly and deliberately.**
   To write the engine-disposal fixture, `dispose_engine`'s body in
   `shared/infrastructure/driven/database.py` was read, to establish whether
   it also clears the factory cache (it does, so the fixture needs no second
   call). That module belongs to the already-landed
   `centralize-database-session`, is not the behaviour under test here, and
   no assertion in this pass says anything about it. Nothing in
   `worker.py`, `daily_digest_job.py` or `job_history.py` — the code these
   tests are *about* — was read by either pass.

## Baseline

**Second pass** — full, taken before any file was written, with the
implementation as it then stood:

```
uv run pytest tests/unit tests/agents -q
12 failed, 252 passed, 4 errors in 9.82s
```

The 12 failures and 4 errors were all attributable to unimplemented tasks at
that moment (`worker` absent from `docker-compose.yml`, the cadence routes
still mounted, `TRIGGER_SECRET` still declared) — that is, to the change's
own not-yet-done work, not to anything this pass added.

Integration tier, at the same moment, against the throwaway Postgres with the
migration applied (`DATABASE_URL=postgresql+asyncpg://commerce_ops:probe@localhost:55432/commerce_ops`):

```
uv run pytest tests/integration/shared -q
2 failed, 5 passed
```

Both failures were the event-loop defect described under Findings 3, reported
by the implementer and reproduced here before anything was changed.

**After this pass**, with the implementation as it now stands:

```
uv run pytest tests/ -q          (DATABASE_URL set as above)
280 passed in 11.60s
```

Every test this pass added executes and passes, which — per the second
pass's situation, above — is the expected result rather than an alarm,
because the code under test now exists. Each was additionally checked for
discriminating power against the state its absence would produce:

- **`test_a_tick_that_already_ran_is_not_run_again_after_a_restart`** — with
  the deduplication key defeated (the same tick re-offered under a different
  `periodic_id`), a second job *is* created and the assertion fails.
  Verified directly.
- **`test_the_deduplication_key_is_the_tick_itself`** — the
  `(task_name, periodic_id, defer_timestamp)` key exists on
  `procrastinate_periodic_defers` and on no other runner table; querying the
  catalogue for any other table returns nothing matching.
- **`test_a_retried_run_is_one_record_spanning_its_attempts`** — asserts a
  *strict* inequality between the run's start and the successful attempt's
  start, so a history that took its start from the attempt that succeeded
  fails it; the retry itself is a precondition assertion, so a run that
  never failed fails the test rather than passing it vacuously.
- **`test_the_worker_entrypoint_configures_logging_before_its_own_work`** —
  with logging unconfigured, an informational record reaches nothing
  (verified: Python's `lastResort` handler emits `WARNING` and above only),
  so the marker's presence in stderr is evidence of the call and not of the
  default. The printed precondition marker separates "the entrypoint never
  started its worker" from "it started one with logging unconfigured".
- **`test_the_members_of_the_network_postgres_is_on_are_this_applications_own`**
  — asserts set equality, so both a missing `worker` and an extra member
  fail it. `app_db` had two members before this change and the test would
  have failed then.
