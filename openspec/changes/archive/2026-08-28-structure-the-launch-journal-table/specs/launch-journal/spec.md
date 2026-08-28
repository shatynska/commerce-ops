## MODIFIED Requirements

### Requirement: One launch's journal is readable, most recent first

The system SHALL report one launch's journal, given the product identifier the launch references, with the most recent entry first — ordered by the moment each entry names, entries naming the same moment reported in the reverse of the order they were appended, so that the later of two simultaneous entries is reported first.

Each reported entry SHALL name what occurred, when it occurred, and what caused it. What caused it is the person and the source where the occurrence names one — the recorder of a step outcome, the approver of a decision, the attester of a metric condition — and the command that produced it where the occurrence names nobody.

Each reported entry SHALL additionally carry a short label naming its kind, and a category, both composed at read time from the stored occurrence rather than stored. The label SHALL be one of a fixed set, one per journal kind. The category SHALL be one of a fixed set of four — progression, judgment, blocked, admin — assigned per kind, except for two kinds whose category depends on a fact the occurrence carries, so that a negative outcome reads distinctly from ordinary progress:

- a `gate-approval-recorded` entry SHALL be categorized blocked where it carries a rejecting decision and judgment where it carries an approving one;
- a `step-outcome-recorded` entry SHALL be categorized blocked where the outcome it names is `Blocked` or `Refused`, and progression for every other outcome.

A read made on a caller's behalf SHALL be subject to that caller's access scope: a launch whose product identifier the scope does not permit SHALL report an empty journal, exactly as a launch with nothing recorded does, so that a read can never confirm the existence of a launch the caller may not see.

A launch that predates the journal, and a product with no launch record at all, SHALL each report an empty journal rather than an error.

#### Scenario: A launch's journal is read most recent first

- **WHEN** a launch whose journal holds three entries naming three different moments is read
- **THEN** the three entries are reported most recent first

#### Scenario: Entries naming the same moment report the later append first

- **WHEN** two entries naming the same moment are read
- **THEN** the one appended later is reported first

#### Scenario: An entry reports what occurred, when, and what caused it

- **WHEN** a launch whose journal holds a step outcome recorded by a named person from a named source is read
- **THEN** that entry names what occurred, the moment it occurred, and that person and source as what caused it

#### Scenario: An occurrence naming nobody reports the command as its cause

- **WHEN** an entry for an occurrence that names no person is read
- **THEN** it names the command that produced it as what caused it

#### Scenario: An entry reports a label naming its kind

- **WHEN** any entry is read
- **THEN** it carries a short label naming its kind, drawn from the fixed set of labels rather than the raw kind string

#### Scenario: An entry reports a category

- **WHEN** any entry is read
- **THEN** it carries one of the four categories — progression, judgment, blocked, admin

#### Scenario: A rejecting approval categorizes as blocked

- **WHEN** a `gate-approval-recorded` entry carrying a rejecting decision is read
- **THEN** it is categorized blocked, not judgment

#### Scenario: An approving approval categorizes as judgment

- **WHEN** a `gate-approval-recorded` entry carrying an approving decision is read
- **THEN** it is categorized judgment, not blocked

#### Scenario: A blocked or refused step outcome categorizes as blocked

- **WHEN** a `step-outcome-recorded` entry naming the outcome `Blocked`, or one naming the outcome `Refused`, is read
- **THEN** each is categorized blocked, not progression

#### Scenario: Every other step outcome categorizes as progression

- **WHEN** a `step-outcome-recorded` entry naming the outcome `NotStarted`, `InProgress`, `Satisfied`, or `NotApplicable` is read
- **THEN** it is categorized progression, not blocked

#### Scenario: An out-of-scope launch reports an empty journal

- **WHEN** a launch's journal is read on the behalf of a caller whose scope does not permit that product
- **THEN** an empty journal is reported, exactly as for a launch with nothing recorded

#### Scenario: A launch with nothing recorded reports an empty journal

- **WHEN** the journal of a launch that has nothing recorded is read — the state every launch predating the journal is in
- **THEN** an empty journal is reported, rather than an error

#### Scenario: A product with no launch record reports an empty journal

- **WHEN** the journal is read for a product identifier that has no launch record at all
- **THEN** an empty journal is reported, indistinguishable from that of a permitted launch with nothing recorded, rather than an error
