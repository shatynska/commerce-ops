## ADDED Requirements

### Requirement: A rejected write names the fields its faults concern

A surface **carrying the authorable form** — the edit form and the
create surface — SHALL name, for each fault it reports, the form fields
that fault concerns, so that an admin reads which controls to touch
rather than translating prose back into inputs.

This requirement binds those two surfaces only. The step list also
renders rejections — of a retirement, an un-retirement, a status change
or a move — and carries no authorable form for a fault to be attributed
against; those rejections SHALL keep rendering at page level exactly as
they do.

Attribution SHALL be **additional to** the fault list, never a filter:
every fault the write reported SHALL still be rendered in full, in the
surface's own fault list, whether or not it was attributed. A fault the
surface cannot attribute SHALL be rendered at page level, exactly as it
would have been without this requirement — an unrecognised fault
degrades, it does not disappear.

Faults concern fields in three ways, and each SHALL be treated
differently:

- A fault about **one field** SHALL mark that field.
- A fault about a **combination of fields** SHALL mark **every** field
  in the combination. Neither value is wrong on its own — an `automated`
  step carrying no automation brief is refused for the pair, and
  changing either the kind or the brief resolves it — so marking one
  would tell the admin to change that one.
- A fault about the **step set as a whole, or about a gate**, SHALL mark
  no field and SHALL be rendered at page level. Such a fault does not
  concern anything the form in front of the admin carries.

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

#### Scenario: No rule an authoring write can provoke is unattributed by accident

- **WHEN** every rule an edit or a create can provoke is provoked in
  turn
- **THEN** each resulting fault is either attributed to the fields it
  concerns, or concerns no control the authorable form carries
- **AND** no fault falls through unrecognised

## MODIFIED Requirements

### Requirement: A step can be edited in place

The page SHALL let a step's authorable fields be edited inline and saved through the authoring update write. A saved edit SHALL re-render the step with its new values. A rejected write SHALL re-render the form still holding the submitted values, carrying **every** fault the write's validation reported. A write rejected because the step set changed underneath the form SHALL persist nothing and SHALL say so, so the admin re-reads before retrying.

"Every fault" SHALL hold across **all the values the surface itself
parses before the write**, not merely within one kind of them. Where a
submission carries both an unrecognised value in one control and an
unparseable one in another, the rejection SHALL report both, rather than
stopping at whichever was read first. A rejection an admin has to
correct one fault at a time is the failure this guarantee exists to
prevent.

The scope is stated precisely because it cannot honestly be wider. The
surface parses submitted values before calling the write at all, so a
submission the surface refuses never reaches the coherence rules and
their faults are never computed. What this guarantees is that the
surface reports everything **it** found, not that a rejection unites
faults the write never produced.

#### Scenario: A clean edit lands

- **WHEN** an edit with valid values is saved
- **THEN** the step re-renders with the new values

#### Scenario: A rejected edit shows every fault

- **WHEN** a submitted edit violates two coherence rules at once
- **THEN** the re-rendered form reports both faults
- **AND** the submitted values are still in the form
- **AND** the served step set is unchanged

#### Scenario: Faults from different sources arrive together

- **WHEN** a submitted write carries both an unrecognised value in a
  field the surface parses and an unparseable timing anchor
- **THEN** the rejection reports both faults
- **AND** neither source's faults are dropped in favour of the other's

#### Scenario: A create wrong in a field and in its discipline reports both

- **WHEN** a create carries both an unrecognised value in a field the
  surface parses and an unrecognised discipline
- **THEN** the rejection reports both faults
- **AND** each marks its own control

#### Scenario: A stale edit is surfaced, not silently dropped

- **WHEN** an edit is submitted after another write has changed the step set
- **THEN** nothing is persisted and the page states the set changed underneath the edit

### Requirement: Steps can be created, retired and un-retired from the page

The admin surface SHALL offer creating a step with the full authorable
shape — the identifier is generated, never asked for — and retiring or
un-retiring a step. Each flow SHALL go through the corresponding
authoring write, and a rejection SHALL render its full fault list the
same way a rejected edit does.

Creating SHALL live on its own surface rather than within the step
list, and SHALL be reachable from the list without traversing the step
set, so that reaching it does not depend on how many steps are shown.

A create rejected by validation SHALL re-render the create surface
still holding **every** submitted value, carrying every fault the write
reported. Every value means every one: the fields the surface shares
with editing, the timing anchor's inputs, the discipline — which only
the create surface offers, since a step's discipline cannot be updated —
and **each** person named as an assignee, not merely one of them. A
create rejected because the step set changed underneath it SHALL persist
nothing, say so, and likewise keep what was typed. This is the guarantee
a rejected edit already carries; a create surface that loses a set of
named people on a rejection is worse than one that loses a line of text,
because retyping it means remembering who was on it.

A fault a rejected create reports about **the step being created** SHALL
NOT identify that step by the identifier the write would have generated.
No such step exists — the identifier is generated before validation and
nothing was persisted — so naming it sends the admin looking for a step
that is not there.

The rewriting SHALL be exactly this and no more: the leading
`step '<identifier>' ` — the words every step-level fault opens with —
is removed, and the remainder of the fault is rendered exactly as the
write reported it. No fault text is composed by the surface. The literal
form is given because it is the delta a test is derived from, and an
intent is not assertable.

A consequence, accepted rather than repaired: what remains reads as a
predicate without a subject — *"is automated and beyond draft but
carries no automation brief"*. Repairing it inside the fault would mean
composing text, which the sentence above forbids. Where the rendering
needs a subject, it belongs to the surface around the list rather than
to the fault.

Faults about the step set, which may legitimately name steps that do
exist, SHALL keep the identifiers they carry. So SHALL a fault the
surface does not recognise: unrecognised is unclassified, and a surface
that guessed would strip identifiers from faults naming steps the admin
would need to go and look at.

The create surface SHALL require a discipline, and a create submitted
without one SHALL be refused rather than assigned a default. A step's
discipline is carried in the identifier the write generates and cannot
be updated afterwards, so a default chosen on the admin's behalf is a
choice they cannot reverse. The surface offers a discipline selector,
which always submits one of its options; refusing is therefore an answer
only a request built by hand can provoke, and a refusal is a better
answer to it than a silent default.

Leaving the create surface without creating SHALL return to the step
list narrowed as it was when the create surface was opened. A create
that lands SHALL likewise return to the step list under that same
narrowing, and the list SHALL identify which step was just created —
addressing it directly, so that a browser can bring it into view.

Where the created step renders depends on the status it was created
with, and the list SHALL address it wherever that is: a step created
`active` among its gate's active steps, and a step created `draft` or
`in-development` among the non-active steps set apart from the served
set, holding no position in its gate's order. Addressing SHALL NOT
assume the created step joined the served order, since a step written
down before it is ready is the case the draft status exists to serve.

The create surface SHALL NOT offer `retired` among the statuses a step
can be created with, and a create submitting `retired` SHALL be refused
rather than persisted. Retirement is the end of a step's life and is
reached through the retire flow, which records who ended it; a step
created straight into it would render behind the control that reveals
retired steps, where the list could not address it and the notice below
could not help. Leaving this to the rendered control alone would rest
the rule on markup — which this capability already declines to do for
reordering, refusing a move submitted where reordering is unavailable
rather than trusting the absent control.

These two refusals — a create naming no discipline, and a create naming
`retired` — answer requests the create surface cannot have produced,
since its own controls always submit a discipline and never offer
`retired`. They SHALL be refused without rendering a create surface, and
are therefore not "rejected by validation" in the sense used above: there
is no admin mid-edit whose typed values must survive, and rendering a
form in answer to a request no form made would invent a session that
does not exist.

Where the active narrowing would hide the created step, the list SHALL
render under that narrowing and SHALL state that the created step falls
outside it, naming it and offering to clear the narrowing. That offer
SHALL keep addressing the created step, so that clearing the narrowing
brings it into view rather than landing at the top of the whole set. A
create SHALL NOT appear to have been lost.

The notice SHALL be rendered only where clearing the narrowing it offers
to clear would reveal the named step. Where the named step is not among
the steps the page's own read returns, or where clearing that narrowing
would not reveal it — a step retired since it was created, say — the
list SHALL render as it would without the name. An offer the admin
cannot act on is worse than saying nothing.

"The steps the page's read returns" is deliberately not "the served
set". The served set is the `active` steps a launch is held to, and a
step created as a `draft` is by definition outside it while being
exactly the step this notice exists to find. The test is what the page
would render once the narrowing is cleared, not what a launch is held
to.

#### Scenario: Creating is reachable regardless of how large the set is

- **WHEN** the admin page is opened with the full step set rendered
- **THEN** a control opening the create surface is rendered ahead of the
  gate tables
- **AND** no create form is rendered within or after the gate tables

#### Scenario: A created step appears in its gate

- **WHEN** a step is created from the create surface as `active` with
  valid fields, with no narrowing active
- **THEN** the step list is shown again with the created step rendered
  as the last step of its gate's active steps, carrying its generated
  identifier
- **AND** the list addresses that step directly, so a browser lands on
  it rather than at the top

#### Scenario: A step created as a draft is addressed where it renders

- **WHEN** a step is created from the create surface as a `draft`, with
  no narrowing active
- **THEN** the step list is shown again with the created step rendered
  among the non-active steps, set apart from the served set and holding
  no position in its gate's order
- **AND** the list addresses that step directly

#### Scenario: A created step the narrowing keeps visible is still identified

- **WHEN** a step is created under a narrowing the created step matches
- **THEN** the step list is shown under that narrowing with the created
  step rendered
- **AND** the list addresses that step directly

#### Scenario: A create the narrowing would hide is not left looking lost

- **WHEN** a step is created while a search is active that matches
  neither the created step's name nor its description
- **THEN** the step list is shown under that search
- **AND** names the created step and states that it falls outside the
  active narrowing, offering to clear the narrowing
- **AND** taking that offer shows the list with the narrowing cleared,
  still addressing the created step rather than the top of the set

#### Scenario: A step named as created but not there is ignored

- **WHEN** the list is requested naming a created step that the page's
  read does not return at all
- **THEN** the list renders as it would without that name
- **AND** states nothing about a step falling outside the narrowing

#### Scenario: A draft the narrowing would hide is named like any other step

- **WHEN** a step is created as a `draft` while a gate filter is active
  that its gate does not match
- **THEN** the step list is shown under that filter
- **AND** names the created step and offers to clear the filter, exactly
  as it would for a step created `active`

#### Scenario: A named step the offer could not reveal is ignored

- **WHEN** the list is requested naming a created step that has since
  been retired, from a view that does not reveal retired steps
- **THEN** the list renders as it would without that name
- **AND** does not offer to clear a narrowing that would not reveal it

#### Scenario: A rejected create keeps every submitted value

- **WHEN** a submitted create is rejected by validation
- **THEN** the re-rendered create surface reports every fault the write
  reported
- **AND** every submitted value, the timing anchor's included, is still
  in the form
- **AND** the served step set is unchanged

#### Scenario: A rejected create keeps every assignee that was named

- **WHEN** a create naming two assignees is rejected by validation
- **THEN** the re-rendered create surface still shows both of them named
- **AND** neither is dropped nor replaced by the other

#### Scenario: A rejected create keeps the submitted discipline

- **WHEN** a create submitting a discipline other than the first offered
  is rejected by validation
- **THEN** the re-rendered create surface still shows the submitted
  discipline selected
- **AND** a corrected resubmission generates an identifier carrying that
  discipline

#### Scenario: A rejected create does not name the step it did not persist

- **WHEN** a create is rejected by a fault about the step being created
- **THEN** the reported fault does not identify that step by a generated
  identifier
- **AND** no step carrying that identifier is in the served set

#### Scenario: A create naming no discipline is refused, not defaulted

- **WHEN** a create is submitted carrying no discipline at all
- **THEN** it is refused without a create surface being rendered, and
  nothing is persisted
- **AND** no step is created carrying a discipline the submission did
  not name

#### Scenario: A create naming a retired status is refused

- **WHEN** a create is submitted naming `retired` as the status
- **THEN** it is refused without a create surface being rendered, and
  nothing is persisted
- **AND** the create surface offers no such status to begin with

#### Scenario: A stale create is surfaced, not silently dropped

- **WHEN** a create is submitted after another write has changed the
  step set
- **THEN** nothing is persisted and the surface states the set changed
  underneath the create
- **AND** the submitted values are still in the form

#### Scenario: A blocked retirement explains itself

- **WHEN** retiring a step is rejected because its gate would be left
  with no blocking step
- **THEN** the page renders the fault naming that gate and the step is
  not retired
