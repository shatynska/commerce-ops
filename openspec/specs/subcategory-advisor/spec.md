# subcategory-advisor Specification

## Purpose
The first step handler with real judgement in it: given a product's name and marketplace, it proposes the Amazon sub-category node the product belongs in and names the compliance fields and certifications that node then demands — the work `lp.listing.007` describes. It advises; it never decides.

## Requirements

### Requirement: A recommendation is produced from the product's name and marketplace

The advisor SHALL accept a product name and a marketplace identifier, and SHALL return, where it can support a node choice, a recommendation containing: the sub-category node it proposes, expressed as the full path from the top-level category down; the compliance fields and certifications that node demands; and the alternative node a reader would most plausibly have chosen instead, with why this one was preferred.

The alternative is required rather than optional because the step exists precisely to stop the obvious node being taken by default: a recommendation that names no rejected alternative gives its reader nothing to disagree with.

#### Scenario: A recommendation names node, demands and alternative

- **WHEN** the advisor is given a product name and a marketplace identifier it can support a node choice for
- **THEN** it returns a recommendation naming the proposed node as a full path, the compliance fields and certifications that node demands, and a rejected alternative node with the reason it was rejected

#### Scenario: A recommendation is readable as it stands

- **WHEN** a recommendation is returned
- **THEN** it is text a person can read without further processing, since it is delivered to a person for a decision and stored as the evidence of what was decided

### Requirement: The advisor proposes satisfaction only where it can support a node choice

The advisor SHALL propose the step's satisfying outcome only together with a recommendation meeting the requirement above. Where a marketplace's category structure gives it no confident answer, it SHALL propose a **non-terminal** outcome whose reason states that it cannot support a node choice for this product and marketplace — never a satisfying one accompanied by text admitting there is no answer.

This is the difference between a recommendation a person can weigh and a proposal that cannot be weighed at all. Under `launch-step-automation`, a terminal proposal on this step is held for a person's acceptance while a non-terminal one is recorded directly with its reason — so proposing satisfaction alongside "I cannot tell you the category" would put a compliance-relevant step one unread paragraph away from being recorded `Satisfied`, whereas the non-terminal proposal leaves the step unresolved and says on the launch's own record why.

The advisor is never relied on to settle the step by itself: Amazon's browse-node structure is not knowledge a language model holds reliably, and the step carries compliance consequences. The recommendation's value is that a person reads it, which is why the step it is written for requires confirmation.

#### Scenario: A supported choice proposes satisfaction

- **WHEN** the advisor can support a node choice for the given product and marketplace
- **THEN** it proposes the step's satisfying outcome together with the recommendation

#### Scenario: An unsupported choice proposes no satisfaction

- **WHEN** the advisor cannot support a confident node choice for the given product and marketplace
- **THEN** it proposes a non-terminal outcome whose reason states that it cannot support a choice, and does not propose a satisfying outcome

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
