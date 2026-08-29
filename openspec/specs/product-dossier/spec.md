# product-dossier Specification

## Purpose
The admin surface addressed by product rather than by launch: an index of every product the caller may see, and, for one product, its identity as the catalog holds it together with the record of what automated steps produced about it and what became of each result. It is read-only, and it outlives any launch, because what a handler produced stays true after the launch that occasioned it has ended.

## Requirements

### Requirement: The index lists every product the caller's scope permits

The admin surface SHALL serve a product index listing every product the caller's access scope permits, one row each, carrying that product's SKU, its name and its current lifecycle stage. A scope permitting nothing, and a catalog holding no products, SHALL each render the page with no rows rather than a failure.

Rows SHALL be ordered by SKU ascending **within each group**, so that the same catalog renders in the same order on every request and an admin can find a product by scanning. The qualification is load-bearing: a single ascending sort across the whole page and the set-apart rule below cannot both hold once a retired product's SKU sorts before an active one's, and a test derived from an unqualified sort would fail a correct implementation. Products in the `Retired` stage SHALL be presented distinctly from the rest and SHALL NOT be interleaved with them — the shape `roster-admin` established for deactivated people, and for the same reason: a discontinued product is still worth reaching and is never what an admin is looking for first.

A retired product's row SHALL carry the literal marker `product-retired`; no other row SHALL carry it; and every row carrying it SHALL follow every row that does not. Where nothing is listed, the page SHALL carry the literal marker `nothing-to-show`. The literal forms are given because they are what a test is derived from, and "presented distinctly" is not assertable — the discipline `playbook-admin` already settled for `row-action` and `just-created`.

Each row SHALL open that product's dossier in one action.

#### Scenario: Every permitted product is listed

- **WHEN** an admin opens the product index under a scope permitting every registered product
- **THEN** every registered product appears with its SKU, its name and its current lifecycle stage

#### Scenario: A restricted scope lists only its products

- **WHEN** the index is rendered under a scope permitting some registered products' identifiers but not others
- **THEN** exactly the permitted products appear, and the others are absent

#### Scenario: An empty index is a page, not a failure

- **WHEN** the index is rendered under a scope permitting no product identifier
- **THEN** the page renders with no rows and carries `nothing-to-show`

#### Scenario: Retired products are set apart

- **WHEN** the index is rendered and the catalog holds retired products alongside others
- **THEN** every retired product's row carries `product-retired`, no other row carries it, and every row carrying it follows every row that does not

#### Scenario: Setting apart outranks the SKU sort

- **WHEN** the index is rendered and a retired product's SKU sorts before an active product's
- **THEN** the active product's row still precedes the retired one's
- **AND** within each group the rows are ordered by SKU ascending

#### Scenario: A row reaches the dossier

- **WHEN** a row on the index is followed
- **THEN** that product's dossier is opened

### Requirement: The dossier is addressed by product identifier

The dossier SHALL be addressed by the product's identifier and by nothing else. An identifier naming no registered product, and one naming a product the caller's scope does not permit, SHALL be refused identically and in the shape of a route that does not exist — an out-of-scope product is indistinguishable from one that does not exist, exactly as `product-catalog`'s read already reports it, so a refusal can never confirm that a product the caller may not see exists.

The dossier SHALL turn on the **product** and never on whether a launch exists for it.

#### Scenario: An unknown product is refused as absence

- **WHEN** the dossier is requested for an identifier no registered product carries
- **THEN** the response is identical in shape to requesting a route that does not exist

#### Scenario: An out-of-scope product is refused identically

- **WHEN** the dossier is requested for a registered product the caller's scope does not permit
- **THEN** the response is identical to the refusal for a product that does not exist, and reveals nothing about the product

#### Scenario: A SKU is not an address

- **WHEN** the dossier is requested using a product's SKU rather than its identifier
- **THEN** it is refused as absence, exactly as any other identifier naming no product is

### Requirement: The dossier renders the product as the catalog holds it

The dossier SHALL render the product's identity as `product-catalog` answers it: its SKU, its name, its marketplace, its ASIN, its current lifecycle stage, the moment that stage was entered, and who confirmed the change into it.

Where the catalog holds no value for a field, the dossier SHALL say so explicitly rather than render an empty space, and the rendered field SHALL carry the literal marker `not-recorded`. A product registered and not yet moved has no stage confirmer at all — `product-catalog` stamps `Development` by definition rather than by a human decision — and a product has no ASIN until its listing exists; a blank in either place would read as data the page failed to load rather than as a fact about the product.

#### Scenario: A product's identity is rendered whole

- **WHEN** the dossier is rendered for a product the catalog holds with every field populated
- **THEN** the page presents its SKU, name, marketplace, ASIN, lifecycle stage, stage-entry moment and stage confirmer

#### Scenario: An absent ASIN is stated, not blank

- **WHEN** the dossier is rendered for a product registered without an ASIN
- **THEN** its ASIN field is rendered carrying `not-recorded`, and is not left blank

#### Scenario: A product with no stage confirmer says so

- **WHEN** the dossier is rendered for a freshly registered product still in `Development`
- **THEN** its stage-confirmer field is rendered carrying `not-recorded`, rather than presenting an empty confirmer

### Requirement: The dossier renders every retained result for the product, newest first

The dossier SHALL render every result retained for that product, whatever its state, ordered by the moment it was produced with the most recent first. Ordering SHALL be total: results produced at the same moment SHALL be ordered by a stable tiebreak, so that a re-render of unchanged data produces the same page.

Each entry SHALL carry: the step the result was produced for, the handler that produced it, the outcome the handler proposed, the produced text itself, the moment it was produced, and what became of it.

The page's own guarantee is that it renders entries in the order the read answered them and reorders nothing. The tiebreak that makes that order total is the read's, and is required of it by `launch-step-automation`; the page never sees the row identifier it turns on.

#### Scenario: Results are ordered newest first

- **WHEN** the dossier is rendered for a product carrying results produced at different moments
- **THEN** they appear ordered by the moment produced, most recent first

#### Scenario: An entry carries what produced it

- **WHEN** a retained result is rendered
- **THEN** its entry presents the step, the handler, the proposed outcome, the produced text and the moment it was produced

#### Scenario: The page renders in the order it was given

- **WHEN** the dossier is rendered for a product whose retained results the read answers in a given order
- **THEN** the entries appear in that order, and the page reorders nothing

### Requirement: A result's fate is rendered, and a voided result is never shown as rejected

Each entry SHALL render which of the four states the result reached — awaiting a decision, accepted, rejected, or voided — and, where a person decided it, who decided and when.

Each entry SHALL carry exactly one of the literal markers `result-pending`, `result-accepted`, `result-rejected` and `result-withdrawn`, according to the state the result reached. The literal forms are given for the reason `playbook-admin` gives for `just-created` and `write-failure-notice`: they are what a test is derived from, and this is the one rendering rule on the page where a wrong label misattributes a decision to a person. `result-withdrawn` rather than `result-voided` because it names what the page says; the stored state is `voided`.

A `voided` result SHALL be labelled as withdrawn and SHALL NOT be presented as a rejection. A result is voided when a decision arrived for a step the served playbook no longer defines: the decision was refused and the proposal withdrawn, and nobody rejected anything. Presenting it as a rejection would attribute to the person who tried to decide a judgement they never made, and the two states are distinct in storage for exactly that reason.

A voided entry SHALL NOT present a decider, because none is recorded for it.

An entry still awaiting a decision SHALL be rendered as awaiting one, and SHALL NOT be presented as though it had been settled.

#### Scenario: An accepted result names its decider

- **WHEN** an entry for an accepted result is rendered
- **THEN** it carries `result-accepted` and presents who decided it and when

#### Scenario: A rejected result names its decider

- **WHEN** an entry for a rejected result is rendered
- **THEN** it carries `result-rejected` and presents who decided it and when

#### Scenario: A voided result is withdrawn, not rejected

- **WHEN** an entry for a voided result is rendered
- **THEN** it carries `result-withdrawn`, does not carry `result-rejected`, and presents no decider

#### Scenario: A pending result is shown as awaiting a decision

- **WHEN** an entry for a result no person has decided is rendered
- **THEN** it carries `result-pending` and presents no decider

#### Scenario: An entry carries one state and no other

- **WHEN** any entry in the produced record is rendered
- **THEN** it carries exactly one of `result-pending`, `result-accepted`, `result-rejected` and `result-withdrawn`

### Requirement: A decider is rendered as recorded, not resolved afresh

The decider a settled entry names SHALL be the one recorded with the decision at the moment it was made, and SHALL NOT be re-resolved against the roster when the page is rendered. A person whose roster entry has since been renamed, deactivated or otherwise changed SHALL still appear on a past decision under the name recorded at the time.

The dossier is a record of decisions taken, and a record that silently re-renders itself as its subjects change is not a record. This is also what the store actually holds: the decision is settled with a name, not with a reference the roster can later reinterpret.

#### Scenario: A renamed decider keeps the recorded name

- **WHEN** the dossier renders an entry decided by a person whose roster display name has since changed
- **THEN** the entry presents the name recorded with the decision, not the roster's current one

#### Scenario: A deactivated decider still appears

- **WHEN** the dossier renders an entry decided by a person whose roster entry has since been deactivated
- **THEN** the entry still presents that decider and the moment of the decision

### Requirement: An entry names its step where the playbook can name it, and never hides which step it was

Each entry SHALL present the step's name where the served playbook defines that step, and SHALL present the step's identifier where it does not. A result outlives the step it was produced for — a step retired or moved out of `active` is exactly the circumstance that voids a proposal — so an entry naming a step the playbook no longer serves SHALL still render, identified by the raw identifier rather than dropped or left nameless.

An entry rendered by its step identifier for want of a name SHALL carry the literal marker `step-unnamed`, so that a fallback is distinguishable from a step whose authored name happens to be its identifier.

Resolving names SHALL NOT be able to fail the page: where the playbook cannot be read at all, every entry SHALL render by its step identifier.

#### Scenario: A served step is named

- **WHEN** an entry is rendered for a step the served playbook defines
- **THEN** the entry presents that step's name and does not carry `step-unnamed`

#### Scenario: A step the playbook no longer serves still renders

- **WHEN** an entry is rendered for a step the served playbook no longer defines
- **THEN** the entry still renders, identified by the step's identifier and carrying `step-unnamed`

#### Scenario: An unreadable playbook does not fail the page

- **WHEN** the dossier is rendered while the served playbook cannot be read
- **THEN** the page still renders every entry, each identified by its step identifier and carrying `step-unnamed`

### Requirement: The produced record states what it does not cover

The dossier SHALL present the produced record as the results that were **retained for a decision**, and SHALL NOT present it as every outcome an automated step produced for the product.

Only a terminal proposal on a step whose confirmation flag is true is retained; a result needing no confirmation, and every non-terminal outcome, is recorded against the launch and never reaches this record. A page that offered the retained set as the complete automated history would be wrong in a way a reader cannot detect from the page, and would be most wrong precisely for the products whose steps need no confirmation.

The record's container SHALL carry the literal marker `retained-for-decision`, whatever the wording it is introduced with, so that the qualification cannot be dropped by a later edit to the prose without a test noticing.

#### Scenario: The record is labelled for what it holds

- **WHEN** the dossier's produced record is rendered
- **THEN** its container carries `retained-for-decision`

#### Scenario: The qualification is present on an empty record too

- **WHEN** the dossier is rendered for a product carrying no retained results
- **THEN** the record's container still carries `retained-for-decision`

### Requirement: The dossier exists for a product with no results and for one with no launch

The dossier SHALL render for a product that has never had a launch, and for one whose launch has graduated. Where no result is retained for the product, the page SHALL render the product's identity and state explicitly that nothing has been produced for it, rather than rendering an empty record or refusing.

Where nothing is retained, the record SHALL carry the literal marker `nothing-produced`, for the same reason the index carries `nothing-to-show`.

Rendering turns on the product because the record belongs to the product. A launch is a temporary state over a continuously observed product; a page that appeared when a launch began and vanished when it ended would make a permanent record conditional on a temporary one.

#### Scenario: A product that never launched has a dossier

- **WHEN** the dossier is rendered for a product with no launch position at all
- **THEN** the page renders the product's identity and its record carries `nothing-produced`

#### Scenario: A graduated launch does not remove the dossier

- **WHEN** the dossier is rendered for a product whose launch has reached `graduated`
- **THEN** the page renders the product's identity and every result retained for it

#### Scenario: An empty record is stated, not blank

- **WHEN** the dossier is rendered for a product carrying no retained results
- **THEN** its record carries `nothing-produced`, rather than presenting an empty record region

### Requirement: Both pages are read-only

Neither the index nor the dossier SHALL offer any action that changes stored state. Accepting and rejecting a pending result SHALL remain reachable only by the Slack path `launch-step-automation` specifies, and the dossier SHALL NOT offer a decision on a pending entry it renders.

Assertably: neither page's rendered response SHALL contain a form, and no element on either SHALL carry `row-action` — the marker `playbook-admin` and `roster-admin` both require of every action control on an admin page. A page with no action controls is the one page on which that marker's absence is the whole claim.

The decision flow's refusals, its once-only settlement and its roster checks are all specified against a Slack decision. Offering a second path to the same decision would put those guarantees behind two doors, one of which nothing has specified.

#### Scenario: A pending entry offers no decision

- **WHEN** the dossier renders an entry awaiting a decision
- **THEN** it offers no control that accepts or rejects it, and the entry contains no form

#### Scenario: Neither page writes

- **WHEN** either page is rendered
- **THEN** its response contains no form and no element carrying `row-action`

### Requirement: The produced text is rendered as the text it is

The dossier SHALL render each result's produced text as text, preserving the line structure it was stored with, and SHALL NOT interpret it as markup or impose a structure on it.

`StepResolution.result` is plain text deliberately, because both of its consumers want text. The dossier is a third consumer that also wants text; inventing structure the producers never wrote would present as a fact about the result something the page had inferred.

#### Scenario: Produced text renders as written

- **WHEN** an entry whose produced text spans several lines is rendered
- **THEN** the text appears with its line structure intact and is not interpreted as markup

### Requirement: Both pages ride the admin session guard and carry the shared header

Both pages SHALL be served only to a caller holding a valid admin session whose principal resolves admin-capable at the time of the request, and SHALL be refused in the same absence shape `admin-session` requires of every admin route.

Both SHALL carry the header the other admin surfaces carry, and the header SHALL offer the product index in one action from every admin surface. The index SHALL be the surface the header names; the dossier SHALL carry the header without being a named entry in it, since it is a page about one product and has no address the header could name.

Both pages' presentation SHALL come from the same shared admin stylesheet the other admin surfaces load, reached through the route no single admin surface owns, rather than from styling carried in the pages themselves or through a route belonging to another surface.

#### Scenario: No admin session means no surface

- **WHEN** either page is requested without an admin session
- **THEN** the response is identical in shape to requesting a route that does not exist

#### Scenario: A revoked admin resolves to the same absence

- **WHEN** either page is requested with an unexpired session whose principal's roster entry has since lost the admin declaration
- **THEN** the request is refused with the absence-shaped response

#### Scenario: The index is reachable from another admin surface

- **WHEN** an existing admin surface is rendered
- **THEN** its header offers the product index in one action

#### Scenario: The dossier carries the header

- **WHEN** the dossier is rendered
- **THEN** it carries the header, from which the other admin surfaces are reachable

#### Scenario: Presentation is shared, not page-local

- **WHEN** either page is rendered
- **THEN** it loads the shared admin stylesheet and carries no page-local style block

### Requirement: The dossier offers the way back to the product index

The dossier SHALL carry a breadcrumb trail naming the product index as a
link and the product itself as the current, un-linked, segment — the
current segment rendered as the page's own title, so the page carries no
separate title beside it. Following the index link SHALL reach the index
in one action, without scripting, as the index renders with no narrowing
active.

The dossier carries no way back today: it identifies no admin surface as
current in the shared header (it is a page about one product and has no
address the header could name), and nothing else on the page offers the
index. An admin who opens a dossier and wants the index back has had no
way to get there except the browser's own back button.

#### Scenario: The index is reachable from a product's dossier

- **WHEN** a product's dossier is rendered
- **THEN** its breadcrumb trail offers the product index in one action, without scripting
- **AND** the trail's last segment names the product and is not a link
