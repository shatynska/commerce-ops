## ADDED Requirements

### Requirement: A launch's detail page distinguishes a step that has not started

A launch's detail page SHALL render every served step whether or not the launch has released it, and SHALL distinguish those it has not released. Hiding them is forbidden: the page exists to show the launch's whole plan against its position, and a page showing less than the playbook would misrepresent what the launch is committed to.

An unreleased step SHALL carry a mark saying what it is waiting for — the gate it starts at, the steps it waits on, or both — so that a reader can tell a step nobody has begun from a step nobody *may yet* begin. The two are different facts about the launch and the surface SHALL NOT collapse them: a step that is unrecorded and released is work outstanding, and a step that is unrecorded and unreleased is work not yet asked for.

The mark's wording SHALL be drawn from *starting*, and SHALL NOT use *blocked* or any inflection of it. This surface already renders a step's `blocking` declaration and the `Blocked` step outcome, which are two distinct senses of the word on one page; a third would make the page unreadable. A step's own gate and its start gate SHALL likewise be worded so that neither can be read as the other.

A step whose start gate the launch has not reached SHALL NOT be marked overdue. The page SHALL NOT reach that conclusion itself: the overdue judgement is taken from the launch report, as this capability already requires, and `launch-instance` carries the rule. Stated here as what the page renders rather than as what it decides — a surface suppressing the mark on its own would leave the page, the report and the daily briefing saying different things about one step, which is the arrangement carrying the fact on the report exists to prevent.

A step the launch has reached but which waits on an unresolved dependency MAY be both marked overdue and marked as waiting, and the page SHALL render both rather than letting either suppress the other. The two say different things — the work is late, and this is what it is late behind — and a reader needs them together.

#### Scenario: An unreleased step is rendered, not hidden

- **WHEN** a launch standing at `commit` is rendered and its served playbook carries steps that start at `listable`
- **THEN** those steps appear on the page under their own gates

#### Scenario: An unreleased step says what it waits for

- **WHEN** a step the launch has not released is rendered
- **THEN** it carries a mark naming the gate it starts at, the steps it waits on, or both

#### Scenario: Unreleased is distinguishable from unrecorded

- **WHEN** a page renders one released step with no recorded outcome and one unreleased step with no recorded outcome
- **THEN** the two are distinguishable from one another on the page

#### Scenario: A released step carries no such mark

- **WHEN** a step the launch has released is rendered
- **THEN** it carries no start mark, whatever it declares

#### Scenario: A step whose start gate is not reached is never marked overdue

- **WHEN** a step whose start gate the launch has not reached has a due period that has passed
- **THEN** it is not marked overdue, the launch report not stating it as overdue

#### Scenario: A step waiting on a dependency can be both overdue and waiting

- **WHEN** a step the launch has reached waits on an unresolved dependency and the report states it as overdue
- **THEN** the page renders both the overdue mark and the mark naming what it waits for

#### Scenario: The page carries no third sense of blocked

- **WHEN** the detail page is rendered for a launch with unreleased steps
- **THEN** no mark introduced for release uses the word *blocked* or an inflection of it
