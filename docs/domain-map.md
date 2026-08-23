# Domain map — the high-level vision

**Status: living document.** This is the top-level map of the business domain and the intended shape of the system — the picture we steer by, not a contract. It is expected to change as work details it; when a real change diverges from this map, update the map in the same change. Authoritative behavior lives in `openspec/specs/`; this document records the *model* those specs incrementally realize. That relationship cuts both ways: where a shipped spec already mandates a detail, the map may summarize it but never silently drop it — a change written from the map must never regress a spec.

## The business in one paragraph

The company sells physical products through online marketplaces (Amazon first). Every product moves through one lifecycle: it is **validated and committed**, **launched** (a gated, roughly T-90 → T+120 sequence of work), then **operated in steady state**, where it is continuously **monitored** against a registry of metric rules — each with a cadence and an escalation route — and periodically re-postured (Scale / Optimize / Hold / Recover). The ops team works in Slack and ClickUp; the system's job is to hold the process so no step and no signal depends on a person remembering it.

## The unifying axis: Product × Stage, TASK × CHECK

Two principles carry the whole model:

- **Stage is an attribute of the product**, not of whoever owns a rule.
- **Launch work and observation differ by row type, not by owner**: a CHECK is recurring and threshold-judged ("is this within range"); a TASK is one-time and completion-judged ("is this done").

Launch and Monitoring are therefore **not two parallel systems** — and not even two sequential phases. Launch is a *temporary product state*, exactly as Inventory Override is: a launching product is monitored **concurrently**, against launch-keyed thresholds, with fewer applicable metrics (sales-trend checks apply only in steady state — a launching SKU has no history to compare against). Launch is an overlay on one continuously observed product, not a stage before observation begins.

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
                          │ briefing  CORE — the convergence point │
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
  - Invariants: legal transitions only; temporary states carry an exit window (Hold > 2w / Recover > 4w forces a decision, defaulting to Optimize).
  - Stage changes are **human-confirmed** (quarterly review; graduation event) — the system never self-stamps a posture.
- Domain events: `StageChanged`.
- Deliberately *not* a rich context: no launch knowledge, no metric knowledge. Listing *content* (copy, images, A+) is a future sibling context, not part of `catalog` — see open questions on naming.

### `launch` — the launch execution engine (core)

Runs a product from commitment to graduation against a versioned playbook.

- **`PlaybookDefinition`** — versioned, repo-owned (YAML), loaded and validated, never mutated or persisted. A specification object, not an aggregate. Versioning cut-off (recorded 2026-08-23, `complete-playbook-definition`): the shipped `v1` file is edited in place while no real launch has been started against it; from slice 3 on — once a `Launch` records the version it runs under — a definition change means a new version.
  - `Gate` (VO): id, position, `OpeningMode` (automatic | requires-confirmation), and its **`GateCondition`s**:

    ```
    GateCondition = StepObligation(step_id)              ← TASK: a person/agent does it
                  | MetricCondition(metric_id, threshold)← CHECK: observation satisfies it
    ```

    This split is what makes `stock-ready`, `phase-one-complete` and `graduated` modelable as what they are. Until marketplace access lands, a `MetricCondition` is satisfied by **human attestation** through the same recording path; when live data arrives, `monitoring` evaluates it — the domain model does not change. That is the marketplace deferral done cleanly.
  - `StepDefinition` (VO) — the shipped `launch-playbook` spec mandates the full attribute set, and the map carries all of it: id, gate, owning `Discipline` (shared vocabulary), **`Scope`** (the product itself | the product on one marketplace), `TimingAnchor` (VO: offset | window | open-ended | recurring, anchored to launch date), **`Binding`** (framework — a rule the launch is held to | lesson — advice), blocking flag, rule policy (optional while the team's decision is outstanding), **provenance** (an optional citation into whatever source material a step derives from — a citation only, never an identifier) — and two **orthogonal axes** that must not be collapsed into one "step kind" (the current `launch_playbook.py` already has them separate, and correctly):

    ```
    ExecutionMode = automated | ai-assisted | human-attested        ← HOW it gets resolved
    Hazard        = none | prohibited-tactic | compliance-obligation ← WHAT RISK it carries
    ```

    `ai-assisted` is the per-step LLM seam — judgment-shaped work opts in here, step by step, never per-agent. The two hazard values behave oppositely: a `prohibited-tactic`'s only terminal state is refusal, so it can never be satisfied and never blocks a gate; a `compliance-obligation` (EPR / WEEE / GPSR / VAT — legal requirements) must be satisfied and may block freely. Collapsing the axes would make a compliance obligation indistinguishable from a plain human task. `Binding` carries a rule of its own: advice that blocks a gate the same way a framework rule does is a category error, so a `lesson` step cannot block — a load-time coherence invariant since `complete-playbook-definition` (2026-08-23).
  - Coherence invariants at load: a `prohibited-tactic` never blocks a gate; an `automated` step must carry a rule policy; gate positions total and unique. Eight gates: `commit → order → listable → stock-ready → live → ignition → phase-one-complete → graduated` (already in `openspec/specs/launch-playbook`).
- **Aggregate: `Launch`** (root) — one per product per playbook run. One aggregate for the whole run (all invariants in one place; ~100–150 step rows per product is not a scale problem), with per-gate splitting as the documented escape hatch if it ever is.
  - `ProductId` ref (by ID only), `PlaybookVersion`, `LaunchDate` (VO, movable), current `GatePosition`.
  - `StepProgress` (per step): a **`StepOutcome`** — not a boolean — plus completion **provenance**: source (`clickup` | `automated` | `attestation`), who, when, evidence. Given the webhook-drift obligation the README names, where a completion came from belongs in the model, not only in the sync code.

    ```
    StepOutcome = NotStarted | InProgress | Satisfied | Blocked(reason)
                | Refused                  ← the only terminal state a prohibited-tactic can reach
                | NotApplicable(reason)    ← "missing is not fine": absent and inapplicable differ
    ```

  - `GateApproval` (VO): decision (approving | rejecting — only an approving decision opens a gate), approver, timestamp — required for confirmation gates. The graduation approval additionally carries the **approver-chosen `Posture`**: catalog's "the system never self-stamps a posture" means no default posture is legal, so the human approving graduation chooses the steady state the product enters (recorded 2026-08-23, `introduce-launch-aggregate`). `MetricAttestation` (VO): a human's recorded satisfaction of a `MetricCondition`, with evidence.
  - Invariants: gates advance monotonically, never skipped; a gate opens only when every blocking condition attached to it is satisfied; a confirmation gate additionally requires an approval; a `Refused` outcome can never satisfy anything; every step's due date derives from `LaunchDate + TimingAnchor`; completion from ClickUp is *recorded*, never inferred. The **at-risk rule** (recorded 2026-08-23, `introduce-launch-aggregate`): the launch date is at risk exactly when a blocking step's due period has fully passed without the step reaching a permitted terminal outcome — evaluated as of a given date, the clock never lives in the domain.
  - Domain events: `LaunchStarted`, `StepSatisfied`, `StepRefused`, `GateOpened`, `GateBlocked`, `LaunchDateMoved`, `LaunchDateAtRisk`, `LaunchGraduated` (→ catalog stamps `SteadyState`, → monitoring switches the product to steady-state thresholds).
  - `LaunchDateMoved` has a wide blast radius by design: production and sea-freight lead times dominate the launch calendar and slip constantly. When the date moves, **every timing anchor re-resolves at once** — due dates, at-risk judgements, and already-created ClickUp tasks all cascade from this one event. It is a first-class domain occurrence, not a field edit.
- **State ownership** (from README, unchanged): repo owns the definition, Postgres owns position/outcomes, ClickUp owns human completion; a periodic reconciliation pass covers webhook drift. Realized in slice 4 (`add-clickup-completion-loop`, 2026-08-23) with three details worth carrying here, because each settles a question the map left open:
  - **One ClickUp list per launch**, created in a configured folder and named from the catalog product's name and SKU — the `ProductId` is opaque and is never parsed for meaning.
  - **Only `human-attested`, non-`prohibited-tactic` steps are projected as tasks.** A `prohibited-tactic` step's only terminal state is refusal, so offering a person a task to tick would invite them to complete the thing the model says is uncompletable.
  - **Completion travels one way and is keyed on transitions, not on state.** Each mapped task retains the closed state last observed for it; an outcome is recorded only when a fresh reading differs (closed ⇒ `Satisfied`, reopened ⇒ `InProgress`). It is never compared against the step's *recorded* outcome — a read exposes state, not history, so that comparison would overwrite an attested `Satisfied` with `InProgress` on the next pass. The system never writes a task's status back to ClickUp, so an attested step and a still-open task are an expected pair, not a drift to repair.
- LangGraph here: none in the engine. Later: conversational step assistance, creative/copy generation — always *around* the engine, never deciding gate logic.

### `monitoring` — observation and evaluation (core)

Watches every product — launching ones included, against launch-keyed thresholds.

- **`MetricRegistry`** — versioned, repo-owned; the CHECK-side twin of the playbook.
  - `MetricDefinition` (VO): `MetricId`, owning `Discipline`, what is checked, `ThresholdSet` **keyed by LifecycleStage** — the same metric, one ID, different thresholds per stage; there is never a second registry to reconcile.
  - `Cadence` (VO), `ComparisonWindow` (VO: DoD | WoW | MoM | YoY-same-week | vs-plan-if-exists), escalation route, provenance.
- **Aggregate: `MonitoringRun`** (root) — one per cadence firing.
  - Lifecycle: `started → observations-collected → validated → handed to briefing`.
  - `Observation` (VO — the report contract): metric_id, entity, market, period, comparison, value, prior, delta, `Verdict` (finding | no-finding | cannot-answer), `EvidenceRef`, `DataFreshness`.
  - Invariants: an observation failing the contract is **rejected, not interpreted**; stale data is not a finding; *cannot-answer* ≠ *no-finding*; only reported numbers exist downstream.
- **One deterministic evaluation engine, not eleven agents**: the disciplines (sales, PPC, inventory, rank, price, finance, traffic, listing, customer, health, external) are a `Discipline` field partitioning one registry, evaluated by one engine over per-discipline collector ports — read as code, discipline rules are deterministic rule chains, not judgment. A genuinely judgment-shaped check opts into LLM assistance per-check (`ai-assisted` execution mode on its definition), not per-discipline. Across the whole system the genuine LLM seams are three: interpretation (behind `briefing`), generation (creative and copy, in `launch`'s orbit), and conversation (Omni).
- **Blocked on marketplace access** only for real collectors — the whole domain layer (registry, contract, run lifecycle) is buildable and testable now against stubs; gate `MetricCondition`s run on attestation meanwhile.

### `briefing` — the convergence point (core)

Both sides hand their raw results here; this context owns the discipline of *what the team actually sees*. Its rules are substantial, and they are exactly the ones both sides would otherwise duplicate:

- **Aggregate: `Briefing`** (root): period, `Recipient`/`Audience`, `AttentionItem`s; knows whether it is clean — and a clean briefing is **not sent**.
- `AttentionItem` (VO): product · discipline · severity · evidence · due — produced from launch outcomes (blocked gates, at-risk dates, overdue steps) and from monitoring findings alike.
- **`CauseOrder`** — *the order is data, the collapse is code*: one shared collapse mechanism; monitoring supplies its 8-level order (availability > price > listing > competitor > demand > traffic > conversion > advertising), launch supplies its own ("blocking gate first"). One stockout is one item with symptoms attached, not five alerts.
- `SignificanceTier`: <10% noise / 10–20% monitor / 20–35% diagnose / >35% critical, binary events always critical, and the carve-out: SKUs under 2 units/day are exempt from percentage tiers.
- **State gates action**: a product in `Hold` or `Recover` never gets an aggressive recommendation.
- **Traceability**: every number carries metric_id + evidence_ref or the item is rejected.
- Routing: to a person (Slack), to a ClickUp task, or to another rule's owner.
- **The interpretation agent sits behind this** — the one interpretation LLM seam (LangGraph): it turns a validated `Briefing` into `Recommendation`s; every number it states traces to a metric_id + evidence_ref, and anything beyond the findings is labelled hypothesis. Whether `Recommendation` persists as its own aggregate is an open question.

Realized on the launch side in slice 5 (`introduce-launch-briefing`, 2026-08-23), with six details worth carrying here because each settles something the map left open:

- **Digest semantics, not alarm semantics.** Each daily briefing reports every attention item open *that day*; a clean day sends nothing. There is deliberately no cross-briefing memory — no suppression table, no persisted `Briefing`, no new tables at all. A long-standing item is therefore repeated daily, accepted as the cost of a briefing being a digest rather than an alarm; alarm-style suppression (the shape `scheduled-jobs`' overdue check already uses) stays available as a purely additive later change.
- **`Severity` is three tiers in `shared`** — `monitor | diagnose | critical` — the *reporting* tiers of `SignificanceTier`. The `<10%` noise band is not a severity: something not worth reporting produces no item, so there is nothing for a fourth member to grade. Monitoring's percentage bands grade into these same three in slice 7, which is the "never a second scale to reconcile" rule cashed in.
- **Launch's cause order and grading, as data**: `launch-date-at-risk` (CRITICAL — a binary event) > `gate-awaiting-confirmation` (DIAGNOSE — a human decision is due and progression is paused on it) > `overdue-step` (MONITOR). Absorption is **by fact, not by cause**: the at-risk item names the overdue *blocking* steps that produced it and absorbs exactly those, so an overdue non-blocking step on the same launch still stands as its own item. Remaining overdue steps collapse one item per discipline.
- **Activeness is the catalog's answer, and it fails toward reporting.** A launch drops out of the briefing when its product's stage is steady-state or retired — never by anything the launch context knows about itself. A product the catalog cannot resolve is treated as **active** and identified by its raw id: losing an item to a failed name lookup is exactly the silent failure the briefing exists to prevent. This is also why launch's new enumeration is deliberately unfiltered, and separate from the ClickUp loop's `list_active` — a launch waiting at the `graduated` gate for its approval is precisely something to brief, and the persisted shape cannot tell it apart from one already through.
- **The report is the whole of what briefing may know.** Whether a step is overdue depends on its *hazard* (a `prohibited-tactic` step is resolved by `Refused`), so that judgement — along with each step's discipline and blocking flag — travels on the launch report rather than being re-derived outside the launch context. Slice 5 grew `LaunchReport` accordingly instead of giving briefing a playbook reader.
- **Briefing owns Slack delivery**, inheriting the retired daily product-name digest's schedule slot, tolerance and failure discipline: an *assembly* failure fails the run (so `scheduled-jobs` retries it and posts one message once retries are exhausted); a *delivery* failure is logged and the run succeeds. `product-monitoring` is emptied by this change and returns in slice 7 as the metric registry and evaluation engine.
- **Deferred deliberately**: interactive gate approval in Slack (Block Kit buttons wired to `approve_gate`) waits for slice 6, when `access` can say who may approve — a pending confirmation gate is a briefing *item* here, nothing more; and `EvidenceRef` stays briefing-owned rather than moving to `shared`, since the kernel rule is that vocabulary moves up when a second module needs it, not before.

### `omni_agent` — cross-module Q&A and, later, orchestration

- Thin, deliberately. Its tools are **exactly the `application/__init__.py` exports** of the domain modules, called with the asker's `AccessScope`. The rule with teeth: **if Omni can't answer a question, the fix is to add a use case to a module's public surface — never to give Omni database access.** That is the interpretation agent's traceability rule expressed as architecture.
- Direction (per README): a process-manager/saga role sequencing peer modules through their public APIs — never a peer module holding domain state of its own.

### `access` — who may see what (supporting, thin)

Required the moment Omni answers arbitrary askers in Slack. Two distinct questions, two mechanisms:

- *"May this person call this?"* — guards at the driving adapters (FastAPI `Depends()`, Slack middleware), Nest-guard style.
- *"Which products may this person see?"* — row-level, and it cannot live in middleware. Adapter resolves identity → `AccessScope` (VO: product/marketplace visibility, capability flags like *approve gates*, *see finance*) → **every read use case takes the scope as a parameter and filters by it**. The domain never authenticates; Omni forwards the asker's scope and has no privileges of its own.
- Constraint this puts on the whole map: every read model is scope-aware **from day one**, not retrofitted — `briefing` and `omni_agent` read the same projections.
- Model: `Principal` (root): identity (Slack user / API caller), roles; `AccessScope` derived from it.

### `shared` — kernel, kept deliberately anemic

Cross-context *vocabulary* only — identity VOs (`ProductId`, `Sku`, `Asin`, `MarketplaceId`, `MetricId`) and the enums everyone speaks (`Discipline`, `LifecycleStage`, `Severity`, `Verdict`, `Cadence`, `EvidenceRef`) — plus cross-cutting infra (settings, Slack plumbing, ClickUp client, trigger guard). Vocabulary, never behavior: stage *transitions* belong to `catalog`, threshold *evaluation* to `monitoring`. The moment something in `shared/domain` grows rules two modules argue about, it moves to one of them.

## The path — incremental, each slice a reviewable change

Modules appear when domain work needs them (README's incremental rule): the MVP is five modules plus `shared`, not eight.

| # | Slice | Modules | Gated on |
|---|---|---|---|
| 1 | Shared vocabulary + `catalog`: Product, `LifecycleStage`, stage stamp split out of the launch record | `shared`, `catalog` | — |
| 2 | Playbook definition completed: `GateCondition` split, `StepOutcome`, timing anchors — plus a report of steps whose rule policy is still undecided | `launch` | — |
| 3 | **The `Launch` aggregate**: gate evaluation, outcomes, attestations, approvals, due dates, events — the heart of the MVP — **realized** 2026-08-23 (`introduce-launch-aggregate`) | `launch` | — |
| 4 | **ClickUp completion loop**: per-launch list projection, step↔task mapping, webhook intake, reconciliation pass — **realized** 2026-08-23 (`add-clickup-completion-loop`) | `launch` infra | — |
| 5 | **`briefing` with the launch-side cause order**: AttentionItems, severity, silent-when-clean, Slack delivery + gate-confirmation requests — **realized** 2026-08-23 (`introduce-launch-briefing`) | `briefing` | — |
| 6 | `access` scope + scope-aware read use cases; Omni rewired over public surfaces | `access`, `omni_agent` | — |
| — | **MVP line** | | |
| 7 | Metric registry + evaluation engine on stub collectors; gate `MetricCondition`s switch from attestation where data exists | `monitoring` | — |
| 8 | Marketplace adapters → live observations | marketplace ports | 🔒 external API access |
| 9 | Interpretation graph → `Recommendation` | `briefing` | needs 7–8 |
| 10 | Launch-keyed threshold refinement; future contexts (support, research, marketing) as new modules | … | — |

Slices 5 and 6 are where the anti-duplication investment pays: if `briefing` and `AccessScope` are built stage-generically there, slice 7 is mostly *data* (metric definitions in YAML) plus one engine — not a second system. Slices 1–6 need zero marketplace access, consistent with the README's "no change is sequenced as depending on a marketplace adapter".

## Open questions (to settle as changes reach them)

- **Naming collision — settled** (2026-08-23, `introduce-catalog-and-shared-vocabulary`): `catalog` = product *identity* and lifecycle (the module built in slice 1); the future listing-*content* context will be named `listing`. The ownership tag is **`Discipline`**; the migration from the playbook's former `Track` landed with the shared enum's introduction in one step (2026-08-23, `complete-playbook-definition`), so two words for one concept never coexisted in code. The same change renamed the module holding the playbook from its pre-slice-1 name `products` to **`launch`**, the bounded-context name this map uses.
- **`Launch` aggregate boundary**: one aggregate per run (current lean — all invariants in one place) vs. per-gate passage aggregates; revisit only if size actually hurts.
- Is `Recommendation` persisted as its own aggregate (history, follow-up tracking) or emitted as a delivered artifact only?
- **Multi-marketplace — settled for now, with a recorded revisit trigger** (2026-08-23, `introduce-catalog-and-shared-vocabulary`): `Product` carries a singular required `MarketplaceId` and optional `Asin` — Amazon-first. `Scope.MARKET` on playbook steps stays as latent shape, deliberately. Revisit when the first real launch targets a second marketplace for an existing product, or when marketplace API access makes multi-market listings actionable; at that point `Product` grows per-marketplace listings and the launch key is reconsidered as (product, marketplace).
- Where do *vs-plan* comparisons get their plan? (A future `planning` concern; a missing plan is skipped, not failed.)
- Does ClickUp mapping stay per-module infrastructure, or does a dedicated `work` context become warranted once briefing also routes findings into ClickUp tasks? (Lean: infrastructure until the mapping grows rules of its own. Slice 4 built it that way — two tables and a sync module in `launch/infrastructure/`, with no domain object learning a ClickUp identifier — so the question stands unchanged, now with one implementation behind it.)
- **Deferred from slice 4** (`add-clickup-completion-loop`, 2026-08-23), each because no scenario needed it yet: mapping ClickUp custom statuses to `Blocked`/`NotApplicable` (which need a reason ClickUp has nowhere to carry); projecting `ai-assisted` steps or gate metric conditions; task bodies richer than a name; and registering the ClickUp webhook from inside the application rather than operationally.