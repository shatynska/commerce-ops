## Context

See proposal.md — Why, for the problem. This section records only the facts about the current process that constrain the approach; each was verified against the installed dependency rather than assumed.

**Uvicorn's default logging configuration** (`uvicorn.config.LOGGING_CONFIG`, uvicorn 0.52):

```
uvicorn         → handlers: [default → stderr], level: INFO, propagate: false
uvicorn.error   → level: INFO                        (no handlers; propagates to `uvicorn`)
uvicorn.access  → handlers: [access  → stdout], level: INFO, propagate: false
root            → not configured at all
disable_existing_loggers: false
```

Three things follow, and the design rests on all three:

1. **Root is never configured by uvicorn.** This is the whole cause of the defect — `commerce_ops.*` records propagate to a handler-less root and reach `logging.lastResort`, a bare `StreamHandler` fixed at `WARNING` with no formatter.
2. **Uvicorn's own loggers do not propagate.** `uvicorn` and `uvicorn.access` both set `propagate: false` and carry their own handlers; `uvicorn.error` has no handlers but propagates only as far as `uvicorn`, which stops it. No uvicorn record ever reaches the root logger. Therefore attaching a handler to root cannot duplicate uvicorn's output.
3. **A root handler attached before uvicorn starts survives uvicorn's `dictConfig` call in effect — but not for the reason it first appears.** `dictConfig` is not selective: `logging/config.py`'s non-incremental path calls `_clearExistingHandlers()`, which flushes, `close()`s and de-registers *every* live handler, whether or not its logger is named in the config. The attached handler survives usefully only because `StreamHandler` inherits `Handler.close()`, which is a no-op, where `FileHandler` overrides it with a real close.

   **This imposes a constraint the design must carry:** the handler this change installs must remain a plain `StreamHandler`. Swapping it for a file-backed, rotating or queue-backed handler later — which the Non-Goals section leaves open as "a formatter change behind the same entry point" — would break silently under any `dictConfig` call. Recorded here so that future change knows it is not merely a formatter change.

**Entrypoints that exist today**: `commerce_ops.main` (under uvicorn) and `commerce_ops.preflight` (a plain `python -m` in the Dockerfile's `CMD` chain, running before uvicorn exists at all). The scheduler change will add a third that uvicorn never hosts.

The same `CMD` chain also runs `alembic upgrade head`, whose `alembic/env.py` calls `fileConfig(...)` and configures root in **its own process**, with `disable_existing_loggers` defaulting to `True`. That process is out of scope here: separate process, separate ini-driven configuration, no interference either way. Noted because "nothing in this repository configures logging" is true of `src/` and not of the repository as a whole.

**Constraint from `runtime-configuration`**: "Importing And Starting The Application Do Not Require Configuration To Be Present." Two existing regression guards enforce it — `test_main_slack_wiring.py` and `test_main_monitoring_wiring.py` each import `commerce_ops.main` in a fresh interpreter with required variables removed. Anything this change adds to import or startup must survive an empty environment.

## Goals / Non-Goals

**Goals:**

- Application records are emitted and formatted from every entrypoint, including ones uvicorn does not host.
- Third-party library records at `WARNING` and above are formatted too, rather than falling through to `lastResort` unformatted.
- The threshold is settable for the deployment without an application code change, and actually reaches the running container.

**Non-Goals:**

- **Structured (JSON) log output.** Nothing consumes these logs programmatically — there is no aggregator, no log query layer, and the reader is a person running `docker logs`. Human-readable lines are the better format for that reader, and switching later is a formatter change behind the same entry point, not a redesign. Revisit when something actually queries logs.
- **Log rotation.** Docker's `json-file` driver runs with no `max-size` on this host, so container logs grow unbounded. That is host-wide configuration affecting every container on a shared server, and belongs in the separate `/infrastructure` repository's `docker_daemon_options`, not in this application. Named in proposal.md — Impact so the log-volume increase is a known consequence.
- **Request-level correlation ids / structured context.** Worth having once there is a worker and a scheduler putting concurrent work through the same log stream; premature while the only writer is a single request handler.
- **Changing any existing log call site.** Making them visible is the point; rewording them is not.

## Decisions

### Attach the handler to the root logger, not to the `commerce_ops` logger

The narrower option — configure only the `commerce_ops` hierarchy — was the first instinct, because it obviously cannot disturb uvicorn. But it leaves every third-party library exactly where the application is today: `slack_bolt`, `sqlalchemy`, `httpx` and `langchain` records still land on a handler-less root, still get `lastResort`, still arrive at `WARNING` with no timestamp. A SQLAlchemy pool warning or a Bolt middleware error is precisely the kind of record worth having formatted and timestamped.

Fact 2 above removes the reason to avoid root: uvicorn's loggers do not propagate, so a root handler cannot duplicate them. The concern that motivated the narrow option does not exist in this process.

**Alternative considered — `logging.basicConfig()`**: it does attach a formatted handler to root, and would be one line. Rejected because it is silently a no-op when root already has a handler, which makes the "configured more than once" requirement depend on an implicit behavior rather than an explicit guard, and because it offers no way to set the two levels independently, which the next decision needs.

### Set root's level to `WARNING` and the `commerce_ops` logger's level to the configured threshold

Setting root's level to the configured threshold (`INFO` by default) would turn on `INFO` for every installed library at once — `httpx` logs a line per request, and the OpenAI and LangChain clients are chattier still. The result would be an application whose own records are buried in library noise, which is a different failure of the same goal.

Python's propagation semantics let both be had at once: **only the originating logger's effective level gates a record**; ancestor loggers' levels are not consulted once the record is created, though ancestor *handlers* are. So:

- `commerce_ops` logger at the configured threshold → application records at `INFO` are created and propagate to root's handler, which emits them.
- root at `WARNING` → an `httpx` record at `INFO` is never created, while an `httpx` record at `WARNING` is, and reaches the same formatted handler.

The handler itself carries no level (`NOTSET`), so it emits everything that reaches it and the two logger levels are the only gates.

**Alternative considered — root at the threshold plus an explicit `WARNING` override list for known-chatty libraries.** Rejected: the list is a maintenance burden that must be updated whenever a dependency is added, and it fails open — a newly added chatty library floods the logs until someone notices and adds it. The chosen split fails closed **for any library that sets no level of its own**, which is the common case: such a library is quiet at `INFO` until someone deliberately turns it up.

**The qualifier matters and was missing from an earlier draft.** By the same propagation rule this design relies on, a library that sets *its own* logger's level to `INFO` and attaches no handler has every such record created and propagated to the root handler, which sits at `NOTSET` and emits whatever reaches it. Root's `WARNING` never gates it. So the "fails closed" property covers unconfigured loggers only.

**The installed dependencies were then checked, rather than left to assertion.** After importing `commerce_ops.main`, measured directly:

| logger | own level | effective |
|---|---|---|
| `sqlalchemy` | `WARNING` | `WARNING` |
| `slack_bolt` (parent) | `NOTSET` | `WARNING` |
| `slack_bolt.AsyncApp` and middleware | copied from root at construction | `WARNING` |
| `httpx` | `NOTSET` | `WARNING` |
| `langchain_core`, `openai` | `NOTSET` | `WARNING` |

So the log-volume estimate stands — every one of them is quiet at informational level — but by **three** different mechanisms, only one of which is the design's:

- `httpx`, `openai`, `langchain_core` set nothing and are genuinely root-gated. This is the design's mechanism.
- `sqlalchemy` sets its own logger to `WARNING` at import (`sqlalchemy/log.py`), so it would stay quiet even if root did not gate it.
- `slack_bolt` emits on `slack_bolt.<ClassName>` children, and `_configure_from_root` copies `logging.root.level` onto them **at construction**. The parent name reads `NOTSET`, which is misleading. The copy is one-shot, so a future change that lowered root's level would turn on Bolt `INFO` output — and re-raising root afterwards would not undo it.

Only the first group is protected by the two-gate split. The other two happen to agree with it today.

Note also that no top-level `langchain` package is installed at all — the tree has `langchain_core` and `langchain_openai` — so any check written against the name `langchain` would silently create a fresh `NOTSET` logger and verify nothing.

**This is recorded here rather than asserted in a test.** An earlier draft added a unit test asserting these loggers were at `NOTSET`; it would have been red on its first run against `sqlalchemy`, blocking every commit through the pre-commit hook, and for two of the four names it would have passed while checking nothing. Facts about third-party internals belong in a design record, where a dependency bump makes them stale rather than red.

### Read `LOG_LEVEL` directly from the environment, and declare it in the settings model as optional

`get_settings()` raises `ValidationError` when any required variable is absent, and `configure_logging()` is called at `main.py`'s **module import**. `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" requires that import to succeed with the environment empty, and two fresh-interpreter guards enforce it by running `python -c "import commerce_ops.main"` with required variables removed. Routing the threshold through `get_settings()` would break both.

(An earlier draft justified this by saying `preflight.py` "needs working logging to report that its configuration is broken." That is not so, and task 3.3 forbids it: preflight emits no log record at all — its report is `print` to stderr, whose wording `deploy-pipeline` depends on. Preflight is a secondary beneficiary of a configured stream, not the reason for the direct read.)

This is the pattern `trigger_guard.py` already establishes and `settings.py`'s own module docstring describes: read directly where tolerance of absence is required behavior, declare it in the model regardless so the drift test still sees it and the startup report still names it. `LOG_LEVEL` is declared optional, so `runtime-configuration`'s "An optional variable's absence is not a fault" covers it with no change to that capability.

### An unrecognized `LOG_LEVEL` falls back to the default rather than failing

A typo in an operator-set variable (`LOG_LEVEl=DEBGU`) must not be able to take the deployment down, and must not silently leave logging unconfigured either — that would reintroduce the exact defect this change fixes, in the one situation where someone was actively trying to adjust logging. Falling back to `INFO` and reporting the bad value keeps both the application and its logging working while making the mistake visible.

Reporting it is deliberately done through the logging that was just configured, not through `print`, so it lands in the same stream as everything else.

### Configuration is idempotent, guarded by an explicit check

`main.py` and `preflight.py` can both run in one process (the Dockerfile chains them as separate processes today, but nothing guarantees that stays true, and tests import both). Adding a second handler to root would emit every record twice. The entry point therefore checks for its own previously-installed handler and returns early, rather than relying on `basicConfig`'s implicit no-op.

### Deliver `LOG_LEVEL` through `deploy.yml`'s `.env` render step

The container's environment comes entirely from a `.env` that `deploy.yml` renders fresh on every deploy from a fixed list of `echo` lines, delivers over SSH, and extracts over the host's copy. A variable absent from that list can never hold a value in the deployment: setting it by hand on the host survives only until the next merge to `main`, then vanishes without a trace. So the render step gains a line, or the configurability is fictional.

The line uses a literal fallback — the rendered value is the repository variable **or** `INFO` — rather than interpolating the variable bare. An unset repository variable would otherwise render `LOG_LEVEL=` (present but empty), which the settings model's `NonEmpty` type reports as a faulting variable on **every** deploy, turning an unset optional knob into a permanent startup warning. The fallback makes the common case render a valid value.

The expression form is `${{ vars.LOG_LEVEL || 'INFO' }}` — a repository/Environment **variable**, not a secret, unlike every other line in that step, because the threshold is not sensitive and a secret would be masked in logs for no reason. GitHub expressions treat `''` as falsy, so the one form covers both the unset and the empty-string cases. No such variable exists today; the deploy renders `INFO` until someone creates one.

**Empty deserves a straight answer, because two mechanisms see it.** The spec defines empty as "treated as not configured", so `configure_logging()` uses `INFO` and makes no unrecognized-value report. The settings model declares `log_level` as `NonEmpty | None`, so an empty value *is* a validation fault, and `preflight` would name `LOG_LEVEL` among faulting variables while logging behaved perfectly.

Those are not the same account, and the fix is to make the declaration agree with the spec rather than to write around the difference: `log_level` is declared **`str | None = None`**, not `NonEmpty | None`. Empty then parses as a value, no fault is reported, and both mechanisms read empty as "not configured". `NonEmpty` exists to catch a rendered-but-empty *required* secret, where absence is a real fault; an optional threshold with a safe default is the case it was not written for. The `deploy.yml` fallback stays regardless — it stops the state arising through the pipeline at all; the declaration handles the hand-edited `.env` the fallback cannot reach.

### Call it at module import in `main.py`, not in a lifespan hook

`main.py` is imported before the lifespan runs; records emitted during its own module body — and any emitted later by anything it wires up — would be lost if configuration waited for startup. The call reads at most one environment variable, has a default for it, and touches no external service, so it satisfies the empty-environment constraint the two `main`-import regression guards enforce.

**A precise claim, since an imprecise one invites a wrong "fix":** the call sits after `main.py`'s own imports, so module-level records emitted *by the adapter modules themselves during their import* are still not covered. Nothing emits one today (`slack_app.py`'s `warning` is inside a function body), so this costs nothing now. Moving the call above the imports to close that gap would trip ruff's `E402`, and the project takes ruff's default selection — so the placement is a deliberate trade, not an oversight.

### Placement: `shared/infrastructure/logging.py`

Logging configuration is an infrastructure concern, and `shared` is the Shared Kernel every module's infrastructure layer may already reach. `main.py` and `preflight.py` both sit outside the three `.importlinter` containers (as `preflight.py`'s docstring records), so both may import it freely. The module is named `logging.py`, which does not shadow the standard library's: absolute imports are Python 3's default, so `import logging` inside `commerce_ops.shared.infrastructure.*` resolves to the stdlib regardless of a sibling of that name. (An earlier draft credited `from __future__ import annotations` for this; that import governs annotation evaluation and has nothing to do with import resolution.)

## Risks / Trade-offs

- **Root-level configuration is process-global; a future dependency could reconfigure it and undo this.** → Uvicorn is the only in-process `dictConfig` caller in the application's own processes, and fact 3 establishes the handler survives it — but on the narrow grounds that a `StreamHandler`'s `close()` is a no-op, not because root is unnamed. A regression test asserts an application record still reaches the stream after uvicorn's configuration is applied, in **both** orders: the production order under the uvicorn CLI is uvicorn-configures-then-app-imports, while a test that imports first exercises the reverse. Covering both costs one extra assertion and is what makes the guarantee real rather than order-dependent.
- **Configuring logging at import makes the whole pytest process carry a root handler**, since several unit modules import `commerce_ops.main` at module level. Combined with the idempotency guard, a later test that re-configures at a different threshold would silently assert against the configuration installed at collection time. → The new tests own a fixture that detaches the sentinel handler and restores both levels around each test, and `configure_logging()` exposes a reset seam for it rather than having tests reach into module internals. Without this the threshold tests would pass for the wrong reason, which is worse than failing.
- **Third-party `WARNING` records now appear that previously did too, but unformatted — volume is unchanged; application `INFO` records are genuinely new volume.** → Accepted, and the point of the change. Log growth on an unrotated host is named in proposal.md — Impact and belongs to `/infrastructure`.
- **`LOG_LEVEL=DEBUG` in production would be very loud, including SQLAlchemy statement logging if root were also lowered.** → Root stays at `WARNING` regardless of `LOG_LEVEL`, by the second decision, so `DEBUG` turns up the application's own records only. A library's debug output still requires a deliberate, separate change.
- **Records emitted before the configuration call in a given process are still lost.** → The call sites are the first statements of each entrypoint, so the window is the import of `logging` itself. Not eliminable without an import hook, and not worth one.

## Migration Plan

No migration. The change adds a module and three call sites; there is no data, no schema, and no external contract involved. Rollback is reverting the commit — the previous behavior (records discarded) returns, which is not a broken state, only a blind one.

Deploy verification: after the deploy, `docker logs` on the app container shows formatted, timestamped lines.

For the informational record specifically — the line that has never appeared in production and whose appearance is the change working end to end — the cadence matters. **The 06:00 job is `daily`, which calls `run_daily_digest` and never touches `pending_cadence.py`.** The `INFO` record comes from the four *unimplemented* cadences: weekly (Mondays 07:00), biweekly, monthly, quarterly. Waiting for Monday leaves the change unverified in production for up to a week, so the verification issues the weekly trigger by hand after the deploy, using the deployed `TRIGGER_SECRET`. That exercises the same code path within minutes. It does not prove cron's own scheduling, which this change does not touch and which `add-product-agent-daily-digest` already covers.
