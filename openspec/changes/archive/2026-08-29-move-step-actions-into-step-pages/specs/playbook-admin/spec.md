## MODIFIED Requirements

### Requirement: A step's actions are presented as one affordance vocabulary

The one action a step's row still offers — reordering — SHALL be presented as a control carrying the same vocabulary this requirement has always used: the marker `row-action`, observable in the rendered response rather than expressed only visually. Editing, changing status, retiring and un-retiring are no longer row actions; they are reached by opening the step's own page through its name, and are governed there by the step form's own requirements, not by this one.

A step's row SHALL occupy one line, as it always has. What changes is only which controls sit in that line: the reorder pair, and nothing pooled beside it by virtue of being a control.

There is no longer a destructive action on the row to distinguish: retiring, the row's one destructive action, moved to the step's edit page along with the rest. A row carries no control marked `danger`.

The markers are a necessary condition, not a sufficient one. That a row occupies one line cannot be established by a server response and SHALL be confirmed by direct inspection of the rendered page.

Nothing in this requirement licenses removing the move controls, changing what a move does, or changing which rows offer one.

#### Scenario: A row's actions share one vocabulary

- **WHEN** an active step's row that can move is rendered
- **THEN** each move control carries `row-action`
- **AND** no action is rendered as an unmarked link among marked controls

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** any step's row is rendered, active or retired
- **THEN** no control on that row carries `danger` — the row's one
  destructive action, retiring, no longer lives on it, so distinguishing
  it here means it is simply not present

#### Scenario: A retired step's only action speaks the same vocabulary

- **WHEN** a retired step's row is rendered from the view that reveals
  retired steps
- **THEN** it carries no control marked `row-action` at all — retired
  steps hold no slot to reorder, and every other action moved to the
  step's edit page, so there is no longer an "only action" for the row
  to offer, only the marker's continued absence

#### Scenario: The vocabulary does not change which actions are offered

- **WHEN** a step that cannot be moved further up is rendered
- **THEN** its move control is still rendered inert, exactly as before
- **AND** carries `row-action` like every other move control

#### Scenario: The row offers no other action

- **WHEN** any step's row is rendered, active or not
- **THEN** no control marked `row-action` on that row changes the step's
  status, edits it, retires it or un-retires it

### Requirement: A step's name in the table opens its edit page

Each step's row SHALL offer that step's edit page in one action through the step's own name, the way a launch's row already offers its detail page through the launch's label and a product's row already offers its dossier through the product's SKU. This is now the row's **only** way into a step: editing, changing status, retiring and un-retiring all happen on the page the name leads to, not on the row itself.

#### Scenario: A step's name opens its edit page

- **WHEN** any step's row is rendered
- **THEN** its name offers that step's edit page in one action

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

Faults concern fields in three ways, and each SHALL be treated
differently:

- A fault about **one field** SHALL mark that field.
- A fault about a **combination of fields** SHALL mark **every** field
  in the combination. Neither value is wrong on its own — an `automated`
  step carrying no automation brief is refused for the pair, and
  changing either the kind or the brief resolves it — so marking one
  would tell the admin to change that one.
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

### Requirement: The narrowed view survives every write and every move between views

Every write made from the page — an edit, a creation, a retirement, an
un-retirement, a reorder — SHALL carry forward the narrowing that was
active when it was made: the gate filter, the discipline filter, the
text search, and whether retired steps are shown. Navigation
between the list and a step's edit form, and between the list and the
create surface, SHALL carry that narrowing too, in both directions, and
so SHALL the control that reveals or hides retired steps.

Where a write re-renders the list, it SHALL render it under that
narrowing. Where a write re-renders some other view — a rejected edit
re-renders the edit form, and a rejected creation re-renders the create
surface, as the editing and creation requirements demand — the narrowing
SHALL be preserved so that the next render of the list applies it. A
write SHALL NOT widen, clear, or otherwise alter what the page shows
beyond the effect of the write itself.

Retiring, un-retiring and changing status are submitted through the
edit form now, not from the list, so a **rejection** of any of them
follows the edit form's own rule above rather than rendering on the
list — the same as a rejected field edit. An **accepted** retirement,
un-retirement or status change still ends on the list, exactly as
before: the write's own route re-renders the list on success regardless
of which form submitted it. Move is the only write left that renders
its rejection on the list itself, since it is the only one the list
still submits directly.

#### Scenario: An accepted write keeps the narrowing

- **WHEN** a step is retired while a gate filter and a discipline filter are active
- **THEN** the re-rendered list still applies both filters
- **AND** shows the same gate and discipline selections as before the write

#### Scenario: A rejected list-level write keeps the narrowing

- **WHEN** a move is rejected while a text search is active — the one
  write left that renders its rejection on the list itself
- **THEN** the re-rendered list reports why the move did not land
- **AND** still applies the search term

#### Scenario: A rejected creation keeps the narrowing without leaving the create surface

- **WHEN** a creation is rejected while a text search is active
- **THEN** the create surface re-renders with its faults and the submitted values, as the creation requirement requires
- **AND** returning to the list from that surface applies the search term

#### Scenario: A rejected edit keeps the narrowing without leaving the form

- **WHEN** an edit is rejected while a gate filter is active
- **THEN** the edit form re-renders with its faults and the submitted values, as the editing requirement requires
- **AND** returning to the list from that form applies the gate filter

#### Scenario: A rejected retirement keeps the narrowing without leaving the edit form

- **WHEN** a retirement submitted through the edit form's `status`
  field is rejected while a gate filter is active
- **THEN** the edit form re-renders with the fault, exactly as any other
  rejected edit does
- **AND** returning to the list from that form applies the gate filter

#### Scenario: Opening and leaving an edit form preserves the narrowing

- **WHEN** a step's edit form is opened from a narrowed list and left without saving
- **THEN** the list re-renders under the same narrowing

#### Scenario: Opening and leaving the create surface preserves the narrowing

- **WHEN** the create surface is opened from a narrowed list and left without creating
- **THEN** the list re-renders under the same narrowing

#### Scenario: Un-retiring keeps the retired steps visible

- **WHEN** a step is un-retired from the view that reveals retired steps
- **THEN** the re-rendered list still reveals retired steps
- **AND** still applies whatever gate and discipline filters were active
