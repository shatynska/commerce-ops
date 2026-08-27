## MODIFIED Requirements

### Requirement: Each launch is projected into its own ClickUp list

The system SHALL maintain one ClickUp list per launch, created inside a configured parent folder and named with the product's name and SKU as the catalog records them (the product identifier itself is opaque and never parsed for meaning), and SHALL record the association between the launch and its list. A launch that has reached its final gate (`graduated`) SHALL NOT be projected or reconciled. When the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped.

Before a launch's projection uses a recorded list, once per pass, the system SHALL establish from ClickUp that the list still exists. A launch whose recorded list still exists SHALL NOT get a second one.

A launch whose recorded list has been deleted in ClickUp SHALL be given a new one, and its task mappings SHALL be discarded together with the recorded list they belonged to, as one indivisible act: either the launch is left recorded against its old list with its mappings intact, or it is recorded against the new list with the discard applied. The indivisibility is of the *record*; a replacement list created in ClickUp before the record is written may be left with nothing naming it, and reclaiming such a list is not undertaken here. A task mapping names a task inside a particular list, so a mapping outliving that list records something the system knows to be untrue.

**A mapping SHALL be exempt from that discard, and SHALL stand, where the playbook still defines its step and that step's recorded outcome is one that settles work** — `Satisfied`, `NotApplicable` or `Refused` — whether or not the step is one the launch is currently held to. Whether the outcome settles work SHALL be judged without reference to the step's current hazard: an outcome that settled the work when it was recorded is not unsettled by the step being re-authored afterwards, and the work does not become unfinished because the rules for finishing it changed. Such a mapping is not a stale record but a working one: it is what tells the projection that the step's work is finished, so that discarding it would re-project completed work as a fresh open task in the replacement list. The exemption reaches steps the launch is not currently held to because a step can leave the served set and return to it; its finished work must survive the round trip. A mapping whose step the playbook no longer defines at all SHALL be discarded with the rest, since nothing can re-project a step that is not defined. No sanctioned operation produces that state — a step is retired, never deleted, and a retired step is still defined — so this clause is defensive, covering mappings older than the playbook's move into Postgres and any left by an unsanctioned edit.

This exemption is stated in terms of the launch's own state — whether the playbook defines the step, and whether its work is finished — and not in terms of how the projection loop reaches it.

Replacing a list is the one thing that removes the mapping of a step the launch is no longer held to. A departed step whose work is unsettled loses its mapping here, notwithstanding the general rule that such a step leaves the completion loop with its mapping and task left standing — the task it named died with the list, so nothing stands to leave standing. Should that step return, it is projected afresh and observed afresh, so nothing that happened while it was away is replayed as a transition.

The discard is an obligation in its own right and SHALL NOT be relied upon as the means by which steps re-project; a step whose work is unfinished re-projects because its task is absent from the launch's list, whether or not its mapping was discarded first.

The deleted condition SHALL be established from what ClickUp reports about the list itself, and SHALL NOT be inferred from any failed request — neither from a failed write against the list nor from a failed read of it. A request failing with "not found" is also what a transient fault, a withdrawn permission or a mistaken identifier looks like, whereas ClickUp reporting the list as deleted is ClickUp stating the fact. Where the system cannot establish a recorded list's state, the launch SHALL fail its pass rather than be healed on the strength of the failure; a launch so failed is contained as any failing launch is.

Completions already recorded against the deleted list's tasks SHALL stand. What a deletion ends is the ability to observe *further* transitions on tasks that no longer exist; the re-projected tasks begin unobserved, exactly as newly projected tasks do.

A pass that stands down because the served playbook cannot hold a launch SHALL create nothing and write nothing, as the stand-down requirement specifies; that is a decline rather than the silent skip this requirement forbids, and it is recorded as a successful run.

#### Scenario: A launch without a list gets one

- **WHEN** the reconciliation pass runs and an active launch has no recorded ClickUp list
- **THEN** a list is created in the configured folder, named with the product's catalog name and SKU
- **AND** the association between the launch and the created list is recorded

#### Scenario: An existing list is not recreated

- **WHEN** the reconciliation pass runs, the launch already has a recorded list, and ClickUp reports that list as existing
- **THEN** no new list is created

#### Scenario: A launch whose list was deleted gets a new one

- **WHEN** the reconciliation pass runs and ClickUp reports the launch's recorded list as deleted
- **THEN** a new list is created in the configured folder, named with the product's catalog name and SKU as any launch list is
- **AND** the launch is recorded against the new list
- **AND** the launch's task mappings are discarded, except those for playbook-defined steps whose recorded outcome is terminal

#### Scenario: The replacement and the discard cannot come apart

- **WHEN** the reconciliation pass replaces a launch's deleted list and the write of that replacement does not complete
- **THEN** the launch is left recorded against its old list with its task mappings intact

#### Scenario: Steps re-project into the replacement list

- **WHEN** a launch's deleted list has been replaced and the reconciliation pass runs again
- **THEN** every projectable step whose work is unfinished has a task in the new list
- **AND** each such task begins unobserved, so its first completion is recorded as a transition

#### Scenario: Finished work is not re-projected into the replacement list

- **WHEN** a launch's deleted list is replaced and a projectable step's recorded outcome is already terminal
- **THEN** no task is created for that step in the new list

#### Scenario: Finished work of a step the launch is not held to survives the replacement

- **WHEN** a launch's deleted list is replaced, a step's recorded outcome is terminal, and the playbook defines that step but the launch is not currently held to it
- **THEN** its mapping is not discarded
- **AND** no task is created for that step should the launch later be held to it again

#### Scenario: A mapping for an undefined step is discarded

- **WHEN** a launch's deleted list is replaced and a mapping names a step the playbook no longer defines
- **THEN** that mapping is discarded with the rest

#### Scenario: Outcomes recorded before the deletion are kept

- **WHEN** a launch's deleted list is replaced and steps had outcomes recorded from tasks in that list
- **THEN** those recorded outcomes are unchanged

#### Scenario: A failed write is not read as a deletion

- **WHEN** the reconciliation pass runs and a write against the launch's list fails with "not found" while ClickUp does not report the list as deleted
- **THEN** no new list is created and no task mapping is discarded

#### Scenario: A list whose state cannot be established is not healed

- **WHEN** the reconciliation pass cannot establish the state of a launch's recorded list, because the request for it fails
- **THEN** no new list is created and no task mapping is discarded
- **AND** that launch's pass fails, rather than the failure being read as a deletion

#### Scenario: A graduated launch is left alone

- **WHEN** the reconciliation pass runs and a launch has reached `graduated`
- **THEN** no list or task is created or updated for it and no outcome is recorded from it
- **AND** its recorded list is not checked for existence

#### Scenario: Missing folder configuration fails the run

- **WHEN** the reconciliation pass runs, an active launch needs a list, and no parent folder is configured
- **THEN** the pass reports failure rather than skipping the launch silently
- **AND** this holds equally for a launch needing a list because ClickUp reports its recorded one deleted, which is not given its deleted list's identifier back
