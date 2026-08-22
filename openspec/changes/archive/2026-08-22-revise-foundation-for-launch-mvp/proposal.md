## Why

Seven changes in, the project has a working deploy pipeline and three module skeletons, but its recorded foundation and its code have drifted apart in two ways that get more expensive to correct with every change built on top of them.

**The direction is not recorded anywhere.** `README.md`'s Scope section lists four domains with no ordering between them, which reads as though all four are concurrent work. They are not. The near-term target is **Product Launch**, delivered through Slack and ClickUp — the one subdomain that can be built to completion with the integrations available today. Marketplace access is being obtained externally and is not available to build against, which blocks every part of the recorded scope that reads marketplace data. Further subdomains, customer support among them, follow after. Without that ordering recorded, every subsequent proposal has to re-derive it, and the two proposed most recently both did.

**Configuration is scattered and fails late.** Seven environment variables are read via `os.environ[...]` across five modules, each behind its own `functools.lru_cache` factory. There is no single declaration of what the application requires to run. A variable that is registered as a GitHub Actions secret but never added to `deploy.yml`'s "Render .env" step reaches nothing, and the first symptom is a `KeyError` inside a cron-fired handler at 06:00, where nothing is watching. `add-product-agent-daily-digest` already left exactly this gap on the record for `PRODUCT_AGENT_SLACK_SIGNING_SECRET`, which is registered as a `production` secret, absent from the render step, and consumed by nothing.

## What Changes

- **`README.md`'s foundation block is revised** to record: Product Launch as the MVP subdomain, with the existing scope sequenced behind it; marketplace integration explicitly deferred pending external access; the ownership split between the repository, Postgres and ClickUp for launch state; and LangGraph's scope narrowed to the surfaces that genuinely need a language model.
- **A typed settings object declares the application's configuration in one place.** One `pydantic-settings` model in `shared/application/` names every environment variable the application's **runtime** requires — whether its own source reads it, or a dependency reads it on its behalf — with the variable's type, whether it is required or optional, and whether it is startup-critical. Variables the deployment consumes but the application process never receives, such as `POSTGRES_PASSWORD`, are outside it.
- **Configuration faults are detected and reported before the container serves traffic**, by a preflight step in the Dockerfile's start command ahead of the existing `alembic upgrade head`. Every faulting variable is named at once. A fault in a **startup-critical** variable aborts startup; any other fault is reported loudly and the application still serves, so one missing channel id degrades one capability instead of taking the deployment down.
- **A drift test keeps the declaration honest**, asymmetrically: every variable the codebase reads must be declared, with no exemption; every declared variable must either be read by the codebase or carry a recorded reason naming what consumes it instead. A plain set-equality assertion would be false against the current tree — `OPENAI_API_KEY` is required and read only inside `langchain_openai`.
- **Project-authored artifacts stop citing the external documents under `docs/reference/`.** `launch_playbook.py`, `playbook_v1.yaml` and `test_launch_playbook.py` are reworded so the project's decisions stand on their own terms. Comment-and-docstring edits only; no assertion, value or behavior changes, and `docs/reference/` itself is not edited.

## Capabilities

### New Capabilities
- `runtime-configuration`: declaring, in one place, every environment variable the application's runtime requires — whether its own source reads it, or a dependency reads it on its behalf; detecting an incomplete or malformed configuration and reporting every fault at once; and distinguishing a fault that must prevent startup from one that must not.

### Modified Capabilities
- `deploy-pipeline`: gains a requirement that the container check its runtime configuration before migrating and before serving, alongside the existing migration-before-serving requirement.

## Impact

- `pyproject.toml`: adds `pydantic-settings`.
- New: `shared/application/settings.py`, a preflight entry point at `src/commerce_ops/preflight.py` (alongside `main.py`, outside the three containers `.importlinter` layers, so it may import the settings model freely), and a drift test.
- Modified: `Dockerfile`, `README.md`, `AGENTS.md`'s Architecture summary, and comment text in `launch_playbook.py`, `playbook_v1.yaml`, `test_launch_playbook.py` and `test_playbook_loader.py`.
- **Existing regression guards constrain the implementation.** `tests/unit/omni_agent/.../test_main_slack_wiring.py` and `tests/unit/products/.../test_main_monitoring_wiring.py` each run `commerce_ops.main` in a fresh interpreter, and run its lifespan and `/health`, with three named variables removed — `OMNI_AGENT_SLACK_SIGNING_SECRET`/`OMNI_AGENT_SLACK_BOT_TOKEN`/`OPENAI_API_KEY` and `TRIGGER_SECRET`/`PRODUCT_AGENT_SLACK_BOT_TOKEN`/`DATABASE_URL` respectively. Those sets intersect the model's declared variables, so settings loading must stay lazy and validation must live in the preflight step rather than in a lifespan hook. Neither file is modified.
- **`internal-trigger`'s "Guard Fails Closed When Unconfigured" requirement is preserved.** `trigger_guard.py` reads `TRIGGER_SECRET` with `os.environ.get` and returns 401 when it is absent. This change does **not** route that read through a validating accessor, which would raise instead of returning 401 and break both that requirement and its tests. The settings model is a declaration plus a startup check, not a replacement for per-request reads — see design.md.
- No secrets are added, removed or renamed, and no variable's runtime source changes.

### Deliberately out of scope
Named here so their absence is a decision on the record, not an oversight. Each becomes its own change:

- **The Slack Bolt migration and the async conversion of outbound Slack calls.** Originally part of this change; split out after review established that two of its load-bearing premises were false — Bolt's `token_verification_enabled=False` defers rather than removes its `auth.test` call, and `tests/unit/omni_agent/.../test_slack_events_endpoint.py` is coupled to the current adapter's internals by name, so it cannot survive the migration unmodified. Both now have verified remedies, and both need designing properly rather than being carried here. That change also inherits the obligation to revise the pending `add-product-creation-clickup-task`, whose Slack-handling decisions Bolt supersedes.
- **Migrating existing `os.environ` call sites to read through the settings model.** Doing so naively breaks `internal-trigger`'s fail-closed guard (see Impact). The drift test covers the gap this change exists to close; per-field lazy accessors that preserve per-request absence tolerance are a separate design question.
- **Amazon marketplace clients, a metric store, a threshold rule engine, report assembly and interpretation.** Blocked on marketplace access being granted, and not part of the Launch MVP.
- **Replacing the `cron` container with a job runner.** The launch playbook's timing anchors will need scheduled evaluation with retries and run history, and the current BusyBox `crond` firing `wget -O /dev/null` provides neither.
- **Loading the launch step definitions into `playbook_v1.yaml`** (it declares eight gates and zero steps), **and the ClickUp task/webhook synchronization** the ownership split calls for. Both are the substance of the Launch MVP and follow directly from this change.
