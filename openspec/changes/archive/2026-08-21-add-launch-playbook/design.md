## Context

See `proposal.md` — Why.

Constraints that shape this design:

- **The reference material is not ours.** `docs/reference/product-launch.md` and its three companions were supplied to us; we take them as the authoritative description of *what launch work exists*, but we are free to — and here do — organise it differently. Its structure is input, not schema.
- **The reference's ordering is unreliable.** Its ten "areas" are thematic groupings, not a sequence; work in several of them proceeds concurrently. Anything that treats area order as execution order will be wrong.
- **Its rule column is empty on all 358 rows.** The playbook must therefore be able to carry work whose acceptance criterion is undecided, without that blocking anything.
- **Its companion document flags its own identifier problem.** `docs/reference/agent-orchestration.md` states that the launch registry (`lp.<agent>.<n>`) and the monitoring registry (`<domain>.<metric>`) are unreconciled, and that until they are, "the same agents serve both stages" is true on paper only. We are not obliged to inherit that.
- The `products` module scaffold exists with empty `domain/`, `application/`, `infrastructure/` packages. The project's architecture commits to the domain layer being free of framework and I/O dependencies.
- **Launch progress will eventually be mirrored into the team's task manager (ClickUp)** — steps the code agent performs assigned to it, steps a person owns assigned to that person, and the task view reflecting which stage a product is at and with what results. Stated by the project owner while this change was in review, and out of scope here; recorded as a constraint this model must not foreclose. It requires nothing structural from the playbook: assignment derives from `execution` (automated and AI-assisted steps to the code agent, human-attested to a person) keyed by `track`, and the mirror's plausible granularities — blocking steps only, steps whose timing anchor is near, or one task per gate with its steps beneath — are each served by the blocking flag, the timing anchor, and the by-gate query already specified. Two constraints for whoever builds it: gate state stays in our domain, since a launch's right to proceed must not become contingent on an external service; and a 358-task-per-launch mirror is not a task list anyone reads, so the granularity is a deliberate decision rather than a default.

## Goals / Non-Goals

**Goals:**

- Establish an ordering spine that is correct under concurrency, rather than one inherited from a document that is not sequential.
- Make the playbook's coherence rules structural — enforced at load, not by convention — so the 358 rules can be filled in over months without the file drifting into an unexecutable state.
- Leave the eventual product-scoped / market-scoped split cheap, without paying for it now.

**Non-Goals:**

- Any runtime behaviour. Nothing loads the playbook in production in this change.
- Authoring the 358 step definitions. See Decisions — *Ship gates only*.
- Reconciling the monitoring registry. This change only avoids foreclosing it.

## Decisions

### Gates, not stages, are the ordering spine

The reference's ten areas cannot order execution: work in SETUP, CREATIVE, LISTING, INVENTORY and PRICE all proceeds in parallel between the purchase order and go-live. Ordering instead attaches to **commitment points** — moments where money leaves, stock lands, or the listing becomes publicly visible, and the previous decision stops being cheaply reversible.

Each step declares the gate it must be resolved before. That single field carries ordering, gate membership and blocking semantics at once, and concurrency falls out for free: steps sharing a gate are unordered by construction, so the model cannot accidentally imply a sequence that does not exist.

*Alternative considered:* keep the ten areas as ordered stages and add explicit step-to-step dependencies for the concurrent cases. Rejected — it inverts the common case, requiring an exception for most of the work rather than for the little of it that is genuinely ordered.

### The eight gates, and the two places we diverge from the reference

`docs/reference/agent-orchestration.md` names six gates. We define eight. Both differences are corrections, and both are traceable to statements in the reference itself:

**We add an `order` gate.** The purchase order is the largest single cash commitment in the launch and locks in a ~90-day lead time, yet the reference has no gate for it. It nonetheless describes the checkpoint: `lp.finance.012` requires re-running profit and ROI validation *immediately before placing the order*, "so the numbers you validated on are stale"; `lp.finance.010` requires terms negotiated and the first order split; `lp.inventory.001` warns against ordering into Chinese New Year. That is a gate in everything but name.

**We split the reference's "go live" gate into `live` and `ignition`.** The reference's Gate 4 bundles them, but its own most emphatic operational advice separates them: `lp.listing.032` requires the listing live 3–4 days before the launch date, and adds "**Live is not launched.** That buffer absorbs the predictable failures — slow check-in, main image flagged, compliance docs rejected." `lp.ppc.019` starts PPC on the day the listing goes live, deliberately before the marketing date; `lp.external.001` fires the email blast on Day 1. Collapsing these into one gate erases the single most useful distinction in the launch plan.

A related correction: the reference's Gate 2 ("listing ready") includes *indexed*, but indexation can only be confirmed once the listing is live (`lp.rank.008`, `lp.rank.009`). Indexation therefore belongs to `live`, not `listable`.

| Gate | Commitment it guards |
|---|---|
| `commit` | Spending on samples, tooling, trademark |
| `order` | Cash out, ~90-day lead time |
| `listable` | Everything buildable without stock or a live listing |
| `stock-ready` | Fulfillable units at the fulfilment centre |
| `live` | Amazon begins learning about the listing |
| `ignition` | The launch fires once; the list is blasted once |
| `phase-one-complete` | The ranking push is judged done |
| `graduated` | The product leaves launch for monitoring |

### The gate sequence is authored as data, but validated against the specification

The eight gates live in the playbook file rather than in code, so the sequence stays reviewable in the same diff as the steps attached to it — which is where a reader can actually judge whether a reordering is safe. That authorability is only safe if the file cannot silently disagree with the specification: a swapped pair or a dropped gate would otherwise load cleanly and misorder every step attached to it.

The loader therefore checks the gate sequence against the eight gates named in the spec — membership, order, and distinct positions — and rejects any deviation. Revising the gate set becomes a two-file edit (the spec and the data), which is the correct cost: the sequence is a domain commitment, not a configuration knob.

*Alternative considered:* move the sequence into code and let the file carry only per-gate opening modes, making the invariant unfalsifiable by construction. Rejected on two grounds that survive the validation requirement: the check is a handful of comparisons, and keeping the gates in the data file means the sequence stays reviewable in the same diff as the steps attached to it — which is where a reader can actually judge whether a reordering is safe.

### Discretionary gates require confirmation instead of a quorum mechanism

`lp.strategy.026` says of the phase-one criteria: "Ticking 60-80% of the boxes is enough — do not require all of them." A gate whose rule is "most of these" cannot be modelled as "all blocking steps resolved".

Rather than introduce a quorum gate type with a threshold, a gate declares whether it opens automatically or requires human confirmation. Soft gates keep a small hard core marked blocking (for `phase-one-complete`, the organic-share floor of `lp.strategy.033`), leave the rest advisory, and require a person to open them. This also matches `docs/reference/monitoring.md`, which states that product state is "assigned quarterly, human confirms — agent never self-diagnoses state".

*Alternative considered:* a quorum threshold per gate. Rejected as false precision — nobody can defend 60% over 65%, and the real decision is a judgement call that should be recorded as one.

The criterion separating the two kinds, stated so a reader can apply it to a ninth gate: a gate requires confirmation when its opening turns on a judgement no objective condition settles — committing capital, or declaring a phase finished. It opens automatically when its preconditions are an observable state of the world. `ignition` sits on the automatic side despite being the most dramatic moment in the launch, because its preconditions — listing live, indexation confirmed, campaigns armed — are all observable; opening the gate grants permission to fire, and the firing itself is a step.

### The terms-of-service flag is split, because it was carrying three different things

The reference marks ten rows `TOS RISK` and its header at `product-launch.md:3` describes them uniformly as "tactics that risk suspension — listed so they are recognised and refused". The rows do not bear that out. Four are genuinely tactics to refuse: buying at list price to trigger a strike-through (`:580`), the friends-of-friends purchase ring (`:906`), review-inflation tactics (`:1070`), paid review-removal services (`:1104`). Four are obligations whose terminal state is compliance, not refusal: the GS1 record matching Seller Central exactly (`:285`), never accepting the convert-to-manufacturer-barcode prompt (`:307`), inserts never mentioning reviews (`:750`), the procedure for refunding a negative reviewer (`:1112`). Two are hazard warnings attached to ordinary work (`:162`, `:184`).

A single boolean forces all ten into one rule. The rule we want — "a gate can never wait on something that can never be satisfied" — is correct for the first four and wrong for the rest: the GS1 record genuinely must block listing creation. Worse, a single flag makes clearing the safety marker the path of least resistance for an author whose correct model the loader rejects, erasing the suspension-risk signal the flag exists to carry.

So the flag becomes a three-valued classification. `prohibited-tactic` keeps the rule and may not block. `compliance-obligation` may block freely. Hazard warnings are authored as compliance obligations, since as steps they read as "confirm X is true" and can be satisfied. The distinction also survives into the launch instance later, where `prohibited-tactic` is the classification whose only terminal state is refusal.

### Day zero is the marketing launch date, and `T-N` values are coarse buckets

The reference's `WHEN` vocabulary anchors on the marketing launch date, not on go-live: `lp.ppc.019` starts PPC "three to four days BEFORE the marketing launch date", and `lp.listing.032` turns the listing live "3-4 days before the actual launch date". Both rows are nonetheless labelled `T-7`. The `T-N` values are therefore **planning buckets, not due dates** — which is why the spec says a timing anchor is a planning position and must not be read as an obligation about when its gate is open. Encoding them faithfully means transcribing the bucket, not inventing a precision the source does not have.

A fourth anchor form was needed: `Day 60+` appears on 23 rows and is an obligation that begins and does not expire. Three forms could only express it by inventing an end date, which would put fabricated timing in the file indistinguishable from authored timing. An open-ended anchor states exactly what the source states.

**Transcription table for the follow-up import.** The reference numbers days from one — `lp.external.001` puts the marketing ignition at `Day 1` — while our offsets are zero-based, so the ordinal forms shift by one. The `T-N` forms do not, because they are subtraction rather than ordinal numbering. Every one of the 358 rows transcribes through this table:

| Reference `WHEN` | Anchor | Worked example |
|---|---|---|
| `T-N` | offset −*N* | `T-90` → −90 |
| `Day N` | offset *N*−1 | `Day 1` → 0 (launch day) |
| `Day 60+` | open-ended from 59 | 23 rows |
| `Week N` | window 7(*N*−1) … 7*N*−1 | `Week 1` → 0…6 |
| `Week N-M` | window 7(*N*−1) … 7*M*−1 | `Week 5-8` → 28…55 |
| `Daily` / `Weekly` / `Biweekly` / `Monthly` | recurring, that cadence | — |

Getting this wrong is not visibly wrong: a uniform one-day drift across every post-launch anchor produces a file that looks entirely plausible and is expensive to unpick once 358 rows are authored against it. Fixing the convention here costs a table.

### Our own identifier namespace, shared with future monitoring

Step identifiers are human-readable slugs in a namespace we own (`inventory.fulfillable-units-gate`). Reference identifiers such as `lp.inventory.040` are retained as provenance only: not unique, not addressable, and free to change upstream without moving our keys.

The namespace is deliberately the same one future monitoring metrics will use, so a concept measured in both stages carries one identifier with stage-keyed thresholds — `inventory.cover` gating at 60–80 fulfillable units during launch and at a 45–90 day band in steady state (named as the reference names it, since only one of its two thresholds is measured in days). This is the reconciliation the reference flags as open and cannot itself perform.

*Alternative considered:* opaque UUIDs. Rejected — the playbook is authored and reviewed as a file in pull requests and will be quoted in Slack messages; an identifier a human cannot read makes both worse.

### YAML data file with a typed loader, not Python literals and not a database

The playbook is authored as a versioned YAML file in the repository and parsed into frozen domain objects by a driven adapter.

Against a database: the empty rule column will be filled in over months, one decision at a time. As a file, each decision is a pull request — attributable, reviewable, revertible, and visible to whoever reads the project next. As database rows it is none of those.

Against Python literals: the ops team should be able to author a rule without editing Python, and structural validation (identifier uniqueness, gate references, the automation/policy rule) has to run at load regardless — a literal cannot express those constraints statically anyway, so the type checker buys less than it appears to.

`pyyaml` is currently available transitively; it will be declared as a direct dependency rather than relied on implicitly, with `types-PyYAML` added for `mypy`.

### Coherence is enforced at load, and failure is fatal

A playbook is rejected rather than returning one partially valid. Two of the six rules exist to catch specific, predictable authoring mistakes:

- **Automated or AI-assisted execution without a rule policy is rejected.** A step cannot be automated when nobody has decided what "done" means. This makes premature automation fail at startup instead of at runtime, three months into a launch.
- **A step classified `prohibited-tactic` may not be blocking.** A gate can never wait on something whose only terminal state is refusal — such a playbook would deadlock. Of the reference's ten `TOS RISK` rows, four fall in this class (`:580`, `:906`, `:1070`, `:1104`); the rest are compliance obligations and may block. See *The terms-of-service flag is split* above.

The absent-policy case is otherwise explicitly allowed, so the file can carry all 358 items with the rule column still empty.

**Where the rules live: `LaunchPlaybook`'s constructor, not the loader.** These are domain invariants — they hold regardless of where a playbook came from — so they are enforced by the `LaunchPlaybook` aggregate itself at construction, as pure domain code with no I/O. The driven adapter (`application`'s loader, per task 4.3) reads the file, parses it into the values `LaunchPlaybook` expects, and constructs it; it does not duplicate the checks. A shape or parse fault the adapter finds while building those values (a malformed YAML document, a field of the wrong type, an unparseable timing anchor) is collected the same way and merged into a single reported failure, so "every fault reported together" (see the spec's aggregation requirement) holds across both layers without the domain depending on the adapter or the adapter re-implementing domain rules.

This settles a question the tests written against this change had to leave open: they exercise the six coherence rules by constructing `LaunchPlaybook` directly, and reserve the loader's own tests for the file-boundary concerns that only exist there — the shipped `v1` file loading successfully, and a malformed file's parse faults surfacing through the same aggregated failure.

**A sixth rule: a gate's opening mode must match this specification.** The gate-sequence rule added in review checks identity, order and position, but not opening mode — a playbook could name all eight gates correctly and still mark `commit` as opening automatically. Since *A gate declares how it opens* (spec) already fixes which four gates require confirmation and which four do not, silently accepting a contradicting file would mean the specification's own criterion is unenforced anywhere. The `v1` data file is where the correct assignment is first authored; this rule is what stops a later edit from drifting.

### `scope` is carried now, and paid for later

The work splits genuinely: unit economics, sourcing, and the purchase order concern the product; listing, price, PPC, rank and reviews concern the product on one marketplace. Modelling that as two aggregates today buys nothing — one product, one marketplace — and costs coordination on every gate.

Instead each step declares `product` or `market` scope, and the launch remains a single unit. When a second marketplace arrives, the extraction is mechanical: filter by scope. One enum field is cheap insurance for a refactor that would otherwise be dreaded rather than executed.

### `track` replaces the reference's `AGENT` column, as a fixed set of twelve

The reference labels each row with an agent name. That conflates *who owns this expertise* — permanent domain knowledge — with *what software runs it* — an implementation choice this project intends to revise per step. `track` names the discipline; the execution mode names the mechanism; the two vary independently.

`track` is a closed enumeration of the twelve disciplines the reference's own `AGENT` column already uses — `strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`, `price`, `ppc`, `customer`, `external`, `traffic` — rather than a free-text field. A step's track has to be queryable (spec: *Steps can be selected by gate and by scope* extends naturally to track) and it has to mean the same thing every time a step names it; an open string field gets both wrong the first time someone types `Inventory` where another step typed `inventory`. Closing it costs nothing today, since the follow-up import needs a fixed target to map the reference's twelve codes onto regardless, and it is what makes *Track is restricted to the known disciplines* (spec) a load-time check rather than a convention.

This is deliberately a narrower claim than the gate sequence's closure: gates are the ordering spine and changing them is a structural decision about the model. `track` is a labelling taxonomy borrowed from the reference. Extending it later — if a discipline is added or split — is expected to happen, and costs adding one enum member, not revisiting an invariant.

### No step-to-step dependencies

Every genuine ordering constraint found in the reference — PPC starting when the listing goes live, the listing not switching on until units land, indexation preceding the first ad impression — is *cross-gate*, and is therefore already expressed by gate order. Adding a dependency graph would introduce cycle detection, topological sorting, and a class of bug, for no case the gates do not already cover. It can be added later if a real intra-gate constraint appears.

### Ship gates only; import the 358 steps as a follow-up

Assigning each of the 358 items a gate, a scope, and a blocking flag is a human judgement pass over data, with a completely different review character from reviewing code. Bundling it here would make this change unreviewable in one sitting.

The follow-up change extracts the rows mechanically (the source markdown is regularly structured — `**AGENT:** … **WHEN:** … **ID:**`), emits a skeleton with `gate`, `scope` and `blocking` marked for review, and takes a human pass over them. A defensible starting default for the blocking flag: `FRAMEWORK` binding blocks, `LESSON` binding is advisory — which is consistent with `lp.strategy.026`.

## Risks / Trade-offs

- [Risk] The eight-gate set is our derivation, not the reference's, and could prove wrong once real steps are attached to it. → Mitigation: the playbook is versioned and carries no state; a launch records the version it started under. Revising the gate set before any launch exists costs two file edits — the specification and the data — and no migration.
- [Risk] The follow-up import is a large, judgement-heavy change that could stall, leaving a playbook with gates and no steps. → Mitigation: the import is mechanical for every field except three, and the playbook is valid and loadable at any subset of items — the file can land incrementally, gate by gate, rather than as one 358-row commit.
- [Risk] Confirmation-gated soft gates may turn out to need a real quorum rule after all. → Mitigation: the opening mode is a per-gate attribute in data; adding a third mode later does not disturb steps.
- [Risk] Declaring `pyyaml` directly adds a dependency the project did not previously own. → Mitigation: it is already present transitively and is the de facto standard; the parsing surface is one function, so replacing it is contained.
- [Trade-off] A step's rule policy is free text at this stage, not a machine-checkable predicate. Automating a step will therefore require reading its policy and writing code against it, not deriving code from it. Making policies executable now would be speculative — none of the 358 exist yet.

## Migration Plan

Purely additive: new domain code, one new driven adapter, one new data file, one new direct dependency. No database schema, no API surface, no scheduled job, nothing loading the playbook in production. Rollback is deleting the added files and the dependency line.

Committing the reference documents to `docs/reference/`, having moved them out of the gitignored `.idea/` directory, is in scope for this change and is carried by task 7.1. It is grouped separately from the implementation because it touches no code, but it belongs to this change: these specs cite those documents, and a citation into an untracked file is not a citation.

## Open Questions

- Does `track` need to correspond one-to-one with ownership — both the boundaries the monitoring module will use, and the person a task-manager mirror would assign a human-attested step to? `track` is defined here as *which discipline's expertise a step belongs to*, which is not the same question as *who is responsible for it*; the two collapse in a small team. Deferrable: it is a label on step definitions here, monitoring is not yet designed, and no mirror exists. If they ever diverge, the fix is a separate owner-role attribute rather than overloading `track` — noted so that nobody assumes otherwise.
- Is a task-manager mirror a projection of launch state, or an input to it? If completing an assigned task there does not resolve the step, the assignee must confirm elsewhere and will not — which points at a completion being an attestation carrying evidence, and therefore a second adapter behind the same resolver port as a Slack approval, with idempotency and reconciliation attached. Deferrable: it changes nothing in the playbook, only in the change that builds the mirror.
- Whether waiving a `FRAMEWORK` step should require an approver distinct from the person doing the work. Deferrable: waivers are a property of a launch instance, not of the playbook, and belong to the follow-up change.
