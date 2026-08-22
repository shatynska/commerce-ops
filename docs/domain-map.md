# Domain map — the high-level vision

**Status: living document.** This is the top-level map of the business domain and the intended shape of the system — the picture we steer by, not a contract. It is expected to change as work details it; when a real change diverges from this map, update the map in the same change. Authoritative behavior lives in `openspec/specs/`; this document records the *model* those specs incrementally realize. That relationship cuts both ways: where a shipped spec already mandates a detail, the map may summarize it but never silently drop it — a change written from the map must never regress a spec.

Provenance: derived from `README.md` (foundation) and `docs/reference/` (external input, not schema). Reference identifiers like `lp.strategy.001` appear only as citations.

## The business in one paragraph

The company sells physical products through online marketplaces (Amazon first). Every product moves through one lifecycle: it is **validated and committed**, **launched** (a gated, roughly T-90 → T+120 sequence of work), then **operated in steady state**, where it is continuously **monitored** (95 metrics with rules, cadences and escalation) and periodically re-postured (Scale / Optimize / Hold / Recover). The ops team works in Slack and ClickUp; the system's job is to hold the process so no step and no signal depends on a person remembering it.

## The unifying axis: Product × Stage, TASK × CHECK

Two lines in the reference material carry the whole model:

> Stage is an attribute of the **product**, not of the agent.
> The difference is the **row type**, not the agent: a CHECK is recurring and threshold-judged ("is this within range"); a TASK is one-time and completion-judged ("is this done").

Launch and Monitoring are therefore **not two parallel systems** — and not even two sequential phases. Launch is a *temporary product state*, exactly as Inventory Override is: a launching product is monitored **concurrently**, against launch-keyed thresholds, with fewer applicable metrics (SALES is monitoring-only because a launching SKU has no history to compare against). Launch is an overlay on one continuously observed product, not a stage before observation begins.

More than that: **Launch depends on Monitoring's kind of evaluation.** Half the launch gates are not task checklists at all — Gate `stock-ready` ("60–80 fulfillable units, excluding Vine") is a threshold check; so are `phase-one-complete` ("~10 units/day, organic above 40%") and `graduated` ("TACOS falling, rating stable at 4.5"). The model reflects this directly (see `GateCondition` below) instead of pretending every gate is a pile of TASK rows.

| | TASK side (launch work) | CHECK side (observation) |
|---|---|---|
| Judged by | completion / attestation | value vs. stage-keyed threshold |
| Ordering logic | commitment-gate sequence | cause order (root cause wins) |
| Definition owned by | repo: versioned playbook | repo: versioned metric registry |
| Runtime state owned by | Postgres (position, outcomes) + ClickUp (human completion) | Postgres (runs, observations) |

Both sides converge on **one output shape** — the `AttentionItem`: *product · discipline · severity · evidence · due*. The derivation differs completely; the result has one shape, one dedup/collapse mechanism, one delivery path, one permission model. That convergence point (the `briefing` context, below) is where "complement, don't duplicate" is actually cashed in — not in a forced super-abstraction over TASK and CHECK, which stay separate because their ordering logic genuinely does not transfer between stages.

## Strategic map

**Domain:** marketplace commerce operations.

| Subdomain | Class | Bounded context (module) |
|---|---|---|
| Launch execution — gates, conditions, timing, approvals | **Core** | `launch` |
| Observation — metric registry, evaluation, runs | **Core** | `monitoring` |
| Briefing — collapse, severity, routing, delivery discipline | **Core** | `briefing` |
| Product catalog & lifecycle — identity, stage, posture | Supporting | `catalog` |
| Work-tracking sync — ClickUp mapping & reconciliation | Supporting | consuming modules' infrastructure (ACL) |
| Access — who may see/do what, from Slack or HTTP | Supporting | `access` (thin; enforced at adapters) |
| Cross-module Q&A and orchestration — Omni | Supporting (grows toward core) | `omni_agent` (process manager, not a peer) |
| Marketplace data, Slack conversation, scheduling | Generic | adapters; marketplace **deferred**, port-only |

Future contexts (`support`, `product_research`, `marketing`) arrive as sibling modules; nothing above assumes their shape.

```
                    ┌──────────────────────────────────────────┐
                    │ shared (kernel — vocabulary, no behavior)│
                    │ ProductId · Sku · Asin · MarketplaceId   │
                    │ Discipline · LifecycleStage · Severity   │
                    │ Verdict · EvidenceRef · Cadence          │
                    └──────────────────────────────────────────┘
                                   ▲ everyone speaks this
    ┌──────────────────────────────┼──────────────────────────────┐
┌───┴──────────┐         ┌─────────┴────────┐          ┌──────────┴─────┐
│  catalog     │         │  launch   CORE   │          │ monitoring CORE│
│  SUPPORTING  │◄──stage─│ Playbook (defn)  │─reads───►│ MetricRegistry │
│  Product,    │  stamp  │ Launch (instance)│ metric   │ MonitoringRun  │
│  Lifecycle   │         │ gates·conditions │ verdicts │ ThresholdSet   │
└──────────────┘         └────────┬─────────┘          └───────┬────────┘
                                  │   both emit AttentionItems │
                                  └──────────────┬─────────────┘
                                                 ▼
                          ┌────────────────────────────────────────┐
                          │ briefing  CORE  (LOOKER as domain code)│
                          │ cause-order collapse · severity tiers  │
                          │ silent-when-clean · state-gates-action │
                          └─────────┬───────────────────┬──────────┘
                                    │                   │
                      ClickUp tasks ▼                   ▼ Slack delivery
                                            ┌──────────────────────┐
                                            │ omni_agent           │
                                            │ Q&A over public      │
                                            │ surfaces + AccessScope│
                                            └──────────────────────┘
        ┌───────────────────────────────────────────┐
        │ marketplace  GENERIC · DEFERRED (port only)│ Amazon SP-API / Ads
        └───────────────────────────────────────────┘
```

## Bounded contexts in detail

Everything named below in **domain layer** terms is deterministic, I/O-free code in that module's `domain/` folder — readable as the business rules themselves, showable to managers. LangGraph appears only where flagged.

### `catalog` — product identity & lifecycle (supporting)

The one place that answers "which products exist and what stage is each in". Everyone else references products by ID and reads the stamp.

- **Aggregate: `Product`** (root)
  - identity `ProductId`; `Sku` (VO, unique), `Asin` (VO, optional until live), `MarketplaceId` (VO), name — `Asin` and `MarketplaceId` singular *for now*, a shape that already leans one way on the multi-marketplace question (see open questions).
  - **`LifecycleStage`** (VO — a small state machine): `Development → Launching(phase 1..4) → SteadyState(posture) → Retired`, where `posture ∈ {Scale, Optimize, Hold, Recover, InventoryOverride}`. `Launching` and `InventoryOverride` are the two *temporary* states.
  - Invariants: legal transitions only; temporary states carry an exit window (Hold > 2w / Recover > 4w forces a decision — `strategy.temp_state_expiry`).
  - Stage changes are **human-confirmed** (quarterly review; graduation event) — the system never self-stamps a posture (`strategy.state`).
- Domain events: `StageChanged`.
- Deliberately *not* a rich context: no launch knowledge, no metric knowledge. Listing *content* (copy, images, A+) is a future sibling context, not part of `catalog` — see open questions on naming.

### `launch` — the launch execution engine (core)

Runs a product from commitment to graduation against a versioned playbook.

- **`PlaybookDefinition`** — versioned, repo-owned (YAML), loaded and validated, never mutated or persisted. A specification object, not an aggregate.
  - `Gate` (VO): id, position, `OpeningMode` (automatic | requires-confirmation), and its **`GateCondition`s**:

    ```
    GateCondition = StepObligation(step_id)              ← TASK: a person/agent does it
                  | MetricCondition(metric_id, threshold)← CHECK: observation satisfies it
    ```

    This split is what makes `stock-ready`, `phase-one-complete` and `graduated` modelable as what they are. Until marketplace access lands, a `MetricCondition` is satisfied by **human attestation** through the same recording path; when live data arrives, `monitoring` evaluates it — the domain model does not change. That is the marketplace deferral done cleanly.
  - `StepDefinition` (VO) — the shipped `launch-playbook` spec mandates the full attribute set, and the map carries all of it: id, gate, owning `Discipline` (`Track` in today's code), **`Scope`** (the product itself | the product on one marketplace), `TimingAnchor` (VO: offset | window | open-ended | recurring, anchored to launch date), **`Binding`** (framework — a rule the launch is held to | lesson — advice), blocking flag, rule policy (optional while the team's decision is outstanding), **provenance** (optional citation into `docs/reference/`, e.g. `lp.finance.006` — a citation only, never an identifier) — and two **orthogonal axes** that must not be collapsed into one "step kind" (the current `launch_playbook.py` already has them separate, and correctly):

    ```
    ExecutionMode = automated | ai-assisted | human-attested        ← HOW it gets resolved
    Hazard        = none | prohibited-tactic | compliance-obligation ← WHAT RISK it carries
    ```

    `ai-assisted` is the per-step LLM seam — judgment-shaped work opts in here, step by step, never per-agent. The two hazard values behave oppositely: a `prohibited-tactic`'s only terminal state is refusal, so it can never be satisfied and never blocks a gate; a `compliance-obligation` (EPR / WEEE / GPSR / VAT — legal requirements, per `docs/reference/README.md`'s correction of the source's uniform "TOS RISK" label) must be satisfied and may block freely. Collapsing the axes would make a compliance obligation indistinguishable from a plain human task. `Binding` carries a candidate rule of its own: advice that blocks a gate the same way a framework rule does is a category error, so a `lesson` step should not block — not yet an invariant in the shipped spec or code, to be added when a change next touches the playbook.
  - Coherence invariants at load: a `prohibited-tactic` never blocks a gate; an `automated` step must carry a rule policy; gate positions total and unique. Eight gates: `commit → order → listable → stock-ready → live → ignition → phase-one-complete → graduated` (already in `openspec/specs/launch-playbook`).
- **Aggregate: `Launch`** (root) — one per product per playbook run. One aggregate for the whole run (all invariants in one place; ~100–150 step rows per product is not a scale problem), with per-gate splitting as the documented escape hatch if it ever is.
  - `ProductId` ref (by ID only), `PlaybookVersion`, `LaunchDate` (VO, movable), current `GatePosition`.
  - `StepProgress` (per step): a **`StepOutcome`** — not a boolean — plus completion **provenance**: source (`clickup` | `automated` | `attestation`), who, when, evidence. Given the webhook-drift obligation the README names, where a completion came from belongs in the model, not only in the sync code.

    ```
    StepOutcome = NotStarted | InProgress | Satisfied | Blocked(reason)
                | Refused                  ← the only terminal state a prohibited-tactic can reach
                | NotApplicable(reason)    ← "missing is not fine": absent and inapplicable differ
    ```

  - `GateApproval` (VO): decision, approver, timestamp — required for confirmation gates. `MetricAttestation` (VO): a human's recorded satisfaction of a `MetricCondition`, with evidence.
  - Invariants: gates advance monotonically, never skipped; a gate opens only when every blocking condition attached to it is satisfied; a confirmation gate additionally requires an approval; a `Refused` outcome can never satisfy anything; every step's due date derives from `LaunchDate + TimingAnchor`; completion from ClickUp is *recorded*, never inferred.
  - Domain events: `LaunchStarted`, `StepSatisfied`, `StepRefused`, `GateOpened`, `GateBlocked`, `LaunchDateMoved`, `LaunchDateAtRisk`, `LaunchGraduated` (→ catalog stamps `SteadyState`, → monitoring switches the product to steady-state thresholds).
  - `LaunchDateMoved` has a wide blast radius by design: lead time is "90 days = 60 production + 30 sea" (`lp.strategy.011`) and sea freight slips constantly. When the date moves, **every timing anchor re-resolves at once** — due dates, at-risk judgements, and already-created ClickUp tasks all cascade from this one event. It is a first-class domain occurrence, not a field edit.
- **State ownership** (from README, unchanged): repo owns the definition, Postgres owns position/outcomes, ClickUp owns human completion; a periodic reconciliation pass covers webhook drift.
- LangGraph here: none in the engine. Later: conversational step assistance, creative/copy generation — always *around* the engine, never deciding gate logic.

### `monitoring` — observation and evaluation (core)

Watches every product — launching ones included, against launch-keyed thresholds.

- **`MetricRegistry`** — versioned, repo-owned; the CHECK-side twin of the playbook.
  - `MetricDefinition` (VO): `MetricId`, owning `Discipline`, what is checked, `ThresholdSet` **keyed by LifecycleStage** — the same metric, one ID, different thresholds per stage. This dissolves the reference's open "two registries, two ID schemes" defect by construction: there is never a second registry to reconcile.
  - `Cadence` (VO), `ComparisonWindow` (VO: DoD | WoW | MoM | YoY-same-week | vs-plan-if-exists), escalation route, provenance.
- **Aggregate: `MonitoringRun`** (root) — one per cadence firing.
  - Lifecycle: `started → observations-collected → validated → handed to briefing`.
  - `Observation` (VO — the report contract): metric_id, entity, market, period, comparison, value, prior, delta, `Verdict` (finding | no-finding | cannot-answer), `EvidenceRef`, `DataFreshness`.
  - Invariants: an observation failing the contract is **rejected, not interpreted**; stale data is not a finding; *cannot-answer* ≠ *no-finding*; only reported numbers exist downstream.
- **One deterministic evaluation engine, not eleven agents**: the reference's discipline agents (SALES, PPC, INVENTORY, RANK, PRICE, FINANCE, TRAFFIC, LISTING, CUSTOMER, HEALTH, EXTERNAL) collapse into a `Discipline` field partitioning one registry, evaluated by one engine over per-discipline collector ports. Read as code, their rules are rule chains ("first driver question that applies wins"), not judgment. A genuinely judgment-shaped check opts into LLM assistance per-check (`ai-assisted` execution mode on its definition), not per-agent.
- **Blocked on marketplace access** only for real collectors — the whole domain layer (registry, contract, run lifecycle) is buildable and testable now against stubs; gate `MetricCondition`s run on attestation meanwhile.

### `briefing` — the convergence point (core; LOOKER as domain code)

Both sides hand their raw results here; this context owns the discipline of *what the team actually sees*. Its rules are substantial, and they are exactly the ones both sides would otherwise duplicate:

- **Aggregate: `Briefing`** (root): period, `Recipient`/`Audience`, `AttentionItem`s; knows whether it is clean — and a clean briefing is **not sent**.
- `AttentionItem` (VO): product · discipline · severity · evidence · due — produced from launch outcomes (blocked gates, at-risk dates, overdue steps) and from monitoring findings alike.
- **`CauseOrder`** — *the order is data, the collapse is code*: one shared collapse mechanism; monitoring supplies its 8-level order (availability > price > listing > competitor > demand > traffic > conversion > advertising), launch supplies its own ("blocking gate first"). One stockout is one item with symptoms attached, not five alerts.
- `SignificanceTier`: <10% noise / 10–20% monitor / 20–35% diagnose / >35% critical, binary events always critical, and the carve-out: SKUs under 2 units/day are exempt from percentage tiers.
- **State gates action**: a product in `Hold` or `Recover` never gets an aggressive recommendation.
- **Traceability**: every number carries metric_id + evidence_ref or the item is rejected.
- Routing: to a person (Slack), to a ClickUp task, or to another rule's owner.
- **SKAUT sits behind this** as the one interpretation LLM (LangGraph): it turns a validated `Briefing` into `Recommendation`s; every number it states traces to a metric_id + evidence_ref, and anything beyond the findings is labelled hypothesis. Whether `Recommendation` persists as its own aggregate is an open question.

### `omni_agent` — cross-module Q&A and, later, orchestration

- Thin, deliberately. Its tools are **exactly the `application/__init__.py` exports** of the domain modules, called with the asker's `AccessScope`. The rule with teeth: **if Omni can't answer a question, the fix is to add a use case to a module's public surface — never to give Omni database access.** That is SKAUT's traceability rule expressed as architecture.
- Direction (per README): a process-manager/saga role sequencing peer modules through their public APIs — never a peer module holding domain state of its own.

### `access` — who may see what (supporting, thin)

Required the moment Omni answers arbitrary askers in Slack. Two distinct questions, two mechanisms:

- *"May this person call this?"* — guards at the driving adapters (FastAPI `Depends()`, Slack middleware), Nest-guard style.
- *"Which products may this person see?"* — row-level, and it cannot live in middleware. Adapter resolves identity → `AccessScope` (VO: product/marketplace visibility, capability flags like *approve gates*, *see finance*) → **every read use case takes the scope as a parameter and filters by it**. The domain never authenticates; Omni forwards the asker's scope and has no privileges of its own.
- Constraint this puts on the whole map: every read model is scope-aware **from day one**, not retrofitted — `briefing` and `omni_agent` read the same projections.
- Model: `Principal` (root): identity (Slack user / API caller), roles; `AccessScope` derived from it.

### `shared` — kernel, kept deliberately anemic

Cross-context *vocabulary* only — identity VOs (`ProductId`, `Sku`, `Asin`, `MarketplaceId`, `MetricId`) and the enums everyone speaks (`Discipline`, `LifecycleStage`, `Severity`, `Verdict`, `Cadence`, `EvidenceRef`) — plus cross-cutting infra (settings, Slack plumbing, ClickUp client, trigger guard). Vocabulary, never behavior: stage *transitions* belong to `catalog`, threshold *evaluation* to `monitoring`. The moment something in `shared/domain` grows rules two modules argue about, it moves to one of them.

## Where the reference's 14 agents went

The roster is an *ownership taxonomy*, not an implementation demand. 14 agents → one deterministic evaluation engine + roughly three real LLM seams:

| Reference agent | Here |
|---|---|
| 11 discipline agents | `Discipline` tag partitioning the registries + one evaluation engine + per-discipline collector ports. Deterministic. |
| LOOKER | the `briefing` context's domain code + the run orchestrator. "No data access, no interpretation" holds by construction — it only ever sees contract VOs. |
| SKAUT | the interpretation graph behind `briefing`. The only LLM with raw-data tools; every number traces. |
| STRATEGY | split: posture stamping → `catalog` (human-confirmed); launch project state → the `Launch` aggregate; transition triggers → ordinary `monitoring` checks. |
| SETUP | human-attested step definitions + future integrations. |
| CREATIVE | step definitions now; a genuine generation LLM seam later, inside `launch`'s orbit. |
| Omni | the conversational LLM over public surfaces. |

## The path — incremental, each slice a reviewable change

Modules appear when domain work needs them (README's incremental rule): the MVP is five modules plus `shared`, not eight.

| # | Slice | Modules | Gated on |
|---|---|---|---|
| 1 | Shared vocabulary + `catalog`: Product, `LifecycleStage`, stage stamp split out of the launch record | `shared`, `catalog` | — |
| 2 | Playbook definition completed: `GateCondition` split, `StepOutcome`, timing anchors — plus a "which steps still have no OUR-RULE decision?" report | `launch` | — |
| 3 | **The `Launch` aggregate**: gate evaluation, outcomes, attestations, approvals, due dates, events — the heart of the MVP | `launch` | — |
| 4 | ClickUp completion loop: step↔task mapping, webhook intake, reconciliation pass | `launch` infra | — |
| 5 | `briefing` with the launch-side cause order: AttentionItems, severity, silent-when-clean, Slack delivery + gate-confirmation requests | `briefing` | — |
| 6 | `access` scope + scope-aware read use cases; Omni rewired over public surfaces | `access`, `omni_agent` | — |
| — | **MVP line** | | |
| 7 | Metric registry + evaluation engine on stub collectors; gate `MetricCondition`s switch from attestation where data exists | `monitoring` | — |
| 8 | Marketplace adapters → live observations | marketplace ports | 🔒 external API access |
| 9 | SKAUT interpretation graph → `Recommendation` | `briefing` | needs 7–8 |
| 10 | Launch-keyed threshold refinement; future contexts (support, research, marketing) as new modules | … | — |

Slices 5 and 6 are where the anti-duplication investment pays: if `briefing` and `AccessScope` are built stage-generically there, slice 7 is mostly *data* (metric definitions in YAML) plus one engine — not a second system. Slices 1–6 need zero marketplace access, consistent with the README's "no change is sequenced as depending on a marketplace adapter".

## Open questions (to settle as changes reach them)

- **The empty OUR RULE / DECISION column — a business decision, not technical.** All 358 reference rows say what Titan teaches, never what *we* do. Does the MVP run purely on human attestation with rule policies filled in later, or is capturing "our rule" per step in scope? This changes slice 2 substantially. The slice-2 report exists to make the gap visible either way.
- **Naming collision**: `catalog` here means product *identity*, but README lists "AI-assisted listing/catalog management" (listing *content*) as a future domain. Settle the pair before slice 1 — e.g. `catalog` = identity + `listing` = content, or `product` = identity + `catalog` = content. Also one word for the ownership tag (reference says AGENT, today's code says `Track`, this map says `Discipline`) — whichever is chosen is the word managers read in `domain/`.
- **`Launch` aggregate boundary**: one aggregate per run (current lean — all invariants in one place) vs. per-gate passage aggregates; revisit only if size actually hurts.
- Is `Recommendation` persisted as its own aggregate (history, follow-up tracking) or emitted as a delivered artifact only?
- **Multi-marketplace — genuinely open, but the current shape already leans.** A singular `MarketplaceId`/`Asin` on `Product` half-decides one-product-one-marketplace; yet the shipped spec's `Scope.MARKET` (a step scoped to the product *on one marketplace*) only means anything if a product can exist on several. The first change touching `catalog` must decide: either `Product` grows per-marketplace identifiers/listings, or `Scope.MARKET` is dead weight. Is a launch then per (product, marketplace) or per product?
- Where do *vs-plan* comparisons get their plan? (A future `planning` concern; skipped-not-failed when absent, per the reference.)
- Does ClickUp mapping stay per-module infrastructure, or does a dedicated `work` context become warranted once briefing also routes findings into ClickUp tasks? (Lean: infrastructure until the mapping grows rules of its own.)
- The seven open SALES rules in the reference need team decisions before that discipline's checks are authored.
