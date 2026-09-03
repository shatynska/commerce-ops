## Why

`lp.strategy.006` — *"Screen against the FBA-prohibited hazmat list and high-compliance
categories (furniture, medical devices, supplements, grills, fire pits, balloons,
lighters, CO detectors) before sourcing"* — is one of four steps in the `commit` gate and
is `human-attested` today. It is the cheapest step in that gate to automate honestly: it
needs no marketplace API, no search-results data, no competitor lookup and no artefact the
product does not already carry. It reads a product's name and asks whether it lands in a
category the screen names.

The three steps beside it in the `commit` gate all wait on data the system does not hold —
`lp.strategy.001` needs a keyword and a product image, `lp.strategy.003` needs keyword
search volumes, `lp.finance.001` needs landed cost inputs. This one waits on nothing. It
is therefore the step that can demonstrate the automation runtime end to end — pass →
handler → proposal → member decision → recorded outcome — while the data dependencies the
others need are still being resolved.

It is also the low-risk one to be second with. `subcategory-advisor` is the only handler
with judgement in it today, and it resolves a `listable`-gate step. This change puts a
second handler beside it, in a second discipline, on a step authored `blocking: false` —
so a wrong proposal costs a member one rejection and holds no gate closed.

## What Changes

- A new `compliance-screen` capability: given a product and the screening step it is
  resolving, it proposes whether that product is clear of the categories the step names,
  or reports that it cannot support that judgement.
- A new step handler, `strategy.compliance_screen`, registered against that capability and
  resolving `lp.strategy.006`. It follows `subcategory-advisor`'s established shape: a
  `build_graph(model)` / `build_production_graph()` split, an async-only compiled graph, a
  flat schema-validated wire response, graph libraries imported inside the functions that
  build a graph, and an `lru_cache`d production graph so that registration reads no
  credentials.
- A new `step_handlers/strategy/` package — the second discipline directory, named for the
  first segment of the handler names beneath it.
- `registrations.py` gains the handler module, so both composition roots hold it.

**The screen's category list is read from the step's own `description`, not hard-coded.**
The authored step already carries the list, `playbook-authoring` already owns editing it —
recording who edited it and when — and a copy in Python would be a second source of truth
that drifts from the one members read. `playbook-authoring` already blesses this shape for
operative content: a gate threshold likewise lives in the description of the step that
establishes it. A consequence follows and is stated in the specs: editing that description
edits the screen, with no deploy and no code review. The screen therefore **renders the
categories it read into the text it produces**, so that a narrowed screen leaves a trace on
every launch it ran on.

**The handler proposes satisfaction only where it can support "clear".** A product the
screen flags, and a product the screen cannot judge from what it was given, both reach a
non-terminal outcome carrying the reason — never a satisfying one with the flag buried in
its prose. This is `subcategory-advisor`'s rule, and it holds here for a sharper reason:
the step exists to catch a category before money is spent on sourcing, so a false "clear"
costs a production run.

**A model failure is surfaced, never routed to a verdict.** A call that fails, or answers
with content that is not plain text, is a fault prior to any response existing — distinct
from a completed call whose response maps to no verdict. `launch-step-automation` already
reports a raising handler and records nothing; the capability states this so that a later
broad `except` cannot quietly turn an outage into a `Blocked` recorded on the launch as
the screen's judgement about a product.

**The wire schema's acceptance is established by conversion, not by argument.** This
screen's schema carries a construct the existing handler's does not — a three-valued
discriminant — and reasoning that a construct is inside a provider's accepted subset is
what made `subcategory-advisor` inert at every invocation. The capability requires the
provider adapter's own conversion to be exercised over the schema the call site passes.

### Non-goals

- **No finding is reported.** `StepResolution.finding` has exactly one sink today
  (`Product.sub_category`), and a compliance verdict is not it. Giving the verdict a home
  on the product is a separate change, and this one does not need it.
- **Activating the step is not a code change.** Setting `lp.strategy.006` to `automated`,
  naming this handler on it, and naming its confirmer are `playbook-authoring` actions
  against the live set in Postgres. This change makes the handler resolvable; an admin
  turns it on. The specs state what the step must be authored as for the handler to run.
- **No authoritative hazmat list is imported.** The screen is as good as the list the step
  names and the model's knowledge of it. Nothing here fetches Amazon's published list or
  claims to be current with it.

## Capabilities

### New Capabilities

- `compliance-screen`: the second handler with judgement in it — screening a product
  against the prohibited and high-compliance categories its step names, proposing the
  step's satisfying outcome only where it can support that the product is clear, and
  reporting a flag or an unsupportable judgement as a non-terminal outcome instead.

### Modified Capabilities

None. `launch-step-automation` already states everything this handler relies on — how a
handler is invoked, what its context carries, how a terminal proposal is held for a
confirmer while a non-terminal one is recorded directly, and how a repeated non-terminal
outcome cools the step off. This change adds a handler that obeys those requirements; it
changes none of them.

## Impact

- **New**: `src/commerce_ops/step_handlers/strategy/__init__.py`,
  `src/commerce_ops/step_handlers/strategy/compliance_screen.py`.
- **Modified**: `src/commerce_ops/registrations.py` — one import, one tuple entry.
- **Tests**: `tests/agents/step_handlers/strategy/` for the graph over a stubbed model;
  `tests/unit/step_handlers/strategy/` for the proposal routing and the registration.
- **No schema change, no migration, no new runtime configuration variable.** The handler
  reads the same model configuration `subcategory-advisor` already reads.
- **`.importlinter`**: no change. The `step-handler-boundary` contract names
  `commerce_ops.step_handlers` as a whole, so a new discipline package beneath it is
  already covered.
- **Cost**: at most one model call per unresolved `lp.strategy.006` per pass, and in
  practice fewer. `launch-step-automation` compares repeated non-terminal outcomes by
  **kind**, disregarding the reason each carries, so a screen that flags on one pass and
  returns undetermined on the next still cools off — the three distinct reasons this
  change requires do not defeat that. A step with no description costs no call at all.
