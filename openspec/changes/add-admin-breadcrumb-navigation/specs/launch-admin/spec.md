## MODIFIED Requirements

### Requirement: A launch's detail page offers the way back to the list

The detail page SHALL carry a breadcrumb trail immediately above its title, naming
the launch list as a link and the launch itself as the current,
un-linked, segment. Following the list link SHALL reach the list in one
action, without scripting.

The header does not serve this today and is not obliged to. Both pages are
required to identify the launch surface as the one being viewed, so the header
renders `Launches` as a position rather than as a link — and the requirement
that the header make *the other* admin surfaces reachable says nothing about the
list an admin arrived from, because the list is the same surface. Nothing
therefore obliged a way back, and there was none. Whether a header entry could
also link to its own surface's index is a template question this requirement
does not settle; what it settles is that the page offers the list.

The link SHALL reach the list as the list renders with no narrowing and nothing
revealed. Carrying the reader's narrowing back is a defensible alternative and
is deliberately not chosen: an admin leaving a launch is leaving the narrowing
that found it as often as not, and a control that silently restores a filter is
harder to understand than one that plainly returns.

#### Scenario: The list is reachable from a launch's detail page

- **WHEN** a launch's detail page is rendered
- **THEN** its breadcrumb trail offers the launch list in one action, without scripting
- **AND** the trail's last segment names the launch and is not a link

### Requirement: Both surfaces are read-only

Neither the list, the detail page, nor the launch's journal page SHALL
offer any control that changes launch state. Approving a gate, accepting
or rejecting an automated result, recording an outcome and moving a
launch date SHALL remain reachable only by the paths that already serve
them.

Stated as a requirement rather than left as an omission: these pages
render an admin's own launches beside controls they are used to acting
through elsewhere, and "there is deliberately nothing to press here" is
the guarantee that makes the surface safe to open on a live launch. The
journal page inherits the guarantee rather than earning it separately —
it renders the same append-only record the detail page rendered before
this change moved it, and moving where a record is shown does not make
it writable.

#### Scenario: The pages present no launch-changing control

- **WHEN** any of the list, the detail page, or the journal page is rendered for a launch in any state
- **THEN** it offers no control that records an outcome, approves a gate, decides an automated result, or moves a launch date

### Requirement: A launch the caller may not see is indistinguishable from one that does not exist

A detail page or a journal page requested for an identifier with no
launch position, for one the caller's scope does not permit, and for an
identifier naming nothing the system knows SHALL each be refused
identically, in the same shape as a request for a route that does not
exist.

The refusal turns on the **launch position**, never on whether the
catalog can name the product. A launch position whose product the catalog
cannot resolve SHALL be served, not refused: the list renders that launch
by its raw identifier and offers its detail page in one action, so
refusing it here would put a dead end behind a row this capability
deliberately keeps visible — and during a catalog outage it would put one
behind every row. The journal page resolves the same launch position the
detail page does, so it is served or refused by the identical rule.

`launch-instance` already reports absence and refusal identically on the
read itself, so that a caller cannot confirm the existence of a launch
they may not see. A surface that answered the three differently would
give back exactly what that read withholds.

#### Scenario: A product with no launch is refused as absent

- **WHEN** a detail page or a journal page is requested for a product that has no launch position
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: A forbidden launch is refused identically

- **WHEN** a detail page or a journal page is requested for a launch the caller's scope does not permit
- **THEN** the response is identical in shape to the one given for a product with no launch

*(Unreachable end to end for the same reason, and covered the same way:
the scope resolver alone is stubbed, and the response is asserted against
the one given for a product with no launch.)*

#### Scenario: A launch whose product cannot be resolved is served

- **WHEN** a detail page is requested for a launch position whose product the catalog cannot resolve
- **THEN** the page is served, identifying the launch by its raw product identifier

#### Scenario: An unknown identifier is refused identically

- **WHEN** a detail page or a journal page is requested for an identifier with no launch position and no catalog product
- **THEN** the response is identical in shape to the other two refusals

### Requirement: Both surfaces ride the admin session and carry the shared header

Every route of the list, the detail page and the journal page SHALL
require a valid admin session and SHALL refuse a request without one in
the same absence-shaped way every other admin route does. All three
SHALL carry the header the other admin surfaces carry, identifying the
launch surface as the one being viewed, and from each the other admin
surfaces SHALL be reachable in one action without scripting.

The header identifies the surface a caller is *within*; the breadcrumb
trail beside each page's title identifies the specific launch and page
within it. The two are not the same control and this requirement does
not merge them — the header's job is switching between admin surfaces,
the breadcrumb's is moving within this one.

#### Scenario: A request without a session is refused as absent

- **WHEN** any of the three pages is requested with no admin session, or with one that has expired
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: The header names the other surfaces

- **WHEN** any of the three pages is rendered
- **THEN** its header identifies the launch surface as the one being viewed and offers the other admin surfaces in one action

### Requirement: The pages' presentation comes from the shared admin vocabulary

The list, the detail page and the journal page SHALL come from the same
stylesheet the other admin surfaces load, rather than from styling
carried in the pages themselves, so that a change to the vocabulary
reaches every admin surface rather than some of them.

`roster-admin` already requires this of itself, and records why: a page
carrying its own styling is why two surfaces an admin moves between look
like two products, and — more to the point — why a presentation fix
applied to one silently does not apply to the other, a divergence nothing
in the repository reveals. The journal page, introduced by this change,
is bound by the same requirement rather than being free to invent its own
styling.

The pages SHALL reach that stylesheet through a route no single admin
surface owns, on the same terms every other surface reaches it, and SHALL
NOT reach it through a route belonging to the module that owns another
admin surface.

#### Scenario: The pages carry no styling of their own

- **WHEN** any of the three pages is rendered
- **THEN** its presentation comes from the shared admin stylesheet, and the page carries no styling of its own

#### Scenario: The stylesheet is not reached through another surface's route

- **WHEN** any of the three pages is rendered
- **THEN** the stylesheet it loads is served by a route no single admin surface owns

#### Scenario: A vocabulary change reaches these pages

- **WHEN** the shared admin stylesheet changes
- **THEN** all three pages render under the changed vocabulary without any of them being edited

## REMOVED Requirements

### Requirement: A launch's detail page renders its journal, newest first

**Reason**: The journal is no longer rendered inline on the detail page.
It moves to its own page, reached from the detail page as a descendant,
so that the detail page stays about the launch's current position and the
journal's growing history does not run underneath it.

**Migration**: See "A launch's journal page renders its journal, newest
first" and "A launch's detail page offers its journal in one action"
below. The rendered behavior — newest entry first, each entry naming what
occurred, when, and what caused it, and an empty journal saying so — is
unchanged; only which page renders it moves.

## ADDED Requirements

### Requirement: A launch's detail page offers its journal in one action

The detail page SHALL offer the launch's journal page in one action,
without scripting, in a region beside the page's title reserved for the
page's own descendants. A launch whose journal holds nothing SHALL still
offer the journal page — the journal page itself, not the detail page,
is what states there is nothing recorded.

#### Scenario: The journal is reachable from a launch's detail page

- **WHEN** a launch's detail page is rendered
- **THEN** it offers that launch's journal page in one action, without scripting

#### Scenario: An empty journal is still reachable

- **WHEN** a launch's detail page is rendered for a launch whose journal holds no entry
- **THEN** the detail page still offers the journal page in one action

### Requirement: A launch's journal page carries a breadcrumb to the list and to its launch

The journal page SHALL carry a breadcrumb trail immediately above its title naming,
in order, the launch list and the launch itself, each as a link, with the
journal page named last as the current, un-linked, segment. The list
link SHALL reach the list as it renders with no narrowing and nothing
revealed, for the reason the detail page's own list link does. The
launch link SHALL reach that launch's detail page.

#### Scenario: Both ancestors are reachable from the journal page

- **WHEN** a launch's journal page is rendered
- **THEN** its breadcrumb trail offers the launch list and that launch's detail page, each in one action
- **AND** the trail's last segment names the journal and is not a link

### Requirement: A launch's journal page renders its journal, newest first

The journal page SHALL render the launch's journal with the most recent
entry first, each entry naming what occurred, when, and what caused it.

A launch whose journal holds nothing SHALL render the page saying so.
A journal is empty for launches that predate it, and a page that could
not be reached when empty would read as "nothing happened" on exactly
those launches — which is why the detail page offers this page
regardless of whether anything is recorded.

#### Scenario: An entry names what occurred, when, and what caused it

- **WHEN** a launch's journal holds an entry
- **THEN** the journal page renders it naming what occurred, when it occurred, and what caused it

#### Scenario: Entries render newest first

- **WHEN** a launch's journal holds several entries
- **THEN** the journal page renders them most recent first

#### Scenario: An empty journal says so

- **WHEN** a launch's journal holds no entry
- **THEN** the journal page renders and states that nothing is recorded
