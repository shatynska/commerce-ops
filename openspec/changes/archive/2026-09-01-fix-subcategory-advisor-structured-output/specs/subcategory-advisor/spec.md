## ADDED Requirements

### Requirement: The structured-output schema is one the model provider's adapter accepts

The schema the advisor hands the model provider to constrain its response SHALL be one that provider's adapter accepts, and acceptance SHALL be established by exercising the provider adapter's **own** conversion rather than any stand-in for it. This check requires no model call, no network access and no credential, so nothing about its cost justifies substituting a double for it.

The schema converted by that check SHALL be the one the advisor actually passes at its structured-output call site, not a module-level symbol that is merely expected to be the same. A guard that converts a symbol the call site has stopped using guards nothing.

*Rationale, not itself normative: today's adapter rejects a top-level union of the response variants — it converts what it is given into the provider's own request format, and a union is not a shape that conversion accepts, so passing one makes every invocation fail before the model is ever called. That is the defect this requirement exists to prevent recurring, but the requirement is the general rule; if a future adapter accepts a union, the rule is still satisfied by whatever that adapter accepts.*

The shape crossing the model boundary MAY differ from the shape the advisor reports to its own callers. Where the two differ, the advisor SHALL convert the provider's parsed response into its reported results, and that conversion SHALL be defined for **every** combination of fields the wire schema can express — not only those a well-behaved model is expected to produce. No combination SHALL be left without a defined destination.

How each destination is then treated — which propose a satisfying outcome, which withhold it, and what reason each records — is governed entirely by *The advisor proposes satisfaction only where it can support a node choice*, and SHALL NOT be restated here. This requirement governs the wire contract: that the schema is accepted, that the conversion is total, and that the fields say when they are to be populated. A wire shape that can express a state the reported results forbid does not acquire its own routing rule by virtue of being a wire shape.

Where a wire schema's fields are individually optional, and so admit combinations the reported variants forbid, each field SHALL carry a description stating what it is for and when it is to be populated. The reported variants couple their fields structurally — a supported variant cannot exist without its value — and a wire shape that drops that coupling SHALL replace it with something the model can read, rather than leaving the coupling implicit in the prompt alone.

Adopting a differing wire shape SHALL NOT change what the advisor reports: the supported and unsupported variants, their fields, and the typed finding built from them are unaffected by how the response is requested.

#### Scenario: The schema is accepted by the provider's own conversion

- **WHEN** the schema the advisor passes at its structured-output call site is converted by the model provider's adapter
- **THEN** the conversion succeeds, and this is verified without invoking a model, opening a network connection, or supplying a credential

#### Scenario: The converted schema is the one the call site passes

- **WHEN** the advisor's structured-output call site passes a schema other than the one a guard converts
- **THEN** that divergence is detectable, since the guard obtains its schema from the call site rather than by importing a symbol independently

#### Scenario: Every wire combination has a defined destination

- **WHEN** the provider returns any response that parses against the wire schema
- **THEN** the advisor's conversion yields exactly one of its defined results — a supported result, an unsupported result, a contradiction, or none of them — with no combination of fields left to fall through to an unintended route, and with what each destination then proposes and records governed by *The advisor proposes satisfaction only where it can support a node choice*

#### Scenario: Wire fields state when they are to be populated

- **WHEN** the wire schema expresses the reported variants' fields as individually optional
- **THEN** each field carries a description of what it is for and when it is to be populated, so the coupling the reported variants enforce structurally is stated rather than left to the prompt alone

#### Scenario: The reported variants are unchanged by the wire shape

- **WHEN** the advisor reports a supported or unsupported result
- **THEN** that result carries the same fields, and produces the same rendered text and the same typed finding, as it would have had the wire shape and the reported shape been identical

## MODIFIED Requirements

### Requirement: The advisor proposes satisfaction only where it can support a node choice

The advisor SHALL propose the step's satisfying outcome only together with a recommendation meeting the requirement above. Where a marketplace's category structure gives it no confident answer, it SHALL propose a **non-terminal** outcome whose reason states that it cannot support a node choice for this product and marketplace — never a satisfying one accompanied by text admitting there is no answer.

This is the difference between a recommendation a person can weigh and a proposal that cannot be weighed at all. Under `launch-step-automation`, a terminal proposal on this step is held for a person's acceptance while a non-terminal one is recorded directly with its reason — so proposing satisfaction alongside "I cannot tell you the category" would put a compliance-relevant step one unread paragraph away from being recorded `Satisfied`, whereas the non-terminal proposal leaves the step unresolved and says on the launch's own record why.

The advisor is never relied on to settle the step by itself: Amazon's browse-node structure is not knowledge a language model holds reliably, and the step carries compliance consequences. The recommendation's value is that a person reads it, which is why the step it is written for requires confirmation.

**Support SHALL be established by the structured verdict discriminant together with the field that discriminant's variant requires — the discriminant alone SHALL NOT establish it, and the comment SHALL NOT establish it in the supporting direction.** A response is supported only where its discriminant reports support (`ok: true`) *and* it carries the value that support consists of; a response is unsupported only where its discriminant withholds support (`ok: false`) *and* it carries the error stating why. Support so established SHALL always be treated as support, and support so withheld SHALL always be treated as withheld — the value carries no prose to misread at all, which is what retires the free-text veto this requirement previously ran over the whole recommendation.

Requiring the variant's own field alongside the discriminant is what keeps a discriminant that reports support without any recommendation to support from reaching a person as one. Where the wire shape expresses these fields independently, so that a discriminant can arrive without its field, this is the rule that decides it, and it decides it in the withholding direction.

**Two further directions SHALL withhold support** — and, in one case below, SHALL decide which withholding reason is recorded where support was never established at all. Both are narrow, and both are cases of a response contradicting itself rather than of a judgement about the product:

1. **A supporting discriminant carrying a reported error.** Where a response reports support and also carries the error field by which support is withheld, the advisor SHALL treat the result as a contradiction and propose a non-terminal outcome. **This SHALL apply whether or not a value accompanies the error, and SHALL take precedence over the missing-value rule above.** A response reporting support with no value but a populated error has told the reader *why* no node could be named; routing it to the shortfall path instead would discard that explanation and record only that no verdict could be read, which is the same loss this direction exists to prevent — the reason must name what was actually wrong, and here the model said what was wrong. The error SHALL NOT be discarded as surplus to a supported response: a response that both claims a node and states why it cannot name one has not established support, and dropping the second half is how a refusal reaches a person as a recommendation to accept. The rendered text for such a result SHALL carry that error, so the refusal is visible to the person reading it — a contradiction of this kind may carry no comment at all, and rendering it as a supported result would show a reader a node path with nothing anywhere in it to say support was withheld.
2. **A supporting response whose comment withholds support.** Where a response is established as supported but its comment itself states that the advisor cannot assign a node choice for this product and marketplace, the advisor SHALL treat the result as unsupported. The comment is where all of the advisor's narrative now lives — the compliance demands, the rejected alternative, and any aside — so it is also a place a model can still say "actually, I'm not confident" despite having reported support. A rejected alternative described as unsupportable does not trigger this veto: that is a statement about the alternative, not about the advisor's own ability to choose, on the same reasoning the original requirement drew.

The served prohibition on "a satisfying one accompanied by text admitting there is no answer" is what both directions keep enforceable — without them, a verdict contradicting its own response would reach a person as a proposal to accept, which is the state that prohibition exists to forbid.

A verdict the advisor did not report — the structured call completed but produced content the advisor's conversion maps to neither a supported nor an unsupported result, **and which is not a contradiction under the directions above** — SHALL **withhold satisfaction**, exactly as reporting a value that fits neither was treated before structured output existed. "Withhold satisfaction" states the direction, not the result type: such a response SHALL NOT be reported as an unsupported result, which would assert a classification the advisor considered and declined when none was considered at all. Absence is not evidence of a supportable node choice, and the two directions do not cost the same: an unsupported result wrongly treated as supported puts a false terminal outcome in front of a person to accept, while a supported result wrongly treated as unsupported leaves the step live for the next pass.

That fail-safe SHALL NOT extend to a model response whose content is not plain text at all — a transport- or client-level fault, prior to and distinct from validating a completed response against the schema. Such a response is governed by the standing requirement that a model failure is surfaced rather than masked, and SHALL continue to fail visibly: recording it as unsupported would enter a client or prompt fault on the launch's own record as the advisor's judgement about a product, which is the substitution `launch-step-automation` forbids when it refuses to let a crash be recorded as a handler's finding that the step is blocked.

Where satisfaction is withheld, the reason recorded SHALL name what was actually wrong — the unsupported error where the advisor reported one, that no verdict could be read where the structured call produced nothing that mapped to a result, or the contradiction where a supporting response's own error or comment withheld it — rather than assert that no node choice could be supported for the product where that is not, in fact, what happened. An operator reading the launch record SHALL be able to tell each of those from a classification the advisor considered and declined, since only a classification considered and declined is a finding about the product at all.

Reporting the verdict as a structured discriminant SHALL NOT remove the refusal from the recommendation itself. Where the advisor cannot support a choice, the rendered text SHALL still say so, since it is what a person reads in Slack and on the product's record, and a reader SHALL NOT have to infer a refusal from a field the page does not show them.

#### Scenario: A supported choice proposes satisfaction

- **WHEN** the advisor can support a node choice for the given product and marketplace
- **THEN** it proposes the step's satisfying outcome together with the recommendation

#### Scenario: An unsupported choice proposes no satisfaction

- **WHEN** the advisor cannot support a confident node choice for the given product and marketplace
- **THEN** it proposes a non-terminal outcome whose reason states that it cannot support a choice, and does not propose a satisfying outcome

#### Scenario: A refusal is recognised however it is worded

- **WHEN** the advisor reports two unsupported responses whose error text shares no wording
- **THEN** both propose a non-terminal outcome, since support is read from the discriminant together with its variant's field, and never searched for in text

#### Scenario: The recommendation's wording does not establish the outcome

- **WHEN** the advisor's structured response is established as supported
- **THEN** it proposes the satisfying outcome whatever its value or its comment's compliance-demands and rejected-alternative content say — including a rejected alternative described as unsupportable, which is a statement about that alternative and not about the advisor's ability to choose

#### Scenario: A supporting discriminant without its value is not support

- **WHEN** the advisor's structured response reports support, carries no value or a value that is empty or blank, **and carries no error either**
- **THEN** it proposes a non-terminal outcome whose reason states that no verdict could be read, and does not propose a satisfying outcome — a response that carries an error alongside the missing value is a contradiction instead, governed by the direction above

#### Scenario: A withholding discriminant without its error is not a refusal

- **WHEN** the advisor's structured response withholds support but carries no error, or an error that is empty or blank
- **THEN** it proposes a non-terminal outcome whose reason states that no verdict could be read, rather than one asserting that the advisor considered and declined a classification

#### Scenario: A supporting discriminant carrying a reported error withholds satisfaction

- **WHEN** the advisor's structured response reports support and also carries a non-empty error
- **THEN** it proposes a non-terminal outcome naming the contradiction, does not propose a satisfying outcome, and its rendered text carries that error — the error is never discarded as surplus to a supported response, and never left only in the recorded reason where the person reading the recommendation would not see it

#### Scenario: A verdict contradicting its own prose withholds satisfaction

- **WHEN** the advisor's structured response is established as supported but its comment states that it cannot assign a node choice for this product and marketplace
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: A missing verdict is unsupported, not supported

- **WHEN** the advisor's structured call completes but produces content the advisor's conversion maps to neither a supported nor an unsupported result
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: An unreadable verdict is unsupported, not supported

- **WHEN** the advisor's structured call completes and the response fails validation against the wire schema entirely — the same condition a value fitting neither `supported` nor `unsupported` described before structured output existed
- **THEN** it proposes a non-terminal outcome, exactly as a verdict that maps to neither result does

#### Scenario: A fail-safe reason names what was wrong

- **WHEN** the advisor proposes a non-terminal outcome because no verdict could be read
- **THEN** the reason states that no verdict could be read, and does not assert that a node choice could not be supported for the product

#### Scenario: An unrecognised verdict is not reported as an absent one

- **WHEN** the advisor's structured call completes but the response fails validation against the wire schema
- **THEN** the reason names that the response could not be read as a verdict — the same single reason a verdict mapping to neither result produces, since structured output no longer distinguishes "nothing reported" from "something unreadable reported" as two separate technical states

#### Scenario: A vetoed verdict names the contradiction

- **WHEN** the advisor proposes a non-terminal outcome because a supporting response's own error or comment contradicted it
- **THEN** the reason names that contradiction, and does not assert that the advisor considered and declined a classification

#### Scenario: A response that is not text still fails visibly

- **WHEN** the model answers with content that is not plain text at all
- **THEN** the failure is surfaced as a model failure, and no outcome is proposed for the step

#### Scenario: An unsupported recommendation still says so in prose

- **WHEN** the advisor cannot support a node choice
- **THEN** the rendered text states that it cannot support one, readable without reference to the structured discriminant

### Requirement: A recommendation is produced from the product's name and marketplace

The advisor SHALL accept a product name and a marketplace identifier, and SHALL return, where it can support a node choice, a structured recommendation carrying exactly two things: the sub-category node it proposes, expressed as the full path from the top-level category down, as a value; and a comment carrying everything else a reader needs — the compliance fields and certifications that node demands, and the alternative node a reader would most plausibly have chosen instead, with why this one was preferred.

This two-field shape — one recorded value, one comment — is deliberately the same shape every automated step handler's finding is expected to take (`launch-step-automation`, `Success[T]`/`Failure[E]`). The advisor does not get its own bespoke set of named fields for its node, its demands, and its alternative: anything beyond the recorded value belongs in the comment, so that nothing outside this capability ever needs to know this step in particular has a "sub-category" or "compliance demands" field.

The comment is not optional *for this step*, even though the universal shape allows one. Where the advisor supports a node choice, the comment SHALL be non-empty, and a response established as supported but whose comment is empty SHALL be treated exactly as an unreadable verdict is treated below — a shortfall in what the model produced, not evidence to be trusted with satisfaction.

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

- **WHEN** the advisor's structured response is established as supported but its comment is empty
- **THEN** the advisor proposes a non-terminal outcome instead, exactly as it would for an unreadable verdict — a supported result with no comment is not a valid recommendation for this step

#### Scenario: A comment's content is never checked by code

- **WHEN** the advisor's structured response is established as supported with a non-empty comment
- **THEN** the advisor proposes the satisfying outcome whatever the comment's content is — including a comment that, in fact, omits the compliance demands or the rejected alternative the prompt asked for, since detecting that omission would require parsing prose content, which this capability does not do

#### Scenario: The marketplace reaching the model is the identifier

- **WHEN** the advisor resolves a step for a product whose marketplace is carried as a value object
- **THEN** the marketplace the model is asked about is that object's identifier, and carries nothing else of the object's rendering — neither its type name, nor its field name, nor the quoting around its value

#### Scenario: A refusal names the marketplace as a reader would recognise it

- **WHEN** the advisor cannot support a node choice and states the marketplace in its reason
- **THEN** that reason names the identifier, not a rendering of the object carrying it
