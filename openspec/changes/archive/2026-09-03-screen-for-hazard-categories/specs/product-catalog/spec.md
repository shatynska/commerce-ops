## ADDED Requirements

### Requirement: A hazard-category finding can be recorded against a product

The system SHALL record a set of hazard categories against a registered product, given its product identifier and the set — the categories a compliance screening found the product to fall in, which MAY be empty. Recording SHALL be independent of the product's lifecycle stage: it is not a stage transition, requires no confirmer, and MAY be recorded for a product in any stage, including `Retired`. A later recording for the same product SHALL replace the previously recorded set entirely, never merge with it.

This mirrors how a sub-category is recorded, and for the same reason: a standalone fact about the product, not part of the stage machine, that starts absent and may be supplied — or replaced — at any point after registration.

**Recording an empty set SHALL be a recording, not a way of clearing the field.** An empty set is the assertion that the product was screened and found to fall in none of the named categories; it is the fact this capability is being extended to hold, and the one that could not be expressed before. A caller with nothing to assert SHALL record nothing at all rather than record an empty set.

**A recorded set is relative to what the screening screened against, and this capability does not record what that was.** "Found in none of the named categories" is meaningful only against the set of categories in force when the screening ran, and that set is the authored step description, which an admin may edit without a deploy. This capability records the result, never the question. A consumer SHALL therefore read an empty set as *this product was screened and nothing was found*, and SHALL NOT read it as *this product falls in no prohibited category*, which is a stronger claim than any screening made. Where what was screened against matters, it is on the launch recording that produced the value — `compliance-screen` requires the screen to cite it in the text every recording keeps.

**Replacement SHALL be wholesale, including replacement by an empty set.** A screening that found a product clear replaces a set recorded by an earlier screening that flagged it; the later screening is the more recent statement about the product and this capability keeps the current fact, not a history of findings. Where the history matters, the launch's own recordings hold it — each carries the finding that produced it, which is what `launch-instance` provides for.

#### Scenario: Hazard categories are recorded for a product with none

- **WHEN** a non-empty set of hazard categories is recorded for a product that has none recorded yet
- **THEN** reading the product back reports exactly that set

#### Scenario: An empty set is recorded as an empty set

- **WHEN** an empty set of hazard categories is recorded for a product that has none recorded yet
- **THEN** reading the product back reports an empty set, and does not report the categories as never recorded

#### Scenario: A later recording replaces the earlier one wholesale

- **WHEN** a set of hazard categories is recorded for a product that already has a different set recorded
- **THEN** reading the product back reports the later set alone, with no member of the earlier set surviving

#### Scenario: An empty set replaces a recorded set

- **WHEN** an empty set of hazard categories is recorded for a product whose recorded set is non-empty
- **THEN** reading the product back reports an empty set

#### Scenario: Recording does not require a particular stage

- **WHEN** hazard categories are recorded for a product in `Retired`
- **THEN** the recording succeeds exactly as it would for a product in any other stage

#### Scenario: What was screened against is not recorded with the result

- **WHEN** a set of hazard categories is recorded for a product
- **THEN** reading the product back reports the recorded set and reports nothing about which categories the screening screened against

### Requirement: A product reports its hazard categories in three states, never two

Reading a product back SHALL distinguish three states of its hazard categories, and SHALL NOT collapse any two of them:

- **Nothing recorded** — no screening has ever recorded a result for this product. The question is open.
- **Recorded and empty** — a screening recorded that the product falls in none of the categories it screened against. The question is answered, and the answer is that it is clear.
- **Recorded and non-empty** — a screening recorded the categories the product falls in.

The first two are the pair that must not merge, and the requirement exists for them. They are opposite facts about a product — an unasked question and an answered one — and a representation reporting both as "no categories" would report a product nothing has screened as clear. This capability already draws the same line for a sub-category, where absence is reported as absence and never as an empty value; here the empty value is itself meaningful, so the distinction carries twice the weight and is stated as its own requirement rather than left to a clause.

A product registered and never screened SHALL report the first state. Every product registered before this capability held the field SHALL report the first state, and SHALL NOT report the second.

#### Scenario: A never-screened product reports the question as open

- **WHEN** a registered product that has never had hazard categories recorded is read back
- **THEN** its hazard categories are reported as never recorded, and not as an empty set

#### Scenario: A cleared product reports an answered question

- **WHEN** a product for which an empty set was recorded is read back
- **THEN** its hazard categories are reported as recorded and empty, distinguishable from never recorded

#### Scenario: A flagged product reports its categories

- **WHEN** a product for which a non-empty set was recorded is read back
- **THEN** its hazard categories are reported as recorded, carrying exactly the members that were recorded

#### Scenario: A product predating the field reports the question as open

- **WHEN** a product registered before this capability held hazard categories is read back
- **THEN** its hazard categories are reported as never recorded

### Requirement: A recorded hazard-category set is what a screening established, not what a member ratified

A recorded set of hazard categories SHALL be understood, and SHALL be presented wherever it is rendered, as **what an automated screening established about the product** — not as an assertion that any member reviewed or accepted it.

`launch-step-automation` writes a handler's supported finding to its sink as soon as the handler returns, deliberately and independently of whether the step's own outcome is held for a member's confirmation; it states that a step's outcome and the last value recorded from its finding MAY therefore disagree, and it delegates what such a value means to this capability. This requirement is that answer.

**A value recorded from a proposal a member later rejected SHALL stand.** The rejection is a decision about the *step* — the member declined to let the launch advance on the strength of that proposal — and this capability does not hold a record of steps. What the screening found is still what it found, and erasing it would leave the product reporting the question as open when it has in fact been screened, which is the one confusion the three-state rule exists to prevent.

**The recorded value SHALL therefore never be presented as a ratified or confirmed fact.** A surface rendering it states what was screened and found; it SHALL NOT imply that a member agreed. Where a member's judgement about a particular screening matters, it is on that launch's own recording, which carries the finding that produced it and the decision that settled it.

**A rejection SHALL be answerable by a later screening, not by a reconciliation.** The correction path for a value a member disagrees with is a subsequent screening whose finding replaces it under the replacement rule above, or a direct recording; this capability builds no mechanism that reaches back into a value on a decision's behalf.

#### Scenario: A rejected proposal's recorded value stands

- **WHEN** a screening records a set of hazard categories for a product and a member subsequently rejects the pending result that screening proposed
- **THEN** reading the product back still reports the recorded set, unchanged by the rejection

#### Scenario: A rejected clear reading is still a screening, not an open question

- **WHEN** a screening records an empty set for a product and a member subsequently rejects the pending result it proposed
- **THEN** reading the product back reports the hazard categories as recorded and empty, not as never recorded

#### Scenario: A later screening replaces a disputed value

- **WHEN** a subsequent screening records a different set for a product whose recorded set was disputed
- **THEN** reading the product back reports the later set, the replacement having been performed by the screening rather than by the earlier decision
