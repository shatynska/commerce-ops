## MODIFIED Requirements

### Requirement: A carried finding's result is rendered ahead of its comment

Where a step's recording carries a finding, the launch detail page SHALL render that finding's **field and value first**, and the finding's comment after it, as two distinguishable parts of the outcome the page already renders.

**The result SHALL lead with the field and the value and nothing else.** No introductory sentence, no restatement of the step, no label narrating what is about to be shown — the field's name and its value are the whole of it. What the page is reporting is a fact the launch now asserts, and a reader scanning a column of them must be able to read the fact itself rather than a sentence containing it.

**The field SHALL be rendered as the words an admin uses, not as its storage identifier.** This capability already requires the outcome vocabulary be rendered as an admin's words rather than as its tokens, and a field name is the same kind of thing: `sub_category` is how a column is spelled, not how a person reads. The wording SHALL be supplied alongside the sink registration that names the field, so that naming a sink and naming how it reads are one act, and SHALL reach the page **on the carried finding itself** — the page SHALL NOT resolve it through a registry of its own. Where the carried finding has no wording, the field's own name SHALL be rendered rather than nothing — an unrendered fact is the failure this surface exists to prevent.

**An empty value SHALL be rendered as visible text standing for emptiness, inside the result itself, and that text counts as the value rather than as a label.** An empty value is a result — something was established and it was empty — and it is exactly the state a reader most needs distinguished from a step that established nothing. Rendering it as blank, as whitespace, as an element carrying a class and no text, or by omitting the result SHALL NOT satisfy this: a reader must be able to see that the answer was "none", not infer it from an absence.

*"Text", not "marker", deliberately.* This capability uses **marker** for a literal class name, and the class names this requirement fixes are named below; what an empty value needs is something a person reads.

**The result and the comment SHALL carry distinct literal markers in the rendered response.** The result element SHALL carry `finding-result` and the comment element `finding-comment`. The markers are given because they are what a test is derived from, exactly as this capability's outcome-tag requirement already does — and they are a **necessary and not a sufficient** condition: carrying them satisfies this clause and does not by itself satisfy the ones below.

**The distinction SHALL be carried by structure, not only by colour.** The result and the comment SHALL be **separate block-level elements, one following the other**, neither containing the other.

**No separating element is required between them, and none SHALL be relied on to carry the distinction.** An earlier statement of this requirement demanded one. The break between two blocks does the same work: two blocks on two lines are as visible to a reader who sees no colour as a rule between them would be, and a drawn rule in a scanned table column reads as furniture the column does not need. What is dropped is a *particular* means; the property it existed to guarantee is unchanged and is stated here and below.

**The two SHALL be laid out one below the other, and no rule in the served stylesheet SHALL place them side by side.** Being block-level in the markup does not settle this and must not be mistaken for settling it: an ancestor laying its children out in a row overrides it, which is exactly how the three parts of a carried finding came to render as three narrow columns on the live page. The layout obligation is therefore stated over the stylesheet, where the failure actually lives, and not left to be entailed by the markup, where it is not.

Colour MAY carry the distinction in addition, and where it does it SHALL come from the presentation vocabulary's own tokens rather than from literal values, so that both themes are covered by construction. **A rendering distinguished only by a colour declaration SHALL NOT satisfy this**, whatever class names it carries.

Weight, spacing and which token is used are not fixed here. They are visual judgements settled by looking at the running page, and fixing them in a specification would be pretending a test can decide them.

**The result, the comment, the verbatim evidence and the provenance SHALL be bounded together, within one container carrying `evidence-clamp`, and one disclosure control on the cell SHALL reveal all of them.** Closed, the outcome occupies a bounded height — a scanned table column cannot afford a cell that grows with a model's prose. Opened, everything the recording carries is visible. Bounding the parts separately, or leaving one of them outside the bound, SHALL NOT satisfy this: a reader pressing the control expects the cell to open, not a portion of it.

**A bound of this kind is not truncation, and is not rendering a fact as not displayed.** This capability requires elsewhere that an automated handler's evidence be laid out within a bounded measure and **SHALL NOT be truncated**, and that no rule render a fact this surface exists to show — a step's recorded provenance among them — or a container holding one, as not displayed. Those obligations stand unchanged and are not weakened here. They are about **loss**: an ellipsis that suppresses the field explaining why a step was refused, or a rule that quiets a fact the admin came for. A bound whose full content is present in the response and is revealed in full by a control on the same cell loses nothing and quiets nothing — it is the shape this capability's evidence already takes, and extending it to the provenance changes how much a reader must press to see, not whether they can. A bound that could not be opened, or that dropped content from the response, would breach both of those requirements and SHALL NOT be adopted.

**That bound SHALL be one the browser applies to block content, and SHALL NOT be expressed as a count of lines.** A line-count bound is defined over inline content, and the parts of a carried finding are blocks; a rendering that bounds blocks by line count is undefined across browsers and clips the established fact on some of them. This is stated because the failure is silent and looks like a styling preference rather than a defect.

**A recording carrying no finding SHALL render the same facts, in the same order, as it does without this change.** That is every recording made before this capability existed and every recording by a handler reporting no finding, so the unchanged path is the common one and SHALL NOT be disturbed. This is a statement about what a reader sees, and it is not satisfied merely by the markup being identical: rules reaching the bounding container reach that cell too, so a change to them is a change to this path and SHALL be looked at on it.

**The verbatim evidence and the provenance SHALL still be rendered.** The result and comment lead the cell; they do not replace what the page already shows. The evidence is the record of what a member was shown, and a presentation that dropped it in favour of a tidier rendering would lose the only account of what was actually read.

#### Scenario: The field and value lead the outcome

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the finding's field and value are rendered ahead of the comment, the result element carrying `finding-result` and the comment element `finding-comment`

#### Scenario: The result carries no leading prose

- **WHEN** the detail page renders a carried finding's result
- **THEN** what precedes the field in that result is nothing — no introductory sentence and no narrating label

#### Scenario: The field reads as an admin's words

- **WHEN** the detail page renders a carried finding that carries a wording for its field
- **THEN** that wording is rendered rather than the storage identifier

#### Scenario: A field with no supplied wording still renders

- **WHEN** the detail page renders a carried finding that carries no wording
- **THEN** the field's own name is rendered rather than nothing

#### Scenario: An empty value renders as readable text

- **WHEN** the detail page renders a step whose carried finding has an empty value
- **THEN** the result carries visible text standing for emptiness, distinguishable from a step whose recording carries no finding at all

#### Scenario: The distinction survives without colour

- **WHEN** a carried finding's result and comment are rendered
- **THEN** they are separate block-level elements, neither containing the other, so that a rendering whose only difference is a colour declaration does not satisfy this

#### Scenario: No separating element is required

- **WHEN** a carried finding's result and comment are rendered with no element between them
- **THEN** the rendering satisfies this requirement, the break between the two blocks being the separation

#### Scenario: No rule lays the two out in a row

- **WHEN** the served stylesheet is read
- **THEN** no rule reaching the container of a carried finding's result and comment lays its children out in a row

#### Scenario: The whole outcome opens together

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the result, the comment, the verbatim evidence and the provenance are all within one container carrying `evidence-clamp`, none of them bounded independently of the others

#### Scenario: The bound is not a count of lines

- **WHEN** the served stylesheet is read
- **THEN** the rule bounding the container carrying `evidence-clamp` does not bound it by a count of lines

#### Scenario: A recording with no carried finding is rendered unchanged

- **WHEN** the detail page renders a step whose recording carries no finding
- **THEN** its outcome renders the same facts, in the same order, as it did before this capability existed

#### Scenario: The evidence and provenance are still rendered

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the verbatim evidence and the recording's provenance are rendered as well, the result and comment leading rather than replacing them
