## ADDED Requirements

### Requirement: A retained result is kept and stays readable as the product's record

Every result stored for a decision SHALL be retained whatever state it reaches. Settling a result — as accepted or as rejected — and voiding one SHALL each keep the row, carrying the state it reached and, where a person decided it, who decided and when. Nothing in the decision flow SHALL delete a result.

This narrows three requirements already in this specification. *Accepting records the proposed outcome and names the accepter* says the pending result "SHALL then be settled"; *Rejecting does not terminate the step* says it "SHALL settle the pending result as rejected"; and *A decision on a step the playbook no longer serves is refused* says the system "SHALL void the pending result rather than leaving it standing". Read alone, each could be satisfied by deleting the row. None may be, and a later amendment to any of the three SHALL be read against this requirement.

The system SHALL be able to answer, for one product, every result retained for it: results in every state, results produced for a step the served playbook no longer defines, and results retained for a launch that has since graduated. That answer SHALL be ordered by the moment each result was produced, most recent first, and SHALL be total — results produced at the same moment SHALL be ordered by a stable tiebreak, so that the same stored data is answered in the same order every time.

Retention is already what the store does; what this requires is that it be *readable as a record*. Every read the store offers today serves the decision loop — the pending result for a step, a result by its identifier, the undelivered ones, the most recent rejection — and none of them answers "what has been produced for this product". Without such a read, "settled rows are kept, never deleted" buys storage and nothing else: the record of a compliance-adjacent decision exists and is reachable only by querying the database directly.

The read SHALL be filtered by the caller's access scope, in the shape every other product-keyed read follows: for a product the scope does not permit, it SHALL answer exactly as it does for a product with nothing retained, so that reading can never confirm the existence of a product or a result the caller may not see.

#### Scenario: A settled result is still readable

- **WHEN** every result retained for a product is read after one of them was accepted and another rejected
- **THEN** both are answered, each carrying the state it reached, the person who decided it and the moment of the decision

#### Scenario: A voided result is readable and is not a rejection

- **WHEN** every result retained for a product is read after a decision voided one of them
- **THEN** that result is answered carrying the voided state, distinct from a rejected one

#### Scenario: A voided result carries no decider

- **WHEN** every result retained for a product is read after a decision voided one of them
- **THEN** that result is answered with no decider, because voiding refuses a decision rather than recording one

#### Scenario: A result for a step no longer served is still readable

- **WHEN** every result retained for a product is read after the step one of them names has been moved out of `active`
- **THEN** that result is still answered

#### Scenario: A graduated launch's results are still readable

- **WHEN** every result retained for a product is read after that product's launch has reached `graduated`
- **THEN** every result retained for it is answered

#### Scenario: Results are answered newest first

- **WHEN** every result retained for a product is read and results were produced at different moments
- **THEN** they are answered ordered by the moment produced, most recent first

#### Scenario: Results sharing a produced moment are answered in the tiebreak's order

- **WHEN** every result retained for a product is read and two of them share a produced moment and differ in row identifier
- **THEN** the one whose row identifier sorts higher is answered first
- **AND** it is answered first whichever order the two were stored in

#### Scenario: A product outside the caller's scope answers as an empty record

- **WHEN** every result retained for a product is read under a scope that does not permit that product's identifier
- **THEN** nothing is answered, exactly as for a product with nothing retained, and no error distinguishes the two

#### Scenario: A product with nothing retained answers emptily, not with a failure

- **WHEN** every result retained for a product that has never had a result stored is read
- **THEN** nothing is answered and the read succeeds

### Requirement: The retained record covers results held for a decision and nothing else

Every result the system retains SHALL be one held for a decision — a terminal outcome the step's hazard permits, proposed for a step whose confirmation flag is true, and actually stored. An outcome recorded directly SHALL NOT be retained here: neither a non-terminal outcome, which this specification records against the launch whatever the confirmation flag says, nor a terminal outcome on a step needing no confirmation.

Stated as a necessary condition and not as a biconditional, because the converse is false and this specification already says why: a terminal outcome the step's hazard forbids stores nothing at all (*A terminal outcome the step's hazard forbids is a handler fault, not a recording*), and a second proposal racing an existing pending one stores nothing either (*A result needing confirmation is held until a person decides*). A consumer may rely on everything in the record being a proposal someone was asked to accept; it may not rely on the record holding every such proposal ever made.

This states no new routing policy. Which outcomes are held and which are recorded directly is settled by three requirements already in this specification — *A non-terminal outcome is recorded directly and never held for a decision*, *A result needing no confirmation is recorded at once* and *A result needing confirmation is held until a person decides* — and this requirement is their consequence, not a second statement of them. Where they change, this changes with them.

What it adds is the boundary as a fact *about the retained set*, which a consumer reads rather than derives. The retained set is the record of **what people were asked to accept**, not the record of everything handlers produced; a consumer that presented it as the latter would be wrong in a way its readers could not detect, and most wrong for exactly those products whose automated steps need no confirmation.

#### Scenario: An outcome needing no confirmation is not retained

- **WHEN** a handler resolves a step whose confirmation flag is false, and every result retained for that product is read
- **THEN** nothing is answered for that step

#### Scenario: A non-terminal outcome is not retained

- **WHEN** a handler proposes a non-terminal outcome for a step whose confirmation flag is true, and every result retained for that product is read
- **THEN** nothing is answered for that step
