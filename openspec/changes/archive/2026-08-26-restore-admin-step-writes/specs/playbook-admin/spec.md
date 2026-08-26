## ADDED Requirements

### Requirement: Every write is judged against the same roster the page reads

The page reads the roster to render a step's assignees and to offer who can be named. The writes it makes are judged against the roster too, by the preconditions `playbook-authoring` owns and states — this requirement adds no rule of its own about who may be named. What it adds is that both readings SHALL reach the **same** roster: whatever the page offers as an assignee, a write from that page SHALL be able to name, and whatever a write refuses on roster grounds SHALL be explicable from what the page itself displayed.

No write SHALL be refused **on roster grounds** for a reason that cannot be explained by what the page displayed. This binds refusals about people; it says nothing about a write failing for other reasons, which is the subject of *A write that fails is never silent* below.

#### Scenario: A write names a person the page offered

- **WHEN** an author saves a step naming an assignee the page offered them in the assignee control
- **THEN** the write is judged on the rules, not refused for being unable to read the roster
- **AND** the step is saved naming that person

#### Scenario: Each write reaches the roster

- **WHEN** a create, an edit, a status change, a retirement or an un-retirement is submitted from the page
- **THEN** each one evaluates its roster preconditions against the roster the page reads

#### Scenario: A roster refusal is explicable from the page

- **WHEN** a write is refused on roster grounds
- **THEN** the refusal concerns people the page displayed or offered, and never the page's inability to read the roster at all

### Requirement: A write that fails is never silent

Every write the page offers SHALL report its outcome to the admin. A write that is refused renders its faults, as this capability already requires. A write that fails for a reason the page has no fault rendering for SHALL still be reported.

No write SHALL be able to leave the page in a state indistinguishable from one where nothing was submitted, and no failed write SHALL be able to leave the page looking as though it succeeded. This binds every write on the page, whether submitted as an ordinary form post or through the page's progressive enhancement — an enhancement that discards a failed response is exactly how a whole page of broken writes went unnoticed. It binds all three ways such a submission can fail: a response the page cannot render, no response at all, and a response that never arrives in time.

What the report SHALL say is bounded by what the page can establish. The page observes that a submission did not complete; it does **not** observe whether anything was persisted, because a failure raised after the set was written produces the same response as one raised before it. The report SHALL therefore state that the write did not complete and that what the page is showing may no longer describe the step set, and SHALL direct the admin to reload to see the set as it stands. It SHALL NOT assert that nothing was saved.

The report SHALL be observable in the rendered response. The container it renders into SHALL carry the literal marker `write-failure-notice`, which names the container's **role** and is therefore present on every admin page whether or not anything has failed; the marker `write-failed` SHALL appear only once a failure has actually been reported into it. The distinction is the one this capability already draws for `just-created` — a marker that asserts an occurrence must never outrun the occurrence. Whether the notice then *appears* on a live failure is confirmed by inspection; that there is a container for it to appear in is not.

Which submissions this page enhances is fixed here rather than left to the templates to decide, because two of the clauses below turn on it: as of this change the step list and the edit surface are enhanced, and the create surface is not. A later change to that set SHALL amend this requirement rather than silently narrow what an admin is told — otherwise un-boosting a form would shrink the guarantee with no test failing and nothing recording that it had shrunk.

Where a submission the page enhances fails because the admin's own session has ended, the report SHALL say so and offer the way back, rather than presenting an expired session as an unexplained failure — it is the one case in this class the admin can act on directly. The page SHALL reach that reading from what it already knows (it posted to a route it had just rendered, so a refusal of that route is the guard's), and SHALL NOT require the server to mark the refusal. The guard's answer to a write SHALL stay indistinguishable from an unregistered route's — the shape `playbook-admin` already describes for every unauthorised admin path, and binding here on this requirement's own account.

A submission the page does **not** enhance — one deliberately left un-boosted, or any submission where the enhancement is unavailable — satisfies this requirement through the browser's own rendering of the failure. That is less legible and carries none of the wording above, and it is accepted: what this requirement forbids is silence, not inelegance.

#### Scenario: An unanticipated failure is reported

- **WHEN** a write fails with a response the page has no fault rendering for
- **THEN** the page reports that the write did not complete and directs the admin to reload

#### Scenario: A failure with no response is reported too

- **WHEN** a write submitted through the page's progressive enhancement receives no response, or none in time
- **THEN** the page reports it exactly as it reports a failed response, rather than remaining as it was

#### Scenario: The report does not claim what the page cannot know

- **WHEN** any such failure is reported
- **THEN** the report does not state that nothing was saved

#### Scenario: A failed write does not read as a successful one

- **WHEN** a write fails before the set is written
- **THEN** the page does not render as though the write was accepted, and the step set is unchanged

#### Scenario: A failed write does not read as an unsubmitted one

- **WHEN** a write submitted through the page's progressive enhancement fails
- **THEN** the page changes in a way the admin can see, rather than remaining exactly as it was before submitting

#### Scenario: The report is observable in the response

- **WHEN** an admin page the failure report can render into is served
- **THEN** it carries a container marked `write-failure-notice`, so a response can be asked whether there is somewhere for the report to appear
- **AND** that container carries `write-failed` only once a failure has been reported into it

#### Scenario: An ended session says so

- **WHEN** a submission from the step list or the edit surface fails because the admin's session is no longer live
- **THEN** the page says the session ended and offers the way back, rather than reporting an unexplained failure

#### Scenario: The guard's refusal stays indistinguishable

- **WHEN** the page distinguishes an ended session from any other failure
- **THEN** it does so from what it already knew about the route it posted to, and the server's refusal is not marked to make it recognisable

#### Scenario: A failure is visible on a submission the page does not enhance

- **WHEN** a write fails on a submission from the create surface, or on any submission where the enhancement is unavailable
- **THEN** the failure is still visible to the admin, even if less legibly presented and without the wording above
