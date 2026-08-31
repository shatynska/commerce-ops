# subcategory-advisor Specification

## Purpose
The first step handler with real judgement in it: given a product's name and marketplace, it proposes the Amazon sub-category node the product belongs in and names the compliance fields and certifications that node then demands — the work `lp.listing.007` describes. It advises; it never decides.

## Requirements

### Requirement: A recommendation is produced from the product's name and marketplace

The advisor SHALL accept a product name and a marketplace identifier, and SHALL return, where it can support a node choice, a structured recommendation carrying exactly two things: the sub-category node it proposes, expressed as the full path from the top-level category down, as a value; and a comment carrying everything else a reader needs — the compliance fields and certifications that node demands, and the alternative node a reader would most plausibly have chosen instead, with why this one was preferred.

This two-field shape — one recorded value, one comment — is deliberately the same shape every automated step handler's finding is expected to take (`launch-step-automation`, `Success[T]`/`Failure[E]`). The advisor does not get its own bespoke set of named fields for its node, its demands, and its alternative: anything beyond the recorded value belongs in the comment, so that nothing outside this capability ever needs to know this step in particular has a "sub-category" or "compliance demands" field.

The comment is not optional *for this step*, even though the universal shape allows one. Where the advisor supports a node choice, the comment SHALL be non-empty, and a response that validates as supported but whose comment is empty SHALL be treated exactly as an unreadable verdict is treated below — a shortfall in what the model produced, not evidence to be trusted with satisfaction.

**Non-emptiness is the whole of what this capability checks for content *completeness*.** The advisor is prompted to use the comment to state the compliance fields and certifications the node demands and the alternative node rejected, with why — the same content this step has always required a reader be given, and required rather than left to the model's discretion because the step exists precisely to stop the obvious node being taken by default: a comment that names no rejected alternative gives its reader nothing to disagree with. But **whether the comment actually contains that content is not verified by code, and SHALL NOT be** — checking prose for the presence of particular content is exactly the free-text-parsing fragility this change retires (the original `Verdict:`-line veto's own failure mode), and reintroducing it one field over would undo the point of moving to structured output. The system already extends the model this same trust for the node choice itself: nothing verifies the proposed value names a real Amazon taxonomy path either. Requiring specific content within the comment is therefore a prompting obligation on the advisor, not a runtime guarantee this requirement can make.

This is deliberately narrower than "the whole of what this capability checks mechanically" about `comment` — it is only what is checked *for completeness*. A separate, distinct check survives below: whether the comment's content *contradicts* the verdict already reported, which the next requirement keeps for a different reason (a false `Satisfied` reaching a person is worse than a false `Blocked`) and which does not require judging whether required content is present, only whether the comment states an inability to choose at all.

**The marketplace the advisor is given SHALL be the identifier itself, as the catalog holds it and as a reader of the prompt would recognise it — never a rendering of the object carrying it.** The advisor is handed a product resolved by the system, whose marketplace is ordinarily carried by a value object; where it is, reading that object's textual form rather than its value asks the model about a marketplace that does not exist, and records the same non-existent marketplace in the reason the launch keeps. The same SHALL hold of every other value the advisor passes on from the product it was given.

This is stated because the failure is silent: the model answers plausibly whatever it was asked, so a malformed marketplace produces a well-formed answer and nothing anywhere reports the prompt was wrong. Neither the outcome proposed nor the recommendation returned reveals it.

The text a person reads — delivered to Slack and stored as evidence — SHALL be a rendering of the value and the comment together. It SHALL NOT be the model's own free-form prose assembled outside the schema: support and the recommendation's content are both established from the structured response, never from text the model assembled itself.

#### Scenario: A recommendation names node, demands and alternative

- **WHEN** the advisor is given a product name and a marketplace identifier it can support a node choice for
- **THEN** it returns a structured recommendation whose value is the proposed node as a full path, and whose comment states the compliance fields and certifications that node demands and a rejected alternative node with the reason it was rejected

#### Scenario: A recommendation is readable as it stands

- **WHEN** a recommendation is returned
- **THEN** the rendered text is readable by a person without further processing, since it is delivered to a person for a decision and stored as the evidence of what was decided

#### Scenario: A supported comment cannot be empty

- **WHEN** the advisor's structured response validates as supported but its comment is empty
- **THEN** the advisor proposes a non-terminal outcome instead, exactly as it would for an unreadable verdict — a supported result with no comment is not a valid recommendation for this step

#### Scenario: A comment's content is never checked by code

- **WHEN** the advisor's structured response validates as supported with a non-empty comment
- **THEN** the advisor proposes the satisfying outcome whatever the comment's content is — including a comment that, in fact, omits the compliance demands or the rejected alternative the prompt asked for, since detecting that omission would require parsing prose content, which this capability does not do

#### Scenario: The marketplace reaching the model is the identifier

- **WHEN** the advisor resolves a step for a product whose marketplace is carried as a value object
- **THEN** the marketplace the model is asked about is that object's identifier, and carries nothing else of the object's rendering — neither its type name, nor its field name, nor the quoting around its value

#### Scenario: A refusal names the marketplace as a reader would recognise it

- **WHEN** the advisor cannot support a node choice and states the marketplace in its reason
- **THEN** that reason names the identifier, not a rendering of the object carrying it

### Requirement: The advisor proposes satisfaction only where it can support a node choice

The advisor SHALL propose the step's satisfying outcome only together with a recommendation meeting the requirement above. Where a marketplace's category structure gives it no confident answer, it SHALL propose a **non-terminal** outcome whose reason states that it cannot support a node choice for this product and marketplace — never a satisfying one accompanied by text admitting there is no answer.

This is the difference between a recommendation a person can weigh and a proposal that cannot be weighed at all. Under `launch-step-automation`, a terminal proposal on this step is held for a person's acceptance while a non-terminal one is recorded directly with its reason — so proposing satisfaction alongside "I cannot tell you the category" would put a compliance-relevant step one unread paragraph away from being recorded `Satisfied`, whereas the non-terminal proposal leaves the step unresolved and says on the launch's own record why.

The advisor is never relied on to settle the step by itself: Amazon's browse-node structure is not knowledge a language model holds reliably, and the step carries compliance consequences. The recommendation's value is that a person reads it, which is why the step it is written for requires confirmation.

**Support SHALL be established only by the structured verdict discriminant the advisor reports, and never by the value or the comment that accompanies it — except in the one direction named below.** The advisor's structured response carries a discriminant (`ok: true` for a supported value, `ok: false` for an unsupported error); support is read primarily from that discriminant. A response validated as supported SHALL always be treated as support, and a response validated as unsupported SHALL always be treated as withheld — the value carries no prose to misread at all, which is what retires the free-text veto this requirement previously ran over the whole recommendation.

**The comment SHALL still be able to withhold support**, narrowly. Where a response validates as supported but its comment itself states that the advisor cannot assign a node choice for this product and marketplace, the advisor SHALL treat the result as unsupported. This is the one place a contradiction can still occur: the comment is where all of the advisor's narrative now lives — the compliance demands, the rejected alternative, and any aside — so it is also the one place a model can still say "actually, I'm not confident" despite having set `ok: true`. The served prohibition on "a satisfying one accompanied by text admitting there is no answer" is what this veto keeps enforceable — without it, a verdict contradicting its own comment would reach a person as a proposal to accept, which is the state that prohibition exists to forbid. A rejected alternative described as unsupportable does not trigger this veto: that is a statement about the alternative, not about the advisor's own ability to choose, on the same reasoning the original requirement drew.

A verdict the advisor did not report — the structured call completed but produced content satisfying neither the supported nor the unsupported variant of the schema — SHALL be treated as **unsupported**, exactly as reporting a value that fits neither was treated before structured output existed. Absence is not evidence of a supportable node choice, and the two directions do not cost the same: an unsupported result wrongly treated as supported puts a false terminal outcome in front of a person to accept, while a supported result wrongly treated as unsupported leaves the step live for the next pass.

That fail-safe SHALL NOT extend to a model response whose content is not plain text at all — a transport- or client-level fault, prior to and distinct from validating a completed response against the schema. Such a response is governed by the standing requirement that a model failure is surfaced rather than masked, and SHALL continue to fail visibly: recording it as unsupported would enter a client or prompt fault on the launch's own record as the advisor's judgement about a product, which is the substitution `launch-step-automation` forbids when it refuses to let a crash be recorded as a handler's finding that the step is blocked.

Where satisfaction is withheld, the reason recorded SHALL name what was actually wrong — the unsupported error where the advisor reported one, that no verdict could be read where the structured call produced nothing that validated, or the contradiction where a supporting verdict's own comment withheld it — rather than assert that no node choice could be supported for the product where that is not, in fact, what happened. An operator reading the launch record SHALL be able to tell each of those from a classification the advisor considered and declined, since only a classification considered and declined is a finding about the product at all.

Reporting the verdict as a structured discriminant SHALL NOT remove the refusal from the recommendation itself. Where the advisor cannot support a choice, the rendered text SHALL still say so, since it is what a person reads in Slack and on the product's record, and a reader SHALL NOT have to infer a refusal from a field the page does not show them.

#### Scenario: A supported choice proposes satisfaction

- **WHEN** the advisor can support a node choice for the given product and marketplace
- **THEN** it proposes the step's satisfying outcome together with the recommendation

#### Scenario: An unsupported choice proposes no satisfaction

- **WHEN** the advisor cannot support a confident node choice for the given product and marketplace
- **THEN** it proposes a non-terminal outcome whose reason states that it cannot support a choice, and does not propose a satisfying outcome

#### Scenario: A refusal is recognised however it is worded

- **WHEN** the advisor reports two unsupported responses whose error text shares no wording
- **THEN** both propose a non-terminal outcome, since support is read from the `ok` discriminant and never searched for in text

#### Scenario: The recommendation's wording does not establish the outcome

- **WHEN** the advisor's structured response validates as supported
- **THEN** it proposes the satisfying outcome whatever its value or its comment's compliance-demands and rejected-alternative content say — including a rejected alternative described as unsupportable, which is a statement about that alternative and not about the advisor's ability to choose

#### Scenario: A verdict contradicting its own prose withholds satisfaction

- **WHEN** the advisor's structured response validates as supported but its comment states that it cannot assign a node choice for this product and marketplace
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: A missing verdict is unsupported, not supported

- **WHEN** the advisor's structured call completes but produces content satisfying neither the supported nor the unsupported variant
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: An unreadable verdict is unsupported, not supported

- **WHEN** the advisor's structured call completes and the response fails schema validation against both variants — the same condition a value fitting neither `supported` nor `unsupported` described before structured output existed
- **THEN** it proposes a non-terminal outcome, exactly as a missing verdict does

#### Scenario: A fail-safe reason names what was wrong

- **WHEN** the advisor proposes a non-terminal outcome because no verdict could be read
- **THEN** the reason states that no verdict could be read, and does not assert that a node choice could not be supported for the product

#### Scenario: An unrecognised verdict is not reported as an absent one

- **WHEN** the advisor's structured call completes but the response fails schema validation
- **THEN** the reason names that the response could not be read as a verdict — the same single reason a missing verdict produces, since structured output no longer distinguishes "nothing reported" from "something unreadable reported" as two separate technical states

#### Scenario: A vetoed verdict names the contradiction

- **WHEN** the advisor proposes a non-terminal outcome because a supporting verdict's comment contradicted it
- **THEN** the reason names that contradiction, and does not assert that the advisor considered and declined a classification

#### Scenario: A response that is not text still fails visibly

- **WHEN** the model answers with content that is not plain text at all
- **THEN** the failure is surfaced as a model failure, and no outcome is proposed for the step

#### Scenario: An unsupported recommendation still says so in prose

- **WHEN** the advisor cannot support a node choice
- **THEN** the rendered text states that it cannot support one, readable without reference to the structured discriminant

### Requirement: No tool invocation

The advisor SHALL NOT invoke any external, side-effecting tool, function, or marketplace API while producing its recommendation; the recommendation SHALL come solely from the language model's own generation over the product name and marketplace it was given, constrained to a structured response schema.

Constraining the model's response to a schema — however the model provider implements that constraint internally — is not invoking a tool: nothing external is called and nothing outside the model's own generation has any side effect. This requirement governs side-effecting calls the advisor's *own* code might otherwise make during generation (a marketplace lookup, a search call), not the mechanism the model uses to shape its output.

#### Scenario: Producing a recommendation invokes no tools

- **WHEN** the advisor produces a recommendation
- **THEN** no external, side-effecting tool, function, or marketplace call occurs during that processing

#### Scenario: Structured output is not a tool invocation

- **WHEN** the advisor's model call uses a structured-output mechanism to constrain the response to the schema
- **THEN** this is not treated as a forbidden tool invocation, since nothing external is called and no side effect occurs

### Requirement: No state across invocations

The advisor SHALL NOT retain or use any state, memory, or context from a previous invocation when producing a new recommendation; each invocation SHALL be independent of every other, including two invocations for the same product.

#### Scenario: Two invocations do not share context

- **WHEN** the advisor produces a recommendation, and is then invoked again for a different product
- **THEN** the second recommendation is produced without reference to the first product or its recommendation

### Requirement: Model failure is surfaced, not masked

If the underlying language model call fails, or returns content that is not a plain string, the advisor SHALL surface that failure rather than returning a fabricated, empty, or silently degraded recommendation.

A masked failure here would not merely return a poor answer: it would reach a person as a recommendation to accept, and be recorded as the evidence for a compliance-relevant decision.

#### Scenario: Language model call fails

- **WHEN** the configured language model is unavailable or returns an error while the advisor is producing a recommendation
- **THEN** the invocation fails visibly rather than returning a recommendation as if the call had succeeded

#### Scenario: Response content is not a plain string

- **WHEN** the configured language model's response content is not a plain string
- **THEN** the invocation fails visibly rather than returning a recommendation coerced or fabricated from that content

### Requirement: A supported recommendation's value is recorded against the product

Where the advisor proposes the step's satisfying outcome, it SHALL make its recommendation available as a typed finding — the same `Success[T]` shape `launch-step-automation` defines for every automated handler — so that its value can be recorded against the product the step resolved for. The finding's value SHALL be the node exactly as the advisor's structured response reported it — the full path from the top-level category down. The finding MAY also carry the comment, per the universal shape, but only the value SHALL ever be written to the product; the comment is never recorded there, exactly as none of today's recommendation text is recorded on the product.

The advisor SHALL NOT record this finding itself, and SHALL NOT depend on anything capable of recording it. Making the finding available is the whole of the advisor's obligation; what does or does not become of it beyond that belongs to `launch-step-automation` and to `product-catalog`, not to this capability.

This recording is provisional: it happens whenever the advisor proposes satisfaction, independent of whether a person later accepts or rejects the step's own pending result. A later rejection SHALL NOT retract or correct a value already recorded from an earlier proposal — see `launch-step-automation`'s *A handler's supported finding is recorded independently of the step's own confirmation*.

#### Scenario: A supported recommendation carries a recordable finding

- **WHEN** the advisor proposes the step's satisfying outcome
- **THEN** a typed finding whose value is exactly the proposed sub-category node is available alongside the rendered text

#### Scenario: An unsupported recommendation carries no finding

- **WHEN** the advisor proposes a non-terminal outcome
- **THEN** no typed finding is made available — there is nothing supported to record

#### Scenario: Only the finding's value is ever written to the product

- **WHEN** a typed finding is produced for a supported recommendation and recorded against the product
- **THEN** the product receives exactly the finding's value — the sub-category node — and nothing from its comment
