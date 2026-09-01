## MODIFIED Requirements

### Requirement: The step form carries every authorable field

The step form SHALL offer every field the authoring capability accepts: the name, the description, the assignees, the kind, whether the result needs confirmation, the status, the hazard, the gate it starts at, the steps it waits on, the metric identifier, and — for an `automated` step — the automation brief and the handler, alongside the gate, scope, timing anchor and blocking flag it already carries.

The metric identifier's input SHALL accept any value the shared vocabulary accepts and SHALL NOT constrain the author to a list: nothing defines metrics, so a control offering choices would have none to offer. It SHALL be clearable, absent being the value almost every step carries.

The name and the description SHALL be distinct inputs, and the description's input SHALL accept more than one line: a single-line box for a field whose whole purpose is to be longer than the name would teach the author the opposite of what the two fields are for.

Assignees SHALL be chosen from the roster's active people rather than typed, so an author cannot name a person who does not exist and cannot mistype an identifier. The people offered SHALL be identified by their display names, since an author knows colleagues by name and not by generated identifier.

**Every control admitting more than one value SHALL be choosable and clearable without a modifier key.** A control that deselects only on ctrl/cmd-click has no plain-click route back to none, which for a field whose ordinary value *is* none — the steps a step waits on — leaves an author who chose by accident unable to undo it.

**What is currently chosen SHALL be rendered apart from the options**, in a region carrying the marker `chosen-set` and naming the field it belongs to, since the form carries two such regions and a marker that cannot tell them apart is one a reader must fall back to structure to use. **Each value's own control SHALL be rendered among the options**, where it is what chooses and unchooses — so clearing needs nothing to run and no modifier key, and an author reads the list as a set of things to tick. `chosen-set` MAY additionally offer a way to clear a value where it is shown, and that MAY depend on the options being enhanced, since the option's own control is always there.

**What `chosen-set` offers SHALL NOT be a second control over a value.** It renders what is chosen and it may offer to clear one, but it SHALL NOT be an affordance that also *chooses* — anything bound to the option's own control is a toggle, and a toggle here would let a second action silently re-choose a value the author had just cleared, their clearing undone by the act of confirming it. The option's control remains the authority on what is chosen and what is submitted, and this region is a view of it, never a second copy of the answer.

Where nothing is chosen the region SHALL say so rather than render empty. A blank line is indistinguishable from a region that has failed to draw, and it moves the page under the author's hands as the first value is chosen.

**What a response can be asked of these two controls, and what it cannot.** That each control renders a control per value **among its options**, that a region marked `chosen-set` names its field, that an element naming each chosen value appears there, that the region says so when nothing is chosen, and that a fault mark renders outside anything the options are scrolled within — all observable in the rendered response. That each control's values can be chosen and cleared without a modifier key, that clearing a value stops it being shown, and that no filtering removes a mark — these are behaviours and computed style, cannot be established by a server response, and SHALL be confirmed by direct inspection of the rendered page.

**An emptied multi-valued control SHALL still submit its key**, present and empty, rather than omitting it. A control whose values are individually submitted sends nothing at all when none is chosen, so without this a cleared field is indistinguishable from one never rendered — and a write rejected for an unrelated fault would re-render from the submission and restore what the author had just cleared, which the requirement that a rejected form still hold what was submitted forbids. A submission that carries no such key SHALL nonetheless be read as the empty set, by every reader of it, so that a submission reaching the surface any other way cannot mean something else.

A fault marking either control SHALL attach to the control as a whole and SHALL render where nothing the author has done to the options can hide it — unaffected by any filtering of the options, and outside anything they are scrolled within. A mark an author must scroll or un-filter to discover is one the surface has failed to make. This and the scoping clause below sit under this heading because both are about *rendering this form's controls* — where a mark on one lands, and what styles them and everything the dependency control renders around them, its filtering included. One stylesheet and one change, so splitting the scoping across two requirements would leave a rule governed by whichever heading it happened to be written under.

**No rule introduced for either of these controls, or for the filtering of the dependency control's options, SHALL render on an element another admin surface renders** — save for a rule whose declarations are custom properties only, which changes nothing on a surface that never reads them. None SHALL select `gate` or `empty` unqualified — both are class names another admin surface already renders. One stylesheet serves every admin surface and `gate` is already a class name several of them use, so this is arranged rather than left to be caught by inspection.

Stated over what a rule *renders* and not over what it matches, which is the distinction `launch-admin` draws for its own selectors — and stated here rather than inherited, because that requirement binds the selectors *that* change added and reaches nothing this one introduces. It covers the filtering's selectors as well as these two controls', which is where the collision hazard actually sits: `option-gate-filter` renders a row of gate names, and `gate` is the name a launch surface already uses.

Fields that carry no meaning for the step's current kind — an automation brief on a `human` step — SHALL either be hidden or render disabled, so the form does not invite a value the write would refuse.

The start-gate control SHALL offer the framework's gates other than the final one, which is refused as a start gate, and an explicit "starts immediately" choice — that being a meaningful authored value rather than an empty field, and the two being indistinguishable in a control that offered only gates.

The control for the steps a step waits on SHALL admit more than one step, and SHALL offer **the `active` steps only**, excluding the step being edited. Both exclusions are the same rule this requirement already states for a field that carries no meaning: the write refuses a dependency on a step that is not `active`, and refuses a self-reference as the cycle it is, so offering either invites a value the write would reject. Restricting the options also keeps the served and unserved steps apart in the way the step table is separately required to.

It SHALL present those steps grouped by the gate they belong to, and SHALL identify each option by both its identifier and its name. Where assignees are a handful of colleagues an author knows by name, this control ranges over the served step set — steps in the dozens — and a flat list identified one way is not a set a person can choose from.

Grouping alone does not make that set navigable, and what else the control offers is the subject of its own requirement below.

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

#### Scenario: A multi-valued control clears without a modifier key

- **WHEN** an author clears every value from the assignee control, and from the control for the steps a step waits on
- **THEN** each clears without a modifier key held, and the form submits the empty set for it

#### Scenario: What is chosen is rendered apart from the options and names its field

- **WHEN** a step waiting on two other steps is opened for editing
- **THEN** each control's chosen values are in a region marked `chosen-set` that names the field it belongs to

#### Scenario: Every value has its own control among the options

- **WHEN** either control is rendered
- **THEN** each value it offers has its own control in the list of options, so that choosing and clearing need nothing to run

#### Scenario: An empty set says so

- **WHEN** a control is rendered with nothing chosen
- **THEN** its `chosen-set` region says so rather than rendering empty

#### Scenario: An emptied control still submits its key

- **WHEN** an author clears every value from a multi-valued control and submits
- **THEN** the submission carries that field, present and empty

#### Scenario: A cleared control stays cleared when the write is rejected

- **WHEN** an author clears every value from a multi-valued control and the write is rejected for a fault concerning some other field
- **THEN** the re-rendered form holds that control cleared, and not what was stored before

#### Scenario: A submission omitting the key means the empty set

- **WHEN** a submission carries no key for a multi-valued control
- **THEN** it is read as the empty set for that field, not as a field left unsubmitted

#### Scenario: A fault mark cannot be hidden by what the author did to the options

- **WHEN** a write is rejected for a fault concerning one of these two controls
- **THEN** the mark renders outside anything the options are scrolled within, and no filtering of the options removes it

#### Scenario: The form offers the metric identifier

- **WHEN** the step form is rendered
- **THEN** it offers an input for the metric identifier, free-typed rather than chosen from a list, and clearable

