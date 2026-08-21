## Context

See `proposal.md` - Why for the motivating violation. Current module
layout: `products`, `omni_agent`, `shared`, each with `domain/`,
`application/`, `infrastructure/` (some with `driving`/`driven` splits
under `infrastructure`). Existing precedent already follows the intended
layering: `products/infrastructure/driven/playbook_loader.py` imports
`products/domain/launch_playbook.py` (infrastructure → domain). No
import-boundary tool exists today; `pre-commit` only runs `ruff`,
`ruff format --check`, `mypy`, and the unit/agent pytest tiers.

## Goals / Non-Goals

**Goals:**
- A concrete, *enforced* module-boundary contract, not just a documented
  convention.
- Land the contract without leaving `main` red — the one existing
  violation gets fixed in the same change that turns on enforcement.
- A stated escalation path for cross-module dependencies, so future work
  doesn't have to re-derive it.
- A stated exception for `shared` (Shared Kernel), distinct from how
  business-capability modules relate to each other.
- Room for one level of module nesting without weakening the outer
  boundary.

**Non-Goals:**
- No DI container. Constructor injection + `main.py` as the composition
  root remains sufficient; this design doesn't revisit that.
- No saga/process-manager implementation. This change only names the
  architectural implication for `omni_agent`'s eventual orchestrator role
  so peer modules aren't coupled to each other prematurely — the STRATEGY/
  LOOKER/SKAUT machinery itself is future work.
- No `shared/infrastructure/driving/slack_common.py` yet. No second
  Slack app exists to justify it; this design leaves room for one without
  creating it preemptively.
- No change to `slack-trigger`'s or `omni-agent`'s spec requirements —
  see proposal.md - Capabilities.

## Decisions

**Import-linter contract shape.** Two contract types in one
`.importlinter` config, root package `commerce_ops`.

A `layers` contract per module (`products`, `omni_agent`, `shared`):
`layers = ["infrastructure", "application", "domain"]`. Higher layers may
import lower layers; lower layers may not import higher ones. This is
exactly the existing `playbook_loader.py` precedent, made checked rather
than incidental.

For the inter-module rule, import-linter's `forbidden` contract type
takes one flat `source_modules` list and one flat `forbidden_modules`
list — it has no per-source-layer conditional, so a single contract
cannot express "domain may reach `shared.domain` but not
`shared.infrastructure`, while infrastructure may reach both." The
correct encoding is **one `forbidden` contract per source layer, per
business module** — three contracts for `products`, three for
`omni_agent` (six total today, growing by three per new business
module, each just adding the new module to the existing contracts'
`forbidden_modules` list — not growing quadratically). A new business
module also needs adding to the seventh, `shared`-sourced contract's
`forbidden_modules` list below — growth is "three new contracts plus one
addition to the seventh," not just "three":

- **`<module>.domain` source contract** — forbidden: every other business
  module in full (e.g. `commerce_ops.omni_agent` for `products.domain`'s
  contract) plus `shared.application` and `shared.infrastructure`. Domain
  never makes a cross-module call, public surface or not; `shared.domain`
  is simply never listed, so it's implicitly allowed — this *is* the
  Shared Kernel exemption, expressed as an omission, not a special case.
- **`<module>.application` source contract** — forbidden: every other
  business module's `.domain`, `.infrastructure`, and named internal-only
  `.application` submodules (e.g.
  `commerce_ops.omni_agent.application.graph`) — but *not* the other
  module's `application` package root, so its published `__all__`
  surface stays reachable — plus `shared.infrastructure`. `shared.domain`
  and `shared.application` are unlisted, hence allowed.
- **`<module>.infrastructure` source contract** — forbidden: every other
  business module in full. An infrastructure layer reaches another
  module only through its *own* application layer, never directly — so,
  like domain, it gets no exception for the other module's public
  surface. `shared.*` is unlisted at every layer, hence allowed — this is
  the one layer allowed to reach all three of `shared`'s layers, since
  infrastructure is already the outermost rung.

A seventh contract is needed for the reverse direction, and it's the one
that actually catches the motivating violation: import-linter's
`forbidden` contract is one-directional, and none of the six contracts
above has `shared` as `source_modules` — so nothing yet stops `shared`
from importing a business module. Shared Kernel semantics make this
contract simple, with no per-layer split needed: `shared` should never
depend on a business module *at all*, regardless of which of `shared`'s
own layers is doing the importing, since a shared kernel that reached
into one bounded context's business logic wouldn't be a shared kernel
anymore.

- **`shared` source contract** — `source_modules = ["commerce_ops.shared"]`,
  `forbidden_modules = ["commerce_ops.products", "commerce_ops.omni_agent"]`.
  This is exactly the direction of the existing violation:
  `shared/infrastructure/driving/slack.py` importing
  `omni_agent.application.graph`.

This must be verified empirically before being trusted or wired into any
gate: write the contracts, add a deliberately-wrong throwaway import
(e.g. `products/domain/__init__.py` temporarily importing
`shared.infrastructure`) or exercise the real one already in the
codebase, confirm `lint-imports` catches it, then remove the throwaway
import.

Limitation worth naming regardless: import-linter has no primitive for
"only names in `__all__` are importable" — it can only forbid explicitly
listed submodule paths. The forbidden-modules list is a floor, not a
complete derivation from each module's `__init__.py`. Anything narrower
than what's explicitly listed relies on code review and the `ddd`
skill's own guidance, same as today. The list grows whenever a new
internal-only submodule is added to a module's `application/` layer.

**Public-API-per-module mechanism.** `<module>/application/__init__.py`
re-exports via `__all__`; that's the only import surface other modules
may use. For `omni_agent`: `graph.py` (the compiled LangGraph state
machine) stays unexported; a new module exposes
`answer_question(question: str) -> str`, and `__init__.py` does
`from .use_cases import answer_question` / `__all__ = ["answer_question"]`.
This keeps `MessagesState`/`HumanMessage` behind the application
boundary even for code inside the same module (infra should not need to
know the graph's state shape), though once `slack.py` lives inside
`omni_agent` this is no longer required for the import-linter contract to
pass — it's kept for testability and layering hygiene, not enforcement.

**Escalation ladder for genuine cross-module dependencies.** Default:
direct import of the producer module's `application` public surface.
Escalate to a consumer-owned `Protocol` port only when the dependency
needs mocking in tests, or there's a real risk of the dependency
direction flipping. Not mandated for every dependency — matches this
project's existing stance (README) of adopting tactical patterns per
module only as needed, not universally upfront.

**Nested modules.** One level supported:
`<module>/<child>/{domain,application,infrastructure}`, with both
contracts applied recursively at that level. A child's `application`
surface is importable by its siblings within the parent and by the
parent's own `application/__init__.py` (which may re-export a curated
subset), but never directly from outside the parent — the parent module
is still the unit external code depends on. A second level of nesting is
treated as a signal to promote the concept to a sibling top-level module
instead, per the `ddd` skill's "recognizing a strategic leak."

**Driving adapters belong to the module they drive.** Each module owns
its own `infrastructure/driving/` (routes, credentials, framework
wiring); `main.py` stays the sole composition root, `include_router`-ing
each module's router. `shared/infrastructure/driving/` holds only
adapters with no module-specific business logic — after this change,
just `health.py`. Concretely: `omni_agent/infrastructure/driving/slack.py`
owns `/omni_agent/slack/events`, `OMNI_AGENT_SLACK_SIGNING_SECRET`, and
`OMNI_AGENT_SLACK_BOT_TOKEN`.

**Extraction trigger for future shared Slack code.** Only once a second
module's Slack adapter exists and shows real, identical duplication —
judged by what's actually duplicated, not limited to any fixed category
(signature verification, envelope parsing, or anything else) — not
extracted preemptively for one caller.

**Orchestrator/saga framing (documentation only).** `README.md` names
that a future cross-module coordinating role — `omni_agent` is the
stated direction, though its current slice is far from it — plays a
process-manager/saga role (per the `ddd` skill's own boundary: it names
this pattern but deliberately doesn't own its tradeoffs) coordinating
peer domain modules through their own public `application` APIs. Peer
domain modules never call each other directly for orchestration
purposes — only for a narrow, stable, genuine business dependency via
the escalation ladder above. No orchestrator code is added in this
change.

## Risks / Trade-offs

- [Risk] The forbidden-modules contract can't fully auto-derive
  "public = what's in `__all__`" from import-linter's primitives, only
  block explicitly-listed internal paths. → [Mitigation] Treat the
  explicit list as the enforced floor; expand it whenever a new
  internal-only `application` submodule is added; lean on code review for
  anything narrower.
- [Risk] Turning on enforcement immediately fails pre-commit against the
  existing `slack.py` violation. → [Mitigation] This change fixes that
  violation (the relocation into `omni_agent`) in the same change that
  adds the contract, so `main` is never left red.
- [Risk] The route path change (`/slack/events` → `/omni_agent/slack/events`)
  is breaking for Slack's own Event Subscriptions config, which lives
  outside this repo and isn't checked by the post-deploy `/health`
  verification. → [Mitigation] The PR description alone isn't a durable,
  deploy-time-visible tracking mechanism — this needs to be sequenced as
  an explicit pre-merge or pre-deploy step (an ops checklist item or
  linked ticket consulted at the actual deploy, not just noted in the
  PR), and it should be stated plainly that events arriving between
  deploy and the URL update are dropped, not queued, since Slack's own
  retry budget is bounded and nothing in this repo observes the gap.
- [Risk] `import-linter` adds a new pre-commit *and* CI step, another
  pinned dev dependency, and a `deploy-pipeline` spec delta. →
  [Mitigation] Accepted trade-off — enforcing the boundary at the actual
  merge gate (not just locally, where it's optional to install and
  bypassable) is the point of adopting it now, while the module count is
  small enough to keep the contract set simple.

## Migration Plan

1. Add the `import-linter` dev dependency and `.importlinter` config
   (the per-source-layer contract set above), not yet wired into
   `pre-commit` or CI.
2. Verify the contract set empirically: run `lint-imports` and confirm
   it flags exactly the known `slack.py` violation; add a throwaway
   deliberately-wrong import exercising the Shared Kernel boundary
   (e.g. `products.domain` importing `shared.infrastructure`), confirm
   it's caught, then remove the throwaway import.
3. Relocate `slack.py` into `omni_agent/infrastructure/driving/`, add
   the `answer_question` wrapper, update `main.py`'s router wiring,
   move/update the two affected test files, change the route path.
4. Re-run `lint-imports` — should pass clean.
5. Wire `lint-imports` into `.pre-commit-config.yaml` **and** into the
   CI validation job (`.github/workflows/ci.yml`), alongside `ruff`,
   `mypy`, and `pytest` — pre-commit alone is locally bypassable and
   isn't what actually gates merges to `main`.
6. Update `README.md`'s Architecture section and `AGENTS.md`'s
   Architecture summary.
7. Sequence the Slack Event Subscriptions Request URL update as an
   explicit pre-deploy or immediately-post-deploy ops action, tracked
   somewhere consulted at deploy time (not only the PR description),
   with the dropped-events window during the gap made explicit rather
   than assumed away.

**Rollback:** a plain revert — no persisted state or data migration is
involved. If rolled back after deploying, the Slack Request URL would
need to be pointed back at `/slack/events`.
