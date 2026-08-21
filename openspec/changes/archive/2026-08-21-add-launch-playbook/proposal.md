## Why

The Products domain's first process is Amazon product launch. Our reference material for it (`docs/reference/product-launch.md`, sourced externally and not ours to change) describes 358 discrete launch items across 12 disciplines, each carrying a timing anchor, a provenance citation, and a FRAMEWORK/LESSON binding — but its `OUR RULE / DECISION` column is empty on all 358 rows, and its own companion document flags that its identifier registry is unreconciled with the monitoring one.

Before any of that content can be executed — by code, by an agent, or by a person attesting a checkbox — the project needs a domain representation of *what a launch playbook is*: an ordered set of commitment gates, and step definitions that hang off them. This change establishes that representation and nothing else. It is the foundation both the launch-instance change and the eventual monitoring module build on, and it is the artifact into which the 358 undecided rules get captured over time.

Doing this first, separately from any launch instance, keeps the reviewable unit small: this change has no product, no launch, no state machine, no I/O beyond reading a file at startup.

## What Changes

- Introduce a `launch-playbook` capability in the `products` module: the definition-side model of an Amazon product launch.
- Define the **gate sequence** as the launch's ordering spine — eight ordered commitment gates, each a point at which money or reputation becomes irreversible. Gates, not stages, order the work; steps sharing a gate are explicitly unordered relative to one another.
- Define `StepDefinition`: the unit of launch work, declaring its gate, track (discipline), scope, timing anchor, binding, blocking flag, execution mode, hazard classification, optional rule policy, and provenance back into the reference document.
- Classify terms-of-service exposure in three values rather than one flag — `none`, `prohibited-tactic`, `compliance-obligation` — because the reference's ten `TOS RISK` rows are not one kind of thing: some are tactics to refuse, and some are obligations that must be complied with and may legitimately block a gate.
- Define `TimingAnchor` as a value object with four shapes — offset, window, open-ended, and recurring — resolving against the marketing launch date as day zero.
- Represent the playbook as a **versioned YAML file in the repository**, loaded through a driven adapter into frozen domain objects. Team decisions (the empty rule column) are therefore captured as reviewable pull requests, not database rows.
- Enforce playbook coherence **at load time**, so an incoherent playbook fails fast rather than producing a launch that cannot be completed. Notably: the gate sequence must match this specification exactly, a step marked automated or AI-assisted without a rule policy is rejected, and a `prohibited-tactic` step may not be blocking. Every violation in a playbook is reported together, so authoring a large file does not become a sequence of load attempts.
- Ship the playbook containing the eight gates and no step definitions. Importing the 358 reference items is deliberately a **follow-up change**, because assigning each item a gate, a scope and a blocking flag is a human judgement pass over data, not a code review.
- Adopt our own identifier namespace (human-readable slugs, shared with future monitoring metrics). Reference identifiers such as `lp.inventory.040` are retained as provenance only, never as keys.

Explicitly not in this change: the `ProductLaunch` aggregate, step outcomes, gate opening, evidence, waivers, scheduling, Slack or HTTP surfaces, and any marketplace or LLM integration. Also excluded: mirroring launch progress into the team's task manager (ClickUp), raised by the project owner during this change's review and deferred to its own change — see `design.md` — Context, and its two entries under Open Questions.

## Capabilities

### New Capabilities
- `launch-playbook`: the definition of an Amazon product launch — its ordered commitment gates, its step definitions, timing-anchor resolution, versioning, and the coherence rules a playbook must satisfy to be loadable.

### Modified Capabilities
None. The repository holds three capabilities — `omni-agent`, `health-check` and `deploy-pipeline` — and none is affected. `deploy-pipeline` requires `tests/unit` to run in CI, which this change's new tests satisfy by living under `tests/unit/products/`.

## Impact

- New domain code under `src/commerce_ops/products/domain/` (playbook, gates, step definitions, timing anchors) — pure, no I/O, no framework.
- New driven adapter under `src/commerce_ops/products/infrastructure/driven/` for loading and parsing the playbook file.
- New playbook data file committed in the repository, versioned.
- New unit tests under `tests/unit/products/`.
- `pyyaml` becomes a declared direct runtime dependency. It is already present transitively, but the playbook loader depends on it deliberately, and a transitive dependency is not one this project owns.
- `docs/reference/` (moved out of the gitignored `.idea/` directory as part of this work) becomes the committed home of the four externally supplied reference documents this change draws on.
- No API surface, no database schema, no scheduled job. Nothing loads the playbook in production until the launch-instance change lands.
