## ADDED Requirements

### Requirement: A projected task carries its step's gate and discipline as tags

The system SHALL tag each projected task with the gate the step belongs to and the discipline that owns it, so that a launch list can be grouped and filtered along the two divisions the playbook is built on. The tags SHALL be named `gate:<gate identifier>` and `discipline:<discipline value>`, using the identifiers the playbook and the shared vocabulary already fix, so no second naming scheme has to be kept true to the first.

The prefixes are what the system owns. A tag carrying neither prefix belongs to whoever put it there: it SHALL NOT be written or removed by any pass, and SHALL have no bearing on what any pass does — a person labelling a task `urgent` or `waiting-on-supplier` is doing something this projection has no opinion about. A pass necessarily *reads* every tag a task carries, since telling an owned tag from a foreign one is what the prefix is for; reading is not the thing forbidden here.

Carrying the discipline as a tag does not reopen the task **name**, which SHALL continue to exclude it as the projection requirement specifies. That exclusion rests on name width — a single line a reader scans, where restating the discipline costs the wording the name exists to surface — and a tag spends none of it, while making the discipline filterable in a way a segment of the step identifier never was.

A task SHALL be created carrying both of its step's tags. A tag SHALL NOT be required to exist before it is used: attaching a tag name to a task creates it in that task's space where it is not already there, so the system SHALL NOT maintain, seed, or verify any tag vocabulary of its own, and SHALL read and write nothing about a launch's space. The only tag operations are the ones that put a tag on a task. On a later pass, the system SHALL add either tag to a mapped task that does not carry it, so that tasks projected before this requirement existed gain their tags rather than the behaviour reaching only launches started afterwards — the same obligation the assignee requirement already carries, and for the same reason: a projection that fixed only future work would leave every in-flight launch as it is.

The system SHALL NOT remove a tag from a task, and SHALL NOT replace one owned tag with another. Two consequences follow and are accepted rather than worked around:

- A step moved to a different gate keeps the gate tag it was projected with. Correcting it would require deciding whether a person's own retagging is preserved or overruled, which this requirement deliberately does not settle.
- A tag a person removes by hand stays removed only until the next pass, which adds it back, because the system retains nothing with which to tell "never added" from "added and then removed". A person therefore cannot keep a projected task untagged; that is the price of not policing tags in the other direction.

Tagging SHALL follow the projection it belongs to and never run ahead of it. A task whose step has left the projection SHALL NOT be tagged, exactly as *A step that is not active leaves the loop* specifies and on every ground that requirement names — the step is not `active`, its kind is no longer `human`, or it carries the `prohibited-tactic` hazard. That requirement is referenced rather than paraphrased deliberately: it states that projection turns on three fields and that "a rule naming fewer would leave the rest undefined", so restating a subset here would reintroduce exactly the gap it was written to close. A step the served playbook does not define at all is likewise never tagged, on the projection requirement's own ground rather than that one's — it is not a step of the launch's obligations, so nothing projects or tags it. No tag is written while the passes have stood down, for the reason the stand-down requirement already gives. A launch that has reached `graduated` is not visited by any pass at all, as *Each launch is projected into its own ClickUp list* specifies, so its tasks are never tagged and never backfilled.

No tagging failure SHALL fail the pass. Tagging follows the projection and never runs ahead of it, so a fault in the tag concern SHALL cost tags and nothing else — never the projection of a launch's work, and never the completion intake that travels on the same pass. Where setting a tag on a task fails, the pass SHALL continue, SHALL still attempt the task's other tag, and SHALL report the omission as a warning-level application log record naming the step, the tag and the task.

This is the trade `scheduled-jobs` already forces: it records only whether a run succeeded, so a failed run would hide the gap behind a retry, and a warning log is where a tagging gap is visible. The accepted cost is that a backfill can stall behind runs recorded as succeeded — the same cost the assignee rule already accepts for an unresolvable person.

A created task needs no separate rule: its tags travel inside the creation, and the two a step yields come from the closed gate and discipline vocabularies, whose form was measured accepted in a create body whether or not the tag already existed, so no tag failure arises for it to survive. A creation that fails does so on its own account and is handled as any creation failure is.

#### Scenario: A newly projected task carries both tags

- **WHEN** a task is projected for an `active` `human` step whose gate is `listable` and whose discipline is `listing`
- **THEN** the created task carries the tags `gate:listable` and `discipline:listing`
- **AND** no space-level tag request — no tag creation, and no read of a space's tags — is sent before or after the create

#### Scenario: An existing untagged task gains its tags

- **WHEN** a pass runs over a mapped task that was projected before tagging existed
- **THEN** the task gains its step's `gate:` and `discipline:` tags

#### Scenario: A task already carrying its tags is left alone

- **WHEN** a pass runs over a mapped task already carrying both of its step's tags
- **THEN** no tag write is sent for that task

#### Scenario: A person's own tags are never touched

- **WHEN** a pass runs over a mapped task carrying tags outside the `gate:` and `discipline:` prefixes
- **THEN** those tags are left exactly as they stand

#### Scenario: A step moved between gates keeps its original gate tag

- **WHEN** a step whose task carries `gate:commit` is moved to the `listable` gate and a pass runs
- **THEN** the task carries `gate:listable` in addition to `gate:commit`, and no tag is removed

#### Scenario: A hand-removed tag is added back

- **WHEN** a person removes a mapped task's `gate:` tag in ClickUp and the next pass runs
- **THEN** the tag is added back to the task

#### Scenario: A step that has left the projection is not tagged

- **WHEN** a pass runs and a mapped task's step is not defined by the served playbook, or is not `active`, or is no longer of kind `human`, or carries the `prohibited-tactic` hazard
- **THEN** no tag is written for that task

#### Scenario: No tag is written during a stand-down

- **WHEN** a pass stands down because the served playbook cannot hold a launch
- **THEN** no tag is written to any task

#### Scenario: A tag that cannot be set on a task is reported, not fatal

- **WHEN** a pass adds a missing tag to a mapped task and that tag write fails
- **THEN** the pass continues and still succeeds
- **AND** the omission is reported as a warning naming the step, the tag and the task
- **AND** the task's other missing tag is still added

## MODIFIED Requirements

### Requirement: Human steps are projected as tasks carrying their name, description and assignees

The system SHALL project, into the launch's list, one ClickUp task per step of the served playbook whose kind is `human`, whose status is `active`, and whose hazard is not `prohibited-tactic`, and SHALL record the association between each step and its task. The served playbook is live, so a step activated after the launch started is projected on the next pass like any other. `automated` steps, steps that are not `active`, steps with the `prohibited-tactic` hazard, and gate metric conditions SHALL NOT be projected. A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's **name**, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a step's name happens to say — a name whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A projected task's body SHALL be the step's **description** where the step carries one. Where a step carries no description the system SHALL compose no body at all, and SHALL neither write nor rewrite the task's body — leaving whatever stands there. Composing an *empty* body instead would destroy work: a task projected before this change whose name was shortened carries the step's full former text in its body, written by the system and therefore matching its retained value, so a rule that rewrote it to empty would leave that task stating its work nowhere. The body is no longer a place the name overflows into: the step's own two fields map onto the task's two, which is what having them separate is for.

A projected task SHALL be assigned to the step's assignees, each resolved to the ClickUp user the roster records for that person. Assignment SHALL be reconciled on later passes as well as at creation, so that a step whose assignees change reaches its task, and so that tasks projected before steps had assignees stop being unowned — which is the problem this field exists to solve, and solving it only for new work would leave every in-flight launch as it is. The system SHALL retain, with the mapping, the assignees it last set, exactly as it retains the name and the body it last composed. A person's own assignment change SHALL be respected the way an edited name or body is: where a task's assignees differ from what the system last set, the system SHALL NOT overwrite them. A mapping holding no retained assignees — every mapping made before this change — SHALL be treated as having last been set to nobody, so a task the system left unassigned heals to its step's assignees while one somebody has already assigned is treated as person-edited and left alone. Assignees are the one *retained* field where that reading is right: an unassigned task is the failure this projection exists to fix, so silence there is the system's own doing rather than an edit worth preserving. The tag rule reaches the same reading by a different route and does not qualify it — it retains nothing at all, so absence there carries no claim about authorship either way (see *A projected task carries its step's gate and discipline as tags*). An assignee the roster carries without a ClickUp user id SHALL be skipped for assignment — the task is still created, still carries its remaining assignees, and the omission SHALL be reported as a warning-level application log record naming the step, the person and the task rather than silently dropped — the pass itself succeeds, since a failed run would hide a data gap behind a retry, and `scheduled-jobs` records only whether a run succeeded, so the run record is not where this can be carried.

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
