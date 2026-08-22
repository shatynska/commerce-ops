## Why

The application configures no logging at all, so most of what it writes to its logs is silently discarded.

Nothing in `src/` calls `logging.basicConfig`, `logging.config.dictConfig`, or otherwise attaches a handler to the root logger. Uvicorn configures its own `uvicorn`, `uvicorn.error` and `uvicorn.access` loggers, but never the root logger, so every `commerce_ops.*` record propagates to a handler-less root and falls through to `logging.lastResort` — a bare `StreamHandler` fixed at `WARNING`, with no formatter.

Two consequences are live in production today:

- **`INFO` and `DEBUG` records are dropped entirely.** `products/application/pending_cadence.py` logs each no-op cadence trigger at `INFO`, and its own docstring claims this makes the trigger "read in logs as 'not built yet,' not as a silent failure." It does not — that line has never reached a log. Four of the five scheduled cadences fire into complete silence.
- **The records that do survive carry no context.** `lastResort` has no formatter, so the surviving records arrive with no timestamp, no level and no logger name, and cannot be placed in time or attributed to a module. This affects at least `products/infrastructure/driving/monitoring.py`'s two `exception` calls and `shared/infrastructure/driving/slack_app.py`'s `warning` and two `exception` calls; the list is illustrative, not exhaustive.

This is worth fixing before the scheduler work rather than after. That change's value is run visibility — retries, run history, and an alert when an expected run never lands — and every part of it reports through the same logging path that currently discards `INFO`.

## What Changes

- **The application configures its own logging** from a single entry point, rather than inheriting whatever the process happens to have.
- **The formatting handler attaches to the root logger**, so records from the application *and* from its dependencies are formatted with a timestamp, level, logger name and message on the process's standard error. Attaching to root is safe here for a verified reason: uvicorn's own loggers set `propagate: false` and carry their own handlers, so no uvicorn record ever reaches root and none can be duplicated.
- **Two levels are set, not one.** The `commerce_ops` logger is set to the configured threshold, and the **root** logger to `WARNING`. Python gates a record on the originating logger's effective level only, so this emits the application's own `INFO` records while leaving chatty dependencies (`httpx`, the OpenAI and LangChain clients) quiet at `INFO` — and still formatting their `WARNING`s and errors. A single level could not do both.
- **The threshold is configurable and defaults to `INFO`**, via a new optional `LOG_LEVEL` environment variable, declared in the existing settings model and **rendered into the deployed `.env` by `deploy.yml`** so it can actually hold a value in production. A changed value reaches the container on the next deploy, not immediately.
- **Configuration is applied at every entrypoint the application starts through**, not only the HTTP one. `main.py` and `preflight.py` are both entrypoints today, and the scheduler work will add a worker process uvicorn never hosts.
- **Uvicorn's own request logging is untouched** — neither silenced nor emitted twice.
- **No existing log call site changes.** Making them visible is the entire point.

## Capabilities

### New Capabilities
- `application-logging`: emitting log records at a configurable threshold, formatted with enough context to place a record in time and attribute it to a module, from every entrypoint the application starts through — governing the application's own records directly and its dependencies' records at a fixed, separate threshold, independently of whichever server or runner happens to host the process.

### Modified Capabilities

(none. Two capabilities were considered:

- `runtime-configuration` — its existing requirements already govern `LOG_LEVEL`. It is declared optional, and that capability's "An optional variable's absence is not a fault" scenario covers its absence, so no requirement changes.
- `deploy-pipeline` — this change edits `.github/workflows/deploy.yml`, which that capability governs. Its requirements constrain the rendered file to carry the image tag and the runtime secrets — a floor, not an enumeration — so adding a non-secret line falsifies nothing. (A future edit that *removed* a line would be a different matter.) Named explicitly so it is visible that it was checked rather than overlooked.)

## Impact

- **New**: `src/commerce_ops/shared/infrastructure/logging.py`, holding the configuration entry point, and unit tests at `tests/unit/shared/infrastructure/`.
- **Modified**: `src/commerce_ops/main.py` and `src/commerce_ops/preflight.py` each call it; `src/commerce_ops/shared/application/settings.py` declares `log_level` as optional; **`.github/workflows/deploy.yml`** gains a `LOG_LEVEL` line in its `.env` render step, with a literal fallback so an unset repository variable renders `INFO` rather than an empty one. The fallback stops that state arising through the pipeline at all; an empty value from a hand-edited `.env` is handled by the declaration itself, which is why `log_level` is declared `str | None` rather than `NonEmpty | None`.
- **`tests/unit/shared/application/test_settings.py` must be updated.** It asserts `set(_declared_fields()) == set(ALL_DECLARED)` and `set(declared) - actually_required == set(OPTIONAL)` against hardcoded transcriptions of the declared set. Adding an optional `log_level` field fails both, and the pre-commit hook runs the whole unit tier, so this blocks every commit of the change until handled. This is a required edit, not a side effect.
- **`LOG_LEVEL` is read directly rather than through `get_settings()`**, and declared in the settings model as well. `configure_logging()` is called at `main.py`'s module import, where `get_settings()` would raise if any required variable were absent — which `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" forbids and two fresh-interpreter guards enforce. The drift test requires every variable the source reads to be declared, so the declaration is needed regardless of how it is read.
- **No new dependency.** The standard library's `logging` module suffices; structured/JSON output is deliberately out of scope (see design.md).
- **Behavior visible in the deployment**: container logs gain the application's `INFO` records and its dependencies' formatted `WARNING`s, which the boot disk holds unrotated — Docker's `json-file` driver is configured with no `max-size` anywhere on this host. That is a pre-existing condition this change makes slightly more visible, and it belongs to host configuration in the separate `/infrastructure` repository, not here. Named so the increase in log volume is a known consequence rather than a discovered one.
