## Why

Every Slack message about one launch — the registration confirmation, each gate ask, each automated-result decision, each stuck-step alert — lands today as its own independent top-level post: the confirmation as a DM to whoever created it, everything else as a separate message in the shared monitoring channel, indistinguishable from ops-health reports for every other product. Nothing links these messages to each other or to the launch they concern. A person following one product's launch has no single place to look; the channel accumulates an unordered mix of every launch's asks and reports together.

## What Changes

- A new, dedicated Slack channel (`PRODUCT_AGENT_LAUNCHES_CHANNEL_ID`, already provisioned) carries per-launch messages, separate from the existing monitoring channel, which keeps carrying cross-product reports (ClickUp configuration gaps, overdue-work digests, the daily briefing).
- **BREAKING**: A launch's registration confirmation is no longer a DM to the submitter. Starting a launch now posts one anchor message to the launches channel — naming the product, its SKU, its marketplace, and its launch date — and the confirmation becomes a reply within that message's thread, tagging the submitter. The existing DM path continues to carry only a post-acknowledgement *failure* report, since a failed start has no thread to reply into.
- A launch's Slack thread is established lazily: the first per-product message that has one to deliver creates the anchor if none exists yet and persists the reference; every later message for that launch replies within it instead of posting a new top-level message. This is also how a launch that predates this change (including an existing test launch) gets its first thread — nothing is backfilled up front.
- Gate-confirmation asks, automated-result decision asks, and stuck-step alerts move from independent top-level posts in the monitoring channel to replies within the launch's own thread in the launches channel.
- A thread reply tags whoever is positioned to act on it: a message tied to a step naming a `confirmer` tags that confirmer; every other message (a gate ask, or a step message whose step names no confirmer) tags the launch's submitter instead.
- The launch record persists two new facts: the Slack identity of whoever submitted it, and the reference to its established Slack thread — both live only as long as the launch itself, tracking `launch_positions` rather than the catalog product, since they stop being meaningful once a product leaves its launch.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities

- `launch-entry`: "A launch is started from Slack in one interaction" changes what confirms a successful start — an anchor message to the launches channel plus a tagged thread reply, replacing the DM. The post-acknowledgement-failure requirement is unchanged; its DM delivery still applies.
- `launch-instance`: gains a new requirement — a launch record persists its submitter (recorded once, at start) and its Slack thread reference (absent until a message first needs it, established idempotently under concurrent delivery).
- `launch-gate-progression`: "A gate awaiting only confirmation is asked about in Slack" changes where and how the ask is delivered — as a reply within the launch's thread in the launches channel, establishing that thread first if it does not yet exist, tagging the submitter.
- `launch-step-automation`: "A pending result is delivered for a decision, and delivery failure does not lose it" and "A step whose handler has stopped making progress is reported once" both change where and how delivery happens — as a thread reply in the launches channel, tagging the step's named confirmer where it has one, the submitter otherwise.

## Impact

- Domain: `src/commerce_ops/launch/domain/launch_run.py` (`Launch` gains `submitter` and `slack_thread_id`, the latter mutable exactly once).
- Application: `src/commerce_ops/launch/application/ports.py` / `use_cases.py` (the launch-start use case records the submitter; a new shared operation resolves-or-establishes a launch's thread reference).
- Infrastructure (driven): `src/commerce_ops/launch/infrastructure/driven/models.py` (`LaunchPosition` gains `submitter`, `slack_thread_id`), an Alembic migration adding both nullable columns, `launch_repository.py`, `slack_notifier.py` (a `launches_channel()` alongside `monitoring_channel()`; posting gains a `thread_ts`), a new advisory-lock keyed helper mirroring `launch_advisory_lock.py` to serialize concurrent thread establishment for one launch.
- Infrastructure (driving): `slack_entry.py` (anchor + tagged reply, replacing the DM confirmation), `gate_confirmation.py`, `automation_confirmation.py`, `automation_pass.py` (all three switch to thread-reply delivery and mention resolution).
- Configuration: `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` — the Environment secret is already set; `deploy.yml` needs to render it, `shared/application/settings.py` needs to declare it, and `tests/unit/shared/application/test_settings.py`'s declared set needs it added. No `runtime-configuration` spec delta: that capability's requirement is that every variable be declared somewhere, and this only adds an instance of already-specified behavior.
- Specs: `openspec/specs/launch-entry/spec.md`, `openspec/specs/launch-instance/spec.md`, `openspec/specs/launch-gate-progression/spec.md`, `openspec/specs/launch-step-automation/spec.md`.
- Tests: unit coverage for the three call sites' new channel/thread/mention behavior, the lazy-establishment race, and the DM-to-anchor confirmation change; the wide set of existing tests asserting delivery to `monitoring_channel()` for per-product messages need updating to the launches channel.
