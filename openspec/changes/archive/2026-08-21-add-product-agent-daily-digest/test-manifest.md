# Test manifest: add-product-agent-daily-digest

Not an OpenSpec-schema artifact -- `openspec instructions apply` will not
surface this file among its context files. Read it on purpose before
implementing any task in `tasks.md`. (The library's own `rules/` fragment
also points implementers back to this file; this is the second, redundant
pointer that doesn't depend on that fragment's machine-local import path
resolving on this machine.)

Written by a dispatched test-writing pass that never read any
implementation of this change (none exists yet) and never wrote any. Every
test below is additive: no existing test file was edited, deleted, or
weakened to produce this pass. Both delta specs are `ADDED`-only (no
`MODIFIED`/`REMOVED`/`RENAMED` deltas), so nothing here was compared against
a prior spec revision, and the obsolete-tests list is **not applicable**
for that reason.

## Baseline

Full-suite baseline, taken before writing any test in this pass:

```
uv run pytest tests/unit tests/agents tests/integration -q
80 passed, 20 skipped in 2.09s
```

(The 20 skips are the existing `tests/integration/products/` tests,
skipped for lack of a `DATABASE_URL` -- pre-existing, unrelated to this
pass.)

After writing every test below, the same command
(`uv run pytest tests/unit tests/agents tests/integration -q
--continue-on-collection-errors`) reports:

```
5 failed, 82 passed, 22 skipped, 3 errors in 3.21s
```

- **82 passed** = the original 80, plus two new regression-guard tests in
  `test_main_monitoring_wiring.py` that pass today because `commerce_ops.main`
  does not yet import anything this change adds (`test_main_imports_...` and
  `test_health_endpoint_still_serves_...`).
- **22 skipped** = the original 20, plus the two new
  `tests/integration/products/test_product_repository_list_names.py` tests,
  skipped for the same `DATABASE_URL`-absence reason as their siblings.
- **5 failed** = `test_main_monitoring_wiring.py::test_route_is_registered`,
  parametrized over the five cadence paths -- each currently 404s, since
  `main.py` does not yet mount any monitoring router (Task 5.6 not done).
- **3 errors** = collection failures (`ModuleNotFoundError`/`ImportError`)
  in `test_internal_trigger_guard.py`, `test_daily_digest.py`, and
  `test_monitoring_routes.py` -- each imports a module/name that does not
  exist yet (Tasks 1, 2.2, 3.1/3.3, 4, 5).

Every one of these 8 non-passing results is failure state 2
(`ai-toolkit:testing`'s taxonomy: target absent) -- none establishes
anything about whether the assertions inside are well-formed, only that
the target does not exist yet. **No previously-passing test regressed.**

## Scenario accounting

11 `#### Scenario:` blocks total across both delta specs (5 in
`internal-trigger`, 6 in `product-monitoring`); all 11 accounted for below.

### `internal-trigger` (5 scenarios)

File: `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py`

| Scenario | Test(s) |
|---|---|
| Missing secret is rejected | `test_missing_authorization_header_is_rejected` |
| Incorrect secret is rejected | `test_incorrect_secret_is_rejected` (+ DERIVED `test_secret_that_is_a_prefix_of_the_real_one_is_still_rejected`) |
| Matching secret is accepted | `test_matching_secret_is_accepted` |
| Comparison uses constant-time equality | **UNCOVERED** -- see below |
| Trigger secret is not configured | `test_every_request_is_rejected_when_secret_is_unconfigured_and_no_header_sent` (+ `..._even_with_a_header`) |

**Uncovered: "Comparison uses constant-time equality."** This requirement
names an internal *mechanism* (constant-time vs. short-circuiting
comparison), not an externally observable outcome. Verifying it would
require either (a) reading the implementation to see which comparison
function it calls -- a bound this pass does not cross, since no
implementation exists yet and the pass is not permitted to read one even
once it does -- or (b) a wall-clock timing measurement, which this
project's own precedent (`test_slack_events_endpoint.py`'s explicit
rejection of a deliberate `sleep` "because it would add runtime without
adding evidence") and `ai-toolkit:testing`'s own discipline both argue
against: a timing-based assertion would be flaky and would not reliably
discriminate constant-time from short-circuiting behavior at the
millisecond resolution a test process can measure. Recorded as
deliberately uncovered by a test; this remains a **code-review** item
(confirm the implementation calls `hmac.compare_digest` /
`secrets.compare_digest` or an equivalent, not `==`), not a test-authoring
one.

### `product-monitoring` (6 scenarios)

File: `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`
(primary evidence for all 6); `tests/unit/products/application/test_daily_digest.py`
and `tests/integration/products/test_product_repository_list_names.py`
add DERIVED supplementary coverage at lower layers (see "Level choices"
below).

| Scenario | Test(s) |
|---|---|
| A cadence endpoint rejects an unguarded request | `test_unguarded_request_is_rejected_and_performs_no_reporting_action` (parametrized over all 5 cadence paths) |
| Daily trigger lists product names | `test_daily_trigger_lists_product_names` |
| No products exist | `test_no_products_exist_posts_a_message_rather_than_nothing` |
| A non-daily cadence is triggered | `test_non_daily_cadence_is_acknowledged_without_posting` (parametrized over weekly/biweekly/monthly/quarterly) |
| Slack post fails | `test_slack_post_failure_still_yields_an_accepted_trigger_response` |
| Database read fails | `test_database_read_failure_yields_a_failing_status_and_an_attempted_post` |

No scenario in this delta spec is uncovered.

### Level choices

`product-monitoring`'s requirements are all stated in terms of the
*endpoint's* observable behavior (invoked -> Slack post / response
status), so per `ai-toolkit:testing`'s Level rule the route is the smallest
unit that can observe them -- `test_monitoring_routes.py` is the primary
evidence for all 6 scenarios above. Two supplementary, lower-level files
were also written, both DERIVED from `tasks.md` rather than from a named
scenario (they do not double-count any scenario in the table above):

- `tests/unit/products/application/test_daily_digest.py` -- `tasks.md`
  8.2's ask for use-case-level coverage of the daily use case against a
  fake `ProductNameReader` (names returned correctly, "no products" case,
  a reader failure propagating rather than being swallowed).
- `tests/integration/products/test_product_repository_list_names.py` --
  `tasks.md` 8.3's ask, run against real Postgres (this repo's convention
  for anything touching `ProductRepository`). A new file, not an edit to
  the existing `tests/integration/products/test_product_repository.py`.

`tasks.md` 8.4 (unit tests for the no-op placeholder use case: performs no
reporting action, logs as intentional) was **deliberately not written as a
separate file**. The one scenario it would support --
"A non-daily cadence is triggered" -- is already fully accounted for at
the route level, and the no-op placeholder's own name/shape is never fixed
by any artifact; inventing one purely to duplicate already-covered ground
would add an invented contract without adding scenario evidence. This is a
recorded choice, not an omission -- see "Unresolved project questions"
below if a future pass wants to name and test it directly once its shape
exists.

## Obsolete tests

**Not applicable.** Both delta specs (`internal-trigger`,
`product-monitoring`) are `ADDED`-only; there is no `MODIFIED` or `REMOVED`
delta to compare against a prior spec revision, and no existing test in
this repository's `tests/**/test_*.py` was found (nor searched for outside
the ordinary course of reading this repo's existing test layout) to bear
on superseded behavior, because none is superseded.

## Assertion classification

Classified inline in each test/docstring (`SPECIFIED`, `DERIVED`,
`DELIBERATELY UNTESTED`), following this repo's own established
convention (see e.g. `test_product_repository.py`,
`test_slack_events_endpoint.py`). Summary:

- **SPECIFIED** (traces directly to a requirement's SHALL/scenario text):
  guard rejection/acceptance outcomes and handler-invocation facts; the
  guard's fail-closed-when-unconfigured behavior; each cadence path's
  guard enforcement; the daily endpoint posting product names / a
  no-products message; non-daily cadences never posting; delivery-failure
  logging + accepted response; database-read-failure's failing status +
  attempted failure post.
- **DERIVED** (inferred, no artifact pins it exactly): exact status codes
  where the spec says only "accepted"/"failing" (read as 2xx / >=500
  respectively); log level used to detect "logged" (WARNING or above);
  the guard's exact 401 status code doubling as evidence in
  `test_monitoring_routes.py` (the guard's own spec fixes 401; this file
  reuses that fact rather than re-deriving it); the prefix-of-the-real-secret
  probe in the guard file; both application-layer and repository-layer
  supplementary tests in their entirety (see "Level choices").
- **DELIBERATELY UNTESTED**: the exact wording of the "no products exist"
  message and of the database-read-failure message (neither spec nor
  design.md pins any phrasing -- same reasoning this repo's own
  `test_omni_agent_invocation_failure_posts_a_message_to_the_channel`
  already applies to an analogous failure message); the constant-time
  comparison mechanism (see "Uncovered" above, `internal-trigger`).

## Unresolved project questions (assumptions taken, and what depends on them)

None of these are answered by any artifact this pass could read (proposal,
design, tasks, delta specs, `AGENTS.md`/`CLAUDE.md`). Each is an INVENTED
name/shape a later correction may need to adjust -- per `ai-toolkit:testing`'s
provenance rule, adjusting an import or a fixture's construction on account
of one of these is a **fixture correction**, not license to weaken the
postcondition each test actually asserts.

1. **The guard's module path and callable name.** Assumed
   `commerce_ops.shared.infrastructure.driving.trigger_guard.require_trigger_secret`.
   Depends on: every test in `test_internal_trigger_guard.py`; the guard
   import in `test_monitoring_routes.py`'s own assumed wiring (see #3).
2. **The `daily` use case's function name and "no products" return shape.**
   Assumed `commerce_ops.products.application.run_daily_digest(reader) ->
   Sequence[str]`, with an empty sequence read as the explicit "no products
   exist" signal. Depends on: every test in `test_daily_digest.py`, and the
   `run_daily_digest` patch target in `test_monitoring_routes.py`.
3. **The five routes' module path, router attribute name, and the names
   the router imports its collaborators under.** Assumed
   `commerce_ops.products.infrastructure.driving.monitoring`, exposing
   `router`, `run_daily_digest`, `post_monitoring_message`, and
   `get_session` as module-level names patchable/overridable the same way
   `omni_agent/infrastructure/driving/slack.py` exposes `answer_question`.
   Depends on: every test in `test_monitoring_routes.py`.
4. **`post_monitoring_message`'s signature.** Assumed
   `products/infrastructure/driven/slack_notifier.py` (path itself is
   SPECIFIED, by `tasks.md` 4.1) exposes a callable taking one positional
   `message: str`. Depends on: the notifier-related assertions in
   `test_monitoring_routes.py`.
5. **The per-request session dependency's shape.** Assumed a `get_session`
   async-generator FastAPI dependency (`design.md`'s Decisions says it
   "yields a session"), overridable via `app.dependency_overrides`.
   Depends on: `test_monitoring_routes.py`'s `app`/`client` fixtures.
6. **No async-test-plugin convention is recorded for this project.**
   Following `tests/integration/products/conftest.py`'s own prior
   assumption (no `pytest-asyncio`, `anyio` used via `@pytest.mark.anyio`
   with the backend pinned to `asyncio`), `test_daily_digest.py` and
   `test_product_repository_list_names.py` both do the same. This was
   already an unresolved project question before this pass; not newly
   introduced by it.
7. **"Failing status" for a database-read failure is read as >=500.**
   Neither spec nor design.md names an exact code, only that it must be
   "distinct from the response given when only report delivery fails."
   Depends on: `test_database_read_failure_yields_a_failing_status_and_an_attempted_post`.
8. **No truncate/rollback fixture exists for `tests/integration/products/`**
   (pre-existing convention, not introduced here). This is why
   `test_product_repository_list_names.py` asserts containment rather than
   exact-set equality, and does not attempt a "the database has zero
   products" case at the repository level (that case stays covered at the
   route level, where a fake reader can control this directly).

## Regression guard (Task 8.6)

`tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py`
mirrors `tests/unit/omni_agent/infrastructure/driving/test_main_slack_wiring.py`'s
own two guards (subprocess import of `commerce_ops.main` and a `/health`
request, both with `TRIGGER_SECRET`/`PRODUCT_AGENT_SLACK_BOT_TOKEN`/
`DATABASE_URL` absent), plus a `test_route_is_registered` check per
cadence path modeled on that file's own `test_slack_events_route_is_registered`.
This is a regression guard, not scenario coverage -- it does not appear in
either scenario-accounting table above.

## What the implementation step must make pass

Every test enumerated in the two scenario tables above, plus the
supplementary/DERIVED files (`test_daily_digest.py`,
`test_product_repository_list_names.py`) and the regression guard
(`test_main_monitoring_wiring.py`). Selectable individually via
`uv run pytest <path>::<test_name>`; every parametrized test is selectable
per-parameter via `<path>::<test_name>[<id>]` (e.g.
`test_monitoring_routes.py::test_unguarded_request_is_rejected_and_performs_no_reporting_action[daily]`).

Full file list this pass added (all new; nothing existing was edited):

- `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py`
- `tests/unit/products/application/test_daily_digest.py`
- `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`
- `tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py`
- `tests/integration/products/test_product_repository_list_names.py`
