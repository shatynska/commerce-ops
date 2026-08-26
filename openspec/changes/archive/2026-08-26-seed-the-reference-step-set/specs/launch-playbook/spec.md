## MODIFIED Requirements

### Requirement: The seeded step set carries the authored v1 definitions

The stored step set SHALL be seeded with the authored step definitions — not started empty. The seeded set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) **completely**: every ID-bearing row of every area appears as a step, except those excluded below for restating a gate's authored metric condition, so a gate carries what the reference document puts behind it rather than a sample of it. Each seeded step's identifier SHALL be the reference document's own row ID and its provenance SHALL carry that row's source citation, so every seeded step traces to exactly one reference row.

A seeded step's **description** SHALL be the text of its reference row transcribed unaltered, except that trailing whitespace SHALL be removed, and then any trailing character in the closed set `;` `:` `,` `.` — repeating until neither whitespace nor one of those four characters remains at the end. No other character SHALL be stripped, and nothing else SHALL be changed — not the wording, the casing, or the order of clauses.

The set is closed deliberately, and is not "trailing punctuation": reference rows end variously in a closing quote, a closing parenthesis, or a `+` (as in "A+"), and each of those is part of what the row says rather than a fragment's terminal mark. A rule broad enough to remove them would silently corrupt the text it exists to preserve.

Transcribing this way is what makes every seeded description re-derivable from the reference document and comparable against it, so that a divergence between the two is detectable rather than silent. The reference document's wording belongs to the team that wrote it; the seed moves it, and does not improve it.

A seeded step's **name** SHALL be authored rather than transcribed, and SHALL be at most 80 characters. The two fields answer to different readers: a name is scanned in a list and composed into a task tracker's title, while a description is read once someone has decided to do the work. Transcribing the row into the name — as this requirement previously required — produces names with a median of 114 characters and a maximum of 253, which is a paragraph occupying a title. The authored name SHALL preserve any leading marker the row carries (`TOS RISK:`, `EU:`, `NOTE:`), because those are what a reader scans for, and SHALL preserve any numeric threshold the row states, because a threshold is the work rather than a detail of it.

An authored name is not re-derivable from the reference document, and this requirement SHALL NOT claim it is. What stays re-derivable is the description; a divergence in the text the reference owns remains detectable.

A seeded step's identifier SHALL carry its declared discipline as its second segment (`lp.creative.008` is a `creative` step). This is what allows a surface composed from the identifier to omit the discipline without losing it, and it holds for every step of the seeded set.

Rows of the reference document that restate a condition a gate already authors as a metric condition SHALL NOT additionally appear as seeded steps: one obligation is expressed once.

These guarantees describe the set the **preparation step** establishes (see *The step set is seeded before the application serves*), not the set the migration-era seed left behind. That earlier seed remains as it was — it runs exactly once per environment, from its own vendored file, and is what a database built from scratch receives before the preparation step has run.

Once established, the step set changes through the `playbook-authoring` capability and through the preparation step, and through nothing else. A step edited through authoring is thereafter governed by its recorded authorship rather than by re-derivability from the reference document; a step the preparation step re-establishes carries no authoring attribution, exactly as the migration-era seed's rows carry none.

#### Scenario: The shipped playbook loads with steps

- **WHEN** the playbook is loaded after seeding
- **THEN** it loads coherently and its step list is non-empty
- **AND** every gate has at least one step attached

#### Scenario: BUILD THE LISTING is fully represented

- **WHEN** the seeded step set is compared against the ID-bearing rows of the reference document's BUILD THE LISTING area
- **THEN** every such row's ID appears as a step identifier

#### Scenario: Every area is fully represented

- **WHEN** the seeded step set is compared against the ID-bearing rows of every area of the reference document
- **THEN** every such row's ID appears as a step identifier, except those excluded for restating a gate's authored metric condition

#### Scenario: A step traces to its source row

- **WHEN** any seeded step is read, before any authored edit to it
- **THEN** its identifier is a reference-document row ID and its provenance reference is that row's source citation
- **AND** the second segment of that identifier is the step's declared discipline

#### Scenario: A step states its work without the source document

- **WHEN** any seeded step is read
- **THEN** its name is non-empty

#### Scenario: Every description re-derives from its reference row

- **WHEN** every seeded step's description, before any authored edit to it, is compared against the text of the reference row its identifier names, reduced by the trimming rule above
- **THEN** each description equals that row's trimmed text exactly

#### Scenario: A name is short enough to title a task

- **WHEN** every seeded step's name is measured
- **THEN** none exceeds 80 characters

#### Scenario: A row's leading marker survives into its name

- **WHEN** a seeded step's reference row begins with `TOS RISK:`, `EU:` or `NOTE:`
- **THEN** its authored name begins with that same marker

#### Scenario: A gate-authored condition is not duplicated as a step

- **WHEN** the seeded step identifiers are compared against the reference rows that restate a gate's authored metric conditions
- **THEN** none of those rows' IDs appears as a step identifier

#### Scenario: The seed runs once

- **WHEN** the seed has already populated the step set and the **migration machinery** runs again
- **THEN** the step set is not re-seeded by it and authored changes made since are not overwritten by it
- **AND** this says nothing about the preparation step, which is a separate write path governed by its own requirement

### Requirement: The authored set exercises the full step vocabulary

The **seeded** step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring) and at least one step for every discipline in the shared vocabulary, so that no part of the vocabulary the playbook defines goes unrepresented by the work it ships with.

Every seeded step SHALL be `draft` and SHALL be `human`, and SHALL name no assignee. This is the whole point of seeding the reference document entire: 352 rows nobody has yet judged are work written down, not work in play. A seeded set is therefore **not ready** to hold a launch, and the deployment says so rather than pretending otherwise.

It follows that the seeded set SHALL NOT be required to exercise `kind`, `status` or `needs_confirmation`. Requiring an `automated` step would mean seeding a claim that code resolves it, and requiring an `active` step would mean pre-committing the review the seed exists to enable. Both are consequences of every step being a draft nobody has judged, so neither can be asked of this seed.

The **hazard** vocabulary is different and its coverage SHALL be kept: at least one `prohibited-tactic` step and at least one `compliance-obligation` step SHALL be present. A human pass has already classified rows of the reference document, and those classifications SHALL be carried across unchanged, so both are satisfiable without classifying anything new. What the seed SHALL NOT do is invent a classification for a row the human pass did not reach: a wrong `prohibited-tactic` produces a step whose only terminal outcome is `Refused` — work that can never be done — so an unreached row SHALL arrive as `none`.

That a runtime now exists to invoke handlers (`launch-step-automation`) does not change what a seed delivers, and under this requirement it changes it less than before: the seeded set carries no `automated` step at all. Registering a handler activates nothing, because activation is an authoring act performed against a deployment that registers the step's handler — never something seeding or deploying does on an author's behalf. The paragraph this replaces said the same of the two automated steps the migration-era seed delivered; the principle survives its subject.

The rule this requirement previously carried — that a suspension-risk row becomes a `prohibited-tactic` step only where it names a tactic to refuse, while a caution remains ordinary work — is superseded rather than dropped: carrying the human pass across unchanged and classifying nothing new delivers the same outcome without asking the seed to make the judgement.

Like its sibling seed requirement, this describes the seed and only the seed: it is a property of what seeding delivers, not a standing invariant of the served set. Write validation under `playbook-authoring` enforces the coherence rules, and does not additionally hold authored changes to this coverage.

#### Scenario: Anchor kinds are all present

- **WHEN** the seeded step set is grouped by timing-anchor kind
- **THEN** each of offset, window, open-ended, and recurring is represented by at least one step

#### Scenario: Every discipline appears

- **WHEN** the seeded step set is grouped by discipline
- **THEN** every discipline of the shared vocabulary is represented by at least one step

#### Scenario: Execution modes and the compliance hazard are represented

- **WHEN** the seeded step set is grouped by kind and confirmation and filtered by hazard
- **THEN** every step is `human` and none needs confirmation, so no coverage of `automated` is required of the seed
- **AND** at least one `compliance-obligation` step exists

#### Scenario: Prohibited tactics are present and never block

- **WHEN** the seeded step set is filtered to hazard `prohibited-tactic`
- **THEN** at least one such step exists
- **AND** none of them has a true blocking flag

#### Scenario: Every seeded step is a draft nobody owns

- **WHEN** the seeded step set is read
- **THEN** every step is `draft`, every step is `human`, and no step names an assignee

#### Scenario: A seeded playbook is not ready

- **WHEN** the playbook is read on a launch's behalf immediately after seeding
- **THEN** it is refused as not ready, naming every gate no surviving active blocking step holds — all eight where the seed is the whole set

#### Scenario: A registered runtime does not activate a seeded step

- **WHEN** a deployment registers step handlers and the seeded step set is read back
- **THEN** no seeded step has become `active` or `automated` — the seeded set is entirely `human` drafts, and registering a handler activates nothing

#### Scenario: Outstanding rule-policy decisions stay visible

- **WHEN** the report of what blocks activation runs over the authored set while any step cannot yet be made `active`
- **THEN** it lists exactly those steps

## ADDED Requirements

### Requirement: The step set is seeded before the application serves

The seeded step set SHALL be established by a preparation step that runs between the schema migration and the serving process, not by the serving process itself and not by the migration machinery. Reading or writing the step set inside the server would make it open a database connection before its first request, which `database-session` forbids; and the migration machinery cannot express it, because a migration runs exactly once per environment while a reference document that gains a row must be able to deliver it later.

The step SHALL insert every vendored step no stored step names, and SHALL leave every stored step exactly as it stands — whatever its status, whatever an author has since made of it, whether or not the vendored set names it. A stored step SHALL NOT be replaced, re-dated, re-statused, un-retired, de-activated or stripped of an assignee by a seeding run.

Identity is the only question the step is entitled to ask of the stored set. Whether a stored row *differs* from its vendored counterpart is not a question it may act on, because a row that differs is indistinguishable from one an author edited — the difference is the edit. So the rule is drawn on the identifier, which `playbook-authoring` requires to be unique and never updatable, and which is therefore a key that cannot move underneath the comparison.

This is what makes the step safe to run on every container start, and why nothing arms it. Running it twice in succession SHALL change nothing the first run did not, so its condition is readable from the data in the way `roster`'s admin-seeding condition is — and a step whose condition is readable needs no signal delivered alongside it. A signal *would* have been needed for a step that replaces, because runtime configuration reaches a host only when a deployment is made, so a signal withdrawn after an armed deploy would go on arming every restart until the next one.

It follows that a **corrected** vendored definition SHALL NOT reach a step that already exists. Correcting a stored step is an authoring act, performed through the surface `playbook-authoring` governs, by someone who can see what they are changing and whose change is attributed. A wholesale refresh requires emptying the step set first, which is a deliberate destructive act and SHALL look like one.

Exit status SHALL be the whole interface — zero when the set is established, non-zero with the reason on stderr when it cannot be — so the start chain stops on a failure rather than serving a set nobody verified.

#### Scenario: An empty set receives the whole vendored set

- **WHEN** the step runs against a step set carrying none of the vendored steps
- **THEN** every vendored step is stored, and the step exits zero

#### Scenario: Running twice changes nothing the first run did not

- **WHEN** the step runs against a set that already carries every vendored step
- **THEN** nothing is written and the step exits zero

#### Scenario: A step the vendored set names is left exactly as it stands

- **WHEN** the step runs against a set holding a step whose identifier the vendored set names, which an author has renamed, activated and assigned
- **THEN** that step keeps its name, its status, its assignee and its attribution

#### Scenario: A retired step is not returned by a seeding run

- **WHEN** the step runs against a set holding a `retired` step whose identifier the vendored set names
- **THEN** that step is still `retired` afterwards, and the principal and date of its retirement are unchanged

#### Scenario: A step outside the vendored set survives

- **WHEN** the step runs against a set holding a step created through the authoring surface, which the vendored set does not name
- **THEN** it is still stored afterwards, with its status and attribution unchanged

#### Scenario: A reference row added later is delivered

- **WHEN** the vendored set gains a step no stored step names, and the step runs
- **THEN** that step is stored, and no other stored step is altered

#### Scenario: A failure leaves the previous set intact

- **WHEN** the step fails part-way through persisting the set
- **THEN** the stored set is exactly what it was before the run, and the step exits non-zero with the reason on stderr
