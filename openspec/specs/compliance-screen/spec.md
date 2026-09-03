# compliance-screen Specification

## Purpose
The second step handler with judgement in it: given a product and the screening step it is resolving, it screens that product against the prohibited and high-compliance categories the step itself names, and proposes the step's satisfying outcome only where it can support that the product is clear of them — the work `lp.strategy.006` describes, performed before money is spent on sourcing. It screens; it never decides.

## Requirements

### Requirement: The screen is performed against the categories the step itself names

The categories the screen tests a product against SHALL be read from the description of the step being resolved, as the served playbook holds it. They SHALL NOT be held as a list in the screening code, and SHALL NOT be supplied by the screen's own knowledge of what Amazon prohibits.

The authored step already carries the list — it is the sentence a member reads when they open the step — and `playbook-authoring` already owns editing it against the live set, recording who edited it and when. A copy in code would be a second statement of the same thing with no mechanism keeping the two in step, and the failure would be silent in the worst direction: the step would say one thing to the member reading it and the screen would test another.

**A consequence follows, and is stated here rather than discovered later: editing that step's description edits the screen.** Rewording the sentence for readability changes what is tested, with no deploy and no code review. This is the accepted cost of one source of truth. It is acceptable because the alternative — a list in code — makes the same divergence permanent instead of momentary, and because the step's description is already the thing a member is asked to act on, which is a strictly larger power over the same step than changing what the screen tests.

**The text the screen produces SHALL state the categories it screened against, and SHALL state them as the screen read them from the description.** This SHALL be rendered by the screen from what it read, and SHALL NOT be taken from the model's response — the requirement below forbids code from inspecting the comment's content, so a citation carried only by the comment is one nothing can rely on and nothing can assert. Without this, a description edited to name fewer categories leaves no trace on any launch the narrowed screen ran on, and the consequence accepted above would be accepted against a record that cannot show it.

**The screen SHALL carry the description's text through unaltered — into what it asks the model and into what it cites — and SHALL extract nothing from it.** It does not parse the description into a list of category names, and does not select the part of it that looks like a list. A description naming both a referenced list and an inline parenthetical of examples is the ordinary case, and an extraction step would plausibly keep the parenthetical and silently drop the reference, so the citation would understate what was screened while every assertion written against the parenthetical items still passed. Carrying the text through is also what keeps this requirement consistent with the rest of the capability: a screen that parsed prose to say what it screened against would be doing, in its own citation, the thing the verdict requirement forbids it doing to the model's answer.

Where the step being resolved carries no description, or one that is empty or whitespace-only, the screen SHALL propose a non-terminal outcome whose reason states that the step names no categories to screen against; it SHALL NOT fall back to any list of its own, and SHALL NOT call the model. A screen with nothing to screen against has not found the product clear; it has not screened, and a model asked to screen against nothing would answer anyway.

#### Scenario: The step's description is what the product is tested against

- **WHEN** the screen resolves a step whose description names a set of prohibited and high-compliance categories
- **THEN** the judgement it produces is made against those categories

#### Scenario: The produced text cites what was screened against

- **WHEN** the screen produces text for any verdict it reaches after reading a step's description
- **THEN** that text states the categories the screen read from that description, rendered from what the screen read rather than taken from the model's response

#### Scenario: An edited description changes what is screened

- **WHEN** the step's description is re-authored to name a different set of categories, and the screen runs again
- **THEN** the product is tested against the newly authored categories, and the text produced cites the newly authored categories, without any change to the screening code

#### Scenario: A step naming no categories is not a clear product

- **WHEN** the screen resolves a step that carries no description, or one that is empty or whitespace-only
- **THEN** it proposes a non-terminal outcome whose reason states that the step names no categories to screen against, proposes no satisfying outcome, and makes no model call

### Requirement: A verdict distinguishes clear, flagged and undetermined

The screen SHALL establish its verdict from a structured, schema-validated response, and that response SHALL distinguish exactly three states:

- **clear** — the product falls in none of the categories the step names;
- **flagged** — the product falls in at least one of them;
- **undetermined** — what the screen was given does not settle which of the two it is.

The verdict SHALL be read from that structured discriminant and SHALL NEVER be searched for in prose. The three states SHALL be distinguishable in the record without reading the accompanying text, because they carry three different meanings for the launch: a step that may be satisfied, a finding about the product that a member must act on, and a shortfall in what the screen could establish.

**Undetermined is a first-class verdict, not a failure.** Most of what decides a hazmat or high-compliance classification — whether the item contains a lithium battery, a pressurised gas, a liquid over a volume threshold, a magnet, an ingestible — is not derivable from a product's name, which is the substance of what the screen is given. A screen that had to answer clear-or-flagged would answer one of them by guessing, and a guessed "clear" on this step is the failure the step exists to prevent.

Every verdict SHALL be accompanied by a comment that is neither empty nor whitespace-only, and that comment SHALL be carried into the text a member reads. A response established as carrying a verdict but whose comment is empty or whitespace-only SHALL be treated exactly as an unreadable verdict is treated below — a shortfall in what the model produced, not evidence to be trusted with a judgement.

The screen SHALL prompt for the comment to state, for a clear verdict, the categories considered and why none applies; for a flagged verdict, which categories the product falls in and what that implies for the launch; and for an undetermined verdict, what fact about the product would settle it — so that a member reading it knows what to supply rather than only that the screen declined.

**Those three are prompting obligations, and whether the comment actually contains that content SHALL NOT be verified by code.** Only that the comment is neither empty nor whitespace-only is checked. Checking prose for the presence of particular content is the free-text-parsing fragility this project has already retired once in `subcategory-advisor`, and reintroducing it here would undo that. The system already extends the model this same trust for the verdict's own justification; requiring the content is an obligation on the prompt, not a runtime guarantee this capability makes.

#### Scenario: A verdict is read from the discriminant, not the prose

- **WHEN** the screen's structured response carries a verdict whose accompanying comment reads as though it says something else
- **THEN** the verdict acted on is the one the structured response carries, and the comment is never parsed to establish it

#### Scenario: A comment's content is never checked by code

- **WHEN** the screen's structured response carries a verdict with a comment that is neither empty nor whitespace-only
- **THEN** the screen routes that verdict as the requirement below states, whatever the comment's content is — including a comment that omits the categories considered, the categories flagged, or the settling fact the prompt asked for, since detecting that omission would require parsing prose content, which this capability does not do

#### Scenario: A verdict's comment reaches the reader

- **WHEN** the screen reaches any verdict with a comment
- **THEN** that comment is carried into the text a member reads, alongside the verdict and the cited categories

#### Scenario: A verdict with an empty comment is treated as unreadable

- **WHEN** the screen's structured response carries a verdict but its comment is empty or whitespace-only
- **THEN** the screen proposes a non-terminal outcome, exactly as it would for an unreadable verdict

### Requirement: Satisfaction is proposed only for a clear verdict

The screen SHALL propose the step's satisfying outcome only where its verdict is clear and its comment is neither empty nor whitespace-only. A flagged verdict, an undetermined verdict, an unreadable verdict, and a step naming no categories SHALL each produce a **non-terminal** outcome whose reason states which of them occurred — never a satisfying outcome accompanied by text admitting the product was flagged or the question was not settled.

This is `subcategory-advisor`'s rule, and it binds harder here. Under `launch-step-automation` a terminal proposal on a step naming a confirmer is held for that member's acceptance, while a non-terminal one is recorded directly with its reason. The step exists to catch a category **before sourcing**, so a satisfying proposal carrying a flag in its prose would put a production run one unread paragraph away from being committed against a product Amazon will not let the seller ship.

The reasons SHALL be distinguishable from one another. A flagged verdict is a finding about the product — the screen did its work and the answer was unwelcome. An undetermined verdict is a statement about what the screen was given. An unreadable verdict is a shortfall in what the model produced. Recording any of them under another's reason misstates on the launch's own record what happened, and a member reading "could not screen this product" where the truth was "this product is a supplement" would take the wrong next action.

#### Scenario: A clear verdict proposes satisfaction

- **WHEN** the screen's verdict is clear and its comment is neither empty nor whitespace-only
- **THEN** it proposes the step's satisfying outcome, carrying the cited categories, the verdict and the comment as the text a member reads

#### Scenario: A flagged verdict proposes a non-terminal outcome

- **WHEN** the screen's verdict is flagged
- **THEN** it proposes a non-terminal outcome whose reason names the product and states that the screen flagged it, and the text a member reads carries the comment

#### Scenario: An undetermined verdict proposes a non-terminal outcome

- **WHEN** the screen's verdict is undetermined
- **THEN** it proposes a non-terminal outcome whose reason states that the screen could not settle the question from what it was given, and that reason differs from the one a flagged verdict produces

#### Scenario: An unreadable verdict is not reported as a judgement about the product

- **WHEN** the screen's response validates against no verdict that can be read
- **THEN** it proposes a non-terminal outcome whose reason states that no verdict could be read, and that reason does not state that the product was flagged or that it is clear

### Requirement: A verdict its own response contradicts is not satisfaction

Where the screen's response reports a clear verdict and, in the same response, states that it could not screen the product, the screen SHALL propose a non-terminal outcome and SHALL NOT propose satisfaction. The text a member reads SHALL carry the contradicting statement, not only the clear verdict — the contradiction is what the reader must see, and a rendering showing a bare "clear" would show them a judgement the response itself withheld.

This is kept for the same reason `subcategory-advisor` keeps it: a false satisfying proposal reaching a member is worse than a false non-terminal one, and this is the one direction in which prose may still act. It does not require judging whether the comment's required content is present — only whether the response states an inability to screen at all.

**The statement withholding support SHALL be one about the screen's own ability to screen, not about a category.** A comment describing a category the product cannot fall in, or a classification the screen ruled out, is a statement about that category and SHALL NOT trigger this veto — the same distinction `subcategory-advisor` draws for a rejected alternative described as unsupportable. Vetoing on such a statement would block the step on every pass for that product, since the same prompt yields the same shape.

#### Scenario: A clear verdict carrying a stated inability is refused

- **WHEN** the screen's response reports a clear verdict while also stating that the screen could not screen the product
- **THEN** it proposes a non-terminal outcome, and the text a member reads carries the stated inability

#### Scenario: A statement about a category does not withhold satisfaction

- **WHEN** the screen's response reports a clear verdict whose comment states that a named category cannot apply to the product
- **THEN** it proposes the step's satisfying outcome, that being a statement about the category rather than about the screen's own ability to screen

### Requirement: Model failure is surfaced, not masked

If the underlying language model call fails, or returns content that is not a plain string, the screen SHALL surface that failure rather than proposing a fabricated, empty or silently degraded verdict. Such a failure SHALL NOT be routed to the unreadable-verdict path, nor to any other non-terminal outcome.

The distinction is between a completed call whose response mapped to no verdict — a shortfall in what the model produced, which the requirements above route — and a transport- or client-level fault prior to any response existing at all. `launch-step-automation` reports a raising handler naming the launch, step and handler, records nothing against the step, and continues the pass; that is the correct treatment, and this requirement exists so that a later broad `except` cannot quietly replace it.

Recording a model outage as a non-terminal outcome would enter a client fault on the launch's own record as the screen's judgement about a product — the substitution `launch-step-automation` refuses when it declines to let a crash be recorded as a handler's finding — and would additionally suppress the operator-facing fault report, leaving an outage indistinguishable from a badly-formed response.

#### Scenario: A failing model call surfaces as a failure

- **WHEN** the configured language model is unavailable or returns an error while the screen is producing a verdict
- **THEN** the invocation fails visibly, no outcome is proposed, and the failure is not recorded as a verdict about the product

#### Scenario: Response content that is not a plain string surfaces as a failure

- **WHEN** the configured language model's response content is not a plain string
- **THEN** the invocation fails visibly rather than yielding a verdict coerced or fabricated from that content

### Requirement: The structured-output schema is one the model provider's adapter accepts

The schema the screen hands the model provider to constrain its response SHALL be one that provider's adapter accepts, and acceptance SHALL be established by exercising the provider adapter's **own** conversion rather than any stand-in for it. This check requires no model call, no network access and no credential, so nothing about its cost justifies substituting a double for it.

The schema converted by that check SHALL be the one the screen actually passes at its structured-output call site, not a module-level symbol that is merely expected to be the same. A guard that converts a symbol the call site has stopped using guards nothing.

*Rationale, not itself normative: this screen's schema carries a construct the existing handler's does not — a discriminant of three named values rather than a boolean. Reasoning that a construct is inside a provider's accepted subset is exactly the reasoning that made `subcategory-advisor` inert at every invocation, so this capability establishes acceptance by conversion rather than by argument. The requirement is the general rule, not a rule about that construct.*

The shape crossing the model boundary MAY differ from the shape the screen reports to its own callers. Where the two differ, the screen SHALL convert the provider's parsed response into its reported results, and that conversion SHALL be defined for **every** combination of fields the wire schema can express — not only those a well-behaved model is expected to produce. No combination SHALL be left without a defined destination. How each destination is then treated is governed entirely by the requirements above and SHALL NOT be restated here.

Every field of the wire schema SHALL carry a description stating what it is for and when it is to be populated — the required discriminant as well as the optional prose. Where a wire shape drops the structural coupling the reported verdicts have, it SHALL replace that coupling with something the model can read, rather than leaving it implicit in the prompt alone; and a required field whose permitted values decide how every optional one is to be filled is exactly where that reading starts.

#### Scenario: The schema is accepted by the provider's own conversion

- **WHEN** the schema the screen passes at its structured-output call site is converted by the model provider's adapter
- **THEN** the conversion succeeds, and this is verified without invoking a model, opening a network connection, or supplying a credential

#### Scenario: The converted schema is the one the call site passes

- **WHEN** the screen's structured-output call site passes a schema other than the one a guard converts
- **THEN** that divergence is detectable, since the guard obtains its schema from the call site rather than by importing a symbol independently

#### Scenario: Every wire combination has a defined destination

- **WHEN** the provider returns any response that parses against the wire schema
- **THEN** the screen's conversion yields exactly one of its defined destinations, with no combination of fields left to fall through to an unintended route

#### Scenario: Wire fields state when they are to be populated

- **WHEN** the wire schema is generated
- **THEN** each of its fields carries a description stating what it is for and when it is to be populated

### Requirement: The screen reads only what it is given, and reports no finding

The screen SHALL read the product and the step from the context it is invoked with, and SHALL NOT fetch a product, a playbook or a category taxonomy of its own. Every value it passes on from that context SHALL be the value itself, as the catalog holds it and as a reader would recognise it — never a rendering of the object carrying it.

This is stated because the failure is silent: the model answers plausibly whatever it was asked, so a malformed product name produces a well-formed verdict, and nothing anywhere reports that the screen was asked about something that does not exist. Neither the outcome proposed nor the text produced reveals it. This capability inherits that lesson rather than relearning it.

The screen SHALL report no typed finding alongside its outcome. Its verdict is carried by the outcome and the evidence, which is where the launch and its readers consume it; nothing downstream reads a compliance verdict from a product today, and reporting a finding no sink accepts would record nothing while implying something was recorded.

#### Scenario: The product is taken from the context

- **WHEN** the screen is invoked for a step on a launch
- **THEN** it screens the product its context carries, and performs no lookup of its own

#### Scenario: A value reaching the model is the value, not its object's rendering

- **WHEN** the screen passes on a value the product carries as a value object
- **THEN** what reaches the model is that object's value, carrying nothing of the object's rendering — neither its type name, nor its field name, nor the quoting around its value

#### Scenario: No finding accompanies the outcome

- **WHEN** the screen resolves a step with any verdict
- **THEN** it reports an outcome and the text a member reads, and no typed finding

### Requirement: The screen is reached only through the step it is authored onto

The screen SHALL be resolvable as a registered step handler under a name whose first segment is the discipline it is written for, and SHALL be registered in every process that consults the handler registry. That correspondence is a convention of where handlers are grouped, not a rule the registry enforces.

Which step it runs for SHALL be a property of the authored playbook and never of the screening code: the screen SHALL NOT test the identifier, discipline or gate of the step it was invoked for, and SHALL screen whatever step names it. A step naming this handler that names no categories is handled by the first requirement above, which is the only sense in which the screen inspects what step it was given.

Registration SHALL load nothing the screen needs in order to run. A process that consults the registry in order to report which handlers it answers for, or to validate an activation against it, SHALL pay only the cost of the name becoming resolvable.

#### Scenario: The handler is resolvable in every process consulting the registry

- **WHEN** a process consults the handler registry
- **THEN** this screen's name is registered in it, whether that process serves the admin surface or runs the automation pass

#### Scenario: The screen does not test which step invoked it

- **WHEN** the screen is invoked for a step whose identifier and discipline are not the ones it was written for, and which names categories in its description
- **THEN** it screens against that step's categories and proposes an outcome, refusing nothing on the basis of the step's identifier, discipline or gate

#### Scenario: Registration loads nothing the run needs

- **WHEN** the module holding this screen is imported so that its name becomes resolvable
- **THEN** no model is constructed, no credential is read, and no graph library is imported
