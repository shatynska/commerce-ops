# add-clickup-completion-loop — Test Manifest

Written before any implementation of this change, strictly from its delta
specs. Not an artifact the OpenSpec schema knows about: it does not appear
among `openspec instructions apply`'s context files and has to be read on
purpose.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted, disabled, or weakened, and no implementation code was
written.

## Baseline

Taken before any test was written, on the full suite (`uv run pytest`),
split by tier as `AGENTS.md` defines them:

| Tier | Command | Result |
| --- | --- | --- |
| unit + agents | `uv run pytest tests/unit tests/agents` | **440 passed**, 0 failed |
| integration | `uv run pytest tests/integration` | **3 passed, 31 skipped** — skipped for want of `DATABASE_URL`; no Postgres is reachable from this environment |

So the suite was fully green beforehand, and every failure reported below
is attributable to this pass.

### State after this pass

Every new unit-tier file fails at **collection** on an absent target
(`ModuleNotFoundError` / `ImportError`) — failure state 2 in
`ai-toolkit:testing`: it establishes that the target is absent and nothing
about whether the assertions are any good, because they never executed.

```
uv run pytest tests/unit tests/agents
ERROR tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py
ERROR tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py
ERROR tests/unit/launch/infrastructure/driving/test_clickup_webhook.py
ERROR tests/unit/shared/infrastructure/driven/test_clickup_client_list_and_read.py
!!! Interrupted: 4 errors during collection !!!
```

**A collection error interrupts the whole run**, so until the
implementation lands no unit test executes at all — not merely the new
ones. See *Unresolved project questions*, Q1.

`test_clickup_sync_job_schedule.py` collects (it imports nothing that does
not exist) and reports 3 failed, 1 passed. The three fail on the absent
job. The one that passes is recorded below as a first-run pass, with its
reason.

## Scenario accounting

**36 `#### Scenario:` blocks across the two delta specs; 36 accounted for;
0 uncovered.**

### `specs/clickup-task-client/spec.md` — 9 scenarios

| # | Requirement / Scenario | Op | Covering test(s) |
| --- | --- | --- | --- |
| 1 | A list can be created in a given folder / List created in a folder | ADDED | `tests/unit/shared/infrastructure/driven/test_clickup_client_list_and_read.py::test_a_list_is_created_in_the_given_folder` |
| 2 | The tasks of a list can be read / Tasks returned with status and due date | ADDED | `…test_clickup_client_list_and_read.py::test_tasks_are_returned_with_status_closed_judgement_and_due_date` |
| 3 | The tasks of a list can be read / An empty list reads as empty | ADDED | `…test_clickup_client_list_and_read.py::test_an_empty_list_reads_as_empty_rather_than_erroring` |
| 4 | The tasks of a list can be read / A multi-page list is read completely | ADDED | `…test_clickup_client_list_and_read.py::test_a_multi_page_list_is_read_completely` |
| 5 | A failed ClickUp request… / ClickUp rejects a create request | MODIFIED | **existing, untouched**: `tests/unit/shared/infrastructure/driven/test_clickup_client.py::test_create_task_rejected_by_clickup_raises` |
| 6 | A failed ClickUp request… / ClickUp rejects an update request | MODIFIED | **existing, untouched**: `…test_clickup_client.py::test_update_task_rejected_by_clickup_raises` |
| 7 | A failed ClickUp request… / ClickUp rejects a create-list request | MODIFIED | `…test_clickup_client_list_and_read.py::test_a_rejected_create_list_request_raises` |
| 8 | A failed ClickUp request… / ClickUp rejects a read of a list's tasks | MODIFIED | `…test_clickup_client_list_and_read.py::test_a_rejected_read_of_a_lists_tasks_raises` |
| 9 | A failed ClickUp request… / ClickUp is unreachable | MODIFIED | new: `…test_clickup_client_list_and_read.py::test_create_list_when_clickup_is_unreachable_raises`, `::test_list_tasks_when_clickup_is_unreachable_raises`; existing, untouched: `…test_clickup_client.py::test_create_task_when_clickup_is_unreachable_raises`, `::test_update_task_when_clickup_is_unreachable_raises` |

Scenarios 5 and 6 are reproduced in the delta **verbatim** from the
requirement as it stands at `openspec/specs/clickup-task-client/spec.md`.
No new test was written for them: the existing ones still cover exactly
what the revised requirement states, and duplicating them would add no
evidence. Scenario 9's WHEN clause broadened from "a create-task or
update-task request" to "any of the client's requests", so the two new
operations get their own tests while the two existing ones stay valid.

### `specs/launch-clickup-sync/spec.md` — 27 scenarios (all ADDED)

Requirement: **Each launch is projected into its own ClickUp list**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 10 | A launch without a list gets one | `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_launch_without_a_list_gets_one` |
| 11 | An existing list is not recreated | `…test_clickup_sync_projection.py::test_an_existing_list_is_not_recreated` |
| 12 | A graduated launch is left alone | `…test_clickup_sync_projection.py::test_a_graduated_launch_is_left_alone` (behavioural half) **and** `tests/integration/launch/test_launch_clickup_mapping.py::test_the_enumeration_the_pass_runs_over_excludes_graduated_launches` (enumeration half) |
| 13 | Missing folder configuration fails the run | `…test_clickup_sync_projection.py::test_missing_folder_configuration_fails_the_run` |

The requirement's "SHALL record the association between the launch and its
list" clause is additionally covered at the tier where "recorded" means
persisted: `tests/integration/launch/test_launch_clickup_mapping.py::test_the_launch_to_list_association_survives_the_session`
and `::test_a_launch_with_no_recorded_list_reports_absence`.

Requirement: **Human-attested steps are projected as tasks**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 14 | A human-attested step gets a task | `…test_clickup_sync_projection.py::test_a_human_attested_step_gets_a_task`; persistence half: `tests/integration/launch/test_launch_clickup_mapping.py::test_the_step_to_task_association_survives_the_session` |
| 15 | An existing task is not recreated | `…test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated` |
| 16 | A prohibited-tactic step is never projected | `…test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected` |
| 17 | A deleted task for unfinished work is re-projected | `…test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected`; persistence half: `tests/integration/launch/test_launch_clickup_mapping.py::test_re_projecting_a_step_replaces_its_mapping` |
| 18 | A deleted task for finished work stays gone | `…test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone` |
| 19 | Automated and ai-assisted steps are never projected | `…test_clickup_sync_projection.py::test_automated_and_ai_assisted_steps_are_never_projected` |

Requirement: **Task due dates derive from the launch schedule**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 20 | Tasks carry due dates resolved from the launch date | `…test_clickup_sync_projection.py::test_tasks_carry_due_dates_resolved_from_the_launch_date` |
| 21 | A moved launch date updates existing tasks | `…test_clickup_sync_projection.py::test_a_moved_launch_date_updates_existing_tasks` |
| 22 | An unresolvable due period means no due date | `…test_clickup_sync_projection.py::test_an_unresolvable_due_period_means_no_due_date` |

Requirement: **Completion flows from ClickUp to the launch as a recorded
outcome**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 23 | A closed task records Satisfied | `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py::test_a_closed_task_records_satisfied` |
| 24 | A reopened task records InProgress | `…test_clickup_webhook.py::test_a_reopened_task_records_in_progress` |
| 25 | A reopening without an observed closing records nothing | `…test_clickup_webhook.py::test_a_reopening_without_an_observed_closing_records_nothing` |
| 26 | A repeated delivery changes nothing | `…test_clickup_webhook.py::test_a_repeated_delivery_changes_nothing` |
| 27 | The system never closes a task | `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py::test_the_system_never_closes_a_task` |

Requirement: **Webhook deliveries are verified before anything is
recorded**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 28 | A validly signed delivery is processed | `…test_clickup_webhook.py::test_a_validly_signed_delivery_is_processed` |
| 29 | An invalid signature is rejected | `…test_clickup_webhook.py::test_a_delivery_failing_signature_verification_is_rejected[no-signature-header]`, `[signed-with-wrong-secret]`, `[body-tampered-after-signing]` |
| 30 | No configured secret rejects all deliveries | `…test_clickup_webhook.py::test_no_configured_secret_rejects_all_deliveries` |
| 31 | An unmapped task is acknowledged and ignored | `…test_clickup_webhook.py::test_an_unmapped_task_is_acknowledged_and_ignored` |
| 32 | A graduated launch's task is acknowledged and ignored | `…test_clickup_webhook.py::test_a_graduated_launchs_task_is_acknowledged_and_ignored` |

The requirement's third acknowledge-and-ignore case — "an event other than
a task status change" — carries no scenario of its own and is covered by
`…test_clickup_webhook.py::test_an_event_other_than_a_status_change_is_acknowledged_and_ignored`.

Requirement: **The reconciliation pass records completions and reopenings
the webhook missed**

| # | Scenario | Covering test(s) |
| --- | --- | --- |
| 33 | A missed completion is recorded on reconciliation | `…test_clickup_sync_reconciliation.py::test_a_missed_completion_is_recorded_on_reconciliation` |
| 34 | A missed reopening is recorded on reconciliation | `…test_clickup_sync_reconciliation.py::test_a_missed_reopening_is_recorded_on_reconciliation` |
| 35 | No transition means no recording | `…test_clickup_sync_reconciliation.py::test_no_transition_means_no_recording[closed-and-observed-closed]`, `[open-and-observed-open]` |
| 36 | Reconciliation never overwrites other recording paths | `…test_clickup_sync_reconciliation.py::test_reconciliation_never_overwrites_other_recording_paths` |

The requirement's opening clause — "periodically, on a declared schedule
and without any request from outside the deployment" — is stated outside
any scenario and is covered by
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py`
(all four tests). Its "SHALL retain, per mapped task, the closed state it
last observed" clause is covered at the persistence tier by
`tests/integration/launch/test_launch_clickup_mapping.py::test_the_retained_observed_state_survives_the_session`.

### Uncovered scenarios

**None.** Every scenario in both delta specs has at least one named test.

## Assertion classification

Per-assertion labels are inline in each test file (`SPECIFIED` /
`DERIVED` comments) and the deliberately-untested cases are listed at the
foot of each file. Summarised:

### Specified

Everything traceable to a `#### Scenario:` block or to a requirement's own
statement: which ClickUp calls are and are not made, which associations
end up recorded, which outcome is recorded for which step, the provenance
source (`clickup`), the task as evidence, the resolved due-period end, the
rejection of unverifiable deliveries, the acknowledgement of ignorable
ones, and the transition rule keyed on the retained observed state.

Values transcribed from this change's own planning artifacts are treated
as specified for these tests' purposes, following the precedent of every
prior pass in this repository (`tasks.md`'s declared env-var set in
`test_settings.py`, `tasks.md`'s 06:00 schedule in
`test_daily_digest_job.py`). Those are: the module placements in
`tasks.md` 4.1/5.1/6.1, the `create_list`/`list_tasks` signatures in
`tasks.md` 1.2/1.3, the HMAC-SHA256/`X-Signature` scheme in `design.md`,
the `clickup-reconciliation` recorder identity in `design.md`, and the
30-minute cadence in `design.md`. Each is flagged in place, so a revision
to the artifact shows up as a readable failure rather than a mystery.

### Derived

Recorded here because each obliges the implementation to satisfy something
no scenario states:

1. **"Rejected" is a 4xx; "acknowledged" is a 2xx.** No artifact pins a
   status code. Same reading `test_slack_events_endpoint.py` records.
2. **"Failure is reported" is an exception.** The unconfigured-folder
   test asserts only that something raises, not a type — a job body has no
   other way to report a failed run.
3. **A task is "named for the step" if the step identifier appears in the
   name**; a list is named from the product if the catalog name and SKU
   both appear. Containment, not an exact format, because no artifact
   fixes one.
4. **Due-date encoding is not pinned.** `_as_date()` in each file
   normalises a `date`, a `datetime`, or an epoch-millisecond number, so
   the assertion is on the calendar day the spec names.
5. **The read-side value object's attribute spellings** (`.id`,
   `.status`, `.closed`, `.due_date`) and **`create_list`'s return
   shape** (a bare identifier or an object carrying one — `tasks.md` 1.1
   and the delta spec disagree; `_list_identifier()` accepts either).
6. **`include_closed` is asserted on the request**, not only on the
   result. Against a `MockTransport` the result is whatever the test
   scripts, so only the request establishes that real ClickUp would have
   included closed tasks.
7. **A re-delivered webhook issues no second recording call.** The
   scenario is satisfiable by an idempotent re-recording too; the
   stronger assertion follows `design.md`'s stated mechanism and is
   labelled as such in the test.
8. **The per-launch passes are themselves graduated-safe.** `design.md`
   puts the filter upstream in `list_active()`; the projection test
   asserts the specified outcome at the per-launch entry point because
   that is where it is observable without a database. If the
   implementation relies solely on `list_active()`, the response is to add
   the guard or move the assertion to the pass level — not to weaken it.
9. **The webhook's acting user reaches provenance's recorder by
   containment**, since no artifact says whether the ClickUp user is
   recorded as username, id, or both.
10. **The reconciliation pass declares a tolerance** (`tasks.md` 6.1,
    "tolerance per `scheduled-jobs` conventions") — guarding another
    capability's requirement against this change's addition.

### Deliberately untested

Listed at the foot of each test file. The substantive ones:

- **Constant-time signature comparison** (`design.md` requires it). Timing
  behaviour is not observable from a functional test; a wrong-signature
  rejection passes either way. This stays a review obligation.
- **Clearing a stale due date when the period becomes unresolvable**
  (`design.md`). No scenario states it — the unresolvable-period scenario
  is written over projection only.
- **Create-then-record ordering and the crash window** (`design.md`
  Risks). Not stated by any scenario.
- **The list name excluding the opaque product identifier.** The
  requirement constrains how the name is *derived* (covered by asserting
  the catalog read), not what it may contain.
- **The Alembic migration's up/down round-trip.** `tasks.md` 7.2 makes it
  a manual verification step against a scratch database; this project has
  no precedent for asserting a migration from a test.
- **Credential absence on `create_list`/`list_tasks`.** The
  `clickup-task-client` "Authentication is configured independently of any
  one caller" requirement is unmodified and its scenarios name only task
  creation and update; the delta does not broaden them the way it broadens
  the failure requirement.
- **Retry behaviour of the reconciliation job.** Already required and
  tested under `scheduled-jobs`; this delta adds no scenario about it.
- **A delivery whose history items name no acting user.** The requirement
  says "the ClickUp actor **where the delivery identifies one**", leaving
  the other case open.

### First-run pass — investigated, not recorded as coverage

`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py::test_no_externally_reachable_route_starts_the_reconciliation_pass`
**passes on its first run, before any implementation exists.**

Investigated per `ai-toolkit:testing`'s fourth failure state. It is not
vacuous — it asserts over the real application's OpenAPI paths and fails
its own guard if the app exposes none — but it asserts a *negative*
requirement ("without any request from outside the deployment"), which is
trivially satisfied while the capability does not exist. It establishes
nothing yet; its value is as a regression guard once the webhook route and
the job land. It shares the limitation of the existing
`tests/unit/test_no_external_cadence_trigger.py`: it can catch a trigger
route named for what it does, not one named for something else.

## Obsolete tests

**Applicable** — the change carries one MODIFIED delta (`clickup-task-client`
/ *A failed ClickUp request is surfaced to the caller*). It carries no
REMOVED and no RENAMED delta.

**Result: no bearing test found, and in this case that means "no such test
exists", not "none was found by this search."**

Evidence, established by comparing the requirement as it currently stands
at `openspec/specs/clickup-task-client/spec.md` (lines 39–52) with the
delta at `specs/clickup-task-client/spec.md` (lines 36–64):

- The revision is **purely additive**. The requirement statement extends
  the operations it covers ("creating or updating a task" → "creating or
  updating a task, creating a list, or reading a list's tasks"); nothing
  is narrowed, weakened, or reversed.
- Both pre-existing scenarios ("ClickUp rejects a create request",
  "ClickUp rejects an update request") appear in the delta **word for
  word**, so the tests covering them
  (`tests/unit/shared/infrastructure/driven/test_clickup_client.py::test_create_task_rejected_by_clickup_raises`,
  `::test_update_task_rejected_by_clickup_raises`) assert current, not
  superseded, behaviour.
- The one reworded scenario, "ClickUp is unreachable", broadens its WHEN
  clause from "a create-task or update-task request" to "any of the
  client's requests". The two existing tests
  (`::test_create_task_when_clickup_is_unreachable_raises`,
  `::test_update_task_when_clickup_is_unreachable_raises`) cover two of
  the four paths the broadened clause now spans and remain valid; the two
  new paths are covered by new tests rather than by editing those.

**Search bound:** `tests/**/test_*.py` only, as dispatched. No earlier
`test-manifest.md` was supplied for this change, so no
scenario-to-test mapping from a previous pass was available; the search
was by matching assertion text and referenced behaviour across the glob
(`grep` for ClickUp client operations and for the failure scenarios'
wording).

**No entry is proposed for human confirmation, because there is nothing to
delete or rewrite.**

## Existing tests this change will turn red (not obsolete — extend, don't weaken)

These are not superseded by any delta. They are transcriptions and exact-count
guards that this change's *own additions* will trip, by design — each guard
firing is the guard working. They need extending as part of the
implementation, and extending them is spec-driven, not a weakening. They
are recorded here because they are otherwise found only by running the
suite after the implementation is half-written.

1. **`tests/unit/shared/application/test_settings.py::test_every_required_runtime_variable_is_declared_in_one_definition`**
   asserts `set(Settings.model_fields) == ALL_DECLARED`, a transcription of
   `tasks.md`'s declared set from earlier changes. Declaring
   `clickup_launch_folder_id` and `clickup_webhook_secret` (task 2.1) makes
   it fail until `OPTIONAL` in that file gains
   `CLICKUP_LAUNCH_FOLDER_ID` and `CLICKUP_WEBHOOK_SECRET`. The same two
   names also belong in `test_each_declaration_records_whether_it_is_required_or_optional`'s
   optional set, which reads the same constant.
2. **`tests/unit/shared/application/test_settings_env_drift.py::test_every_declared_variable_is_read_or_carries_an_exemption`**
   requires every declared variable to be read via `os.environ`/`os.getenv`
   somewhere under `src/commerce_ops` **or** to carry an
   `ENV_VAR_EXEMPTIONS` entry with a reason. If the two new variables are
   consumed only through `Settings`, they need exemption entries; if they
   are read directly (as `CLICKUP_API_TOKEN` is), they do not.
3. **`tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py::test_exactly_the_declared_pieces_of_recurring_work_are_scheduled`**
   asserts `len(registered) == 2`. Registering the reconciliation job
   (tasks 6.1/6.2) makes it 3. The count and its message need updating to
   name this change's job as the third, per that test's own stated intent
   ("so that scheduling some *other* recurring work without a spec to
   declare it also fails here" — this one *has* a spec).
4. **`tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py::test_an_absent_worker_becomes_visible_before_the_work_it_runs`**
   requires every registered piece of work to have a tolerance strictly
   greater than the worker-liveness tolerance. This constrains the
   reconciliation job's tolerance choice (task 6.1); a 30-minute cadence
   with a tight tolerance would fail it.
5. **`tests/unit/test_no_external_cadence_trigger.py::test_no_route_exists_for_starting_a_cadence`**
   fails any mounted path containing `monitoring`, `daily`, `weekly`,
   `biweekly`, `monthly` or `quarterly`. The webhook route's URL (task 5.1)
   must avoid those words.
6. **`tests/unit/test_registrations_across_processes.py`** and
   **`tests/unit/test_startup_without_configuration.py`** each transcribe
   the declared env-var list; neither asserts the set exactly, so both
   should keep passing — listed only so the transcriptions are not
   forgotten.

None of the above was touched by this pass.

## Unresolved project questions

Each records the assumption taken and the tests that depend on it. The
project's convention files (`AGENTS.md`, `CLAUDE.md` — a pointer to it —
and `README.md`) were read; none answers these, and this pass has no
channel to ask on.

**Q1 — How is a test-first pass committed, given the pre-commit hook runs
the whole `tests/unit` + `tests/agents` tree?**
Not recorded anywhere. `AGENTS.md` mandates test derivation strictly before
implementation, and its Development Tooling section runs the whole unit
tier at commit time — so a test-first pass cannot be committed on its own
without the hook rejecting it. Worse than red: a collection error
**interrupts the entire run**, so no unit test executes.
*Assumption taken:* follow the observable convention of the previous slice
(`git log`: `275d3a6 feat: introduce the launch aggregate…` precedes
`a2100f5 test: add the introduce-launch-aggregate scenario tests`) — the
tests are committed alongside or after the implementation, not before.
Marking these tests `skip`/`xfail` to keep the hook green was rejected:
that is disabling a test to reach green, which `ai-toolkit:testing` does
not permit a project convention to override, and it would also hide the
target-absent signal these tests exist to give.
*Depends on it:* every file this pass added.

**Q2 — Does `commerce_ops.launch.application` export
`record_step_outcome`, and with what signature?**
The dispatch names it as existing; no artifact fixes its parameter list,
and this pass may not read implementation source to check.
*Assumption taken:* an async callable reachable as
`record_outcome(product_id=…, step_id=…, outcome=…, provenance=…)`,
injected into the sync passes as a collaborator (the shape
`test_graduation.py` already uses for the catalog stamp). The webhook's
recorder double accepts anything and inspects only keywords, so extra
parameters (stores, playbook) do not break it.
*Depends on it:* `test_clickup_sync_reconciliation.py` (all tests),
`test_clickup_webhook.py` (all tests).

**Q3 — What are the sync pass entry points called, and what do they take?**
`tasks.md` 4.1–4.4 fix the module and the work, not a call shape.
*Assumption taken:* `converge_launch(launch=, playbook=, clickup=,
mapping=, read_product=, folder_id=)` and `reconcile_launch(launch=,
playbook=, clickup=, mapping=, record_outcome=)` in
`launch/infrastructure/driven/clickup_sync.py`. Each test file funnels
every call through one `_converge()` / `_reconcile()` helper, so a
differing signature is a one-line fixture correction per file.
*Depends on it:* both `test_clickup_sync_*.py` files.

**Q4 — What is the mapping store called, and what are its methods?**
`tasks.md` 3.1 fixes the two tables and the last-observed-closed column;
nothing names a store over them.
*Assumption taken:* `ClickUpMappingRepository(session)` in
`launch/infrastructure/driven/clickup_mapping.py`, with `record_list` /
`list_id_for`, `record_task` / `task_for` / `tasks_for` / `resolve_task`,
and `observe(product_id, step_id, closed)`.
*Depends on it:* both `test_clickup_sync_*.py` files (through the fakes),
`test_clickup_webhook.py` (through the substituted name), and
`tests/integration/launch/test_launch_clickup_mapping.py` (against the
real store).

**Q5 — Which module-level names does the webhook route import its
collaborators under?**
*Assumption taken:* `session`, `ClickUpMappingRepository`,
`LaunchRepository`, `record_step_outcome` — the by-name-import pattern
`monitoring.py` and the daily-digest job already use.
`monkeypatch.setattr` at its default `raising=True`, so a mismatch fails
loudly rather than silently leaving a real collaborator in place.
*Depends on it:* `test_clickup_webhook.py` (all tests).

**Q6 — What URL does the webhook route mount at?**
Deliberately not assumed: `_webhook_path()` reads the path off the
module's own `router`. The only assumption is that `main.py` includes the
router **without an extra prefix**, which
`test_the_webhook_route_is_mounted_in_the_application` depends on and
which matches how the Slack adapter is mounted.

**Q7 — Do the test doubles have to be duplicated across files?**
The dispatched test-path glob is `tests/**/test_*.py`, which a
`conftest.py` does not match, so this pass could not put the shared fakes
in one. `_FakeClickUp`, `_FakeMapping` and friends are therefore
duplicated between `test_clickup_sync_projection.py` and
`test_clickup_sync_reconciliation.py`. Consolidating them into a
`tests/unit/launch/infrastructure/driven/conftest.py` is a reasonable
follow-up for whoever holds a wider write scope; it is not a change to
what any test asserts.

**Q8 — `ruff check` reports `I001` on three of the new files.**
Ruff's isort resolves first-party by checking whether the module exists
under `src/`, so imports of the not-yet-created `clickup_sync` and
`clickup_mapping` modules are classified third-party and it wants them
moved into the third-party block. The imports are deliberately left in
their **post-implementation-correct** first-party position, since the
files are expected to be committed once the modules exist. `ruff format
--check` is clean across `tests/`. The three findings disappear the moment
tasks 3.1 and 4.1 land; no other lint finding remains.

## Files added by this pass

- `tests/unit/shared/infrastructure/driven/test_clickup_client_list_and_read.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`
- `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`
- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py`
- `tests/integration/launch/test_launch_clickup_mapping.py`
- this manifest

Nothing else was written, and nothing existing was modified.
