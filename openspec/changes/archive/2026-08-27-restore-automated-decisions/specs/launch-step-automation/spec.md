## MODIFIED Requirements

### Requirement: Only a known, active person may decide a pending result

The system SHALL accept a decision on a pending result only from a Slack identity the roster knows and that is active. A decision from an unrecognised or deactivated identity SHALL be refused, SHALL record no outcome, SHALL leave the pending result standing, and SHALL tell the decider it was refused.

Decisions arrive on the same verified `product_agent` Slack surface `launch-entry` already uses, so a decision whose authenticity cannot be established never reaches this rule; and a decision SHALL be acknowledged within Slack's timeout independently of whether the recording it triggers has completed.

The roster this rule is evaluated against is supplied by the caller, and SHALL answer to **one** stated shape: it SHALL be able to answer who the roster carries, deactivated entries included, since both halves of "known **and** active" are decided here rather than by whatever supplies the roster. A collaborator that cannot answer that — including no collaborator at all — SHALL be refused as a defect of *wiring*: a named error identifying what was supplied and what was expected, raised before the deciding identity is judged. It is raised at the point the identity would be resolved, so a decision already refused for a reason that does not depend on the roster keeps that refusal.

That refusal SHALL NOT be reachable as a decision refusal. A decision refusal is a statement about the decision that was made, so an unreadable collaborator SHALL NOT be resolved into "the roster does not carry that identity", SHALL NOT be reported to the decider as a fact about their identity, and SHALL NOT leave a decider with any reason to believe their roster entry is at fault. The decider SHALL still be told their decision was not processed, and the mis-wiring SHALL be reported where operators see faults rather than only in the Slack reply.

This exists because the opposite arrangement shipped. The collaborator was accepted in whichever of several shapes it happened to arrive in; the shape production actually supplied was none of them; the read fell through to "no such person"; and every decision by every identity — active admins included — was refused as though the roster did not carry them. Unlike the same mis-wiring elsewhere in this repository, it did not fail loudly, and the message it produced pointed at correct roster data instead of at the wiring.

Consequently, the roster a decision is judged against SHALL be the same roster the roster-administration surface writes: an identity that surface holds as active SHALL be able to decide, and no arrangement of the collaborator SHALL be able to refuse every identity alike.

#### Scenario: An unknown identity cannot decide

- **WHEN** a decision arrives from a Slack identity the roster does not know
- **THEN** it is refused, no outcome is recorded, the pending result still stands, and the decider is told

#### Scenario: A deactivated person cannot decide

- **WHEN** a decision arrives from a Slack identity belonging to a person the roster holds as inactive
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

#### Scenario: A collaborator that cannot answer who the roster carries is refused by name

- **WHEN** a decision is judged against a roster collaborator that cannot answer who the roster carries
- **THEN** it is refused with a named error identifying the collaborator supplied and the shape expected, raised before the deciding identity is judged
- **AND** no outcome is recorded and the pending result still stands

#### Scenario: An absent collaborator is refused the same way, not silently

- **WHEN** a decision arrives at a deployment where no roster collaborator was supplied at all
- **THEN** it is refused with the same named wiring error, the decider is told their decision was not processed, and the decision does not fail without an answer

#### Scenario: A mis-wiring is never reported as an unknown identity

- **WHEN** a decision is judged against a roster collaborator that cannot answer who the roster carries
- **THEN** the decider is not told that the roster does not know their Slack identity, and the mis-wiring is reported where operators see faults

#### Scenario: A person the roster carries can decide through the wiring production supplies

- **WHEN** a decision arrives from a Slack identity that the roster-administration surface holds as active, judged against the roster collaborator the running system supplies
- **THEN** that person is resolved and the decision is judged on its merits rather than refused as unknown
