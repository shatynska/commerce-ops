## 1. One resolver for the tier's database

- [x] 1.1 Add `tests/integration/conftest.py` resolving the URL once per session in the four-rung order `design.md` — Decisions fixes: the `DATABASE_URL` environment variable, else `.env.test`, else `.env`, else required-or-skip
- [x] 1.2 Expose that resolution through **two** fixtures, not one: an autouse session fixture that only publishes the resolved value into `os.environ["DATABASE_URL"]` (session-scoped `MonkeyPatch`; publishes nothing when nothing resolves, but still reports) and a requested `database_url` fixture that gates — see `design.md` — "Publishing is autouse; gating is opt-in"
- [x] 1.3 Publish because three integration files drive the real app and its session provider reads that variable directly (`shared/infrastructure/driven/database.py:31-37`) — without publication, rungs 2 and 3 make those three fail rather than run
- [x] 1.4 Read **only** the `DATABASE_URL` key from either file, with the standard library and no new dependency, so no other secret in them reaches the test process
- [x] 1.5 Treat an empty value as absent, matching `database.py:33` and all twelve existing helpers, and state which parse forms the reader honours — quoting, an `export ` prefix, inline comments — since the value carries a password and two other tools parse the same file
- [x] 1.6 Make the skip and failure messages name what to start (`docker compose up -d postgres`), what to set, and that migrations must be applied — the twelve messages being replaced each name their own subtree's migration, so the shared one has to carry a migration note to stay as useful
- [x] 1.7 Report at session start which rung supplied the URL, through `pytest_report_header` rather than `print` — a session fixture's stdout is captured and surfaces only beside a failing test, so on the run that matters most, where everything skips and nothing fails, a printed report is never seen
- [x] 1.8 Include host, port, database name and **username** in that report, and **not** the password — the username tells two databases apart and is decided here rather than left to the implementer
- [x] 1.9 Report the no-URL state too, saying the tier will skip — it is where a test that needs a database and did not request the gate hard-errors from `database.py:34`, and where nothing else explains why
- [x] 1.10 Carry `docker compose up -d postgres` in both reports, since rung 3 now means a stopped Postgres turns a push into connection tracebacks rather than a skip — the path `design.md`'s Risks require a guided message on

- [x] 1.11 Add `-rs` to `addopts` in `pyproject.toml`, so a skipped test's reason reaches the terminal. Without it the default `-r fE` hides every skip reason — including the twelve existing messages, which is why `3 passed, 64 skipped` read as success — and task 1.6's replacement message would be composed and never shown
- [x] 1.12 Verify by running the tier with no database configured and confirming both the header and the skip reason appear in a plain `uv run pytest tests/integration`

## 2. Retire the twelve duplicated resolvers

- [x] 2.1 Replace each local `_database_url()` in `tests/integration/` with the shared fixture — the twelve files carrying the helper, plus any other file resolving `DATABASE_URL` itself
- [x] 2.2 Change no assertion, fixture or test body beyond the resolver call. The per-subtree skip messages are the one deliberate loss; nothing else about behaviour changes
- [x] 2.3 Verify the whole tier still passes against a live database, and that no file under `tests/integration/` still reads `DATABASE_URL` directly
- [x] 2.4 Verify the three app-driving files that resolve a URL — `test_known_work_anchor.py`, `test_scheduled_runs_freshness_cache.py`, `test_slack_entry_start.py` — since publication exists for them, and confirm each requests the gating fixture on the path that builds its `TestClient`
- [x] 2.5 Verify `test_scheduled_runs_freshness_unreachable.py` still runs with no database configured at all, requesting neither fixture: its docstring makes never-skipping its stated purpose, and it is one of only two integration tests that run on a bare machine

## 3. Make a required tier fail rather than skip

- [x] 3.1 Honour `COMMERCE_OPS_REQUIRE_DATABASE=1` in the fixture: when no URL resolves and the flag is set, fail the session instead of skipping
- [x] 3.2 Keep the skip when the flag is absent, so a contributor with **no database configuration at all** — no variable, no `.env`, no `.env.test` — can still run `uv run pytest` over the whole tree on a fresh clone
- [x] 3.3 Leave the `pre-push` hook in `.pre-commit-config.yaml` without the flag, and record in `README.md` (task 5.1) what actually changes there: with `.env` present the tier now runs, so a stopped Postgres fails the push — the flag would be inert in that case and would only penalise someone with no configuration at all
- [x] 3.4 Cover the resolver with tests in `tests/unit` — each rung, their precedence, empty-as-absent, and the flag's two directions. It is pure logic over a filesystem and an environment, so it needs no database, and no spec scenario covers it

## 4. Run the tier in CI

- [x] 4.1 Add a `postgres:16-alpine` service container to `.github/workflows/ci.yml`, matching the image `docker-compose.yml` runs, with a health check the job waits on
- [x] 4.2 Compose `DATABASE_URL` in the workflow from the service's own credentials — no repository secret, since the database is ephemeral and reachable only from the job
- [x] 4.3 Run `alembic upgrade head` against it before the tier, which the tests assume applied (schema plus seed)
- [x] 4.4 Add the `pytest tests/integration` step with `COMMERCE_OPS_REQUIRE_DATABASE=1` set
- [x] 4.5 Confirm the job still declares no deploy SSH credential and makes no connection to the deploy host, per `deploy-pipeline`'s preserved constraints
- [ ] 4.6 Verify on a pull request that the tier reports run counts rather than skips, and that removing the service makes the job fail rather than pass
- [ ] 4.7 Watch the first CI run of `test_scheduled_runs_freshness_unreachable.py`: its unanswered-database shape targets `192.0.2.1:5432`, and a runner that returns RST rather than blackholing would quietly turn it into a duplicate of the refused case — still green, no longer discriminating

## 5. Record how the tier reaches its database

- [x] 5.1 Rewrite `README.md`'s "Local Postgres" section: the manual `export` is no longer needed, and line 105's "skips rather than failing" stops being true for anyone with a `.env`
- [x] 5.2 Note in the same section that the pre-push hook exists only for contributors who ran `pre-commit install --hook-type pre-push`, since `default_install_hook_types` omits it and the local behaviour above reaches nobody else
- [x] 5.3 Document `.env.test` there — what it is for, that it is optional, and that opting in means creating and migrating that database once by hand, since nothing in this change creates it
- [x] 5.4 Add one line to `AGENTS.md`'s Testing Strategy naming how the integration tier resolves its database and what makes it required in CI

## 6. Verification

- [x] 6.1 Run `uv run pytest tests/unit tests/agents`
- [x] 6.2 Run `uv run pytest tests/integration` with no `DATABASE_URL` exported, and confirm it now runs rather than skipping
- [x] 6.3 Run it again with a `.env.test` present, and confirm the tier used that database — no new `mg.*` rows appear in the database `.env` names
- [x] 6.4 Run `ruff check`, `ruff format --check`, `mypy`, and `lint-imports`
- [ ] 6.5 Push the branch and confirm the CI job runs the integration tier green, with a non-zero test count
