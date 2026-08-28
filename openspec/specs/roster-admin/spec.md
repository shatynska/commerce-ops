# roster-admin Specification

## Purpose
The admin surface's roster page: people are listed, created, edited, deactivated and reactivated from the browser, on the same authenticated admin surface the playbook page rides.

## Requirements

### Requirement: The roster page shows the roster whole

The admin surface SHALL serve a roster page listing every active person — display name, Slack identity, ClickUp user id, admin flag — on one page without pagination. Deactivated people SHALL be reachable from the page but visibly set apart from the active roster, never interleaved with it. Each entry's attribution SHALL be readable from the page — who created it and when, and its most recent update, deactivation or reactivation with who and when — this visibility being the audit that replaces the deleted directory file's git trail.

#### Scenario: An entry's attribution is readable

- **WHEN** an admin views a person's entry on the roster page
- **THEN** the page presents who created the entry and when, and the most recent change to it with who made it and when

#### Scenario: The whole active roster is one page

- **WHEN** an admin opens the roster page
- **THEN** every active person is listed on that one page with their identity data and admin flag

#### Scenario: Deactivated people are reachable but set apart

- **WHEN** the roster holds deactivated people
- **THEN** the page presents them distinctly from the active roster, and never mixed into it

### Requirement: A person can be created and edited from the page

The roster page SHALL offer creating a person and editing an existing person's updatable fields. A clean write SHALL land through the roster's write use cases and the page SHALL reflect it. A rejected write SHALL re-present the form with every reported fault and the submitted values still in place, and SHALL persist nothing.

#### Scenario: A created person appears on the page

- **WHEN** an admin submits a valid new person from the page
- **THEN** the person appears on the active roster with the submitted identity data

#### Scenario: A rejected write shows every fault with the typed values

- **WHEN** an admin submits a person the roster's validation rejects
- **THEN** the form is re-presented showing every fault and still holding the submitted values, and the roster is unchanged

### Requirement: Deactivation and reactivation are available from the page

The roster page SHALL offer deactivating an active person and reactivating a deactivated one. A refused deactivation — the last-admin refusal — SHALL be surfaced on the page with the refusal's explanation, leaving the roster unchanged.

#### Scenario: A deactivation lands and the person is set apart

- **WHEN** an admin deactivates a person who is not the last active admin
- **THEN** the person leaves the active roster and appears among the deactivated

#### Scenario: A blocked deactivation explains itself

- **WHEN** an admin attempts to deactivate the last active admin
- **THEN** the page shows the refusal's explanation and the person remains on the active roster

### Requirement: The page carries a header from which the other admin surface is reachable

The roster page SHALL carry the same header every other admin surface
carries, naming the admin surfaces the session can reach, and from it
each of those other surfaces SHALL be reachable in one action. The header
SHALL identify the roster as the surface currently being viewed.

The requirement was written when there were two admin surfaces and named
the playbook page as "the other" one. There are more than two now, and
the guarantee was never about that page in particular: what it asks is
that an admin who reaches any admin surface can reach the others from it
without knowing a URL. The header SHALL name every surface the session
can reach, so that a surface added later is added to one partial rather
than left unreachable from the pages that predate it.

Today the page carries no link of any kind. An admin who reaches it —
which itself requires knowing the URL, since nothing links here — cannot
get back to the other surfaces without typing another one. Both
directions are the same gap and are closed together.

Reachability SHALL NOT depend on scripting.

#### Scenario: The playbook page is reachable from the roster

- **WHEN** the roster page is rendered
- **THEN** its header offers the playbook page in one action
- **AND** identifies the roster as the surface currently viewed

#### Scenario: Every other admin surface is reachable from the roster

- **WHEN** the roster page is rendered
- **THEN** its header offers each admin surface the session can reach, other than the roster itself, in one action

#### Scenario: The header is rendered on a roster holding nobody

- **WHEN** the roster page is rendered holding no people at all
- **THEN** the header is still rendered and still offers the other admin
  surfaces

#### Scenario: A surface added later is named by the header

- **WHEN** an admin surface beyond the playbook and roster pages is reachable by the session
- **THEN** the roster page's header names it and offers it in one action

### Requirement: The page's presentation comes from the shared admin vocabulary

The roster page's presentation SHALL come from the same stylesheet the
playbook admin surfaces load, rather than from styling carried in the
page itself, so that a change to the vocabulary reaches both admin
surfaces rather than one.

The page currently carries its own inline style block, which is why the
two surfaces an admin moves between look like two products. More to the
point, it is why a presentation fix applied to one of them silently does
not apply to the other — a divergence nothing in the repository reveals.

That stylesheet SHALL be served behind the same admin guard the roster
page's own routes ride, refused to a caller without a valid admin
session in the same shape as any other unauthorised admin path, and
SHALL be served as committed with no build step between source and
response.

The roster page SHALL NOT reach the asset through a route belonging to
the module that owns **the other admin surface**. A shared route both
surfaces reach on equal terms is what this requires; what it forbids is
one admin surface depending on a route owned by the other, where nothing
in the import graph would record the dependency and deleting the route
while working on that other surface would break this page silently.

The page's actions — creating, editing, deactivating and reactivating a
person — SHALL each carry the marker `row-action`, and the destructive
one SHALL carry the further marker `danger`, exactly as the playbook
page's step actions do. `Deactivate` is this page's destructive action.
The create control is included deliberately: it is the one action not on
a person's row, and a create submit left at the default weight while
every neighbour is restyled is precisely the mismatch this requirement
exists to end.

#### Scenario: The page carries no styling of its own

- **WHEN** the roster page is rendered
- **THEN** it loads the shared admin stylesheet
- **AND** carries no page-local style block

#### Scenario: The stylesheet is refused without an admin session

- **WHEN** the stylesheet is requested from the roster surface with no
  admin session cookie
- **THEN** the response is the same 404 an unregistered route returns
- **AND** carries no stylesheet content

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** an active person's row is rendered
- **THEN** its deactivate control carries `danger`
- **AND** no other action control on that row carries it

#### Scenario: A deactivated person's action is not destructive

- **WHEN** a deactivated person's row is rendered
- **THEN** its reactivate control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: The create control speaks the same vocabulary

- **WHEN** the page's add-a-person form is rendered
- **THEN** its submit control carries `row-action`
- **AND** does not carry `danger`
