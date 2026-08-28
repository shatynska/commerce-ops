## MODIFIED Requirements

### Requirement: A launch's detail page renders its journal, newest first

The detail page SHALL render the launch's journal as a table, with the most recent entry first, each row naming the entry's label, what occurred, when, and what caused it.

The presentation SHALL be observable in the rendered response — each row SHALL carry the marker `category-` followed by the entry's category, one of `category-progression`, `category-judgment`, `category-blocked`, `category-admin`, matching the standard `A step's outcome is rendered as a tag carrying its state` already holds for this page's other markers: the literal tokens are given because they are what a test is derived from. The markers are a necessary condition, not a sufficient one — that the categories are visually distinguished from one another SHALL be confirmed by direct inspection of the rendered page.

A launch whose journal holds nothing SHALL render the section saying so. A journal is empty for launches that predate it, and a section that vanished when empty would read as "nothing happened" on exactly those launches.

#### Scenario: An entry names what occurred, when, and what caused it

- **WHEN** a launch's journal holds an entry
- **THEN** it is rendered naming what occurred, when it occurred, and what caused it

#### Scenario: An entry's row shows its label and carries its category marker

- **WHEN** a launch's journal holds an entry
- **THEN** its row shows the entry's short label, and carries the marker `category-` followed by its category

#### Scenario: Entries render newest first

- **WHEN** a launch's journal holds several entries
- **THEN** they are rendered most recent first

#### Scenario: An empty journal says so

- **WHEN** a launch's journal holds no entry
- **THEN** the section is rendered and states that nothing is recorded
