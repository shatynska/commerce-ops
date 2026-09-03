# product-catalog Specification

## Purpose

The one place that answers "which products exist and what lifecycle stage is each in": owns product identity (SKU, ASIN, marketplace, name) and the lifecycle-stage state machine, with human-confirmed stage changes. Every other context references products by identifier and reads the stage stamp from here.

## Requirements

### Requirement: A product is registered with its identity

The system SHALL register a product carrying: a unique product identifier, a SKU (required, unique across all products), a marketplace identifier (required), an optional ASIN, and a name. The ASIN MAY be absent at registration and supplied later, since a product has no ASIN until its listing exists. Registering a product whose SKU already belongs to an existing product SHALL be rejected without persisting anything.

#### Scenario: A product is registered with required fields only

- **WHEN** a product is registered with a SKU, a marketplace identifier, and a name, and no ASIN
- **THEN** the product is persisted with those values and its ASIN reported as absent

#### Scenario: A duplicate SKU is rejected

- **WHEN** a product is registered with a SKU that already belongs to an existing product
- **THEN** the registration is rejected and no new record is persisted

#### Scenario: An ASIN is recorded later

- **WHEN** an ASIN is recorded for a product registered without one
- **THEN** reading the product back reports that ASIN

### Requirement: A new product starts in Development

A newly registered product SHALL be in the `Development` lifecycle stage. The system SHALL NOT allow registering a product directly into any other stage. The product's stage-entry time SHALL be the registration time, and no stage-change confirmer SHALL be recorded for it — `Development` is stamped by definition, not by a human decision; a confirmer exists only once the first stage change occurs.

#### Scenario: Registration stamps Development

- **WHEN** a product is registered
- **THEN** its lifecycle stage is reported as `Development`

#### Scenario: Registration provenance

- **WHEN** a freshly registered product's stage is read
- **THEN** its stage-entry time equals the registration time
- **AND** no stage-change confirmer is reported

### Requirement: Stage changes follow the legal-transition table and are human-confirmed

A product's lifecycle stage SHALL change only along these transitions, and every change SHALL record who confirmed it and when — the system SHALL never change a stage without a named human confirmer:

- `Development` → `Launching` phase 1
- `Launching` phase n → `Launching` phase n+1
- `Launching` (any phase) → `SteadyState` with an explicitly supplied posture (graduation)
- `SteadyState` posture p → `SteadyState` posture p′ (re-posturing, including entering and leaving `InventoryOverride`)
- any stage → `Retired` (a product can be discontinued at any point)

`Retired` SHALL be terminal: no transition SHALL leave it. A transition whose target equals the product's current stage — including re-posturing to the same posture — SHALL be rejected, because a no-op change would spuriously reset the stage-entry time. Any transition not listed SHALL be rejected, leaving the stored stage unchanged.

A successful stage change SHALL yield a stage-changed notification object carrying the product identifier, the prior stage, the new stage, the confirmer, and the time of the change.

#### Scenario: A legal transition is applied and attributed

- **WHEN** a product in `Development` is moved to `Launching` phase 1 with a confirming member named
- **THEN** the product's stage is reported as `Launching` phase 1
- **AND** the change records the confirmer and the time of the change

#### Scenario: A phase is skipped

- **WHEN** a product in `Launching` phase 1 is moved to `Launching` phase 3
- **THEN** the change is rejected and the stored stage is unchanged

#### Scenario: An illegal transition is rejected

- **WHEN** a product in `Development` is moved directly to `SteadyState`
- **THEN** the change is rejected and the stored stage is unchanged

#### Scenario: Graduation requires an explicit posture

- **WHEN** a product in `Launching` is graduated to `SteadyState` without a posture supplied
- **THEN** the change is rejected — the system never chooses a posture itself

#### Scenario: A same-stage change is rejected

- **WHEN** a product in `SteadyState` with posture `Optimize` is moved to `SteadyState` with posture `Optimize`
- **THEN** the change is rejected and the stage-entry time is unchanged

#### Scenario: A successful change yields a stage-changed notification

- **WHEN** a legal, confirmed stage change is applied to a product
- **THEN** a stage-changed object is produced carrying the product identifier, the prior stage, the new stage, the confirmer, and the time of the change

#### Scenario: A retired product cannot change stage

- **WHEN** any stage change targets a product in `Retired`
- **THEN** the change is rejected

#### Scenario: An unconfirmed change is rejected

- **WHEN** a stage change is requested without a confirming member
- **THEN** the change is rejected and the stored stage is unchanged

### Requirement: A product reports when its current stage was entered

The system SHALL record the moment a product entered its current stage and report it alongside the stage, so that time-in-stage — the input to the exit-window rules later slices enforce — is always derivable.

#### Scenario: Stage entry time is reported

- **WHEN** a product's stage is read after a stage change
- **THEN** the time the current stage was entered is reported with it

### Requirement: A product can be read back by identifier or by SKU

The system SHALL retrieve a registered product — identity, name, current stage, and stage-entry time — given either its product identifier or its SKU, together with the caller's access scope, and SHALL return the product only when the scope permits its product identifier. When no product matches, or a matching product is outside the caller's scope, the system SHALL report absence rather than an error — an out-of-scope product is indistinguishable from one that does not exist, so a read can never confirm the existence of a product the caller may not see.

#### Scenario: A product is retrieved by identifier

- **WHEN** a product is read using the identifier it was registered with, under a scope that permits that identifier
- **THEN** the product is returned with every field it carries

#### Scenario: A product is retrieved by SKU

- **WHEN** a product is read using its SKU, under a scope that permits its product identifier
- **THEN** the same product is returned

#### Scenario: An unknown product reports absence

- **WHEN** a product is read using an identifier or SKU no registered product has, under any scope
- **THEN** the system reports that no product was found, rather than an error

#### Scenario: An out-of-scope product reports the same absence

- **WHEN** a registered product is read by identifier or by SKU under a scope that does not permit its product identifier
- **THEN** the system reports that no product was found, exactly as it does for a product that does not exist

### Requirement: Products can be listed with their stages

The system SHALL list registered products with, at minimum, each product's identifier, SKU, name, and current lifecycle stage, filtered by the caller's access scope: only products whose identifier the scope permits SHALL appear, an unrestricted scope SHALL list every registered product, and the system SHALL report an empty result rather than an error when no product exists or none is in scope.

#### Scenario: Products are listed

- **WHEN** the product list is requested under the unrestricted scope and products exist
- **THEN** every registered product is returned with its identifier, SKU, name, and current stage

#### Scenario: A restricted scope lists only its products

- **WHEN** the product list is requested under a scope permitting some registered products' identifiers but not others
- **THEN** exactly the permitted products are returned

#### Scenario: An empty catalog lists nothing

- **WHEN** the product list is requested and no products exist
- **THEN** an empty result is returned

#### Scenario: A scope permitting nothing lists nothing

- **WHEN** the product list is requested under a scope that permits no product identifier and products exist
- **THEN** an empty result is returned rather than an error

### Requirement: A sub-category finding can be recorded against a product

The system SHALL record a sub-category node against a registered product, given its product identifier and the node — a full path from the top-level category down. Recording SHALL be independent of the product's lifecycle stage: it is not a stage transition, requires no confirmer, and MAY be recorded for a product in any stage, including `Retired`. A later recording for the same product SHALL replace the previously recorded node.

This mirrors how an ASIN is recorded (`product-catalog`, *A product is registered with its identity*): a standalone fact about the product, not part of the stage machine, that starts absent and may be supplied — or replaced — at any point after registration.

#### Scenario: A sub-category is recorded for a product with none

- **WHEN** a sub-category node is recorded for a product that has none recorded yet
- **THEN** reading the product back reports that node

#### Scenario: A later recording replaces the earlier one

- **WHEN** a sub-category node is recorded for a product that already has one recorded
- **THEN** reading the product back reports the later node, not the earlier one

#### Scenario: Recording does not require a particular stage

- **WHEN** a sub-category node is recorded for a product in `Retired`
- **THEN** the recording succeeds exactly as it would for a product in any other stage

### Requirement: A product reports its recorded sub-category, or its absence

Reading a product back SHALL report its recorded sub-category node where one has been recorded, and SHALL report it as absent — never as an empty or default value — for a product nothing has been recorded for.

#### Scenario: An unrecorded sub-category reports absence

- **WHEN** a registered product that has never had a sub-category recorded is read back
- **THEN** its sub-category is reported as absent, not as an empty string

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
