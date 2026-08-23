# Test manifest — introduce-launch-briefing

Written by `ai-toolkit:openspec-test-writer` from the change's delta specs
alone, before any implementation of this change existed. Not an artifact the
OpenSpec schema defines, so `openspec instructions apply` will not surface it
— read it on purpose before implementing.

**This pass is additive only.** No existing test was edited, deleted or
disabled. Everything under *Obsolete and affected tests* is a candidate for
human confirmation, never an action taken.

Test command: `uv run pytest`. Every identifier below is selectable
individually with it (`uv run pytest 'path::test_name'`).

---

## Baseline

Taken before any test was written, **scoped** to the commit-time tiers
`tests/unit` and `tests/agents`:

```
uv run pytest tests/unit tests/agents -q
→ 4 failed, 480 passed in 17.85s
```

Pre-existing failures, all in one file and all unrelated to this change:

- `tests/unit/shared/application/test_settings.py::test_absent_optional_variable_is_reported_as_absent_to_a_caller`
- `tests/unit/shared/application/test_settings.py::test_an_unrecognized_variable_in_the_environment_is_not_a_fault`
- `tests/unit/shared/application/test_settings.py::test_reading_configuration_opens_no_socket`
- `tests/unit/shared/application/test_settings.py::test_accessor_is_cached_across_calls`

All four fail on the same cause: `pydantic` rejects an empty
`clickup_launch_folder_id` in this environment's `Settings` construction
(`String should have at least 1 character`). They are red before this change
and are expected to stay red until that environment value is set; do not read
them as fallout from this pass.

**`tests/integration` was not run**, and is the scope this baseline excludes:
it requires a live Postgres, which is not available here. No test written in
this pass is in that tier, so nothing below depends on it.

---

## Scenario accounting

29 `#### Scenario:` blocks exist across this change's delta specs — 19 in
`briefing`, 2 in `shared-vocabulary`, 8 in `launch-instance`, 0 in
`product-monitoring` (its delta carries four `REMOVED` requirements and no
scenario blocks). All 29 are accounted for below: 29 covered, 0 uncovered.

### `specs/briefing/spec.md` (ADDED — new capability)

#### Requirement: Attention items are derived from every active launch

| Scenario | Covering test |
| --- | --- |
| An at-risk launch date yields a critical item | `tests/unit/briefing/application/test_briefing_assembly.py::test_an_at_risk_launch_date_yields_a_critical_item` |
| A gate awaiting confirmation yields a diagnose item | `tests/unit/briefing/application/test_briefing_assembly.py::test_a_gate_awaiting_confirmation_yields_a_diagnose_item` |
| An overdue non-blocking step yields a monitor item | `tests/unit/briefing/application/test_briefing_assembly.py::test_an_overdue_non_blocking_step_yields_a_monitor_item` |
| A healthy launch contributes nothing | `tests/unit/briefing/application/test_briefing_assembly.py::test_a_healthy_launch_contributes_nothing` |
| A graduated product's launch is not briefed | `tests/unit/briefing/application/test_briefing_assembly.py::test_a_graduated_products_launch_is_not_briefed` |
| An unresolvable product's launch is still derived from | `tests/unit/briefing/application/test_briefing_assembly.py::test_an_unresolvable_products_launch_is_still_derived_from` |

Requirement-statement coverage beyond the scenarios (each labelled in the
test's own docstring):

- `::test_a_retired_products_launch_is_not_briefed` — "neither steady-state
  **nor retired**"; no scenario names the retired half.
- `::test_every_active_launch_is_derived_from_not_merely_the_first` —
  "**every** active launch"; every scenario uses a single launch.

#### Requirement: Findings collapse by cause and the causal item leads

| Scenario | Covering test |
| --- | --- |
| Overdue blocking steps are absorbed by the at-risk item | `tests/unit/briefing/application/test_briefing_assembly.py::test_overdue_blocking_steps_are_absorbed_by_the_at_risk_item` |
| Overdue non-blocking steps in one discipline collapse into one item | `tests/unit/briefing/application/test_briefing_assembly.py::test_overdue_non_blocking_steps_in_one_discipline_collapse` |
| The causal item precedes the rest | `tests/unit/briefing/application/test_briefing_assembly.py::test_the_causal_item_precedes_the_rest` |

Requirement-statement coverage beyond the scenarios:

- `::test_overdue_non_blocking_steps_in_two_disciplines_do_not_collapse` —
  "one item **per discipline**".
- `::test_the_awaiting_confirmation_item_ranks_between_the_other_two` — the
  middle rank of the three-cause order, which the named scenario (first vs.
  third) leaves unconstrained.

#### Requirement: A clean briefing is not sent

| Scenario | Covering test |
| --- | --- |
| A clean day posts nothing | `tests/unit/briefing/application/test_briefing_delivery.py::test_a_clean_day_posts_nothing` |
| A briefing with items is delivered | `tests/unit/briefing/application/test_briefing_delivery.py::test_a_briefing_with_items_is_delivered` |

Plus `::test_a_clean_day_posts_nothing_even_with_no_launches_at_all` — the
empty-enumeration boundary of the same scenario.

#### Requirement: Items identify products by name and SKU, and never drop an item over naming

| Scenario | Covering test |
| --- | --- |
| A resolvable product is named | `tests/unit/briefing/application/test_briefing_delivery.py::test_a_resolvable_product_is_named` |
| An unresolvable product does not lose its item | `tests/unit/briefing/application/test_briefing_delivery.py::test_an_unresolvable_product_does_not_lose_its_item` |

Plus `::test_one_unresolvable_product_does_not_take_the_others_with_it` —
"never drop an item over naming", with a resolvable and an unresolvable
product in the same briefing.

#### Requirement: The daily briefing runs on a schedule

| Scenario | Covering test |
| --- | --- |
| The briefing runs when its schedule is due | `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py::test_the_briefing_has_a_declared_schedule` and `::test_the_declared_schedule_becomes_due_once_a_day` |
| The briefing cannot be started from outside the deployment | `tests/unit/test_briefing_not_externally_startable.py::test_no_externally_reachable_path_names_the_briefing` and `::test_a_request_to_a_briefing_trigger_path_finds_nothing` |

Plus `test_daily_briefing_job.py::test_the_briefing_inherits_the_retired_digests_schedule_slot`
— derived from `tasks.md` 5.2, not from a scenario; kept as its own test so a
deliberate change of slot fails there alone.

#### Requirement: Delivery failure is decoupled from the run

| Scenario | Covering test |
| --- | --- |
| A failed Slack post does not fail the run | `tests/unit/briefing/application/test_briefing_delivery.py::test_a_failed_slack_post_does_not_fail_the_run` |

#### Requirement: A failure to assemble is surfaced, not treated like a delivery failure

| Scenario | Covering test |
| --- | --- |
| A read failure on the final attempt fails the run and says so | `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py::test_a_read_failure_on_the_final_attempt_fails_the_run_and_says_so` |
| An intermediate failed attempt does not post | `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py::test_an_intermediate_failed_attempt_does_not_post` |
| An assembly failure is retried | `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py::test_an_assembly_failure_is_retried` |

Supporting tests, each labelled derived in its docstring:

- `test_briefing_delivery.py::test_a_read_failure_is_not_swallowed_like_a_delivery_failure`
  — the use-case half: a read failure propagates (`tasks.md` 4.4), without
  which the job-level scenarios are unreachable.
- `test_daily_briefing_job.py::test_one_outage_produces_exactly_one_message`
  — the requirement's own reason clause, across every attempt of one outage.
- `test_daily_briefing_job.py::test_successive_retries_are_declared_and_bounded`
  — retries must both back off and stop, or "once retries are exhausted"
  names a moment that never arrives.

### `specs/shared-vocabulary/spec.md` (ADDED)

| Scenario | Covering test |
| --- | --- |
| A known severity is constructed | `tests/unit/shared/domain/test_severity.py::test_a_known_severity_is_constructed` |
| An unknown severity is rejected | `tests/unit/shared/domain/test_severity.py::test_an_unknown_severity_is_rejected` |

Plus `::test_each_specified_tier_is_constructible`,
`::test_the_severity_set_is_exactly_the_three_reporting_tiers`, and
`::test_severity_values_compare_by_value_and_are_immutable`.

### `specs/launch-instance/spec.md` (ADDED)

| Scenario | Covering test |
| --- | --- |
| All launch positions are reported | `tests/unit/launch/application/test_launch_reports.py::test_all_launch_positions_are_reported` |
| No launches yields an empty enumeration | `tests/unit/launch/application/test_launch_reports.py::test_no_launches_yields_an_empty_enumeration` |
| A step entry carries its owning discipline | `tests/unit/launch/application/test_launch_reports.py::test_a_step_entry_carries_its_owning_discipline` |
| The at-risk evaluation names its overdue blocking steps | `tests/unit/launch/application/test_launch_reports.py::test_the_at_risk_evaluation_names_its_overdue_blocking_steps` |
| A satisfied confirmation gate without an approval awaits confirmation | `tests/unit/launch/application/test_launch_reports.py::test_a_satisfied_confirmation_gate_without_an_approval_awaits` |
| Unsatisfied blocking conditions mean the gate is not awaiting confirmation | `tests/unit/launch/application/test_launch_reports.py::test_unsatisfied_blocking_conditions_mean_not_awaiting` |
| A recorded approving approval ends the wait | `tests/unit/launch/application/test_launch_reports.py::test_a_recorded_approving_approval_ends_the_wait` |
| An automatic gate never awaits confirmation | `tests/unit/launch/application/test_launch_reports.py::test_an_automatic_gate_never_awaits_confirmation` |

Plus `::test_enumeration_does_not_filter_by_lifecycle` — the requirement
statement's "Enumeration SHALL NOT filter by lifecycle", using a launch
standing at the final gate with its graduation approval recorded.

### `specs/product-monitoring/spec.md` (REMOVED)

**Zero scenarios to account for**: the delta carries four `REMOVED`
requirements, each with a Reason and a Migration and no `#### Scenario:`
block. Removed behavior is not tested, and the surviving obligations are
re-expressed in `briefing`, where they are covered above. The eight scenarios
those four requirements carry in `openspec/specs/product-monitoring/spec.md`
are therefore accounted for as **uncovered, reason: removed by this change** —
all eight of them, each mapped below to where its obligation now lives, per
the delta's own Migration notes:

| Removed main-spec scenario | Where the obligation now lives |
| --- | --- |
| Daily trigger lists product names | nowhere — the listing itself is retired |
| No products exist | nowhere — same |
| Slack post fails | `briefing` — Delivery failure is decoupled from the run |
| Database read fails | `briefing` — A failure to assemble is surfaced … |
| An intermediate failed attempt does not post | `briefing` — same requirement |
| A database read failure is retried | `briefing` — same requirement |
| The daily cadence runs when its schedule is due | `briefing` — The daily briefing runs on a schedule |
| The daily cadence cannot be started from outside the deployment | `briefing` — same requirement |

---

## Assertion provenance

Every assertion is labelled in its own test's docstring or an inline
`# SPECIFIED:` / `# DERIVED:` comment. Summary of what is **not** specified:

**Derived assertions** (inferred; no delta-spec statement covers them)

- `Severity` is an `Enum` constructed by value, rejecting with `ValueError`;
  wire values are lower-case (`"critical"`). Follows `Discipline`'s recorded
  precedent, which the requirement points at by name.
- Severity rendering in the delivered message is read case-insensitively
  (`"critical" in message.lower()`).
- "Logged" is read as at least one log record at `WARNING` or above.
- "The run is recorded as failed" is read as the callable raising; "recorded
  as succeeded" / "not retried" as it returning normally. The reading the
  retired digest's job tests already recorded for the same words.
- HTTP 404 as "nothing is mounted there".
- The briefing's schedule slot is 06:00 UTC (from `tasks.md` 5.2's "the
  digest's schedule slot", not from any scenario).
- The evaluation dates, launch dates, and step identifiers used throughout.
- An unresolvable product is reported to the caller as `None`.

**Deliberately untested**

- The briefing message's layout, wording, ordering across products, and any
  phrasing beyond the facts the requirements name. `design.md`'s Non-Goals put
  formatting outside this change and its Open Questions leave Block Kit open;
  asserting a phrasing would impose a contract nobody agreed to.
- The assemble-failure message's wording (same reason).
- The "already graduated" clause of *The launch report states whether the
  current gate awaits confirmation*. After graduation an approving approval is
  necessarily recorded for the final gate, so that clause cannot be
  discriminated from the already-approved clause at the report level; the
  approved clause is covered.
- `Briefing`'s refusal to render a clean briefing for delivery (`tasks.md`
  3.4) as a domain-level invariant. No scenario states it; the observable
  consequence — a clean day posts nothing — is covered.
- The runner's own recording of a run outcome. That is integration-tier
  (`tests/integration/shared/test_scheduled_run_history.py`) and needs
  Postgres, which this pass could not run.

**A note on one file that passes today.**
`tests/unit/test_briefing_not_externally_startable.py` passes on its first
run. That is not `ai-toolkit:testing`'s fourth failure state: the requirement
is a prohibition ("none of them SHALL start the daily briefing") and its
target — the FastAPI application — already exists, so a pass is the correct
result and the test's job is to keep it true. It would fail today if a
briefing trigger route existed.

---

## Obsolete and affected tests

The change carries one non-`ADDED` delta (`product-monitoring`, `REMOVED`),
so this list is applicable.

**Search bound**: `tests/**/test_*.py`, the dispatched test-path glob, and
nowhere else. No earlier `test-manifest.md` was supplied to this pass, so no
scenario-to-test mapping from a previous change was available; the matches
below come from searching the glob for the retired behavior's own vocabulary
(`daily_digest`, `run_daily_digest`, `pending_cadence`, `slack_notifier`,
`products.monitoring.daily`). **Every entry is a candidate for human
confirmation, not a conclusion.**

### Superseded by the `REMOVED` delta

**1. `tests/unit/catalog/application/test_daily_digest.py` — whole file (4 tests)**

- `::test_reader_satisfies_the_port_structurally`
- `::test_returns_the_names_the_reader_reports`
- `::test_no_products_case_reports_no_names`
- `::test_reader_failure_propagates_rather_than_being_swallowed`

Superseding delta: `product-monitoring` REMOVED *Daily Cadence Lists Existing
Product Names*.
Evidence: the file imports `run_daily_digest` and `ProductNameReader` from
`commerce_ops.catalog.application` and asserts the product-name listing's
assembly ("product names returned correctly", "the 'no products exist'
case"). `tasks.md` 5.3 deletes `catalog/application/daily_digest.py` and
`run_daily_digest` from catalog's surface, so the file's imports cannot
resolve after the change.

**2. `tests/unit/catalog/infrastructure/driving/test_daily_digest_job.py` — whole file (13 tests)**

- `::test_the_daily_cadence_has_a_declared_schedule`
- `::test_the_declared_schedule_becomes_due_once_a_day_at_06_00`
- `::test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone`
- `::test_a_failing_run_is_retried`
- `::test_successive_retries_wait_longer`
- `::test_retries_stop_at_the_declared_maximum`
- `::test_daily_trigger_lists_product_names`
- `::test_no_products_exist_posts_a_message_rather_than_nothing`
- `::test_slack_post_failure_leaves_the_run_succeeded_and_unretried`
- `::test_database_read_failure_on_the_final_attempt_fails_and_posts`
- `::test_an_intermediate_failed_attempt_does_not_post`
- `::test_every_intermediate_attempt_stays_silent_and_the_last_one_posts`
- `::test_the_registry_this_file_reads_is_the_one_the_worker_defers_from`

Superseding delta: all four `product-monitoring` REMOVED requirements.
Evidence: the file's own docstring enumerates them by name as what it is
derived from; it reaches the job by selecting the registered periodic task
whose name contains "daily" (today `products.monitoring.daily`, which
`tasks.md` 5.4 removes) and patches `run_daily_digest` on the job module,
which `tasks.md` 5.3 deletes.

**One caution before deleting it.** Several of its tests are derived from
`scheduled-jobs`, not from `product-monitoring` — the retry-backoff trio and
`::test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone`. The
new `test_daily_briefing_job.py` re-expresses the retry-backoff and
schedule-due assertions against the briefing job, but **deliberately does not
re-express the host-timezone one**: that is a property of `scheduled-jobs`'
runner rather than of any job, this change's deltas say nothing about it, and
re-homing it would be a change to `scheduled-jobs`' coverage that this pass
was not dispatched to make. If the digest's file is deleted whole, that
assertion leaves the suite. Consider re-homing it (a separate change) rather
than losing it silently.

### Affected by the change but *not* superseded by any delta

These fail or go vacuous for mechanical reasons — a module moves, a task name
disappears — while what they assert stays true and stays wanted. Correcting an
import path or a constant here is a fixture correction, not a weakening. None
was edited by this pass.

**3. `tests/unit/shared/application/test_monitoring_notifier_port.py`** —
`::test_the_products_notifier_module_satisfies_the_port_structurally`,
`::test_the_port_member_is_awaitable`.
Evidence: both import
`commerce_ops.catalog.infrastructure.driven.slack_notifier`, which `tasks.md`
5.1 moves to `briefing/infrastructure/driven/`. The assertion — that whichever
module posts to the monitoring channel satisfies `MonitoringNotifier` — is
unchanged and becomes *more* load-bearing after the move, since `worker.py`
re-points `overdue_check.notifier` at briefing's copy.

**4. `tests/unit/shared/infrastructure/driving/test_scheduled_runs_freshness.py`**
— module-level import of the same `catalog…slack_notifier`, monkeypatched at
line ~651. Same move, same one-line correction.

**5. `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py`** —
`_CATCH_UP_WORK = "products.monitoring.daily"` pins the digest's task name, and
`::test_exactly_the_declared_pieces_of_recurring_work_are_scheduled` asserts a
registry of exactly three whose names include "daily". After the swap the count
is still three and the briefing is still daily, so the name assertion may
survive by luck — but every catch-up scenario keyed on `_CATCH_UP_WORK` will
silently match nothing once that task name is gone. `tasks.md` 6.2 names this
file's category; worth an explicit look.

### Where no bearing test was found

- **`run_pending_cadence_report`** (retired by `tasks.md` 2.5). Searching the
  full glob for `pending_cadence` / `run_pending_cadence_report` returned no
  match. Read as **no such test exists** rather than "none was found": the
  export is an intentional no-op, so there was no behavior to cover.
- **The `slack_notifier` module's own tests.** No file in the glob tests
  `slack_notifier` directly; it is exercised only through the two
  port-satisfaction tests listed above. Read as **none was found by this
  search** — the search was by name, and a test exercising it under a
  different name would not have matched.

---

## Unresolved project questions

`AGENTS.md`, `CLAUDE.md` and `README.md` were read. Each question below has no
recorded answer in them or in the change's artifacts; this pass had no channel
to ask on, so each records the assumption taken and which tests depend on it.
None was resolved silently.

| # | Question | Assumption taken | Tests depending on it |
| --- | --- | --- | --- |
| 1 | `Severity`'s import path and construction form | `commerce_ops.shared.domain.severity.Severity`, an `Enum` constructed by lower-case value, rejecting with `ValueError` | all of `test_severity.py`; every briefing test that names a severity |
| 2 | The `LaunchStore`'s enumeration method name (`tasks.md` 2.2 fixes that one exists, not its spelling) | the fake answers to `list_all`, `all` and `list_launches` | `test_launch_reports.py`, `test_briefing_assembly.py`, `test_briefing_delivery.py` |
| 3 | `LaunchReport`'s field spellings — `product_id`, `steps`, `at_risk` — and each step entry's `identifier`, `discipline`, `due_period`, `outcome` | read through `_ATTRIBUTE_ALIASES` / `_read`, which fails loudly rather than defaulting | `test_launch_reports.py` only (the briefing files build reports through launch's own use case and never read report fields) |
| 4 | `assemble_daily_briefing`'s and `run_daily_briefing`'s keyword names for their readers, notifier, audience and `as_of` | `read_launch_reports=`, `read_product=`, `notifier=`, `audience=`, `as_of=` — isolated in `_assemble` / `_run`, one correction point per file | all of `test_briefing_assembly.py`, `test_briefing_delivery.py` |
| 5 | `Briefing.items`, `AttentionItem.product_id` / `.severity` / `.discipline` / `.evidence` | those spellings; evidence read as text so either a field-carrying or a rendering evidence value satisfies "names the fact" | `test_briefing_assembly.py` |
| 6 | How the catalog reports "cannot resolve this product" | the reader returns `None` | `::test_an_unresolvable_products_launch_is_still_derived_from`, `::test_an_unresolvable_product_does_not_lose_its_item`, `::test_one_unresolvable_product_does_not_take_the_others_with_it` |
| 7 | The briefing job's registered task name | contains "brief"; the selector asserts exactly one such task and fails loudly otherwise | all of `test_daily_briefing_job.py` |
| 8 | The job module's injection-point names | `run_daily_briefing` imported by name (patched with `raising=True`); the notifier as either `post_monitoring_message` or `notifier` (fixture fails loudly if neither exists); `session` patched with `raising=False`, since `design.md` Decision 5 has readers arrive already closed over their sessions | the four job-body tests in `test_daily_briefing_job.py` |
| 9 | Whether the briefing's audience parameter is a channel identifier or a richer value | a plain string (`"monitoring-channel"`); nothing asserts anything about it | `test_briefing_assembly.py`, `test_briefing_delivery.py` |

**One tooling note, not a question.** `ruff`'s isort classifies
`commerce_ops.briefing` and `commerce_ops.shared.domain.severity` as
third-party today, because neither module exists — so `ruff check --fix`
placed those imports beside `import pytest` in three of the new files. Once
the modules land the classification flips and `ruff` will move them back into
the first-party block. Expect that reordering during implementation; it is not
a defect in the tests.

**A note on the library's own reachability fragment.** `ai-toolkit`'s
`rules/test-manifest.md` ("Read the test manifest before implementing")
exists in the toolkit but is **not** imported into this project's `AGENTS.md`,
which carries only the `development-workflow` and `project-foundation` managed
blocks. Until it is, this file's location travels by the implementer being
told, not by the project's own conventions.

---

## What implementation must make pass

By task group, the tests that must go from failing to passing:

- **1 (shared vocabulary)** — `tests/unit/shared/domain/test_severity.py`
  (whole file).
- **2 (launch public surface)** —
  `tests/unit/launch/application/test_launch_reports.py` (whole file). 2.1 and
  2.3 are what the four `awaiting_confirmation` tests turn on; 2.2 and 2.4 are
  what the enumeration tests turn on.
- **3–4 (briefing domain and application)** —
  `tests/unit/briefing/application/test_briefing_assembly.py` and
  `tests/unit/briefing/application/test_briefing_delivery.py` (whole files).
  Both also require task group 2 to have landed: they build their input by
  running launch's own `read_launches`.
- **5 (infrastructure and composition)** —
  `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`
  (whole file). `tests/unit/test_briefing_not_externally_startable.py` passes
  already and must stay passing.
- **Throughout** — the 480 tests green at baseline must stay green, except
  where an entry under *Obsolete and affected tests* explains why one no
  longer applies.

Observed failure states as written (`ai-toolkit:testing`'s enumeration), all
state 2 — *the target does not exist yet*, which establishes absence and
nothing about whether the assertions are any good:

- `test_severity.py`, `test_launch_reports.py`, `test_briefing_assembly.py`,
  `test_briefing_delivery.py` — collection-time `ModuleNotFoundError` /
  `ImportError`.
- `test_daily_briefing_job.py` — 5 failed, 4 errored on the selector finding
  no registered briefing task (`registered: ['launch.clickup.completion_pass',
  'products.monitoring.daily', 'shared.scheduled_runs.overdue_check']`); its
  one guard test passes, since the runner registry it guards exists.
- `test_briefing_not_externally_startable.py` — 6 passed, for the reason
  recorded under *Assertion provenance*.
