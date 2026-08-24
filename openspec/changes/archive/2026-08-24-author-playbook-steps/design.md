## Context

`playbook_v1.yaml` ships eight gates with authored metric conditions and `steps: []`. The step schema, its load-time coherence rules (an `automated`/`ai-assisted` step must carry a rule policy; a `prohibited-tactic` step and a `lesson`-bound step can never block), the timing-anchor kinds, and the undecided-rule-policies report all exist and are tested. The source material is `docs/reference/product-launch.md` — 358 ID-bearing rows across ten areas, each carrying AGENT (discipline), WHEN (timing), SOURCE (citation), LAYER (FRAMEWORK/LESSON), and an `lp.<agent>.<nnn>` ID; rows marked TOS RISK are, per the document's own preamble, "tactics that risk suspension - listed so they are recognised and refused".

The versioning cut-off recorded in `docs/domain-map.md` (2026-08-23, `complete-playbook-definition`) permits editing `v1` in place while no real launch has been started against it. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**

- The `listable` gate carries the reference plan's BUILD THE LISTING area completely, because that is where the team's real work is right now.
- Every mechanism in the launch engine is exercised by at least one step: all four anchor kinds, all twelve disciplines, both non-none hazards, all three execution modes, blocking and non-blocking, framework and lesson.
- Every step traces to its source row (identifier and provenance).

**Non-Goals:**

- Full authoring of the other nine areas (~260 remaining rows). That is a follow-up change — it requires gate-assignment and blocking decisions the team has not made, and the document's "OUR RULE" column is deliberately theirs to fill.
- Deciding rule policies for human-attested steps. The undecided-rule-policies report existing is the mechanism for carrying that debt visibly.
- Any change to the step schema, loader, or coherence rules.

## Decisions

### 1. `v1` is edited in place, not versioned to `v2`

The recorded cut-off allows it while no launch has pinned `v1`. Before merge, confirm the deployment's `launch_positions` table is empty (or contains only disposable test rows — the pinned version is its `playbook_version` column); if a real launch exists by then, this change ships the same content as `v2` instead and the launch keeps resolving `v1`. Editing in place was chosen over always-`v2` because `ShippedPlaybooks` resolves exactly one version — shipping `v2` while nothing pins `v1` would leave dead content.

### 2. Column mapping from the reference document

| Reference column | Step field | Rule |
|---|---|---|
| ID (`lp.strategy.001`) | `identifier` | verbatim |
| AGENT | `discipline` | lowercase (STRATEGY → `strategy`) |
| WHEN | `timing_anchor` | table in Decision 3 |
| LAYER | `binding` | FRAMEWORK → `framework`, LESSON → `lesson` |
| SOURCE | `provenance` | verbatim citation string |
| TOS RISK marker | `hazard` | by substance, Decision 5 |

`scope` defaults to `product`; the EU/non-US marketplace rows (`lp.listing.018`, `lp.listing.020`) are `market`.

### 3. WHEN → timing anchor

| WHEN | Anchor |
|---|---|
| T-90 / T-60 / T-30 / T-15 / T-14 / T-7 | `offset` {days: -90 … -7} |
| Day 1 | `offset` {days: 0} (launch day is offset zero, per spec) |
| Week 1 | `window` {start: 0, end: 6} |
| Week 1-2 | `window` {start: 0, end: 13} |
| Week 2-4 | `window` {start: 7, end: 27} |
| Week 5-8 | `window` {start: 28, end: 55} |
| Day 60+ | `open-ended` {start: 59} (day N is offset N−1 under "Day 1 is offset 0") |
| Daily / Weekly / Biweekly / Monthly | `recurring` {cadence: …} |

### 4. Gate assignment: by the gate the work must precede, not by document area

Area 3 rows default to `listable`. Seven rows are reassigned because their own timing serves a later gate: `lp.ppc.001`–`004` (campaign construction → `live`), `lp.inventory.018` (shipment-creation caution → `stock-ready`), `lp.listing.023` and `lp.creative.023` (launch-day actions → `ignition`). The subset rows outside area 3 are assigned to the gate their WHEN and content precede (T-90 validation → `commit`, T-60 sourcing → `order`, T-7 go-live prep → `live`, Day 1/Week 1 → `ignition`, Weeks 2–8 → `phase-one-complete`, Day 60+ → `graduated`).

### 5. Hazard by substance, not by the TOS RISK label

`prohibited-tactic` is reserved for rows that name a tactic to refuse: `lp.listing.013` (Vine-stacking variation architecture), `lp.price.014` (friend-buys-at-list-price strike-through trigger), `lp.strategy.021` (friends-and-family drip purchases). TOS RISK rows that are cautions about mistakes rather than tactics (`lp.setup.020` GS1 record mismatch, `lp.inventory.018` barcode-convert prompt) stay hazard-`none` lessons — a caution can be *satisfied* by heeding it; a tactic can only be refused. `compliance-obligation` marks rows whose subject is a regulatory/marketplace-compliance duty: `lp.strategy.006`, `lp.setup.009`, `lp.setup.024`, `lp.listing.014`.

Alternative considered: mapping every TOS RISK row to `prohibited-tactic` (the document's own framing). Rejected because a `prohibited-tactic` step's only terminal outcome is `Refused` — recording `lp.setup.020` as "refused" would misstate work that is actually done by complying.

### 6. Blocking: framework-only structural spine

Only `framework` rows may block (coherence rule). Among them, blocking is given to steps whose absence genuinely leaves the gate's meaning unfulfilled, not to every framework row. Result: every gate holds at least one blocking step; `listable` holds eleven (the keyword-research chain, flat-file completeness, browse-path presence, product-document upload, main image, and the pre-live survey test). A+/Brand-Story steps are never blocking, because `lp.creative.023` (same document) states A+ must not delay launch — blocking `listable` on A+ would contradict the source.

### 7. Execution modes and rule policies

Two steps are non-human: `lp.traffic.001` is `automated` (a deterministic stop-rule) with rule policy `"stop-rule: if CTR and CVR have not improved over the window, halt external traffic and fix the listing first"`; `lp.listing.014` is `ai-assisted` (compliance-advisor pass over listing copy) with rule policy `"copy is run through the compliance advisor and flagged issues are resolved before publishing"`. Everything else is `human-attested` with no rule policy — deliberately, so the undecided-rule-policies report shows the real outstanding decisions.

### 8. Metric-condition rows are not duplicated as steps

The excluded restatement rows, enumerated: `lp.inventory.040`/`lp.inventory.041` restate `stock-ready`'s `units-fulfillable` condition; `lp.strategy.033` restates `phase-one-complete`'s `organic-share`; `lp.strategy.025` (critical mass ~10 units/day) restates its `sales-velocity`; `lp.ppc.048` (phase 1 graduated on conversions, all four must hold) restates that gate's condition bundle; `lp.finance.036` (steady-state TACoS benchmark) restates `graduated`'s `tacos`. No reference row purely restates `review-rating` (`lp.ppc.043` gates *spend scaling* on rating stability — a PPC practice, not the graduation condition — and is simply outside the curated subset). A step copy of any of these would make one obligation two; task 3.1 asserts these six IDs are absent.

## The authored step set (97 steps)

Notation: **F**/**L** binding, **✔** blocking, due as authored WHEN, hazard/execution noted only when not none/human-attested.

### `commit` (4)

| ID | Due | B | Blk | Notes |
|---|---|---|---|---|
| lp.strategy.001 product visibly better on the search page | T-90 | F | ✔ | |
| lp.finance.001 unit economics clear 70% CM1 / 35% CM2 | T-90 | F | ✔ | |
| lp.strategy.003 demand gate: 8 keywords ≥1,000 searches | T-90 | L | | |
| lp.strategy.006 hazmat / high-compliance category screen | T-90 | L | | compliance-obligation |

### `order` (3)

| lp.finance.010 terms: pay on ship, split first order | T-60 | F | ✔ | |
| lp.inventory.004 HS code verified via lookup + forwarder | T-90 | F | ✔ | |
| lp.setup.009 compliance testing booked pre-production | T-90 | L | | compliance-obligation |

### `listable` (65 — full BUILD THE LISTING)

Barcodes & listing creation:

| lp.setup.019 GS1 bought in the company's country | T-60 | L | | |
| lp.setup.020 GS1 record matches Seller Central exactly | T-60 | L | | |
| lp.setup.021 wait 3–5 days after UPC purchase | T-60 | L | | |
| lp.setup.022 create the listing before inventory ships | T-60 | L | | |
| lp.setup.023 keep the GTIN, no exemption | T-60 | L | | |
| lp.setup.024 category gating cleared via Qualification Center | T-60 | L | | compliance-obligation |
| lp.inventory.017 FNSKU vs manufacturer barcode decided | T-60 | L | | |

Keyword research & indexation:

| lp.strategy.015 competitor keyword map (ranked + missing) | T-60 | F | ✔ | |
| lp.rank.001 root keywords from competitor organics | T-60 | F | ✔ | |
| lp.rank.002 ONE launch keyword family chosen | T-30 | F | ✔ | |
| lp.rank.003 head term not attacked head-on | T-30 | F | | |
| lp.rank.004 keyword + competitor list loaded into tracking | T-60 | F | ✔ | |
| lp.rank.005 keyword sets ≤15,000 searches | T-30 | L | | |
| lp.rank.006 above-ceiling volume deployed in waves | T-30 | L | | |
| lp.rank.007 rank-ambition reality check | T-30 | L | | |
| lp.listing.019 top ~20% terms + competitor share mapped | T-30 | F | ✔ | |
| lp.listing.024 optimizer: phrase-form + coverage check | T-15 | L | | |
| lp.listing.025 Rufus questions documented and answered | T-30 | F | | |
| lp.listing.026 every researched keyword placed | T-14 | F | ✔ | |
| lp.listing.027 keyword research refreshed at 30 days out | T-30 | L | | |
| lp.listing.028 launch set = 10–20 mid-volume keywords | T-14 | L | | |

Listing content & structure:

| lp.listing.001 flat file, every attribute populated | T-30 | F | ✔ | |
| lp.listing.002 appears in competitors' browse paths | T-14 | F | ✔ | |
| lp.listing.006 full content pack before Add-a-Product | T-60 | L | | |
| lp.listing.007 sub-category picked deliberately | T-60 | L | | |
| lp.listing.008 flat files over UI once variations exist | T-60 | L | | |
| lp.listing.014 copy through compliance advisor pre-publish | T-14 | F | | compliance-obligation · ai-assisted |
| lp.listing.015 instructions + test-results PDFs uploaded | T-7 | F | ✔ | |
| lp.listing.016 badge eligibility reviewed | T-14 | F | | |
| lp.listing.017 assets uploaded while inactive, as each lands | T-15 | L | | |
| lp.listing.018 EU rollout sequenced so reviews port | T-30 | L | | scope: market |
| lp.listing.020 non-US volume tiers rescaled | T-14 | L | | scope: market |
| lp.listing.021 title rendering checked mobile + desktop | T-30 | F | | |
| lp.listing.022 all three release dates set far future | T-30 | L | | |
| lp.listing.029 title converts for top-20% terms, 2+ versions | T-30 | F | | |
| lp.listing.030 bullets/description/backend for indexation | T-30 | F | | |

Variation family:

| lp.listing.003 category/GL matched pre-parenting | T-30 | F | | |
| lp.listing.004 restructures in slow/OOS windows | T-30 | F | | |
| lp.listing.005 no weak child drags the parent | T-30 | F | | |
| lp.listing.009 parent carries no relationship type / SKU | T-60 | L | | |
| lp.listing.010 family designed so Amazon doesn't break it | T-60 | L | | |
| lp.listing.011 every child enriched; parent never advertised | T-60 | L | | |
| lp.listing.012 canonical URL set up | T-30 | L | | |
| lp.listing.013 Vine-stacking variation architecture | T-30 | L | | prohibited-tactic |

Creative:

| lp.strategy.016 CTR assets first: title, main image, price | T-30 | F | | |
| lp.creative.003 CTR elements tested 3–5× more | T-30 | F | | |
| lp.creative.004 every asset readable in a 17-second visit | T-30 | F | | |
| lp.creative.005 named owners: design / research / publish | T-60 | F | | |
| lp.creative.006 assets finished 1–2 weeks pre-launch | T-14 | L | | |
| lp.creative.007 competitors depositioned via review flaws | T-30 | L | | |
| lp.creative.008 main image scroll-stopping, unlike others | T-30 | F | ✔ | |
| lp.creative.009 titles + main images survey-tested pre-live | T-14 | F | ✔ | |
| lp.creative.010 image brief as concepts before design spend | T-60 | F | | |
| lp.creative.011 confirm / differentiate / set expectations | T-60 | F | | |
| lp.creative.012 competitor reviews mined | T-60 | F | | |
| lp.creative.013 launch video 15–20s | T-30 | F | | |
| lp.creative.014 tutorial asset wherever user error is likely | T-30 | F | | |
| lp.creative.015 photoshoot list + units out (budget a month) | T-30 | L | | |
| lp.creative.016 production-period samples to photographer | T-30 | L | | |
| lp.creative.017 listing look planned before launch | T-30 | L | | |
| lp.creative.018 pre-review window won on assets alone | T-30 | L | | |
| lp.creative.019 A+ modules answer the Rufus questions | T-30 | F | | never blocking (Decision 6) |
| lp.creative.020 ONE Brand Story for the whole brand | T-30 | F | | |
| lp.creative.021 Brand Story previewed desktop + mobile | T-14 | F | | |
| lp.creative.022 Brand Story carries blocked-elsewhere content | T-30 | F | | |

### `stock-ready` (3)

| lp.inventory.019 first order sized to 45–90 days cover | T-30 | F | ✔ | |
| lp.inventory.008 pre-shipment 3-foot drop test | T-30 | L | | |
| lp.inventory.018 never accept the barcode-convert prompt | T-30 | L | | reassigned from area 3 |

### `live` (9)

| lp.rank.008 listing indexing for the full keyword list | T-7 | F | ✔ | |
| lp.ppc.008 bid waterfall set from exact-match anchor | T-7 | F | ✔ | |
| lp.ppc.001 campaign naming convention fixed first | T-14 | F | ✔ | reassigned |
| lp.ppc.002 keywords bucketed at 1,000-search threshold | T-14 | F | ✔ | reassigned |
| lp.ppc.003 never-keywords list built | T-60 | F | ✔ | reassigned |
| lp.ppc.004 no launch keywords above 5,000 searches | T-14 | L | | reassigned |
| lp.listing.032 listing live 3–4 days before launch date | T-7 | L | | |
| lp.price.013 strike-through trigger, the compliant route | T-7 | L | | |
| lp.price.014 friend-buys-at-list-price trigger | T-7 | L | | prohibited-tactic |

### `ignition` (7)

| lp.ppc.010 broad campaigns launched first | Day 1 | F | ✔ | |
| lp.external.001 ignition: email ×3, social, influencers | Day 1 | L | | |
| lp.customer.007 Vine 30 units after strikethrough visible | Week 1 | L | | |
| lp.ppc.016 search-term report watched, negate hard | Daily | F | | recurring |
| lp.strategy.021 friends-and-family drip purchases | Week 1 | L | | prohibited-tactic |
| lp.listing.023 backdate release dates on launch day | Day 1 | L | | reassigned |
| lp.creative.023 A+ added shortly after launch | Day 1 | L | | reassigned |

### `phase-one-complete` (3)

| lp.ppc.029 single-keyword exacts on proven 1,000+ terms | Wk 2-4 | F | ✔ | |
| lp.customer.002 reviews/feedback read, negatives categorized | Weekly | F | | recurring |
| lp.traffic.001 traffic stop-rule: CTR/CVR flat → stop, fix | Wk 2-4 | F | | automated (Decision 7) |

### `graduated` (3)

| lp.strategy.030 stable availability + demand over 60 days | Day 60+ | F | ✔ | |
| lp.strategy.029 state & driver assigned via decision flow | Day 60+ | F | | |
| lp.finance.031 Fee Preview run, reimbursements filed | Day 60+ | F | | |

## Risks / Trade-offs

- [~92 ClickUp tasks per launch on the first converge pass] → Named in the proposal; the ClickUp list is sectioned only by task naming (`<step-id> · <discipline>`), so the volume is visible but flat. If it overwhelms, a follow-up change can project by gate or discipline — not folded in here.
- [Curated blocking/gate decisions are the author's, not the team's] → The full table above is the reviewable record; the "OUR RULE" column of the reference stays untouched for the team, and any step's blocking flag or gate is a one-line YAML edit under the same in-place cut-off.
- [A real launch starting before merge invalidates the in-place edit] → Decision 1's fallback: ship as `v2`.
- [Two invented rule-policy strings (Decision 7)] → They state current practice conservatively; the undecided report keeps every other policy decision visible rather than implying completeness.

## Migration Plan

No schema, no data migration. Deploy is the ordinary image roll; the next ClickUp convergence pass projects the new steps for any active launch. Rollback is reverting the YAML.
