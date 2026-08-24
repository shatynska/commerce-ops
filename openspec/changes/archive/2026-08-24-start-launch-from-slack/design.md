## Context

See proposal.md for motivation. Constraints that shape the approach:

- `catalog`'s own design (Decision 10 of `introduce-catalog-and-shared-vocabulary`) deliberately gave it no HTTP/Slack driving surface: registration is exercised through use cases only.
- `.importlinter` forbids launch infrastructure from importing catalog's infrastructure (store); catalog's *application* surface is importable from launch (the graduation stamp already crosses the other way).
- The shared `slack_app.py` registry composes per-identity Bolt apps; `omni_agent`'s adapter is the working example of listener registration, credential gating, and direct-env credential reads sanctioned by `runtime-configuration` ("per-request tolerance of absence is itself required behavior").
- The ClickUp completion loop (`launch-clickup-sync`) converges every active launch's list and tasks on a 30-minute cadence; anything this adapter created in ClickUp would be duplicated or fought by that pass.
- `start_launch` accepts an optional launch date; without one, no due periods resolve until a date is set.
- Write use cases are scope-free by design (`introduce-access-scope` touched reads only).

## Goals / Non-Goals

**Goals:**

- One Slack interaction takes a new product from nonexistent to launched-and-tracked, with the existing machinery doing everything downstream.
- Failure semantics a non-technical user can trust: an error in the modal means nothing happened.

**Non-Goals:**

- No ClickUp writes, no notification fan-out beyond the confirmation message.
- No restriction on *who* may start a launch beyond workspace membership — capability flags are slice-6 follow-up work (`access` currently models visibility only). Recorded as accepted, not overlooked.
- No Slack surface for `move_launch_date`, `approve_gate`, or `record_step_outcome` — later changes.
- No second marketplace; the select exists so adding one is a data change, not a redesign.

## Decisions

### 1. One modal registers the product and starts the launch

Alternative — register-only, start elsewhere — was rejected: the team's intent in filling the form is "launch this product", and a registered-but-unlaunched product is a state nothing currently needs. Catalog still keeps no driving surface of its own; the surface belongs to launch entry, which consumes catalog's public use case. This keeps catalog's Decision 10 true in spirit: registration remains exercised only through its use case.

### 2. The adapter lives in `launch/infrastructure/driving/`; the catalog write is injected

The act is starting a launch, so the adapter is launch's. It imports launch's own application surface and repositories freely, and `catalog.application`'s types for the errors it must render — but constructing catalog's store is barred by the import contract. The composition root (`main.py`, outside the containers, exactly like `worker.py` for the sync job's `read_product`) injects a registrar callable into the adapter module. The callable takes the adapter's open session plus the field values and runs `catalog.application.register_product` over a store built on that session — which is what makes Decision 3 possible. Module-global injection point, resolved at call time, keeping `daily_briefing_job.py`'s monkeypatch-friendly pattern.

### 3. Register and start are one transaction

Both writes run in a single `session()` scope: the catalog row and the launch row commit together or not at all. A sequential two-transaction design was rejected because its failure mode — product registered, launch absent, resubmission then blocked by duplicate SKU — is exactly the half-state a non-technical user cannot repair from Slack. The launch store's own rejections (unknown product, duplicate launch) behave correctly inside the shared transaction: the uncommitted product row is visible to the launch write.

### 4. Modal contract

SKU (required, plain text), name (required), ASIN (optional), launch date (optional, Slack datepicker), marketplace (static select, single Amazon US option `ATVPDKIKX0DER`, preselected). No playbook-version field — `ShippedPlaybooks` resolves exactly one version and rejects the rest, so asking invites unfixable input. Validation failures checkable before acknowledgement return Bolt `response_action: errors` mapped to the offending block; the modal stays open. Domain rejections established only at persistence time (duplicate SKU, duplicate launch) arrive after the ack, when the modal is already closed, so they are reported to the submitting user as an error message naming the rejection (see Risks — the acknowledgement window) — never as a modal error.

### 5. Credentials mirror the existing Slack adapters

Signing secret and bot token read directly from `os.environ` with literal variable names (the environment-drift check parses for constants); absent secret rejects every request rather than waving them through; the credential gate acknowledges non-replying requests without a bot token, per the registry's established predicate pattern. `product_agent_slack_signing_secret` moves to required in the settings model — the app now receives inbound Slack traffic, so a deployment without it is misconfigured, not merely feature-less. Required but **not startup-critical**: `runtime-configuration` reserves preventing startup for startup-critical variables, and this secret is capability-scoped like the other Slack credentials — its absence is reported by name at startup, the process serves, and this surface rejects every request until the secret arrives. Fail-closed degradation, not a down application.

### 6. Confirmation is a message, not a modal update

Outcome messages — success confirmation and post-ack failure reports alike — are delivered to the submitting user directly (a DM through the bot token), not to the invoking channel: a slash command can be invoked in a channel the bot is not a member of, where a channel post would fail silently, defeating the visibility requirement. The credential gate (Decision 5) guarantees a reply-needing request is only handled when the bot token exists, so direct delivery is always possible once a submission was acknowledged. The confirmation names the product, SKU, launch date or "no date yet", and that ClickUp tasks appear within the sync cadence. Managing expectations about the ≤30-minute ClickUp delay in the confirmation text is deliberate — otherwise the first demo question is "where are the tasks?".

## Risks / Trade-offs

- [Anyone in the workspace can start a launch] → Accepted for this slice and stated in Non-Goals; the slice-6 access follow-up adds capability checks at adapters.
- [The injected registrar is a runtime contract, not a typed import] → Same trade the codebase already carries for `clickup_sync_job.read_product`; a missing injection fails loudly at first use, and the adapter's tests pin the contract.
- [Slack's 3-second ack window vs. two DB writes] → Bolt's lazy-listener/ack pattern: acknowledge the submission immediately after field validation, run the transaction in the handler's continuation; a persistence failure then surfaces as a posted error message rather than a modal error. The per-field inline path covers what is checkable before ack (missing/malformed fields); duplicate SKU detection happens in the transaction, so its failure is delivered as a message — recorded here so the spec's "inline" language is scoped to field validation honestly.
- [Marketplace hardcoded to Amazon US] → A single-option select keeps the contract shaped for more options without pretending they exist.

## Migration Plan

1. Deliver the new required secret through `deploy.yml` before or with the deploy. The variable is not startup-critical, so an undelivered secret does not fail the container: the startup check reports it by name and the entry surface rejects every request until it is delivered (fail-closed degradation per `runtime-configuration`, Decision 5).
2. Reconfigure the `product_agent` Slack app: create the slash command, set the Interactivity Request URL to the new route.
3. Rollback is removing the router; no schema changes, no data migration. Products/launches created meanwhile are ordinary data and stay.

## Open Questions

- The slash command's name (`/start-launch` vs `/add-product` vs a Ukrainian-language name for the team) — cosmetic, decided at implementation with the team.
