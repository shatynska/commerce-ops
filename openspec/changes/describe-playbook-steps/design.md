## Context

`StepDefinition` carries an identifier, a provenance citation and nine other declared attributes, but nothing stating the work. The wording lives only in `docs/reference/product-launch.md`, which nothing at runtime reads — it is a document for people, parsed once during `author-playbook-steps` to derive identifiers and provenance, then left behind.

The shipped playbook's 97 steps each already point at exactly one reference row, and that row's text sits on the line above the row's metadata line. So the descriptions are not written fresh: they are transcribed from rows the playbook already names. See proposal.md for motivation.

`launch_positions` was empty on the deployment when `author-playbook-steps` checked it. This change does not inherit that: **task 1.2 re-confirms it and is still open**, so the statements below hold pending that check. If a launch has started since, no task is renamed — the sync never renames a mapped task — and the list simply carries both namings.

## Goals / Non-Goals

**Goals:**

- A step states its own work, so nothing downstream needs the reference document to render a step for a person.
- A projected ClickUp task reads as work in the list, without losing traceability to its step.
- The transcription is mechanical and checkable against the source, not retyped by hand.

**Non-Goals:**

- Rewording, shortening or editorialising the reference document's text. The row's wording is the team's; this change moves it, it does not improve it.
- Carrying any other reference column into the playbook (`OUR RULE` stays the team's to fill; `LVL` is document structure, not step data).
- Any change to how completion, due dates, mapping or reconciliation work. Only the task's *name* changes.
- Localising or templating the description. One line, one language, as the source has it.

## Decisions

### 1. `description` is required, not optional

A step whose work cannot be read from the step itself is, to the person asked to do it, indistinguishable from a step nobody wrote down — which is the defect this change removes. An optional field would let that state persist silently and would leave every consumer writing a fallback for the absent case.

The emptiness rule lives with the other playbook coherence rules (rejected at load, naming the step), not as a constructor rule on `StepDefinition`, matching how `MetricCondition`'s empty-threshold rule is already handled: a malformed authored value reports *where it was authored*.

Alternative considered: optional, defaulting to the identifier. Rejected — a description that falls back to `lp.creative.008` reproduces exactly the task name this change exists to eliminate, while making the failure invisible.

Cost, stated plainly: roughly sixteen per-file `_step(**overrides)` test factories each gain a default description. That is one line per factory, and it is the price of the field being a guarantee rather than a hope.

### 2. Transcribed at authoring time, never read at runtime

The descriptions are extracted from the reference document by a one-off script and written into `playbook_v1.yaml`, exactly as the identifiers and provenance citations were.

Alternative considered: have the ClickUp sync resolve the text from the markdown document when it creates a task. Rejected on two counts — it makes a hand-maintained document a production dependency of a deploy, and it breaks silently on reformatting, at the moment of task creation, where the failure is least visible. The repository owns the playbook definition (README, "State ownership"); a document that happens to sit in the same repository is not the same thing as data the system owns.

### 3. The row's text is transcribed verbatim, with a closed set of terminal marks trimmed

Reference rows are fragments of a nested list, and end variously. Trailing whitespace is stripped, then any trailing `;` `:` `,` or `.`, repeating until neither remains. Nothing else is altered — no case change, no re-wrapping, no expansion of the document's abbreviations.

The stripped set is closed, and deliberately narrower than "trailing punctuation". Measured across the 97 shipped rows: 14 end in `.` and 3 in `:` — terminal marks of a fragment, and better removed from a task title. But 5 end in a closing quote, 3 in a closing parenthesis, and 2 in `+` (as in "A+"), and those are content. A broader rule would render `lp.creative.019` as "…answered inside A", corrupting the text this decision exists to preserve. One row (`lp.rank.003`) ends "(worked example:" and reads badly under any rule — it is truncated in the source, and the route for that is editing the reference document, per the third risk below.

This keeps the transcription checkable: a test can re-derive every description from the document and compare, the way `author-playbook-steps` does for provenance. A description that had been "improved" could not be checked that way.

### 4. Task name is `<description> · <identifier>`, and discipline leaves the name

The separator matches the one the name already uses. Discipline drops out because the identifier's second segment already encodes it (`lp.creative.008` is a `creative` step) — verified across the shipped set on 2026-08-24, where all 97 identifiers' second segment equals the step's declared discipline, and asserted by task 3.3 rather than left as an observation, and name width spent restating it costs the reader the wording this change exists to surface. Discipline remains on the step, in the briefing, and on this playbook's own surfaces.

Among today's 97 steps the worst case is **225 characters** (`lp.listing.019`), with a median of 136. The shipped set is deliberately incomplete — every non-`BUILD THE LISTING` gate carries only a representative subset — and across all 358 rows of the reference document the worst composed name is **271 characters** (`lp.strategy.023`).

**The limit, measured (task 1.1, 2026-08-24).** ClickUp's task-name limit is **2048 characters**, and the platform **rejects** an over-long name — `HTTP 400`, `{"err": "Task name invalid", "ECODE": "INPUT_005"}` — rather than silently truncating it. Measured against the live API: 300, 1000 and 2048 characters were each stored intact; 2049, 4096, 5000 and 20000 were each rejected. This was established empirically in a throwaway list, since ClickUp's published limits pages do not state it. **Unit, stated honestly:** the ladder used ASCII characters only, so it does not distinguish characters from bytes or UTF-16 units — and a composed name always contains a multibyte `·`, a shortened one also `…`. The constant is therefore applied as Python `len()` counts characters. At a worst case of 271 the distinction cannot bite; it would only matter for a name within a few characters of 2048, which this document cannot produce.

Two things follow, and the second corrects what this decision originally assumed.

First, rejection rather than truncation is the safe regime. Had ClickUp truncated, the cut would take the *tail* — precisely where the identifier sits — destroying traceability with no error anywhere. It does not, so an over-long name can never silently lose its identifier.

Second, **the shortening rule guards against something that cannot currently arise.** The worst composed name in the entire reference document is 271 characters, roughly one thirteenth of the limit. The original argument for specifying the rule now — that a later authoring session would fail at task creation inside a scheduled reconciliation run — does not hold at 2048. The rule is kept anyway, as a defensive guarantee rather than a fix for a live failure: `launch-clickup-sync` promises that no step fails to project merely because its description is long, and that promise is worth stating and cheap to honour. What is *not* claimed any more is urgency.

For the same reason the threshold this decision would otherwise need — the limit below which composing the name from the description stops making sense, around 150 given a median of 136 — is moot. 2048 is not near it.

The full description goes into the created task's body when shortening occurs, which needs no new capability: `clickup-task-client` already creates a task with a name and a description.

**Where the constant lives.** `clickup_sync.py` in the launch module, as a named constant rather than a bare literal. The number is a ClickUp fact and so arguably belongs with `clickup-task-client`, but what the launch module owns is the *policy* — cut the description, mark the cut, keep the identifier whole — and that policy is launch's, not the client's. The number travels with the policy that reads it.

### 5. The name is never the mapping, and is never rewritten

Making the name meaningful invites two assumptions, and both are wrong.

The first is that the name identifies the task. It does not: the sync resolves a step to its task through the recorded mapping, and a person editing a task's title in ClickUp must not cause a duplicate task on the next pass. The existing code already behaves this way; the delta spec now *states* it, so a future change cannot quietly start matching on names.

The second is more dangerous because the capability's own neighbouring requirement invites it. "Task due dates derive from the launch schedule" mandates that the system *update* a task whose due date has drifted from the resolved value — so the obvious symmetry is to keep names in step with descriptions too. That symmetry is false. A due date is derived with no human authorship, and restoring it destroys nothing; a task title is something a person may legitimately rewrite to suit their own list, and a pass that restored the authored name would silently discard that edit. The name is therefore set once, at creation, and never afterwards — stated in the delta so it survives beyond this conversation.

## Risks / Trade-offs

- [The playbook file grows by 97 long lines, and reviewing a step now means reading a sentence rather than scanning a code] → Accepted, and arguably the point. The file is authored data, read by people; a diff that shows the work changing is more reviewable than one showing an identifier changing.
- [The same wording now exists in two places — the reference document and the YAML] → Mitigated by Decision 3: the transcription is mechanical, and a test re-derives it from the document, so drift is a failing test rather than a silent divergence. Genuine duplication remains; the alternative (Decision 2) was worse.
- [A reference row's wording is a fragment, not a task title — some read oddly on their own] → Accepted for now. Rewording is explicitly a non-goal because the text is the team's; if specific rows read badly in ClickUp, editing those rows in the reference document and re-transcribing is the route, and it keeps one source. Stated plainly for the one case already identified: `lp.rank.003` ends "(worked example:" and is truncated in the source, so it **ships as-is** under this change and will read as broken text wherever it surfaces. Fixing it means editing that reference row, which is a separate change and not tasked here.
- [225-character task names may render awkwardly in ClickUp's list view] → Named rather than hidden, and still open. Task 1.1 established that ClickUp *accepts* such names (the limit is 2048), which settles whether they can be created but not whether they read well in a list; the five rows over 200 characters are the ones to look at first once a launch has projected.

## Migration Plan

No data migration and no schema migration — `StepDefinition` is a value object loaded from a file, never persisted. `launch_positions` is empty, so no projected task exists under the old naming; the first launch to start is named the new way from the outset.

Had tasks existed, they would have kept their old names: the sync never renames a mapped task, and the mapping is by task id. That is a property to preserve, not a gap to close, so this change does not add a renaming pass.

If task 1.2 finds a launch that started since the earlier check, that is the outcome: its already-projected tasks keep their code-only names, newly projected ones read as work, and the list carries both. That mixed naming is accepted rather than migrated, for the same reason — a name a person may have edited is not the system's to rewrite.

Rollback is reverting the field and the YAML together.
