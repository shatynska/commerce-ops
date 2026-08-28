# subcategory-advisor Specification

## Purpose
The first step handler with real judgement in it: given a product's name and marketplace, it proposes the Amazon sub-category node the product belongs in and names the compliance fields and certifications that node then demands — the work `lp.listing.007` describes. It advises; it never decides.

## Requirements

### Requirement: A recommendation is produced from the product's name and marketplace

The advisor SHALL accept a product name and a marketplace identifier, and SHALL return, where it can support a node choice, a recommendation containing: the sub-category node it proposes, expressed as the full path from the top-level category down; the compliance fields and certifications that node demands; and the alternative node a reader would most plausibly have chosen instead, with why this one was preferred.

The alternative is required rather than optional because the step exists precisely to stop the obvious node being taken by default: a recommendation that names no rejected alternative gives its reader nothing to disagree with.

**The marketplace the advisor is given SHALL be the identifier itself, as the catalog holds it and as a reader of the prompt would recognise it — never a rendering of the object carrying it.** The advisor is handed a product resolved by the system, whose marketplace is ordinarily carried by a value object; where it is, reading that object's textual form rather than its value asks the model about a marketplace that does not exist, and records the same non-existent marketplace in the reason the launch keeps. The same SHALL hold of every other value the advisor passes on from the product it was given.

This is stated because the failure is silent: the model answers plausibly whatever it was asked, so a malformed marketplace produces a well-formed answer and nothing anywhere reports the prompt was wrong. Neither the outcome proposed nor the recommendation returned reveals it.

#### Scenario: A recommendation names node, demands and alternative

- **WHEN** the advisor is given a product name and a marketplace identifier it can support a node choice for
- **THEN** it returns a recommendation naming the proposed node as a full path, the compliance fields and certifications that node demands, and a rejected alternative node with the reason it was rejected

#### Scenario: A recommendation is readable as it stands

- **WHEN** a recommendation is returned
- **THEN** it is text a person can read without further processing, since it is delivered to a person for a decision and stored as the evidence of what was decided

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

**Support SHALL be established only by a verdict the advisor reports as a value alongside the recommendation, and never by the recommendation's wording.** The recommendation is prose written for a person, and the advisor does not control how it is phrased; a rule that reads *support* out of that prose makes a compliance-relevant decision depend on a wording nothing constrains. Two refusals that mean the same thing SHALL therefore reach the same outcome, whatever words each uses, and no phrasing of the recommendation SHALL be able to produce the satisfying outcome on its own.

The wording SHALL, however, still be able to **withhold** it. Where the verdict reports support but the recommendation states that the advisor cannot assign a node choice for this product and marketplace, the advisor SHALL treat the result as unsupported. A recommendation describing a *rejected alternative* as unsupportable does not state that, and SHALL NOT be vetoed on account of it. This direction is safe in a way the other is not, and for a reason specific to what is being detected: a check keyed on a refusal being *present* fails by missing one, which is no worse than having no check, whereas one that establishes support puts a false terminal outcome in front of a person to accept. The served prohibition on "a satisfying one accompanied by text admitting there is no answer" is what this clause keeps enforceable — without it, a verdict contradicting its own prose would reach a person as a proposal to accept, which is the state that prohibition exists to forbid.

A verdict the advisor did not report, or reported with a value that is neither supported nor unsupported, SHALL be treated as **unsupported**. Absence is not evidence of a supportable node choice, and the two directions do not cost the same: an unsupported result wrongly treated as supported puts a false terminal outcome in front of a person to accept, while a supported result wrongly treated as unsupported leaves the step live for the next pass.

That fail-safe SHALL NOT extend to a model response whose content is not plain text. Such a response is governed by the standing requirement that a model failure is surfaced rather than masked, and SHALL continue to fail visibly: recording it as unsupported would enter a client or prompt fault on the launch's own record as the advisor's judgement about a product, which is the substitution `launch-step-automation` forbids when it refuses to let a crash be recorded as a handler's finding that the step is blocked. A verdict the model was asked for and did not give is a shortfall the fail-safe answers; a response that is not text at all is a fault, and the two SHALL be distinguishable on the launch's record.

Where satisfaction is withheld for any reason other than the advisor reporting that it cannot support a choice, the reason recorded SHALL name what was actually wrong — a verdict that was never reported, a verdict reported with an unrecognised value, or a verdict reporting support that its own recommendation contradicts — rather than assert that no node choice could be supported for the product. An operator reading the launch record SHALL be able to tell each of those from a classification the advisor considered and declined, since only a classification considered and declined is a finding about the product at all.

Reporting the verdict as a value SHALL NOT remove the refusal from the recommendation itself. Where the advisor cannot support a choice, the recommendation SHALL still say so in prose, since it is what a person reads in Slack and on the product's record, and a reader SHALL NOT have to infer a refusal from a field the page does not show them.

#### Scenario: A supported choice proposes satisfaction

- **WHEN** the advisor can support a node choice for the given product and marketplace
- **THEN** it proposes the step's satisfying outcome together with the recommendation

#### Scenario: An unsupported choice proposes no satisfaction

- **WHEN** the advisor cannot support a confident node choice for the given product and marketplace
- **THEN** it proposes a non-terminal outcome whose reason states that it cannot support a choice, and does not propose a satisfying outcome

#### Scenario: A refusal is recognised however it is worded

- **WHEN** the advisor reports that it cannot support a node choice in two invocations whose recommendations share no wording, one of them phrased so that searching it for `cannot support`, `can not support`, `no confident answer` or `unable to support` finds nothing
- **THEN** both propose a non-terminal outcome

#### Scenario: The recommendation's wording does not establish the outcome

- **WHEN** the advisor reports that it can support a node choice and returns a recommendation naming a node, its demands and a rejected alternative
- **THEN** it proposes the satisfying outcome, whatever the recommendation's prose contains short of a statement that the advisor cannot assign a node — including a rejected alternative described as unsupportable, which is a statement about that alternative and not about the advisor's ability to choose

#### Scenario: A verdict contradicting its own prose withholds satisfaction

- **WHEN** the advisor reports that it can support a node choice but the recommendation states that it cannot assign one
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: A missing verdict is unsupported, not supported

- **WHEN** the advisor produces a recommendation but reports no verdict at all
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: An unreadable verdict is unsupported, not supported

- **WHEN** the advisor reports a verdict that is neither supported nor unsupported
- **THEN** it proposes a non-terminal outcome and does not propose a satisfying outcome

#### Scenario: A fail-safe reason names what was wrong

- **WHEN** the advisor proposes a non-terminal outcome because it reported no verdict
- **THEN** the reason states that no verdict was reported, and does not assert that a node choice could not be supported for the product

#### Scenario: An unrecognised verdict is not reported as an absent one

- **WHEN** the advisor proposes a non-terminal outcome because its verdict carried an unrecognised value
- **THEN** the reason says so, and does not state that no verdict was reported

#### Scenario: A vetoed verdict names the contradiction

- **WHEN** the advisor proposes a non-terminal outcome because a supporting verdict was contradicted by its own recommendation
- **THEN** the reason names that contradiction, and does not assert that the advisor considered and declined a classification

#### Scenario: A response that is not text still fails visibly

- **WHEN** the model answers with content that is not plain text
- **THEN** the failure is surfaced as a model failure, and no outcome is proposed for the step

#### Scenario: An unsupported recommendation still says so in prose

- **WHEN** the advisor cannot support a node choice
- **THEN** the recommendation it returns states that it cannot support one, readable without reference to the verdict value

### Requirement: No tool invocation

The advisor SHALL NOT invoke any external tool, function, or marketplace API while producing its recommendation; the recommendation SHALL come solely from the language model's own generation over the product name and marketplace it was given.

#### Scenario: Producing a recommendation invokes no tools

- **WHEN** the advisor produces a recommendation
- **THEN** no tool, function, or marketplace call occurs during that processing

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
