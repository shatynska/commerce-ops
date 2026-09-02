## ADDED Requirements

### Requirement: A launch's journal page renders every entry as a row, newest first

The journal page SHALL render the launch's journal as a table, with the
most recent entry first, a row for each entry carrying when it
occurred, its label, a gate/step, its source, who recorded it, and a
detail — when leading the row, since a journal is read by when
something happened before it is read by what happened.
The gate/step column SHALL carry the entry's subject where that subject
names a gate or a step, and SHALL be empty otherwise. Detail is
this page's own composed phrase, built from `launch-journal`'s per-kind
fact fields (`playbook_version`, `outcome`, `reason`, `evidence`,
`decision`, `posture`, `standing_at`, `previous_date`,
`new_date`, `unsatisfied`) — the page tried a
column per fact, then two columns, and settled on one short readable
phrase per entry, the shape closest to how a reader actually wants to
scan a kind-specific fact. The phrase SHALL NOT restate a subject that
already has its own gate/step column.

Every journal kind now names either a gate or a step as its subject, so
the gate/step column is empty only where an occurrence names no subject
at all. A metric obligation reaches this page as an ordinary step, its
threshold being the step's own description, and needs no exception to
the columns' meaning.

Where an entry's `actor` matches a person the roster carries — by that
person's roster identifier or by their ClickUp user id — the page
SHALL render the person's name rather than the raw identifier; where
it matches neither, the page SHALL render the raw value rather than
omitting it or failing.

Where an entry carries no source, the page SHALL render its source
column as `system` rather than as an absence — `system` names that no
channel was recorded for the occurrence, independently of whether the
entry names an actor: a graduating entry carries a known approver and
still no recorded source, and SHALL still read `system` in that column
without implying the approver is unknown, since `who` renders that
fact in its own column regardless.

The presentation SHALL be observable in the rendered response, and
SHALL match the visual vocabulary the detail page's own step table
uses for the same purpose (`kind-tag`/`outcome-tag`'s shared shape;
row height and font size inherited from the site-wide table rule
rather than overridden per page) rather than a distinct one:

- Each row SHALL carry the marker `category-` followed by the entry's
  category, one of `category-progression`, `category-judgment`,
  `category-blocked`, `category-admin`, matching the standard `A
  step's outcome is rendered as a tag carrying its state` already
  holds for the detail page's own markers: the literal tokens are
  given because they are what a test is derived from.
- The label SHALL render as a tag carrying the marker `kind-tag`,
  coloured according to the row's category — the same "readable by
  treatment before it is read by word" standard `outcome-tag` already
  holds, applied to the kind a reader scans a journal by instead of
  the outcome a reader scans a step by.
- The source SHALL render as a tag carrying the marker `mark`, the
  page's existing plain-fact vocabulary (`A step's actions are
  presented as one affordance vocabulary`'s sibling for a stated fact
  rather than a control) — flat and uncoloured by category, since a
  source is where an occurrence arrived from, not a judgement on it.

The markers are a necessary condition, not a sufficient one — that the
categories are visually distinguished from one another, and that the
journal table's row height and type size read as one page with the
detail page's own tables, SHALL be confirmed by direct inspection of
the rendered page.

A launch whose journal holds nothing SHALL render the page saying so.
A journal is empty for launches that predate it, and a page that could
not be reached when empty would read as "nothing happened" on exactly
those launches — which is why the detail page offers this page
regardless of whether anything is recorded.

#### Scenario: An entry names when it occurred

- **WHEN** a launch's journal holds an entry
- **THEN** its row shows the moment it occurred, in its own column

#### Scenario: An entry's row shows its subject, source and who recorded it as separate facts

- **WHEN** a launch's journal holds an entry carrying a subject, a source and an actor
- **THEN** its row shows each in its own column, and none of the three is folded into a sentence with another

#### Scenario: A kind's facts are composed into the row's detail phrase

- **WHEN** a launch's journal holds a `step-outcome-recorded` entry carrying an outcome and a reason
- **THEN** its row's detail column shows a phrase naming both, without a further column for the second

#### Scenario: A detail phrase does not restate the subject

- **WHEN** a launch's journal holds an entry carrying a subject that names a gate or a step
- **THEN** its row's detail column does not repeat that subject — the subject is read from its own gate/step column instead

#### Scenario: A metric step reads as a step

- **WHEN** a launch's journal holds a `step-outcome-recorded` entry for a blocking step declaring a metric identifier
- **THEN** its row's gate/step column carries that step, exactly as for any other step, and its detail column carries the entry's own facts

#### Scenario: A sourceless entry's source column says system

- **WHEN** a launch's journal holds an entry carrying no source
- **THEN** its row's source column reads `system`, whether or not that entry names an actor

#### Scenario: A known actor resolves to their name by roster identifier

- **WHEN** an entry's `actor` is the roster identifier of a person the roster carries
- **THEN** the row shows that person's name rather than the raw identifier

#### Scenario: A known actor resolves to their name by ClickUp user id

- **WHEN** an entry's `actor` is the ClickUp user id of a person the roster carries
- **THEN** the row shows that person's name rather than the raw identifier

#### Scenario: An unresolvable actor renders as its raw value

- **WHEN** an entry's `actor` does not match any person the roster carries, by either identifier
- **THEN** the row shows the raw actor value rather than omitting it

#### Scenario: An entry's row shows its label as a coloured kind tag and carries its category marker

- **WHEN** a launch's journal holds an entry
- **THEN** its row shows the entry's short label as a tag carrying the marker `kind-tag`, coloured according to the row's category, and the row carries the marker `category-` followed by its category

#### Scenario: A source renders as a plain, uncoloured tag

- **WHEN** a launch's journal holds an entry carrying a source
- **THEN** its row shows that source as a tag carrying the marker `mark`, its colour independent of the row's category

#### Scenario: Entries render newest first

- **WHEN** a launch's journal holds several entries
- **THEN** the journal page renders them most recent first

#### Scenario: An empty journal says so

- **WHEN** a launch's journal holds no entry
- **THEN** the journal page renders and states that nothing is recorded

## REMOVED Requirements

### Requirement: A launch's journal page renders its journal, newest first

**Reason**: The requirement carried an exception for the one journal kind whose subject was neither a gate nor a step — a `metric-attested` entry, whose subject was the condition being attested. With attestation removed, no kind has that shape, so the exception describes a row the page can never render and the `gate_id` fact it composed into the detail phrase is populated by nothing. *A launch's journal page renders every entry as a row, newest first* replaces it, keeping every other rule about columns, actor resolution, tags and empty journals unchanged.

**Migration**: None. No `metric-attested` entry was ever written, so no rendered row changes.
