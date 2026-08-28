## MODIFIED Requirements

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
