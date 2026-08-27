# Test manifest — `let-the-handler-report-see-handlers`

Written by the test-writing pass, before any implementation of this change
exists. **This file is not an artifact the OpenSpec schema knows about**, so it
does not appear among `openspec instructions apply`'s context files and must be
read on purpose.

- Change root: `/home/shatynska/projects/commerce-ops-automated-step/openspec/changes/let-the-handler-report-see-handlers`
- Delta spec: `openspec/changes/let-the-handler-report-see-handlers/specs/launch-playbook/spec.md`
- Recorded spec compared against: `openspec/specs/launch-playbook/spec.md:476-502`
- Test command: `uv run pytest`
- New test file: `tests/unit/test_startup_handler_report_holds_the_registry.py`
- Extended, per `tasks.md` 1.3: `tests/unit/test_registrations_across_processes.py`
  gains scenario 1 as a third root beside the two composition roots it
  already compares. Written into the new file first (this pass is
  additive-only and may not edit an existing test file); relocated by the
  implementer, which `tasks.md` 1.3 specifies and the report flagged as a
  legitimate implementer choice. No existing assertion in that file was
  altered.

This pass **adds tests and never subtracts**. No existing test file was edited,
deleted or disabled, and no implementation code was written or modified.

## Baseline

Full, not scoped. Taken on the unmodified tree before any test here was
written:

```
uv run pytest tests/unit tests/agents
1114 passed in 30.51s
```

(The dispatch predicted 1115; 1114 is what this run actually reported. The
difference is recorded rather than reconciled.)

The `tests/integration` tier was not run: it needs a database, this change
needs none, and every test written here runs in the unit tier.

## Observed state after this pass

Same command, same tree, with the new file present:

```
uv run pytest tests/unit tests/agents
3 failed, 1115 passed in 34.50s
```

1114 pre-existing passes + 1 new pass + 3 new failures. **No pre-existing test
changed state.**

The same three fail and the same one passes when the file is run alone
(`uv run pytest tests/unit/test_startup_handler_report_holds_the_registry.py`
→ `3 failed, 1 passed`). That equivalence is deliberate and is the point of
the subprocess level — see *Level* below.

| Test | State on the unmodified tree | Failure state (per `testing`) |
| --- | --- | --- |
| `test_the_reporting_process_holds_the_deployments_own_registrations` | RED | 1 — ran, wrong value: reporting root holds `[]`, the other roots hold `["listing.subcategory_advisor"]` |
| `test_a_registered_handler_draws_no_fault_at_startup` | RED | 1 — ran, wrong value: a handler this deployment registers is reported unresolvable |
| `test_an_unregistered_handler_is_named_at_startup` | RED, on its third assertion only | 1 — ran, wrong value: the report names the registered-handler step too, so it answers identically for both |
| `test_the_faults_the_report_names_do_not_stop_the_deployment` | GREEN | n/a — green on both sides by design; regression protection for the advisory exit this change must preserve |

None of the three reds is state 2 (absent target): `commerce_ops.check_step_handlers`
exists and runs. Each executed its assertions and produced a wrong value.

## Level

Every test in the new file drives a **fresh interpreter** via `subprocess`,
following the pattern `tests/unit/test_registrations_across_processes.py`
establishes (`_handler_names`, `:263`).

This is the smallest unit that can observe the stated outcome, not a
preference. Each new scenario's **WHEN** says the process is "started the way
the deployment starts it", which is a claim about *where the registry came
from*. `HANDLERS` is a module global and several files under `tests/unit`
import `commerce_ops.registrations` at module scope, so pytest collection
alone populates it for the whole run. An in-process test would be red run
alone and green run in the full tree, whichever way `check_step_handlers.py`
went — a guard that cannot catch its own revert. Verified directly while
writing this pass: importing `commerce_ops.check_step_handlers` alone leaves
the registry empty; importing `commerce_ops.registrations` leaves it holding
`listing.subcategory_advisor`.

Only the playbook read and the database session are substituted inside the
driver script, so no database is needed. **The registry is never supplied** —
it is whatever importing the reporting module left behind.

## Scenario accounting

The MODIFIED requirement *A step carries the brief and the handler its
automation needs* carries **8** `#### Scenario:` blocks in the delta — the 4
already in the recorded spec, unaltered, plus 4 added. All 8 are accounted for
below; the count matches.

### Added by this change (4)

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | The reporting process holds the deployment's own registrations | `tests/unit/test_registrations_across_processes.py::test_the_reporting_process_holds_the_deployments_own_registrations` |
| 2 | A registered handler draws no fault at startup | `tests/unit/test_startup_handler_report_holds_the_registry.py::test_a_registered_handler_draws_no_fault_at_startup` |
| 3 | An unregistered handler is named at startup | `tests/unit/test_startup_handler_report_holds_the_registry.py::test_an_unregistered_handler_is_named_at_startup` |
| 4 | The faults the report names do not stop the deployment | `tests/unit/test_startup_handler_report_holds_the_registry.py::test_the_faults_the_report_names_do_not_stop_the_deployment` |

Scenario 4's second **THEN** clause — "every step whose handler is registered
is unaffected" — is carried by scenario 2's test and by the third assertion of
scenario 3's test, and is deliberately not re-asserted in scenario 4's own
test, which would make it red before the fix and so destroy the
green-on-both-sides regression guard tasks.md 2.3a asks for.

### Unaltered by this change, already covered (4)

The delta reproduces these verbatim; no sentence bearing on them changed. Each
is listed with the existing test that covers it, so the count is complete.
**None of these tests was touched.**

| # | Scenario | Covered by |
| --- | --- | --- |
| 5 | A draft automated step needs neither | `tests/unit/launch/domain/test_step_automation_brief_and_handler.py::test_a_draft_automated_step_needs_neither` |
| 6 | Leaving draft requires the brief | `tests/unit/launch/application/test_step_activation.py::test_leaving_draft_requires_the_brief`; `tests/unit/launch/domain/test_step_automation_brief_and_handler.py::test_an_automated_step_beyond_draft_without_a_brief_is_rejected` |
| 7 | A handler the code does not register cannot be activated | `tests/unit/launch/application/test_step_activation.py::test_a_handler_the_code_does_not_register_cannot_be_activated` |
| 8 | A human step carries no automation fields | `tests/unit/launch/domain/test_step_automation_brief_and_handler.py::test_a_human_step_carrying_an_automation_brief_is_rejected`; `tests/unit/launch/domain/test_step_automation_brief_and_handler.py::test_a_human_step_carrying_a_handler_is_rejected`; `tests/unit/launch/application/test_step_activation.py::test_a_human_step_written_with_automation_fields_is_refused` |

### Uncovered scenarios

**None.** Every scenario in the delta is covered by at least one named test.

## Assertion classification

### `test_the_reporting_process_holds_the_deployments_own_registrations`

- `reporting == declared` — **SPECIFIED**: "the registry it consults holds
  every handler this deployment answers for".
- `reporting == http and reporting == worker` — **SPECIFIED**: "holds the same
  handlers as every other process of this deployment that consults the
  registry".
- `registered_handler in reporting` — **DERIVED** guard. Two empty lists are
  equal, and an empty registry passing a non-emptiness check is precisely how
  this defect survived a test tier. Recorded as derived because no scenario
  states non-emptiness.

### `test_a_registered_handler_draws_no_fault_at_startup`

- `observed["faults"] == []` — **SPECIFIED**: "no fault is reported for that
  step". The step set holds exactly one step, so "no fault for that step" and
  "no fault at all" coincide here; this is why the set is a single step.
- Fixture precondition `registered_handler` (fails loudly where the deployment
  declares no handler at all) — **DERIVED** guard against a vacuous pass.

### `test_an_unregistered_handler_is_named_at_startup`

- the report names `price.buy-box-check` — **SPECIFIED** by the **THEN**.
- the report names `price.a_handler_no_deploy_answers_for` — **SPECIFIED** by
  the same **THEN** ("and the handler it could not resolve").
- the report does **not** name `listing.subcategory-suggested` — **SPECIFIED**,
  by the paragraph this delta adds: "A report produced against a registry
  holding none of them SHALL NOT satisfy this requirement: such a report
  answers identically for a deployment that registers a step's handler and one
  that does not". This is the assertion that is red today, and the one an
  implementer is most likely to read as optional. It is not.

### `test_the_faults_the_report_names_do_not_stop_the_deployment`

- exit status is `None` or `0` — **SPECIFIED**: "the deployment continues to
  start". The process runs inside a `&&` chain ahead of `exec uvicorn`
  (`Dockerfile:86`), so its own exit status is the observable.
- the report named at least one fault — **DERIVED** guard: without it, the test
  passes against a process that exits zero because it reported nothing, which
  is the state this whole change exists to end.

### Deliberately untested

- **That registration happens by importing `commerce_ops.registrations`.**
  design.md is explicit that the added text "deliberately does not say *how*
  registration happens". Whether that module reached `sys.modules` is recorded
  in the driver's dump and printed in failure messages as a diagnostic; nothing
  asserts on it. An implementation registering by some other means would pass.
- **The report's wording.** No scenario states it. Capturing the `ERROR` log
  lines was considered as the observation channel and rejected for that reason;
  the tests read what `report_unregistered_handlers` returned instead.
- **The import cost of the fix** (tasks.md 5.5, ~0.42s of job modules). A
  measurement to be recorded in the PR, not a stated behaviour, and a test
  asserting a wall-clock threshold in the commit-time tier would be flaky.
- **The `INFO`-suppression that makes this process silent in production**
  (`docs/deferred-work.md:224-232`). design.md names it a non-goal with its own
  change.
- **Whether an `active` `automated` step exists in any real database.** Not
  assertable of a live set (step status is runtime-editable), and out of the
  unit tier.

## Obsolete tests

**Search bound:** `tests/**/test_*.py` only, by `grep` for
`check_step_handlers`, `report_unregistered_handlers`, `reported at startup`
and `startup report`. No earlier `test-manifest.md` was supplied to this pass,
so no scenario-to-test mapping from a previous change was available. This pass
has not read any implementation of the behaviour under test and holds no
requirement-to-test index, so the search is bounded as stated and nothing
outside it was examined.

**Comparison of the recorded requirement with the delta:** the delta adds two
normative paragraphs and four scenarios and **alters or removes no existing
sentence or scenario**. No behaviour is superseded, so no test asserts
superseded behaviour.

Four bearing tests were found and examined. **None is obsolete**, and no entry
below authorises a deletion:

| Test | Verdict | Evidence |
| --- | --- | --- |
| `tests/unit/launch/application/test_step_activation.py::test_a_deploy_dropping_an_active_steps_handler_is_reported_at_startup` | **Not obsolete.** Keep. | Cites the startup clause, but calls the report with `handlers=_registry(REGISTERED_HANDLER)` — a supplied registry. It covers the filtering rule (only `active` `automated` steps are named), which the delta leaves untouched. The delta constrains where the registry comes from, which this test does not speak to. |
| `tests/unit/test_check_step_handlers_reads_the_authored_set.py::test_the_startup_check_reports_while_the_playbook_is_not_ready` | **Not obsolete.** Keep. | Substitutes `report_unregistered_handlers` entirely and asserts only that it ran. Nothing it asserts is superseded; the delta adds a constraint it is silent on. |
| `tests/unit/test_seed_playbook.py:221-222` (start-chain ordering) | **Not obsolete.** Keep. | Asserts `seed_playbook < check_step_handlers < uvicorn`. The proposal states the `Dockerfile` is untouched, so this must stay green through the change. |
| `tests/unit/test_registrations_across_processes.py::test_both_composition_roots_resolve_the_same_handler_names` | **Assertions not obsolete. Its docstring is — candidate for human confirmation.** | Its docstring (`:303-304`) reasons that "A handler imported into only one leaves `check_step_handlers` reporting it registered". That claim is false in both directions and this change does not make it true: today the report answers the same regardless of what any root imports, and after the change a handler absent from `registrations.py` is reported *un*registered. Superseding text: the delta's new paragraph, "That startup report SHALL be produced by a process in which every handler this deployment answers for is registered." **This is a documentation correction to a docstring, not a reason to weaken, rewrite or delete any assertion in that test — every assertion in it stays exactly as it is.** tasks.md 4.1 already schedules this correction. This pass did not make it: the additive-only rule forbids editing an existing test file. |

## Unresolved project questions

No channel exists to ask on from a dispatched subagent, so each is recorded
with the assumption taken and the tests that depend on it.

1. **Where does a process-level test that spawns interpreters belong among the
   three tiers?** `AGENTS.md` describes `tests/unit/<module>/<layer>/`, but
   this file's subject is a composition root, which belongs to no module and
   no layer.
   *Assumption:* the `tests/unit/` root directory, matching the three files
   already there that do exactly this — `test_registrations_across_processes.py`,
   `test_startup_without_configuration.py`, `test_check_step_handlers_reads_the_authored_set.py`.
   *Tests depending on it:* all four, by location only. Moving the file changes
   nothing about what they assert.

2. **tasks.md 1.3 asks for the coverage of scenario 1 to be added *to*
   `tests/unit/test_registrations_across_processes.py`.** This pass is
   additive-only and never edits an existing test file.
   *Assumption:* scenario 1's coverage lives in the new file instead, written
   to the same pattern and reaching the same verdict. Relocating it into that
   file is a legitimate choice for whoever implements — it would be their edit,
   made with the whole file in view, not one this pass may make.
   *Tests depending on it:*
   `test_the_reporting_process_holds_the_deployments_own_registrations`.

3. **No convention is recorded for how a test may pass data into a subprocess
   it drives.** The existing files format values into the script source.
   *Assumption:* an environment variable, `COMMERCE_OPS_TEST_STEP_SET`, chosen
   because the step set is JSON and formatting braces into a script template is
   error-prone. It is deliberately not an application variable — nothing in
   `shared/application/settings.py` declares it and nothing in `src/` reads it,
   so `AGENTS.md`'s four-place runtime-variable obligation does not apply and
   `tests/unit/shared/application/test_settings.py` (which scans no files) is
   unaffected. Verified: that file's declared-set comparison still passes.
   *Tests depending on it:* scenarios 2, 3 and 4.

4. **Runtime cost in the commit-time tier.** The new file spawns 7 interpreters
   and takes ~4s locally; the full `tests/unit`+`tests/agents` run went from
   30.5s to 34.5s. No convention records a budget for the pre-commit tier.
   *Assumption:* acceptable, since `test_registrations_across_processes.py`
   already pays the same kind of cost for the same kind of property.
   *Tests depending on it:* all four.

## What the implementation must make pass

```
uv run pytest tests/unit/test_startup_handler_report_holds_the_registry.py
```

specifically these three, which are red today:

```
tests/unit/test_registrations_across_processes.py::test_the_reporting_process_holds_the_deployments_own_registrations
tests/unit/test_startup_handler_report_holds_the_registry.py::test_a_registered_handler_draws_no_fault_at_startup
tests/unit/test_startup_handler_report_holds_the_registry.py::test_an_unregistered_handler_is_named_at_startup
```

and this one, which is green today and must stay green:

```
tests/unit/test_startup_handler_report_holds_the_registry.py::test_the_faults_the_report_names_do_not_stop_the_deployment
```

together with the whole of `uv run pytest tests/unit tests/agents`, which was
green at 1114 before this pass and must be green at 1118 after the change.

Note for the implementer: the reds are read **by import alone**. A
`register_all()` deferred into a function that `check_step_handlers.main()`
calls later would satisfy scenarios 2, 3 and 4 and still fail scenario 1,
which dumps each root's registry after importing it and nothing else. tasks.md
3.1 and design.md Decision 1 say the import must sit at module scope; scenario
1's test is what enforces it.

## Verification run on the new file

- `uv run ruff check` — passed
- `uv run ruff format --check` — passed (`1 file already formatted`)
- `uv run mypy` — passed (`Success: no issues found in 1 source file`)
