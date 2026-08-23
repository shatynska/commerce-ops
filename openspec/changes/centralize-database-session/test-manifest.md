# Test manifest — `centralize-database-session`

Not an OpenSpec-schema artifact: `openspec instructions apply` will not list
this file among its context files. Read it on purpose before implementing —
`ai-toolkit`'s `rules/` fragment also directs the implementer here, but that
import path is machine-local, so this pointer (and the one in the dispatch
report) are the two ways to actually reach it.

This pass adds tests only. Nothing existing was edited, deleted, or
disabled, and no implementation code was written — see "How this was
verified" at the end for what was done to check the tests themselves and
how it was reverted.

## Scenario accounting

The delta spec (`specs/database-session/spec.md`) declares 13
`#### Scenario:` blocks, across 5 ADDED requirements. All 13 are accounted
for below — 11 covered, 2 uncovered with reason.

### Requirement: One Connection Pool Per Process Serves Every Application Session

| Scenario | Test |
|---|---|
| Repeated session requests share one pool | `tests/unit/shared/infrastructure/driven/test_database.py::test_repeated_session_requests_share_one_pool` |
| Request-scoped and standalone callers share one pool | `tests/unit/shared/infrastructure/driven/test_database.py::test_request_scoped_and_standalone_callers_share_one_pool` |
| Infrastructure holding its own connection or pool is not a second route to domain data | **UNCOVERED.** No infrastructure component holding its own bookkeeping connection/pool exists in this codebase at the time of this pass — design.md attributes the example this axis was drawn from (a task queue's own tables/`LISTEN`) to the sibling `replace-cron-with-job-runner` change, not this one. There is no subject in the current tree to exercise the "not a violation" branch against; tasks.md's own task list (sections 1–4) contains no task implementing an enforcement/registration mechanism for this exemption either — it is a policy statement for reviewing a future component, not an observable runtime behaviour of `database.py` itself. Fabricating a fake bookkeeping component to exercise it would invent a component this change does not add. |
| An exempt component reaching domain data is a violation | **UNCOVERED**, same reason as above — no such component exists, and no enforcement mechanism is specified by any artifact for this pass to exercise. |

### Requirement: A Session Is Available Outside An HTTP Request

| Scenario | Test |
|---|---|
| Work that is not an HTTP request obtains a session | `tests/unit/shared/infrastructure/driven/test_database.py::test_standalone_caller_obtains_a_usable_session` |
| A session is released after the caller's work completes | `tests/unit/shared/infrastructure/driven/test_database.py::test_session_released_after_the_callers_work_completes` |
| A session is released when the caller's work raises | `tests/unit/shared/infrastructure/driven/test_database.py::test_session_released_when_the_callers_work_raises` |

### Requirement: A Process That Obtained A Session Closes Its Pool Before Exiting

| Scenario | Test |
|---|---|
| The HTTP process releases connections when it stops | `tests/unit/test_main_database_lifespan.py::test_http_process_disposes_the_engine_it_obtained_when_it_stops` |
| Shutdown with no database use is not an error | `tests/unit/shared/infrastructure/driven/test_database.py::test_dispose_with_no_session_ever_requested_does_not_raise` (the application-level path — start/stop `main.app` without ever requesting a session — is also exercised, incidentally, by `tests/unit/test_main_database_lifespan.py::test_stopping_http_application_with_database_unconfigured_succeeds`, whose primary purpose is the next requirement below) |

### Requirement: The Connection Setting Is Read No Earlier Than The First Session Request

| Scenario | Test |
|---|---|
| The connection setting is read only when a session is first requested | `tests/unit/shared/infrastructure/driven/test_database.py::test_importing_the_provider_does_not_require_database_url` |
| Starting and stopping with the database unconfigured | `tests/unit/test_main_database_lifespan.py::test_stopping_http_application_with_database_unconfigured_succeeds` (the *starting* half, with every declared variable absent, is already covered by the existing `tests/unit/test_startup_without_configuration.py`, per tasks.md 4.9a's own instruction to cite rather than duplicate it — this new test's contribution is the *stopping* half, scoped to `DATABASE_URL` specifically) |

### Requirement: An Absent Or Malformed Connection Setting Is Reported At The Point Of Use

| Scenario | Test |
|---|---|
| A session is requested with the setting absent | `tests/unit/shared/infrastructure/driven/test_database.py::test_session_requested_with_the_setting_absent_reports_the_setting` |
| A session is requested with a setting the application cannot connect with | `tests/unit/shared/infrastructure/driven/test_database.py::test_session_requested_with_an_unconnectable_scheme_reports_setting_and_scheme` |

### DERIVED tests, not themselves a `#### Scenario:` block

These extend coverage beyond the 13 scenarios above, each traceable to
tasks.md or design.md rather than to spec text, and each labelled DERIVED
in the test file itself:

- `test_database.py::test_dispose_engine_after_use_disposes_the_engine` —
  tasks.md 4.6 ("`dispose_engine()` after use disposes the engine — this
  covers the provider's half only, not the application-shutdown scenario").
- `test_database.py::test_session_after_dispose_gets_a_fresh_usable_engine`
  — tasks.md 4.8 / design.md's Risks (third entry: an `lru_cache`d engine
  factory must pair disposal with cache invalidation).
- `test_database.py::test_session_requested_with_the_setting_empty_reports_the_setting`
  — tasks.md 1.3 ("reporting absence or emptiness in a message naming
  DATABASE_URL"); the requirement's own text names "absent, empty, or not a
  connection string" but only two of those three get their own `####
  Scenario:` block.

## Assertion classification

Per `ai-toolkit:testing`'s specified/derived/deliberately-untested rule,
noted inline in each test via `# SPECIFIED` / `# DERIVED` comments; summary:

- **Specified** (traces directly to a scenario's WHEN/THEN): every
  assertion in the 11 covered-scenario tests above.
- **Derived** (traces to tasks.md/design.md, not spec text): the three
  tests listed under "DERIVED tests" above, plus the "no real Postgres" /
  "same event loop is not required" claims embedded in fixture docstrings
  (verified by hand against this project's pinned sqlalchemy/asyncpg
  versions, not asserted as test assertions themselves).
- **Deliberately untested**: the two bookkeeping-exemption scenarios,
  recorded uncovered above with reason — not silently dropped.

## Obsolete-tests list

**Not applicable.** Every requirement in this delta spec is ADDED; there is
no MODIFIED or REMOVED delta, so there is no superseded pre-change behaviour
to compare against and no existing test that could bear on one. (`specsRoot`
was correctly not supplied for this dispatch, per the dispatch's own
"Delta type" note.)

## Unresolved project questions

1. **"Released"/"disposed" are read as SQLAlchemy's standard
   `AsyncSession.close()` / `AsyncEngine.dispose()`, not asserted by any
   artifact directly.** Tasks.md fixes the *mechanism* by name
   ("`dispose_engine()`... awaits `engine.dispose()`"; `session()`
   "releas[es]... on both normal completion and exception") but not the
   literal call. This reading is the only established SQLAlchemy idiom for
   the shape design.md's own code excerpt already uses
   (`async with session_factory() as session: yield session`, whose
   `__aexit__` calls `.close()`). Tests depending on this assumption: every
   test using the `track_session_close`/`track_engine_dispose` fixtures in
   both files. If a real implementation releases/disposes through some
   other path, these tests would need their monkeypatch target corrected —
   a fixture correction, not a change to what any test asserts, per this
   file's own precedent in `test_clickup_client.py`'s docstring for its
   `get_client()` seam.
2. **No skill matched this stack specifically.** `python` (general Python)
   applies; no bundled skill exists for SQLAlchemy/FastAPI lifespan testing
   specifically. Recorded per the dispatch contract's "record the absence"
   instruction; proceeded on the `testing` floor plus `python` alone.
3. **Whether `get_session()` takes no arguments** is assumed from
   design.md's Context section transcribing today's `monitoring.py`
   (`async def get_session() -> AsyncIterator[AsyncSession]:`, no
   parameters) plus the Decisions section's "monitoring.py keeps a
   get_session name" (a re-export, implying the same signature survives).
   `test_request_scoped_and_standalone_callers_share_one_pool` depends on
   this. If the real signature takes a parameter, that call site is a
   fixture-level correction.

## Baseline

Full baseline taken before writing any new test file:

```
uv run pytest tests/unit tests/agents -q
200 passed in 7.04s
```

After adding the two new files (before any implementation exists):

```
uv run pytest tests/unit tests/agents -q --continue-on-collection-errors
200 passed, 2 errors in 6.84s
```

The 2 errors are `ImportError: cannot import name 'database' from
commerce_ops.shared.infrastructure.driven` — the expected, correct failure
state per `ai-toolkit:testing`'s failure-state taxonomy (target absent),
not evidence about whether the assertions are well-formed. The 200
previously-passing tests are unaffected.

The integration tier (`tests/integration`) was not run — it requires a
local Postgres this environment does not have; tasks.md 5.2 assigns running
it (unmodified; `tests/integration/products/conftest.py` is explicitly out
of this change's scope) to the implementer.

## How this was verified

To check the test file's own logic (fixture ordering, the async-autouse-
fixture-vs-sync-test-in-the-same-module bug this caught and fixed, the
event-loop-independence claim, the disposal-spy seam) before handing them
off, a throwaway stub was written to
`src/commerce_ops/shared/infrastructure/driven/database.py` and a throwaway
lifespan wired into `src/commerce_ops/main.py`, the full suite was run
(200 baseline + 14 new = 214 passed), and both files were then reverted
with `git checkout -- src/commerce_ops/main.py` and `rm` of the untracked
stub. `git status --porcelain` after reverting shows only the two new test
files as untracked — no implementation was left behind. This is reported
so the check is auditable, not left as an unstated step.
