## MODIFIED Requirements

### Requirement: A carried finding's result is rendered ahead of its comment

Where a step's recording carries a finding, the launch detail page SHALL render that finding's **field and value first**, and the finding's comment after it, as two distinguishable parts of the outcome the page already renders.

**The result SHALL lead with the field and the value and nothing else.** No introductory sentence, no restatement of the step, no label narrating what is about to be shown — the field's name and its value are the whole of it. What the page is reporting is a fact the launch now asserts, and a reader scanning a column of them must be able to read the fact itself rather than a sentence containing it.

**The field SHALL be rendered as the words an admin uses, not as its storage identifier.** This capability already requires the outcome vocabulary be rendered as an admin's words rather than as its tokens, and a field name is the same kind of thing: `sub_category` is how a column is spelled, not how a person reads. The wording SHALL be supplied alongside the sink registration that names the field, so that naming a sink and naming how it reads are one act, and SHALL reach the page **on the carried finding itself** — the page SHALL NOT resolve it through a registry of its own. Where the carried finding has no wording, the field's own name SHALL be rendered rather than nothing — an unrendered fact is the failure this surface exists to prevent.

**An empty value SHALL be rendered as visible text standing for emptiness, inside the result itself, and that text counts as the value rather than as a label.** An empty value is a result — something was established and it was empty — and it is exactly the state a reader most needs distinguished from a step that established nothing. Rendering it as blank, as whitespace, as an element carrying a class and no text, or by omitting the result SHALL NOT satisfy this: a reader must be able to see that the answer was "none", not infer it from an absence.

*"Text", not "marker", deliberately.* This capability uses **marker** for a literal class name, and the class names this requirement fixes are named below; what an empty value needs is something a person reads.

**A value carrying several members SHALL be rendered as those members, each readable and separated from the next.** A finding's value is whatever its handler established, and it is not required to be a scalar; the first such value is a set of compliance categories. Rendering SHALL NOT present a multi-member value in a programming language's own notation for a collection — brackets, quotation marks around each member, or a type name — because the result element is prose an admin reads, and the surrounding requirement that it lead with the value and nothing else forbids decoration around it just as it forbids a label before it. Every member the finding carries SHALL appear; none SHALL be elided, summarised or truncated away, since a category omitted from a compliance result is the one a reader most needs.

**A textual value SHALL NOT be rendered as a collection of its characters.** A string is one member, not a sequence of them, and this is stated because the two are the same kind of thing to most languages and not to a reader — a sub-category rendered as its letters, separated, would satisfy a naive reading of the clause above.

**Emptiness outranks member rendering**: a value carrying no members is governed by the empty-value clause above and renders as text standing for emptiness, never as nothing at all.

**The result and the comment SHALL carry distinct literal markers in the rendered response.** The result element SHALL carry `finding-result` and the comment element `finding-comment`. The markers are given because they are what a test is derived from, exactly as this capability's outcome-tag requirement already does — and they are a **necessary and not a sufficient** condition: carrying them satisfies this clause and does not by itself satisfy the one below.

**The distinction SHALL be carried by structure, not only by colour.** The result and the comment SHALL be separate block-level elements, and a separating element carrying `finding-divide` SHALL sit between them. That separation is observable in the rendered response, which is what makes this requirement assertable rather than a matter of opinion — and it is what a reader who cannot distinguish the colours, or who is reading in the theme the colour was not chosen for, has left.

Colour MAY carry the distinction in addition, and where it does it SHALL come from the presentation vocabulary's own tokens rather than from literal values, so that both themes are covered by construction. **A rendering distinguished only by a colour declaration SHALL NOT satisfy this**, whatever class names it carries.

Weight, spacing and which token is used are not fixed here. They are visual judgements settled by looking at the running page, and fixing them in a specification would be pretending a test can decide them. How members are separated from one another is the same kind of judgement and is likewise not fixed; that they are separated, and individually readable, is.

**A recording carrying no finding SHALL render as it does without this change.** That is every recording made before this capability existed and every recording by a handler reporting no finding, so the unchanged path is the common one and SHALL NOT be disturbed.

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

#### Scenario: A value of several members renders as those members

- **WHEN** the detail page renders a step whose carried finding has a value carrying several members
- **THEN** every member appears in the result, each readable and separated from the next, with no bracket, quotation mark or type name from a collection's programming notation around them

#### Scenario: A textual value is not rendered as its characters

- **WHEN** the detail page renders a step whose carried finding has a textual value
- **THEN** that text is rendered as one value, not as its characters separated from one another

#### Scenario: The distinction survives without colour

- **WHEN** a carried finding's result and comment are rendered
- **THEN** they are separate block-level elements with a separating element carrying `finding-divide` between them, so that a rendering whose only difference is a colour declaration does not satisfy this

#### Scenario: A recording with no carried finding is rendered unchanged

- **WHEN** the detail page renders a step whose recording carries no finding
- **THEN** its outcome renders as it did before this capability existed

#### Scenario: The evidence and provenance are still rendered

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the verbatim evidence and the recording's provenance are rendered as well, the result and comment leading rather than replacing them
