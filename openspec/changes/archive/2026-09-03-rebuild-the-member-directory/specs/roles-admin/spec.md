## Purpose

The admin surface's Roles pages: the role collection is listed, and each role is created, renamed, retired, un-retired and has its holders and default managed from its own page, on the same authenticated admin surface the Team and playbook pages ride.

## ADDED Requirements

### Requirement: The Roles page lists the collection grouped by status

The admin surface SHALL serve a Roles page listing every role on one page without pagination, presenting for each its title, its slug, and its default holder where it has one. Roles SHALL be grouped by status so that `active`, `draft` and `retired` are each visibly set apart and never interleaved — a draft role and an active one differ in exactly one obligation, and a listing that mixed them would leave that difference to be inferred from a column.

A role's row SHALL carry no action controls at all. There is no reordering here — the collection has no authored order — so unlike a step's row there is not even one action left on it, and every way of changing a role is reached through its own page.

#### Scenario: The whole collection is one page

- **WHEN** an admin opens the Roles page
- **THEN** every role is listed on that one page with its title, slug and default holder

#### Scenario: The three statuses are set apart

- **WHEN** the collection holds active, draft and retired roles
- **THEN** the page presents each status group distinctly, and never mixes roles of different statuses into one group

#### Scenario: A role with no default holder is listed without one

- **WHEN** a draft role holding nobody is listed
- **THEN** its row is rendered showing no default holder, rather than being omitted or rendered as holding a placeholder person

#### Scenario: A role's row carries no actions

- **WHEN** any role's row is rendered, whatever its status
- **THEN** the row carries no control that renames, retires, un-retires or activates the role, and none that changes its holders

### Requirement: A role's title in the list opens its own page

Each role's row SHALL offer that role's own page in one action through the role's title, the way a step's row offers its edit page through the step's name and a member's row offers theirs. This is the row's only way into a role.

A role's slug SHALL be presented on the row but SHALL NOT be a second way in — one row, one destination, so that which of two adjacent controls an admin clicked is never the question.

#### Scenario: A role's title opens its page

- **WHEN** any role's row is rendered
- **THEN** its title offers that role's own page in one action

#### Scenario: The slug is shown but is not a link

- **WHEN** any role's row is rendered
- **THEN** its slug is readable on the row and offers no destination of its own

### Requirement: A role is created on its own page

Creating a role SHALL happen on a page of its own, reached from the Roles page, rather than through a form carried at the top of the list. The Roles page SHALL offer that page in one action.

The create page SHALL take the slug, the title, and the role's initial status and default holder together — a role created `active` needs a default holder to satisfy the active-role obligation, so the page SHALL take one in the same submission rather than creating a role that is momentarily incoherent and asking for a holder afterwards. Creating a `draft` role SHALL NOT require a holder.

#### Scenario: Creating is reached from the list

- **WHEN** the Roles page is rendered
- **THEN** it offers the create page in one action, and carries no create form of its own

#### Scenario: An active role is created with its default holder in one submission

- **WHEN** an admin submits a new role with status `active`, a slug, a title and a default holder
- **THEN** the role is created active with that member as its sole holder and default, and appears in the active group

#### Scenario: A draft role is created holding nobody

- **WHEN** an admin submits a new role with status `draft` and no holder
- **THEN** the role is created and appears in the draft group holding nobody

#### Scenario: An active role submitted without a holder is rejected

- **WHEN** an admin submits a new role with status `active` and no default holder
- **THEN** the create page is re-presented with the fault and the submitted values still in place, and no role is created

### Requirement: A role's own page carries every change to it

A role's page SHALL offer: correcting its title, adding and removing holders, moving the default to another holder, and its permitted status transitions — activating a draft, retiring, and un-retiring. Its slug SHALL be presented as an unchangeable value rather than as an input, since `roles` states it is chosen once and never changes.

The page SHALL offer only the transitions permitted from that role's current status, rather than offering all of them and refusing on submission: a retired role SHALL be offered un-retiring and not retiring, an active role retiring and not activating, and no role of any status SHALL be offered a return to `draft`.

The page SHALL present the role's attribution — who created it and when, and its most recent change with who made it and when — the same audit the Team page presents for a member.

#### Scenario: The slug is not editable

- **WHEN** a role's page is rendered
- **THEN** its slug is presented as a value and not as an editable input

#### Scenario: Only permitted transitions are offered

- **WHEN** a retired role's page is rendered
- **THEN** it offers un-retiring, and offers neither retiring nor any return to `draft`

#### Scenario: A draft role is offered activation

- **WHEN** a draft role's page is rendered
- **THEN** it offers activating the role and retiring it, and does not offer un-retiring

#### Scenario: Holders are managed from the role's page

- **WHEN** an admin adds a holder, removes a non-default holder, and moves the default on a role's page
- **THEN** each write lands and the page reflects the role's holders and default afterwards

#### Scenario: The role's attribution is readable

- **WHEN** an admin views a role's page
- **THEN** the page presents who created the role and when, and its most recent change with who made it and when

### Requirement: A rejected role write re-presents the form with its faults

A clean write SHALL land through the role collection's write use cases and the surface SHALL reflect it. A rejected write SHALL re-present the form it was submitted from — the create page or the role's own page — showing every reported fault with the submitted values still in place, and SHALL persist nothing. A rejection SHALL NOT return the admin to the list, so that a refusal is read where the values that caused it are still visible.

A refused transition SHALL be surfaced with the refusal's own explanation rather than a generic one: activating a draft role holding nobody, un-retiring a role whose default has since been deactivated, and removing an active role's default each explain the specific obligation they failed.

#### Scenario: A rejected write shows every fault with the typed values

- **WHEN** an admin submits a role change the collection's validation rejects
- **THEN** the form is re-presented showing every fault and still holding the submitted values, and the collection is unchanged

#### Scenario: A refused activation explains its own obligation

- **WHEN** an admin activates a draft role holding nobody
- **THEN** the page shows that an active role must have a default holder, and the role remains draft

#### Scenario: A refused default removal explains its own obligation

- **WHEN** an admin removes the default holder of an active role holding other members
- **THEN** the page shows that the default must be moved to another holder first, and the holders are unchanged

### Requirement: The create page and a role's own page carry a breadcrumb back to the list

Every Roles page SHALL carry a breadcrumb trail, and its segments SHALL name the containment: `Team` first, then `Roles`, then — on the create page and a role's own page — that page itself.

`Team` and `Roles` SHALL be links wherever they are not the current page; the last segment SHALL be un-linked and SHALL read `New role` on the create page and the role's title on a role's own page. The current segment SHALL be rendered as the page's own title, so that the page carries no separate title beside it.

The Roles listing carries this trail as well as the two sub-pages, which is a departure from the steps surface, where only the sub-pages do. It is the listing's only way back to the members half, and it is what states — on the page where an admin most needs to read it — that roles sit inside Team rather than beside it.

The header does not serve this and is not obliged to. It identifies the roles surface as the one being viewed, rendering it as a position rather than as a link, and its guarantee concerns the *other* admin surfaces — the list a role's page was reached from is the same surface, so nothing in the header requirement obliges a way back. `launch-admin` records exactly this gap having been left open on its own detail pages, and `playbook-admin` records the breadcrumb that closed it for steps. A surface built now to the pattern minus the part that had to be added later would repeat the mistake this change exists to undo.

Following the breadcrumb SHALL NOT depend on scripting.

#### Scenario: A role's page offers the list

- **WHEN** a role's own page is rendered
- **THEN** it carries a breadcrumb offering the Roles list in one action, with the role's title as the current, un-linked segment

#### Scenario: The create page offers the list

- **WHEN** the create page is rendered
- **THEN** it carries a breadcrumb offering the Roles list in one action, with `New role` as its current, un-linked segment

#### Scenario: The listing's own breadcrumb names its container

- **WHEN** the Roles page is rendered
- **THEN** it carries a breadcrumb offering `Team` in one action, with `Roles` as its current, un-linked segment

#### Scenario: The breadcrumb needs no scripting

- **WHEN** a role's page is rendered and its breadcrumb link is followed without scripting
- **THEN** the Roles list is reached

### Requirement: The Roles pages sit inside the Team surface

Roles are a **section of the Team surface**, not an admin surface of their own. A role's holders are members, both collections live in one module, and an admin moving between them is doing one job — so the shared admin header, which names the admin *surfaces*, SHALL NOT carry a roles entry, and every Roles page SHALL render that header identifying **Team** as the surface currently being viewed.

Every Roles page SHALL nevertheless carry that header, so that each admin surface the session can reach is reachable from it in one action — the guarantee is about not stranding an admin, and it is owed by a section as much as by a surface.

The roles listing SHALL be reachable from the members listing in one action, through the heading of the column presenting each member's roles. The link sits on the thing it explains: a reader looking at which roles a member holds is already looking at the subject the roles listing is about, so the way there belongs on that column rather than in a navigation bar above the page.

The roles listing SHALL in turn offer the members listing in one action, through its breadcrumb's `Team` segment. Both directions are required together — the header identifies Team as the current surface and so links to neither half, and a section reachable in one direction only strands whoever follows it.

Reachability SHALL NOT depend on scripting.

#### Scenario: Every other admin surface is reachable from the roles surface

- **WHEN** the Roles page is rendered
- **THEN** its header offers each admin surface the session can reach in one action
- **AND** identifies Team as the surface currently viewed

#### Scenario: The header carries no roles entry

- **WHEN** any admin page is rendered
- **THEN** its header names no surface for roles, roles being a section of Team rather than a surface

#### Scenario: The roles listing is reached from the members listing

- **WHEN** the Team page is rendered
- **THEN** the heading of the column presenting each member's roles offers the roles listing in one action

#### Scenario: The members listing is reached back from the roles listing

- **WHEN** the Roles page is rendered
- **THEN** it offers the members listing in one action

#### Scenario: The header is rendered on an empty collection

- **WHEN** the Roles page is rendered holding no roles at all
- **THEN** the header is still rendered and still offers the other admin surfaces

#### Scenario: A role's own page carries the header too

- **WHEN** a role's page is rendered
- **THEN** it carries the same header, offering the other admin surfaces in one action

#### Scenario: The create page carries the header too

- **WHEN** the create page is rendered
- **THEN** it carries the same header, offering the other admin surfaces in one action

### Requirement: The Roles pages' presentation comes from the shared admin vocabulary

The Roles pages' presentation SHALL come from the same stylesheet the other admin surfaces load, rather than from styling carried in the pages themselves, so that a change to the vocabulary reaches every admin surface rather than one. The pages SHALL carry no page-local style block.

Each action control on a role's own page and on the create page SHALL carry the marker `row-action`, observable in the rendered response rather than expressed only visually, and the destructive one SHALL carry the further marker `danger`. **Retire** is this surface's destructive action; un-retiring, activating, renaming and every holder action are not. Removing a holder is deliberately not destructive: it takes nothing away that cannot be restored by adding the member back, and marking it `danger` alongside retirement would flatten the distinction the marker exists to draw.

#### Scenario: The pages carry no styling of their own

- **WHEN** any Roles surface is rendered
- **THEN** it loads the shared admin stylesheet
- **AND** carries no page-local style block

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** an active role's page is rendered
- **THEN** its retire control carries `danger`
- **AND** no other control on that page carries it

#### Scenario: Un-retiring is not destructive

- **WHEN** a retired role's page is rendered
- **THEN** its un-retire control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: Removing a holder is not destructive

- **WHEN** a role's page is rendered offering a holder's removal
- **THEN** that control carries `row-action`
- **AND** does not carry `danger`
