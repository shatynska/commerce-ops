## MODIFIED Requirements

### Requirement: Every gate is held by at least one blocking step

Each of the eight gates SHALL have at least one **active** blocking step attached to it before the playbook may be served to a launch, so that no gate's step obligations are trivially satisfied by an empty set. Advice, cautions and optional-at-launch work are expressed by not blocking; with `binding` removed the playbook records no separate notion of advice for a rule to key on.

This floor is a property of the **served** set, not a coherence rule. A step set that leaves a gate unheld SHALL load, and SHALL be readable and editable through the authoring surface — a set whose steps are all `draft` is a legitimate state of a playbook being written, not a malformed one. What such a set SHALL NOT do is hold a launch; see *A playbook that cannot hold a launch is not served*.

Counting only active steps is what makes the floor mean what it says: a gate whose only blocking step is a draft is a gate that would open for free, and the floor exists to make that state unservable.

#### Scenario: No gate opens for free

- **WHEN** a playbook is served to a launch and its served steps are grouped by gate
- **THEN** every gate has at least one active step with a true blocking flag

#### Scenario: A set that leaves a gate unheld still loads

- **WHEN** a step set satisfying every coherence rule leaves one or more gates with no active blocking step
- **THEN** it loads, and its authored steps are readable

#### Scenario: A set whose steps are all drafts loads

- **WHEN** every step in the set carries a status other than `active`
- **THEN** the set loads and no gate-holding fault is reported

### Requirement: An incoherent playbook is rejected against each step's status

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

Every rule below is a statement about the step set's own internal consistency, and each holds whatever the set's stage of completion. Whether the set is *finished* — whether every gate is held — is deliberately not among them: it is a property of the served set, governed by its own requirement, so that a set under construction is incomplete rather than incoherent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's name is empty, consists only of whitespace, or is not declared at all
- a step definition's name spans more than one line — a name is composed into a task's name, and a name is a single line
- a step definition is `automated` and beyond `draft` while its automation brief is absent
- a step definition is `automated` and `active` while its handler is absent
- a step definition is `human` while carrying an automation brief or a handler
- a step definition is classified `prohibited-tactic` and is also marked as blocking its gate
- a gate's authored metric condition has an empty threshold description

#### Scenario: Gate sequence deviates from the specification

- **WHEN** a playbook's gate sequence omits a gate, adds one, repeats a position, or orders the gates differently from the defined sequence
- **THEN** loading fails with an error naming the deviation

#### Scenario: A gate's opening mode disagrees with the specification

- **WHEN** a playbook declares an opening mode for a gate that differs from the mode this specification assigns to it
- **THEN** loading fails with an error naming that gate

#### Scenario: Duplicate step identifier

- **WHEN** a playbook defines two steps with the same identifier
- **THEN** loading fails with an error naming that identifier

#### Scenario: Step references an unknown gate

- **WHEN** a step definition declares a gate that is not part of the gate sequence
- **THEN** loading fails with an error naming the step and the unknown gate

#### Scenario: A step with no name is rejected by identifier

- **WHEN** a playbook declares a step whose name is empty, consists only of whitespace, or omits the name entirely
- **THEN** loading fails with an error naming that step, in the same aggregated report as any other fault

#### Scenario: A name spanning several lines is rejected

- **WHEN** a playbook declares a step whose name contains a line break
- **THEN** loading fails with an error naming that step

#### Scenario: A description spanning several lines is accepted

- **WHEN** a playbook declares a step whose description contains line breaks
- **THEN** the playbook loads, and the description is carried unaltered

#### Scenario: Automation past draft without a brief

- **WHEN** an `automated` step beyond `draft` has no automation brief
- **THEN** loading fails with an error naming that step

#### Scenario: A prohibited tactic cannot block a gate

- **WHEN** a step definition is classified `prohibited-tactic` and marked as blocking its gate
- **THEN** loading fails with an error naming that step

#### Scenario: A gate with no active blocking step is rejected

- **WHEN** a playbook's steps leave any gate with no active step whose blocking flag is true
- **THEN** the rejection happens when that playbook is asked for in order to hold a launch, naming the gate, and not when it is loaded

#### Scenario: A malformed metric condition is rejected

- **WHEN** a playbook authors a metric condition whose threshold description is empty
- **THEN** loading fails with an error naming the gate carrying it

#### Scenario: Multiple violations are reported together

- **WHEN** a playbook contains two distinct coherence violations
- **THEN** loading fails once, and the failure names both

#### Scenario: A malformed step is reported alongside a coherence violation

- **WHEN** a playbook contains one step whose timing anchor is invalid and a second, separate coherence violation
- **THEN** loading fails once, and the failure names both faults

#### Scenario: A coherent playbook loads

- **WHEN** a playbook satisfies every coherence rule
- **THEN** it loads successfully and exposes its gates and step definitions

### Requirement: A step declares a lifecycle status, and only active steps are served

Each step definition SHALL declare a status: `draft`, `in-development`, `active` or `retired`. The status says how far the step has been carried, not what it asks for, and it decides what the rest of the system may do with it.

Only `active` steps SHALL be served to a launch, count toward a gate's obligations, or be projected to a task tracker. The playbook's own step queries — by gate, by scope — SHALL answer the **served** set, so nothing that advances a launch can be handed a draft by accident; the authored set is reached by a separate read, which is the read the admin surface already uses to reveal retired steps. `draft`, `in-development` and `retired` steps SHALL remain readable to whoever authors the step set and SHALL be excluded from every served view. A step that has not been made active is therefore free to be incomplete: this is what lets an author write down work whose automation does not exist yet, rather than inventing a description of code nobody has written.

Status SHALL be declared explicitly, with `draft` the value a step carries when its author declares nothing.

Any status MAY move to any other, and every move SHALL be a write validated by the rules of the status it moves **to**. A move into or out of `retired` is the one exception to that freedom: it SHALL be the retirement or un-retirement write itself — carrying the attribution `playbook-authoring` requires of it, and arriving at `in-development` on the way out — whatever surface asks for the change, so that a status control cannot become a second way out of `retired` that lands somewhere else and records nobody — so there is no transition table to consult beyond the target's own requirements, and no ordering a step must climb. What makes a move legal is that the step satisfies where it is going, plus the whole-set rules every write obeys: moving a step out of `active` is refused where the set is currently ready and the move would leave its gate unheld, exactly as retiring it is, and is permitted where the set is not ready — the one-directional rule `playbook-authoring` states.

"Beyond `draft`" means `in-development` or `active`, and does not include `retired`: a step abandoned before its automation was ever specified is retired without ever owing a brief, which is the honest record of what happened to it.

#### Scenario: A draft step is authored but not served

- **WHEN** a step is created with status `draft`
- **THEN** it is readable in the authored set, and the served playbook does not carry it

#### Scenario: Only active steps hold a gate

- **WHEN** a gate holds one active blocking step and one `in-development` blocking step
- **THEN** only the active one holds the gate, and the `in-development` one contributes no obligation

#### Scenario: A retired step leaves the served set without leaving the record

- **WHEN** a step's status becomes `retired`
- **THEN** it is no longer served, and it remains readable to authors with its history intact

## ADDED Requirements

### Requirement: A playbook that cannot hold a launch is not served

A playbook SHALL be **ready** exactly when every gate has at least one active blocking step attached. Readiness SHALL be derived from the step set on every read and SHALL NOT be stored, so it can never disagree with the steps it summarises.

The read that serves a launch SHALL refuse a playbook that is not ready, and the refusal SHALL name the gates holding no active blocking step. The read that serves the authoring surface SHALL NOT be refused for that reason, so a set under construction stays visible and editable throughout.

Not being ready SHALL be reported as its own condition, distinguishable by a consumer from an incoherent playbook: the first is an expected stage of a set being written, the second is a defect. A playbook that is **absent** SHALL remain an error and SHALL NOT be reported as not ready — nothing to serve and nothing built yet are different failures.

The refusal SHALL additionally carry the playbook it was constructed from. A consumer that is declining to act may still owe an obligation that turns on what the set contains — `launch-clickup-sync`'s intake owes opposite treatments to a served and a non-served step's task — and a refusal that carried only the gate names would force it either to take a second read or to guess. The playbook is coherent; the only thing wrong with it is that it cannot hold a launch, which is exactly what the refusal says.

The carried playbook SHALL be used only to classify what the set contains. It SHALL NOT be used to advance, project or report on a launch, and SHALL NOT be supplied to a use case in place of a playbook obtained by a read that succeeded. Without this the refusal would hand back the very aggregate it withheld, and the guarantee that a launch is only ever advanced through a playbook that can hold one would rest on the good manners of each consumer rather than on the refusal.

#### Scenario: A launch cannot be advanced by an unready playbook

- **WHEN** a consumer asks for the playbook on a launch's behalf — to advance one, project one, or report on one — and one or more gates hold no active blocking step
- **THEN** the request is refused, and the refusal names those gates

#### Scenario: Authoring reads an unready playbook freely

- **WHEN** the authoring surface reads a step set that leaves gates unheld
- **THEN** the read succeeds and every authored step is listed, whatever its status

#### Scenario: Readiness follows the set without ceremony

- **WHEN** the last gate holding no active blocking step gains one through an ordinary authoring write
- **THEN** the next serving read succeeds, with no further action

#### Scenario: A refusal carries the set it declined to serve

- **WHEN** a consumer is refused a playbook because a gate is unheld
- **THEN** the refusal carries both the unheld gate identifiers and the playbook itself, so the consumer can tell a served step from one that is not without taking a second read

#### Scenario: The carried set may be classified but not acted on

- **WHEN** a consumer holds the playbook carried by a refusal
- **THEN** it may ask which of that set's steps are served, and may not use it to advance, project or report on a launch

#### Scenario: Not ready is distinguishable from incoherent

- **WHEN** a consumer is refused a playbook because a gate is unheld
- **THEN** the condition reported is distinct from the one reported for a playbook that violates a coherence rule

#### Scenario: An absent playbook is still an error

- **WHEN** no step set exists at all
- **THEN** the failure reported is that the playbook is absent, not that it is unready
