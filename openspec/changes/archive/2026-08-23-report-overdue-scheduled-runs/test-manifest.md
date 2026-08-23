# Test manifest — `report-overdue-scheduled-runs`

Written by a test-authoring pass that derived every test below from
`specs/scheduled-jobs/spec.md` at this change root, before any of the
change's implementation existed. It reads the delta spec, `proposal.md`,
`design.md`, `tasks.md`, the published specs under `openspec/specs/`, the
project's convention files, and the existing tests. It never read the
implementation of the behaviour under test, because there is none yet.

**This file is not part of the OpenSpec schema.** It will not appear among
`openspec instructions apply`'s context files and has to be opened on
purpose. Whoever implements this change should read it before starting:
it records which tests each task must make pass, which assertions were
invented rather than specified, and the seam names the tests assume.

**This pass added tests and subtracted nothing.** No existing test file was
edited, deleted or disabled, and no implementation — not a module, not a
function, not an empty stub — was written to make an absent import resolve.

---

## Baseline

| | |
| --- | --- |
| Command | `uv run pytest` (full suite) |
| Result before this pass | **263 passed, 32 skipped, 0 failed** in 10.8 s |
| Command | `uv run mypy .` |
| Result before this pass | **8 errors in 7 files**, all `attr-defined` of the `Module "X" has no attribute "y"` kind that `strict = true` + `no_implicit_reexport` produces in existing test files. Pre-existing and out of scope. |

The 32 skips are the `tests/integration/` tier skipping for want of
`DATABASE_URL`, which is the documented behaviour of that tier.

**A caveat that matters for re-reading this baseline.** Another session is
working in the same working tree on `introduce-catalog-and-shared-vocabulary`.
Between the baseline run and the end of this pass, six test files appeared
that were not present at baseline —
`tests/unit/catalog/application/test_list_products_empty_catalog.py`,
`tests/unit/catalog/domain/test_product_lifecycle.py`,
`tests/unit/shared/domain/test_identity_value_objects.py`,
`tests/unit/shared/domain/test_lifecycle_stage.py`,
`tests/integration/catalog/test_catalog_products.py`,
`tests/integration/products/test_launch_position_repository.py` — and each
fails to collect on its own absent targets. They are not this pass's, were
not touched by it, and a later full-suite run will show their collection
errors alongside this change's. Attribute failures by file, not by count.

---

## What every new test's failure currently establishes

Every test written by this pass fails, and each failure is
**failure-state 2 — the target does not exist**, per `ai-toolkit:testing`'s
taxonomy. Nothing passed on its first run, so there is no state-4 alarm to
investigate. The assertions have therefore never executed, and whether they
are any good is still unverified — that becomes readable only once the
implementation lands.

The concrete shapes, at the time of writing:

- `ModuleNotFoundError: No module named 'commerce_ops.registrations'`
  (tasks 1.3) — nine files.
- `ModuleNotFoundError: No module named
  'commerce_ops.shared.infrastructure.driven.recurring_work'` (tasks 1.1)
  — reached in the fresh-interpreter subprocess of
  `test_registrations_across_processes.py`.
- `ImportError: cannot import name 'MonitoringNotifier' from
  'commerce_ops.shared.application'` (tasks 2.1, 2.2) — one file.

### Lint and type-check state of the new files

`uv run ruff check` and `uv run ruff format --check` pass on all eleven new
files. `uv run mypy .` reports **13 further errors, all attributable to
absent targets**, and none of the kind that would survive implementation:

- 11 × `Skipping analyzing "commerce_ops.registrations" / ".recurring_work"`
  — resolves when tasks 1.1 and 1.3 land.
- 1 × `Module "commerce_ops.shared.application" has no attribute
  "MonitoringNotifier"` — resolves when tasks 2.1 and 2.2 land.
- 1 × `Library stubs not installed for "croniter"` in
  `test_recurring_work_registry.py` — **this is exactly the error tasks.md
  1.6c predicts**, and it resolves when `types-croniter` is added to the
  `dev` dependency group. Until then it blocks the `mypy` commit hook.

Two type errors this pass did introduce were fixed before finishing, and
the fixes are worth knowing about because they shape how two things are
written:

- `"BaseRoute" has no attribute "endpoint"`. The freshness route's endpoint
  function is read with `getattr(route, "endpoint", None)` plus an assert,
  rather than by narrowing to a FastAPI-internal class.
- `Module "commerce_ops.products.infrastructure.driven" has no attribute
  "slack_notifier"`, the same `no_implicit_reexport` class as the eight
  baseline errors. Avoided by
  `import commerce_ops.products.infrastructure.driven.slack_notifier as
  products_slack_notifier` — an alias that differs from the module's own
  basename, because ruff's `PLR0402` rewrites the same-name form back into
  the `from ... import ...` one that mypy rejects.

One further cosmetic note. Ruff's isort currently classifies
`commerce_ops.registrations` as **third-party**, because no such module
exists for it to resolve against `src/`. Once tasks 1.3 lands, `ruff check`
will report `I001` on the nine files that import it and want the import
moved into the first-party block. That is a formatting fix on an import
line, not a change to any test.

---

## Files added

All paths are absolute-from-repository-root. Tiering follows `AGENTS.md`:
`tests/unit` runs at `pre-commit` and is I/O-free; `tests/integration` runs
at `pre-push`.

| File | Tier | Covers |
| --- | --- | --- |
| `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py` | unit | Registry: tolerance-per-periodic, schedule identity, longest-gap, worker liveness |
| `tests/unit/test_registrations_across_processes.py` | unit (subprocess) | Both composition roots hold the same registration |
| `tests/unit/shared/application/test_monitoring_notifier_port.py` | unit | The `MonitoringNotifier` port (derived; no scenario) |
| `tests/unit/shared/infrastructure/driving/test_overdue_check.py` | unit | Overdue determination, reporting, suppression |
| `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py` | unit | The freshness endpoint's normal serving |
| `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness_unreadable.py` | unit | Unreadable state (setting), cache exemption |
| `tests/unit/shared/infrastructure/driving/test_overdue_consumers_agree.py` | unit | Check and endpoint reach the same verdict |
| `tests/integration/shared/test_known_work_anchor.py` | integration | The anchor, durably |
| `tests/integration/shared/test_overdue_report_suppression_store.py` | integration | Suppression survives the writing connection |
| `tests/integration/shared/test_scheduled_runs_freshness_cache.py` | integration | A cache hit anchors work that has none |
| `tests/integration/shared/test_scheduled_runs_freshness_unreachable.py` | integration | Unreachable database, bounded in time |

`tests/integration/shared/test_scheduled_runs_freshness_unreachable.py` is
in the `pre-push` tier because it opens real TCP connections, but it
**does not skip when `DATABASE_URL` is unset**: it supplies its own
unreachable address. The other three integration files skip as the tier
does.

---

## Scenario coverage — 32 of 32 accounted for

The delta spec contains 32 `#### Scenario:` blocks across 6 requirements.
Every one is covered by at least one named test. **None is uncovered.**

Test names are given as pytest node IDs, selectable individually with
`uv run pytest '<node id>'`.

### Requirement: Each Piece Of Recurring Work Declares Its Schedule And Tolerance In One Place

| # | Scenario | Test |
| --- | --- | --- |
| 1 | Every piece of work the runner will run has a tolerance | `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_every_piece_of_work_the_runner_will_run_has_a_tolerance` |
| 2 | The schedule run and the schedule checked are the same value | `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_the_schedule_run_and_the_schedule_checked_are_the_same_value` |
| 3 | A tolerance exceeds its work's longest scheduling gap | `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_each_tolerance_exceeds_its_works_longest_scheduling_gap` |
| 4 | Every consumer reads the same declaration | `tests/unit/shared/infrastructure/driving/test_overdue_consumers_agree.py::test_both_consumers_reach_the_same_verdict_from_the_same_declaration` |
| 5 | Every process holds the same registration | `tests/unit/test_registrations_across_processes.py::test_both_composition_roots_hold_the_same_registration` |

Scenario 1 is enumerated **from the runner's periodic registry, not from
the tolerance registry**, per tasks.md 1.6b. The guard against that
enumeration being circular is
`test_recurring_work_registry.py::test_a_periodic_missing_from_the_registry_is_caught`
(tasks.md 6.20) — derived, not a scenario of its own.

Scenario 5's guard against two empty registries comparing equal is
`test_registrations_across_processes.py::test_each_root_registers_work_at_all`
— derived, not a scenario.

### Requirement: Work Is Overdue Relative To Its Last Success Or To When It Was First Known

| # | Scenario | Test |
| --- | --- | --- |
| 6 | Work is overdue after its tolerance elapses since its last success | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_work_is_overdue_after_its_tolerance_elapses_since_its_last_success` |
| 7 | Work that has never succeeded becomes overdue after its tolerance | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_work_that_has_never_succeeded_becomes_overdue_after_its_tolerance` |
| 8 | A freshly deployed system does not report work as overdue immediately | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_a_freshly_deployed_system_does_not_report_work_as_overdue_immediately` |
| 9 | Work within its tolerance is not overdue | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_work_within_its_tolerance_is_not_overdue` |
| 10 | A worker that never started still produces an anchor | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_a_request_anchors_every_registered_piece_of_work` **and** `tests/integration/shared/test_known_work_anchor.py::test_a_worker_that_never_started_still_produces_an_anchor` |
| 11 | A later observation does not advance the anchor | `tests/integration/shared/test_known_work_anchor.py::test_a_later_observation_does_not_advance_the_anchor` |
| 12 | A success does not erase the first-known time | `tests/integration/shared/test_known_work_anchor.py::test_a_success_does_not_erase_the_first_known_time` |

Scenario 10 is split deliberately. Its second clause — "SHALL become
overdue once its tolerance has elapsed since that time" — is asserted in
the unit test, where the anchor can be aged past a tolerance without
waiting out a real one. Its first clause is asserted in both tiers,
because a row that exists only in a double is not a recorded time.

Scenarios 11 and 12 are integration-only: idempotence of an upsert and the
independence of two tables' lifecycles are properties of the schema and the
statement, not of a Python function, and an in-memory double asserts only
that the double behaved as the test wrote it.

Scenario 12 is exercised **through the operation a success performs** — the
suppression record being cleared, which tasks.md 3.6 pairs in the same
breath with "Do not clear the first-known row". Recorded as a reading
rather than left implicit: a fully faithful version would defer and run a
real job through the runner to produce a genuine success event. See
"Deliberately untested" below.

### Requirement: Overdue Work Is Reported To Slack From Inside The Deployment

| # | Scenario | Test |
| --- | --- | --- |
| 13 | Overdue work is reported | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_overdue_work_is_reported_naming_it_and_its_last_success` **and** `...::test_work_that_has_never_succeeded_is_reported_as_never_having_succeeded` |
| 14 | Work within its tolerance is not reported | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_work_within_its_tolerance_is_not_reported` |
| 15 | Work with no declared schedule is never reported | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_work_with_no_declared_schedule_is_never_reported` |
| 16 | Overdueness during an absent worker remains visible | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_freshness_is_reported_while_no_worker_is_running` |

Scenario 16's whole content is that the overdueness arising while no worker
is available is reported *by the freshness interface* — the in-deployment
check cannot observe its own process's absence. It is therefore covered by
an endpoint test, not a check test. Scenario 13 needs two tests because the
requirement's "or" is a real branch: naming when the work last succeeded,
and naming that it never has.

### Requirement: The Process Running Scheduled Work Is Itself Monitored Work

| # | Scenario | Test |
| --- | --- | --- |
| 17 | A completed evaluation records a successful run despite a failed delivery | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_a_completed_evaluation_records_a_successful_run_despite_a_failed_delivery` |
| 18 | The freshness interface is unaffected by a reporting-channel outage | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_the_freshness_interface_is_unaffected_by_a_reporting_channel_outage` |
| 19 | The worker's own liveness is monitored work | `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_the_workers_own_liveness_is_monitored_work` |
| 20 | An absent worker becomes visible well before the work it runs is overdue | `tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_an_absent_worker_becomes_visible_before_the_work_it_runs` |

### Requirement: A Continuing Outage Is Reported Once, Not Repeatedly

| # | Scenario | Test |
| --- | --- | --- |
| 21 | A continuing outage is not reported repeatedly | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_a_continuing_outage_is_not_reported_repeatedly` |
| 22 | A failed delivery leaves the work eligible to be reported again | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_a_failed_delivery_leaves_the_work_eligible_to_be_reported_again` |
| 23 | A restart does not resume reporting | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_a_restart_does_not_resume_reporting` **and** `tests/integration/shared/test_overdue_report_suppression_store.py::test_a_delivered_report_stays_suppressed_across_a_restart` |
| 24 | Overdueness recurring after a success is reported again | `tests/unit/shared/infrastructure/driving/test_overdue_check.py::test_overdueness_recurring_after_a_success_is_reported_again` |

Scenario 23 is the one scenario in this requirement that in-memory
suppression would fail, so it is covered at both levels: the unit test
fixes that the check reads suppression from the store rather than from
anything it remembers, and the integration test fixes that the record
survives the connection that wrote it.

### Requirement: Run Freshness Is Reportable Over HTTP

| # | Scenario | Test |
| --- | --- | --- |
| 25 | Freshness is reported | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_freshness_is_reported_for_each_piece_of_recurring_work` |
| 26 | Unhealthy is signalled so an automated checker can act on it | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_unhealthy_is_signalled_so_an_automated_checker_can_act_on_it` **and** `...::test_nothing_overdue_answers_two_hundred_and_ok` |
| 27 | Freshness is reported while no worker is running | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_freshness_is_reported_while_no_worker_is_running` |
| 28 | A freshly deployed system reports healthy | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_a_freshly_deployed_system_reports_healthy` |
| 29 | The endpoint does not consult the process running scheduled work | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py::test_the_endpoint_does_not_consult_the_process_running_scheduled_work` |
| 30 | Recorded state that cannot be read is not reported as healthy | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness_unreadable.py::test_an_absent_connection_setting_is_not_reported_as_healthy`, `...::test_a_malformed_connection_setting_is_not_reported_as_healthy`, `tests/integration/shared/test_scheduled_runs_freshness_unreachable.py::test_a_refused_database_connection_is_not_reported_as_healthy`, `...::test_a_database_that_never_answers_is_not_waited_on_indefinitely` |
| 31 | A recent healthy answer is not repeated once the state cannot be read | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness_unreadable.py::test_a_recent_healthy_answer_is_not_repeated_once_the_state_cannot_be_read` |
| 32 | A repeated request still anchors work that has no first-known time | `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness_unreadable.py::test_a_repeated_request_still_anchors_every_registered_piece_of_work` **and** `tests/integration/shared/test_scheduled_runs_freshness_cache.py::test_a_repeated_request_anchors_work_that_has_none_at_that_moment` |

Scenario 26 needs two tests because tasks.md 6.12 asks for the exact codes
in both directions: an implementation answering 503 unconditionally would
satisfy the scenario's letter while making the endpoint useless.

Scenario 30 needs four because the three conditions tasks.md 5.8/5.8a/5.8b
name fail by different mechanisms: an absent setting and a malformed one
raise immediately at the point of use (`database-session`'s published
requirement), a refused connection raises from the network layer, and a
database that never answers only fails if a timeout exists. An
implementation catching only connection and timeout errors passes two of
these and fails the other two.

Scenario 32 is split by clause. Its first — the upsert runs on the repeated
request — is asserted in the unit tier. Its second — a time is recorded for
work that has none *at that moment* — cannot be observed against a double
that already anchored everything on the first request, which is the
vacuousness tasks.md 6.24 warns of; the integration test removes the rows
between the two requests, which is the only non-vacuous arrangement.

The cache's own existence, on which both clauses' preconditions rest, is
asserted by
`test_scheduled_runs_freshness_unreadable.py::test_a_repeated_request_is_not_re_evaluated`
(specified by tasks.md 5.7, not a scenario). It counts reads rather than
naming anything, so it holds however the cache is implemented.

---

## Assertion classification

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. Each test's docstring carries its own
classification; this section records the ones a reviewer should look at
first, because a derived assertion obliges the implementer to satisfy a
constraint nobody agreed to.

### Derived assertions — invented here, open to challenge

1. **How an overdue report names when the work last succeeded.**
   `test_overdue_work_is_reported_naming_it_and_its_last_success` asserts
   the message contains the **ISO date** of the last success. The scenario
   says "naming ... when it last succeeded", which is unobservable without
   fixing some rendering, and no artifact fixes one for a Slack message.
   The ISO date is the weakest recognizable form — present in
   `str(datetime)`, in `isoformat()`, and in the RFC 3339 rendering
   design.md fixes for the endpoint. A message naming the time in prose
   ("yesterday morning") fails here. If that is the deliberate choice,
   changing this assertion is a change to a derived assertion and should be
   recorded as one, not performed as a repair.

2. **How a report says the work has never succeeded.**
   `test_work_that_has_never_succeeded_is_reported_as_never_having_succeeded`
   asserts the word "never" appears (case-insensitively). The
   *distinction* between never-succeeded and succeeded-long-ago is
   specified; the word is derived, taken from the spec's own wording.

3. **What "within a bounded time" means numerically.** `BOUNDED_SECONDS`
   is 15 s in the unit file and 20 s in the integration one, with a 120 s
   ceiling after which the request is abandoned and the test fails rather
   than hanging the suite. design.md says only "a short timeout" and
   "promptly". These are generous by an order of magnitude or two: what
   they assert is the difference between answering and hanging, not a
   latency budget.

4. **Two guards that are not scenarios but keep scenarios honest.**
   `test_a_periodic_missing_from_the_registry_is_caught` (tasks.md 6.20)
   and `test_each_root_registers_work_at_all`. Both exist because the
   scenario they guard would otherwise hold vacuously.

5. **The whole of `test_monitoring_notifier_port.py`.** No scenario maps to
   it; it derives from tasks.md 2.1–2.3 and design.md. The mechanism is
   nonetheless machine-enforced — `.importlinter`'s `shared-boundary` — so
   if the structural satisfaction fails there is no legal route from the
   check in `shared` to the monitoring channel.

6. **`test_nothing_overdue_answers_two_hundred_and_ok`** as a separate
   test. tasks.md 6.12 names both codes; the scenario names only the
   unhealthy one.

### Specified-by-tasks rather than by a scenario

Recorded separately because they are not invented, but they trace to
`tasks.md`/`design.md` rather than to a `#### Scenario:` block:

- `test_registering_reads_no_configuration_at_import` — tasks.md 1.4a, and
  `runtime-configuration`'s published "Importing And Starting The
  Application Do Not Require Configuration To Be Present".
- `test_a_repeated_request_is_not_re_evaluated` — tasks.md 5.7.
- The fixed JSON shape asserted in
  `test_freshness_is_reported_for_each_piece_of_recurring_work` — design.md
  and tasks.md 6.11, which requires the *shape* be asserted rather than
  that the body merely contains the identifiers.
- The route being reachable only through `commerce_ops.main.app` — tasks.md
  5.2, "a green unit suite does not catch an unregistered router". Every
  endpoint test in this pass goes through `main.app`, so an unregistered
  router fails here rather than at deploy.

### Deliberately untested, with reasons

- **The exact tolerance figures** — the digest's 30 hours (tasks.md 1.5),
  the check's hourly interval (4.3) and its liveness tolerance (4.7).
  design.md's Open Questions call all three initial figures, better chosen
  after a few weeks of real run history. Scenario 3 (tolerance exceeds the
  longest gap) and scenario 20 (liveness tolerance shorter than every
  other) constrain them relationally instead, which is what the spec
  actually fixes. Pinning the numbers would make a deliberate revision look
  like a regression.
- **The exact overdue boundary.** Every overdue fixture places its last
  success an hour past the tolerance, and every within-tolerance fixture
  well inside it. Whether the comparison is `>` or `>=` at the exact
  instant is not fixed by the spec and is not worth a test that would
  fail on a rounding choice.
- **The exact count of registered periodics.** Deliberately left to
  `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py`,
  which tasks.md 4.3a amends to `== 2` — see the obsolete-test entry below.
  This pass's registry tests identify the overdue check by the placement
  tasks.md 4.1 fixes (`shared/infrastructure/driving/`), so a third piece
  of scheduled work added later fails the exact-count guard, as intended,
  rather than failing here too.
- **A genuine `succeeded` run event behind scenario 12.** The anchor's
  survival is exercised through the operation a success performs (clearing
  suppression), not by deferring and running a real job through the runner.
  Deferring a real job is what
  `tests/integration/shared/test_scheduled_run_history.py` already does for
  the prerequisite change; doing it again here would test the runner's
  recording rather than the anchor's independence, which is what this
  scenario is about.
- **That the freshness handler makes no outbound network call of any
  kind.** Scenario 29 is asserted structurally — the HTTP process does not
  import the worker entry point, in a fresh interpreter — plus the ambient
  fact that the endpoint serves correctly in a process with no worker. A
  general "no outbound call" assertion would have to intercept the HTTP
  client `TestClient` itself uses. Noted rather than attempted: the worker
  exposes no interface, port or route, so the module import is the only
  route by which the endpoint could reach it.
- **Rate limiting on the anonymous endpoint.** design.md names it as
  belonging at the edge if it is ever needed, and explicitly tasks nothing.

---

## Obsolete tests — candidates for human confirmation

This change carries **no `MODIFIED`, `REMOVED` or `RENAMED` delta**; its
one delta spec is a single `## ADDED Requirements` section. On the ordinary
reading that would make this list *not applicable*. It is not empty anyway,
because one existing test is made false by a task of this change, and the
dispatch supplied the evidence.

The search was bounded to the dispatched test-path glob `tests/**/test_*.py`.
No earlier `test-manifest.md` was supplied for this change, and none was
looked for.

### Entry 1 — candidate for human confirmation

| | |
| --- | --- |
| Test | `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py::test_exactly_one_piece_of_recurring_work_is_scheduled` |
| Superseded by | tasks.md 4.3 (schedule the overdue check hourly) and 4.3a, which directs the amendment |
| Evidence | The test asserts `len(registered) == 1` over the runner's periodic registry, with the message "expected exactly one scheduled piece of recurring work". Task 4.3 registers a second periodic, so the assertion becomes false the moment the check is scheduled. |
| Disposition | **Amend, do not delete.** tasks.md 4.3a requires it stay an *exact* count (`== 2`) and be renamed accordingly — not loosened to `>=`. The exact count is what forces a human to acknowledge each newly scheduled thing, which is a different guard from the one tasks.md 1.6b provides: 1.6b catches a periodic missing from the tolerance registry and would pass a stray or duplicated periodic that happens to carry a tolerance. |
| Not touched by this pass | This pass added tests and subtracted nothing. The amendment belongs to the implementation step. |

### Tests searched and found **not** obsolete

Recorded so that "no such test exists" is distinguishable from "none was
found". Each of these was inspected and bears on something this change
touches, and each should keep passing unmodified:

- `tests/unit/test_no_external_cadence_trigger.py` — enumerates every
  mounted path from the OpenAPI document and fails any path naming a
  monitoring cadence. `/health/scheduled-runs` names none of `monitoring`,
  `daily`, `weekly`, `biweekly`, `monthly`, `quarterly`, so adding the
  route leaves it passing. **Worth re-reading if the endpoint is ever
  renamed.**
- `tests/unit/test_startup_without_configuration.py` — starts `main.app`
  with every declared variable absent. tasks.md 1.4a and 3.2b both exist to
  keep it passing (no configuration read at import; no anchor write in the
  lifespan). Not superseded; it is a constraint on this change, not a
  casualty of it.
- `tests/unit/test_http_serves_without_a_worker.py` — asserts in a fresh
  interpreter that importing `commerce_ops.main` does not import
  `commerce_ops.worker`. Adding `registrations.py` to `main.py`'s import
  graph must not break it. This pass adds its own scenario-29 test rather
  than extending or relying on this one.
- `tests/unit/shared/infrastructure/test_logging_process_boundary.py` —
  runs `commerce_ops.worker` as `__main__` with the runner's loop stubbed.
  tasks.md 1.3a replaces the worker's own job-module import list with a
  `register_all()` call; that file asserts nothing about the list, so it is
  unaffected as long as 1.4a holds.
- `tests/unit/products/infrastructure/driving/test_daily_digest_job.py` —
  reaches the daily job by filtering the periodic registry for a name
  containing "daily" and never asserts a registry size, so a second
  periodic leaves it passing. It does `import commerce_ops.worker` to
  register the definitions, which keeps working after 1.3a.
- `tests/unit/shared/application/test_settings.py` — asserts `"Settings"`
  and `"get_settings"` are *in* `shared.application.__all__`, not that
  `__all__` equals a set, so adding `MonitoringNotifier` leaves it passing.
- `tests/unit/shared/infrastructure/driven/test_clickup_client.py::test_clickup_client_module_satisfies_the_writer_port_structurally`
  — the pattern tasks.md 2.3 mirrors. Untouched; the new port test is a
  sibling, not a replacement.

---

## Unresolved project questions

`ai-toolkit:testing` requires a question with no recorded answer to be
asked rather than assumed. This pass ran non-interactively with no channel
to ask on, so each question is recorded here with the assumption taken and
the tests that depend on it. **None of these was resolved silently.**

### Q1 — The overdue check's and the freshness route's collaborator seams

**This is by far the largest invented surface in this pass.** No artifact
fixes how either module reaches its collaborators.

*Assumption taken:* the by-name import pattern this project's existing
driving adapters use — `daily_digest_job.py` and the retired
`monitoring.py` both import collaborators by name into the module's own
namespace and reference them as bare globals, which is what lets tests
substitute them with `monkeypatch.setattr`. The names assumed:

In the **overdue check's** module namespace:

| Name | Shape | Note |
| --- | --- | --- |
| `registered_work()` | sync → registry | |
| `last_successful_run(name)` | async → `datetime \| None` | **Not invented** — already exists in `shared/infrastructure/driven/job_history.py` |
| `first_known_times()` | async → mapping | |
| `record_first_known(identifiers)` | async | Substituted only to keep the unit tier off the database; nothing asserts on it there |
| `suppressed_identifiers()` | async → set | |
| `record_report_delivered(identifier)` | async | Written only after a delivery succeeds (tasks.md 3.5) |
| `clear_report_suppression(identifier)` | async | Cleared when the work next succeeds (tasks.md 3.6) |
| `notifier` | module attribute | The `MonitoringNotifier` `worker.py` injects after `register_all()` (tasks.md 4.2) |

In the **freshness route's** module namespace: `registered_work`,
`last_successful_run`, `first_known_times`, `record_first_known`, and
`CACHE_SECONDS`.

*Depends on it:* `test_overdue_check.py` (all 13 tests),
`test_scheduled_runs_freshness.py` (all but the fresh-interpreter one),
`test_scheduled_runs_freshness_unreadable.py` (all but the two
connection-setting tests), `test_overdue_consumers_agree.py`, and — for
reaching the repositories without naming their modules —
`test_known_work_anchor.py`, `test_overdue_report_suppression_store.py`,
`test_scheduled_runs_freshness_cache.py`.

*How a mismatch shows up:* every one of these calls a `_substitute` /
`_collaborator` helper that fails with an instructive message naming the
module and the missing attribute, rather than raising a bare
`AttributeError`. Correcting a name is a **fixture correction**; the
assertions are about what is determined, posted and responded, not about
where the collaborators live.

Neither module's own path is invented: the check is found through the
runner's periodic registry filtered by the placement tasks.md 4.1 fixes,
and the route through `main.app.routes` filtered by the path design.md
fixes.

### Q2 — Where the schedule/tolerance registry lives, and its shape

*Assumption taken:*
`commerce_ops.shared.infrastructure.driven.recurring_work.registered_work()`.
tasks.md 1.1 says only "a registry in `shared`". It is placed in
`infrastructure/driven/` because `module-layers` forbids
`shared.application` from importing `shared.infrastructure`, while the
single registration helper of tasks.md 1.1a must apply the runner's
periodic decorator, which lives in `shared/infrastructure/driven/`.

The shape is accommodated rather than pinned: `registered_work()` may
return a mapping of identifier to entry or an iterable of entries; an entry
carries `schedule` (or `cron`) and `tolerance` (a `timedelta`) or
`tolerance_seconds` (a number); an identifier may be exposed as
`identifier`, `id`, `task_name` or `name`, and whether it equals the
runner's own task name is left open — design.md's illustrative JSON shows
`product-daily-digest` where the runner's task is `products.monitoring.daily`.
That accommodation is at fixture level; every assertion is made on the
normalized value.

*Depends on it:* `test_recurring_work_registry.py`,
`test_registrations_across_processes.py` (its `REGISTRY_MODULE` /
`REGISTRY_ACCESSOR` constants), `test_overdue_consumers_agree.py`.

### Q3 — Whether `register_all()` is called at import of each root

*Assumption taken:* yes, at module import of both `commerce_ops.worker`
and `commerce_ops.main` — `worker.py` today registers its job definitions
by importing them at module import, and `main.py` builds its `app` at
import. The subprocess in `test_registrations_across_processes.py` reads
each root **by import alone**, so a `register_all()` deferred into
`worker.main()` would fail it. The failure message says so explicitly.

### Q4 — The response cache's name

*Assumption taken:* a module-level `CACHE_SECONDS` on the route module,
substituted with `raising=False` everywhere. Consequence if it is named
otherwise: the endpoint tests that set it to zero cannot disable the cache,
and a cached answer can leak from one test to the next. That leak surfaces
as `test_a_repeated_request_is_not_re_evaluated` failing on a read count of
zero — a loud failure, not a silent pass. `CACHE_SECONDS` is the single
correction point.

### Q5 — The async test plugin

*Assumption taken:* `@pytest.mark.anyio` with a session-scoped
`anyio_backend` fixture pinned to `"asyncio"`, matching every existing
async test file in this project. `pyproject.toml` declares neither
`pytest-asyncio` nor an `asyncio_mode`; `anyio` arrives transitively with
FastAPI/Starlette and auto-registers its pytest plugin. This question is
already recorded as unresolved by
`tests/integration/products/conftest.py`; nothing has been decided since,
so it is carried forward rather than treated as settled.

### Q6 — Whether an integration test may delete rows

*Assumption taken:* yes, for `known_work` specifically.
`test_scheduled_runs_freshness_cache.py` issues `DELETE FROM known_work`
between two requests, because tasks.md 6.24 says in terms that any other
arrangement makes the test vacuous. The table holds only first-known
anchors and the very next request re-creates them. No project convention
records a truncate/rollback fixture for the integration tier — the existing
files instead generate unique identifiers per run, which the other new
integration tests here do too. This one cannot, since it is about the
absence of rows.

### Q7 — No conftest.py was added

The dispatched test-path glob is `tests/**/test_*.py`, which a
`conftest.py` does not match, so shared helpers are repeated per file
rather than extracted. That is why several files carry near-identical
`_route_module` / `_substitute` helpers. If the project would rather they
were shared, extracting them into a `conftest.py` is a refactor for
whoever holds the wider mandate — this pass wrote only inside the glob.

---

## What the implementation step must make pass

Grouped so a task can be run against exactly the tests it must satisfy.

| Tasks | Run |
| --- | --- |
| 1.1, 1.1a, 1.2, 1.5, 1.6, 1.6a–1.6c, 4.3, 4.7 | `uv run pytest tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py` |
| 1.3, 1.3a, 1.4, 1.4a, 1.4b | `uv run pytest tests/unit/test_registrations_across_processes.py` |
| 2.1, 2.2, 2.3 | `uv run pytest tests/unit/shared/application/test_monitoring_notifier_port.py` |
| 3.5, 3.6, 3.7, 4.1, 4.2, 4.4, 4.5, 4.6, 4.8 | `uv run pytest tests/unit/shared/infrastructure/driving/test_overdue_check.py` |
| 5.1–5.6, 3.2a | `uv run pytest tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py` |
| 5.7, 5.8, 5.8b | `uv run pytest tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness_unreadable.py` |
| 1.1 + 4.4 + 5.3 together | `uv run pytest tests/unit/shared/infrastructure/driving/test_overdue_consumers_agree.py` |
| 3.1–3.4, 5.8a | `uv run pytest tests/integration/shared/` (needs `DATABASE_URL` and `alembic upgrade head`, except the unreachable-database file, which needs neither) |
| 4.3a | Amend `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py::test_exactly_one_piece_of_recurring_work_is_scheduled` to an exact `== 2` — see the obsolete-test entry above |

Two mypy obligations are already visible from this pass's run and are worth
doing early, since `mypy` is a commit-time hook: `types-croniter` in the
`dev` group (tasks.md 1.6c) and `croniter` declared directly (1.6a).
