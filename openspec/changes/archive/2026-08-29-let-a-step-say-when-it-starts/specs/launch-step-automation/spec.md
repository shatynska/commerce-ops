## MODIFIED Requirements

### Requirement: An automated step's handler is invoked by recurring work

The system SHALL invoke registered step handlers from recurring work that runs inside the deployment, declaring its schedule and tolerance as `scheduled-jobs` requires of every piece of recurring work. Each pass SHALL consider every launch that has not graduated, and within each launch every step of its served playbook whose kind is `automated`.

A pass SHALL invoke the handler of such a step only where all of the following hold: the launch has released the step (`launch-playbook`, *A step declares when it may start*); the step's recorded outcome is not one the step's hazard permits as terminal; no pending result stands for it; it is not within the cool-off this specification places after a rejection; and it is not within the cool-off this specification places after a handler repeated a non-terminal outcome. `human` steps, steps that are not `active`, steps the launch has not released, and steps already at a permitted terminal outcome SHALL NOT be invoked.

Release is judged by the same rule the projection into a task tracker is judged by, and never by a rule private to this pass: a step's eligibility is one fact about the launch, so that what the system asks of a person and what it asks of a handler cannot drift apart.

A step that names no start gate and no dependencies is released from the launch's first pass, which is every step until an author says otherwise. Gating invocation therefore withholds nothing by itself — it gives an author a way to say that a handler must not run before the launch is ready for it, which without this rule cannot be said at all. A handler whose answer is useful early, and whose inputs are available early, is left to say nothing and keep running early.

An unreleased step SHALL be passed over silently: it is not a fault, not a stuck step, and SHALL NOT be reported as one. It has not failed to make progress — it has not been asked to.

What this means for a step naming an unregistered handler is settled by that requirement, which is narrowed to match.

Invocation SHALL NOT be reachable from outside the deployment.

#### Scenario: An unresolved automated step is invoked

- **WHEN** a pass runs over a launch whose served playbook carries a released `active` `automated` step with no recorded outcome, no pending result and no recent rejection
- **THEN** that step's named handler is invoked

#### Scenario: A human step is never invoked

- **WHEN** a pass runs over a launch whose served playbook carries an `active` `human` step
- **THEN** no handler is invoked for it, whether or not it needs confirmation

#### Scenario: A resolved step is not invoked again

- **WHEN** a pass runs over an `automated` step whose recorded outcome is one its hazard permits as terminal
- **THEN** its handler is not invoked and its recorded outcome is left unchanged

#### Scenario: A graduated launch is left alone

- **WHEN** a pass runs and a launch has reached `graduated`
- **THEN** no handler is invoked for any of its steps

#### Scenario: A step whose start gate the launch has not reached is not invoked

- **WHEN** a pass runs over a launch standing at `commit` and the served playbook carries an `active` `automated` step whose start gate is `listable`
- **THEN** its handler is not invoked, and nothing is recorded against the step

#### Scenario: A step naming no start gate keeps running from the first pass

- **WHEN** a pass runs over a launch standing at `commit` and the served playbook carries an `active` `automated` step naming no start gate and no dependencies
- **THEN** its handler is invoked, whatever gate the step itself belongs to

#### Scenario: A step is invoked on the pass after the launch releases it

- **WHEN** a launch that stood at `commit` advances to the start gate of an unresolved `active` `automated` step, and the next pass runs
- **THEN** that step's handler is invoked

#### Scenario: An unreleased step is not reported as stuck

- **WHEN** a pass runs over a launch that has not released an `active` `automated` step
- **THEN** no stuck-step report is produced for it and no application log record names it as making no progress

#### Scenario: An unregistered handler on an unreleased step is not reported by the pass

- **WHEN** a pass runs over a launch that has not released a step whose named handler no registered use case answers to
- **THEN** the pass reports nothing for it, the startup registration report being where that fault is named

### Requirement: An unregistered handler is reported and skipped, never fatal

Where an `active` `automated` step **the launch has released** names a handler this deployment does not register, the pass SHALL skip that step, SHALL record no outcome for it, and SHALL report the step and the handler name it could not resolve. The pass SHALL continue with every other step and every other launch.

A step the launch has **not** released is passed over before its handler is resolved, so the pass SHALL NOT report it. This narrowing is deliberate and is safe because the pass is not the only place the fault is found: the deployment's own handler-registration report names every step naming an unregistered handler at start, before anything serves. A step nothing will invoke for several gates is not this pass's news to break, and reporting it every pass until its gate arrives would bury the steps that are actually stuck. Once the launch releases it, the pass reports it exactly as it always did.

This is the same trade the startup handler report already settles: a step nothing can resolve is a deployment fault worth naming, never a reason to stop resolving everything else.

#### Scenario: A step naming an unregistered handler is skipped

- **WHEN** a pass reaches an `active` `automated` step whose named handler is not registered in this deployment
- **THEN** no outcome is recorded for it, the step and the handler name are reported, and the pass continues

#### Scenario: A step naming an unregistered handler is not reported before its launch releases it

- **WHEN** a pass reaches a step whose named handler is not registered and whose start gate the launch has not reached
- **THEN** nothing is reported for it, the startup registration report being where that fault is named

