## 1. Configuration entry point

- [x] 1.1 Add `src/commerce_ops/shared/infrastructure/logging.py` with `configure_logging() -> None`, importing the standard library's `logging` absolutely
- [x] 1.2 Resolve the threshold: read `LOG_LEVEL` via `os.environ.get("LOG_LEVEL")` with the variable name written as a string literal at the read site, so `test_settings_env_drift.py`'s source scan (which matches a *constant* argument) sees it
- [x] 1.3 Treat absent **or empty** as not configured — default `INFO`, no report. Match level names **case-insensitively**. Treat as unrecognized: a present, non-empty value that names no level, a numeric one such as `20`, and `NOTSET` — the last because it is a real name whose effect (defer to root's `WARNING`) silently restores the defect this change fixes. On any unrecognized value fall back to `INFO` and record the rejected value through the logging this same call configures, never `print`
- [x] 1.4 Guard idempotency: mark the handler this function installs with a module-level sentinel attribute and return early if root already carries one, rather than relying on `basicConfig`'s implicit no-op
- [x] 1.5 Attach a **`StreamHandler`** writing to `sys.stderr` to the **root** logger, with a formatter carrying timestamp, level name, logger name and message; leave the handler's own level at `NOTSET`. It must stay a `StreamHandler` — design.md, Context fact 3 records why a file-backed or queue-backed handler would break silently under `dictConfig`
- [x] 1.6 Set the root logger's level to `WARNING` and the `commerce_ops` logger's level to the resolved threshold — the two-gate split in design.md, "Set root's level to `WARNING`"
- [x] 1.7 Expose a reset seam (e.g. a private `_reset()`) that **detaches the sentinel handler only** — it must not set levels, since "restore" has no single correct target. The fixture in 5.1 snapshots and restores `logging.getLogger().level` and `logging.getLogger("commerce_ops").level` itself. Resetting root to `NOTSET` would leak a level-0 root into every later test module in the session, and the commit hook runs the whole tier

## 2. Declaration

- [x] 2.1 Declare `log_level: str | None = None` on `Settings` in `shared/application/settings.py`, as optional. Deliberately **not** `NonEmpty | None`: the spec defines an empty value as "not configured", and `NonEmpty` would make `preflight` report `LOG_LEVEL` as faulting while logging behaved exactly as specified — two accounts of one value (design.md — "Empty deserves a straight answer")
- [x] 2.2 Extend the module docstring's account of directly-read variables to cover `LOG_LEVEL`, naming the real reason: `configure_logging()` runs at `main.py`'s module import, where `get_settings()` would raise under `runtime-configuration`'s empty-environment guarantee
- [x] 2.3 Confirm no `ENV_VAR_EXEMPTIONS` entry is needed — the source does read it, so the drift test is satisfied by the read in 1.2
- [x] 2.4 **Update `tests/unit/shared/application/test_settings.py`**: add `LOG_LEVEL` to `OPTIONAL` (and therefore to `ALL_DECLARED`), which its `assert set(_declared_fields()) == set(ALL_DECLARED)` and `assert set(declared) - actually_required == set(OPTIONAL)` both require. Without this the pre-commit hook blocks every commit of this change. Add a comment recording that the transcribed set now spans more than one change
- [x] 2.5 Check `tests/unit/test_preflight.py` and `tests/unit/test_startup_without_configuration.py` for the same transcribed set — neither asserts equality so neither fails, but a stale transcription weakens their empty-environment preconditions

## 3. Call sites

- [x] 3.1 Call `configure_logging()` at module import in `src/commerce_ops/main.py`, after its imports and before the routers are included (design.md records why not above the imports: ruff `E402`)
- [x] 3.2 Call `configure_logging()` as the first statement of `check()` in `src/commerce_ops/preflight.py`
- [x] 3.3 Leave `preflight.py`'s existing `print(..., file=sys.stderr)` report as it is — it is the process's user-facing report, deliberately not a log record, and `deploy-pipeline` depends on its wording

## 4. Delivery through the deploy pipeline

- [x] 4.1 Add a `LOG_LEVEL` line to `.github/workflows/deploy.yml`'s "Render .env" step as `${{ vars.LOG_LEVEL || 'INFO' }}` — a repository/Environment **variable**, not `secrets.*` as every other line in that step uses, because the threshold is not sensitive and masking it in logs would serve nothing. GitHub expressions treat `''` as falsy, so this one form covers both unset and empty (design.md — "Deliver `LOG_LEVEL` through `deploy.yml`")
- [x] 4.2 Note that no `LOG_LEVEL` variable exists today, so the deploy renders `INFO` until someone creates one. Record, in a comment beside the `deploy.yml` line: the variable is set under Settings → Secrets and variables → Actions → Variables, and **a change takes effect on the next deploy**, since `.env` is re-rendered only then

## 5. Tests

All in `tests/unit/shared/infrastructure/`, per AGENTS.md's `tests/unit/<module>/<layer>/` convention.

**Construct every "dependency" logger inside the test.** Do not assert against an installed package's real logger configuration: `sqlalchemy` sets its own `WARNING` at import and `slack_bolt` copies root's level onto its child loggers, so such an assertion is either red on the first run or vacuous, and it breaks on an unrelated dependency bump with no behavioural meaning.

- [x] 5.1 Fixture: detach the sentinel handler and restore the root and `commerce_ops` levels around each test in this module, via 1.7's reset seam. **Required first** — several unit modules import `commerce_ops.main` at collection, so `configure_logging()` has already run by the time any test body executes, and 1.4's guard makes later calls no-ops. Without this, every threshold test below asserts against the collection-time configuration
- [x] 5.2 Unit test: a `commerce_ops.*` record at the configured threshold reaches stderr (spec: "A record at the configured threshold is emitted"; also covers "The threshold is configured explicitly")
- [x] 5.3 Unit test: with `LOG_LEVEL` absent, an informational record reaches stderr (spec: "An informational record is emitted under the default threshold"; also covers "The threshold is not configured")
- [x] 5.4 Unit test: with `LOG_LEVEL=WARNING`, an informational application record does not reach stderr (spec: "An application record below the configured threshold is suppressed")
- [x] 5.5 Unit test: a dependency logger at informational level is suppressed (spec: "An unconfigured dependency's informational record is suppressed")
- [x] 5.6 Unit test: a dependency logger at `WARNING` is emitted with the same formatting as an application record (spec: "An unconfigured dependency's warning is emitted and formatted")
- [x] 5.7 Unit test: with `LOG_LEVEL=DEBUG`, a dependency's informational record is still suppressed (spec: "Lowering the application's threshold does not turn on dependency logging")
- [x] 5.8 Unit test: with `LOG_LEVEL=ERROR`, a dependency's `WARNING` is still emitted (spec: "Raising the application's threshold does not silence dependency warnings")
- [x] 5.8a Unit test: a library logger that sets its own informational level and attaches its own handler still emits its record, and it reaches this capability's handler as well when that logger propagates (spec: "A library that configures its own logger still emits its own records"). Construct the logger in the test — do **not** assert facts about installed third-party packages' internal logger configuration, which breaks on an unrelated dependency bump with no behavioural meaning
- [x] 5.9 Unit test: a record emitted through the configured logging carries time, level and logger name alongside the message (spec: "A record emitted through the configured logging identifies when, how severe, and from where")
- [x] 5.10 Unit test: `logger.exception(...)` inside an `except` block carries the traceback (spec: "An exception's traceback is preserved")
- [x] 5.11 Unit test: `LOG_LEVEL=` (present, empty) configures at `INFO` and makes **no** unrecognized-value report (spec: "The threshold is configured as an empty value")
- [x] 5.12 Unit test: `LOG_LEVEL=NOT_A_LEVEL`, `LOG_LEVEL=20` and `LOG_LEVEL=NOTSET` each configure at `INFO`, report the rejected value, and do not raise (spec: "The configured threshold is not a recognized level", "The zero level is treated as unrecognized")
- [x] 5.12a Unit test: `LOG_LEVEL=debug` is applied as `DEBUG` with no unrecognized-value report (spec: "A level name in lower case is recognized")
- [x] 5.13 Unit test: calling `configure_logging()` twice emits a subsequent record once (spec: "Configuring logging more than once does not duplicate records")
- [x] 5.14 Unit test: `configure_logging()` succeeds with the environment fully cleared (spec: "Logging is configured with an empty environment")
- [x] 5.15 Regression test, **both orders**: applying `uvicorn.config.LOGGING_CONFIG` via `dictConfig` after `configure_logging()`, and `configure_logging()` after that `dictConfig`, each leave an application record reaching the stream and a `uvicorn.access` record emitted exactly once — note uvicorn's `access` handler writes to **stdout**, not stderr, so capture the right stream (spec: "Server request logs continue to be emitted exactly once", "The application's records survive the server configuring its own logging"). The production order under the uvicorn CLI is uvicorn-first; a test that imports `main` first exercises the reverse
- [x] 5.15a Run 5.15 **in a fresh interpreter** (as `test_main_slack_wiring.py` and `test_preflight.py` already do for process-global effects). `dictConfig` calls `_clearExistingHandlers()`, which flushes, closes and de-registers *every* live handler in the process — including the ones pytest's logging plugin installs for the current item — and leaves `uvicorn`/`uvicorn.access` configured for the remainder of the session. In-process, this surfaces as another test losing captured output, attributed to the wrong test. Task 5.1's fixture restores the sentinel handler and the two levels; it does not and should not try to undo this
- [x] 5.16 Test: a record emitted after `preflight.check()` in a fresh interpreter reaches stderr (spec: "A non-HTTP entrypoint emits records") — without this, deleting task 3.2's call leaves nothing red
- [x] 5.17 Confirm the existing `test_main_slack_wiring.py` and `test_main_monitoring_wiring.py` fresh-interpreter guards still pass unmodified — `main.py` now calls `configure_logging()` at import, and those tests import it with required variables absent

## 6. Verification

- [x] 6.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports`
- [x] 6.2 Run `openspec validate configure-application-logging --strict`
- [ ] 6.3 After deploy: confirm `docker logs` shows formatted, timestamped lines
- [ ] 6.3a After deploy: trigger the **weekly** cadence by hand with the deployed `TRIGGER_SECRET` and confirm `pending_cadence.py`'s informational record appears — the line that has never reached a log. Do **not** use the 06:00 `daily` cadence for this: it calls `run_daily_digest` and never reaches `pending_cadence.py`, so it cannot produce the record and its absence would read as failure (design.md — Migration Plan)
- [ ] 6.4 After deploy: confirm `LOG_LEVEL` is present in the container's environment with the expected value, so the knob is demonstrated to work rather than assumed. This is the verification route for the spec scenario "The threshold can be set in the deployment without changing application code" — there is deliberately no unit test for it, since nothing in `tests/` parses workflow YAML
