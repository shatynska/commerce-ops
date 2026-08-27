# Test manifest — `heal-a-launchs-deleted-list`

Written before any of this change is implemented, from the delta specs
alone. No implementation source for the behaviour under test
(`clickup_sync.py`, `clickup_mapping.py`, `clickup_client.py`) was read.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and must be
opened on purpose.

## Test command

`uv run pytest` — inside the uv-managed environment, never a bare
`pytest`. Individual tests are selectable by the identifiers below.

## Baseline

Taken at the worktree root (`/home/shatynska/projects/commerce-ops-heal-list`,
branch `heal-a-launchs-deleted-list`) **before any test here was written**:

| command | result |
|---|---|
| `uv run pytest tests/unit tests/agents` | **1130 passed, 0 failed** |
| `uv run pytest tests/integration` | **3 passed, 94 skipped** |

The integration tier's 94 skips are the tier finding no database:
`DATABASE_URL` is unset here and neither `.env.test` nor `.env` exists, so
every database-backed test skipped with that reason. **The two integration
tests added by this pass were therefore never executed.** Their first real
run belongs to whoever implements the change, against a migrated database.

After this pass: `uv run pytest tests/unit tests/agents` reports **21
failed, 1132 passed**. Every one of the 21 failures is a new test failing
on an absent target; the 1130 baseline passes are all still passing, plus
two of the new tests (see *First-run passes*, below). `uv run ruff check`,
`uv run ruff format --check` and `uv run mypy .` are clean across the tree.

## Files added

| file | tier |
|---|---|
| `tests/unit/shared/infrastructure/driven/test_clickup_client_list_state.py` | unit |
| `tests/unit/launch/infrastructure/driven/test_clickup_sync_list_healing.py` | unit |
| `tests/integration/launch/test_clickup_mapping_list_replacement.py` | integration |

No existing test file was edited, deleted or disabled. Nothing was written
outside `tests/**/test_*.py` except this manifest.

## Scenario accounting

Twenty-one `#### Scenario:` blocks across the two delta specs; twenty-one
accounted for below.

### `launch-clickup-sync` — MODIFIED *Each launch is projected into its own ClickUp list* (13 scenarios)

| # | Scenario | Covered by |
|---|---|---|
| 1 | A launch without a list gets one | **No new test.** Carried into the delta verbatim; covered by the existing `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_launch_without_a_list_gets_one`, which is unaffected (a launch with no recorded list has no list state to establish). |
| 2 | An existing list is not recreated | `tests/unit/launch/infrastructure/driven/test_clickup_sync_list_healing.py::test_a_list_clickup_reports_as_existing_is_not_recreated` |
| 3 | A launch whose list was deleted gets a new one | `…/test_clickup_sync_list_healing.py::test_a_launch_whose_list_was_deleted_gets_a_new_one`; persistence half in `tests/integration/launch/test_clickup_mapping_list_replacement.py::test_the_replacement_and_the_discard_land_in_one_commit` |
| 4 | The replacement and the discard cannot come apart | `…/test_clickup_sync_list_healing.py::test_the_replacement_and_the_discard_cannot_come_apart` (caller's half) and `tests/integration/launch/test_clickup_mapping_list_replacement.py::test_a_replacement_that_does_not_commit_leaves_the_old_list_and_mappings` (transaction half) |
| 5 | Steps re-project into the replacement list | `…/test_clickup_sync_list_healing.py::test_steps_re_project_into_the_replacement_list` |
| 6 | Finished work is not re-projected into the replacement list | `…/test_clickup_sync_list_healing.py::test_finished_work_is_not_re_projected_into_the_replacement_list[satisfied]` and `[not-applicable]` |
| 7 | Finished work of a step the launch is not held to survives the replacement | `…/test_clickup_sync_list_healing.py::test_finished_work_of_a_step_the_launch_is_not_held_to_survives[retired-out-of-the-served-set]` and `[hazard-re-authored]` |
| 8 | A mapping for an undefined step is discarded | `…/test_clickup_sync_list_healing.py::test_a_mapping_for_an_undefined_step_is_discarded` |
| 9 | Outcomes recorded before the deletion are kept | `…/test_clickup_sync_list_healing.py::test_outcomes_recorded_before_the_deletion_are_kept` |
| 10 | A failed write is not read as a deletion | `…/test_clickup_sync_list_healing.py::test_a_failed_write_is_not_read_as_a_deletion` |
| 11 | A list whose state cannot be established is not healed | `…/test_clickup_sync_list_healing.py::test_a_list_whose_state_cannot_be_established_is_not_healed[not-found]`, `[unauthorized]`, `[unreachable]` |
| 12 | A graduated launch is left alone | New AND ("its recorded list is not checked for existence"): `…/test_clickup_sync_list_healing.py::test_a_graduated_launchs_recorded_list_is_not_checked_for_existence`. Carried clause: existing `…/test_clickup_sync_projection.py::test_a_graduated_launch_is_left_alone`, untouched. |
| 13 | Missing folder configuration fails the run | New AND (a launch needing a list *because* its recorded one is deleted is not given the dead identifier back): `…/test_clickup_sync_list_healing.py::test_missing_folder_configuration_fails_a_launch_needing_a_replacement`. Carried clause: existing `…/test_clickup_sync_projection.py::test_missing_folder_configuration_fails_the_run`, untouched. |

### `clickup-task-client` — ADDED *A list's own state can be read* (2 scenarios)

| # | Scenario | Covered by |
|---|---|---|
| 14 | A deleted list reports itself deleted | `tests/unit/shared/infrastructure/driven/test_clickup_client_list_state.py::test_a_deleted_list_reports_itself_deleted` |
| 15 | A live list reports itself not deleted | `…/test_clickup_client_list_state.py::test_a_live_list_reports_itself_not_deleted` |

### `clickup-task-client` — MODIFIED *A failed ClickUp request is surfaced to the caller* (6 scenarios)

Only the requirement's **enumeration sentence** changed (it now names the
list-state read). Five of the six scenarios are carried into the delta
**verbatim** and stay covered, unchanged and untouched, by the existing
files.

| # | Scenario | Covered by |
|---|---|---|
| 16 | ClickUp rejects a create request | **No new test.** Existing `tests/unit/shared/infrastructure/driven/test_clickup_client.py::test_create_task_rejected_by_clickup_raises` |
| 17 | ClickUp rejects an update request | **No new test.** Existing `…/test_clickup_client.py::test_update_task_rejected_by_clickup_raises` |
| 18 | ClickUp rejects a create-list request | **No new test.** Existing `…/test_clickup_client_list_and_read.py::test_a_rejected_create_list_request_raises` |
| 19 | ClickUp rejects a read of a list's tasks | **No new test.** Existing `…/test_clickup_client_list_and_read.py::test_a_rejected_read_of_a_lists_tasks_raises` |
| 20 | ClickUp rejects a read of a list's own state | **New scenario.** `…/test_clickup_client_list_state.py::test_a_rejected_read_of_a_lists_own_state_raises[not-found]`, `[unauthorized]`, `[server-error]` |
| 21 | ClickUp is unreachable | Verbatim, but its "any of the client's requests" now reaches a fifth operation. The four existing paths stay covered by `test_clickup_client.py::test_create_task_when_clickup_is_unreachable_raises`, `::test_update_task_when_clickup_is_unreachable_raises`, `test_clickup_client_list_and_read.py::test_create_list_when_clickup_is_unreachable_raises`, `::test_list_tasks_when_clickup_is_unreachable_raises`. The new path: `…/test_clickup_client_list_state.py::test_reading_a_lists_state_when_clickup_is_unreachable_raises[connect]`, `[timeout]` |

## First-run passes (failure state 4 — investigated, not recorded as coverage)

Two new tests **pass** on their first run. Per `ai-toolkit:testing` a pass
before any implementation exists is an alarm, so each was investigated
rather than counted:

- `…/test_clickup_sync_list_healing.py::test_a_failed_write_is_not_read_as_a_deletion`
  — passes because today's pass performs no healing at all, so it cannot
  misread a write failure as a deletion. This is the **target-exists** case:
  the assertion is not vacuous (its own guard confirms the failing
  `create_task` really was attempted), so what it establishes is that the
  current behaviour already satisfies the scenario, and it now pins that
  against the change introducing the misreading. It discriminates a wrong
  implementation once the healing branch lands.
- `…/test_clickup_sync_list_healing.py::test_a_graduated_launchs_recorded_list_is_not_checked_for_existence`
  — passes because there is no list-state read to take yet. Same shape: it
  pins the existing graduated short-circuit against the probe being placed
  ahead of it (`tasks.md` 3.3).

Neither asserts nothing; neither is recorded as having exercised the
behaviour this change introduces.

## Assertion classification

Recorded per file in a `DELIBERATELY UNTESTED` block at the foot of each,
and inline against each assertion as `SPECIFIED` / `DERIVED`. Summarised:

### Specified

Every assertion tracing to a scenario's THEN or to a sentence of the
requirement text, including: that the recorded list's existence is
established from ClickUp **once per pass**; that a replacement is created
in the configured folder and carries the product's catalog name and SKU;
that the launch is recorded against the new list; that the discard spares
mappings for playbook-defined steps whose recorded outcome settles work,
judged without reference to the step's current hazard; that a mapping
whose step the playbook does not define is discarded; that re-projected
tasks begin unobserved; that recorded outcomes survive the heal; that
neither a failed write nor a failed state read is read as a deletion; that
a launch whose list state cannot be established fails its pass; that a
graduated launch's list is never read; and that a launch needing a
replacement is not handed its dead identifier back when no folder is
configured.

### Derived

- **Failure is reported by raising.** Three tests (`…is_not_healed`,
  `…fails_a_launch_needing_a_replacement`) read "the pass fails" as the
  pass raising. No artifact names a mechanism or a type, so
  `pytest.raises(Exception)` is deliberately untyped — the reading the
  existing `test_missing_folder_configuration_fails_the_run` already
  records for this project.
- **The list name is asserted by containment**, not by format: no artifact
  fixes the separator or the ordering, only that the catalog name and the
  SKU both appear.
- **A task is attributed to its step by the step identifier appearing in
  the task's name.** That is the composition the existing projection tests
  already pin; nothing in this delta restates it.
- **Endpoint shape** `GET /api/v2/list/{list_id}` in the client tests. The
  scenario says only that the state of a list is read; the path is how
  "that list" is observed.
- **`_ClickUpRequestFailed` / `_ClickUpUnreachable` / `_StoreWriteFailed`**
  are the test files' own exception types. No artifact names any, and no
  test asserts a type — only that the failure is not absorbed.

### Deliberately untested

Each is recorded at the foot of the file it belongs to. In summary:

- **The mid-pass terminality window** (`design.md` — Risks). A step
  attested terminal between the launch being read for the walk and the
  discard has its mapping discarded and a fresh open task created. The
  design records this as **accepted as a live residual rather than
  guarded**, so a test asserting against it would assert a guard the
  change deliberately did not build.
- **The orphan list left when the process dies between `create_list` and
  the transaction commit** (`design.md` — Risks; and the requirement's own
  "reclaiming such a list is not undertaken here"). Accepted, not guarded.
- **A list purged from ClickUp's trash.** `design.md` — Decision 4 records
  that it presumably answers `404` and is therefore never healed, and
  that closing the gap belongs to a different change. The `404` case
  asserts the *stated* behaviour (no heal, the pass fails).
- **`Refused` as an exempting terminal outcome.** The requirement's
  enumeration names it, but `permissible_terminal_outcomes` permits it
  only for a `prohibited-tactic` step and `is_projectable` excludes that
  hazard — no projectable step can carry it, so constructing one would
  assert against a fixture. The reachable half of the same concern (a
  `Satisfied` step re-authored `prohibited-tactic`) *is* covered.
- **The list name's freedom from the SKU value object's repr.** PR #81
  ships that fix ahead of this change and task 5.3 confirms it on the
  healed launch's list; asserting it here would turn this pass red for a
  reason that is not healing. The assertion used
  (`PRODUCT_SKU.value in name`) holds both before and after that fix and
  asserts the defect neither way.
- **A `200` list-state response carrying no `deleted` key.** No scenario
  states what its absence means, and `design.md` — Risks records
  `"deleted": true` as a single observed behaviour. Recorded so that if
  the implementation must choose a reading, the choice is visible.
- **Which ClickUp reads the pass takes in what order**, within
  `_ensure_list`. No scenario states an ordering.
- **Which mappings belong in the spared set, at the integration tier.**
  `design.md` — Decision 2b puts that judgement in the caller and forbids
  the store from making it; asserted at the unit tier instead.
- **Concurrency** between two passes replacing the same launch's list. No
  scenario states an isolation guarantee.

## Obsolete tests

Both delta specs carry a MODIFIED requirement, so this list is applicable.
Every entry below was written as a **candidate for human confirmation**,
never a conclusion, and nothing in it was acted on by the pass that wrote
this file: that pass edited, deleted and disabled nothing.

**Resolved during implementation, 2026-08-27.** The single entry below was
confirmed and the test deleted, leaving a comment in its place naming the
successor. Before deleting, the replacement was read against the original:
it carries both of the original's assertions unchanged — no new list is
created, and the recorded association still names the same list — so no
coverage was surrendered. `uv run pytest tests/unit tests/agents` went from
1153 to 1152 passing, that one test removed and nothing else moving.

### Superseded — one entry

**`tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_an_existing_list_is_not_recreated`**

- **Superseding delta:** `launch-clickup-sync`, MODIFIED *Each launch is
  projected into its own ClickUp list*, scenario *An existing list is not
  recreated*.
- **Evidence:** the scenario's WHEN gained a clause — "**and ClickUp
  reports that list as existing**" — and the requirement text gained
  "Before a launch's projection uses a recorded list, once per pass, the
  system SHALL establish from ClickUp that the list still exists. A launch
  whose recorded list **still exists** SHALL NOT get a second one." The
  test's docstring transcribes the *old* WHEN verbatim ("WHEN the
  reconciliation pass runs and the launch already has a recorded list"),
  and its `_FakeClickUp` offers no read of a list's own state, so the
  state it constructs is one the revised requirement classes as *a list
  whose state cannot be established* — for which the launch's pass SHALL
  fail, not one where the no-second-list rule holds.
- **Replacement written:**
  `tests/unit/launch/infrastructure/driven/test_clickup_sync_list_healing.py::test_a_list_clickup_reports_as_existing_is_not_recreated`,
  which expresses the revised WHEN and additionally asserts the once-per-pass
  establishment.
- **Candidate for human confirmation.** Two defensible resolutions, and
  the choice is not this pass's to make: delete it as superseded, or
  extend its double to answer the state read, in which case it duplicates
  the replacement rather than contradicting it.

### Not superseded, but blocked — a fixture extension, **not** a deletion

This is the finding most likely to be misread, so it is stated as its own
section rather than folded into the list above. **None of the tests below
is obsolete. None asserts superseded behaviour. Deleting any of them would
lose coverage this change does not replace.**

`tasks.md` 3.1 makes `_ensure_list` read the recorded list's state
**unconditionally** before returning it. Every existing unit test that
seeds a recorded list *and* runs the convergence pass therefore reaches
that read through a ClickUp double that has no such operation. The
prediction is derived from the delta and `tasks.md`, not from reading the
implementation; it was not observed, because the healing branch does not
exist yet.

The expected fix is one line per double — teach each file's `_FakeClickUp`
to answer the list-state read for a live list — and no assertion in any of
them changes.

Thirty-four existing tests, enumerated so the work is bounded:

- `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py`:
  `test_an_existing_task_is_not_recreated`,
  `test_a_deleted_task_for_unfinished_work_is_re_projected`,
  `test_a_deleted_task_for_finished_work_stays_gone`,
  `test_a_moved_launch_date_updates_existing_tasks`
  (plus `test_an_existing_list_is_not_recreated`, listed as superseded above)
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py`:
  `test_an_existing_untagged_task_gains_its_tags`,
  `test_a_task_already_carrying_its_tags_is_left_alone`,
  `test_a_persons_own_tags_are_never_touched`,
  `test_a_step_moved_between_gates_keeps_its_original_gate_tag`,
  `test_a_step_that_has_left_the_projection_is_not_tagged`,
  `test_a_tag_that_cannot_be_set_is_reported_and_not_fatal`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py`:
  `test_a_step_authored_mid_launch_is_projected`,
  `test_an_unedited_task_follows_the_steps_current_wording`,
  `test_a_persons_body_note_survives_a_wording_edit`,
  `test_an_unedited_legacy_task_starts_healing`,
  `test_an_ambiguous_legacy_task_is_never_rewritten`,
  `test_an_edited_task_name_is_never_restored`
- `tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py`:
  `test_a_pre_existing_body_is_left_standing_when_the_step_has_none`,
  `test_an_existing_unowned_task_gains_its_steps_assignees`,
  `test_a_persons_own_assignment_change_is_not_overwritten`,
  `test_a_persons_body_note_survives_a_wording_edit`,
  `test_an_unedited_task_heals_to_the_new_composition`
- `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py`:
  `test_a_renamed_task_still_resolves_to_its_step`,
  `test_an_edited_task_name_is_never_restored`
- `tests/unit/launch/infrastructure/driven/test_clickup_automated_steps_leave_loop.py`:
  `test_a_step_that_becomes_automated_leaves_the_loop_while_staying_active`,
  `test_a_step_returning_to_human_work_rejoins_the_loop`,
  `test_a_prohibited_tactic_step_also_leaves_the_loop`
- `tests/unit/launch/infrastructure/driven/test_clickup_non_active_steps_leave_loop.py`:
  `test_a_retired_steps_task_is_left_unmanaged`,
  `test_a_de_activated_step_leaves_the_loop_exactly_as_a_retired_one_does`,
  `test_a_draft_step_with_a_leftover_task_is_left_alone`,
  `test_a_step_returning_to_active_resumes_through_its_existing_task`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_retired_steps.py`:
  `test_a_retired_steps_task_is_left_unmanaged`,
  `test_an_unretired_step_resumes_through_its_existing_task`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`:
  `test_the_system_never_closes_a_task`

### Where no bearing test was found

- **`clickup-task-client`, MODIFIED *A failed ClickUp request is surfaced
  to the caller*.** No obsolete test — and this is "no such test exists",
  not "none was found". All five carried scenarios are verbatim, so the
  tests transcribing them still transcribe the current text; the change is
  purely additive (a sixth operation named in the enumeration).
- **The store's existing operations.** `tests/integration/launch/test_launch_clickup_mapping.py`
  exercises `record_list` / `record_task` / `observe` directly, not through
  `_ensure_list`, so the new read does not reach it and nothing it asserts
  is superseded. Searched and none found.

### Search bound

The search covered `tests/**/test_*.py` and nothing else, by AST scan for
test functions that both seed a recorded list association and invoke the
convergence pass, plus a reading of both capabilities' existing test files.
**No earlier `test-manifest.md` was supplied to this pass**, and none was
sought — so the mapping from requirement to test used here is the one
recoverable from the test files themselves. A test bearing on the revised
scenarios by some route this scan cannot see would not have been found.

## Unresolved project questions

No channel exists to ask on, so each is recorded with the assumption taken
and the tests depending on it. None was resolved silently.

1. **The name of the client's read of a list's own state.** `tasks.md` 1.1
   fixes that it exists and what it returns; nothing names it. *Assumption:*
   one of `get_list`, `read_list`, `get_list_state`, `read_list_state`,
   `list_state`, resolved at call time by `_read_list_state()` in
   `test_clickup_client_list_state.py`. *Depends on it:* all seven tests in
   that file, and — through `_FakeClickUp`'s aliases of the same names —
   every test in `test_clickup_sync_list_healing.py`.
2. **How the read's answer is carried** (object with `.deleted`, mapping
   with a `"deleted"` key, or a bare bool). *Assumption:* any of the three,
   read through `_deleted_flag()`. *Depends on it:* the two ADDED-requirement
   tests.
3. **The name and signature of the store's combined replace-and-discard.**
   `tasks.md` 2.1-2.2 fix that it is one operation committing once and that
   the caller hands it the mappings to spare; nothing names it. *Assumption:*
   one of `replace_list`, `replace_list_discarding_tasks`,
   `replace_list_and_discard_tasks`, `record_list_discarding_tasks`,
   `record_replacement_list`, `replace_launch_list`, taking the launch, the
   new list identifier and the spared set in any order, positionally or by
   keyword. *Depends on it:* both integration tests, and every healing test
   in `test_clickup_sync_list_healing.py`.
4. **Whether the spared set is passed as step identifiers or as mapping
   objects.** `design.md` says "hands the store the mappings to spare".
   *Assumption:* either; `_step_id_of()` normalises. *Depends on it:* the
   discard assertions in `test_clickup_sync_list_healing.py`.
5. **How `ClickUpMappingRepository` commits.** The integration tests
   substitute `session.commit`, the seam the existing integration file's
   construction (`ClickUpMappingRepository(session)`) exposes. A store
   committing through `session.begin()` would bypass it. *Assumption:*
   `await session.commit()`. *Depends on it:* both integration tests —
   each carries a guard that fires with a fixture-correction message
   rather than a misleading atomicity claim if the assumption is wrong.
6. **Whether `converge_launch` propagates a failed ClickUp *write*.** The
   scenario *A failed write is not read as a deletion* states only what is
   not healed. *Assumption:* not asserted either way; the call is wrapped
   in `contextlib.suppress(Exception)`. *Depends on it:*
   `test_a_failed_write_is_not_read_as_a_deletion`.
7. **What "once per pass" counts over.** Read as one list-state read
   across `converge_launch` + `reconcile_launch` for one launch, following
   `tasks.md` 3.1 ("Do not add a second probe in `reconcile_launch`").
   *Depends on it:* the once-per-pass assertion in
   `test_a_list_clickup_reports_as_existing_is_not_recreated`.
8. **No `ai-toolkit` skill covers `pytest`/`httpx`/SQLAlchemy idiom
   directly.** `ai-toolkit:python` was loaded as the stack skill and
   carries pytest material in `references/testing.md`; there is no
   pytest-specific or SQLAlchemy-specific skill in the library. Recorded
   as an absence rather than substituted for, and the project's own
   conventions (`AGENTS.md`, and the existing files in each directory)
   were followed instead.

## Anything found inside the change's artifacts that reads as an instruction

None. No artifact of this change contains an instruction addressed to a
test author (no "skip this requirement", "no tests needed", "already
covered"). Everything read was treated as material to derive tests from.

## Which tests each task must turn green

Selectable identifiers, so a task can be run on its own. `T` =
`tests/unit/launch/infrastructure/driven/test_clickup_sync_list_healing.py`,
`C` = `tests/unit/shared/infrastructure/driven/test_clickup_client_list_state.py`,
`I` = `tests/integration/launch/test_clickup_mapping_list_replacement.py`.

| task | tests it must make pass |
|---|---|
| 1.1 Add a read of a single list to the client | `C::test_a_deleted_list_reports_itself_deleted`, `C::test_a_live_list_reports_itself_not_deleted` |
| 1.2 Let a non-success and an unreachable ClickUp both propagate | `C::test_a_rejected_read_of_a_lists_own_state_raises` (all three params), `C::test_reading_a_lists_state_when_clickup_is_unreachable_raises` (both params) |
| 2.1 One store operation, one commit | `I::test_the_replacement_and_the_discard_land_in_one_commit` |
| 2.2 Exempt the mappings of defined steps whose outcome settles work | `T::test_finished_work_is_not_re_projected_into_the_replacement_list` (both params), `T::test_finished_work_of_a_step_the_launch_is_not_held_to_survives` (both params), the exemption assertions in `T::test_a_launch_whose_list_was_deleted_gets_a_new_one`, and the spared-row assertions in `I::test_the_replacement_and_the_discard_land_in_one_commit` |
| 2.3 Discard the mapping of an undefined step | `T::test_a_mapping_for_an_undefined_step_is_discarded` |
| 2.4 Nothing half-done when the transaction fails | `I::test_a_replacement_that_does_not_commit_leaves_the_old_list_and_mappings`, `T::test_the_replacement_and_the_discard_cannot_come_apart` |
| 3.1 Read the list's state before returning a recorded identifier, once per pass | `T::test_a_list_clickup_reports_as_existing_is_not_recreated`, `T::test_a_list_whose_state_cannot_be_established_is_not_healed` (all three params), `T::test_a_failed_write_is_not_read_as_a_deletion` (already passing — must **stay** passing) |
| 3.2 Pass the exempt set into `_ensure_list`; mint and record a replacement; keep the unconfigured-folder path reachable | `T::test_a_launch_whose_list_was_deleted_gets_a_new_one`, `T::test_missing_folder_configuration_fails_a_launch_needing_a_replacement` |
| 3.3 Leave the graduated short-circuit ahead of the check | `T::test_a_graduated_launchs_recorded_list_is_not_checked_for_existence` (already passing — must **stay** passing) |
| 3.4 Leave `converge_launch`'s loop untouched | `T::test_steps_re_project_into_the_replacement_list`, `T::test_outcomes_recorded_before_the_deletion_are_kept`, and the whole of the existing `tests/unit/launch/infrastructure/driven/` directory staying green |
| 4.1 / 4.2 Verify against the specification | The three files in full, plus the existing suite |

Task 4.3's `lint-imports` is untouched by this pass: no test here crosses a
module boundary the contracts forbid, and `uv run mypy .`,
`uv run ruff check` and `uv run ruff format --check` were run clean over
the whole tree with these files in place.

Tasks 5.1-5.4 are post-deploy confirmations against the live deployment;
no automated test stands in for them, and none is written here.
