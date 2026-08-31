## ADDED Requirements

### Requirement: A launch is converged eagerly at start and at a gate crossing

In addition to the periodic reconciliation pass, the system SHALL run the creation/update half of projection — the same convergence *Each launch is projected into its own ClickUp list*, *Task due dates derive from the launch schedule*, *Human steps are projected as tasks carrying their name, description and assignees* and *A projected task carries its step's gate and discipline as Custom Field values* already define — for one launch immediately when that launch starts, and again immediately whenever that launch's gate crosses, so that a launch's first released steps and a gate's newly released steps get their ClickUp tasks without waiting for the pass's next run.

The eager run SHALL apply every projection and eligibility rule exactly as the pass applies them — release, kind, status, hazard, and retained-composition healing included — because it is the same convergence, run early, not a second rule. Nothing about a task's eligibility, its name, or its body SHALL differ depending on whether the pass or the eager trigger created or last touched it.

The eager run is exempted from one part of that convergence: resolving and correcting a task's Custom Field values (`A projected task carries its step's gate and discipline as Custom Field values`) requires reading ClickUp's field definitions and, on a gap, reporting it — work whose cost and reporting cadence that requirement scopes to a pass run, not to an event. The eager run SHALL write no Custom Field value and SHALL report no configuration gap; a task it creates or corrects is left exactly as if the periodic pass had not yet reached it for that concern, and the next periodic pass resolves and corrects its Custom Field values as it would for any task carrying none — the existing healing rule for "a task projected before the fields existed," reached here by a different route.

The eager run SHALL cover only the creation/update half. It SHALL NOT read back ClickUp state or record any outcome — that remains exactly as *Completion flows from ClickUp to the launch as a recorded outcome*, the webhook, and the pass's own reconciliation half already provide for, untouched by this requirement.

A gate crossing SHALL trigger the eager run regardless of which path crossed it — a recorded decision, the periodic gate-progression pass, or the ClickUp webhook's own advance-and-ask trigger — so that the latency this requirement closes does not silently reopen for whichever of the three happens to be least common.

Because the eager run and the periodic pass perform the same idempotent convergence, either running before, after, or concurrently with the other for the same launch SHALL produce the same converged state as either running alone: neither SHALL create a second list or a second task for work the other has already projected, and a launch's convergence SHALL NOT depend on which of the two reaches it first.

A launch for which the eager run fails SHALL be left exactly as if the eager run had not been attempted: the failure SHALL NOT be raised back to whatever triggered the run — launch start, a recorded decision, the gate-progression pass's own advance, or the webhook's acknowledgement — and SHALL NOT stand in the way of that action's own outcome being reported. The next periodic pass SHALL still attempt to converge that launch on its own schedule, exactly as it would for a launch the eager run never ran for. This requirement creates no new obligation to notice or report a failed eager run beyond what the pass already reports when it, in turn, fails to converge the same launch.

The eager run SHALL be suppressed under exactly the condition *Projection and intake stand down while the playbook cannot hold a launch* already suppresses the pass: while the served playbook cannot hold a launch, neither the pass nor the eager run SHALL create a list or write a task.

#### Scenario: A newly started launch's first tasks appear without waiting for the pass

- **WHEN** `start_launch` succeeds for a product
- **THEN** the launch's released `active` `human` steps have tasks created in its ClickUp list before the next periodic pass runs

#### Scenario: A gate crossing's newly released steps get tasks immediately, however the gate opened

- **WHEN** a launch's gate crosses, whether through a recorded decision, the periodic gate-progression pass, or the ClickUp webhook's advance-and-ask trigger
- **THEN** every `active` `human` step the launch newly releases at that gate has a task created in its ClickUp list before the next periodic reconciliation pass runs

#### Scenario: The eager run applies the same eligibility rules as the pass

- **WHEN** the eager run is triggered for a launch carrying a step that is not `active`, is not `human`, carries the `prohibited-tactic` hazard, or is not yet released
- **THEN** no task is created for that step, exactly as the periodic pass would not create one for it

#### Scenario: Custom Field values on an eagerly created task are left to the next pass

- **WHEN** the eager run creates a task for a step
- **THEN** no Custom Field value is written for that task and no configuration gap is reported by the eager run
- **AND** the next periodic pass gives the task its gate and discipline values, exactly as it would for a task carrying none

#### Scenario: The eager run does not record completions

- **WHEN** the eager run is triggered for a launch
- **THEN** no ClickUp state is read back and no step outcome is recorded as a consequence of the eager run itself

#### Scenario: The eager run and the pass do not duplicate each other's work

- **WHEN** the eager run converges a launch and the periodic pass converges the same launch afterward, with nothing about the launch having changed in between
- **THEN** no new list or task is created by the pass for that launch

#### Scenario: A failed eager run does not fail the action that triggered it

- **WHEN** the eager run raises while converging a launch just started or just crossed a gate
- **THEN** the launch start, the recorded decision, the gate-progression pass's advance, or the webhook's acknowledgement completes and is reported exactly as it would have been had the eager run succeeded

#### Scenario: A failed eager run is caught up by the next periodic pass

- **WHEN** the eager run fails to converge a launch and the next periodic pass reaches that launch
- **THEN** the pass converges it exactly as it would a launch for which no eager run was ever attempted

#### Scenario: The eager run stands down exactly as the pass does

- **WHEN** a launch starts or crosses a gate while the served playbook cannot hold a launch
- **THEN** the eager run creates no list and writes no task for that launch, exactly as the periodic pass would decline to on the same condition
