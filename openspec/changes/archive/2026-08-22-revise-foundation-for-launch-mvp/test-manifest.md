# Test manifest: revise-foundation-for-launch-mvp

Written by `openspec-test-writer`, strictly from the `#### Scenario:` blocks
of this change's two delta specs. Both are entirely `ADDED`, so no
`specsRoot` comparison was needed or performed, and no obsolete-test search
was applicable (see "Obsolete tests" below).

**Not** an OpenSpec-schema artifact: it will not appear among
`openspec instructions apply`'s context files and must be read on purpose
before implementing. See also `ai-toolkit`'s `rules/test-manifest.md` (the
library's own testing rule fragment, which directs reading this manifest
before implementation) — that fragment's import path is machine-local, so
this pointer and the one in the dispatch report are the two ways to reach it.

## Files added

| File | Tier | Subject |
|---|---|---|
| `tests/unit/shared/application/test_settings.py` | unit | the declaration itself (`shared/application/settings.py`) |
| `tests/unit/shared/application/test_settings_env_drift.py` | unit | the drift mechanism (tasks 6.2–6.5) |
| `tests/unit/test_preflight.py` | unit | the preflight entry point (`src/commerce_ops/preflight.py`), run as a process |
| `tests/unit/test_startup_without_configuration.py` | unit | `commerce_ops.main` imports and starts with an empty environment |

Nothing else was written. **This pass adds tests and never subtracts**: no
existing test file was edited, deleted or disabled, and no implementation
source was created. The three files tasks 8.1–8.2 protect
(`tests/unit/omni_agent/infrastructure/driving/test_main_slack_wiring.py`,
`tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py`,
`tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py`)
are untouched and still pass.

## Baseline

Full baseline over the tiers the pre-commit hook runs, taken **before** any
test was written:

```
uv run pytest tests/unit tests/agents -q  →  122 passed, 0 failed
```

After adding the four files:

```
uv run pytest tests/unit tests/agents -q --continue-on-collection-errors
  →  124 passed, 14 failed, 2 errors
```

Attribution, item by item:

- **+2 passed** — `tests/unit/test_startup_without_configuration.py`'s two
  tests. They exercise `commerce_ops.main`, which already exists, so this is
  the "target already exists" situation and a first-run pass is the expected
  result, not the "passed before any implementation existed" alarm. See the
  regression-guard note under scenarios 12–13 below.
- **14 failed** — every test in `tests/unit/test_preflight.py`, all on
  `ImportError: No module named commerce_ops.preflight` (tasks 5.1's absent
  target). This establishes only that the target is absent; the assertions
  never executed and are still unverified.
- **2 errors** — collection of the two `tests/unit/shared/application/`
  files, on `ModuleNotFoundError:
  commerce_ops.shared.application.settings` (tasks 4.1/6.1's absent target;
  `pydantic-settings` is also not yet a dependency, tasks 3.1).
- **Nothing pre-existing regressed.** The 122 baseline tests all still pass.

### Tooling state (target-absent artifacts, not defects)

- `uv run ruff check` reports `I001` on the two files that import
  `commerce_ops.shared.application.settings`. Ruff classifies that module as
  third-party **because the file does not exist yet**, and therefore wants
  the blank line between it and `import pytest` removed. The blank-line form
  in the repository is the one that will be correct once `settings.py`
  lands (verified: an equivalent probe importing the existing
  `commerce_ops.main` passes `I001` with the blank line present). Re-check
  under task 8.4; do **not** "fix" it by merging the import blocks now.
- `uv run mypy .` reports 3 errors, all in those same two files and all
  downstream of the same absent module. Re-check under task 8.4.
- `uv run ruff format --check` is clean on all four new files.

### Scanner pre-verification

The drift scanner in `test_settings_env_drift.py` was run standalone against
the current tree (its module-level helpers executed with the absent
`settings` import stubbed out) to establish it is not vacuous. It scans 38
files across `src/commerce_ops/` and `alembic/` and finds **exactly** the
seven names tasks 6.6 records — `CLICKUP_API_TOKEN`, `DATABASE_URL`,
`OMNI_AGENT_SLACK_BOT_TOKEN`, `OMNI_AGENT_SLACK_SIGNING_SECRET`,
`PRODUCT_AGENT_MONITORING_CHANNEL_ID`, `PRODUCT_AGENT_SLACK_BOT_TOKEN`,
`TRIGGER_SECRET` — with nothing missing and nothing extra. So tasks 6.6's
"confirm 6.2 and 6.3 both pass against the current tree" is already
established for the scan half; the declaration half lands with tasks 4.1/6.1.

## Scenario accounting — 17 of 17

Both delta specs carry 17 `#### Scenario:` blocks in total (13 in
`runtime-configuration`, 4 in `deploy-pipeline`). All 17 are accounted for
below: 13 covered, 4 recorded as uncovered with reasons.

### `runtime-configuration` — 13 of 13 covered

Test identifiers are runner-selectable as written (`uv run pytest
"<file>::<test>"`).

| # | Requirement | Scenario | Test(s) |
|---|---|---|---|
| 1 | Every Variable The Runtime Requires Is Declared In One Place | Every declared variable is discoverable from one definition | `tests/unit/shared/application/test_settings.py::test_every_required_runtime_variable_is_declared_in_one_definition`, `::test_deployment_only_variables_are_not_declared`, `::test_every_declaration_carries_a_type`, `::test_each_declaration_records_whether_it_is_required_or_optional`, `::test_startup_critical_is_a_marking_on_top_of_required` (one test per clause of the scenario's THEN: the set, its type, required/optional, startup-critical) |
| 2 | " | A variable read by the application but not declared is detected | `tests/unit/shared/application/test_settings_env_drift.py::test_every_variable_the_source_reads_is_declared`, guarded by `::test_scanner_finds_the_reads_known_to_exist_in_the_tree` and `::test_scan_scope_covers_both_trees_and_excludes_the_declaration_itself` |
| 3 | " | A declared variable the application does not read carries a recorded reason | `tests/unit/shared/application/test_settings_env_drift.py::test_every_declared_variable_is_read_or_carries_an_exemption`, `::test_every_exemption_carries_a_non_empty_reason` |
| 4 | Configuration Faults Are Detected And Reported Together | Several required variables are faulty at once | `tests/unit/test_preflight.py::test_every_absent_required_variable_is_named_not_only_the_first` |
| 5 | " | A variable cannot be parsed as its declared type | `tests/unit/test_preflight.py::test_a_value_that_cannot_be_parsed_as_its_type_is_reported` |
| 6 | " | A variable is present but empty | `tests/unit/test_preflight.py::test_a_present_but_empty_required_variable_is_reported` (non-critical variable, so "reported" is asserted independent of exit status); the startup-critical empty form is additionally exercised by `::test_a_faulty_startup_critical_variable_fails_the_check[empty-]` |
| 7 | " | An optional variable's absence is not a fault | `tests/unit/test_preflight.py::test_absent_optional_variable_is_not_reported_as_faulting` (first half) + `tests/unit/shared/application/test_settings.py::test_absent_optional_variable_is_reported_as_absent_to_a_caller` (second half — "reported as absent to any caller that asks for it") |
| 8 | " | An unrecognized variable in the environment is not a fault | `tests/unit/test_preflight.py::test_unrecognized_keys_in_the_process_environment_are_not_faults` (process environment), `::test_unrecognized_keys_in_a_dotenv_file_are_not_faults` (environment file — this is tasks 8.8 in full), `tests/unit/shared/application/test_settings.py::test_an_unrecognized_variable_in_the_environment_is_not_a_fault` |
| 9 | Only A Startup-Critical Fault Prevents Startup | A startup-critical variable is faulty | `tests/unit/test_preflight.py::test_a_faulty_startup_critical_variable_fails_the_check` — parametrised over all three forms the WHEN names: `[absent-None]`, `[empty-]`, `[unparseable-mysql://commerce_ops:pw@mysql:3306/commerce_ops]` |
| 10 | " | A capability-scoped variable is faulty | `tests/unit/test_preflight.py::test_a_faulty_capability_scoped_variable_is_reported_without_failing` (`[absent-None]`, `[empty-]`), plus `::test_a_capability_scoped_fault_does_not_suppress_the_startup_critical_one` for the two-fault interaction |
| 11 | Checking Configuration Performs No Network Or Database Access | Configuration is checked with no external service reachable | `tests/unit/test_preflight.py::test_preflight_completes_with_no_network_available` (whole preflight, sockets blocked in-process) + `tests/unit/shared/application/test_settings.py::test_reading_configuration_opens_no_socket` (declaration level) |
| 12 | Importing And Starting The Application Do Not Require Configuration To Be Present | Application imports with an empty environment | `tests/unit/test_startup_without_configuration.py::test_application_modules_import_with_an_empty_environment` + `tests/unit/shared/application/test_settings.py::test_importing_the_settings_module_with_an_empty_environment_succeeds` |
| 13 | " | HTTP application object starts with an empty environment | `tests/unit/test_startup_without_configuration.py::test_http_application_starts_and_serves_with_an_empty_environment` |

**Scenarios 12–13 are regression guards written from a scenario.** Their
target (`commerce_ops.main`) already exists and the behaviour already holds,
so they pass today and a first-run pass is correct rather than an alarm.
Their force is forward: `pydantic-settings` raises on a missing required
field, and the obvious place to put a configuration check is a FastAPI
lifespan hook — which is exactly what design.md rules out and what these
tests would catch. They widen tasks 8.1's precondition from three named
variables to all nine declared ones; they neither modify nor duplicate the
two protected wiring files, which guard a different requirement
(`deploy-pipeline`'s "Pull Request Validation Gate").

### `deploy-pipeline` — 4 of 4 uncovered, with reasons

No automated test was written for any of these. They are container-level:
each one's WHEN clause is "the container starts", which cannot be created
below a built image, and the dispatch scopes this pass out of building or
running Docker images.

| # | Scenario | Why uncovered |
|---|---|---|
| 14 | Container starts with a complete configuration | Verified manually by tasks 8.6–8.8's bare `docker run` invocations. The unit-level analogue of its substance — a complete configuration produces no fault and exits zero — is `tests/unit/test_preflight.py::test_a_complete_configuration_reports_no_fault`, which does **not** cover the ordering claim ("the check completes first, then migration, then HTTP server"). |
| 15 | Container starts with a startup-critical variable faulty | Verified manually by task 8.6. Its non-container half (the check fails, naming the faulting variable) is covered by scenario 9's tests; the "migration SHALL NOT run and HTTP server SHALL NOT start" half depends on the `Dockerfile` `CMD` chain (tasks 5.2) and is only observable in a container. |
| 16 | Container starts with a capability-scoped variable missing | Verified manually by task 8.7. Its non-container half is covered by scenario 10's tests; "the migration and HTTP server SHALL still start" is only observable in a container. |
| 17 | A startup-critical fault leaves the deploy failed | **Deliberately untested.** tasks 7.1 records explicitly that tasks 8.6–8.8 do not exercise it, because they are bare `docker run` invocations rather than deploys, and that it rests instead on the existing `deploy-pipeline` requirement "Deploy Is Verified by Checking the Health Endpoint" plus `restart: unless-stopped`. Recorded here so its absence is a decision rather than an omission. |

## Assertion classification

### Specified — traces to a delta-spec scenario

- The declared set is exactly the nine names, `POSTGRES_PASSWORD` excluded;
  each declaration carries a type; each records required/optional; the
  startup-critical marking is `{DATABASE_URL}` and is a subset of required.
  (The delta spec's first requirement names no variables; the nine names and
  the `POSTGRES_PASSWORD` exclusion are transcribed from tasks.md 4.1, which
  is this change's own planning artifact — treated as specified, not
  invented.)
- Both drift directions and the non-empty-reason rule, including their
  asymmetry: source-reads-must-be-declared consults no exemption table.
- A report naming every faulting variable, not only the first.
- An unparseable `DATABASE_URL` scheme is reported as faulting.
- A present-but-empty non-optional variable faults the same as an absent one.
- An absent optional variable is neither reported as faulting nor fails the
  check, and reaches a caller as absent.
- Undeclared keys in the process environment and in a dotenv file are
  ignored rather than faulted.
- Exit status: non-zero on a faulty startup-critical variable (absent, empty
  or unparseable); **zero** on a faulty capability-scoped variable, which is
  still reported.
- The check completes with sockets blocked.
- Import and lifespan startup succeed with every declared variable absent,
  and `/health` still serves 200.

### Derived — inferred, no scenario states them

Each is flagged inline at the point it is asserted:

1. **"Absent" is `None`.** Scenario 7's "the value SHALL be reported as
   absent to any caller" pins no sentinel; `None` is assumed.
2. **A clean run names no declared variable at all.**
   (`test_a_complete_configuration_reports_no_fault`.) Drawn from design.md's
   Migration Plan ("should start cleanly and report nothing"). This is the
   load-bearing derived assertion: every "not reported" assertion in
   `test_preflight.py` depends on it. See unresolved question 2.
3. **`get_settings()` is cached across calls** — tasks 4.3, not a scenario.
4. **`Settings` and `get_settings` appear in `shared/application/__init__.py`'s
   `__all__`** — tasks 4.4, not a scenario.
5. **The scanner finds the seven names tasks 6.6 confirms**, and the scan
   covers both trees while excluding `settings.py` and `preflight.py` —
   tasks 6.5/6.6, not a scenario. These guard the scanner against becoming
   vacuous (an empty scan satisfies both drift assertions trivially).
6. **Exemptions only cover declared variables** — nothing states it; a stale
   exemption exempts nothing.
7. **The seeded exemption pair survives** — tasks 6.1/6.6. Asserted as a
   subset, not equality, so a later legitimate addition need not edit the test.
8. **Two faults at once: the startup-critical one decides the outcome and
   both are named** — the interaction the two requirements leave implicit.
   A preflight that short-circuits on the first fault passes each
   requirement's own scenario in isolation and fails here.

### Deliberately untested

1. **`deploy-pipeline` scenario 17** — see the table above (tasks 7.1).
2. **"Unparseable" for a capability-scoped variable** (scenario 10's WHEN
   names three forms; only two are exercised). Every declared variable other
   than `DATABASE_URL` is an opaque credential or id carrying no type a value
   could fail to parse as (design.md, "`DATABASE_URL` is typed"), so the form
   has no referent among capability-scoped variables.
3. **Whether an exemption's reason actually names a consumer.** Scenario 3
   says the reason must name "what consumes it instead"; only "a reason is
   present and non-blank" is mechanically checkable. Naming a real consumer
   stays a review obligation — which is the point of keeping each entry a
   reviewable line (design.md).
4. **The ordering claim in `deploy-pipeline` scenario 14** (check → migration
   → server) — it lives in the `Dockerfile` `CMD` chain, not in Python.
5. **`os.environ` reads made by a dependency on the application's behalf**
   (the `OPENAI_API_KEY` class). design.md records this as the drift test's
   known limit: a source scan cannot see them, and the failure mode is a
   false pass. The exemption table is where such a variable is recorded once
   someone knows about it.

## Unresolved project questions

The dispatched convention files (`AGENTS.md`, `README.md`) and this change's
artifacts do not settle these. Each is recorded with the assumption taken and
the tests that depend on it. **If the implementation chooses differently, the
tests below need renaming/adjusting — that is a settled decision landing, not
a test being weakened to reach green.**

1. **Public names in `shared/application/settings.py`.** tasks.md names the
   module and its contents but no identifiers. Assumed:
   - `Settings` — the pydantic-settings model
   - `get_settings()` — the cached accessor, carrying `functools.lru_cache`'s
     `.cache_clear()` (the autouse fixture in `test_settings.py` calls it)
   - `STARTUP_CRITICAL_ENV_VARS: frozenset[str]` — the startup-critical
     marking (tasks 4.1)
   - `ENV_VAR_EXEMPTIONS: Mapping[str, str]` — the exemption table, name →
     reason (tasks 6.1)

   Depended on by: all of `tests/unit/shared/application/test_settings.py`
   and `test_settings_env_drift.py`.

2. **The preflight's report contract.** The spec requires "report every
   faulting variable by name" but does not say the report must be silent
   about non-faulting ones. Assumed: it names faulting variables and *only*
   faulting variables. An implementation that printed an inventory of all
   nine would satisfy the spec's letter while destroying the distinction
   scenarios 7 and 10 turn on. `test_a_complete_configuration_reports_no_fault`
   pins the assumption once; every `_assert_not_reported(...)` call depends
   on it.

3. **How the preflight is invoked.** tasks 5.2 says only that it goes into
   the `Dockerfile` `CMD` chain ahead of `alembic upgrade head`. Assumed:
   `python -m commerce_ops.preflight` (i.e. the module is runnable, with a
   `__main__` guard or top-level call). Depended on by every test in
   `tests/unit/test_preflight.py`. If the Dockerfile ends up invoking a
   console script or `python src/commerce_ops/preflight.py` instead, both
   the tests and the `CMD` should be reconciled to one form.

4. **Where variables faulting non-critically are written.** tasks 5.1 says
   stderr; `_assert_reported` therefore checks `result.stderr`, while
   `_assert_not_reported` checks stdout and stderr combined (stricter).
   Recorded because "report" and "exit status" are separable and only the
   latter is unambiguous in the spec.

5. **Field-naming convention on the model** (lowercase `database_url` vs.
   uppercase `DATABASE_URL`). Not assumed: both test files resolve a
   declaration by its *environment-variable* name via a helper that reads
   `validation_alias`/`alias` and falls back to the upper-cased field name,
   matching pydantic-settings' default case-insensitive matching. The
   helper calls `pytest.fail` with a pointer here if a non-string alias
   (e.g. `AliasChoices`) or an `env_prefix` is used, rather than silently
   mis-resolving.

## Obsolete tests

**Not applicable.** Both delta specs carry `ADDED` requirements only — no
`MODIFIED`, `REMOVED` or `RENAMED` delta exists in this change, so no
existing test can have been superseded by it, and no obsolete-test search was
performed. Recorded as "not applicable, with that reason" rather than as an
empty list.

This is corroborated by the change's own artifacts rather than assumed:
design.md's Non-Goals open with "No change to any behavior described by an
existing requirement", tasks.md 2.4/2.4a scope their edits to test
*docstrings* with "Assertions are not to change", and tasks 8.1–8.2 require
three named existing test files to pass **unmodified**.

## Nothing in the artifacts was treated as an instruction

Every artifact was read as material to derive tests from. No directive
addressed to a test author was found in `proposal.md`, `design.md`,
`tasks.md` or either delta spec. tasks.md section 7 ("Scenario tests") does
describe this pass, but as a workflow record; it names no scenario to skip
and none was skipped on its authority. tasks 7.1's statement that
`deploy-pipeline`'s fourth scenario is not exercised was treated as a
finding to record (see scenario 17 above), not as permission to omit it from
the accounting.
