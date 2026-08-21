## 1. import-linter setup

- [x] 1.1 Add `import-linter` as a dev dependency (`uv add --dev import-linter`).
- [x] 1.2 Write `.importlinter` with a `layers` contract per module
      (`products`, `omni_agent`, `shared`): `infrastructure` →
      `application` → `domain`.
- [x] 1.3 Add the six per-source-layer `forbidden` contracts from
      design.md's Decisions (one each for `products.domain`,
      `products.application`, `products.infrastructure`,
      `omni_agent.domain`, `omni_agent.application`,
      `omni_agent.infrastructure`) — domain and infrastructure source
      contracts forbid the other business module in full; the
      application source contract forbids only the other module's
      `.domain`, `.infrastructure`, and named internal `.application`
      submodules (e.g. `commerce_ops.omni_agent.application.graph`),
      leaving that module's `application` package root reachable.
      `shared.*` is never listed in any contract beyond what design.md
      specifies per layer — the Shared Kernel allowance is an omission,
      not a separate rule.
- [x] 1.3a Add the seventh `forbidden` contract, sourced from `shared`:
      `source_modules = ["commerce_ops.shared"]`,
      `forbidden_modules = ["commerce_ops.products", "commerce_ops.omni_agent"]`.
      Without this contract, nothing catches `shared` importing a
      business module — the direction of the actual existing violation
      (`shared.infrastructure.driving.slack` → `omni_agent`) — since
      `forbidden` contracts are one-directional and none of the six
      contracts in 1.3 has `shared` as a source.
- [x] 1.4 Run `lint-imports` manually and confirm it flags exactly the
      known `shared.infrastructure.driving.slack` → `omni_agent`
      violation and nothing else unexpected.
- [x] 1.5 Add a throwaway deliberately-wrong import exercising the
      Shared Kernel boundary (e.g. temporarily import
      `shared.infrastructure` from `products/domain/__init__.py`),
      confirm `lint-imports` catches it, then remove the throwaway
      import — this is the only way to know the per-layer contract set
      is encoded correctly, since no existing code currently exercises
      that path.

## 2. Relocate the Slack driving adapter into omni_agent

- [x] 2.1 Create `src/commerce_ops/omni_agent/application/use_cases.py`
      with `answer_question(question: str) -> str`, wrapping
      `build_production_graph()` / `.invoke(...)` and extracting the
      answer, so `MessagesState`/`HumanMessage` never cross the
      application boundary.
- [x] 2.2 Create `src/commerce_ops/omni_agent/application/__init__.py`
      re-exporting `answer_question` via `__all__`.
- [x] 2.3 Create `src/commerce_ops/omni_agent/infrastructure/driving/__init__.py`
      and move `slack.py` there from
      `src/commerce_ops/shared/infrastructure/driving/slack.py`, updating
      it to import `answer_question` from `omni_agent.application`
      instead of `build_production_graph` from `omni_agent.application.graph`.
- [x] 2.4 Change the route from `/slack/events` to `/omni_agent/slack/events`.
- [x] 2.5 Delete the old `shared/infrastructure/driving/slack.py`.
- [x] 2.6 Update `src/commerce_ops/main.py` to import the router from
      `omni_agent.infrastructure.driving.slack` instead of
      `shared.infrastructure.driving.slack`.
- [x] 2.7 Move and update
      `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py`
      and `test_main_slack_wiring.py` to `tests/unit/omni_agent/infrastructure/driving/`,
      updating the asserted route path and import paths.

## 3. Verify enforcement

- [x] 3.1 Re-run `lint-imports` and confirm it now passes clean.
- [x] 3.2 Wire a `lint-imports` step into `.pre-commit-config.yaml`
      alongside `ruff check`, `ruff format --check`, and `mypy`.
- [x] 3.3 Wire a `lint-imports` step into `.github/workflows/ci.yml`'s
      validation job, alongside the existing `ruff check`,
      `ruff format --check`, `mypy`, and `pytest` steps — this is what
      actually gates merges to `main` per the `deploy-pipeline` spec;
      pre-commit alone is locally bypassable.
- [x] 3.4 Run `uv run pre-commit run --all-files` and confirm everything
      passes.
- [x] 3.5 Run `uv run pytest` and confirm the full suite passes.

## 4. Documentation

- [x] 4.1 Update `README.md`'s Architecture section: replace the "one
      shared app/entry point... rather than a separate adapter
      instantiated per module" sentence to reflect per-module driving
      adapters wired through `main.py` as the composition root.
- [x] 4.2 Add the module-boundary contract to `README.md`'s Architecture
      section: public-API-per-module (`<module>/application/__init__.py`
      + `__all__`), the Shared Kernel carve-out for `shared`, the
      cross-module escalation ladder (direct import by default, a
      consumer-owned `Protocol` port when justified), one level of
      nested-module support, and the `omni_agent`-as-future-orchestrator
      /saga framing with the peer-modules-never-call-each-other-directly
      rule.
- [x] 4.3 Update `AGENTS.md`'s Architecture summary pointer paragraph to
      match.

## 5. Ops follow-up (outside this repo)

- [x] 5.1 Track the Slack Event Subscriptions Request URL update
      (`/slack/events` → `/omni_agent/slack/events`) somewhere consulted
      at actual deploy time — a deploy runbook entry or linked ops
      ticket, not only the PR description — sequenced as a pre-deploy or
      immediately-post-deploy step, with the dropped-events window
      during the gap stated explicitly rather than assumed away.
      Tracked externally by the project owner (their own ops
      ticket/runbook system), not in this repo.
