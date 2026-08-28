## ADDED Requirements

### Requirement: A step's name in the table opens its edit page

Each step's row SHALL offer that step's edit page in one action through
the step's own name, the way a launch's row already offers its detail
page through the launch's label and a product's row already offers its
dossier through the product's SKU. This is offered **alongside** the
row's existing `edit` action, not instead of it — nothing here changes
which actions a row offers or removes the `edit` control this capability
already requires.

#### Scenario: A step's name opens its edit page

- **WHEN** an active step's row is rendered
- **THEN** its name offers that step's edit page in one action
- **AND** the row's own `edit` action is still present and unchanged

### Requirement: The edit and create surfaces carry a breadcrumb to the step table

The edit surface and the create surface SHALL each carry a breadcrumb
trail immediately above their title, naming the step table as a link and the
surface itself as the current, un-linked, segment — `Playbook steps`
naming the table on the create surface, and the step's own name on the
edit surface. Following the table link SHALL carry forward whatever
narrowing was active when the admin left the table, so returning from an
edit or an abandoned create lands where the admin left rather than on an
unnarrowed table.

The narrowing is carried here deliberately, unlike the launch detail
page's link back to the launch list: an admin who opens a step to edit
it, or opens the create surface, has not left the table's narrowing
behind the way a launch's own detail page — a destination in its own
right — leaves the list's. Editing and creating are interruptions of
work done *on* the table, and returning to a different view of it than
the one that was open is the surprise this requirement exists to
prevent. This is the existing behavior of each surface's own back
link, carried forward under the breadcrumb rather than changed by it.

#### Scenario: The table is reachable from the edit surface, narrowing intact

- **WHEN** a step's edit surface is rendered under an active narrowing
- **THEN** its breadcrumb trail offers the step table in one action, without scripting
- **AND** following it renders the table under that same narrowing

#### Scenario: The table is reachable from the create surface, narrowing intact

- **WHEN** the create surface is rendered under an active narrowing
- **THEN** its breadcrumb trail offers the step table in one action, without scripting
- **AND** following it renders the table under that same narrowing

#### Scenario: The edit surface's trail names the step

- **WHEN** a step's edit surface is rendered
- **THEN** its breadcrumb trail's last segment names that step and is not a link
