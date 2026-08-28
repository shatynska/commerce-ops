## MODIFIED Requirements

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
