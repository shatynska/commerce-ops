## MODIFIED Requirements

### Requirement: Satisfaction is proposed only for a clear verdict

The screen SHALL propose the step's satisfying outcome only where its verdict is clear and its comment is neither empty nor whitespace-only. A flagged verdict, an undetermined verdict, an unreadable verdict, and a step naming no categories SHALL each produce a **non-terminal** outcome whose reason states which of them occurred — never a satisfying outcome accompanied by text admitting the product was flagged or the question was not settled.

This is `subcategory-advisor`'s rule, and it binds harder here. Under `launch-step-automation` a terminal proposal on a step naming a confirmer is held for that member's acceptance, while a non-terminal one is recorded directly with its reason. The step exists to catch a category **before sourcing**, so a satisfying proposal carrying a flag in its prose would put a production run one unread paragraph away from being committed against a product Amazon will not let the seller ship.

The reasons SHALL be distinguishable from one another. A flagged verdict is a finding about the product — the screen did its work and the answer was unwelcome. An undetermined verdict is a statement about what the screen was given. An unreadable verdict is a shortfall in what the model produced. Recording any of them under another's reason misstates on the launch's own record what happened, and a member reading "could not screen this product" where the truth was "this product is a supplement" would take the wrong next action.

**An empty or whitespace-only comment SHALL be resolved before any other property of the response is dispatched on.** A verdict with no comment to justify it is unreadable whatever else the response carries, and the check SHALL precede both the verdict dispatch and the structural contradictions specified below. Without a stated order, a response that is simultaneously blank-commented and structurally contradictory has two candidate destinations, each required to carry wording distinct from the other, and an implementation must guess which. This clause makes the precedence a fact rather than a guess, and it preserves the existing rule against an implementation that, testing `clear` before the comment, proposes satisfaction on a bare verdict.

#### Scenario: A clear verdict proposes satisfaction

- **WHEN** the screen's verdict is clear and its comment is neither empty nor whitespace-only
- **THEN** it proposes the step's satisfying outcome, carrying the cited categories, the verdict and the comment as the text a member reads

#### Scenario: A flagged verdict proposes a non-terminal outcome

- **WHEN** the screen's verdict is flagged and its response names at least one category
- **THEN** it proposes a non-terminal outcome whose reason names the product and states that the screen flagged it, and the text a member reads carries the comment

#### Scenario: An undetermined verdict proposes a non-terminal outcome

- **WHEN** the screen's verdict is undetermined
- **THEN** it proposes a non-terminal outcome whose reason states that the screen could not settle the question from what it was given, and that reason differs from the one a flagged verdict produces

#### Scenario: An unreadable verdict is not reported as a judgement about the product

- **WHEN** the screen's response validates against no verdict that can be read
- **THEN** it proposes a non-terminal outcome whose reason states that no verdict could be read, and that reason does not state that the product was flagged or that it is clear

#### Scenario: A blank comment outranks a structural contradiction

- **WHEN** the screen's response carries an empty or whitespace-only comment and would also trigger a structural contradiction below
- **THEN** it is treated as an unreadable verdict, carrying that route's reason rather than either contradiction's

### Requirement: A verdict its own response contradicts is not satisfaction

Where the screen's response reports a clear verdict and, in the same response, states that it could not screen the product, the screen SHALL propose a non-terminal outcome and SHALL NOT propose satisfaction. The text a member reads SHALL carry the contradicting statement, not only the clear verdict — the contradiction is what the reader must see, and a rendering showing a bare "clear" would show them a judgement the response itself withheld.

This is kept for the same reason `subcategory-advisor` keeps it: a false satisfying proposal reaching a member is worse than a false non-terminal one, and this is the one direction in which prose may still act. It does not require judging whether the comment's required content is present — only whether the response states an inability to screen at all.

**The statement withholding support SHALL be one about the screen's own ability to screen, not about a category.** A comment describing a category the product cannot fall in, or a classification the screen ruled out, is a statement about that category and SHALL NOT trigger this veto — the same distinction `subcategory-advisor` draws for a rejected alternative described as unsupportable. Vetoing on such a statement would block the step on every pass for that product, since the same prompt yields the same shape.

**A clear verdict that names categories the product falls in is contradicted structurally, and SHALL be refused on the same terms.** The response reports that the product falls in none of the named categories while simultaneously naming ones it falls in; the two cannot both be true, and satisfying the step on the strength of the verdict alone would record "clear" for a product the same response says is not. This is established from the response's own structure and SHALL NOT require reading any prose to find, which is what makes it a different kind of check from the one above rather than a second application of it.

**The two contradictions SHALL be distinguishable in what the screen reports.** A response withholding its verdict in prose and a response contradicting it structurally are two different things that happened, and this capability already requires that different things that happened read as different sentences. The text a member reads SHALL, for the structural contradiction, carry both the clear verdict and the categories the same response named — for the reason the prose case gives: the reader must see the contradiction, not one half of it.

**Neither contradiction SHALL establish anything about the product.** A response the screen refuses to read as a verdict is not a source of a finding, and the screen SHALL report none for either — the product's recorded hazard categories are left exactly as they were, including a flag recorded by an earlier screening.

#### Scenario: A clear verdict carrying a stated inability is refused

- **WHEN** the screen's response reports a clear verdict while also stating that the screen could not screen the product
- **THEN** it proposes a non-terminal outcome, and the text a member reads carries the stated inability

#### Scenario: A statement about a category does not withhold satisfaction

- **WHEN** the screen's response reports a clear verdict whose comment states that a named category cannot apply to the product
- **THEN** it proposes the step's satisfying outcome, that being a statement about the category rather than about the screen's own ability to screen

#### Scenario: A clear verdict naming categories is refused

- **WHEN** the screen's response reports a clear verdict and, in the same response, names one or more categories the product falls in
- **THEN** it proposes a non-terminal outcome, and the text a member reads carries both the clear verdict and the categories named

#### Scenario: The structural contradiction is not reported as the prose one

- **WHEN** the screen refuses a clear verdict because the same response named categories
- **THEN** what it reports is distinguishable from what it reports for a clear verdict withheld by its own comment, rather than sharing that route's wording

#### Scenario: A contradicted verdict establishes nothing about the product

- **WHEN** the screen refuses a clear verdict for either contradiction
- **THEN** it reports no typed finding, and nothing is recorded against the product on its behalf

## REMOVED Requirements

### Requirement: The screen reads only what it is given, and reports no finding

**Reason**: The requirement bundles two rules that have diverged. What it says about reading only the context it is invoked with is unchanged and continues to hold; what it says about reporting no finding was written when nothing downstream read a compliance verdict from a product and no sink accepted one, and this change makes both false. Splitting rather than modifying keeps the surviving rule's reasoning intact instead of editing a paragraph out of the middle of it.

**Migration**: The reading rule is re-stated verbatim as *The screen reads only what it is given*, below, with no change to its normative content or its scenarios. The finding rule is replaced by *The screen reports what it established as a typed finding*, which reports one on exactly the two routes that establish something about the product and none on every other route — so the previous requirement's guarantee, that nothing is recorded where nothing was established, is preserved and narrowed rather than dropped.

## ADDED Requirements

### Requirement: The screen reads only what it is given

The screen SHALL read the product and the step from the context it is invoked with, and SHALL NOT fetch a product, a playbook or a category taxonomy of its own. Every value it passes on from that context SHALL be the value itself, as the catalog holds it and as a reader would recognise it — never a rendering of the object carrying it.

This is stated because the failure is silent: the model answers plausibly whatever it was asked, so a malformed product name produces a well-formed verdict, and nothing anywhere reports that the screen was asked about something that does not exist. Neither the outcome proposed nor the text produced reveals it. This capability inherits that lesson rather than relearning it.

#### Scenario: The product is taken from the context

- **WHEN** the screen is invoked for a step on a launch
- **THEN** it screens the product its context carries, and performs no lookup of its own

#### Scenario: A value reaching the model is the value, not its object's rendering

- **WHEN** the screen passes on a value the product carries as a value object
- **THEN** what reaches the model is that object's value, carrying nothing of the object's rendering — neither its type name, nor its field name, nor the quoting around its value

### Requirement: The screen reports what it established as a typed finding

The screen SHALL report a typed finding alongside its outcome on exactly the two routes that establish something about the product, and SHALL report none on every other route.

- A **clear** verdict establishes that the product falls in none of the categories the step names. The finding SHALL carry that as an **empty** set of categories — a value that is present and empty, which `launch-instance` admits one spelling of, and which is the fact that distinguishes a screened product from an unscreened one.
- A **flagged** verdict **naming at least one category** establishes which categories the product falls in. The finding SHALL carry exactly those categories, as the response named them. A flagged verdict naming none establishes nothing and is governed below.

The screen SHALL report **no** finding for an undetermined verdict, a verdict that could not be read, a verdict either contradiction refuses, a flagged verdict naming no category, an absent product, and a step naming no categories. None of these establishes anything about the product, and each of them is a state in which a recorded "screened, nothing found" would be a false assertion — the precise error this capability's satisfaction rule exists to prevent, displaced from the outcome onto the product.

**Reporting no finding SHALL leave what the product already carries untouched.** A screening that establishes nothing SHALL NOT erase a flag an earlier screening recorded. The screen SHALL NOT report an empty finding in order to express that it established nothing; an empty finding is the clear verdict's own assertion and has a meaning of its own.

**The finding SHALL NOT name the field it is written to.** Where a value goes, and the wording that field reads as, are the registering deployment's knowledge — the rule `launch-step-automation` states for every handler, and this capability's handler is not an exception to it.

**Reporting a finding SHALL change neither the outcome proposed nor the text produced.** Every requirement above governing which verdict proposes satisfaction, which propose a non-terminal outcome, and what the text a member reads carries, holds unchanged. The finding is reported beside them, not in place of any of them.

#### Scenario: A clear verdict establishes an empty set of categories

- **WHEN** the screen resolves a step with a clear verdict its response does not contradict
- **THEN** it reports a typed finding whose value is an empty set of categories, distinct from reporting no finding at all

#### Scenario: A flagged verdict establishes the categories it named

- **WHEN** the screen resolves a step with a flagged verdict naming one or more categories
- **THEN** it reports a typed finding carrying exactly those categories

#### Scenario: An undetermined verdict establishes nothing

- **WHEN** the screen resolves a step with an undetermined verdict
- **THEN** it reports no typed finding, and in particular does not report an empty one

#### Scenario: An unreadable verdict establishes nothing

- **WHEN** the screen resolves a step for a response no verdict could be read from
- **THEN** it reports no typed finding

#### Scenario: A screen given nothing to work with establishes nothing

- **WHEN** the screen resolves a step for which no product could be resolved, or a step naming no categories
- **THEN** it reports no typed finding

#### Scenario: A prior flag survives a later screening that establishes nothing

- **WHEN** a product whose hazard categories were recorded as flagged is screened again and the screening establishes nothing
- **THEN** no finding is reported, and the product's recorded categories are unchanged

#### Scenario: The outcome and the produced text are unaffected

- **WHEN** the screen reports a typed finding alongside its outcome
- **THEN** the outcome proposed and the text a member reads are exactly what they would be for the same response without a finding

### Requirement: A flagged verdict naming no category establishes nothing

Where the screen's response reports a flagged verdict and names no category, the screen SHALL propose a non-terminal outcome, SHALL report no typed finding, and SHALL report the shortfall in wording distinct from the reasons the other routes carry.

A flagged verdict is a finding about the product: it asserts that the product falls in at least one of the categories the step names. A response asserting that while naming none has produced no fact — there is nothing to record and nothing for a member to act on beyond the assertion itself. Routing it to the flagged reason would put "this product is flagged" on the launch's record with no category behind it, and routing it to the undetermined reason would say the screen could not settle the question when the response says it did.

The outcome is non-terminal on the same terms as every other route that reaches one, so this requirement adds a destination rather than a new kind of outcome.

**This requirement narrows *Satisfaction is proposed only for a clear verdict*.** That requirement's flagged scenario is modified above so that its **WHEN** applies only where the response names at least one category, the scenario keeping its name, so that a single flagged response is not required to carry two different reasons. The narrowing is stated in both places rather than left to be inferred from their order.

#### Scenario: A flagged verdict naming nothing is not recorded as flagged

- **WHEN** the screen's response reports a flagged verdict and names no category
- **THEN** it proposes a non-terminal outcome and reports no typed finding

#### Scenario: Its reason is its own

- **WHEN** the screen reports the shortfall for a flagged verdict naming no category
- **THEN** the wording is distinguishable from the flagged reason and from the undetermined reason, rather than reusing either

### Requirement: The categories the screen names are the step's own wording, as an instruction to the model and not a check on it

The screen SHALL instruct the model to name each category using the wording the step's description uses for it. Where the model names a category, the screen SHALL carry that name through as the model produced it, apart from normalising surrounding whitespace and letter case, and SHALL NOT alter it otherwise.

**The screen SHALL NOT parse the step's description in order to check the model obeyed.** This capability already refuses to extract anything from that prose, and gives its reasons at length under *The screen is performed against the categories the step itself names*: a parser keeps what matches its shape and drops the rest, so a description naming both a referenced list and inline examples would be checked against the examples alone. A validator built on such a parse would reject correct answers drawn from the referenced half and accept nothing the parse missed. The obligation is therefore placed on the prompt, where it can be stated in full, rather than on a check that can only be built on a misreading.

**The consequence is accepted and stated rather than hidden.** Recorded category values are exactly as stable as the authored description. Re-authoring the description to name a category differently means later screenings record the new wording while earlier recordings keep the old, and nothing reconciles them; a category the description reaches by *referencing* a list rather than enumerating it has no authored wording to be verbatim to, and what is recorded for it is the model's own naming. A consumer of this field SHALL therefore treat it as the screen's report of what it found, in the authored vocabulary where one exists, and SHALL NOT treat it as a closed set of identifiers.

**Nothing SHALL be recorded that the response did not name.** The screen SHALL NOT supply a category from its own knowledge, infer one from the description, or substitute a canonical spelling for one the model produced.

**What the screen reports SHALL be a set.** `product-catalog` records a *set* of hazard categories, so two names that normalise to the same value SHALL be reported once, in the position of the first of them. Reporting a category twice would put it on the product's record twice and render it twice, and the duplication would be a fact about how the model phrased its answer rather than a fact about the product. A name that normalises to nothing at all SHALL be dropped on the same reasoning; where dropping leaves a flagged verdict naming no category, the requirement above governs what happens next.

#### Scenario: A repeated category is reported once

- **WHEN** the model names two categories whose names normalise to the same value
- **THEN** the screen reports that category once, in the position the first of them occupied

#### Scenario: A blank category name is dropped

- **WHEN** the model names a category whose name normalises to nothing
- **THEN** that name is not among the categories the screen reports

#### Scenario: The model is instructed to use the description's wording

- **WHEN** the screen builds the request it sends the model
- **THEN** that request instructs the model to name categories using the wording the step's description uses

#### Scenario: A named category is carried through unaltered

- **WHEN** the model names a category
- **THEN** what the screen reports is that name with surrounding whitespace and letter case normalised and nothing else changed

#### Scenario: The description is not parsed to validate a name

- **WHEN** the model names a category the step's description does not contain verbatim
- **THEN** the screen still reports it, having performed no extraction from the description to check it against

#### Scenario: No category is supplied that the response did not name

- **WHEN** the screen reports the categories a flagged verdict established
- **THEN** every one of them was named by the response, and none was added from the description or from the screen's own knowledge
