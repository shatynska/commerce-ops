## 1. Configuration

- [ ] 1.1 Move `product_agent_slack_signing_secret` from optional to required in `shared/application/settings.py` — required but **not** startup-critical (it stays out of `STARTUP_CRITICAL_ENV_VARS`, matching the other Slack credentials) — and adjust the settings/drift tests that assert its optionality.
- [ ] 1.2 Register `PRODUCT_AGENT_SLACK_SIGNING_SECRET` in `.github/workflows/deploy.yml`'s secret delivery, alongside the existing `product_agent` bot token.

## 2. The entry adapter

- [ ] 2.1 Create `launch/infrastructure/driving/slack_entry.py`: register the `product_agent` Bolt app via the shared `slack_app` registry with direct-env credential reads (literal variable names) and a `will_reply` predicate covering the slash-command and view-submission bodies — the registry's credential gate rejects those without a bot token, and an absent signing secret is rejected by Bolt's own verification — plus the slash-command listener opening the modal (SKU, name, ASIN, launch date, single-option marketplace select; no playbook-version field).
- [ ] 2.2 Implement the view-submission handler: field validation returning inline `response_action: errors`; ack; then one `session()` transaction running the injected catalog registrar and `launch.application.start_launch` pinned to the shipped playbook; any post-ack failure of the persistence — a domain rejection (duplicate SKU, existing launch) or an unexpected infrastructure failure alike — caught and posted to the submitting user as an error message naming it, with nothing persisted; success confirmation naming product, date-or-absence, and the ClickUp sync cadence. Outcome messages are delivered to the submitting user directly (design.md Decision 6), not to the invoking channel.
- [ ] 2.3 Declare the module-global registrar injection point (call-time resolution, `daily_briefing_job.py`'s pattern) and wire it from `main.py` over `catalog.application.register_product` with a store on the handler's session; include the new router in `main.py`.
- [ ] 2.4 Add the new module to `.importlinter` exactly as the existing launch driving adapters are contained.

## 3. Verification

- [ ] 3.1 Run the change's derived tests plus `uv run pytest tests/unit tests/agents`, mypy, ruff, and import-linter; run `tests/integration` before push.

## 4. Operational and record

- [ ] 4.1 Reconfigure the `product_agent` Slack app: create the slash command (name settled with the team per design.md's open question) and point its Interactivity Request URL at the new route; verify end to end in the workspace.
- [ ] 4.2 Close out `docs/deferred-work.md`'s parked `add-product-creation-clickup-task` entry as superseded by this change (and delete the stale local branch after merge).
- [ ] 4.3 Update `docs/domain-map.md` if the slice notes reference product entry, recording that entry lives in `launch` and catalog remains without a driving surface of its own.
