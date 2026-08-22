## 1. Direction record

- [x] 1.1 Revise `README.md`'s Scope section inside the `ai-toolkit:project-foundation` block: name Product Launch as the MVP subdomain and first deliverable. Launch is **not** one of the four domains currently listed and does not replace one — it cuts across listing/catalog management and analytics. Keep all four domains as the surrounding scope, sequenced behind Launch (see design.md, Decisions/Direction)
- [x] 1.2 In the same section, record that further subdomains — customer support among them — follow after, and are not yet specified in any detail
- [x] 1.3 Revise `README.md`'s Scope section to record that marketplace integration is deferred pending external access being granted — the Amazon-first, adapter-based direction is unchanged, but no marketplace adapter is built and no change is sequenced as depending on one until then
- [x] 1.4 Revise `README.md`'s Technology section: `pydantic-settings` for configuration, and LangGraph's scope narrowed to interpretation, generation and conversation rather than deterministic rule evaluation. Do **not** change the Slack technology wording — the Bolt migration is a separate change and owns it
- [x] 1.5 Add to `README.md`'s Architecture section the three-way launch state ownership — the repository owns the playbook definition as versioned YAML (per `launch-playbook`'s "Playbooks are versioned"), Postgres owns each product's position and per-step completion state, ClickUp owns human completion and reports it back — including the reconciliation obligation the split carries
- [x] 1.6 Update `AGENTS.md`'s "Architecture summary" section (outside the `ai-toolkit:project-foundation` block) so it stays coherent with 1.1–1.5; do not restate the detail, it points at `README.md`

## 2. Remove external-source citations from project-authored artifacts

Substance is preserved in every case — only the pointer to the external source is removed. `docs/reference/` itself is not edited.

- [x] 2.1 `src/commerce_ops/products/domain/launch_playbook.py`, module docstring: keep the timing-anchor convention and the one-day-drift warning in full — it documents a real, invisible-by-inspection defect — but state the offset convention on its own terms instead of as a contrast with an external numbering scheme
- [x] 2.1a Same docstring, line 17: it points at "`design.md`'s transcription table" for the full mapping, and that `design.md` lives in the archive task 2.7 freezes. State the mapping in full in the docstring itself so the complete statement lives in the code, then drop the pointer (design.md, Risks)
- [x] 2.2 `src/commerce_ops/products/domain/launch_playbook.py`, `Track` docstring: drop the attribution of the twelve disciplines to an external column; the closed set and the reason it is a weaker closure than the gate sequence both stay
- [x] 2.3 `src/commerce_ops/products/infrastructure/driven/playbook_v1.yaml`, header comment: reword the note that step definitions are a follow-up change without citing an external item count, and drop its pointer to the archived `design.md`'s "Ship gates only" for the same reason as 2.1a
- [x] 2.4 `tests/unit/products/domain/test_launch_playbook.py`: reword docstring citations of the external source, including the item count at line 865. Assertions are not to change — comment-only edit, and every test must pass with its behavior unmodified
- [x] 2.4a `tests/unit/products/infrastructure/test_playbook_loader.py`: same treatment — its docstrings carry the external item count at lines 268 and 293. Comment-only; `test_shipped_playbook_ships_with_no_step_definitions`'s assertion is unaffected
- [x] 2.5 Re-run the repo-wide search — including the external item count as a search term, which an earlier sweep omitted and which is how 2.4a's file was missed — and confirm no project-authored file outside `docs/reference/` cites those documents
- [x] 2.6 Leave `openspec/specs/launch-playbook/spec.md` unchanged, on two points task 2.5's sweep will surface:
  - its "Provenance references are never identifiers" requirement describes the `provenance` field as a citation into source material generically
  - line 55's "matching the ownership boundaries the source material already uses" — the same attribution task 2.2 removes from `Track`'s docstring
  Neither names an external document, and altering a main spec requires a MODIFIED delta this change deliberately does not carry. Recorded here so the sweep does not become an ad-hoc judgment call mid-edit
- [x] 2.7 Leave `openspec/changes/archive/2026-08-21-add-launch-playbook/` unchanged — see design.md, "Archived changes are not rewritten"

## 3. Dependency

- [x] 3.1 Add `pydantic-settings` to `pyproject.toml`'s `dependencies` and run `uv sync` (FastAPI already pins pydantic v2, so no new major version enters the resolution)

## 4. The settings declaration

- [x] 4.1 Add `shared/application/settings.py` with a `pydantic-settings` model declaring every variable the application's **runtime requires** — not only those its own source reads (design.md, "The declaration governs what the runtime requires"):
  - required **and startup-critical**: `DATABASE_URL`
  - required: `OPENAI_API_KEY`, `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_MONITORING_CHANNEL_ID`, `TRIGGER_SECRET`
  - optional: `PRODUCT_AGENT_SLACK_SIGNING_SECRET`, `CLICKUP_API_TOKEN`
  Startup-critical is a marking **on top of** required, not a third peer status — `DATABASE_URL` is both.
  Do **not** declare `POSTGRES_PASSWORD`: it is consumed by `docker-compose.yml`'s substitution and the `postgres` service, never by the application process
- [x] 4.2 Configure the model to read the process environment and an optional `.env`; treat an empty string for a non-optional variable as faulting; and **ignore unrecognized keys** (`extra="ignore"`). This matters for local development, not the container: the image copies no `.env` and Compose mounts none, delivering those values as process environment instead — but a developer holding a copy of the rendered `.env` has `IMAGE_TAG` and `POSTGRES_PASSWORD` in it, neither a model field, and the strict default would report both as faults
- [x] 4.2a Type `DATABASE_URL` so a scheme the application cannot connect with (anything other than `postgresql+asyncpg`) is reported as unparseable. Every other declared variable is an opaque credential or id, so presence is all that is meaningful for them (design.md, "`DATABASE_URL` is typed")
- [x] 4.3 Expose a cached accessor that constructs the model on first call, never at import time
- [x] 4.4 Export the model and accessor from `shared/application/__init__.py`'s `__all__`
- [x] 4.5 Do **not** change `slack.py`, `monitoring.py`, `slack_notifier.py`, `trigger_guard.py` or `clickup_client.py` to read through the model. `trigger_guard.py` in particular must keep its `os.environ.get` read, or `internal-trigger`'s "Guard Fails Closed When Unconfigured" and its two tests at `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py` break (design.md, "The model is a declaration plus a startup check")

## 5. The preflight check

- [x] 5.1 Add a preflight entry point at `src/commerce_ops/preflight.py` — alongside `main.py`, outside the three layered containers `.importlinter` defines, so importing `shared.application.settings` from it violates no contract. It reads the configuration, writes every faulting variable's name to stderr, and exits non-zero only if a startup-critical variable is faulting; a non-critical fault is reported and exits zero
- [x] 5.2 Insert it into the `Dockerfile`'s `CMD` chain ahead of `alembic upgrade head`
- [x] 5.3 Update the `CMD`'s existing comment to cover both gates (configuration check, then migration) rather than only the migration

## 6. The drift test

The two directions are deliberately **not** symmetric — see design.md, "A drift test with a reasoned exemption table". A naive set-equality assertion is red the day it is written, because `OPENAI_API_KEY` is read by `langchain_openai` and `PRODUCT_AGENT_SLACK_SIGNING_SECRET` is read nowhere yet.

- [x] 6.1 Add an exemption table beside the settings model: declared variables the application's own source does not read, each with a stated reason naming its consumer. Seed it with `OPENAI_API_KEY` ("read by `langchain_openai.ChatOpenAI`, constructed in `omni_agent/application/graph.py`") and `PRODUCT_AGENT_SLACK_SIGNING_SECRET` ("registered `production` secret; consumer lands with `add-product-creation-clickup-task`")
- [x] 6.2 Add a unit test asserting, in this direction with **no** exemption possible: every environment variable name the application source reads is declared in the model
- [x] 6.3 Add a unit test asserting, in the other direction: every declared variable is either read by the source or present in the exemption table
- [x] 6.4 Add a unit test asserting every exemption-table entry carries a non-empty reason, so the table cannot become a place to hide omissions
- [x] 6.5 Scope the scan to `src/commerce_ops/` **and `alembic/`** — both run inside the same container, and `alembic/env.py:24` reads `DATABASE_URL` — and to the idiom family in use: `os.environ[...]`, `os.environ.get(...)` and `os.getenv(...)`. `os.getenv` is unused today but is the same family, not a future diversification, and costs nothing to include. Exclude the settings module and the preflight entry point themselves
- [x] 6.6 Confirm against the current tree that 6.2 and 6.3 both pass: the scanned tree reads exactly `PRODUCT_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_MONITORING_CHANNEL_ID`, `DATABASE_URL` (in both `monitoring.py` and `alembic/env.py`), `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN`, `TRIGGER_SECRET`, `CLICKUP_API_TOKEN` — seven distinct names, all declared; the two declared-but-unread are exactly the seeded exemptions

## 7. Scenario tests

Sections 4–6 name the implementation tasks. The scenario-level tests for `runtime-configuration`'s requirements — multiple faults reported together, present-but-empty, unparseable `DATABASE_URL`, optional absence not a fault, unrecognized keys ignored, no network access during a check, and import/startup with an empty environment — are derived from the delta spec by `openspec-test-writer` before implementation, per `AGENTS.md`'s test-design binding. Recorded here so their absence from sections 4–6 is a workflow step rather than an omission.

- [x] 7.0 Confirm the derived tests cover every scenario in `specs/runtime-configuration/spec.md`
- [x] 7.1 Account for the `deploy-pipeline` delta's four scenarios explicitly: its first three are exercised by 8.6–8.8 below, which are bare `docker run` invocations. Its fourth — "A startup-critical fault leaves the deploy failed" — is **not** exercised by those, since they are not deploys. Record it as resting on the existing `deploy-pipeline` requirement "Deploy Is Verified by Checking the Health Endpoint" plus `restart: unless-stopped`, or add a task that exercises it. Do not leave it claimed as covered when it is not

## 8. Verification

- [x] 8.1 Confirm `tests/unit/omni_agent/infrastructure/driving/test_main_slack_wiring.py` and `tests/unit/products/infrastructure/driving/test_main_monitoring_wiring.py` pass **unmodified** — each deletes three named variables and requires import, lifespan and `/health` to succeed
- [x] 8.2 Confirm `tests/unit/shared/infrastructure/driving/test_internal_trigger_guard.py` passes unmodified — specifically its fail-closed-when-unconfigured cases
- [x] 8.3 Cross-check the model against the deployment **in both directions**, one variable at a time — this correspondence is the mechanism's purpose and is verified, not assumed:
  - declared → delivered: every required and startup-critical field is rendered by `deploy.yml`'s "Render .env" step or set by `docker-compose.yml`'s `environment:` block
  - delivered → declared: every line `deploy.yml` renders, and every key the **`app` and `cron` services** set, is either a declared variable or a named deployment-only variable (`IMAGE_TAG`, `POSTGRES_PASSWORD`). This is the direction that catches an `OPENAI_API_KEY`-class omission — a variable the deploy delivers and the model does not know about, which no drift test can see.
    Scope it to those two services deliberately: the `postgres` service sets `POSTGRES_USER` and `POSTGRES_DB` as literals (`docker-compose.yml:34,36`), which the application process never receives and must not be declared
- [x] 8.4 Run `uv run pytest`, `uv run mypy .`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports --config .importlinter`
- [x] 8.5 Run `openspec validate revise-foundation-for-launch-mvp --strict`
- [x] 8.6 Build the image and start it with `DATABASE_URL` absent; confirm startup fails, every faulting variable is named, and no migration runs. This must be run with a bare `docker run`, **not** through `docker-compose.yml` — its `app` service always sets `DATABASE_URL` in its `environment:` block, so the fault is unreachable that way (design.md, "The `DATABASE_URL` abort path is unreachable through this project's own Compose file")
- [x] 8.7 Start it with `DATABASE_URL` present but `PRODUCT_AGENT_MONITORING_CHANNEL_ID` absent; confirm the fault is reported, the migration runs, and `/health` serves — the capability-scoped-degradation behavior this change chose over a full outage
- [x] 8.8 Verify `extra="ignore"` at **unit level**, over a dotenv fixture containing `IMAGE_TAG` and `POSTGRES_PASSWORD`, not at container level — the image copies no `.env` and Compose mounts none, so a container never sees a dotenv file at all and the precondition cannot be created there (task 4.2)
