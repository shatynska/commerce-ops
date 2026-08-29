## MODIFIED Requirements

### Requirement: The step form carries every authorable field

The step form SHALL offer every field the authoring capability accepts: the name, the description, the assignees, the kind, whether the result needs confirmation, the status, the hazard, the gate it starts at, the steps it waits on, and — for an `automated` step — the automation brief and the handler, alongside the gate, scope, timing anchor and blocking flag it already carries.

The name and the description SHALL be distinct inputs, and the description's input SHALL accept more than one line: a single-line box for a field whose whole purpose is to be longer than the name would teach the author the opposite of what the two fields are for.

Assignees SHALL be chosen from the roster's active people rather than typed, so an author cannot name a person who does not exist and cannot mistype an identifier. The people offered SHALL be identified by their display names, since an author knows colleagues by name and not by generated identifier.

**Every control admitting more than one value SHALL be choosable and clearable without a modifier key.** A control that deselects only on ctrl/cmd-click has no plain-click route back to none, which for a field whose ordinary value *is* none — the steps a step waits on — leaves an author who chose by accident unable to undo it.

**What is currently chosen SHALL be rendered apart from the options**, in a region carrying the marker `chosen-set` and naming the field it belongs to, since the form carries two such regions and a marker that cannot tell them apart is one a reader must fall back to structure to use. Each value SHALL be clearable from that region as well as from the options, **and that clearing SHALL NOT depend on the options being enhanced**: a value an author can see but not act on where they see it sends them back to search the options for it, which is the whole of what the region exists to spare them.

**A value SHALL NOT be shown in `chosen-set` while its own control is unchosen**, whether or not the enhancement is running. This does not follow from the rule above and is the harder half of it: an affordance that acts on the option's own control is a *toggle*, so a rendering that did not follow the control would leave a cleared value still shown, and a second click on it would silently choose the value again — the author's clearing undone by the action they took to confirm it. The control remains the authority on what is chosen and what is submitted, and this rendering is a view of it, never a second copy of the answer.

**What a response can be asked of these two controls, and what it cannot.** That each control renders a control per value, that a region marked `chosen-set` names its field, that a chip element exists for each chosen value, that the served stylesheet carries a rule keyed on a control's checked state reaching that region, and that a fault mark renders outside anything the options are scrolled within — all observable in the rendered response. That each control's values can be chosen and cleared without a modifier key, that clearing from `chosen-set` actually clears, that a cleared value actually stops being shown, and that no filtering removes a mark — these are behaviours and computed style, cannot be established by a server response, and SHALL be confirmed by direct inspection of the rendered page.

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

#### Scenario: A cleared value is not left shown as chosen

- **WHEN** an author clears a value from `chosen-set`, with the options unenhanced
- **THEN** that value is no longer shown as chosen, so that acting on it again cannot restore it unremarked

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

## ADDED Requirements

### Requirement: The dependency control's options can be filtered

The control for the steps a step waits on ranges over every `active` step — dozens of them, two thirds on one gate — and grouping alone does not make that navigable: a group of sixty is not navigable for being labelled. The control SHALL therefore offer **filtering its options**: by gate, through controls carrying the marker `option-gate-filter`, and by text through one carrying `option-filter`, the text matching a step's identifier, its name **and** its gate. Two mechanisms because they fail differently — choosing a gate is one gesture and no typing, while text finds a step whose gate the author does not remember — and the two SHALL compose rather than replace one another.

This filtering belongs to the option control alone, which is what its markers say. It is neither the page *narrowing* this capability requires elsewhere nor the step list's own gate and discipline *filters*: it is local to one control on one unsaved form, it SHALL be carried on no link and reach no submission, and it SHALL NOT survive the write.

**Filtering SHALL change only which options are shown.** It SHALL NOT change which are chosen, and every chosen value SHALL be submitted whether or not the filtering in force shows it.

Where filtering hides a chosen option the surface SHALL say so. The region it says it in SHALL carry the marker `hidden-chosen-notice`, which names that region's **role** and is therefore present whether or not anything is hidden; the marker `hidden-chosen` SHALL appear only once a chosen option actually is hidden, and SHALL name how many are. This is the distinction this capability already draws for `write-failure-notice` against `write-failed`: a marker asserting an occurrence must never outrun the occurrence — and no server response can carry the occurrence at all, since filtering never survives a render. An author who has hidden a chosen row is looking at a control that appears to hold less than it will submit, and left unsaid that reads as a value stuck beyond their reach.

The gate filtering SHALL state **how many of the offered options each gate holds** — the options as offered, which excludes every step that is not `active` and, where the form is editing a step, that step. The set is heavily uneven, and that is the fact which makes the control feel unusable when it is discovered by scrolling. Stated up front it is a reason to filter; discovered by scrolling it is only an obstacle. The counts state what the control offers and SHALL NOT track the text filtering, which changes what is shown moment to moment and would make them unreadable.

Gates later than **the gate the form was rendered with** SHALL be marked wherever they are offered, in the filtering as well as in the list, and the form SHALL NOT withhold them — which constrains what the *form* offers and says nothing about what an author's own filtering may hide. That gate is the step's own where a step is being edited, the gate the submission carried where a rejected write is being re-rendered, and the gate the create surface was rendered holding otherwise. It is what the form was rendered with and not what its gate control presently holds: the marks are rendered once, with the form, and an author who changes the gate without submitting is reading marks for the gate they arrived with until the form is rendered again.

Where the gate the form was rendered with names no gate of the sequence — which a re-rendered submission can carry — no gate SHALL be marked as later, there being nothing to be later than.

The mark is by gate and is deliberately coarse. A step's start gate is never later than its own gate, so marking by gate cannot miss a dependency that would be refused; it can include one that would not, since a step at a later gate may start immediately. It says where a refusable dependency can live, and asserts nothing about any particular option.

Neither the filtering controls nor the gate marks SHALL be worded so that they read as the step's own gate. This control now renders a row of gate names beside the control that does carry that gate, and the two must stay distinguishable.

Where the filtering in force matches no option the control SHALL say so plainly, rather than showing an empty list — an empty box reads as a failure to load, and an author cannot tell one from a filter that happens to match nothing.

Filtering MAY be unavailable, and SHALL then degrade to the complete grouped list rather than to an empty or partial one, so that nothing is unreachable and only the convenience is lost.

**What a response can be asked, and what it cannot.** That the controls are present and marked, that each gate states its count, that every option carries its gate, that later gates are marked and offered, that no link carries the filtering and no filtering state reaches the submission, that every option is present and grouped, that neither the filtering controls nor the gate marks are worded as the step's own gate, that a statement is rendered for the no-match case, and that the region for the hidden-chosen report exists are all observable in the rendered response. That the filtering *narrows* what is shown, that the two mechanisms compose, that a chosen option hidden by filtering is still submitted, and that the report appears when one is — these are behaviours of the enhancement, cannot be established by a server response, and SHALL be confirmed by direct inspection of the rendered page, as this capability already requires for what a row's single line cannot be asked of a response.

#### Scenario: The control offers both ways of filtering

- **WHEN** the control for the steps a step waits on is opened
- **THEN** controls marked `option-gate-filter` offer each gate, and one marked `option-filter` accepts text

#### Scenario: Each gate states how many options it offers

- **WHEN** that control is opened while a step is being edited
- **THEN** each `option-gate-filter` states how many of the offered options its gate holds
- **AND** the count for the edited step's own gate excludes that step

#### Scenario: The region for the hidden-chosen report exists before anything is hidden

- **WHEN** the form is rendered
- **THEN** it carries a region marked `hidden-chosen-notice`, so a response can be asked whether there is somewhere for the report to appear
- **AND** that region carries `hidden-chosen` only once a chosen option is actually hidden

#### Scenario: Every option carries the gate its text filtering matches on

- **WHEN** the form is rendered
- **THEN** each option carries its step's gate, so that text matching a gate's name can match it

#### Scenario: A later gate is marked against the gate the form was rendered with

- **WHEN** the form is rendered carrying the gate `listable`
- **THEN** the gates after `listable` are offered, and are marked as later, in the filtering and in the list

#### Scenario: A create surface marks against the gate it was rendered holding

- **WHEN** the create surface is rendered holding a gate
- **THEN** the later-gate marks are computed against that gate, and not against a step, there being none

#### Scenario: The filtering reaches no link and no submission

- **WHEN** the form is rendered and submitted
- **THEN** no link on it carries the filtering, and the submission carries no filtering state

#### Scenario: The control is complete without filtering

- **WHEN** the form is rendered where the filtering cannot run
- **THEN** every option is present, grouped by gate, and what is stored as chosen is shown as chosen

#### Scenario: Filtering narrows what is shown and never what is chosen

- **WHEN** an author chooses a step, then filters so that step's option is hidden, and submits
- **THEN** the chosen step is submitted
- **AND** while it is hidden the region marked `hidden-chosen-notice` carries `hidden-chosen` and names how many are hidden
- **AND** this is confirmed by direct inspection of the rendered page, no response being able to establish it

#### Scenario: Gate filtering and text filtering compose

- **WHEN** an author filters to one gate and then enters text
- **THEN** only the options matching both are shown, confirmed by direct inspection of the rendered page

