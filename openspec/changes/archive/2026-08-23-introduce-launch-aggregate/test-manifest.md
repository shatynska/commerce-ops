# Test manifest — `introduce-launch-aggregate`

Written by the test-writer pass on 2026-08-23, strictly from the delta
spec at
`openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md`,
compared against the existing requirement text at
`openspec/specs/launch-instance/spec.md` for the `MODIFIED`/`REMOVED`
operations. No implementation source was read; the definition-side
vocabulary (playbook, outcomes, anchors, lifecycle stages, catalog
surfaces) was taken from the existing tests under `tests/**`, which
record it.

This file is not an artifact the OpenSpec schema knows about — it will
not appear among `openspec instructions apply`'s context files and must
be read on purpose before implementing.

**Property the dispatcher can rely on:** this pass added tests and never
subtracted — no existing test file was edited, deleted, or disabled.

## Baseline

Scoped baseline (scope: `tests/unit/launch`, `tests/unit/shared/domain`,
`tests/integration/launch`), taken with `uv run pytest` before any new
test was written: **144 passed, 18 skipped, 0 failed** (the 18 skips are
the integration tier's documented skip when `DATABASE_URL` is unset).
Re-run after this pass with the five new files excluded: identical.
Every new test currently fails at collection on the absent target
(`ModuleNotFoundError: commerce_ops.launch.domain.launch_run` /
`ImportError` on the new application and repository names). Per
`ai-toolkit:testing`, that establishes only absence — the assertions
have never executed.

## New test files

- `tests/unit/launch/domain/test_launch_run.py`
- `tests/unit/launch/domain/test_launch_gate_advance.py`
- `tests/unit/launch/domain/test_launch_dates.py`
- `tests/unit/launch/application/test_graduation.py`
- `tests/integration/launch/test_launch_repository.py`

Run with `uv run pytest <path>::<test_name>`; all names below are
runner-selectable.

## Scenario accounting

The delta contains **35** `#### Scenario:` blocks; each is accounted for
exactly once below (a scenario whose THEN clauses span two tiers is
covered by two named tests, still one accounting entry). 34 covered, 1
uncovered-with-reason; the `REMOVED` requirement carries no scenario
blocks and is accounted for in the obsolete list.

### MODIFIED: A launch position is persisted for a catalog product

1. *A launch position is created for an existing product* — covered by
   `tests/integration/launch/test_launch_repository.py::test_a_started_launch_is_persisted_for_an_existing_product`
   (persistence, pinned version, absent launch date) **and**
   `tests/unit/launch/domain/test_launch_run.py::test_starting_reports_a_launch_started_occurrence`
   (the `LaunchStarted` occurrence with product id and pinned version).
2. *A launch position for an unknown product is rejected* — covered by
   `tests/integration/launch/test_launch_repository.py::test_a_launch_for_an_unknown_product_is_rejected`.
3. *A second launch position for the same product is rejected* — covered by
   `tests/integration/launch/test_launch_repository.py::test_a_second_launch_for_the_same_product_is_rejected`.

### MODIFIED: A product's current gate is restricted to the launch-playbook gate sequence

4. *A new product defaults to the first gate* — covered by
   `tests/unit/launch/domain/test_launch_run.py::test_a_started_launch_begins_at_the_first_gate`.
5. *An unrecognized gate is rejected* — covered by
   `tests/integration/launch/test_launch_repository.py::test_persisting_an_unrecognized_gate_is_rejected`.

### MODIFIED: A launch position can be read back by product identifier

6. *A launch position is retrieved* — covered by
   `tests/integration/launch/test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state`.
7. *A product without a launch position reports absence* — covered by
   `tests/integration/launch/test_launch_repository.py::test_a_product_without_a_launch_reports_absence`.

### ADDED: A step outcome is recorded with provenance

8. *A satisfied step is recorded with its provenance* — covered by
   `tests/unit/launch/domain/test_launch_run.py::test_a_satisfied_step_is_recorded_with_its_provenance`.
9. *A re-recorded outcome replaces the stored one without reopening gates* — covered by
   `tests/unit/launch/domain/test_launch_run.py::test_a_re_recorded_outcome_replaces_the_stored_one_without_reopening_gates`.
10. *A prohibited-tactic step is refused* — covered by
    `tests/unit/launch/domain/test_launch_run.py::test_a_prohibited_tactic_step_is_refused`.
11. *Satisfying a prohibited-tactic step is rejected* — covered by
    `tests/unit/launch/domain/test_launch_run.py::test_satisfying_a_prohibited_tactic_step_is_rejected`.
12. *Refusing an ordinary step is rejected* — covered by
    `tests/unit/launch/domain/test_launch_run.py::test_refusing_an_ordinary_step_is_rejected`.
13. *An unknown step identifier is rejected* — covered by
    `tests/unit/launch/domain/test_launch_run.py::test_an_unknown_step_identifier_is_rejected`.

### ADDED: A gate opens only when every blocking condition attached to it is satisfied

14. *An automatic gate opens when every blocking condition is satisfied* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_automatic_gate_opens_when_every_blocking_condition_is_satisfied`.
15. *An advance with an unresolved blocking step is rejected* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_advance_with_an_unresolved_blocking_step_is_rejected`.
16. *A refused prohibited-tactic step never holds a gate closed* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_refused_prohibited_tactic_step_never_holds_a_gate_closed`.
17. *An advance moves to exactly the next gate* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_advance_moves_to_exactly_the_next_gate`
    (positive half, walked over the whole sequence). The clause "the
    advance operation offers no way to target a later or an earlier
    gate" is **deliberately untested** as a negative: the nonexistence
    of an unspecified targeting API cannot be asserted behaviorally, and
    a signature-introspection assertion would invent a constraint on the
    command's parameters that no artifact states.

### ADDED: A confirmation gate additionally requires a recorded approval

18. *A confirmation gate with satisfied conditions but no approval stays closed* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_confirmation_gate_with_satisfied_conditions_but_no_approval_stays_closed`.
19. *A confirmation gate opens once approved* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_confirmation_gate_opens_once_approved`.
20. *An approval without a named approver is rejected* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_approval_without_a_named_approver_is_rejected`.
21. *A rejecting decision keeps the gate closed* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_rejecting_decision_keeps_the_gate_closed`.
22. *A posture on a non-graduation approval is rejected* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_posture_on_a_non_graduation_approval_is_rejected`.

The requirement statement's "An automatic gate SHALL NOT require an
approval" is covered implicitly (the walks through `listable` ..
`ignition` in several tests advance automatic gates with no approval
recorded); no dedicated test asserts it — recorded as deliberately
implicit rather than omitted unthinkingly.

### ADDED: A metric condition is satisfied by human attestation until live evaluation exists

23. *An attested metric condition counts as satisfied* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_attested_metric_condition_counts_as_satisfied`.
24. *An unattested metric condition keeps the gate closed* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_unattested_metric_condition_keeps_the_gate_closed`.
25. *An attestation for a condition the gate does not author is rejected* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_attestation_for_a_condition_the_gate_does_not_author_is_rejected`.

### ADDED: Step due dates derive from the launch date and re-resolve when it moves

26. *A step's due period derives from the launch date* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_a_steps_due_period_derives_from_the_launch_date`.
27. *Without a launch date there are no due periods* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_without_a_launch_date_there_are_no_due_periods`.
28. *Moving the launch date re-resolves every due period* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_moving_the_launch_date_re_resolves_every_due_period`.

### ADDED: The launch date is reported at risk when a blocking unresolved step is overdue

29. *An overdue unresolved blocking step puts the date at risk* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_an_overdue_unresolved_blocking_step_puts_the_date_at_risk`.
30. *An overdue non-blocking step does not put the date at risk* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_an_overdue_non_blocking_step_does_not_put_the_date_at_risk`.
31. *A resolved overdue step does not put the date at risk* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_a_resolved_overdue_step_does_not_put_the_date_at_risk`.
32. *A launch without a launch date is never at risk* — covered by
    `tests/unit/launch/domain/test_launch_dates.py::test_a_launch_without_a_launch_date_is_never_at_risk`.

### ADDED: Graduation stamps the catalog product steady-state

33. *Graduation stamps the product with the approver's chosen posture* — covered by
    `tests/unit/launch/application/test_graduation.py::test_graduation_stamps_the_product_with_the_approvers_chosen_posture`
    — **partially**: the `LaunchGraduated` occurrence, the chosen
    posture, the approver as confirmer, and the persist-before-stamp
    ordering are asserted against a fake stage-stamping collaborator.
    The clause "for a product in a launching stage ... the catalog
    product's stage becomes steady state" is observed as the stamp being
    *requested* with `SteadyState(chosen posture)`, not as a real
    catalog row changing — the real transition rules are `catalog`'s own
    already-tested behavior, and this module's unit tier stubs
    cross-module I/O. Recorded as **deliberately untested** at the
    end-to-end level: no test drives a real catalog product from
    `Launching` to `SteadyState` through graduation, because no HTTP or
    Slack driving adapter exists in this slice to anchor such a test,
    and the delta's own migration notes place that wiring in `tasks.md`
    3.3's verification.
34. *A rejected stage stamp leaves the advance standing* — covered by
    `tests/unit/launch/application/test_graduation.py::test_a_rejected_stage_stamp_leaves_the_advance_standing`.
35. *A graduation approval without a posture is rejected* — covered by
    `tests/unit/launch/domain/test_launch_gate_advance.py::test_a_graduation_approval_without_a_posture_is_rejected`.

### Uncovered scenarios

None omitted: every scenario above is covered by at least one named
test. The two partial/deliberate limits (17's negative half, 33's
end-to-end half) are recorded inline above with their reasons.

## Assertion classification

Every assertion in the new files carries an inline `SPECIFIED` /
`DERIVED` / `DELIBERATELY UNTESTED` comment, the convention this
repository's earlier passes established. Summary of the derived
assertions an implementer is *not* bound to beyond review:

- All module paths, class names, call shapes, and attribute spellings
  (see *Unresolved project questions*): correcting them is a fixture
  correction; the postconditions are what must survive.
- "The stored gate is unchanged" on the create/persist rejection paths
  is read as *nothing new persisted / prior value re-read intact*, the
  same reading the previous launch-instance pass recorded.
- `GateBlocked` / `LaunchDateAtRisk` "naming" a condition or step is
  asserted through the raised error's / report's `str` rendering.
- The graduation error "naming the manual catalog correction" is
  asserted as, at minimum, naming the product identifier.

## Obsolete-test candidates

Search scope: the dispatched test-path glob `tests/**/test_*.py` only,
via content search for the superseded surface (`update_current_gate`,
`LaunchPositionRepository`, `launch_position`); exactly one pre-existing
file matched. No earlier `test-manifest.md` path was supplied with this
dispatch, so no manifest mapping was available to cross-check. These are
**candidates for human confirmation**, not conclusions — nothing was
edited or deleted by this pass. `tasks.md` 4.4 already schedules their
reconciliation.

All entries are in
`tests/integration/launch/test_launch_position_repository.py`, and all
run today (they are part of the green baseline; they will break when the
old repository surface is removed per `tasks.md` 2.3):

1. `::test_updating_the_current_gate_to_a_valid_gate_persists` —
   superseded by the **REMOVED** requirement *A product's current gate
   can be updated*. Evidence: its docstring names the removed
   requirement's scenario and it calls
   `positions.update_current_gate(product_id, "order")`, the exact
   mutation path the delta retires.
2. `::test_updating_a_product_with_no_launch_position_is_rejected` —
   superseded by the same **REMOVED** requirement. Evidence: docstring
   names the removed scenario *Updating a nonexistent product is
   rejected*; exercises `update_current_gate`.
3. `::test_updating_to_an_unrecognized_gate_is_rejected` — superseded
   jointly by the **REMOVED** requirement (it exercises
   `update_current_gate`) and the **MODIFIED** *current gate is
   restricted* requirement, whose revised scenario re-words the
   rejection to the persist path (replacement:
   `test_launch_repository.py::test_persisting_an_unrecognized_gate_is_rejected`).
4. `::test_creating_with_each_of_the_eight_gate_ids_is_accepted` —
   superseded by the **MODIFIED** *current gate is restricted*
   requirement. Evidence: it asserts a launch can be *created at any of
   the eight gates* via `create(..., current_gate=gate_id)`, which the
   revised text now forbids outright ("a launch is never started at any
   other gate" than `commit`). This is the one entry that *contradicts*
   the new spec rather than merely using a retired surface.
5. `::test_a_launch_position_is_retrieved_with_every_field` — superseded
   by the **MODIFIED** *read back* requirement. Evidence: it creates
   with an explicit `current_gate="order"` (a start shape the revised
   spec forbids) and asserts the flat-record field set the revised
   scenario replaces with full-state rehydration (replacement:
   `test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state`).
6. `::test_a_launch_position_is_created_for_an_existing_product`,
   `::test_a_launch_position_for_an_unknown_product_is_rejected`,
   `::test_a_second_launch_position_for_the_same_product_is_rejected`,
   `::test_a_new_launch_position_defaults_to_the_first_gate`,
   `::test_creating_with_an_unrecognized_gate_is_rejected`,
   `::test_a_product_without_a_launch_position_reports_absence` —
   superseded by the **MODIFIED** requirements as a group. Evidence:
   each exercises the retired `create(...)` repository surface that
   `tasks.md` 2.3 / `design.md` Decision 7 replace with
   `save(launch)` / `get_by_product_id`; their postconditions survive in
   the revised requirements and are re-covered by the new
   `test_launch_repository.py`. These are surface-obsolete rather than
   behavior-contradicting.

## Unresolved project questions

No recorded convention answers these; each was resolved by assumption,
recorded here and in the assuming files' docstrings, and every new test
depends on the first two:

1. **The entire new interface shape is invented** (no artifact fixes
   spellings): `commerce_ops.launch.domain.launch_run` exporting
   `Launch`, `Provenance(source, who, when, evidence)`,
   `GateApproval(decision, approver, when, posture)`, `ApprovalDecision`
   (`APPROVING`/`REJECTING`), `MetricAttestation(gate_id, metric_id,
   attester, when, evidence)`, events (`LaunchStarted`, `StepSatisfied`,
   `StepRefused`, `GateOpened`, `LaunchDateMoved`, `LaunchGraduated`),
   and `LaunchError` as the single domain rejection signal;
   `Launch.start(product_id=, playbook=, launch_date=None) -> (Launch,
   LaunchStarted)`; commands mutating in place and returning event
   tuples; read surfaces `current_gate` (gate-id string),
   `playbook_version`, `launch_date`, `progress_for(step_id)`,
   `approval_for(gate_id)`, `.attestations`,
   `due_period_for(playbook, step_id)`, `date_at_risk(playbook, as_of)`.
   Depended on by: every new test. Each file funnels the invented calls
   through module-level helpers (`_start`, `_approval`, `_provenance`,
   `_attestation`) so a differing implementation is a single-point
   fixture correction per file.
2. **Repository name/module**:
   `commerce_ops.launch.infrastructure.driven.launch_repository`
   exporting `LaunchRepository` (the name `design.md` Decision 7 uses)
   and `LaunchRepositoryError`; alternative — evolved in place under
   `launch_position_repository`'s old names. Depended on by the five
   integration tests.
3. **Application wiring for graduation**: `advance_gate` exported from
   `commerce_ops.launch.application`, taking `launches` / `playbooks` /
   `stamp_steady_state` collaborators and `product_id`; the stamping
   collaborator called with `change_stage`'s shape minus the store; a
   rejected stamp surfacing as `GraduationStampError`. If the use case
   instead takes the catalog store and calls
   `catalog.application.change_stage` itself, the fakes in
   `test_graduation.py` are the fixture to correct. Depended on by the
   two graduation tests.
4. **Rejection layering**: whether an unnamed approver / misplaced
   posture rejects at value construction (`ValueError`, the project's
   construction-time convention) or at the recording command
   (`LaunchError`) is unrecorded; the affected tests accept either site
   (`REJECTED` tuples), since the delta fixes the rejection, not its
   layer.
5. **Timestamp convention**: provenance/approval/attestation timestamps
   are assumed timezone-aware UTC (the convention the catalog tests
   record); if the persistence layer stores naive datetimes, the
   integration round-trip equality assertions need a recorded fixture
   correction rather than silent weakening.
6. **Stack-skill coverage**: `ai-toolkit:testing` and `ai-toolkit:python`
   were loaded for this pass. The library carries no skill for
   SQLAlchemy/asyncpg integration testing specifically; the integration
   file follows the conventions its sibling files record instead.

## What the implementation step must make pass

`uv run pytest tests/unit/launch tests/integration/launch` — the three
domain files and the application file must pass with no DB; the
integration file needs `DATABASE_URL` pointing at a Postgres with
`alembic upgrade head` applied (including this change's three child
tables). The pre-existing `test_launch_position_repository.py` will
break when `update_current_gate`/`create` are removed — that removal is
to be reconciled against the obsolete list above (`tasks.md` 4.4), by a
human-confirmed deletion, not by this pass.
