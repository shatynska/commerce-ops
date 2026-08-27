## ADDED Requirements

### Requirement: A projected task carries its step's gate and discipline as Custom Field values

The system SHALL record, on each projected task, the gate the step belongs to and the discipline that owns it, as values on two ClickUp Custom Fields, so that a launch list can be grouped, filtered and **ordered** along the two divisions the playbook is built on. Ordering is what distinguishes this from a label: the gates are a sequence, and a representation that cannot be sorted into that sequence states the gate without stating where in the launch it sits.

The two fields SHALL be identified by configured field identifiers rather than by their names, so that renaming a field in ClickUp does not detach the system from it. The configured identifier is the whole of what names the field: the system SHALL NOT search for a field by name, and SHALL NOT treat a field whose name it recognises as the configured one.

A field SHALL be **resolved** before it is written: the system reads the field's definition and matches the step's gate identifier, or its discipline value, against the field's declared options by name, writing the option the match names. The match SHALL be exact on the identifier string — the gate identifiers and discipline values are the ones the playbook and the shared vocabulary already fix, so no second naming scheme has to be kept true to the first, and a hand-typed option differing from one by case, spacing or wording is a configuration gap rather than a match.

The system SHALL NOT create either field, change its type, or add, remove, reorder or rename any of its options. The fields are configured by hand, and the system's whole relationship to their configuration is to read it and to report on it.

**Each field is configured independently.** A field's identifier is **not configured** when it is absent. An identifier that is present but **empty** SHALL NOT be treated as absent: it SHALL be reported as a configuration gap of its own, naming that field as configured with no value. Absence is how a deployment declines a field, and it is expressed by not setting the variable; an empty value is what a deployment that meant to opt in produces when its configuration is rendered wrongly, and treating that as a decline would answer a mistake with silence. This repository has already lost a deployment to exactly that shape.

Where a field's identifier is not configured, the system SHALL write no value for that field and SHALL report nothing about it — a deployment that names no field has declined that field rather than misconfigured it. The other field SHALL be unaffected: a deployment configuring the gate field alone records gates, reports on the gate field, and says nothing whatever about discipline. Silence therefore means "not asked for" and a report means "asked for and broken", for each field separately.

Carrying the discipline as a Custom Field does not reopen the task **name**, which SHALL continue to exclude it as the projection requirement specifies. That exclusion rests on name width — a single line a reader scans, where restating the discipline costs the wording the name exists to surface — and a field value spends none of it.

A task's values SHALL be set **after** the task is created, never inside the create call itself. Carrying them inside the create would save two requests per created task and would put them on the path that brings a step's work into being, where a value the task system refuses costs the step its whole task — which the guarantee below forbids save on the one path it names. The saving is two requests per created task, paid once each; the price is a failure path on the create that this requirement would then have to qualify its own guarantee around. The system SHALL set either value on a task that does not already carry it — a newly created one included, so that tasks projected before this requirement existed gain their values rather than the behaviour reaching only launches started afterwards — the same obligation the assignee requirement already carries, and for the same reason.

Where a task's value for either field differs from the one its step resolves to, the system SHALL correct it. This is deliberately unlike the name, the body and the assignees, which a person may edit and which no pass overwrites: those are things a person may legitimately mean, whereas each of these two fields is single-valued and wholly determined by the step, so a divergence is drift and there is nothing a person could mean by it that the step does not already say. Correcting it is what allows a step moved to a different gate to reach its task, which the tag representation this replaces could not do — **wherever the step's gate resolves to an option**. Where it does not, the task keeps the value it has: writing an approximation would state something the playbook does not say, and clearing the value would state nothing where something true was standing. Such a task states a gate that is no longer its step's for as long as the gap lasts, which is the predecessor's own accepted defect surviving inside the gap and no further; the gap is what is reported, and repairing it corrects the tasks on the next pass.

Recording these values SHALL follow the projection it belongs to and never run ahead of it. A task whose step has left the projection SHALL NOT be given either value, exactly as *A step that is not active leaves the loop* specifies and on every ground that requirement names — the step is not `active`, its kind is no longer `human`, or it carries the `prohibited-tactic` hazard. That requirement is referenced rather than paraphrased deliberately: it states that projection turns on three fields and that "a rule naming fewer would leave the rest undefined", so restating a subset here would reintroduce exactly the gap it was written to close. A step the served playbook does not define at all is likewise never given a value, on the projection requirement's own ground. No value is written while the passes have stood down, for the reason the stand-down requirement already gives. A launch that has reached `graduated` is not visited by any pass at all, as *Each launch is projected into its own ClickUp list* specifies, so its tasks are never given values and never backfilled.

**No value SHALL be written for a field the configuration check has found in a gap of the kinds that withhold writes** — a field whose identifier is present but empty, a field the folder does not include, a field the read could not interpret, a field of the wrong type, a field declaring no options, or a field declaring more than one option named for the same gate, or for the same discipline, as the gap definition scopes it. The last is included for the reason that definition gives: where two options share a name, "the option the match names" is not a single option, so any write picks one arbitrarily, and a pick that is not stable across passes makes every pass disagree with the task and write again — the standing write storm the representation rule exists to prevent, arriving by another door. For an absent or optionless field nothing could resolve in any case; for a wrong-typed field that nonetheless declares matching options, resolution *would* succeed, and writing anyway would send a value to a field whose write behaviour the system has just established it did not intend. The gap report is the whole of the response, and a per-task record of the same cause is exactly the once-per-task noise the check exists to replace.

No Custom Field failure SHALL fail the pass, and the guarantee carries exactly one qualification, stated in the suppression clause below: a fault in this concern SHALL cost the field values and nothing else — never the projection of a launch's work, and never the completion intake that travels on the same pass. This holds across every path this concern touches, and each is closed by its own rule rather than by assertion: nothing about these two fields reaches the call that creates a task; the sole exception is a shared store this concern could not restore, which the suppression clause below states and hands to *One launch's failure does not stop the other launches being converged*; the folder read's failure is absorbed by the reachability clause below; the read of a list's tasks is required to be total, so no field value can stop it and through it a launch; the record that suppresses repeated reports and the delivery of the report itself are each covered by their own clause below; and a per-task write failure is stepped over. A path added to this concern later joins this rule rather than sitting outside it. Where setting a value on a task fails, the pass SHALL continue, SHALL still attempt the task's other field, and SHALL report the omission as a warning-level application log record naming the step, the field and the task. Where a step's gate or discipline matches no option the field declares, the system SHALL write nothing for that field on that task rather than writing an approximation, and the gap SHALL be reported by the configuration requirement below rather than once per task.

This requirement makes no claim about the run's own outcome. Whether a run is recorded as succeeded or failed is settled by *One launch's failure does not stop the other launches being converged* and by the stand-down requirement; what is required here is only that no fault of this concern is among the things that make a run fail.

#### Scenario: A newly created task is given both values

- **WHEN** a task is projected for an `active` `human` step and both fields are configured and resolve
- **THEN** the create call carries no Custom Field value
- **AND** the task is then given the option matching the step's gate on the gate field, and the option matching its discipline on the discipline field

#### Scenario: A field fault cannot cost a step its task

- **WHEN** every write of a Custom Field value fails for a step being projected for the first time
- **THEN** the task exists and carries its name, body, assignees and due date
- **AND** nothing about the failure causes the run to be recorded as failed

#### Scenario: No value is written to a field found in a gap

- **WHEN** a pass runs and the gate field is present and declares an option for every gate but is not of the type whose values the system writes
- **THEN** no gate value is written on any task
- **AND** the gap is reported once for the pass rather than once per task

#### Scenario: A task projected before the fields existed gains its values

- **WHEN** a pass runs over a mapped task that carries neither field's value and whose step resolves both
- **THEN** the task is given both values

#### Scenario: A task already carrying its values is left alone

- **WHEN** a pass runs over a mapped task already carrying the values its step resolves to
- **THEN** no Custom Field write is sent for that task
- **AND** a task in the same launch whose values are absent is still given them

#### Scenario: A re-gated step's task is corrected

- **WHEN** a step's gate is changed by authoring and a pass runs over its mapped task, which still carries the option for the former gate
- **THEN** the task's gate field is set to the option matching the step's current gate

#### Scenario: A re-gated step whose new gate has no option keeps its former value

- **WHEN** a step's gate is changed to one the gate field declares no option for, and a pass runs over its mapped task
- **THEN** the task's gate field is left carrying what it has
- **AND** the missing option is reported as a configuration gap

#### Scenario: An option differing only in wording is not a match

- **WHEN** the gate field declares an option whose name differs from a gate identifier by case or spacing
- **THEN** no task is given that option for that gate
- **AND** the gate is reported as having no matching option

#### Scenario: A step that is not projected is given no values

- **WHEN** a pass runs and a step is not `active`, or is not `human`, or carries the `prohibited-tactic` hazard, or is not defined by the served playbook
- **THEN** no Custom Field value is written for it
- **AND** a projected step in the same launch is still given both of its values

#### Scenario: A deployment configuring no field writes none

- **WHEN** a pass runs in a deployment that configures neither field identifier
- **THEN** every task is projected with its name, body, assignees and due date as usual
- **AND** no Custom Field value is written and no configuration report is made

#### Scenario: A field identifier configured but empty is a gap

- **WHEN** a pass runs in a deployment where a field's identifier is present but empty
- **THEN** that field is reported as configured with no value, rather than treated as declined
- **AND** no value is written for it

#### Scenario: A deployment configuring one field records only that one

- **WHEN** a pass runs in a deployment that configures the gate field's identifier and not the discipline field's
- **THEN** every task is given its gate value
- **AND** no discipline value is written, and nothing about the discipline field is reported

#### Scenario: A stood-down pass writes no value

- **WHEN** the passes stand down because the playbook cannot hold a launch
- **THEN** no Custom Field value is written on any task of any launch

#### Scenario: A field write that fails costs only that field

- **WHEN** setting the gate value on a task fails
- **THEN** the discipline value is still attempted for that task
- **AND** the pass continues over the remaining launches
- **AND** nothing about this fault causes the run to be recorded as failed
- **AND** the omission is reported as a warning-level log record naming the step, the field and the task

### Requirement: The Custom Field configuration is checked once per pass and a gap is reported without stopping the pass

The system SHALL check the configuration of the configured fields **once per pass, before any task is written**, by a single read of the Custom Fields available to the launches' folder. Checking once rather than per task is what makes the check complete: a gap in an option is a property of the configuration, identical for every task of every launch, and discovering it only where a task happens to need it would leave a gate whose steps are all resolved — or a launch not yet reached — unchecked, so a missing option for a late gate would stay invisible until a launch arrived at it.

**An empty field identifier SHALL be reported whether or not the folder's fields could be read**, since it is established by the configuration alone and needs no network at all. Where the read did not complete, or no launch folder is configured, the empty-identifier finding SHALL still be composed and reported while every other kind is withheld. This is deliberate: an empty identifier is the shape a mis-rendered deployment takes, it is exactly what this rule exists to catch mechanically, and withholding it behind a reachability fault would make the catch depend on the very service whose configuration is in question. A stand-down remains the exception, on the ground it already gives — a stood-down pass declines entirely.

The check of the folder's fields SHALL NOT be performed in any of three states, and in the first two nothing beyond the empty-identifier finding SHALL be reported; in the third — the stand-down — nothing SHALL be reported at all, that finding included, because a stood-down pass declines entirely rather than doing a reduced amount of work. The three states: where neither field identifier is configured, on the ground the projection requirement above gives; where no launch folder is configured, leaving *Each launch is projected into its own ClickUp list* the sole authority on that condition; and on a pass that has stood down, on the ground the stand-down requirement gives — a stood-down pass declines the whole pass and SHALL reach ClickUp for nothing at all, this check included. A standing gap therefore goes unreported for the duration of a stand-down, which is accepted: a stand-down is a deployment being set up, and the configuration it would report on is part of what is still being set up.

A **configuration gap** is any of the following. The first is assessed for a field whose identifier is present at all; the rest only for a field whose identifier is present and non-empty: a field identifier that is present but **empty**, reported as that field being configured with no value and never as the field being absent — the two call for different repairs, and reporting a rendering mistake as a missing field sends someone looking in the wrong place; a configured field identifier that the folder's Custom Fields do not include; a configured field the read reports as **uninterpretable**, reported as such and never as the field declaring no options — a field the client could not make sense of may declare eight options perfectly well, and telling someone to add options to a field that has them sends them to argue with their own screen; a configured field that is not a field declaring a single value drawn from an ordered set of options; a configured field that declares no options; a gate identifier in the playbook's fixed gate sequence that no option of the gate field names exactly; a discipline of the shared vocabulary that no option of the discipline field names exactly; **or a gate field whose options naming gates do not appear in the playbook's gate-sequence order**; the gate field declaring more than one option named for the same **gate**, or the discipline field more than one named for the same **discipline** — since "the option the match names" is then not a single option, and the order clause has no single position to judge. While a duplicate stands on the gate field, no order finding SHALL be composed for that field, and neither the order kind nor the order observed SHALL enter that field's identity — otherwise shuffling options while the duplicate stands would change the identity and re-report the same unrepaired duplicate: the order cannot be judged until the duplicate is resolved, and reporting an order that may be an artefact of the duplicate would name a repair that is not yet the right one. A duplicated name the system never resolves against is **not** a gap: it makes no write ambiguous, and reporting it would disable a field over a duplicate that has nothing to do with this system's use of it.

The order clause is not decoration. Ordering is the whole of why this change prefers a field to a tag, and every other clause here can pass while the order is wrong: a field naming all eight gates in the wrong sequence produces a view that reads as meaninglessly as the tags it replaced, silently and permanently. It is also the clause a repair is most likely to break — an option added by hand lands **last** in the declared order, so the obvious response to "gate `stock-ready` has no option" fixes the reported gap and introduces this one. Checking the order is what makes that visible instead of leaving a passing configuration that does not work.

Where a field is found in a gap of the kinds that **withhold option-level findings** — its identifier empty, the field absent, uninterpretable, of the wrong type, or declaring no options — no option-level or order finding SHALL be composed for that field. This set is not identical to the kinds that withhold writes above: the duplicate-name kind withholds writes, because no write against it is unambiguous, but does not withhold option-level findings, because such a field may still be missing options a repair must address. The fault at the level of the field itself is the one to repair, and the option-level findings it would generate are its consequences rather than separate repairs: an optionless field would otherwise be reported as declaring no options *and* as missing all eight gates, which is the narrowing the absent case already states. The duplicate-name kind is the exception and is handled in its own clause above, since a field carrying duplicates may still be missing options that a repair must address.

The report SHALL name every gap found, not the first, so that one repair round closes them all. It SHALL name what the field does declare where an expected option is missing, so a hand-typed mismatch is diagnosable rather than merely reported; and where the order is wrong it SHALL name the order found, so the repair is a reordering someone can perform rather than a fault they have to reconstruct.

**A failure to read the folder's Custom Fields, or a read whose result cannot be interpreted, is not a configuration gap and SHALL NOT be reported as one.** It is a reachability fault, and `runtime-configuration` requires the two to stay distinguishable — its *Checking Configuration Performs No Network Or Database Access* exists "so that a configuration fault is distinguishable from a reachability fault". Such a read SHALL yield no finding **derived from the folder's fields** — the empty-identifier finding is derived from the configuration alone and is unaffected, as the paragraph above requires — SHALL be reported as a warning-level application log record, and SHALL cost that pass its Custom Field values and nothing else: the pass SHALL continue and project, correct and reconcile every launch as it otherwise would. Reporting an unreachable ClickUp as two absent fields would deliver a false repair instruction and then suppress the truth behind it.

A cancellation or shutdown of the process running the pass is **not** among the failures any clause of this requirement or the one above absorbs. It SHALL be left to propagate, on the ground *One launch's failure does not stop the other launches being converged* already gives for the walk: a worker being stopped must stop, rather than swallowing the cancellation and finishing its work.

A configuration gap SHALL NOT stop the pass, SHALL NOT prevent any task from being projected or corrected, and SHALL NOT be among the things that cause a run to be recorded as failed. The pass SHALL continue and write every value that does resolve. Making a run fail for it would put a working deployment into retry and overdue reporting for a condition retrying cannot resolve — the reason `scheduled-jobs` already gives for the playbook stand-down — and a gap costs the field values and nothing else, which no launch's work depends on. A gap is likewise **not** a per-launch failure and SHALL NOT be contained, reported or counted as one: it is determined once, before the walk begins, in the same phase as readiness, and *One launch's failure does not stop the other launches being converged* governs the walk rather than this check. Where launches do fail on the same run, that requirement decides the run's outcome and this one takes nothing away from it.

A configuration gap SHALL be reported to the team's Slack channel, because a warning-level log record is not a place anybody looks and the entire purpose of the check is that a person acts on it. A **continuing** gap SHALL be reported once and not on every pass: the system SHALL retain that a report was delivered and SHALL NOT report the same gap again while it stands, so that a misconfiguration left in place over days produces one message rather than a wall of identical ones that trains the team to ignore the channel. Retention SHALL survive a restart of the process running the pass, for the same reason `scheduled-jobs` requires it of a continuing outage: a flood that resumes on every restart is not suppressed.

**A failure to read or write the record that suppresses repeated reports SHALL cost this pass its Custom Field values and nothing else, save on the one path this paragraph names.** It sits on the pre-walk path, ahead of every launch, so a fault there would otherwise abort a pass before any launch was projected — a fault wholly inside this concern costing the projection and the completion intake of every launch, which the guarantee above forbids. Otherwise — that is, wherever the store is left in a state in which the launches' writes can be recorded — such a failure SHALL be reported as a warning-level application log record and SHALL NOT fail the run, and the pass SHALL continue. Its effect on reporting depends on which access failed, and the two SHALL NOT be conflated. Where the **read** fails, the system cannot tell a standing gap from a new one, so it SHALL report no gap on that pass rather than risk repeating one already delivered. Where the **write** fails *after* a report has been delivered, the report has already gone out and cannot be recalled; the gap SHALL simply remain eligible to be reported again on the next pass. That is the same trade `scheduled-jobs` makes for a continuing outage — a report that could not be recorded leaves the work eligible rather than silenced — and it is preferred here for the same reason: a repeated message is a nuisance, while a gap silenced permanently is the failure this requirement exists to prevent. Where the store the record lives in is shared with the writes the pass makes for each launch, **any** failed access of that record — a read as much as a write, since either can leave a shared session unusable — SHALL oblige the pass to restore it to a state in which those writes can be recorded before the **first** launch is attempted, on the ground *One launch's failure does not stop the other launches being converged* already gives for recovery between launches: continuing against a store that cannot record is worse than not continuing. Where that restore itself fails, the walk SHALL end and the run SHALL be recorded as failed — on the ground *One launch's failure does not stop the other launches being converged* gives for a failed recovery **between launches**, which this requirement extends to the pre-walk restore. The extension is this requirement's own judgement rather than that one's mandate: the baseline clause is scoped to a recovery following a contained failure, and there is none before the first launch, but the consequence of continuing is identical — writing to ClickUp and losing the record of the write. This is the one path on which a fault of this concern costs more than the field values, and the guarantee above is qualified by exactly this much: the alternative is projecting launches whose writes cannot be recorded, which that requirement judges worse than stopping.

The record that suppresses further reports SHALL be written only after a report has been delivered successfully; a report that could not be delivered SHALL leave the gap eligible to be reported on the next pass, so that a transient failure of the reporting channel does not silence the gap permanently. A failure to deliver a report SHALL NOT be among the things that cause a run to be recorded as failed, and SHALL leave the pass to continue — delivery sits on the pre-walk path ahead of every launch, so a fault there must no more stop a launch being projected than a fault in the folder read does.

Suppression SHALL be lifted when the configuration is repaired, so that a gap appearing again afterwards is reported again. It SHALL likewise be lifted where the capability is **withdrawn** — on a pass performing no check because no field identifier is configured — since a deployment that has opted out has no standing gap for a report to be suppressed against, and leaving the record would let a later opt-in meet an unrepaired gap in silence.

A **stand-down** SHALL NOT lift it. A stand-down is not a withdrawal of the capability and says nothing about the configuration: lifting on one would make a deployment whose playbook moves in and out of readiness report the same unrepaired gap on every ready pass, which is the wall of identical messages this paragraph exists to forbid. The same applies to a pass that made no check because the folder read did not complete, which the reachability clause above already requires to clear nothing, and to write nothing beyond the identity of a report it did deliver, and to a pass that made none because no launch folder is configured — that state says nothing about the two fields either.

Where a report **was** delivered on such a pass — an empty-identifier finding, composed without any read — suppression SHALL be written under the identity of what was actually composed, exactly as for any other delivered report. Withholding it because the pass made no read would deliver that same message on every pass for as long as the reachability fault lasted, which is the flood this rule forbids. One consequence follows and is accepted: while reachability comes and goes with a gap standing across both fields, a pass that reads composes the whole finding and a pass that does not composes only the empty-identifier part, so the two identities differ and each transition reports once. That is bounded to one message per transition, and it is the right way round — a partial finding is genuinely different news from the whole one, and the alternative silences the whole finding behind the partial one. A gap whose **content** changes SHALL be reported again rather than suppressed as though it were the gap already reported, since it names a repair that has not been asked for yet. Content SHALL be taken over the **whole finding**, not over the missing options alone: per field, the **set** of gap kinds found — drawn from empty identifier, absent, uninterpretable, wrong type, optionless, duplicate option name, missing options, wrong order, and compared as a set, since a field may be found in more than one at once — together with the missing option names and the duplicated names — each compared as a **set**, so that two passes finding the same gap in a different enumeration order produce the same identity rather than re-reporting — and the gate-option order observed, which is compared as a sequence because its order is the finding — save while a duplicate stands on that field, where neither the order kind nor the order observed enters its identity, as the gap definition above requires. Seven of the eight gap kinds name nothing missing — only *missing options* does, so an identity taken over missing options alone would make a wrong-typed field and a wrongly-ordered one indistinguishable, and a deployment repairing the first into the second would meet silence where the whole point was a report.

#### Scenario: A missing option is reported before any task is written

- **WHEN** a pass runs and the gate field declares no option naming one of the playbook's gates
- **THEN** the gap is reported to Slack naming that gate and that field
- **AND** the report is made once for the pass, not once per task

#### Scenario: A gap does not stop the pass

- **WHEN** a pass runs with a configuration gap standing
- **THEN** every task is still projected and corrected, and every value that does resolve is still written
- **AND** nothing about the gap causes the run to be recorded as failed

#### Scenario: Every gap is named together

- **WHEN** a pass runs and two gates and one discipline have no matching option
- **THEN** the report names all three

#### Scenario: A configured field that is absent is a gap

- **WHEN** a pass runs and a configured field identifier is not among the folder's Custom Fields
- **THEN** the gap is reported as that field being absent, rather than as each of its options being missing

#### Scenario: A field declaring one option name twice is a gap

- **WHEN** a pass runs and the gate field declares two options both named for the same gate
- **THEN** the gap is reported, naming the duplicated name
- **AND** no value is written for that field on any task
- **AND** a gate field declaring two options under a name that is no gate at all is not a gap

#### Scenario: A field the read could not interpret is reported as such

- **WHEN** a pass runs and a configured field is reported by the read as uninterpretable
- **THEN** the gap names it as uninterpretable, not as declaring no options
- **AND** no value is written for that field on any task

#### Scenario: A configured field of the wrong type is a gap

- **WHEN** a pass runs and a configured field is present but is not of the type whose values the system writes
- **THEN** the gap is reported as that field being of the wrong type

#### Scenario: An empty identifier is reported even when ClickUp cannot be reached

- **WHEN** a pass runs with a field's identifier present but empty, and the read of the folder's Custom Fields does not complete
- **THEN** the empty identifier is reported
- **AND** nothing is reported about the other field's options, since they could not be read

#### Scenario: An unreachable ClickUp is not reported as a gap

- **WHEN** a pass runs with both identifiers configured and non-empty, and the read of the folder's Custom Fields does not complete
- **THEN** no configuration gap is reported to Slack
- **AND** no suppression is written or cleared
- **AND** the pass still projects, corrects and reconciles every launch, writing no Custom Field values

#### Scenario: An empty-identifier report on a read-less pass is suppressed like any other

- **WHEN** an empty identifier is reported on a pass whose folder read did not complete, and the next pass finds the same state
- **THEN** no second report is made

#### Scenario: A pass with no active launches still checks the configuration

- **WHEN** a pass runs, the playbook is ready, and no launch is active
- **THEN** the folder's Custom Fields are still read and a standing gap is still reported
- **AND** the check does not depend on any launch existing

#### Scenario: A failure of the suppression record costs only the field values

- **WHEN** the record that suppresses repeated reports cannot be read or written, and the store it lives in is left in a state where the launches' writes can still be recorded
- **THEN** every launch is still projected, corrected and reconciled
- **AND** nothing about the failure causes the run to be recorded as failed

#### Scenario: A failed suppression read and a failed write after delivery differ

- **WHEN** the suppression record cannot be **read** on a pass
- **THEN** no gap is reported on that pass, since a standing gap cannot be told from a new one
- **AND WHEN** on a later pass a gap is reported and the suppression record cannot then be **written**
- **THEN** the gap remains eligible and is reported again on the pass after

#### Scenario: A store this concern cannot restore ends the walk

- **WHEN** an access of the suppression record fails on a store shared with the launches' writes, and the restore of that store before the first launch itself fails
- **THEN** no launch is attempted
- **AND** the run is recorded as failed

#### Scenario: A pass with no launch folder configured reports only the empty identifier

- **WHEN** a pass runs with no launch folder configured and a field's identifier present but empty
- **THEN** no read of the folder's Custom Fields is made
- **AND** the empty identifier is reported and nothing else is
- **AND** no suppression is cleared

#### Scenario: An empty identifier is not reported during a stand-down

- **WHEN** the passes stand down because the playbook cannot hold a launch, and a field's identifier is present but empty
- **THEN** nothing is reported, the empty identifier included

#### Scenario: A stood-down pass performs no check

- **WHEN** the passes stand down because the playbook cannot hold a launch
- **THEN** no read of the folder's Custom Fields is made and no gap is reported

#### Scenario: Options declared out of the playbook's order are a gap

- **WHEN** a pass runs and the gate field declares an option naming every gate, but not in the playbook's gate-sequence order
- **THEN** the gap is reported, naming the order found
- **AND** it is reported even though no gate is missing an option

#### Scenario: Options the playbook does not know are not an order gap

- **WHEN** the gate field declares an option for every gate in playbook order, and additionally declares options naming no gate at all
- **THEN** no gap is reported
- **AND** the extra options are neither reported nor written to any task

#### Scenario: Missing gates are one gap, not two

- **WHEN** the gate field declares options for only some gates, and those it does declare are in playbook order relative to one another
- **THEN** the missing gates are reported
- **AND** no order gap is reported alongside them

#### Scenario: A duplicate withholds the order finding

- **WHEN** a pass runs and the gate field declares two options named for the same gate, and its gate options are also out of playbook order
- **THEN** the duplicate is reported
- **AND** no order gap is reported alongside it, since the order cannot be judged until the duplicate is resolved

#### Scenario: Reordering options during a duplicate does not re-report it

- **WHEN** a duplicate on the gate field is reported, and a later pass finds the same duplicate with that field's options reordered
- **THEN** no second report is made, since neither the order kind nor the order observed entered that field's identity

#### Scenario: A gap repaired into a different gap is reported again

- **WHEN** a wrong-typed gate field is reported, then replaced by a drop-down whose gate options are out of playbook order
- **THEN** the order gap is reported, rather than suppressed as the gap already reported

#### Scenario: A continuing gap is reported once

- **WHEN** a gap is reported on one pass and the same gap still stands on the next
- **THEN** no second report is made

#### Scenario: A stand-down does not lift suppression

- **WHEN** a gap is reported, a later pass stands down because the playbook cannot hold a launch, and a pass afterwards finds the same gap standing
- **THEN** no second report is made

#### Scenario: A continuing gap is reported once across a restart

- **WHEN** a gap is reported, the process running the pass restarts, and the same gap still stands
- **THEN** no second report is made

#### Scenario: An undelivered report leaves the gap eligible

- **WHEN** a gap is found and the report cannot be delivered to Slack
- **THEN** no suppression is retained and the gap is reported again on the next pass
- **AND** nothing about the failed delivery causes the run to be recorded as failed

#### Scenario: A repaired configuration lifts suppression

- **WHEN** a reported gap is repaired, a pass finds no gap, and a gap appears again afterwards
- **THEN** the later gap is reported

#### Scenario: Opting out lifts suppression

- **WHEN** a gap is reported, both field identifiers are then unconfigured, and a later deployment configures them again with the same gap standing
- **THEN** the gap is reported again

#### Scenario: A changed gap is reported again

- **WHEN** a gap is reported, and a later pass finds a gap naming a different set of missing options
- **THEN** the later gap is reported rather than suppressed

## MODIFIED Requirements

### Requirement: Human steps are projected as tasks carrying their name, description and assignees

The system SHALL project, into the launch's list, one ClickUp task per step of the served playbook whose kind is `human`, whose status is `active`, and whose hazard is not `prohibited-tactic`, and SHALL record the association between each step and its task. The served playbook is live, so a step activated after the launch started is projected on the next pass like any other. `automated` steps, steps that are not `active`, steps with the `prohibited-tactic` hazard, and gate metric conditions SHALL NOT be projected. A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's **name**, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a step's name happens to say — a name whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A projected task's body SHALL be the step's **description** where the step carries one. Where a step carries no description the system SHALL compose no body at all, and SHALL neither write nor rewrite the task's body — leaving whatever stands there. Composing an *empty* body instead would destroy work: a task projected before this change whose name was shortened carries the step's full former text in its body, written by the system and therefore matching its retained value, so a rule that rewrote it to empty would leave that task stating its work nowhere. The body is no longer a place the name overflows into: the step's own two fields map onto the task's two, which is what having them separate is for.

A projected task SHALL be assigned to the step's assignees, each resolved to the ClickUp user the roster records for that person. Assignment SHALL be reconciled on later passes as well as at creation, so that a step whose assignees change reaches its task, and so that tasks projected before steps had assignees stop being unowned — which is the problem this field exists to solve, and solving it only for new work would leave every in-flight launch as it is. The system SHALL retain, with the mapping, the assignees it last set, exactly as it retains the name and the body it last composed. A person's own assignment change SHALL be respected the way an edited name or body is: where a task's assignees differ from what the system last set, the system SHALL NOT overwrite them. A mapping holding no retained assignees — every mapping made before this change — SHALL be treated as having last been set to nobody, so a task the system left unassigned heals to its step's assignees while one somebody has already assigned is treated as person-edited and left alone. Assignees are the one *retained* field where that reading is right: an unassigned task is the failure this projection exists to fix, so silence there is the system's own doing rather than an edit worth preserving. The Custom Field rule does not qualify it, and for the opposite reason: a Custom Field is single-valued and wholly determined by the step, so a value differing from the step's is drift rather than a person's own meaning and is corrected (see *A projected task carries its step's gate and discipline as Custom Field values*). An assignee the roster carries without a ClickUp user id SHALL be skipped for assignment — the task is still created, still carries its remaining assignees, and the omission SHALL be reported as a warning-level application log record naming the step, the person and the task rather than silently dropped — the pass itself succeeds, since a failed run would hide a data gap behind a retry, and `scheduled-jobs` records only whether a run succeeded, so the run record is not where this can be carried.

A task's name and body SHALL be set when the task is created, and the system SHALL retain, with the mapping, the name and the body it last composed for the task. On a later pass, when the step's current composition differs from what is retained, the system SHALL rewrite each of the task's name and its body to the current composition **only while that field in ClickUp still carries exactly what the system last wrote for it** — a field still carrying the system's own words follows the step's current wording, so an authored edit reaches the tasks it describes. A field that differs from its retained value has been edited by a person and SHALL NOT be rewritten by any pass, ever: a task's name, and a note a person keeps in its body, are things a person may legitimately edit, and a pass that restored the authored wording would silently discard their edit. The two fields are guarded independently — a person's body note does not freeze the name, nor a renamed task its body. Whenever the system writes a name or a body, it SHALL update that field's retained value to what it wrote.

A mapping created before compositions were retained holds no retained values. On first observing such a task, the system SHALL adopt a field's current content as its retained value when it is exactly what the system would currently compose — an unedited legacy task starts healing — and SHALL otherwise leave the retained value absent and the field forever unrewritten, treating it as person-edited: where the system cannot tell an authored change from a person's edit, it preserves the person's.

Where the composed name would exceed the length the task system accepts, the name SHALL be shortened to fit, so that no step fails to project merely because its name is long. The shortened name SHALL consist of the step's name cut at its end, then `…` marking that it was cut, then ` · ` and the step's identifier in full: shortening SHALL preserve the identifier, since that is what makes the task traceable, and SHALL be visible as shortening rather than reading as the whole name. The name SHALL be cut to the longest leading portion that leaves the whole composed name within the limit, so that shortening surrenders no more of the wording than the limit requires. Shortening SHALL NOT move the surrendered text into the body: the body belongs to the description, and overwriting it with a fragment of the name would displace what an author wrote.

#### Scenario: A human step gets a task

- **WHEN** the reconciliation pass runs and an `active` `human` step of an active launch has no recorded task
- **THEN** a task named with the step's name, then ` · `, then its identifier is created in the launch's list
- **AND** the step's discipline is not appended as a further element of that name
- **AND** the association between the step and the created task is recorded

#### Scenario: A step's description becomes the task's body

- **WHEN** a task is projected for a step carrying a description
- **THEN** the task's body is that description
- **AND** a step carrying no description is projected with no body written at all, leaving whatever the task already holds

#### Scenario: A task is assigned to the step's people

- **WHEN** a task is projected for a step naming two assignees the roster records ClickUp user ids for
- **THEN** the created task is assigned to both of those ClickUp users

#### Scenario: An existing unowned task gains its step's assignees

- **WHEN** a pass runs over a task the system assigned to nobody and whose step now names an assignee
- **THEN** the task is assigned to that person

#### Scenario: A person's own assignment change is not overwritten

- **WHEN** a task's assignees have been changed in ClickUp from what the system last set, and a pass runs
- **THEN** the system leaves the task's assignees as they stand

#### Scenario: An assignee with no ClickUp account is reported, not silently dropped

- **WHEN** a task is projected for a step naming an assignee the roster carries without a ClickUp user id
- **THEN** the task is created and assigned to the step's remaining assignees, and the omission is reported

#### Scenario: A step activated mid-launch is projected

- **WHEN** a `human` step is activated after a launch started and the next pass runs
- **THEN** a task is created for it in the launch's list like any other step's

#### Scenario: A renamed task still resolves to its step

- **WHEN** a mapped task's name has been edited in ClickUp and the reconciliation pass runs
- **THEN** the task still resolves to its step through the recorded mapping

#### Scenario: An unedited task follows the step's current wording

- **WHEN** a step's name has been edited, the mapped task's name in ClickUp is still exactly the composition the system last wrote, and the pass runs
- **THEN** the task's name is rewritten to the step's current composition
- **AND** the retained composition is updated to what was written

#### Scenario: A person's body note survives a wording edit

- **WHEN** a person has edited a mapped task's body, the task's name still carries the system's retained composition, the step's name is edited, and the pass runs
- **THEN** the task's name is rewritten to the current composition
- **AND** the task's body is left exactly as the person wrote it

#### Scenario: An unedited legacy task starts healing

- **WHEN** a mapped task predating retained compositions is observed carrying exactly the name the system would currently compose
- **THEN** that name is adopted as the retained composition, and the task heals under the rules above thereafter

#### Scenario: An ambiguous legacy task is never rewritten

- **WHEN** a mapped task predating retained compositions is observed carrying a name that differs from the current composition
- **THEN** no retained composition is adopted and no pass ever rewrites that task's name

#### Scenario: An edited task name is never restored

- **WHEN** a mapped task's name has been edited in ClickUp, the step's name has since changed, and the reconciliation pass runs
- **THEN** the task keeps the name it has in ClickUp
- **AND** no update is sent for that task's name

#### Scenario: An over-long name is shortened rather than failing

- **WHEN** a task is projected for a step whose composed name exceeds the length the task system accepts
- **THEN** the task is created with a shortened name that fits, ending in `… · ` followed by the step's identifier in full
- **AND** no more of the name is surrendered than the limit requires
- **AND** the surrendered text is not written into the body

#### Scenario: An existing task is not recreated

- **WHEN** the reconciliation pass runs and a step already has a recorded task
- **THEN** no new task is created for that step

#### Scenario: A prohibited-tactic step is never projected

- **WHEN** the reconciliation pass runs and a step carries the `prohibited-tactic` hazard
- **THEN** no task is created for it, whatever its kind

#### Scenario: A deleted task for unfinished work is re-projected

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is not terminal
- **THEN** a new task is created for the step and the mapping is replaced with the new task

#### Scenario: A deleted task for finished work stays gone

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is terminal
- **THEN** no task is recreated for that step

#### Scenario: Automated steps are never projected

- **WHEN** the reconciliation pass runs and a step's kind is `automated`
- **THEN** no task is created for it, whether or not it needs confirmation

#### Scenario: A step that is not active is never projected

- **WHEN** the reconciliation pass runs and a `human` step's status is `draft`, `in-development` or `retired`
- **THEN** no task is created for it

## REMOVED Requirements

### Requirement: A projected task carries its step's gate and discipline as tags

**Reason**: Superseded by *A projected task carries its step's gate and discipline as Custom Field values*, which takes over the same subject and buys what the tag representation could not. A tag is an unordered member of an open vocabulary; the gates are a sequence fixed by the playbook, and tags sort alphabetically, so a launch list tagged with them could be filtered by gate but never ordered by it. Tags are additionally wanted for other characteristics of a task, which a vocabulary serving two purposes would make ambiguous. The single-valued field also retires two defects this requirement accepted: a step moved to a different gate has its task corrected rather than keeping a stale value wherever its new gate resolves to an option, and a value a person clears is restored on the next pass without the "never set" ambiguity a tag carried.

**Migration**: No data migration and no removal pass. The `gate:` and `discipline:` tags already written remain on their tasks and SHALL be left where they are — the system removed no tag under this requirement and removes none under its successor. They are cleared by hand where they are not wanted. Tasks are given their Custom Field values by the ordinary convergent pass, on the same backfill the tag requirement itself relied on, so no task needs to be visited specially. The client's tag operations are untouched and remain available for the characteristics tags are being freed for.
