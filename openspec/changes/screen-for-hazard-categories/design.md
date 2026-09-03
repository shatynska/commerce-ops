## Context

See `proposal.md` — Why. The mechanism this change plugs into shipped one change ago and
is not built here: a handler reports a typed finding, the automation pass looks up a sink
by step identifier and writes the value, and the finding is kept on the recording the
write belongs to. One sink is registered today, for `lp.listing.007`.

Three facts about that mechanism constrain everything below, and each is already
specified rather than incidental:

- The write happens **when the handler runs**, before any confirmation is sought
  (`launch-step-automation`, *A handler's supported finding is recorded independently of
  the step's own confirmation*). `lp.strategy.006` names a confirmer, so its outcome is
  held; the write is not.
- A finding whose value is **empty** is a present finding, carried and rendered as such,
  and distinct from a recording carrying none (`launch-instance` for the carrying,
  `launch-admin` for the rendering). Both cover *emptiness* generically. Neither covers a
  value carrying **several members** — `launch-admin` fixes the field, the wording, the
  empty-value text and the result/comment structure, and stops there, which was right
  when every finding was a string. The implementation already renders a sequence as its
  members and refuses to treat a string as one; nothing in the specification says it
  must, so this change adds that clause rather than claiming it was already there
  (Decision 8).
- The field name and its wording come from the **sink registration**, never from the
  handler. The handler reports a value and a comment and does not know where they go.

The screen itself is `strategy.compliance_screen`, on a step authored `blocking: false`
with a confirmer, resolving through three verdicts and, today, reporting no finding at
all — a requirement `screen-a-product-for-compliance` wrote explicitly and expected this
change to succeed.

## Goals / Non-Goals

**Goals.** Give the product a place to hold what the screen found, in the three states
that fact actually has; make the screen report it; make the one surface that can show it
show it. Add no mechanism.

**Non-goals**, beyond the proposal's: no consumer of the field; no reconciliation between
a written value and a rejected proposal; no canonical category vocabulary; no change to
the pass, the sink lookup, or the confirmation flow. Nothing about how the launch module
*carries* a finding is modified — `launch-step-automation` and `launch-instance` take no
delta, which is the check that this change is the consumer the last one was built for
rather than an extension of it. One clause is added to how the launch module *renders*
one, for the reason Decision 8 gives.

## Decisions

### 1. Storage is a nullable `text[]` on `products`, not `jsonb` and not a join table

Three states must be representable and distinguishable: `NULL` (never screened), `{}`
(screened, clear), `{'supplements'}` (flagged). A nullable array gives all three natively,
with the distinction enforced by the column's own nullability rather than by a
convention a later reader must know.

- **`jsonb` rejected.** It would also work, and it would admit `null`, `[]`, `{}`, `""`
  and `0` as five spellings of roughly the same thing. `launch-instance` had to write a
  requirement — *the value's own emptiness SHALL be represented one way only* — precisely
  because its own storage is `jsonb` and could not enforce it. A `text[]` cannot express
  the confusion, so the guarantee is structural rather than asserted.
- **A join table rejected.** `product_hazard_categories` would make the empty set and the
  absent set the same zero rows, which is the one distinction this change exists to
  create; recovering it would need a second "screened at" column, which is a nullable
  column doing the work of the nullable array with a table around it. There is also no
  query this change or any named successor makes that a join table serves better.
- **A second `screened_at` column rejected** for the same reason in the other direction:
  it would make the state a function of two columns that can disagree, and nothing
  prevents `screened_at` set with `hazard_categories` null.

The column is `hazard_categories text[] NULL` with no default and no check constraint.
No default, because a default of `'{}'` would declare every existing product screened and
clear — the exact falsehood the three-state rule forbids, applied to the whole catalog at
migration time. Existing rows take `NULL`, which is correct rather than merely convenient:
none of them has been screened.

### 2. The wire schema gains `categories: list[str]`, flat and required

`ScreenResponse` becomes three fields — `verdict`, `categories`, `comment` — and stays
flat. The constraint driving this is documented at length in the handler already and is
not re-derived: OpenAI's strict structured outputs accept `anyOf` and not `oneOf`, and
`langchain_openai`'s conversion accepts a `BaseModel` and not a top-level union. A
`list[str]` emits `{"type": "array", "items": {"type": "string"}}`, which is inside that
subset and introduces no union at all.

**Not a per-verdict variant.** The obvious modelling — categories present only when
flagged — is a tagged union, which is the construct that made `lp.listing.007` inert in
production. The same trade the existing schema made for `verdict` is made again here: one
flat required field, with the coupling to the verdict expressed in the field's own
description, which the model reads, and enforced afterwards by the two contradiction
routes.

**Required of the model, defaulted in Python — two different senses of "required", and
only the first is this decision's.** Under strict structured output every property is
required, so the model must send `categories` whatever the Python declaration says; a
model with nothing to put in it emits `[]`, which is why `[]` is the ordinary `clear`
answer rather than a special case. That is the same reasoning `_blank` already encodes
for `comment`.

Established by running the conversion rather than by argument, which is what this
capability's own schema requirement demands of exactly this kind of claim:

```
convert_to_openai_tool(ScreenResponse, strict=True)
  required: ['verdict', 'categories', 'comment']        # every property, defaults included
  categories: {"type": "array", "items": {"type": "string"}, "description": …}
  oneOf anywhere: False
ScreenResponse.model_json_schema()                       # without strict
  required: ['verdict']
```

So the field is declared `default_factory=list`. Declaring it with no default would
change nothing about what the provider requires and would additionally oblige every
*caller* to pass it — breaking roughly sixty existing tests that script the wire model
as `(verdict=…, comment=…)`, and forcing edits to tests this change has no business
editing. `comment` is already declared this way for the same reason.

`compliance-screen`'s existing schema requirement already demands that the conversion be
exercised against the provider's own adapter, at the call site's schema, and that every
combination the wire can express have a defined destination. Adding a field widens the
combination space; it changes nothing about what that requirement asks, so it is not
modified. The new combinations get destinations from the two contradiction requirements
and the flagged-naming-nothing requirement.

### 3. The contradictions are structural, and each gets its own reason

Three new routes, and they are separated because `compliance-screen` already requires that
three different things that happened read as three different sentences:

| response | destination | finding |
|---|---|---|
| `clear` + non-empty `categories` | non-terminal, its own reason | none |
| `flagged` + empty `categories` | non-terminal, its own reason | none |
| `undetermined` + anything | existing undetermined reason | none |

Neither new route reads prose. That is the point of putting them here rather than
extending `_screen_refuses`: the existing veto is a regex over a comment, with a long
docstring recording how its first version was too generous and blocked the step on every
pass. A structural check cannot have that failure mode, so it is cheaper *and* stronger,
and it is worth saying in the module why the two live side by side rather than being
unified.

`clear` + categories joins the existing "a verdict its own response contradicts" —
it is literally that, and satisfying the step there is the expensive error. `flagged` +
no categories gets its own requirement because it is not about satisfaction at all: a
flagged verdict never proposes satisfaction, so the existing requirement has nothing to
say about it, and folding it in would make that requirement's name false.

### 4. Category names are the model's, normalised, deduplicated, and never validated against the description

Per the decision already taken: the model is instructed to name categories in the
description's own wording, and **no code parses the description to check it did.**

The reason is not laziness, and the specification says so: the seeded description of
`lp.strategy.006` is

> "Screen against **the FBA-prohibited hazmat list** and high-compliance categories
> **(furniture, medical devices, supplements, grills, fire pits, balloons, lighters, CO
> detectors)** before sourcing"

— a *referenced list* whose members the description does not enumerate, plus eight inline
examples. Any parser that could validate a name against this description would validate
against the eight and reject a correct answer drawn from the referenced list. The handler
already refuses to extract from this prose for exactly this shape of reason, at length,
and building a validator on the extraction it refuses would contradict itself. So the
obligation lives in the prompt.

The accepted cost, stated in the spec rather than buried: recorded values are as stable as
the authored description; a category reached through the referenced list has no authored
wording; re-authoring the description leaves earlier recordings spelled the old way. A
consumer must treat the field as a report, not as identifiers.

**Normalisation is whitespace and case only** — `strip()` and casefold-compare for
equality, preserving the model's own casing in what is stored. Deduplication follows,
first-occurrence order preserved, because `product-catalog` records a *set*. Order is
otherwise not canonicalised: sorting would be a transformation the "carry it through
unaltered" rule forbids for no gain, since replacement is wholesale and nothing compares
two recordings for equality.

- **A closed authored vocabulary with identifiers was rejected** during exploration. It
  would give stable values and would require a second authored artifact beside the
  description, kept in step with it by nothing — the drift this capability's central
  requirement exists to prevent, reintroduced one level up.
- **Free text with no instruction was rejected**: it costs nothing and gives values no
  consumer can group on.

### 5. The provisional write stands; `product-catalog` says what it means

A `clear` verdict writes `{}` to the product when the pass runs, and the outcome is then
held for the confirmer. **If the member rejects it, the `{}` remains written.**

This is not a defect introduced here and not a question left open.
`launch-step-automation` states it outright — *a step's own outcome and the last value
recorded from its finding MAY disagree … reconciling the two is not this requirement's
concern* — and delegates the meaning: *the value written to the product before the
proposal was made stands or falls by `product-catalog`'s own rules.* This change writes
those rules, and they say the value stands.

The case has never arisen because `lp.listing.007`, the only step with a sink today, names
no confirmer. `lp.strategy.006` does, so this change is where the delegation is answered.

Three alternatives, and why not:

- **Move the write to the accept path.** Would make the value mean "ratified", which
  reads better. It is a mechanism change one change after the mechanism shipped, it
  changes `lp.listing.007`'s behaviour too or needs a per-sink flag, and it loses the
  property the mechanism was built for — that a fact is available immediately, before a
  member gets round to deciding. Declined.
- **Write only on `flagged`.** Removes the awkward case by removing the empty set, which
  is the entire point of the change. Declined.
- **Erase on rejection.** Would leave the product reporting the question as *open* after
  it had demonstrably been screened — the one confusion the three-state rule exists to
  prevent. Declined.

What the rejection *does* cost is a rendering obligation, and it is specified: the dossier
must present the field as what a screening established, never as something confirmed or
accepted. The launch's own recording remains the record of the decision, and it correctly
carries no finding for a rejection.

### 6. `SubCategoryRecorder` is replaced by one generic `FindingRecorder`

`separate-the-result-from-the-comment` left it deliberately, recording in its own tasks
that *widening it belongs to the change that adds a second sink with a different value
type.* This is that change, so the deferral is discharged here rather than deferred again.

Replaced, not widened. The Protocol names one field in its type (`sub_category: str`) and
is satisfied structurally by a partial application nothing type-checks against it;
`FindingSink.record` is already `Any`, so the Protocol is decorative today and would be
actively misleading the moment a second sink carries a list. It becomes:

```python
class FindingRecorder(Protocol):
    """Records a handler's supported finding against a product …"""

    async def __call__(self, product_id: ProductId, value: Any) -> object: ...
```

One port for every sink, honest about being a shape. `SubCategoryRecorder` is removed from
`launch/application/__init__.py`'s `__all__`, which is a public-surface change — the
export list and `worker.py`'s reference to it move in the same commit. Nothing outside
this repository consumes that surface.

Deleting the port outright was considered. Declined: this codebase names and explains its
ports (`SteadyStateStamper`, `LaunchStore`, `Playbooks`), and the replacement is where the
explanation of *why* the value type is loose can live.

### 7. The dossier gets a third region and a third absence reading

The two catalog-written facts are neither identity nor retained results, so they go in
their own region marked `established-by-automation` rather than being folded into the
identity list — where they would read as things somebody registered.

`sub_category` is rendered too. It has been written since
`write-the-advisors-finding-to-the-product`, `product-catalog` specifies a read for it,
and no surface has ever shown it. Rendering only the new field would leave that true and
would make the convention ambiguous for the next author. It is two states and uses the
page's existing `not-recorded`.

Hazard categories need a **third** marker, `screened-clear`, and this is the design-level
point of the whole surface change. The page's absence vocabulary has exactly one word,
`not-recorded`, and it answers "this fact has no value". "Screened, nothing found" is not
that: it is a positive finding whose content is empty. Rendering it as `not-recorded`
would tell an admin that a screened product is unscreened — collapsing, on the only
surface that shows the field, the distinction the storage was extended to keep.

The marker's presentation goes in `vocabulary.css` with the page's other markers;
`product-dossier` forbids page-local styling and this is the change most likely to reach
for it.

### 8. `launch-admin` gains a clause, because the code has behaviour the spec never stated

`_render_finding_value` already joins a sequence's members, already refuses to treat a
string as a sequence, and already renders an empty value as readable text. Only the last
of those is required by `launch-admin`. The first two were written correctly and
specified nowhere — which was harmless while `sub_category` was the only finding, and
stops being harmless the moment a value carries several members on the surface members
actually read.

So the requirement gains three clauses: members render as members, each readable and
separated; a string is one member and not a sequence of characters; and emptiness
continues to outrank both. What is *not* fixed is how members are separated — that is the
same kind of visual judgement the requirement already declines to fix for weight and
spacing, and fixing it would pretend a test can decide it.

This is a specification catching up to an implementation, not a behaviour change, and the
task list says so: the expected diff to `launch_admin.py` is empty, and the test derived
from the new scenarios should pass on the first run. **A test that passes immediately is
the expected outcome here and is not evidence the test is worthless** — it is a
regression guard on behaviour that currently nothing would notice the loss of.

- **Rejected: compose the rendered string at the sink.** It would put presentation in the
  composition root and would contradict `product-catalog`'s recording of a *set* and
  Decision 4's deduplication, which both need the members to still be members.
- **Rejected: leave it unspecified and note it as an open question.** Cheapest, and
  consistent with how the `screened-clear` wording is deferred. Declined because the
  equivalent question for the empty value was thought worth a requirement one change ago,
  and a flagged screening is the case a member is most likely to act on.

## Risks / Trade-offs

- **A member rejects a `clear` proposal and the product still reads "screened, clear".** →
  Accepted and specified (Decision 5). Mitigated by the dossier's obligation never to
  present the field as confirmed, and by the launch recording, which correctly keeps no
  finding for a rejection. The correction path is a later screening.
- **Category values are as stable as an authored description an admin can edit without a
  deploy.** → Inherent to the decision already taken, and inherited from
  `compliance-screen`'s central requirement rather than introduced. Mitigated by the
  citation the screen already renders into its produced text, which leaves a trace of what
  was screened against on every launch it ran on.
- **A category from the referenced FBA list has no authored wording to match.** → Stated
  in the spec as a limitation of the field, with consumers told to treat it as a report
  rather than as identifiers. No consumer exists yet, which is the cheapest moment to say
  so.
- **A widened wire schema is a new chance to fall outside the provider's strict subset.**
  → `compliance-screen` already requires acceptance be established by the provider's own
  conversion at the call site's schema, with no model call. That guard exists and covers
  the new field; the risk is that someone adds the field without extending the guard's
  coverage of the combinations, which the every-combination-has-a-destination requirement
  is what catches.
- **Two contradiction checks now live beside each other, one regex and one structural.** →
  A later author may try to unify them. The module must say why they are separate: one
  reads prose and has a documented history of over-matching, the other reads structure and
  cannot.
- **A worktree cannot run the integration tier without its own `.env.test`,** and
  `pre-push` reports the skipped tier as `Passed`. → Named in the tasks as a step, not a
  tip: create a database whose name ends `_test`, `alembic upgrade head`, then
  `uv run python -m commerce_ops.seed_playbook`.

## Migration Plan

One Alembic revision, parented on `b62d05f1ae37` — currently the single head
(`uv run alembic heads`) and what production runs. Adding a nullable column with no
default is a metadata-only operation in Postgres: no table rewrite, no lock held for the
length of a scan, safe against a running container.

`uv run alembic heads` must report one head before the branch is pushed. Two revisions
parented on the same ancestor merge green and then break `alembic upgrade head` on the
host; the fix is to re-parent on the newer revision and rebuild, proved rather than
assumed.

Rollback is the revision's own downgrade, dropping the column. It is lossy by nature —
the screenings recorded into it are gone — which is acceptable for a field nothing yet
consumes and no other table references.

Deployment order is the ordinary one: the migration is applied by the deploy, and the
column is nullable, so the previous image is compatible with the new schema and the new
image is compatible with rows that predate it. No backfill: `NULL` is the correct value
for every existing row.

## Open Questions

- **How the `screened-clear` state reads in words** — "Screened, no categories found" or
  another phrasing — and its treatment in the shared stylesheet. Deferrable: the marker,
  the three-way distinction and the prohibition on rendering it as an absence are all
  specified, and the wording behind the marker changes no test derived from them. Settle
  it against the running page, as the Outcome column's treatment was.
