## MODIFIED Requirements

### Requirement: The step form carries every authorable field

The step form SHALL offer every field the authoring capability accepts: the name, the description, the assignees, the kind, whether the result needs confirmation, the status, the hazard, the gate it starts at, the steps it waits on, and — for an `automated` step — the automation brief and the handler, alongside the gate, scope, timing anchor and blocking flag it already carries.

The name and the description SHALL be distinct inputs, and the description's input SHALL accept more than one line: a single-line box for a field whose whole purpose is to be longer than the name would teach the author the opposite of what the two fields are for.

Assignees SHALL be chosen from the roster's active people rather than typed, so an author cannot name a person who does not exist and cannot mistype an identifier. The people offered SHALL be identified by their display names, since an author knows colleagues by name and not by generated identifier.

Fields that carry no meaning for the step's current kind — an automation brief on a `human` step — SHALL either be hidden or render disabled, so the form does not invite a value the write would refuse.

The start-gate control SHALL offer the framework's gates other than the final one, which is refused as a start gate, and an explicit "starts immediately" choice — that being a meaningful authored value rather than an empty field, and the two being indistinguishable in a control that offered only gates.

The control for the steps a step waits on SHALL admit more than one step, and SHALL offer **the `active` steps only**, excluding the step being edited. Both exclusions are the same rule this requirement already states for a field that carries no meaning: the write refuses a dependency on a step that is not `active`, and refuses a self-reference as the cycle it is, so offering either invites a value the write would reject. Restricting the options also keeps the served and unserved steps apart in the way the step table is separately required to.

It SHALL present those steps grouped by the gate they belong to, and SHALL identify each option by both its identifier and its name. Where assignees are a handful of colleagues an author knows by name, this control ranges over the served step set — steps in the dozens — and a flat list identified one way is not a set a person can choose from.

The start-gate control SHALL NOT filter its gates against the step's current gate, though the write refuses a start gate later than it. That refusal is a *combination* fault under *A rejected write names the fields its faults concern* — neither value is wrong alone — so an author may equally mean to move the step's gate, and a control that hid the later gates would silently decide which half of the pair they meant. This is the one place the form offers a value the write may refuse, and it is offered for that reason rather than in spite of it.

Neither control SHALL be worded so that it reads as the step's own gate, and neither SHALL be worded as *blocking* or *blocked*. This surface already carries the step's blocking flag, and the launch surfaces carry a `Blocked` outcome; a third sense of the word across the authoring and launch pages would make both unreadable.

#### Scenario: The form offers name and description separately

- **WHEN** a step's form is opened
- **THEN** the name and the description are separate inputs, and the description accepts line breaks

#### Scenario: Assignees are chosen from the roster

- **WHEN** the assignee control is opened
- **THEN** it offers the roster's active people by display name, and does not accept a free-typed identifier

#### Scenario: A form rejected by validation shows every fault with the typed values

- **WHEN** a submitted step violates two of the new field rules at once
- **THEN** the re-rendered form reports both faults and still holds what was typed, and the step set is unchanged

#### Scenario: The form offers both start fields

- **WHEN** a step's form is opened
- **THEN** it offers a control for the gate the step starts at and a control for the steps it waits on

#### Scenario: Starting immediately is an offered choice

- **WHEN** the start-gate control is opened
- **THEN** "starts immediately" is among its options, and the final gate is not

#### Scenario: The dependency control is grouped and self-excluding

- **WHEN** the control for the steps a step waits on is opened
- **THEN** the steps are grouped by gate, each identified by its identifier and its name
- **AND** the step being edited is not among them
- **AND** no step that is not `active` is among them

### Requirement: Every rule an authoring write can provoke attributes its fault

Every coherence rule and parse failure that a submitted **edit or
create** can provoke SHALL be attributed to the fields it concerns, or
SHALL satisfy the page-level criterion below. There SHALL be no rule
whose fault the surface fails to recognise by accident.

The page-level criterion is a property of the fault, not a decision the
attribution records: a fault is held at page level when **it concerns no
control the authorable form carries** — a fault about the step set as a
whole, or about a gate. Stating it this way is deliberate. Were
"deliberately page-level" defined as whatever attribution declines to
attribute, this requirement would be satisfiable by declaring every gap
deliberate, and it would assert nothing.

This requirement exists because some faults are attributed by matching
message text authored in another layer. A rule reworded there would
silently stop matching and degrade to page level, which the requirement
above permits by design — so nothing about the rendering would reveal
it. The obligation is therefore stated over the rules as a set rather
than over any one rendering.

Rules a write cannot provoke are outside this requirement — the gate
sequence is constructed by the system rather than submitted, and step
identifiers are generated rather than typed — since a rule that cannot
be provoked cannot be checked by provoking it.

The rules governing when a step starts are all provokable by an edit, and each SHALL be attributed rather than left to the page level, since each concerns a control the form now carries. They are: a start gate naming no known gate; a start gate later than the step's own gate; a start gate naming the final gate; a dependency naming a step that is not `active`, that no step in the set carries, or that is classified `prohibited-tactic`; a cycle among dependencies; and a blocking step whose transitive dependencies include one starting later than its own gate. Each SHALL be attributed by **the declaration it turns on**, and never by a fixed control per fault kind, since most of these rules can be provoked from more than one field:

- A start gate naming no known gate, and one naming the final gate, concern the start-gate control alone.
- A start gate later than the step's own gate is a **combination** fault under the rule above: neither value is wrong on its own, and an author may have provoked it by lowering the step's gate as readily as by raising its start gate, so it SHALL mark the gate control and the start-gate control both.
- A dependency naming a step that is not `active`, that no step in the set carries, or that is classified `prohibited-tactic`, concerns the dependency control.
- A cycle and a transitive-deadlock fault name more than one step and SHALL be attributed under the multi-step case of *A rejected write names the fields its faults concern*, which states which controls are marked and why. That case governs; this requirement does not restate it.

Stating this by provoking declaration rather than by fault kind is what keeps the requirement satisfiable: an enumeration fixed to one control per rule leaves an author who provoked a fault from another field looking at an unmarked form, which is the "falls through unrecognised" this requirement forbids.

#### Scenario: No rule an authoring write can provoke is unattributed by accident

- **WHEN** every rule an edit or a create can provoke is provoked in
  turn
- **THEN** each resulting fault is either attributed to the fields it
  concerns, or concerns no control the authorable form carries
- **AND** no fault falls through unrecognised

#### Scenario: Each start rule is attributed to its control

- **WHEN** each of the rules governing when a step starts is provoked in turn by an edit
- **THEN** each fault about a start gate is attributed to the start-gate control, and each fault about a dependency to the dependency control
- **AND** none of them falls through to the page level

### Requirement: A rejected write names the fields its faults concern

A surface **carrying the authorable form** — the edit form and the
create surface — SHALL name, for each fault it reports, the form fields
that fault concerns, so that an admin reads which controls to touch
rather than translating prose back into inputs.

This requirement binds those two surfaces only. The step list also
renders rejections of a move, and carries no authorable form for a
fault to be attributed against; that rejection SHALL keep rendering at
page level exactly as it does. Retiring, un-retiring and changing
status are no longer list-level writes — they are submitted through
the edit form's `status` field, the same write path an ordinary field
edit uses — so a rejection of any of them is a rejection of the edit
form, and SHALL be attributed exactly as any other edit-form rejection
is, not exempted the way the list's own rejections are.

Attribution SHALL be **additional to** the fault list, never a filter:
every fault the write reported SHALL still be rendered in full, in the
surface's own fault list, whether or not it was attributed. A fault the
surface cannot attribute SHALL be rendered at page level, exactly as it
would have been without this requirement — an unrecognised fault
degrades, it does not disappear.

Faults concern fields in four ways, and each SHALL be treated
differently:

- A fault about **one field** SHALL mark that field.
- A fault about a **combination of fields** SHALL mark **every** field
  in the combination. Neither value is wrong on its own — an `automated`
  step carrying no automation brief is refused for the pair, and
  changing either the kind or the brief resolves it — so marking one
  would tell the admin to change that one.
- A fault about **several steps** — a cycle among dependency
  declarations, or a blocking step whose transitive dependencies start
  too late — SHALL mark, on the form of the step being edited, **every**
  control carrying a declaration the fault turns on. Such a fault names
  fields, but names them on steps this form does not carry, so neither
  of the two cases above reaches it: marking "every field in the
  combination" is unsatisfiable when most of them are on other steps,
  and treating it as page-level would leave an author looking at the
  control that caused it with nothing on it.

  Which controls those are depends on the fault, not on a fixed list, and
  **not on which of them the write happened to change**. A cycle turns on
  dependency declarations alone, so it marks the dependency control. A
  transitive deadlock turns additionally on the step's own gate, its start
  gate and whether it blocks — an author provokes one as readily by ticking
  "blocks its gate" or by moving the step to an earlier gate as by adding an
  edge — so it marks all four.

  Marking every control the fault turns on, rather than only those the write
  changed, is deliberate. A latent deadlock can be brought into effect by a
  write that changes none of the four, and a criterion keyed on what changed
  would then mark nothing — which the scenarios below forbid. It also spares
  the surface from having to know what a stored value was, a question a
  create cannot answer at all.
- A fault about the **step set as a whole, or about a gate** — a
  retirement refused because it would leave a gate unheld included —
  SHALL mark no field and SHALL be rendered at page level, on
  whichever surface renders the rejection. Such a fault does not
  concern anything a specific form field carries.

Where more than one fault concerns the same field, that field SHALL be
marked once and SHALL carry all of them, so that a field is not silently
attributed to only the first rule that named it.

Marking SHALL be observable in the rendered response — the field's own
control carries the fault text it was marked with — rather than
expressed only visually, so that what an admin is told is what a
response can be asked for.

A marked control MAY be one the surface does not offer, and the
combination treatment guarantees it will sometimes be: a `human` step
carrying an automation brief is refused for the pair, and the automation
controls render un-offered on a `human` step. Marking SHALL render the
fault text adjacent to such a control just as it does for any other, and
SHALL NOT change whether the control is offered. Telling an admin which
pair was refused is the point; silently omitting half of it because one
half is currently un-offered would leave the refusal unexplained.

#### Scenario: A fault about one field marks that field

- **WHEN** a write is rejected because a step's name is empty
- **THEN** the re-rendered surface marks the name field with that fault
- **AND** no other field is marked with it

#### Scenario: A fault about a combination marks every field in it

- **WHEN** a write is rejected because a `human` step carries an
  automation brief
- **THEN** the re-rendered surface marks both the kind field and the
  automation brief field with that fault

#### Scenario: A fault about the step set marks no field

- **WHEN** a write is rejected because a gate would be left with no
  active blocking step
- **THEN** the re-rendered surface reports that fault at page level
- **AND** marks no field with it

#### Scenario: A blocked retirement is attributed like any other edit-form rejection

- **WHEN** a retirement submitted through the edit form's `status`
  field is rejected because it would leave a gate unheld
- **THEN** the fault is reported at page level, on the edit form, since
  it concerns the step set rather than a single field
- **AND** the submitted `status` value is still in the form

#### Scenario: A move's rejection still renders at the list, unattributed

- **WHEN** a move is rejected
- **THEN** the fault is reported at page level on the step list
- **AND** no field is marked with it, since the list carries no
  authorable form to mark one on

#### Scenario: Attribution never shortens the fault list

- **WHEN** a write is rejected reporting one fault the surface attributes
  and one it does not
- **THEN** both faults are rendered in the surface's fault list
- **AND** the one it attributes is additionally marked on its field

#### Scenario: A field two faults concern carries both

- **WHEN** a write is rejected by two faults that both concern the kind
  field
- **THEN** the kind field is marked once
- **AND** carries both faults

#### Scenario: An unparseable anchor value marks the input it came from

- **WHEN** a write is rejected because one of the timing anchor's
  numeric inputs cannot be read as a number
- **THEN** the re-rendered surface marks that input with the fault
- **AND** marks neither of the anchor's other numeric inputs

#### Scenario: Both authoring surfaces attribute alike

- **WHEN** an edit and a create are each rejected by a fault about one
  field
- **THEN** each surface marks that field on its own rendering

#### Scenario: A multi-step fault marks the edited step's control

- **WHEN** a write is refused because the step being edited introduces a cycle among dependency declarations
- **THEN** the dependency control on that step's form is marked, and the fault is not rendered at page level

