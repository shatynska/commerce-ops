## ADDED Requirements

### Requirement: A written finding is kept on the recording it produced

Where a handler reports a supported finding and the step names a sink for it, the system SHALL keep on that step's recording the name of the field the sink writes, the value written, and the finding's comment — as `launch-instance` provides for.

*"Kept" here is deliberately not "retained".* This capability already uses **retained** for a result held awaiting a member's decision (*A retained result is kept and stays readable as the product's record*), and that is a different record from the one this requirement adds to. The two are related below, and must not be read as one.

**A finding is kept on the recording the value's write belongs to — and for a confirmable step, that recording is made when the result is accepted, not when the handler ran.** This capability already separates the two: a supported finding is written to its sink at the moment the handler runs, *independently of the step's own confirmation*, while a terminal outcome on a step naming a confirmer is held as a pending result and recorded only when a member accepts it. A finding kept only on a recording the pass makes would therefore never reach a confirmable step at all.

So the finding SHALL travel with the pending result: stored alongside the proposed outcome and produced text when the result is held — extending what *A result needing confirmation is held until a member decides* stores — and kept on the recording that acceptance makes, extending what *Accepting a pending result records the proposed outcome* records. A step recording its outcome directly — because it names no confirmer, or because the proposed outcome is non-terminal — SHALL have the finding kept on that recording instead.

**A finding stored with a pending result SHALL follow the same rules `launch-instance` states for one kept on a recording**: one spelling of an empty value, an absent comment carried as absent, and a stored finding that cannot be read reported as none. **A finding that cannot be read at acceptance SHALL NOT fail the acceptance.** The recording and the settlement must both take effect or neither, so a decision a member has made must not be lost to an unreadable field beside it — the outcome the member accepted is what matters, and the finding is what accompanies it.

**The value kept is the value as it was written when the handler ran, and acceptance SHALL NOT re-read the sink.** A pending result suppresses re-invocation of its step, so the handler cannot overwrite it meanwhile; but a direct write elsewhere can, and re-reading at acceptance would silently substitute a later value for the one the member was shown and decided on. What the recording asserts is what the handler established, which is also what the produced text a member read describes.

**A rejected result SHALL keep no finding.** The value written to the product before the proposal was made stands or falls by `product-catalog`'s own rules and is not this requirement's business; but a member rejecting the proposal has declined the fact it asserted, and a `Blocked` recorded from that rejection SHALL NOT carry a finding asserting it anyway.

**Keeping follows the write.** Only a finding actually written to its sink is kept. A finding for a step naming no sink is not written today and SHALL NOT be kept either; where a write did not succeed, no finding SHALL be kept.

**A non-terminal outcome carrying a finding SHALL keep it.** Where a handler writes a finding and proposes a non-terminal outcome, that outcome is recorded directly, and the finding is kept on it. Nothing about keeping a finding is conditional on the outcome being a satisfying one — a fact established about a product is established whether or not the step it came from is resolved.

**The field's name SHALL come from the sink's registration and never from the handler.** A handler reports a value and a comment; where that value goes is the composition root's knowledge, registered alongside the sink itself. A handler SHALL NOT name a field, and SHALL NOT be given a way to. This is the rule `subcategory-advisor` states as "nothing outside this capability ever needs to know this step in particular has a sub-category field", read in the other direction: the capability does not get to know either.

**Keeping a finding changes nothing about the outcome or the result.** The existing requirement that a reported finding leaves both exactly as they would be for a handler reporting none continues to hold in full. This requirement adds what is kept *beside* them; it does not qualify that one. A handler's produced text is still stored as evidence, unchanged and unabridged.

A handler reporting a `Failure` finding, and a handler reporting none, SHALL cause nothing to be kept.

#### Scenario: A written finding is kept with the field it was written to

- **WHEN** a handler reports a supported finding for a step naming a sink and no confirmer, and the value is written
- **THEN** the recording the pass makes carries that sink's field name, the value written, and the finding's comment

#### Scenario: A confirmable step's finding survives until the result is accepted

- **WHEN** a handler reports a supported finding with a terminal outcome for a step naming a confirmer, and the value is written
- **THEN** the finding is stored with the pending result, and the recording made when a member accepts carries the field name, the value and the comment

#### Scenario: An unreadable stored finding does not fail an acceptance

- **WHEN** a member accepts a pending result whose stored finding cannot be read
- **THEN** the acceptance takes effect, the outcome is recorded, and that recording carries no finding

#### Scenario: The value kept is the value as written

- **WHEN** a pending result's finding is kept on the recording an acceptance makes
- **THEN** the value kept is the one written when the handler ran, and the sink is not re-read at acceptance

#### Scenario: A rejected result keeps no finding

- **WHEN** a member rejects a pending result whose finding was written
- **THEN** the outcome recorded from that rejection carries no finding

#### Scenario: A non-terminal outcome keeps the finding it wrote

- **WHEN** a handler writes a finding and proposes a non-terminal outcome
- **THEN** that outcome is recorded directly and carries the field name, the value and the comment

#### Scenario: The field's name is not the handler's to supply

- **WHEN** a handler reports a supported finding
- **THEN** the field name kept is the one the sink's registration names, and no part of it is taken from the handler

#### Scenario: A finding for a step naming no sink is kept no more than it is written

- **WHEN** a handler reports a supported finding for a step that names no sink
- **THEN** nothing is written and nothing is kept, and the outcome and evidence are recorded as they are for any handler reporting no finding

#### Scenario: A failure finding keeps nothing

- **WHEN** a handler reports a `Failure` finding
- **THEN** nothing is kept, exactly as nothing is written

#### Scenario: A finding whose write did not succeed is not kept

- **WHEN** a handler reports a supported finding and writing it to its sink does not succeed
- **THEN** no finding is kept

#### Scenario: The outcome and the evidence are unaffected by what is kept beside them

- **WHEN** a handler reports a supported finding that is written and kept
- **THEN** the outcome recorded and the evidence stored are exactly what they would have been had the handler reported no finding at all
