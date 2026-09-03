## Why

An automated handler already produces two different kinds of thing: a **result** — the
fact it established, structured and typed — and a **comment**, the model's prose about how
it got there. `StepResolution.finding` carries the first; `result` carries both, run
together as one block of text.

At the recording boundary the structure is thrown away. A supported finding is passed to
whatever recorder the step names and then dropped; what the launch keeps is `evidence`, a
single `character varying` holding the handler's rendered text. So the Outcome column on
the launch detail page has nothing to render but that blob, clamped to two lines, with the
established fact and the model's reasoning indistinguishable inside it.

Three consequences, and they are the reason for this change rather than a tidy-up:

- **A reader cannot tell what was recorded from what the model said about it.** On a
  compliance step that difference is the whole point: "no hazardous categories" is a fact
  the launch now asserts; the paragraph after it is a language model's argument. They read
  as one paragraph today.
- **Nothing downstream can read the fact.** A later step that wants what an earlier one
  established has only prose to parse — the fragility this project has already retired
  twice, in `separate-the-verdict-from-the-prose` and again in
  `fix-subcategory-advisor-structured-output`.
- **The findings already being written are invisible.** `lp.listing.007` has written a
  typed sub-category finding to products since `write-the-advisors-finding-to-the-product`,
  and it is rendered on no page. The mechanism exists and has never been shown to anyone.

This change is the mechanism half. It makes a recording able to carry the finding that
produced it, and makes the Outcome column render the fact before the prose. The compliance
category array, the catalog field it lands in, and the dossier showing it are the second
half (`screen-for-hazard-categories`), which builds on this and is not proposed here.

## What Changes

- **A recording may carry the finding that produced it** — the field the value was written
  to, the value, and the finding's comment — alongside its evidence, never instead of it.
- **A carried finding survives the wait for a confirmer.** This is the part that decides
  whether the change works at all. A finding is written to its sink when the handler runs,
  but a *terminal outcome on a step naming a confirmer is held*, and its recording is made
  only when a member accepts. Both steps that exist today sit on opposite sides of that
  line — `lp.listing.007` names no confirmer and is recorded by the pass;
  `lp.strategy.006` names one and is held. So the finding travels with the pending result
  and is carried onto the recording that acceptance makes. A rejection carries none.
- **The field's name comes from the sink registration, not from the handler**, together
  with the wording an admin reads. A handler continues to report a value and a comment and
  to know nothing about where either goes — the rule `subcategory-advisor` set and this
  change must not weaken.
- **The Outcome column renders the carried result first, then the comment.** Field and
  value, with no leading prose; then the comment as a distinct block. A recording carrying
  no finding renders exactly as today.
- **The two are distinguished by more than colour**, with literal markers named in the
  specification so a test can assert them, and the visual judgement settled by looking at
  the running page.

### Non-goals

- **No new product field, and no change to any catalog use case.** This change carries and
  renders what a finding already has. `products.hazard_categories`, the compliance array
  and the dossier belong to `screen-for-hazard-categories`.
- **No change to what `evidence` means or to when it is written.** It stays the verbatim
  text a member read and decided on. The carried finding sits beside it, and a rendering
  change must never rewrite the record of what someone was shown.
- **No change to the Slack rendering of a held result.** A pending result still reaches a
  member as the handler's produced text. Splitting that message is a separate question with
  its own audience.
- **No change to the dossier.** This change *does* add a column to `automated_step_results`,
  the retained-results store the dossier renders from — so the store is touched, and saying
  otherwise would be false. What is not touched is what the dossier renders: adding a stored
  column obliges no surface to show it, and `product-dossier` enumerates each entry's fields
  independently. The dossier would benefit from the same split, and that is deferred rather
  than absent.
- **No handler is asked for anything new.** Every existing handler keeps its signature and
  its output.

## Capabilities

### New Capabilities

None. This change extends three capabilities that already exist and introduces no new one.

### Modified Capabilities

- `launch-instance`: a recorded outcome MAY additionally carry the finding that produced it,
  and a carried finding travels on the launch report's step entry. Stated as additions: what
  a recording already carries, and when it is written, are unchanged.
- `launch-step-automation`: a written finding is kept on the recording it produced —
  including surviving as part of a pending result until a member accepts it. The existing
  requirement that a finding *changes nothing* about the outcome or the result continues to
  hold unqualified: this adds a third thing kept beside them and alters neither.
- `launch-admin`: the launch detail page states a carried finding's field and value ahead of
  the comment, distinguished from it by more than colour.

## Impact

- **Schema**: a nullable `jsonb` column on `launch_step_progress` **and** on
  `automated_step_results`, plus one migration. The second column is what carries a finding
  across the wait for a confirmer.
- **Modified**: `launch/application/ports.py` (a sink carries its field's name and wording),
  `launch/infrastructure/driving/automation_pass.py` (keep what was written, or hand it to
  the pending result), the accept path in `launch/application` and
  `automation_confirmation.py` (carry it onto the recording acceptance makes),
  `launch_admin.py` and `launch.html` (render it), `worker.py` (one registration), and the
  two repositories with their row mappings.
- **Presentation**: `vocabulary.css` gains a token for an established fact if it has none;
  the non-colour treatment is a stylesheet rule, since the page carries no styling of its
  own.
- **Backward compatibility**: both columns are nullable and every existing row has no
  finding, which is the state that renders as today. No backfill, and no migration of the
  25 rows `lp.strategy.006` has already written.
- **Tests**: `tests/unit/launch/` for keeping, the pending-result hop and the row mappings;
  `tests/unit/launch/infrastructure/` for the rendering; `tests/integration/launch/` for
  both columns round-tripping.
