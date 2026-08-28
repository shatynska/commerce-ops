## Why

On 2026-08-27 the sub-category advisor proposed `Satisfied` for a product
it had just said it could not classify. The recommendation it produced
reads, in full:

> To provide an accurate response, I need specific details about the
> product … **without details about the product, I cannot confidently
> assign a sub-category node or compliance requirements.**

That result is still standing, pending, on `TestSKU13`'s
`lp.creative.003`. Had anybody pressed accept, `Satisfied` would have been
recorded against the launch for a compliance-relevant step nothing
resolved.

**This is not a specification gap.** `subcategory-advisor` already forbids
it, in the requirement *The advisor proposes satisfaction only where it
can support a node choice*, and names this exact hazard:

> never a satisfying one accompanied by text admitting there is no answer
> … proposing satisfaction alongside "I cannot tell you the category"
> would put a compliance-relevant step one unread paragraph away from
> being recorded `Satisfied`

The requirement is right. The implementation does not uphold it.

**The mechanism is the defect.** `propose()` does guard — it calls
`_is_unsupported(recommendation)` and returns `Blocked` when that fires.
`_is_unsupported` decides by searching the model's prose for one of four
literal substrings: `cannot support`, `can not support`, `no confident
answer`, `unable to support`. The model wrote *"cannot confidently
assign"*, which is none of them, so the guard did not fire.

The comment above those markers records the reasoning that chose them:

> Recognised by reading the model's own prose rather than by a sentinel
> token: the recommendation is written for a person either way, and a
> token would be one more thing the model could get wrong while still
> being right.

The trade was weighed and taken. Production is the counter-evidence. The
model *was* right — its prose is a clear, well-formed refusal — and the
matcher missed it, so the failure is silent and inverted: not a visible
miss, but a false terminal outcome on the one step whose whole reason for
requiring confirmation is that it carries compliance consequences.

**The test cannot catch it, by construction.**
`test_an_unsupported_choice_proposes_no_satisfaction` feeds a stub whose
answer is *"I cannot support a node choice for this product and
marketplace…"* — the marker phrase itself. It passes because the stub says
the magic words. It asserts the mechanism rather than the requirement, so
every refusal phrased differently is untested, and that is exactly the
case production produced.

Widening the marker list answers this one phrasing and leaves the class
untouched: the next refusal is one synonym away.

## What Changes

- **The graph reports whether it could support a node choice, as state,**
  alongside the recommendation it produced. `AdvisorState` carries
  `product_name`, `marketplace` and `recommendation` today; it gains the
  verdict, and the model is asked for it directly rather than having it
  re-derived from prose it was never constrained to phrase any particular
  way.
- **`propose()` reads that verdict** instead of pattern-matching the
  recommendation to decide the outcome. `_is_unsupported` and
  `_UNSUPPORTED_MARKERS` go.
- **The recommendation's wording keeps a veto, in one direction only.** A
  verdict reporting support whose own prose refuses is treated as
  unsupported. Without this the change would *remove* the served
  prohibition's only mechanism and regress the case where today's matcher
  happens to fire, which is not the trade it is meant to make. Withholding
  only: no phrasing can produce the satisfying outcome, and the veto
  detects a refusal being present rather than expected content being
  absent — the second would fire on well-formed prose it failed to
  recognise, every pass (`design.md` — Decision 1a).
- **A recommendation whose verdict is missing or unreadable is treated as
  unsupported**, not as supported. The safe direction is the one that
  leaves the step unresolved and says why: a missing verdict read as
  support is the defect this change exists to remove, arriving by a
  different route.
- **The prose keeps its refusal.** The recommendation is still text a
  person reads, and where the advisor cannot support a choice it still
  says so in prose — `subcategory-advisor` requires the recommendation to
  be readable as it stands, and a reader of the Slack message or the
  dossier must not have to infer the refusal from a field they cannot see.
  What changes is that the *outcome* no longer depends on that prose.
- **Each way of withholding satisfaction records its own reason.** A
  verdict never reported, one reported with an unrecognised value, and one
  reporting support that its own recommendation contradicts are three
  different things, and none of them is the advisor considering a
  classification and declining it. Recording all four alike would enter a
  model shortfall on the launch as a finding about the product — the
  substitution `launch-step-automation` refuses when it forbids a crash
  being recorded as a handler's judgement that a step is blocked.
- **The unsupported-path test stops feeding the marker phrase.** A stub
  refusing in wording the old matcher would have missed is what
  distinguishes a test of the requirement from a test of the mechanism.

## Capabilities

### Modified Capabilities

- `subcategory-advisor`: the requirement that satisfaction is proposed
  only where a node choice can be supported gains a clause on **how the
  advisor knows** — the verdict is reported by the graph and never
  inferred from the recommendation's wording — the one direction in
  which the wording may still act, withholding satisfaction but never
  establishing it, the fail-safe direction for a verdict that is absent
  or unreadable, and the requirement that each withheld path record a
  reason naming what was actually wrong. The obligation itself is
  unchanged; what is added is the constraint that makes it hold against
  prose the advisor does not control.

`launch-step-automation` is deliberately **not** modified. Its rule that a
handler with nothing conclusive to report proposes a non-terminal outcome
is correct and unchanged; this change makes one handler comply with it.
`launch-playbook` and `playbook-authoring` are untouched — nothing here
changes what a step declares or what a write accepts. `product-dossier`
is untouched too, though it is worth saying it is **in flight rather than
served**: `add-product-dossier-page` is merged but its archive is still
open, so no spec for it stands under `openspec/specs/` yet.

## Impact

**Affected code**

- `step_handlers/listing/subcategory_advisor.py` — `AdvisorState` gains
  the verdict; the prompt asks for it; `propose()` reads it;
  `_is_unsupported` and `_UNSUPPORTED_MARKERS` are removed.
- `tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py`
  — the unsupported-path stub stops using the marker phrasing, and a case
  is added for the wording that defeated the old matcher in production.

**Explicitly untouched**

The automation pass, the confirmation flow, every recording path, and the
`Proposal` contract. This change alters how one handler decides which
outcome to propose, and nothing about what happens to the proposal after.

**Not in scope**

`lp.creative.003` names `listing.subcategory_advisor` while the handler's
own docstring says it does *"the work `lp.listing.007`"* — a creative
CTR-testing step carrying the listing advisor. That is a playbook
authoring error, corrected through `playbook-authoring`'s admin surface
rather than in code, and it is not this change's to fix. It is likely why
the defect surfaced here, but fixing it alone would leave the real hazard
in place: the advisor would do the same thing on `lp.listing.007` for any
product it cannot classify.

**The standing pending result**

The result on `TestSKU13` should be **rejected**, not accepted, and that
is true independently of this change. Rejecting records `Blocked` naming
the rejecter and leaves the step live; accepting would record the false
`Satisfied` this change exists to prevent.
