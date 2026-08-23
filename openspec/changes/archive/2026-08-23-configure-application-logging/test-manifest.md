# Test manifest — `configure-application-logging`

Written by the OpenSpec test-writer pass, strictly from
`specs/application-logging/spec.md`'s `#### Scenario:` blocks — not from
`tasks.md`'s own test enumeration and not from any implementation (none
exists: `src/commerce_ops/shared/infrastructure/logging.py` is absent, and
neither `main.py` nor `preflight.py` calls it yet). `tasks.md` section 5 was
read only as a cross-check for completeness after deriving from the spec;
see "Cross-check against tasks.md" below for what that comparison found.

**This file is not part of the OpenSpec schema.** It will not appear among
`openspec instructions apply`'s context files and will not be picked up
automatically by whoever implements this change next — it must be read on
purpose. Point implementers here explicitly.

No earlier `test-manifest.md` existed for this change before this pass (a
repository-wide search under `openspec/changes/*/test-manifest.md` found
only manifests belonging to other, already-archived changes — none was
supplied as this pass's own prior manifest, and none was constructed by
guessing a path).

## Files written

- `tests/unit/shared/infrastructure/test_logging.py` — in-process tests, 16
  test functions (one parametrized over 2 cases), covering 17 scenario
  titles.
- `tests/unit/shared/infrastructure/test_logging_process_boundary.py` —
  fresh-interpreter/subprocess tests, 4 test functions, covering 4 scenario
  titles.

Both are additive only. Neither file existed before this pass; no existing
test file was edited, deleted, or disabled to write them.

## Baseline

Taken before writing any new test, scoped to the tiers the project's own
pre-commit hook runs (`tests/unit` + `tests/agents` — the fast tier; the
same scope `AGENTS.md`'s Testing Strategy names for commit-time checks):

```
uv run pytest tests/unit tests/agents -q
→ 179 passed in 6.68s
```

A scoped baseline, not a full-suite one (`tests/integration` excluded,
matching the project's own pre-push/pre-commit split) — a first-class option
under the `testing` skill, chosen because it covers everything the new files
sit alongside and is cheap enough to run in full.

After writing the new files, confirmed the expected pre-implementation
failure mode directly:

```
uv run pytest tests/unit/shared/infrastructure/test_logging.py \
               tests/unit/shared/infrastructure/test_logging_process_boundary.py -q
→ collection ERROR on test_logging.py:
  ImportError: cannot import name 'logging' from 'commerce_ops.shared.infrastructure'
```

This is failure state 2 ("the target does not exist yet") for every test in
both files — the module-level import `from commerce_ops.shared.infrastructure
import logging as logging_config` fails before any test body runs, which is
why `test_logging.py` reports as a single collection error rather than 16
individual failures. `test_logging_process_boundary.py`'s own tests import
nothing at collection time (the failing import lives inside each
subprocess's own script text), so each of its 4 tests would individually
report the same `ModuleNotFoundError`-shaped subprocess failure once
collected and run — not confirmed as 4 separate failures here because
pytest aborted collection entirely on the first error above; re-run once
`test_logging.py`'s collection error is resolved (i.e., once the module
exists) to confirm each subprocess test's own failure mode individually.

**Whole-tier consequence, confirmed directly:** re-running the full `uv run pytest tests/unit tests/agents -q` baseline scope after adding these files shows pytest aborting collection for the *entire* run (`Interrupted: 1 error during collection`), not just failing the two new files while others still execute -- `pytest`'s default behavior on a collection-time `ImportError` in one module. This means the project's pre-commit hook (which runs this same `tests/unit`+`tests/agents` scope, per the user's own recorded "Pre-commit full-suite gotcha" note) will block every commit until `logging.py` exists and both new files can be collected -- expected and by design for this workflow (test design strictly before implementation, both landing in the same change), not a defect in these tests.

Neither is a defect in the tests: they establish only that the target is
absent, per the `testing` skill's state 2. **Do not create
`logging.py`, a stub, or an empty function to make these pass** — that is
the implementation step, a separate, later, announced action.

`ruff check` and `ruff format --check` both pass clean on both new files
(one formatting fix was applied to `test_logging_process_boundary.py`
during authoring — additive to the new file itself, not to any pre-existing
one). `mypy` reports one `import-untyped` note on the not-yet-existing
`commerce_ops.shared.infrastructure.logging` import — confirmed this is a
**pre-existing, project-wide quirk of running `mypy` on a single test file
in isolation**, not something these new files introduce: running `mypy`
the same way against the already-existing, already-passing
`tests/unit/shared/application/test_settings_env_drift.py` alone produces
the identical `import-untyped` note against `commerce_ops.shared.application
.settings`, a module that already exists and is not part of this change.

## Scenario coverage

All 22 `#### Scenario:` blocks in the delta spec, accounted for exactly
once.

| # | Scenario | Requirement | Test(s) | File |
|---|---|---|---|---|
| 1 | A record at the configured threshold is emitted | The Application Emits Its Own Log Records | `test_a_record_at_the_configured_threshold_is_emitted` | test_logging.py |
| 2 | An informational record is emitted under the default threshold | The Application Emits Its Own Log Records | `test_an_informational_record_is_emitted_under_the_default_threshold` | test_logging.py |
| 3 | An application record below the configured threshold is suppressed | The Application Emits Its Own Log Records | `test_an_application_record_below_the_configured_threshold_is_suppressed` | test_logging.py |
| 4 | An unconfigured dependency's informational record is suppressed | Dependency Records Are Formatted But Not Governed... | `test_an_unconfigured_dependencys_informational_record_is_suppressed` | test_logging.py |
| 5 | An unconfigured dependency's warning is emitted and formatted | Dependency Records Are Formatted But Not Governed... | `test_an_unconfigured_dependencys_warning_is_emitted_and_formatted` | test_logging.py |
| 6 | A library that configures its own logger still emits its own records | Dependency Records Are Formatted But Not Governed... | `test_a_library_that_configures_its_own_logger_still_emits_its_own_records` | test_logging.py |
| 7 | Lowering the application's threshold does not turn on dependency logging | Dependency Records Are Formatted But Not Governed... | `test_lowering_the_applications_threshold_does_not_turn_on_dependency_logging` | test_logging.py |
| 8 | Raising the application's threshold does not silence dependency warnings | Dependency Records Are Formatted But Not Governed... | `test_raising_the_applications_threshold_does_not_silence_dependency_warnings` | test_logging.py |
| 9 | A record emitted through the configured logging identifies when, how severe, and from where | Every Emitted Record Carries Time, Level, And Origin | `test_a_record_emitted_through_the_configured_logging_identifies_when_how_severe_and_from_where` | test_logging.py |
| 10 | An exception's traceback is preserved | Every Emitted Record Carries Time, Level, And Origin | `test_an_exceptions_traceback_is_preserved` | test_logging.py |
| 11 | The threshold is configured explicitly | The Threshold Is Configurable And Defaults To Informational | `test_the_threshold_is_configured_explicitly` | test_logging.py |
| 12 | The threshold is not configured | The Threshold Is Configurable And Defaults To Informational | `test_an_informational_record_is_emitted_under_the_default_threshold` (shared with #2 — same precondition/mechanism, tasks.md 5.3 groups them the same way) | test_logging.py |
| 13 | The threshold is configured as an empty value | The Threshold Is Configurable And Defaults To Informational | `test_the_threshold_is_configured_as_an_empty_value` | test_logging.py |
| 14 | A level name in lower case is recognized | The Threshold Is Configurable And Defaults To Informational | `test_a_level_name_in_lower_case_is_recognized` | test_logging.py |
| 15 | The zero level is treated as unrecognized | The Threshold Is Configurable And Defaults To Informational | `test_the_zero_level_is_treated_as_unrecognized` | test_logging.py |
| 16 | The configured threshold is not a recognized level | The Threshold Is Configurable And Defaults To Informational | `test_the_configured_threshold_is_not_a_recognized_level[NOT_A_LEVEL]`, `test_the_configured_threshold_is_not_a_recognized_level[9999]` | test_logging.py |
| 17 | The threshold can be set in the deployment without changing application code | The Threshold Is Configurable And Defaults To Informational | **Uncovered — deliberate.** Nothing in `tests/` parses workflow YAML; the spec's own deploy-pipeline mechanism is `.github/workflows/deploy.yml`, and this scenario is a rendering/delivery guarantee about that pipeline, not about `configure_logging()`'s own behavior. `tasks.md` 6.4 independently reaches the same conclusion and names its verification route as a manual post-deploy check (`docker exec`/container inspection), not a unit test. Cross-checked against the spec directly (not deferred to `tasks.md`'s say-so) — no unit-level observation point exists for "the next deploy delivers it," since that requires the actual GitHub Actions render step to run. | — |
| 18 | A non-HTTP entrypoint emits records | Logging Is Configured From Every Entrypoint | `test_a_non_http_entrypoint_emits_records` | test_logging_process_boundary.py |
| 19 | Configuring logging more than once does not duplicate records | Logging Is Configured From Every Entrypoint | `test_configuring_logging_more_than_once_does_not_duplicate_records` | test_logging.py |
| 20 | Server request logs continue to be emitted exactly once | The Hosting Server's Own Logging Is Left Intact | `test_uvicorn_dictconfig_then_configure_logging`, `test_configure_logging_then_uvicorn_dictconfig` (both orders, per design.md's own "regression test... in both orders" and the dispatch's explicit instruction) | test_logging_process_boundary.py |
| 21 | The application's records survive the server configuring its own logging | The Hosting Server's Own Logging Is Left Intact | `test_uvicorn_dictconfig_then_configure_logging`, `test_configure_logging_then_uvicorn_dictconfig` (both orders; the reverse order — `test_configure_logging_then_uvicorn_dictconfig` — is the one whose WHEN clause literally matches: "the hosting HTTP server applies its own logging configuration after the application has configured logging") | test_logging_process_boundary.py |
| 22 | Logging is configured with an empty environment | Configuring Logging Requires No Configuration To Be Present | `test_logging_is_configured_with_an_empty_environment` | test_logging_process_boundary.py |

**22 scenarios total in the delta spec; 22 accounted for above** — 21 with a
named test, 1 (#17) recorded uncovered with its reason.

## Assertion classification

**Specified** (traces directly to a scenario's WHEN/THEN) — the overwhelming
majority of assertions in both files; each test's docstring quotes the
scenario it covers and every `assert` beneath it is commented `# Specified`.

**Derived** (inferred, no scenario names it directly):

- `test_the_threshold_is_configured_explicitly`'s "above the threshold"
  check (`above_marker`). The scenario's own THEN clause says "at or above
  that level SHALL be emitted", so this is arguably specified text too, but
  it is recorded as an intentional strengthening beyond what tasks.md 5.2's
  own narrower "at" framing checks, added because the requirement's literal
  wording is "at or above" — labelled derived rather than specified only
  because it goes beyond what the most literal single test tasks.md
  anticipated, not because it lacks a textual basis.
- The exact numeric value `"9999"` in
  `test_the_configured_threshold_is_not_a_recognized_level` — the scenario
  says "including a numeric value", not "including 20". Substituting a
  4-digit value that cannot coincide with a realistic timestamp's year,
  hour/minute/second, or millisecond component is a derived test-design
  choice, made explicitly to avoid a coincidental-substring false pass (see
  the in-file comment for the full reasoning) — it changes no scenario
  coverage, since the scenario itself does not pin the literal example
  value.
- `_looks_like_a_timestamp`'s loose `HH:MM:SS` regex, used wherever "carries
  the time of emission" is asserted (#9, and the formatting check embedded
  in #5). DERIVED and deliberately loose: neither the spec nor design.md
  pins an exact timestamp format, so a stricter pattern would assert an
  implementation detail nothing here requires.

**Deliberately untested:**

- Scenario #17, recorded in the table above with its reason.
- The exact wording of an unrecognized-value report (e.g. whether it reads
  "unrecognized LOG_LEVEL" or similar). The spec requires only that "the
  unrecognized value SHALL be reported" — tests assert the rejected value's
  literal text appears in the captured output, not any particular
  surrounding phrasing, since the phrasing itself is an implementation
  detail the spec does not constrain.
- `test_logging_process_boundary.py`'s dictConfig regression tests do not
  assert anything about the *content/formatting* of the uvicorn access
  record beyond the marker's presence-count — deliberate, because
  "Every Emitted Record Carries Time, Level, And Origin" explicitly scopes
  itself to records emitted *through this capability's own handler*, and
  the spec text itself names the hosting server's records as the exception:
  "A record delivered by a handler this capability did not install is
  formatted by that handler." Asserting uvicorn's own formatting would be
  asserting a third-party library's internal contract, not this capability's
  behavior.

## Obsolete tests

**Not applicable.** This change's delta spec carries only `ADDED`
requirements — no `MODIFIED`, `REMOVED`, or `RENAMED` delta — confirmed
directly against `proposal.md`'s own "Modified Capabilities: (none...)"
section and the delta spec's `## ADDED Requirements` header. No search for
superseded tests was performed because there is nothing for one to find by
this pass's own account; this is stated as "not applicable, with reason"
rather than an empty list, per the distinction the dispatch requires.

(`tasks.md` section 2 separately requires editing
`tests/unit/shared/application/test_settings.py` to add `LOG_LEVEL` to that
file's own hardcoded declared-field transcription — see "Unresolved
questions / notes for the implementer" below. That is not a scenario this
change's own delta spec states, and editing that pre-existing test is
correctly the implementation step's job, not this pass's: it is a
consequence of *declaring* `log_level` on `Settings`, not a behavior this
capability's own spec describes, and this pass's additive-only rule forbids
touching it regardless.)

## Cross-check against tasks.md

`tasks.md` section 5's own test breakdown (5.2–5.17) was read only after
deriving the table above from the spec directly, as a completeness
cross-check per the dispatch's instruction. Result: **no scenario found in
the spec that tasks.md's breakdown fails to name, and no outright
contradiction** — task 5's own scenario citations match the delta spec's
scenario titles one-for-one, including its own explicit call-out at task 6.4
that scenario #17 gets no unit test. Two things worth flagging as small,
non-blocking mismatches rather than defects:

1. **Task 5.15 asks for one combined test asserting both orders**
   ("Regression test, both orders: ... each leave ..."), phrased as if a
   single test parametrized or looped over both orders. This pass instead
   wrote **two separate test functions**, one per order
   (`test_uvicorn_dictconfig_then_configure_logging` and
   `test_configure_logging_then_uvicorn_dictconfig`), each its own fresh
   subprocess. This is a structural choice, not a coverage gap — task 5.15a
   in the same section separately requires "run in a fresh interpreter"
   (singular "run", read most naturally as per-invocation), and two
   standalone subprocess-launching tests make a failure in one order
   individually attributable rather than bundled into one parametrized
   test's combined report. Flagging in case the project's own convention
   prefers one parametrized test; nothing in the spec itself prefers either
   shape.
2. **Task 5.12's example unrecognized value is literally `LOG_LEVEL=20`**,
   which this pass replaced with `"9999"` for the reason recorded above
   under "Assertion classification — Derived". The scenario text itself
   ("including a numeric value") does not pin the literal example, so this
   is not treated as a spec deviation, but it is a literal divergence from
   tasks.md's own worked example, flagged for visibility.

No mismatch was found that reflects a gap in tasks.md's own understanding of
the spec, and none of tasks.md's task descriptions were treated as
authoritative over the spec itself at any point — where a choice had to be
made (test structure, the numeric example value), the spec's own text is
what was consulted to confirm the choice didn't narrow coverage.

## Unresolved questions / notes for the implementer

Convention files read: `/home/shatynska/projects/commerce-ops-proposals/AGENTS.md`
(via its own generated blocks) and `/home/shatynska/projects/commerce-ops-proposals/CLAUDE.md`
(a bare `@AGENTS.md` include, per the repo's own convention — confirmed by
reading it directly). No conflict found between those conventions and this
pass's approach; nothing here overrides `testing`'s two non-negotiable rules
(never weaken/delete an existing test to reach green; never write the code
under test), and nothing needed to.

- **The reset seam's exact name is assumed to be `_reset()`** (module-private,
  per tasks.md 1.7's own "(e.g. a private `_reset()`)" phrasing — tasks.md
  hedges with "e.g.", so the literal name is not pinned even there). Both
  test files call `logging_config._reset()`. If the implementation names
  this seam differently, every test in `test_logging.py`'s reset fixture
  fails immediately with `AttributeError` — a state-3 (test-itself-broken)
  failure distinguishable from the target-absent state the rest of this
  file's tests are currently in, and the fix is a one-line rename in the
  fixture, not a scenario re-derivation. This is a **project-specific
  interface question with no recorded convention to consult** (design.md and
  tasks.md are this project's only artifacts naming the seam at all, and
  both leave the literal name open) — recorded here per the dispatch's
  non-interactive discharge instructions, rather than resolved by
  assumption silently.
- **`configure_logging()`'s call signature is assumed to be exactly
  `configure_logging() -> None`, reading `LOG_LEVEL` internally via
  `os.environ.get`**, per tasks.md 1.1/1.2 and proposal.md's own account. No
  test in either file passes a threshold as a parameter; every test
  configures the environment via `monkeypatch.setenv`/`delenv` before
  calling it. If the real signature differs, this surfaces immediately as a
  `TypeError` on the first call in every affected test — again a readable
  state-3 failure, not a silent pass.
- **The uvicorn access-log call signature used in
  `test_logging_process_boundary.py`** (`client_addr, method, full_path,
  http_version, status_code` as five positional args to
  `logging.getLogger('uvicorn.access').info(...)`) was **confirmed
  empirically against the installed `uvicorn==0.52.4`** before being written
  into the test (ad hoc script run, not by reading `uvicorn`'s source) — see
  that file's own module docstring. This is a third-party library's public
  call contract, not a `commerce_ops` implementation detail, so relying on
  it does not cross the "don't read the implementation under test" bound;
  it is recorded here only because a future `uvicorn` major-version bump
  changing that contract would turn these two tests into state-3 (broken
  test) failures unrelated to `configure_logging()`'s own correctness, and
  a future reader should know why.

## Test-path glob and location

Both files sit under `tests/unit/shared/infrastructure/`, matching the
dispatched test-path glob `tests/**/test_*.py` and the module/layer
convention `AGENTS.md` states (`tests/unit/<module>/<layer>/`) — mirroring
where `logging.py` itself will live directly under
`src/commerce_ops/shared/infrastructure/` (not under its `driven` or
`driving` subdirectories, since it is a cross-cutting configuration entry
point, not a driving or driven adapter).
