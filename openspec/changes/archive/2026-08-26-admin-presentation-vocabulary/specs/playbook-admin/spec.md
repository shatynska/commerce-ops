## ADDED Requirements

### Requirement: A step's actions are presented as one affordance vocabulary

Every action a step's row offers — reordering, changing status, editing,
retiring, un-retiring — SHALL be presented as a control of the same
weight as its siblings, and a step's row SHALL occupy one line rather
than stacking its controls one per line. Which actions a row offers is
unchanged by this requirement: a step that offers no move today offers
none after it.

Actions that act on the same thing SHALL be grouped with the thing they
act on rather than pooled into one cell by virtue of all being controls.
The reorder pair belongs beside the position it changes; the status
control belongs in the status column. What the requirement forbids is
the vertical stack that cost a step five lines of height, not a layout
that reads by meaning — an admin looking for "where does this sit" and
an admin looking for "retire this" are looking for different things.

The **destructive** action SHALL be distinguished by its own treatment
rather than by being the most prominent control in the row. Retiring a
step is the action an admin is least likely to want by accident, and a
vocabulary in which it is the loudest thing on the row invites exactly
that.

Both the presentation and the destructive distinction SHALL be
observable in the rendered response — each action control carries the
marker `row-action`, and the destructive one carries the further marker
`danger` — rather than being expressed only visually. This is the same
standard the surface already holds for fault marking, and for the same
reason: what an admin is told must be something a response can be asked
for. The literal tokens are given because they are what a test is
derived from, as this capability already does for its fault-rewriting
rule.

The markers are a necessary condition, not a sufficient one. They
establish that the vocabulary was applied; they cannot establish that a
row occupies one line or that the destructive action is not the most
prominent, which no server response can show. Those SHALL be confirmed
by direct inspection of the rendered page.

Nothing in this requirement licenses removing an action, changing what
an action does, or changing which actions a row offers for a given step.

#### Scenario: A row's actions share one vocabulary

- **WHEN** an active step's row is rendered with its full set of actions
- **THEN** every action control carries `row-action`
- **AND** no action is rendered as an unmarked link among marked controls

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** an active step's row is rendered
- **THEN** the retire control carries `danger`
- **AND** no other action control on that row carries it

#### Scenario: A retired step's only action speaks the same vocabulary

- **WHEN** a retired step's row is rendered from the view that reveals
  retired steps
- **THEN** its un-retire control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: The vocabulary does not change which actions are offered

- **WHEN** a step that cannot be moved further up is rendered
- **THEN** its move control is still rendered inert, exactly as before
- **AND** carries `row-action` like every other action

### Requirement: The vocabulary never suppresses a marked control's fault

`playbook-admin` already requires a fault to be rendered adjacent to a
marked control whether or not that control is offered, and requires
marking never to change whether it is offered. Those marks currently
ship with no presentation treatment at all. This requirement binds the
treatment they are about to receive: **the vocabulary SHALL NOT suppress
a fault the surface marked.**

The case this actually concerns is the automation controls. A `human`
step carrying an automation brief is refused for the pair, marking both
the kind and the brief, and the brief renders disabled among controls a
step of that kind cannot use. Any treatment that sets those controls
apart is presentation; hiding them would remove a fault the surface is
required to render, turning a styling decision into a silent breach of
an existing guarantee.

So the obligation is negative and specific: no rule in the vocabulary
SHALL render a marked control's fault, or a container holding one, as
not displayed **or as less legible than the surface's ordinary text**.
A disabled control stays disabled, and the fault marked on it stays as
readable as any other.

Both halves are stated because the second is the one a treatment reaches
by accident. The mark renders *inside* the marked control's label, so
the natural way to set a region apart — reducing its opacity — applies
to descendants and takes the fault down with the controls; opacity also
establishes a stacking context, so restoring it on the mark alone does
not work. Setting apart a control an admin cannot use is legitimate;
dimming the sentence explaining why their write was refused defeats the
guarantee it exists to serve. The legibility half cannot be read from a
response and is confirmed by inspection.

This requirement binds whatever treatment the surface carries, including
none. The vocabulary as built gives those controls no treatment of its
own — every version tried read as a region demanding attention rather
than one that can be ignored, which is the opposite of what it means —
so the controls render as ordinary fields and the browser's own
rendering of a disabled control is what says they are not offered. That
makes this requirement trivially satisfied rather than carefully
satisfied, and it stays stated for exactly that reason: it is the
constraint on the treatment somebody adds next.

#### Scenario: A fault on a disabled automation control is not suppressed

- **WHEN** a `human` step carrying an automation brief is rejected for
  the pair
- **THEN** the mark carrying that fault is rendered
- **AND** the automation brief control is still disabled
- **AND** neither that mark, nor the fieldset holding it, is rendered as
  not displayed

### Requirement: A created step is distinguished on the row the list lands on

The step list already addresses a just-created step directly, so that a
browser brings it into view. Where the list is rendered naming a created
step that it actually renders, that step's row SHALL additionally be
distinguished from every other row, and the distinction SHALL be carried
in the response — the marker `just-created` on that row — rather than
depending on scripting.

Addressing without distinguishing lands the admin somewhere in a table
of 105 rows with nothing saying which row was the point. The two are one
guarantee: find it, then see it.

The distinction SHALL follow the addressing exactly, and SHALL never
outrun it. Where the list renders without naming a created step, or
names one it does not render — a step the narrowing hides, or one
retired since it was created, both of which the list already handles by
rendering as though unnamed — no row SHALL be distinguished. A row
highlighted on a page that is not the result of a create would be a
claim about a step nobody just created.

#### Scenario: The created step's row is distinguished

- **WHEN** a create lands and the list is rendered naming the created
  step, with no narrowing hiding it
- **THEN** that step's row carries `just-created`
- **AND** no other row carries it

#### Scenario: A step created as a draft is distinguished where it renders

- **WHEN** a step is created as a `draft` and the list is rendered
  naming it, with no narrowing hiding it
- **THEN** its row among the non-active steps carries `just-created`
- **AND** no row among the served steps carries it

#### Scenario: A list not naming a created step distinguishes nothing

- **WHEN** the list is rendered without naming a created step
- **THEN** no row carries `just-created`

#### Scenario: A named step the list does not render distinguishes nothing

- **WHEN** the list is rendered naming a created step that its own read
  does not return
- **THEN** the list renders as it would without that name
- **AND** no row carries `just-created`

### Requirement: The page carries a header from which the other admin surface is reachable

Every page this capability serves — the step list, the edit surface and
the create surface — SHALL carry a header naming the admin surfaces the
session can reach, and from it the roster page SHALL be reachable in one
action.

The header exists because the surfaces are otherwise unconnected. The
admin session lands on this page and nothing on it, or on any page
reachable from it, mentions that a roster page exists. An admin who does
not already know the URL cannot get there, and the roster is where
people — including the assignees this page's own form offers — are
added and deactivated.

The header SHALL identify which surface is currently being viewed, so it
reads as a position rather than as an undifferentiated pair of links.
The create and edit surfaces are not themselves named in the header;
each SHALL identify the playbook surface as current, since that is the
surface an admin is within while authoring a step.

Reachability SHALL NOT depend on scripting, and SHALL NOT depend on the
step set: the header renders the same whether the set holds one step or
every one, and whatever narrowing is active. This is the guarantee the
create control already carries on this page, for the same reason — a
control that is only reachable after scrolling past 105 steps is one an
admin concludes does not exist.

Travelling to the roster page SHALL NOT be treated as a write and SHALL
carry nothing forward: the roster page has no narrowing of its own, and
the narrowing requirement governs movement between this capability's own
views, not departure from them.

One consequence is accepted rather than repaired, and is stated because
it is invited by this requirement's own rationale. The roster is where
assignees are added, so an admin part-way through a create who finds an
assignee missing is exactly the person the header serves — and departing
from a filled authoring surface **discards what was typed**. The
surrounding spec works hard to keep a rejected create's values,
including each named assignee, but that guarantee is about a rejection,
not about a deliberate departure. The header SHALL therefore be no
harder to leave from than any other link, and recovery is the browser's
back-navigation. A confirmation prompt was considered and refused: it
would make the common case — travelling from an untouched list — worse
in order to protect the rare one, and this capability nowhere else
guards a navigation.

#### Scenario: Departing from the create surface carries nothing forward

- **WHEN** the header's roster link is taken from the create surface
- **THEN** the roster page is served
- **AND** nothing the create surface held is persisted

#### Scenario: The roster page is reachable from the step list

- **WHEN** the step list is rendered
- **THEN** its header offers the roster page in one action
- **AND** identifies the step list as the surface currently viewed

#### Scenario: The header does not depend on how many steps are shown

- **WHEN** the step list is rendered under a narrowing that matches no
  step at all
- **THEN** the header is still rendered and still offers the roster page

#### Scenario: The authoring surfaces carry the header too

- **WHEN** the create surface and a step's edit surface are each
  rendered
- **THEN** each carries the header offering the roster page
- **AND** each identifies the playbook surface as the one currently
  viewed

### Requirement: The presentation assets stay behind the admin guard and need no build step

The stylesheet the admin surfaces load SHALL be served only to a caller
holding a valid admin session, and a caller without one SHALL be refused
in the same shape as any other unauthorised admin path — the app's own
404, identical to an unregistered route, revealing nothing about what
exists. The vendored assets the playbook page already loads keep this
guarantee unchanged.

The stylesheet SHALL be served as it is committed to the repository,
with no build, compile, bundle or transform step between the source and
what is served. What a reviewer reads in the diff is what a browser
receives.

This is a constraint on the whole vocabulary, not on one file. Adopting
a mechanism that needs a build step — a preprocessor, a bundler, a
subsetting pass over binary assets — would break it however small the
step was, which is why the type layer uses system fonts and this change
commits nothing binary.

#### Scenario: The stylesheet is refused without an admin session

- **WHEN** the stylesheet is requested with no admin session cookie
- **THEN** the response is the same 404 an unregistered route returns
- **AND** carries no stylesheet content

#### Scenario: The stylesheet is served to an admin

- **WHEN** the stylesheet is requested with a valid admin session
- **THEN** it is served
- **AND** its bytes are those of the file committed to the repository

#### Scenario: No build artifact stands between source and response

- **WHEN** the repository is checked out and the application is started
  with no build or asset step run
- **THEN** the admin surfaces load their stylesheet successfully
