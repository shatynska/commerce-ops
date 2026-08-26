## ADDED Requirements

### Requirement: The page carries a header from which the other admin surface is reachable

The roster page SHALL carry the same header the playbook admin surfaces
carry, naming the admin surfaces the session can reach, and from it the
playbook page SHALL be reachable in one action. The header SHALL
identify the roster as the surface currently being viewed.

Today the page carries no link of any kind. An admin who reaches it —
which itself requires knowing the URL, since nothing links here — cannot
get back to the playbook page without typing another one. Both
directions are the same gap and are closed together.

Reachability SHALL NOT depend on scripting.

#### Scenario: The playbook page is reachable from the roster

- **WHEN** the roster page is rendered
- **THEN** its header offers the playbook page in one action
- **AND** identifies the roster as the surface currently viewed

#### Scenario: The header is rendered on a roster holding nobody

- **WHEN** the roster page is rendered holding no people at all
- **THEN** the header is still rendered and still offers the playbook
  page

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
