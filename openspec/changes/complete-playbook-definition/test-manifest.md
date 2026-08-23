# Test manifest — complete-playbook-definition

Written 2026-08-23, before any implementation of this change exists. This
file is not an artifact the OpenSpec schema knows about: it will not appear
among `openspec instructions apply`'s context files and must be read on
purpose by whoever implements the change.

This pass is **additive only**: it wrote the eight new test files listed
below and this manifest, and edited, deleted, or disabled nothing.
Obsolete-test entries below are candidates for human confirmation, never
conclusions acted on.

## Baseline

Scoped baseline, taken before any new test was written: `uv run pytest
tests/unit tests/agents` (the commit-time tier — the scope that bears on
this change; the integration tier was not run because it requires Postgres
and this change touches no I/O): **370 passed, 0 failed**.

Re-run after writing, with the new files excluded via `--ignore`: still
370 passed — the pre-existing suite is untouched.

## State of the new tests

All eight new files fail **at collection** on absent targets
(`ModuleNotFoundError: commerce_ops.launch`, `ModuleNotFoundError:
commerce_ops.shared.domain.discipline`, `ImportError: cannot import name
'MetricId'`). Per `ai-toolkit:testing`, this is failure state 2: it
establishes only that the targets are absent; no assertion has executed
yet. Expected and correct — the code under test does not exist and this
pass never creates it.

Side effect worth knowing: the pre-commit pytest hook runs the whole
`tests/unit` + `tests/agents` tree, and collection errors interrupt the
run, so commits will be blocked until the implementation's first commits
(the module rename and the shared vocabulary) make these files importable.

## New test files

- `tests/unit/shared/domain/test_discipline.py`
- `tests/unit/shared/domain/test_metric_id.py`
- `tests/unit/launch/domain/test_gate_conditions.py`
- `tests/unit/launch/domain/test_step_outcome.py`
- `tests/unit/launch/domain/test_step_definition_discipline.py`
- `tests/unit/launch/domain/test_playbook_coherence_completion.py`
- `tests/unit/launch/infrastructure/test_playbook_loader_completion.py`
- `tests/unit/launch/application/test_report_undecided_rule_policies.py`

New directories carry no `__init__.py`, matching the majority convention
in the tree (`tests/unit/shared/domain` has none); all new basenames are
unique across the tree. Ruff (check + format) passes on all eight files;
mypy was not run against them because their import targets are absent.

## Scenario accounting

Count: the two delta specs contain **34** `#### Scenario:` blocks
(27 in `launch-playbook`, 7 in `shared-vocabulary`). Each is accounted for
exactly once below: 33 covered, 1 uncovered (the `REMOVED` requirement's
scenario, per the operation itself).

Scenarios unchanged in substance by a `MODIFIED` requirement are accounted
to the pre-existing tests that cover them. Those files live under
`tests/unit/products/` until task 1.2 relocates them to
`tests/unit/launch/`; the relocation and the mechanical `track:` →
`discipline:` fixture corrections inside them are the implementer's
(tasks 1.2, 3.3) — this pass touched none of them.

### launch-playbook — ADDED: A gate carries authored metric conditions

| Scenario | Tests |
|---|---|
| A gate's metric conditions are read back | `tests/unit/launch/domain/test_gate_conditions.py::test_a_gates_metric_conditions_are_read_back`; file boundary: `tests/unit/launch/infrastructure/test_playbook_loader_completion.py::test_a_shipped_metric_checked_gate_reports_its_conditions` (3 params) |
| A gate with no metric conditions is valid | `tests/unit/launch/domain/test_gate_conditions.py::test_a_gate_with_no_metric_conditions_is_valid`; file boundary: `tests/unit/launch/infrastructure/test_playbook_loader_completion.py::test_shipped_gates_without_authored_conditions_report_none` |

Extra, DERIVED from the requirement statement ("zero or more"):
`test_gate_conditions.py::test_a_gate_may_carry_more_than_one_metric_condition`.

### launch-playbook — ADDED: Gate conditions unify step obligations and metric conditions

| Scenario | Tests |
|---|---|
| A blocking step appears as a step obligation | `tests/unit/launch/domain/test_gate_conditions.py::test_a_blocking_step_appears_as_a_step_obligation` |
| A non-blocking step produces no condition | `tests/unit/launch/domain/test_gate_conditions.py::test_a_non_blocking_step_produces_no_condition` |
| Authored metric conditions appear alongside derived obligations | `tests/unit/launch/domain/test_gate_conditions.py::test_authored_metric_conditions_appear_alongside_derived_obligations` |

Extra, DERIVED from the requirement statement ("attached to the gate"):
`test_gate_conditions.py::test_conditions_are_scoped_to_the_asked_gate`.

### launch-playbook — ADDED: Step outcome vocabulary

| Scenario | Tests |
|---|---|
| A blocked outcome carries its reason | `tests/unit/launch/domain/test_step_outcome.py::test_a_blocked_outcome_carries_its_reason` (plus the `NotApplicable` counterpart `::test_a_not_applicable_outcome_carries_its_reason`, derived from the requirement statement) |
| An outcome requiring a reason rejects an empty one | `tests/unit/launch/domain/test_step_outcome.py::test_an_outcome_requiring_a_reason_rejects_an_empty_one[blocked]` and `[not-applicable]` |
| A prohibited tactic can only terminate in refusal | `tests/unit/launch/domain/test_step_outcome.py::test_a_prohibited_tactic_can_only_terminate_in_refusal`; completeness half: `::test_refusal_is_the_only_terminal_outcome_for_a_prohibited_tactic` |
| An ordinary step cannot be refused | `tests/unit/launch/domain/test_step_outcome.py::test_an_ordinary_step_cannot_be_refused` (parametrized over `Hazard.NONE` and `Hazard.COMPLIANCE_OBLIGATION`; select by bare name) |
| Blocked is never terminal, inapplicability is | `tests/unit/launch/domain/test_step_outcome.py::test_blocked_is_never_terminal_and_inapplicability_is` (both hazard params) |

### launch-playbook — ADDED: Discipline is drawn from the shared vocabulary

| Scenario | Tests |
|---|---|
| Discipline is restricted to the shared vocabulary | `tests/unit/launch/domain/test_step_definition_discipline.py::test_a_discipline_outside_the_shared_vocabulary_is_rejected`; permitted side: `::test_each_shared_discipline_is_accepted_on_a_step` |

### launch-playbook — ADDED: Undecided rule policies are reported

| Scenario | Tests |
|---|---|
| Steps without a rule policy are listed | `tests/unit/launch/application/test_report_undecided_rule_policies.py::test_steps_without_a_rule_policy_are_listed` |
| A fully decided playbook reports nothing | `tests/unit/launch/application/test_report_undecided_rule_policies.py::test_a_fully_decided_playbook_reports_nothing` |

### launch-playbook — MODIFIED: A step definition declares how it is to be resolved

| Scenario | Tests |
|---|---|
| A step definition is read back with every declared attribute | New (renamed attribute): `tests/unit/launch/domain/test_step_definition_discipline.py::test_step_definition_is_read_back_with_every_declared_attribute` and `::test_unauthored_optional_attributes_are_absent` |
| Steps can be selected by gate and by scope | New: `tests/unit/launch/domain/test_step_definition_discipline.py::test_steps_can_be_selected_by_gate_and_by_scope` (behaviour unchanged; re-derived against the renamed module). Pre-existing counterpart: `tests/unit/products/domain/test_launch_playbook.py::test_steps_can_be_selected_by_gate_and_by_scope` |

### launch-playbook — MODIFIED: An incoherent playbook is rejected at load time

The two rules this delta **adds** are covered by new tests; the rules it
carries forward unchanged are accounted to the pre-existing tests.

| Scenario | Tests |
|---|---|
| Gate sequence deviates from the specification | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`, `::test_gate_sequence_with_an_extra_gate_is_rejected`, `::test_gate_sequence_in_the_wrong_order_is_rejected`, `::test_gate_sequence_repeating_a_position_is_rejected` |
| A gate's opening mode disagrees with the specification | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected` |
| Duplicate step identifier | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_duplicate_step_identifier_is_rejected` |
| Step references an unknown gate | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected` |
| Automation without a decided rule | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected`, `::test_ai_assisted_step_without_a_rule_policy_is_rejected`, permitted side `::test_automated_step_with_a_rule_policy_is_accepted` |
| A prohibited tactic cannot block a gate | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`, permitted side `::test_prohibited_tactic_that_does_not_block_is_accepted` |
| A lesson cannot block a gate (**new rule**) | `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_lesson_step_marked_blocking_is_rejected`; permitted side `::test_a_non_blocking_lesson_step_is_accepted` |
| A malformed metric condition is rejected (**new rule**) | `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_metric_condition_with_an_empty_threshold_is_rejected` — see Q9 below for the level reading this rests on. File boundary: deliberately untested (no metric-condition YAML shape is fixed by any artifact; the shipped file exercises only the well-formed path) |
| Multiple violations are reported together | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_two_distinct_violations_are_reported_together`; as revised (the two new faults participate in aggregation): `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_the_two_new_faults_are_reported_together` |
| A malformed step is reported alongside a coherence violation | Pre-existing: `tests/unit/products/infrastructure/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation` (its invented YAML uses the `track:` key — a mechanical fixture correction to `discipline:` during task 3, not a weakening) |
| A coherent playbook loads | Pre-existing: `tests/unit/products/domain/test_launch_playbook.py::test_a_coherent_playbook_loads`, `tests/unit/products/infrastructure/test_playbook_loader.py::test_a_coherent_playbook_file_loads`; as revised (completed surface): `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_coherent_playbook_with_the_completed_surface_loads`, `tests/unit/launch/infrastructure/test_playbook_loader_completion.py::test_the_shipped_playbook_still_loads_coherently` |

### launch-playbook — REMOVED: Track names one of a fixed set of disciplines

| Scenario | Accounting |
|---|---|
| Track is restricted to the known disciplines | **Uncovered, by the operation itself**: removed behaviour is not to be tested. Its validation intent survives via the ADDED requirement *Discipline is drawn from the shared vocabulary* (covered above); the tests bearing on the removed form are in the obsolete list below |

### shared-vocabulary — ADDED: Discipline vocabulary names the owning disciplines

| Scenario | Tests |
|---|---|
| A known discipline is constructed | `tests/unit/shared/domain/test_discipline.py::test_a_known_discipline_is_constructed`; all twelve: `::test_each_specified_discipline_is_constructible` (12 params); closure at twelve: `::test_the_discipline_set_is_exactly_twelve` |
| An unknown discipline is rejected | `tests/unit/shared/domain/test_discipline.py::test_an_unknown_discipline_is_rejected` |

### shared-vocabulary — MODIFIED: Identity value objects validate at construction

| Scenario | Tests |
|---|---|
| A valid SKU is constructed | Pre-existing (unchanged): `tests/unit/shared/domain/test_identity_value_objects.py::test_a_valid_sku_is_constructed_and_reports_its_value` |
| An empty identity value is rejected | Pre-existing four legs: `tests/unit/shared/domain/test_identity_value_objects.py::test_an_empty_identity_value_is_rejected` (4 params); new metric-identifier leg: `tests/unit/shared/domain/test_metric_id.py::test_an_empty_metric_identifier_is_rejected` |
| A padded identity value is rejected | Pre-existing legs: `tests/unit/shared/domain/test_identity_value_objects.py::test_a_padded_identity_value_is_rejected_not_trimmed` (6 params); new metric-identifier leg: `tests/unit/shared/domain/test_metric_id.py::test_a_padded_metric_identifier_is_rejected_not_trimmed[leading]` and `[trailing]` |
| A malformed ASIN is rejected | Pre-existing (unchanged): `tests/unit/shared/domain/test_identity_value_objects.py::test_a_malformed_asin_is_rejected_with_the_value_named` (3 params) |
| A metric identifier does not require a defined metric | `tests/unit/shared/domain/test_metric_id.py::test_a_metric_identifier_does_not_require_a_defined_metric` |

Extra, SPECIFIED against the main spec's unchanged requirement *Value
objects are immutable and compare by value* (which covers "every
vocabulary value object", now including `MetricId`):
`test_metric_id.py::test_two_metric_identifiers_with_the_same_value_are_equal`,
`::test_mutation_of_a_metric_identifier_fails`.

## Assertion classification

Inline per test, following the house style of the earlier passes: each
assertion is commented `SPECIFIED` (traces to a requirement or scenario
clause, cited) or `DERIVED` (inferred; the inference stated), and each
deliberately untested case is recorded either in this manifest or in the
test's docstring. Summary of the deliberate gaps:

- **File-boundary rejection of an empty metric-condition threshold** — no
  artifact fixes the metric-condition YAML shape; inventing one to provoke
  the fault would add a second invented shape for the implementer to
  reconcile. Domain-level coverage exists (see Q9).
- **`StepOutcome` runtime recording and transitions** — explicitly
  out of scope in the requirement ("belongs to the launch-instance
  capability, not here") and in `design.md` (slice 3).
- **Which YAML wire spelling each new enum/type uses** — only the shipped
  file's observable result is asserted, not the authored spelling.
- **Empty-value error "naming the offending value" for `MetricId("")`** —
  same deliberately narrower reading the earlier pass recorded: an empty
  string has no content for a message to name; only the rejection is
  asserted.
- **The exact wording of any error message** — only that it names the
  offending step or gate, which is what the spec requires.

## Obsolete tests (candidates for human confirmation — no conclusion here)

Search scope: the dispatched test-path glob `tests/**/test_*.py`, plus the
pointers inside those files' own docstrings. No earlier `test-manifest.md`
path was supplied in the dispatch, so none was used. All entries below
were found by that search; where I say "no bearing test exists", I mean
none was found by this bounded search.

Superseded by the REMOVED requirement *Track names one of a fixed set of
disciplines* together with the `Track` → `Discipline` migration (the delta:
"there SHALL be exactly one name for it"):

1. `tests/unit/products/domain/test_launch_playbook.py::test_each_specified_track_value_is_accepted`
   — evidence: parametrized over `SPECIFIED_TRACKS`, resolves members via
   `getattr(Track, ...)`, asserts `read_back.track is track`. Replacement
   coverage: `test_step_definition_discipline.py::test_each_shared_discipline_is_accepted_on_a_step`
   and `test_discipline.py`.
2. `tests/unit/products/domain/test_launch_playbook.py::test_track_outside_the_fixed_set_is_rejected`
   — evidence: constructs a step with `track="not-a-recognised-track"` and
   asserts the error names it. Replacement:
   `test_step_definition_discipline.py::test_a_discipline_outside_the_shared_vocabulary_is_rejected`.
3. `tests/unit/products/infrastructure/test_playbook_loader.py::test_step_with_an_invalid_track_is_reported_alongside_a_coherence_violation`
   — evidence: YAML fixture `track: not-a-recognised-track`; assertions
   `"not-a-recognised-track" in message`. The unrecognised-value fault
   survives under the new name; the *file-boundary aggregation* pairing it
   exercises is otherwise still covered by
   `::test_malformed_step_is_reported_alongside_a_coherence_violation`.

Superseded by the MODIFIED requirement *A step definition declares how it
is to be resolved* (attribute renamed):

4. `tests/unit/products/domain/test_launch_playbook.py::test_step_definition_is_read_back_with_every_declared_attribute`
   — evidence: asserts `read_back.track is track`. Replacement:
   `test_step_definition_discipline.py::test_step_definition_is_read_back_with_every_declared_attribute`
   (which additionally asserts `not hasattr(read_back, "track")`).

**Not obsolete, but needing mechanical correction during the rename**
(fixture-level references, not assertions on superseded behaviour): every
other test in `tests/unit/products/domain/test_launch_playbook.py` builds
steps through a `_step()` helper whose baseline uses the `track=` keyword
and imports `Track`; `tests/unit/products/infrastructure/test_playbook_loader.py`'s
YAML fixtures use the `track:` key; every file under `tests/unit/products/`
and `tests/integration/products/` imports `commerce_ops.products`, and so do
two files *outside* those directories —
`tests/unit/catalog/application/test_daily_digest.py` and
`tests/unit/shared/application/test_monitoring_notifier_port.py` — which the
rename's repo-wide grep (task 1.1/1.2) must also catch. Tasks
1.2 and 3.3 own these corrections; correcting a fixture's input is failure
state 3 in `ai-toolkit:testing`, never a licence to change what a test
asserts.

No other test in the glob asserts on `Track`, `track`, or the removed
requirement (checked by reading the two playbook test files and searching
the tree); the `MODIFIED` shared-vocabulary requirement supersedes no
existing assertion — it only extends the VO family, so
`test_identity_value_objects.py` stands unchanged.

## Unresolved project questions

Each recorded with the assumption taken and the tests depending on it.
None could be asked interactively; none was resolved silently.

- **Q1 — module path for `Discipline`.** Assumed
  `commerce_ops.shared.domain.discipline`, mirroring the
  one-module-per-concept convention (`identity.py`, `lifecycle_stage.py`).
  Depended on by every new file except `test_metric_id.py` and
  `test_playbook_loader_completion.py`.
- **Q2 — `MetricId` location and shape.** Assumed exported from
  `commerce_ops.shared.domain.identity` (tasks 2.2: "next to the existing
  identity VOs"), constructed from one positional string, `.value`
  accessor, `ValueError` on rejection — the shape every existing identity
  VO test assumes. Depends: `test_metric_id.py`, both gate-condition
  files.
- **Q3 — `MetricCondition` attribute names.** Assumed positional
  construction `MetricCondition(MetricId(...), "...")` with attributes
  `metric_id` and `threshold` (`proposal.md` writes
  `MetricCondition(metric_id, threshold)`); the spec's prose
  ("threshold description") makes `threshold_description` the recorded
  alternative. Depends: `test_gate_conditions.py`,
  `test_playbook_coherence_completion.py`,
  `test_playbook_loader_completion.py`.
- **Q4 — `StepObligation` attribute.** Assumed `step_id`, per
  `proposal.md`. Depends: `test_gate_conditions.py`.
- **Q5 — `StepOutcome` answering surface.** Assumed
  `permissible_terminal_outcomes(hazard)` returns a collection supporting
  `in` against the six exported designators (singletons for reasonless
  states, classes for `Blocked`/`NotApplicable`, per `design.md`
  Decision 4); `reason` as the attribute; `ValueError` for an empty
  reason. Depends: all of `test_step_outcome.py`.
- **Q6 — `Discipline` construction and rejection.** Assumed a by-value
  `Enum` (`Discipline("inventory")`) rejecting with `ValueError`. The
  twelve wire values are SPECIFIED; Python member names are deliberately
  never touched. Depends: `test_discipline.py`, and via
  `next(iter(Discipline))` every launch domain file.
- **Q7 — `report_undecided_rule_policies` signature and row shape.**
  Assumed it accepts a playbook source `Path` (the scenarios cannot be
  exercised against the zero-step shipped file otherwise) and returns rows
  with `identifier`, `gate`, `discipline`, `execution`. If the
  implementation can only read the shipped file, the two report scenarios
  are untestable as specified — that must come back as a finding, not be
  papered over. Depends: `test_report_undecided_rule_policies.py`.
- **Q8 — YAML document shape.** The gates document reuses the shape the
  earlier pass invented; the step documents add `discipline:` (tasks 3.2)
  and an invented `rule_policy:` key. A mismatch with the implemented
  shape is a fixture correction in the input, never in the assertions.
  Depends: `test_report_undecided_rule_policies.py`.
- **Q9 — where the empty-threshold fault lives.** The scenario requires
  "an error naming the gate carrying it", and tasks 4.3 places the fault
  in the aggregated load-time error, so the tests assume `MetricCondition`
  itself admits an empty description and the playbook rejects it naming
  the gate. If the implementation instead rejects at `MetricCondition`
  construction (a reading tasks 4.1's "frozen: ... non-empty threshold
  description" also admits), the fixtures error before asserting (state 3)
  and the divergence from the scenario's gate-naming clause must be
  reported. Depends: `test_playbook_coherence_completion.py` (two tests).
- **Q10 — where the unrecognised-discipline fault lives.** Assumed at
  `StepDefinition` construction, exactly where the predecessor pass placed
  the unrecognised-track fault (tasks 3.1 renames that fault's message
  rather than moving it). Depends:
  `test_step_definition_discipline.py::test_a_discipline_outside_the_shared_vocabulary_is_rejected`.
- **Q11 — stack-skill coverage.** The library carries `python` (and
  `testing`), both loaded for this pass; no stack under test here lacks a
  matching skill, so there is no skill-absence to record.

## What the implementation must make pass

Run, per task group as its targets land, and in full at task 7.3:

    uv run pytest tests/unit/shared/domain/test_discipline.py tests/unit/shared/domain/test_metric_id.py   # after task 2
    uv run pytest tests/unit/launch                                                                         # after tasks 3-6
    uv run pytest tests/unit tests/agents                                                                   # the whole commit tier, including the relocated pre-existing tests

Every test in the eight new files must pass with no pre-existing test
weakened, deleted, or disabled; the four obsolete candidates above are
resolved by human decision during the migration commits, not by this
manifest.
