## ADDED Requirements

### Requirement: A recording may carry the finding that produced it

A recorded step outcome SHALL be able to carry, in addition to its evidence and its provenance, the **finding** that produced it: the name of the field the finding's value was written to, that value, and the finding's comment.

*"Carries" rather than "retains":* `launch-step-automation` already uses **retained** for a result held awaiting a member's decision, which is a different record from this one.

This is additive in the strict sense. What a recording already carries — its outcome, its reason where it has one, its source, its recorder, its moment and its evidence — is unchanged, and so is when a recording is written. A recording that carries a finding and one that does not are the same kind of thing, recorded by the same act.

**A carried finding SHALL travel on the launch report, on the step entry the recording belongs to.** A fact a consumer needs travels on the report rather than being re-derived, as this capability already requires of a step's name, whether it blocks, and whether it is overdue. A page cannot read a recording the report did not carry.

**Carrying a finding SHALL NOT alter the evidence.** The evidence is the verbatim text a member was shown and decided on, and it stays that. A finding beside it is a second, structured account of the same act, not a replacement for the first — and a change to how a result is presented must never rewrite the record of what someone actually read.

**A recording carrying no finding SHALL be distinguishable from one whose value is empty.** These are different facts and the difference is the point of carrying anything: no finding means nothing was established, while an empty value means something was established and it was empty. A representation collapsing the two SHALL be rejected. Every recording made before this capability existed carries no finding, and SHALL read as the first of those two, never as the second.

**The value's own emptiness SHALL be represented one way only.** Where a finding is present, its value SHALL be the value written; a value that is absent, or null, SHALL NOT be stored or read as a present finding. A finding whose value cannot be established is not a finding, and admitting a second spelling of "empty" would give the distinction above two answers.

**The comment MAY be absent.** A supported finding is not obliged to carry one, so a finding whose comment is absent SHALL be storable and readable as such, distinct from one whose comment is empty text.

**A recording whose stored finding cannot be read SHALL be reported as carrying none, and SHALL NOT fail the read.** One unreadable row must not deny a reader every other fact about the launch — the surface that consumes this exists to prevent facts going missing, and failing the read would lose all of them to save one.

A later recording for the same step SHALL replace the carried finding along with the outcome and the provenance it replaces, including replacing a carried finding with none.

#### Scenario: A recording carries the finding that produced it

- **WHEN** an outcome is recorded together with a finding's field, value and comment
- **THEN** the recording carries all three, readable back alongside its outcome, evidence and provenance

#### Scenario: A carried finding reaches the launch report

- **WHEN** a launch report is produced for a launch whose step recording carries a finding
- **THEN** that step's entry on the report carries the finding, without a consumer re-deriving it

#### Scenario: A recording made with no finding carries none

- **WHEN** an outcome is recorded with no finding
- **THEN** the recording carries no finding, and its outcome, evidence and provenance are exactly what they would be for any other recording

#### Scenario: An absent finding is distinguishable from an empty value

- **WHEN** one recording carries no finding and another carries a finding whose value is empty
- **THEN** the two are distinguishable when read back, the first reporting that nothing was established and the second reporting that what was established was empty

#### Scenario: A finding with no comment is carried as such

- **WHEN** an outcome is recorded with a finding whose comment is absent
- **THEN** the recording carries the field and the value, and reports the comment as absent rather than as empty text

#### Scenario: An unreadable stored finding does not fail the read

- **WHEN** a recording whose stored finding cannot be read is read back
- **THEN** it reports carrying no finding, and every other fact about the recording is returned

#### Scenario: Evidence is unchanged by what is carried beside it

- **WHEN** an outcome is recorded with a finding
- **THEN** its evidence is the same text it would have been had nothing been carried

#### Scenario: A later recording replaces the carried finding

- **WHEN** a step carrying a finding has a later outcome recorded against it
- **THEN** the carried finding is replaced along with the outcome and provenance, including being replaced by none where the later recording carries nothing

#### Scenario: A recording made before this capability reads as carrying nothing

- **WHEN** a recording stored before this capability existed is read back
- **THEN** it reports that it carries no finding, rather than reporting an empty one
