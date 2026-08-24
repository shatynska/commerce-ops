## Why

There is no user-facing way to bring a product into the system or start its launch — `catalog`'s registration and `launch`'s start exist only as application use cases callable from Python, while the ops team works in Slack. The previously parked `add-product-creation-clickup-task` proposal covered this ground but is superseded: it predates the Bolt migration, the centralized session provider, the catalog/launch module split, and — decisively — the ClickUp completion loop, which now projects a whole per-launch list with per-step tasks automatically, making that proposal's create-one-ClickUp-task half obsolete.

## What Changes

- A new slash command on the `product_agent` Slack app opens a modal collecting a new product's SKU and name (required), and ASIN and launch date (optional). The marketplace is a select carrying the single Amazon US option for now.
- Submitting the modal, in **one transaction**: registers the product in the catalog and starts its launch pinned to the shipped playbook version. Either both persist or neither does.
- A missing or malformed field is rejected inline in the open modal. A rejection established only at persistence time — a duplicate SKU, an already-launched product — arrives after the modal closes and is reported to the submitting user as an error message. In every rejection, nothing is persisted. Success posts a confirmation message naming the product and its launch.
- **No ClickUp interaction in this change.** The completion loop's next convergence pass (≤30 minutes) creates the launch's ClickUp list and tasks; this adapter's job ends at the launch existing.
- The playbook version is not asked for: exactly one version resolves in a build, and a human-typed version field would be a trap.
- Slack request verification on the `product_agent` app: `PRODUCT_AGENT_SLACK_SIGNING_SECRET` moves from optional to required in the settings declaration, this being its first consumer. Required but **not startup-critical** (matching the existing Slack credentials): an absent secret is reported by name at startup while the process still serves, and this surface rejects every request until it arrives — fail-closed either way. An unverifiable request is rejected.
- The parked `add-product-creation-clickup-task` change is formally retired; `docs/deferred-work.md`'s entry for it is closed out pointing here.

## Capabilities

### New Capabilities

- `launch-entry`: starting a product's launch from Slack — the modal's contract, the atomic register-and-start behavior, inline rejection semantics, request verification, and the boundary that entry never projects work into ClickUp.

### Modified Capabilities

(none — `product-catalog`'s registration and `launch-instance`'s start requirements are consumed as they stand, through the modules' public surfaces.)

## Impact

- New driving adapter under `src/commerce_ops/launch/infrastructure/driving/` (Bolt listeners on the `product_agent` app via the shared `slack_app` registry), with the catalog-side write injected from the composition root — the launch module may not import catalog's store (see design.md).
- `main.py`: include the new router; wire the catalog registrar injection.
- `shared/application/settings.py`: `product_agent_slack_signing_secret` becomes required.
- `.github/workflows/deploy.yml`: deliver the signing secret.
- Slack app reconfiguration (operational): a new slash command and an Interactivity Request URL on the `product_agent` app.
- Depends on the shipped playbook resolving (works with `steps: []` today; pairs with `author-playbook-steps` for a meaningful demo).
