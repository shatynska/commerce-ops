## Why

A cross-module boundary violation already exists in the codebase today:
`shared/infrastructure/driving/slack.py` imports `omni_agent.application.graph`
directly and unpacks LangGraph's `MessagesState` shape itself, coupling a
module that isn't `omni_agent` to `omni_agent`'s internal implementation.
The project has no enforced convention for module boundaries, and more
modules (and more per-module Slack apps) are coming — the cost of fixing
this compounds the longer it's deferred. This change establishes the DDD
module-boundary contract this project follows, enforces it in tooling
rather than relying on convention alone, and fixes the one concrete
violation it would otherwise immediately flag.

## What Changes

- Adopt `import-linter` as a dev dependency with a `.importlinter` config:
  a `layers` contract per module (`infrastructure` → `application` →
  `domain`, matching existing precedent such as
  `products/infrastructure/driven/playbook_loader.py` importing
  `products/domain`) and a forbidden-modules contract blocking one
  module from reaching into another module's `domain`, `infrastructure`,
  or non-public `application` internals.
- Wire `lint-imports` into the `pre-commit` hook alongside `ruff` and
  `mypy`.
- Relocate the Slack driving adapter from
  `shared/infrastructure/driving/slack.py` to
  `omni_agent/infrastructure/driving/slack.py` — its own route, continuing
  to use its existing `OMNI_AGENT_SLACK_SIGNING_SECRET`/
  `OMNI_AGENT_SLACK_BOT_TOKEN` env vars, calling into its own module's
  application layer (no cross-module import at all). **BREAKING**: the
  route path changes from `/slack/events` to `/omni_agent/slack/events`
  — Slack's Event Subscriptions Request URL needs updating to match once
  this deploys.
- `shared/infrastructure/driving/` keeps only `health.py`; no
  Slack-specific code remains in `shared`.
- Add a thin application-layer wrapper (`answer_question(question: str)
  -> str`) in `omni_agent/application` so LangGraph's compiled graph and
  its `MessagesState`/`HumanMessage` internals never cross into
  infrastructure, even within the same module.
- Document the module-boundary contract in `README.md`'s Architecture
  section: public-API-per-module (`<module>/application/__init__.py` +
  `__all__`), the Shared Kernel carve-out for `shared` (a business
  module's layer may reach its own-or-lower corresponding layer within
  `shared` — the same layering already used within one module, just
  extended to `shared` as a target; `shared` itself never imports a
  business module, regardless of which of `shared`'s own layers is
  asking), the escalation ladder for
  cross-module dependencies (direct application-layer import by default,
  a consumer-owned `Protocol` port when the dependency needs mocking or
  a real circularity risk exists), nested-module support (one level:
  `<module>/<module>/application/__init__.py`, itself gated behind the
  same public-API rule), and naming `omni_agent`'s eventual orchestrator
  role as the process-manager/saga layer coordinating peer modules —
  peer domain modules never call each other directly for orchestration.
- Update `AGENTS.md`'s Architecture summary pointer paragraph to match.
- Add a `lint-imports` step to the CI pull-request validation job
  (`.github/workflows/ci.yml`), alongside the existing `ruff check`,
  `ruff format --check`, `mypy`, and `pytest` steps — matching the
  project's existing precedent of running every `pre-commit` check in
  CI too, so the module-boundary contract is actually enforced on `main`
  rather than only locally and bypassably.

## Capabilities

`slack-trigger`'s and `omni-agent`'s requirements (signature
verification, `url_verification` challenge response, timely
acknowledgement, failure visibility, question/answer contract) describe
behavior, not the literal route path or which module's source file
implements them, and that behavior is unchanged by this move — neither
capability needs a delta.

`deploy-pipeline` does need one: its "Pull Request Validation Gate"
requirement enumerates the exact checks the job runs
(`ruff check`, `ruff format --check`, `mypy`, `tests/unit`+`tests/agents`
pytest), and this change adds `lint-imports` to that job, which changes
that requirement's text.

### New Capabilities

(none)

### Modified Capabilities

- `deploy-pipeline`: the "Pull Request Validation Gate" requirement's
  enumerated check list grows to include `lint-imports`.

## Impact

- New dev dependency: `import-linter`.
- New file: `.importlinter`.
- Modified: `.pre-commit-config.yaml` (adds a `lint-imports` step).
- Moved: `src/commerce_ops/shared/infrastructure/driving/slack.py` →
  `src/commerce_ops/omni_agent/infrastructure/driving/slack.py`; new
  `src/commerce_ops/omni_agent/application/__init__.py` (public surface)
  and a new module holding `answer_question`.
- Modified: `src/commerce_ops/main.py` (router wiring), `README.md`
  (Architecture section), `AGENTS.md` (Architecture summary).
- Tests move/update: `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py`
  and `tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py`
  relocate under `tests/unit/omni_agent/...` and reflect the new route
  path.
- External/ops action (outside this repo): Slack App's Event
  Subscriptions Request URL must be updated from `/slack/events` to
  `/omni_agent/slack/events` when this deploys.
