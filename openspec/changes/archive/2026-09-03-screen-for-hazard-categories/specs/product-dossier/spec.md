## ADDED Requirements

### Requirement: The dossier renders what the product's automated steps have established about it

The dossier SHALL render, as a region distinct from the product's identity and from its record of retained results, the facts automated steps have established about the product and written to the catalog: its recorded sub-category, and its hazard categories.

These are neither of the two things the page already renders. They are not identity — nobody registered them, a handler established them — and they are not retained results, which are proposals held for a decision and which this page already warns are not every outcome an automated step produced. A fact written to the product outlives the result that produced it and survives a launch's graduation, which is the property that makes the dossier its home: this page turns on the product for exactly that reason.

`product-catalog` has specified a read for the recorded sub-category since it was introduced, and no surface has ever rendered it. Rendering one of the two fields and not the other would leave that true for whichever was left out, and would make the next author guess which is the convention.

The region SHALL carry the literal marker `established-by-automation`, so the distinction from the retained record cannot be lost to a later edit of the surrounding prose — the discipline this capability already applies to `retained-for-decision`.

#### Scenario: The region is present and marked

- **WHEN** the dossier is rendered for any product
- **THEN** it carries a region marked `established-by-automation`, distinct from the region marked `retained-for-decision`

#### Scenario: A recorded sub-category is rendered

- **WHEN** the dossier is rendered for a product with a sub-category recorded
- **THEN** the region presents that sub-category

#### Scenario: The region renders for a product with nothing established

- **WHEN** the dossier is rendered for a product with no sub-category and no hazard categories recorded
- **THEN** the region still renders, stating each field's absence rather than being omitted

### Requirement: An unrecorded sub-category is stated, not blank

Where the catalog holds no sub-category for the product, the dossier SHALL say so explicitly and the rendered field SHALL carry the literal marker `not-recorded`, exactly as this capability already requires of an absent ASIN and an absent stage confirmer.

A sub-category has two states — recorded or not — so the page's existing absence vocabulary covers it without extension.

#### Scenario: An absent sub-category carries the page's absence marker

- **WHEN** the dossier is rendered for a product that has never had a sub-category recorded
- **THEN** its sub-category field is rendered carrying `not-recorded`, and is not left blank

### Requirement: The dossier renders hazard categories in three states, and never renders a clear screening as an absence

The dossier SHALL render the product's hazard categories in the three states `product-catalog` distinguishes, and SHALL render each of them differently:

- Where nothing has been recorded, the field SHALL state that the product has not been screened and SHALL carry the literal marker `not-recorded`, the same absence vocabulary the page uses elsewhere.
- Where an empty set has been recorded, the field SHALL state that the product was screened and no category was found, and SHALL carry the literal marker `screened-clear`. It SHALL NOT carry `not-recorded`.
- Where a non-empty set has been recorded, the field SHALL present the recorded categories — every one of them, each readable and separated from the next, carrying none of a collection's programming notation around them: no brackets, no quotation marks around each category, no type name. This is the rule `launch-admin` states for a carried finding's multi-member value, and it holds here for the same reason and is not re-derived: the field is prose an admin reads, and a category elided or wrapped in a language's own syntax is the one a reader most needs. How the categories are separated from one another is a visual judgement and is not fixed here.
- Where a non-empty set has been recorded, the field SHALL carry neither `not-recorded` nor `screened-clear`.

**The middle state needs a marker of its own because the page has no vocabulary for it.** Every absence this page renders today is a single fact's absence, answered by `not-recorded`. "Screened, nothing found" is not an absence: it is a positive finding whose content happens to be empty, and rendering it as `not-recorded` — or as blank, which this capability already forbids — would tell an admin that a screened product is unscreened. That is the one confusion `product-catalog`'s three-state rule exists to prevent, and a page collapsing it would reintroduce on the only surface that shows the field what the storage was extended to keep apart.

**No state SHALL be rendered as blank.** This capability's standing rule — that a field the catalog holds no value for says so rather than rendering an empty space, because a blank reads as data the page failed to load — applies to all three states, the empty set included.

**The field SHALL be presented as what a screening established, and SHALL NOT be presented as confirmed, approved or accepted.** `product-catalog` states that a recorded set is what an automated screening found and not what any member ratified; a page describing it in the vocabulary of a decision would assert on the product's own record something no member did.

#### Scenario: A never-screened product says so

- **WHEN** the dossier is rendered for a product with no hazard categories recorded
- **THEN** its hazard-categories field carries `not-recorded`, does not carry `screened-clear`, and is not left blank

#### Scenario: A screened-clear product is not rendered as unscreened

- **WHEN** the dossier is rendered for a product whose recorded hazard categories are an empty set
- **THEN** its hazard-categories field carries `screened-clear`, does not carry `not-recorded`, and states that the product was screened and no category was found

#### Scenario: A flagged product presents its categories

- **WHEN** the dossier is rendered for a product whose recorded hazard categories are non-empty
- **THEN** its hazard-categories field presents every recorded category, each readable and separated from the next, and carries neither `not-recorded` nor `screened-clear`

#### Scenario: Categories are not presented in a collection's notation

- **WHEN** the dossier renders a product whose recorded hazard categories carry several members
- **THEN** the field carries no bracket, no quotation mark around a category and no type name from a collection's programming notation

#### Scenario: The three states render three ways

- **WHEN** the dossier is rendered for each of a never-screened product, a screened-clear product and a flagged product
- **THEN** the three hazard-categories fields are distinguishable from one another in the rendered response

#### Scenario: The field claims no ratification

- **WHEN** the dossier renders a product's hazard categories in any recorded state
- **THEN** the field is presented as what a screening established, and presents it as neither confirmed, approved nor accepted by a member

### Requirement: The region established by automation offers no action and carries no page-local styling

The region SHALL contain no form and no element carrying `row-action`, and SHALL take its presentation from the shared admin stylesheet rather than from styling carried in the page.

This capability already requires both of the dossier as a whole; they are restated for this region because it is the first one added to the page since, and because a new state's marker is the natural occasion for someone to reach for a page-local style rule for it.

#### Scenario: The region is read-only

- **WHEN** the region marked `established-by-automation` is rendered
- **THEN** it contains no form and no element carrying `row-action`

#### Scenario: The new state's presentation is shared, not page-local

- **WHEN** the dossier renders a field carrying `screened-clear`
- **THEN** the page carries no page-local style block, that marker's presentation coming from the shared admin stylesheet
