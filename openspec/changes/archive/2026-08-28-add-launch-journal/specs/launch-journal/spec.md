## Purpose

Keeps an append-only record of what happened to one launch — every command the launch context accepted, and every advance it refused — retained independently of the launch state that produced it, so that a launch's history stays readable after that state has moved on.

## ADDED Requirements

### Requirement: Every accepted launch command appends exactly one journal entry

The system SHALL append exactly one journal entry for each command the launch context accepts, against the launch that command targeted:

- a launch started,
- a step outcome recorded — non-terminal outcomes included, and whatever source recorded it,
- a metric condition attested,
- a gate approval recorded — a rejecting decision as much as an approving one,
- a gate opened,
- a graduation,
- a launch date moved.

A graduating advance appends one entry, and that entry SHALL name the graduation rather than only the gate that opened.

Coverage SHALL NOT depend on the occurrence having produced an event: recording an approval, recording an attestation and recording a non-terminal step outcome each produce none, and each is journaled all the same.

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

#### Scenario: A recorded metric attestation is journaled

- **WHEN** a metric condition is attested on a gate
- **THEN** one entry is appended naming the gate, the metric condition and the attester

#### Scenario: An opened gate is journaled

- **WHEN** an advance opens a gate short of `graduated`
- **THEN** one entry is appended naming the gate that opened

#### Scenario: A graduation is journaled as a graduation

- **WHEN** an advance opens `graduated`
- **THEN** one entry is appended naming the graduation, the posture the approver chose and the approver

#### Scenario: A moved launch date is journaled

- **WHEN** a launch date is moved
- **THEN** one entry is appended naming the previous date and the new one

### Requirement: A refused advance is journaled with the conditions that blocked it

The system SHALL append a journal entry when an advance is refused, naming the gate that did not open and every condition that was unsatisfied at that moment. The refusal SHALL still fail exactly as it does without a journal — the same rejection, carrying the same unsatisfied conditions.

Unsatisfied conditions are recomputed from current state and are therefore unrecoverable once satisfied; the entry is the only record that they ever blocked an advance, and when.

#### Scenario: A refused advance is journaled with its unsatisfied conditions

- **WHEN** an advance is attempted on a gate holding two unsatisfied conditions
- **THEN** one entry is appended naming that gate and both conditions

#### Scenario: A refused advance still fails

- **WHEN** an advance is refused and its entry is appended
- **THEN** the command fails with the same rejection, naming the same unsatisfied conditions, and the launch's current gate is unchanged

#### Scenario: A condition satisfied later leaves the entry standing

- **WHEN** a condition that blocked an earlier advance is satisfied and the gate later opens
- **THEN** the entry recording the refusal still names that condition as having blocked the advance

### Requirement: An entry carries the labels the occurrence concerned, captured when it happened

An entry SHALL carry, alongside the identifier of whatever the occurrence concerned, the label that thing bore at the moment it occurred: for a step, the name the served playbook gave it; for a metric condition, the condition's threshold text; for a gate, its identifier, which is the whole of its label.

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

### Requirement: An entry stores structure, never rendered prose

An entry SHALL store the occurrence as facts — its kind, the moment it names, the identifiers and labels it concerned, the attribution it carried, and the values that distinguish it from another occurrence of the same kind — and SHALL NOT store a composed sentence about it.

Wording SHALL be composed when the journal is read, from what the entry carries. Improving how an occurrence reads SHALL therefore improve every entry of that kind already appended, rather than leaving history phrased the way it was first written.

#### Scenario: An entry is stored as facts

- **WHEN** an entry is appended and inspected as stored
- **THEN** its kind, the moment it names, the identifiers and labels it concerned and its distinguishing values are each carried separately, and no composed sentence is among them

#### Scenario: Improved wording reaches entries already appended

- **WHEN** the wording composed for a kind of occurrence changes, and a launch's journal holding an entry of that kind from before the change is read
- **THEN** that entry reads with the new wording

### Requirement: Entries are appended, never replaced or deleted

A second occurrence of the same kind against the same subject SHALL append a second entry; it SHALL NOT replace, amend or remove the first. No command the launch context accepts SHALL remove or amend an entry.

This is the whole difference between the journal and the state it records: a later step outcome replaces the stored outcome, and appends beside the entry recording the earlier one.

#### Scenario: A second recording on the same step appends rather than replaces

- **WHEN** a step recorded once is recorded again
- **THEN** the journal holds two entries for that step, both readable, and neither one altered by the other

#### Scenario: A replaced step outcome leaves the earlier entry standing

- **WHEN** a step recorded `Satisfied` is later recorded `Blocked`, replacing the stored outcome
- **THEN** the journal still reports the earlier entry naming the `Satisfied` recording

### Requirement: A failed append never fails the command it records, nor disturbs its work

Where appending an entry fails, the command it records SHALL complete exactly as it would have without a journal: its own persistence stands, its returned events are unchanged, its failure modes are unchanged, and every step of its work that follows the append SHALL still be performed — most sharply the catalog steady-state stamp a graduating advance performs after the advance is persisted.

Containment SHALL therefore extend beyond catching the failure to leaving the command able to finish: a failed append SHALL NOT leave the command's persistence unusable for the work that follows it.

A failed append SHALL be reported to the application log at error severity, naming the launch and the occurrence that went unrecorded.

#### Scenario: A failed append leaves the command's own work standing

- **WHEN** a step outcome is recorded and appending its entry fails
- **THEN** the command reports success, and reading the launch back reports the outcome as recorded

#### Scenario: A failed append does not prevent the graduation stamp

- **WHEN** an advance opens `graduated` and appending its entry fails
- **THEN** the advance stands persisted and the catalog product is still stamped steady-state with the posture the approver chose

#### Scenario: A failed append on a refused advance leaves the refusal unchanged

- **WHEN** an advance is refused and appending its entry fails
- **THEN** the command fails with the same rejection, naming the same unsatisfied conditions

#### Scenario: A failed append is reported

- **WHEN** appending an entry fails
- **THEN** the failure is reported to the application log at error severity, naming the launch and the occurrence that went unrecorded

### Requirement: One launch's journal is readable, most recent first

The system SHALL report one launch's journal, given the product identifier the launch references, with the most recent entry first — ordered by the moment each entry names, entries naming the same moment reported in the reverse of the order they were appended, so that the later of two simultaneous entries is reported first.

Each reported entry SHALL name what occurred, when it occurred, and what caused it. What caused it is the person and the source where the occurrence names one — the recorder of a step outcome, the approver of a decision, the attester of a metric condition — and the command that produced it where the occurrence names nobody.

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

#### Scenario: An out-of-scope launch reports an empty journal

- **WHEN** a launch's journal is read on the behalf of a caller whose scope does not permit that product
- **THEN** an empty journal is reported, exactly as for a launch with nothing recorded

#### Scenario: A launch with nothing recorded reports an empty journal

- **WHEN** the journal of a launch that has nothing recorded is read — the state every launch predating the journal is in
- **THEN** an empty journal is reported, rather than an error

#### Scenario: A product with no launch record reports an empty journal

- **WHEN** the journal is read for a product identifier that has no launch record at all
- **THEN** an empty journal is reported, indistinguishable from that of a permitted launch with nothing recorded, rather than an error

### Requirement: A launch's journal is retained for the life of the launch record

A launch's journal SHALL outlive every change to the state that produced it — a replaced step outcome, a reopened question, a gate that has since opened — and SHALL be removed only when the launch record it belongs to is itself removed.

#### Scenario: The journal outlives the state it records

- **WHEN** every recorded step outcome of a launch has been replaced by a later recording
- **THEN** the journal still reports an entry for each of the earlier recordings

#### Scenario: Removing the launch record removes its journal

- **WHEN** a launch record is removed
- **THEN** its journal entries are removed with it, and no entry is left referencing a launch that no longer exists
