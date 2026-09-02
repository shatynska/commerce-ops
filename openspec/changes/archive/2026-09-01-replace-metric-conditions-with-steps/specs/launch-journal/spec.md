## ADDED Requirements

### Requirement: The journal covers every accepted launch command

The system SHALL append exactly one journal entry for each command the launch context accepts, against the launch that command targeted:

- a launch started,
- a step outcome recorded — non-terminal outcomes included, and whatever source recorded it,
- a gate approval recorded — a rejecting decision as much as an approving one,
- a gate opened,
- a graduation,
- a launch date moved.

A graduating advance appends one entry, and that entry SHALL name the graduation rather than only the gate that opened.

Coverage SHALL NOT depend on the occurrence having produced an event: recording an approval and recording a non-terminal step outcome each produce none, and each is journaled all the same.

#### Scenario: A started launch is journaled

- **WHEN** a launch is started
- **THEN** one entry is appended against that launch, naming the start

#### Scenario: A recorded step outcome is journaled

- **WHEN** a terminal outcome is recorded for a step
- **THEN** one entry is appended naming the step and the outcome recorded

#### Scenario: A non-terminal step outcome is journaled too

- **WHEN** an outcome that produces no event — `InProgress` — is recorded for a step
- **THEN** one entry is appended naming the step and that outcome

#### Scenario: An outcome recorded from any source is journaled alike

- **WHEN** a step outcome is recorded with source `clickup`, and another with source `automated`
- **THEN** an entry is appended for each, naming the source that recorded it

#### Scenario: A recorded approval is journaled

- **WHEN** an approving decision is recorded on a gate
- **THEN** one entry is appended naming the gate, the decision and the approver

#### Scenario: A rejecting approval is journaled too

- **WHEN** a rejecting decision is recorded on a gate
- **THEN** one entry is appended naming that the decision was rejecting

#### Scenario: A metric step's outcome is journaled as a step outcome

- **WHEN** an outcome is recorded for a blocking step declaring a metric identifier
- **THEN** one entry is appended naming the step and the outcome, with no kind of its own for the metric

#### Scenario: An opened gate is journaled

- **WHEN** an advance opens a gate short of `graduated`
- **THEN** one entry is appended naming the gate that opened

#### Scenario: A graduation is journaled as a graduation

- **WHEN** an advance opens `graduated`
- **THEN** one entry is appended naming the graduation, the posture the approver chose and the approver

#### Scenario: A moved launch date is journaled

- **WHEN** a launch date is moved
- **THEN** one entry is appended naming the previous date and the new one

## MODIFIED Requirements

### Requirement: An entry carries the labels the occurrence concerned, captured when it happened

An entry SHALL carry, alongside the identifier of whatever the occurrence concerned, the label that thing bore at the moment it occurred: for a step, the name the served playbook gave it; for a gate, its identifier, which is the whole of its label.

A later change to the playbook SHALL NOT change what an already-appended entry carries. An entry SHALL stay readable after the served playbook has moved on — a step renamed, or retired, after the entry was appended is still named in that entry as it was named then.

**A refused advance's unsatisfied conditions are the one exception.** They SHALL be stored as the launch domain composes them — a list of condition names — and a name in that list MAY identify a step by its identifier rather than by the name the served playbook gave it. The list is still structure rather than prose: it is condition names, stored as a list, never a sentence about them. The exception exists because carrying names there would mean reshaping the occurrence the domain already raises to describe a blocked advance, which this change deliberately leaves alone; it is recorded in `design.md` — Decision 7, together with what a later change would do instead.

#### Scenario: An entry names the step as well as identifying it

- **WHEN** a step outcome is recorded
- **THEN** the entry carries both the step's identifier and the name the served playbook gave that step

#### Scenario: A step renamed later does not change an appended entry

- **WHEN** a step is renamed after an entry naming it was appended
- **THEN** the entry still carries the name the step bore when the entry was appended

#### Scenario: A step retired later still reads by name

- **WHEN** a step is retired after an entry naming it was appended
- **THEN** the entry still names that step, rather than reporting only its identifier

#### Scenario: A refused advance's conditions are stored as the domain names them

- **WHEN** an advance is refused because a blocking step is unresolved, and its entry is inspected as stored
- **THEN** the entry carries that condition as the domain's own condition name, which identifies the step by identifier, and carries it as one item of a list rather than as a sentence

#### Scenario: A metric step is labelled by its name

- **WHEN** an entry is appended for a blocking step declaring a metric identifier
- **THEN** its label is the name the served playbook gave that step, exactly as for any other step

### Requirement: One launch's journal is readable, most recent first

The system SHALL report one launch's journal, given the product identifier the launch references, with the most recent entry first — ordered by the moment each entry names, entries naming the same moment reported in the reverse of the order they were appended, so that the later of two simultaneous entries is reported first.

Each reported entry SHALL name when it occurred, and SHALL carry every other fact the occurrence recorded as its own field — never composed into a sentence about them. This extends "An entry stores structure, never rendered prose" (below) to the read side as well as the stored side: an earlier revision of this requirement composed a `what` sentence and a `cause` sentence at read time; `raw-out-the-journal-columns` removed both, so that a reader wanting to know what happened reads the facts directly rather than a sentence built from them.

The facts every entry carries: `kind`, `subject` (the occurrence's subject label where it has one, its subject identifier otherwise), `source`, and `actor` — each `None` where the occurrence carries none, rather than a placeholder value. Beyond these, an entry carries the fact or facts that distinguish its kind, read straight from the occurrence's stored details and named for what they are rather than folded into any other field: `playbook_version` (a start), `outcome` and `reason` (a step outcome), `evidence` (a step outcome), `decision` (an approval), `posture` (a graduating approval, or a graduation), `standing_at` (a gate opened), `previous_date` and `new_date` (a moved launch date), and `unsatisfied` (a refusal — a list of condition names, not a sentence about them, per the exception the requirement below already carries). Each is `None` (or, for `unsatisfied`, empty) on every entry whose kind does not populate it.

Each reported entry SHALL additionally carry a short label naming its kind, and a category, both composed at read time from the stored occurrence rather than stored — the one exception to "never composed": a label and a category are not sentences, and composing them is what lets an improved label or a corrected category reach every already-appended entry of that kind, the same reasoning "Improved wording reaches entries already appended" (below) states for the wording this revision removes. The label SHALL be one of a fixed set, one per journal kind. The category SHALL be one of a fixed set of four — progression, judgment, blocked, admin — assigned per kind, except for two kinds whose category depends on a fact the occurrence carries, so that a negative outcome reads distinctly from ordinary progress:

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

#### Scenario: An entry reports its distinguishing facts as their own fields

- **WHEN** a launch whose journal holds a step outcome recorded by a named person from a named source is read
- **THEN** that entry carries the moment it occurred as `when`, that person as `actor`, that source as `source`, and the recorded outcome and its reason as `outcome` and `reason`, each in its own field

#### Scenario: A kind's distinguishing facts are absent from an entry of another kind

- **WHEN** an entry of a kind that carries no `outcome`, `reason`, `decision`, `standing_at`, `posture`, `playbook_version`, `previous_date` or `new_date` is read
- **THEN** each of those fields is `None` on that entry, rather than an empty string or a placeholder

#### Scenario: An entry reports a label naming its kind

- **WHEN** any entry is read
- **THEN** it carries a short label naming its kind, drawn from the fixed set of labels rather than the raw kind string

#### Scenario: An entry reports its subject, source and actor as raw facts

- **WHEN** a launch whose journal holds a step outcome recorded by a named person from a named source, naming a step as its subject, is read
- **THEN** that entry carries the step's name as `subject`, the source as `source`, and the recorder as `actor`, each unworded

#### Scenario: An occurrence naming no subject, source or actor reports each as absent

- **WHEN** an entry for an occurrence that names none of a subject, a source or an actor is read
- **THEN** its `subject`, `source` and `actor` are each `None`, rather than a placeholder value

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

## REMOVED Requirements

### Requirement: Every accepted launch command appends exactly one journal entry

**Reason**: The set of commands the launch context accepts no longer includes attesting a metric condition, so a requirement enumerating that command among them enumerates one that cannot be issued. Everything else it stated is carried unchanged by *The journal covers every accepted launch command*, which replaces it.

**Migration**: None for any entry already appended — no `metric-attested` entry was ever written, the command having had no surface. Every other kind is journaled exactly as before.
