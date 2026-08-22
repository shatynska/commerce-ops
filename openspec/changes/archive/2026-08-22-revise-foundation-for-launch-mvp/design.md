## Context

See `proposal.md` for motivation. This change has two halves that share one justification: a **direction record** (what the project is building first, and what it is deliberately not building yet) and a **configuration correction** that direction makes worth doing now rather than after more surfaces are built on the current shape.

The direction half exists because nothing in the project's own artifacts records which subdomain is being built first, or what is deferred and why. `README.md`'s Scope section lists four domains with no ordering between them.

This change originally also carried a Slack Bolt migration and an async conversion of outbound Slack calls. Review established that two premises those rested on were false — see "What was split out" below. They are now a separate change, designed against verified behavior rather than assumption.

## Goals / Non-Goals

**Goals:**
- Record Product Launch as the MVP subdomain, and record what is deferred and why, in the project's own artifacts rather than in conversation.
- Record which system owns launch state, before code exists that assumes either answer.
- Give the application one declaration of the configuration its runtime requires — whether its own source reads it or a dependency reads it on its behalf — checked before it serves traffic, with every fault named at once.
- Keep that declaration from silently drifting from the reads it describes.
- Stop the project's own artifacts from citing external source documents.

**Non-Goals:**
- No change to any behavior described by an existing requirement.
- No Slack Bolt migration, no async conversion, no change to any Slack adapter.
- No migration of existing `os.environ` call sites to read through the settings model.
- No marketplace integration, metric storage, threshold evaluation, or report assembly.
- No replacement of the `cron` container.
- No launch step definitions loaded, and no ClickUp synchronization implemented — this change records the ownership decision only.
- No new environment variables, and no removal or renaming of existing ones.

## Decisions

### Direction

**Product Launch is the MVP subdomain; the rest of the recorded scope is sequenced behind it.** `README.md`'s Scope section currently lists four domains as though they were concurrent. They are not. Launch is first because it is the one subdomain that can be built to completion with the integrations available today — Slack and ClickUp — while marketplace access is being obtained externally. Customer support and the remaining subdomains follow, and are not yet specified in any detail; the module structure already accommodates them as sibling bounded contexts, so nothing about this ordering constrains them.

Launch is not one of the four domains `README.md` currently lists — it cuts across listing/catalog management and analytics rather than replacing either. The Scope section therefore gains Launch as the named first deliverable and keeps the four existing domains as the surrounding scope, sequenced behind it, rather than substituting one for another.

**Marketplace integration is deferred, not descoped.** `README.md`'s existing statement that the integration layer is marketplace-agnostic and Amazon-first stands. What is added is that no marketplace adapter is built until access is granted, and that no change should be sequenced as depending on one before then. This matters because the analytics, order-sync and monitoring portions of the recorded scope read entirely from marketplace data and are therefore entirely blocked; treating them as near-term work would produce a queue of changes that cannot be finished.

**LangGraph's scope narrows to where a language model is genuinely required.** `README.md` names LangGraph as the agent-orchestration technology without saying what belongs inside an agent, which invites "agent" to become the default unit of work. Most of the Launch subdomain's logic is deterministic: a gate opens when its blocking steps are done, a step becomes due at a fixed offset from the launch date, and `launch_playbook.py` already enforces its own coherence rules as ordinary domain code. Routing that through a language model would make it slower, costlier and non-reproducible for logic that is none of those things. A language model belongs where interpretation, generation or conversation is genuinely required: the conversational Slack surface `omni_agent` is a first slice of, and launch-side content generation. This narrows where LangGraph is used; it does not remove it, and `omni_agent` is untouched by this change.

**Launch state ownership is three-way: the repository owns the playbook definition, Postgres owns each product's position and completion state, ClickUp owns human completion.**

- The **playbook definition** — the gate sequence, step definitions, and which step belongs to which gate — stays authored in the repository as versioned YAML, loaded by `playbook_loader.py`. This is what `launch-playbook`'s "Playbooks are versioned" requirement already fixes, and nothing here changes it. An earlier draft of this decision said Postgres holds the step definitions; that contradicted the existing specification and was wrong.
- **Postgres** holds each product's position in that playbook and its recorded completion state per step — which is per-product, mutable, and has no business in a versioned definition file.
- **ClickUp** is where the ops team marks work done, as they already do, and reports completion back so gate-opening logic can evaluate against it.

The alternatives were both rejected on the same ground: neither system can do the other's job. Making Postgres the sole owner of completion requires the team to stop completing work where they complete it and complete it in Slack instead, which is a process change imposed by an implementation detail. Making ClickUp the owner of structure requires gate sequencing, blocking-step rules and timing anchors to be expressed in ClickUp's data model, which cannot express them — `launch_playbook.py` already encodes coherence rules (a `prohibited-tactic` step can never block a gate; an `automated` step must carry a rule policy) that no task tracker enforces.

The split's cost is a reconciliation obligation: webhook delivery is not guaranteed, so completion state in Postgres can silently drift from ClickUp. That is a known, bounded problem with a known remedy — a periodic reconciliation pass — and it is called out here so the follow-up change that implements synchronization inherits it explicitly rather than discovering it. **No part of this is implemented by this change**; it is recorded so that the changes which do implement it are not each re-deciding it.

**Project-authored artifacts stand on their own terms and do not cite the external documents under `docs/reference/`.** Those documents were supplied for scope orientation. Where the project's own code, comments and artifacts cite them, two problems follow: a reader is sent to a source that does not state what this project does, and the project's decisions read as inherited rather than made. Every such citation is removed, and in each case the substance it carried is kept — most importantly `launch_playbook.py`'s timing-anchor warning, which documents a one-day drift that is invisible by inspection and must survive the edit intact. `docs/reference/` itself is untouched.

**Archived changes are not rewritten.** `openspec/changes/archive/2026-08-21-add-launch-playbook/` carries eighteen such citations. An archived change records what was decided and on what basis at the time; editing it to remove the basis makes it a false record of its own reasoning, which is worse than an outdated one. Archives are historical, not load-bearing — nothing reads them to determine current behavior, and the main specs under `openspec/specs/` are the authority for that. They are left as they are.

### Configuration

**Settings live in `shared/application/`, not `shared/infrastructure/`.** `.importlinter`'s `module-layers` contract forbids an `application` layer from importing an `infrastructure` layer, and `products.application` will need configuration as launch work lands. Placing the settings model in `shared.application` makes it reachable from every module's application *and* infrastructure layer under the existing Shared Kernel rule, with no contract change. It reads `os.environ` and an optional `.env` file and performs no other I/O, which is what makes this placement defensible rather than a layering dodge.

**The model is a declaration plus a startup check — it does not replace per-request `os.environ` reads.** This is the sharpest constraint on the change, and getting it wrong breaks an existing requirement. `internal-trigger`'s "Guard Fails Closed When Unconfigured" requires `require_trigger_secret` to return 401 when `TRIGGER_SECRET` is absent, which `trigger_guard.py` implements with `os.environ.get`. Routing that read through an accessor that validates the whole model would raise instead of returning 401, failing that requirement, its two tests, and both wiring regression guards. So no call site is migrated here. The requirement in the delta spec is scoped to declaration and startup checking accordingly, and the gap that leaves — a declaration drifting from the reads it describes — is closed by a test rather than by a rule no one can satisfy.

**The declaration governs what the runtime requires, not what the source literally reads.** These are different sets, and the codebase already holds members of the difference in both directions:

- `OPENAI_API_KEY` appears in no `os.environ` call anywhere in `src/commerce_ops/`. It is read inside `langchain_openai.ChatOpenAI`, constructed at `omni_agent/application/graph.py:22`. It is nonetheless required — without it the conversational surface does not work — and `deploy.yml` renders it.
- `PRODUCT_AGENT_SLACK_SIGNING_SECRET` is read nowhere in the repository at all. It is a registered `production` secret awaiting its consumer.
- `POSTGRES_PASSWORD` is rendered by the deploy and read by `docker-compose.yml`'s own substitution and by the `postgres` service, never by the application process.

So the declared set is "what the application's runtime requires, whether its own source reads it or a dependency reads it on its behalf", and deployment-only variables like `POSTGRES_PASSWORD` are explicitly outside it — the application cannot check what it never receives. An earlier draft scoped the requirement to "every environment variable the application reads", which would have made two of its own declared variables spec violations.

**A drift test with a reasoned exemption table, not a convention.** The value of a single declaration is that it is complete; a declaration that silently omits a variable is worse than none, because it is trusted. So completeness is asserted mechanically, in two directions that are deliberately not symmetric:

- **Every variable the source reads must be declared.** No exemption is possible here — a direct `os.environ` read that the model does not know about is exactly the drift being prevented.
- **Every declared variable must either be read by the source or carry a recorded exemption naming its consumer.** `OPENAI_API_KEY`'s exemption names `langchain_openai`; `PRODUCT_AGENT_SLACK_SIGNING_SECRET`'s records that its consumer has not landed yet. An exemption with no stated reason fails the test.

The asymmetry is the point. Without the exemption table the test is red the day it is written; with an unreasoned exemption list it becomes a place to hide omissions. Requiring a named consumer keeps each entry a reviewable line, and makes the anticipated-but-unwired state of `PRODUCT_AGENT_SLACK_SIGNING_SECRET` visible in the codebase instead of only on a GitHub secrets page — which is the gap `proposal.md` opens with.

The known limit: a dependency that reads its own variable is invisible to a source scan, so a *new* `OPENAI_API_KEY`-shaped variable would not be caught. The test's failure mode is a false pass, not a false failure, and the exemption table is where that class of variable is recorded once someone knows about it.

**Startup-critical faults abort; every other fault is reported and startup continues.** An earlier draft aborted startup on any missing required variable, justified by the claim that `docker compose up -d --wait` "leaves the previous container running". It does not: the service is recreated at the new image tag, and `restart: unless-stopped` turns a failing preflight into a crash loop with the previous container already gone. So aborting on any fault converts "one capability fails at first use" into "the whole deployment is down" — a missing `PRODUCT_AGENT_MONITORING_CHANNEL_ID` would take `/health`, Slack and every cadence endpoint with it.

`DATABASE_URL` is the one startup-critical variable, and not by preference: the Dockerfile's next step is `alembic upgrade head`, which cannot run without it, so the container already fails there. Making it explicit in the preflight only moves that failure one step earlier and gives it a better message. Every other variable is scoped to one capability, so a fault in it is reported loudly at startup — which is the point, since it surfaces before 06:00 rather than at 06:00 — while the application serves everything else.

**Validation runs as a preflight step in the container's start command, not in a lifespan hook.** The Dockerfile already chains `alembic upgrade head && uvicorn ...` so that a failed migration fails container startup rather than serving traffic against a partial schema; `deploy-pipeline`'s "Application Migrates the Database Before Serving Traffic" requirement records that. Configuration checking is the same shape of concern and goes ahead of it. This is also forced: `test_main_slack_wiring.py` and `test_main_monitoring_wiring.py` each run `TestClient(app)` as a context manager — so the lifespan executes — with three named variables deleted, and require it to succeed. Those sets intersect the model's declared variables, so any lifespan-based check that failed on absence would fail those guards. Neither file is modified.

**Every fault is reported at once.** Pydantic collects all field errors before raising, and the preflight prints them rather than only the first. The gap this addresses — a variable registered as a secret but absent from `deploy.yml`'s render step — tends to come in groups, and a checker that stops at the first fault turns one failed deploy into several.

**The model declares `PRODUCT_AGENT_SLACK_SIGNING_SECRET` and `CLICKUP_API_TOKEN` as optional.** Both are registered as `production` secrets absent from `deploy.yml`'s render step, and neither has a *caller* — `CLICKUP_API_TOKEN` does have a consumer, `clickup_client.py:26`, which reads it directly; nothing calls that adapter.

For `CLICKUP_API_TOKEN`, optional is not merely convenient, it is required by an existing specification: `clickup-task-client`'s "Authentication is configured independently of any one caller" has a scenario "Credential absent until first use", so treating its absence as a startup fault would contradict a spec already in `openspec/specs/`. For `PRODUCT_AGENT_SLACK_SIGNING_SECRET`, optional is the honest third answer between reporting a fault at every startup for a capability nothing uses and omitting it from an inventory that claims completeness. `add-product-creation-clickup-task` owns wiring both through the render step and flipping them to required, in the same change where that can be verified end to end.

**`DATABASE_URL` is typed, not merely present-checked.** Every other declared variable is an opaque credential or id, so a presence check is all that is meaningful for them. `DATABASE_URL` is different: the application connects with `postgresql+asyncpg`, and a value carrying a scheme SQLAlchemy's async engine cannot use fails later with an error that names neither the variable nor the cause. Validating the scheme at preflight gives the "unparseable as its declared type" requirement a real referent rather than a vacuous one, and catches a misconfiguration that is easy to make.

**The `DATABASE_URL` abort path is unreachable through this project's own Compose file.** `docker-compose.yml`'s `app` service always sets `DATABASE_URL` in its `environment:` block, built from `POSTGRES_PASSWORD`. So the startup-critical abort cannot be triggered by a missing variable in `.env` — it is reachable only by running the image outside that Compose file. Note specifically that an absent `POSTGRES_PASSWORD` does **not** reach it: Compose substitutes empty, yielding `postgresql+asyncpg://commerce_ops:@postgres:5432/commerce_ops`, whose scheme and host both pass. That failure still surfaces one step later, in `alembic upgrade head`. This is recorded because it makes the abort path a guard against running the image wrongly rather than a likely production event, and because the task that verifies it has to bypass Compose to do so.

### What was split out

The Slack Bolt migration and the async conversion left this change after review found two of their premises false. Both are recorded here because the change that carries them inherits them:

- **`AsyncApp(token_verification_enabled=False)` does not prevent Bolt's `auth.test` call**; it defers it to the first request. `slack_bolt.middleware.authorization.single_team_authorization` performs `req.context.client.auth_test()` when no cached result exists, and its skip-list is `["app_uninstalled", "tokens_revoked", "team_access_revoked"]`, which does not include `app_mention`. The remedy is a custom `authorize` callable returning a fixed `AuthorizeResult`, which `AsyncApp` accepts.
- **`tests/unit/omni_agent/.../test_slack_events_endpoint.py` cannot survive the migration unmodified.** It asserts `get_slack_client` exists on the adapter module by name, and both its doubles are synchronous, so an adapter that awaits either raises `TypeError` into a broad `except` and posts the failure message instead of the answer. The claim that `slack-trigger`'s tests are a black-box regression contract was wrong, and the Bolt change must rebuild its justification on the requirements alone and treat the doubles as explicit fixture corrections.

## Risks / Trade-offs

- [Risk] A reported-but-not-fatal configuration fault can be ignored, since the container still serves → accepted, and it is the trade chosen deliberately over a full outage on a missing channel id. Note the visibility limit precisely, because it is easy to overstate the benefit: the preflight writes to the container's own stderr, so the report reaches `docker logs`, **not** the deploy job's output — `deploy.yml` captures only the host-side `docker compose pull && up -d --wait` and the health-check step. So a green deploy can still carry an unnoticed fault. The gain over today is that the fault exists in a startup log at deploy time rather than surfacing at 06:00 inside a background handler; routing non-critical faults to an operator-visible channel is a follow-up change, not this one.
- [Risk] The drift test scans source for environment-variable reads, so an unusual access pattern could evade it → accepted at this size; the codebase reads env in five files by two literal idioms. If access patterns diversify, the test is the thing to strengthen, and its failure mode is a false pass, not a false failure.
- [Trade-off] `pydantic-settings` reads a local `.env` if present, which overlaps with local development but not with the container: the image copies no `.env` and mounts none, and Compose's `env_file` delivers those values as process environment instead. The overlap is a local-development convenience only. Note that the `.env` this project renders carries `IMAGE_TAG` and `POSTGRES_PASSWORD`, neither of which is a model field — so the model must ignore unrecognized keys rather than reject them, or a developer holding a copy of the rendered file would see two phantom faults.
- [Risk] `launch_playbook.py`'s docstring currently points at "design.md's transcription table" for the full offset mapping, and that design.md is inside the archive this change freezes → removing the external contrast without restating the mapping would leave the only complete statement of it in a document the change itself calls historical. The docstring must carry the mapping in full on its own terms.
- [Trade-off] Recording the launch state-ownership split without implementing any of it means the decision is reviewed here and exercised elsewhere. Accepted: it is the decision that shapes the next several changes, and settling it once beats re-deciding it in each.

## Migration Plan

Behavior-preserving for every existing requirement; no data migration, no schema change, no secret added or renamed, and no Slack app reconfiguration.

The one behavior change is at container startup: a `DATABASE_URL` fault now aborts before the migration rather than during it, and every other configuration fault is printed where it previously went unreported. Every variable the model declares required is already rendered by `deploy.yml`'s "Render .env" step (`OPENAI_API_KEY`, `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_MONITORING_CHANNEL_ID`, `TRIGGER_SECRET`) or supplied by `docker-compose.yml`'s `environment:` block (`DATABASE_URL`), so the first deploy after this change should start cleanly and report nothing. That correspondence is verified as an explicit task rather than assumed, because it is the whole point of the mechanism.
