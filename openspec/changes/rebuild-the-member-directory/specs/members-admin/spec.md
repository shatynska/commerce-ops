## MODIFIED Requirements

### Requirement: The Team page shows the membership whole

The **Team surface** comprises three pages: the list, the page on which a member is created, and each member's own page. Where a requirement below says "the page" without qualifying it, it means the surface as a whole.

The admin surface SHALL serve a Team page listing every active member — display name, Slack identity, ClickUp user id, admin flag — on one page without pagination. Deactivated members SHALL be reachable from the page but visibly set apart from the active membership, never interleaved with it.

Each entry's attribution — who created it and when, and its most recent update, deactivation or reactivation with who and when — SHALL be readable from the **member's own page** rather than from the list. This visibility remains the audit that replaces the deleted directory file's git trail; what changes is only where it is read. Four attribution facts per row is what made the list a place to cram things, and the member's page is where the record is now inspected.

A member's row SHALL carry no action controls. Every way of changing a member is reached through their own page.

#### Scenario: An entry's attribution is readable

- **WHEN** an admin opens a member's own page
- **THEN** the page presents who created the entry and when, and the most recent change to it with who made it and when

#### Scenario: The whole active membership is one page

- **WHEN** an admin opens the Team page
- **THEN** every active member is listed on that one page with their identity data and admin flag

#### Scenario: Deactivated members are reachable but set apart

- **WHEN** the membership holds deactivated members
- **THEN** the page presents them distinctly from the active membership, and never mixed into it

#### Scenario: A member's row carries no actions

- **WHEN** any member's row is rendered, active or deactivated
- **THEN** the row carries no control that edits, deactivates or reactivates the member

#### Scenario: A member's name opens their own page

- **WHEN** any member's row is rendered
- **THEN** their display name offers that member's own page in one action

### Requirement: A member can be created and edited from the page

Creating a member SHALL happen on a page of its own, reached from the Team page in one action, rather than through the full-width form the list carried at its top. Editing a member's updatable fields SHALL happen on that member's own page, rather than through inputs carried in a row's cells.

A clean write SHALL land through the membership's write use cases and the surface SHALL reflect it. A rejected write SHALL re-present the form it was submitted from — the create page or the member's own page — with every reported fault and the submitted values still in place, and SHALL persist nothing. A rejection SHALL NOT return the admin to the list, so that a refusal is read where the values that caused it are still visible.

#### Scenario: A created member appears on the page

- **WHEN** an admin submits a valid new member from the create page
- **THEN** the member appears on the active membership with the submitted identity data

#### Scenario: Creating is reached from the list

- **WHEN** the Team page is rendered
- **THEN** it offers the create page in one action, and carries no create form of its own

#### Scenario: A rejected write shows every fault with the typed values

- **WHEN** an admin submits a member the membership's validation rejects
- **THEN** the form is re-presented showing every fault and still holding the submitted values, and the membership is unchanged

#### Scenario: Editing happens on the member's page

- **WHEN** an admin changes a member's display name
- **THEN** the change is submitted from that member's own page and the page reflects it afterwards

### Requirement: Deactivation and reactivation are available from the page

Deactivating an active member and reactivating a deactivated one SHALL be offered on that member's own page, not on their row. A refused deactivation SHALL be surfaced on that page with the refusal's own explanation, leaving the membership unchanged.

There are now two refusals to surface, and both are the membership's own: the last-active-admin refusal, and the refusal to deactivate a member who is the default holder of an active role. The latter names every blocking role, and the page SHALL present them all rather than the first — a refusal listing one of eight roles would be read as the only obstacle.

#### Scenario: A deactivation lands and the member is set apart

- **WHEN** an admin deactivates a member who is neither the last active admin nor an active role's default holder
- **THEN** the member leaves the active membership and appears among the deactivated

#### Scenario: A blocked deactivation explains itself

- **WHEN** an admin attempts to deactivate the last active admin
- **THEN** the page shows the refusal's explanation and the member remains on the active membership

#### Scenario: A role-blocked deactivation names every blocking role

- **WHEN** an admin attempts to deactivate a member who is the default holder of several active roles
- **THEN** the page shows the refusal naming all of those roles, and the member remains on the active membership

### Requirement: The page's presentation comes from the shared admin vocabulary

The Team surface's presentation SHALL come from the same stylesheet the
playbook admin surfaces load, rather than from styling carried in the
pages themselves, so that a change to the vocabulary reaches every admin
surface rather than one.

The page currently carries its own inline style block, which is why the
two surfaces an admin moves between look like two products. More to the
point, it is why a presentation fix applied to one of them silently does
not apply to the other — a divergence nothing in the repository reveals.

That stylesheet SHALL be served behind the same admin guard the members
page's own routes ride, refused to a caller without a valid admin
session in the same shape as any other unauthorised admin path, and
SHALL be served as committed with no build step between source and
response.

The Team surface SHALL NOT reach the asset through a route belonging to
the module that owns **another admin surface**. A shared route every
surface reaches on equal terms is what this requires; what it forbids is
one admin surface depending on a route owned by another, where nothing
in the import graph would record the dependency and deleting the route
while working on that other surface would break this page silently.

The surface's actions — creating, editing, deactivating and reactivating
a member — SHALL each carry the marker `row-action`, and the destructive
one SHALL carry the further marker `danger`. `Deactivate` is this
surface's destructive action. Those controls no longer sit on a row:
they sit on the create page and on each member's own page, which is
where the markers are now observed. A member's row carries neither
marker, having no action controls left to mark.

The marker named `row-action` is retained despite no longer naming a
row's action. Renaming it would touch every admin template and
stylesheet rule at once for a vocabulary change with no behavioural
content, and would put that churn in the same diff as this rebuild. It
is the shared admin vocabulary's word for *an action control*, and
correcting it is separate work.

The `td.actions form { display: contents }` rule SHALL be removed with
the row actions it was working around, rather than left behind as a
rule matching nothing.

#### Scenario: The page carries no styling of its own

- **WHEN** any Team surface page is rendered
- **THEN** it loads the shared admin stylesheet
- **AND** carries no page-local style block

#### Scenario: The stylesheet is refused without an admin session

- **WHEN** the stylesheet is requested from the membership surface with no
  admin session cookie
- **THEN** the response is the same 404 an unregistered route returns
- **AND** carries no stylesheet content

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** an active member's own page is rendered
- **THEN** its deactivate control carries `danger`
- **AND** no other control on that page carries it

#### Scenario: A deactivated member's action is not destructive

- **WHEN** a deactivated member's own page is rendered
- **THEN** its reactivate control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: The create control speaks the same vocabulary

- **WHEN** the create page is rendered
- **THEN** its submit control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: A row carries neither marker

- **WHEN** any member's row is rendered on the list
- **THEN** it carries no control marked `row-action` and none marked `danger`

#### Scenario: The workaround rule is gone

- **WHEN** the shared admin stylesheet is served
- **THEN** it carries no rule setting a form inside a table's actions cell to `display: contents`

### Requirement: The page carries a header from which the other admin surface is reachable

Every page of the Team surface — the list, the create page and each
member's own page — SHALL carry the same header every other admin
surface carries, naming the admin surfaces the session can reach, and
from it each of those other surfaces SHALL be reachable in one action.
The header SHALL identify the membership as the surface currently being
viewed.

The requirement was written when the Team surface was a single page, and
said "The Team page". It is now three, and the guarantee was never about
one page in particular: an admin who reaches any admin surface can reach
the others from it without knowing a URL. A create page or a member's
page rendered without the header would be a page from which the rest of
the admin is unreachable — which is precisely the gap this requirement
exists to close, reopened on the two pages the rebuild adds.

The requirement was also written when there were two admin surfaces and
named the playbook page as "the other" one. There are more than two now.
The header SHALL name every surface the session can reach, so that a
surface added later is added to one partial rather than left unreachable
from the pages that predate it — the roles surface this change adds
being the case in point.

Reachability SHALL NOT depend on scripting.

#### Scenario: The playbook page is reachable from the membership

- **WHEN** the Team page is rendered
- **THEN** its header offers the playbook page in one action
- **AND** identifies the membership as the surface currently viewed

#### Scenario: Every other admin surface is reachable from the membership

- **WHEN** the Team page is rendered
- **THEN** its header offers each admin surface the session can reach, other than the membership itself, in one action

#### Scenario: The header is rendered on a membership holding nobody

- **WHEN** the Team page is rendered holding no members at all
- **THEN** the header is still rendered and still offers the other admin
  surfaces

#### Scenario: A surface added later is named by the header

- **WHEN** an admin surface beyond the playbook and membership pages is reachable by the session
- **THEN** the Team page's header names it and offers it in one action

#### Scenario: The create page and a member's page carry the header too

- **WHEN** the create page or a member's own page is rendered
- **THEN** it carries the same header, offering the other admin surfaces in one action

## ADDED Requirements

### Requirement: The create page and a member's own page carry a breadcrumb back to the list

The create page and each member's own page SHALL carry a breadcrumb trail whose linked segment names the Team list on both pages, and whose current, un-linked segment reads `New member` on the create page and the member's display name on a member's own page. The current segment SHALL be rendered as the page's own title, so that the page carries no separate title beside it.

The header does not serve this and is not obliged to. It identifies the membership as the surface being viewed, rendering it as a position rather than as a link, and its guarantee concerns the *other* admin surfaces — the list a member's page was reached from is the same surface, so nothing in the header requirement obliges a way back. `launch-admin` records exactly this gap having been left open on its own detail pages, and `playbook-admin` records the breadcrumb that closed it for steps. This rebuild copies that shipped pattern, and copying it without the part that had to be added later would reproduce the defect rather than the pattern.

Following the breadcrumb SHALL NOT depend on scripting.

#### Scenario: A member's page offers the list

- **WHEN** a member's own page is rendered
- **THEN** it carries a breadcrumb naming the Team list as a link and the member's display name as the current, un-linked segment

#### Scenario: The create page offers the list

- **WHEN** the create page is rendered
- **THEN** it carries a breadcrumb naming the Team list as its linked segment and `New member` as its current, un-linked segment

#### Scenario: The breadcrumb needs no scripting

- **WHEN** a member's page is rendered and its breadcrumb link is followed without scripting
- **THEN** the Team list is reached
