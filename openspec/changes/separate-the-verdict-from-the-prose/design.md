## Context

See `proposal.md` — *Why*. Only the state that shapes the approach follows.

`AdvisorState` is a `TypedDict` carrying `product_name`, `marketplace` and `recommendation`. The graph writes the model's answer into `recommendation` and nothing else; `propose()` then re-derives a verdict from that string by substring search.

Two constraints the fix has to respect, both already recorded in the code:

- **The recommendation reaches the reader whole** — "never summarised, truncated or re-encoded — because it is both what a person decides on and what the recording keeps as evidence." Whatever carries the verdict must not touch the prose.
- **A non-string response is a named error, never coerced.** `NonStringRecommendationError` exists because `str(...)` of a content-block list "is a fabricated recommendation, which is exactly what the requirement forbids." The shared discipline a verdict inherits is *never coerce and never default to supported* — **not** the same remedy: a response whose content is not text keeps failing visibly under the standing requirement, while a verdict the model simply did not give is a shortfall the fail-safe answers. Decision 2 draws that line.

`launch-step-automation` decides what happens to whichever outcome is proposed; nothing here changes that.

`product-dossier` is referred to below as the surface on which a retained result is read after its decision. It is **in flight, not served** — `add-product-dossier-page` is implemented and merged but its archive is still open, so no spec for it stands under `openspec/specs/` yet. Nothing normative here depends on it; it appears in a justification and in a confirmation step.

## Goals / Non-Goals

**Goals:**

- The proposed outcome follows a verdict the advisor reports, not the wording of prose it does not control.
- Absence or unreadability of that verdict resolves to *unsupported*.
- The refusal stays legible in the recommendation itself.

**Non-Goals:**

- Enforcing the served requirement that a satisfying outcome comes "together with a recommendation meeting the requirement above" — a node path, its demands and a rejected alternative. Nothing checks that today and nothing checks it after this change. It is a real gap, but it is not this change's: the prohibition this change restores a mechanism for is about a recommendation that *refuses*, not one that is merely incomplete, and the only sound way to check completeness is to have the model report the three elements as values the way it now reports the verdict — Decision 1's logic applied a second time, and a larger change than this one.

- Changing the `Proposal` contract, the handler's registration, or anything after the proposal is returned.
- Fixing `lp.creative.003`'s handler assignment — playbook authoring, not code (`proposal.md` — *Not in scope*).
- Making the advisor better at classification. This change is about what it does when it *cannot* classify.

## Decisions

### Decision 1 — The verdict is a separate value in graph state, not a token inside the prose

Three options were weighed.

**Widen `_UNSUPPORTED_MARKERS`.** Cheapest, and answers only the phrasing that just failed. The next refusal is one synonym away, and each miss is a false `Satisfied` on a compliance-relevant step. It treats the instance and leaves the class.

**A sentinel token the model must emit in the prose** (`UNSUPPORTED:` as a first line). This is what the existing comment declined, and its objection stands: it is "one more thing the model could get wrong while still being right" — and a model that refuses correctly but omits the token still yields a false `Satisfied`. It also puts machine-readable scaffolding into text written for a person.

**A separate value in state** — taken. The verdict stops being a property of prose and becomes a field, so a phrasing change cannot move it. The model is asked for a classification it can answer directly rather than one inferred from how it happened to write.

The prose objection does not transfer, because of Decision 3: the refusal is still written into the recommendation. The prose keeps its job of being read; the field takes on the job of being *decided on*.

**A fourth option, and the one this design initially missed.** All three above *replace* the matcher. None asked whether prose could stay on as a **veto** — unable to establish support, able only to withhold it. That option is what Decision 1a now adopts, and its omission was the design's own defect: the argument against reading the outcome out of prose is an argument about prose *establishing* an outcome, and it does not reach prose *refusing* one.

### Decision 1a — Prose may withhold support; only the verdict may establish it

Removing the matcher outright leaves the served clause *"never a satisfying one accompanied by text admitting there is no answer"* with no mechanism at all. That clause is the requirement's central prohibition, and it stays in force whether or not this change gives it a way to hold.

Worse, removing it is a **regression** for one case rather than parity. Today a refusal happening to contain one of the four markers *is* caught. After a matcher-free change it is not — so a verdict reporting support while its own prose refuses would reach a person as a proposal to accept, on the step whose confirmation requirement exists precisely because it carries compliance consequences.

So the rule is directional, and Decision 2's asymmetry is what makes it safe:

| Prose check gets it wrong | Consequence |
|---|---|
| withholds support that was real | the step stays live; one pass |
| establishes support that was not | *forbidden* — prose cannot establish support at all |

A phrase list used only to withhold has the failure mode of having no list: it misses. It cannot manufacture the defect it exists to catch. That is why the objection that sank the list as a *decider* does not sink it as a *veto*.

**The refusal detector has a bounded false-positive class of its own, and must be built not to trip it.** The paragraph above prices a wrong withholding at one pass, and that is right for a detector that misfires by chance. It is not right for one that misfires on a *shape* of prose: a recommendation whose rejected-alternative sentence says that alternative "cannot support" something is well-formed, and a naive detector reading it as a refusal would block the step on every pass for that product, since the same prompt yields the same shape. The delta's carve-out is what bounds this — a statement about a rejected alternative is not a statement that the advisor cannot assign a node — and it is a constraint on how the detector is written, not a hope about how models phrase things.

**That argument covers a refusal detector and nothing else, so the veto is a refusal detector and nothing else.** An earlier draft extended the same clause to a recommendation that does not meet the first requirement — no node path, no demands, no rejected alternative. That trigger keys on the *absence* of expected content rather than the presence of a refusal, which inverts its failure mode: it fires on well-formed recommendations it does not recognise. And that misfire is not the table's one-pass cost, because it is deterministic — the same prompt over the same product yields prose of the same shape, so the step would be blocked on every pass rather than retried successfully on the next. Extending the veto that way would have smuggled an unsound trigger in under a sound one's argument.

### Decision 2 — Absent or unreadable resolves to unsupported

Not symmetric, deliberately, and the asymmetry is what makes this a fail-safe rather than a preference:

| Verdict wrong in this direction | Consequence |
|---|---|
| unsupported → read as supported | a false terminal outcome offered to a person to accept; if accepted, `Satisfied` recorded for a step nothing resolved |
| supported → read as unsupported | the step stays live and is offered to the handler again on the next pass |

The second costs a pass. The first is the defect this change exists to remove. Anything not clearly *supported* is therefore treated as not supported — including a verdict the model omitted, and one whose value is neither.

This is also the direction `access-scope` and `admin-session` already take for their own unreadable inputs, so the repository has one answer to "what does an unreadable answer mean" rather than two.

### Decision 3 — The recommendation still states the refusal in prose

The verdict field decides the outcome; it does not become the only place the refusal exists. The recommendation is what a person reads in the Slack decision message and in the product dossier, and neither surface renders graph state. A reader must not have to infer a refusal from a field they cannot see.

This keeps `subcategory-advisor`'s standing requirement that a recommendation is "readable as it stands" true for the refusal case too, and it means the two channels agree rather than one silently carrying the truth.

### Decision 4 — The unsupported-path test stops speaking the marker's language

`test_an_unsupported_choice_proposes_no_satisfaction` currently feeds a stub whose answer *is* the marker phrase. It passed throughout the failure. Its replacement uses wording the old matcher would have missed — the production phrasing is the obvious choice, since it is the one case known to have defeated the mechanism.

That is a test-quality change, not a scope addition: a test that asserts the mechanism it was built around cannot fail when the mechanism is wrong, which is why this defect reached production green.

## Risks / Trade-offs

**The model may not report the verdict reliably** → This is the objection the sentinel-token option failed on, so it has to be answered rather than waved past. It is materially weaker here: asking for a classification as its own answer is a smaller ask than asking for an exact token inside prose, and Decision 2 makes the failure mode safe rather than silent — an omitted verdict leaves the step live instead of proposing a false `Satisfied`.

**A verdict reporting support while its own prose refuses** → Closed by Decision 1a, and worth naming as the failure this design first missed. An earlier draft of this document called the residual "unchanged from today"; that was wrong. Today a refusal containing one of the four markers is caught, so removing the matcher without a replacement would have been a regression for exactly the case the change was written about. The veto restores it. It does **not** widen it: an earlier draft of this change extended the same clause to a recommendation failing the first requirement, and that trigger was removed for the reason Decision 1a's final paragraph gives — it keys on absent content rather than a present refusal, so it fires on well-formed prose it fails to recognise, deterministically, every pass. The completeness obligation is parked in *Non-Goals*, not folded in here.

**The veto over-fires on a rejected alternative described as unsupportable** → The one way this change can block a step the advisor could have resolved, and deterministic rather than one-pass when it happens, for the reason Decision 1a gives. Bounded by the delta's carve-out, which is normative and carries its own scenario, and by task 3.1a. A detector reusing the deleted marker list unchanged would trip it, which is why task 5.4 checks the symbols are gone rather than merely unreferenced.

**A supported verdict with an incomplete recommendation** → Not closed, and deliberately so; see *Non-Goals*. It reaches a person as a proposal to accept, which is the same exposure as today. The person reading it is the check, which is what the step's confirmation requirement is for.

The genuine residual is a *supported* verdict whose prose is a confident, well-formed recommendation that is simply wrong about the node. That is unchanged from today, is not detectable from the text, and is precisely why this step requires human confirmation.

**A second thing the graph must produce is a second thing that can fail** → Bounded by Decision 2 and by the existing `NonStringRecommendationError` precedent: a malformed verdict is an unsupported verdict, not an exception and not a default to supported.

**Only the graph's own tests cover this** → The advisor's behaviour is exercised against stubbed models, so no test proves what a real model returns. That is the standing arrangement for every agent graph in this repository (`AGENTS.md`'s deterministic-agent-tests rule) and this change does not alter it. What it does change is that the tests now discriminate on the verdict rather than on wording, so a stub cannot pass by reciting a phrase.

## Migration Plan

None. No schema, no stored shape, no configuration variable, no change to any recorded outcome. Nothing already recorded is revisited: the pending result on `TestSKU13` is unaffected by this change and should be rejected on its own merits.

Rollback is reverting the merge.

## Open Questions

- Whether other handlers infer an outcome from model prose the same way. `listing.subcategory_advisor` is the only handler this deployment registers today, so the question has no second case yet — worth asking of the next handler rather than answered speculatively here.
