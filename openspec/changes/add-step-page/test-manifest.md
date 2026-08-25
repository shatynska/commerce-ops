# Test manifest — `add-step-page`

Tests derived from this change's delta specs, before any of its
implementation was written. Written by `ai-toolkit:openspec-test-writer`
from the artifacts alone: this pass read the change's proposal, design,
tasks and delta spec, the served `openspec/specs/`, `AGENTS.md`, and the
existing tests under `tests/**/test_*.py`. It did **not** read the
implementation of the surface under test.

> **This manifest is not an OpenSpec artifact.** The schema does not know
> about it, so it will not appear among the context files
> `openspec instructions apply` lists. Whoever implements this change has
> to open it on purpose.

**The pass is additive only.** It adds tests and never subtracts: no
existing test was edited, deleted, disabled or weakened, and nothing was
written outside `tests/unit/launch/infrastructure/driving/` except this
file.

## Files written

| File | Covers |
| --- | --- |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_create_page.py` | MODIFIED *Steps can be created, retired and un-retired from the page* (14 of its 15 scenarios) and the two new scenarios of MODIFIED *The narrowed view survives every write and every move between views* |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_anchor_inputs.py` | ADDED *A timing anchor offers only the inputs its own kind uses* (4 scenarios) |

Both are in the unit tier, per `AGENTS.md` — *Testing Strategy*: routes
over a step-store double, no real I/O. Run either with

```
uv run pytest tests/unit/launch/infrastructure/driving/test_playbook_admin_create_page.py
uv run pytest tests/unit/launch/infrastructure/driving/test_playbook_admin_anchor_inputs.py
```

and a single test with
`uv run pytest <file>::<test name>` — every name below is selectable that
way.

## Baseline

`uv run pytest` at the worktree root, before any test here was written:

```
821 passed, 81 skipped, 0 failed
```

**Scope of the baseline: full.** The `tests/integration` tier was
collected and skipped in its entirety — it needs a live Postgres and
`DATABASE_URL` is unset in this worktree, which the tier reports per
skipped test. The two tiers this change's tests are written into
(`tests/unit`, `tests/agents`) ran green.

After adding these tests, the same command gives **20 failed, 821
passed, 81 skipped** — the 821 unchanged, so every failure is a new
test's and no existing test was disturbed.

## Scenario accounting

Every `#### Scenario:` block in
`openspec/changes/add-step-page/specs/playbook-admin/spec.md` is
accounted for exactly once. The delta carries **26** scenarios
(`grep -c '^#### Scenario:'`); **20** are covered here, one test each,
and **6** are recorded uncovered with their reason — one from the
creation requirement, five from the narrowing requirement.

### MODIFIED — Steps can be created, retired and un-retired from the page

| Scenario | Test |
| --- | --- |
| Creating is reachable regardless of how large the set is | `test_creating_is_reachable_regardless_of_how_large_the_set_is` |
| A created step appears in its gate | `test_a_created_active_step_appears_in_its_gate_and_is_addressed` |
| A step created as a draft is addressed where it renders | `test_a_step_created_as_a_draft_is_addressed_where_it_renders` |
| A created step the narrowing keeps visible is still identified | `test_a_created_step_the_narrowing_keeps_visible_is_still_identified` |
| A create the narrowing would hide is not left looking lost | `test_a_create_the_narrowing_would_hide_is_not_left_looking_lost` |
| A step named as created but not there is ignored | `test_a_step_named_as_created_but_not_there_is_ignored` |
| A draft the narrowing would hide is named like any other step | `test_a_draft_the_narrowing_would_hide_is_named_like_any_other_step` |
| A named step the offer could not reveal is ignored | `test_a_named_step_the_offer_could_not_reveal_is_ignored` |
| A rejected create keeps every submitted value | `test_a_rejected_create_keeps_every_submitted_value` |
| A rejected create keeps every assignee that was named | `test_a_rejected_create_keeps_every_assignee_that_was_named` |
| A rejected create keeps the submitted discipline | `test_a_rejected_create_keeps_the_submitted_discipline` |
| A create naming no discipline is refused, not defaulted | `test_a_create_naming_no_discipline_is_refused_not_defaulted` |
| A create naming a retired status is refused | `test_a_create_naming_a_retired_status_is_refused` |
| A stale create is surfaced, not silently dropped | `test_a_stale_create_is_surfaced_not_silently_dropped` |
| **A blocked retirement explains itself** | **uncovered — reproduced text** |

*A blocked retirement explains itself* is **deliberately uncovered by
this pass.** The delta reproduces it with one word changed ("the step
remains live" → "the step is not retired"), which `proposal.md` discloses
as a vocabulary correction rather than a behaviour change. It is already
covered by
`tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py::test_a_blocked_retirement_explains_itself`,
which passes today and asserts the same behaviour under the older
wording. `tasks.md` 2.1 excludes it by name.

### MODIFIED — The narrowed view survives every write and every move between views

| Scenario | Test |
| --- | --- |
| A rejected creation keeps the narrowing without leaving the create surface | `test_a_rejected_creation_keeps_the_narrowing_without_leaving_the_create_surface` |
| Opening and leaving the create surface preserves the narrowing | `test_opening_and_leaving_the_create_surface_preserves_the_narrowing` |
| **An accepted write keeps the narrowing** | **uncovered — reproduced from `reorder-steps-under-filters`** |
| **A rejected list-level write keeps the narrowing** | **uncovered — same** |
| **A rejected edit keeps the narrowing without leaving the form** | **uncovered — same** |
| **Opening and leaving an edit form preserves the narrowing** | **uncovered — same** |
| **Un-retiring keeps the retired steps visible** | **uncovered — same** |

The five uncovered scenarios are reproduced unchanged from the archived
`reorder-steps-under-filters` (except the disclosed "description search"
→ "text search" wording) and are covered, test for test, by
`tests/unit/launch/infrastructure/driving/test_playbook_admin_filtered_moves.py`:
`test_an_accepted_write_keeps_the_narrowing`,
`test_a_rejected_list_level_write_keeps_the_narrowing`,
`test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form`,
`test_opening_and_leaving_an_edit_form_preserves_the_narrowing`,
`test_un_retiring_keeps_the_retired_steps_visible`. `tasks.md` 2.1
excludes them by name. **They must still pass after this change** —
`tasks.md` 6.1 covers that.

### ADDED — A timing anchor offers only the inputs its own kind uses

| Scenario | Test |
| --- | --- |
| Only the selected anchor kind's inputs are offered | `test_only_the_selected_anchor_kinds_inputs_are_offered` |
| A rejection re-renders against the submitted anchor kind | `test_a_rejection_re_renders_against_the_submitted_anchor_kind` |
| An input two anchor kinds share stays offered for both | `test_an_input_two_anchor_kinds_share_stays_offered_for_both` |
| A value carried by a not-offered input does not reach the step | `test_a_value_carried_by_a_not_offered_input_does_not_reach_the_step` |

The requirement's normative sentence that no scenario states on its own
— *inputs rendered as not offered SHALL retain whatever value they carry,
and SHALL still be submitted* — is asserted inside
`_assert_anchor_offering`, which every one of the four tests calls: a
not-offered input must be hidden **and not disabled**. That is the half
`design.md` says `disabled` would silently break.

## What each failure establishes, on the first run

All 20 new tests fail. None fails at import; none is in the
"test itself is broken" state as far as this pass could establish, and
the harness was exercised against the live page to keep it that way (see
*Harness validation* below).

| Failure | Tests | State |
| --- | --- | --- |
| `no control on the list led to a create surface` | 17 | The list renders no control opening a create surface, which is the first scenario's own `THEN`. `GET {PAGE_PATH}/steps/new` does not exist yet (`tasks.md` 3.3). The assertions past this point have **not** been exercised. |
| `the list makes no offer for a named step the narrowing hides` | `test_a_step_named_as_created_but_not_there_is_ignored`, `test_a_named_step_the_offer_could_not_reveal_is_ignored` | Wrong value: the page renders no "falls outside the narrowing" notice at all (`tasks.md` 3.11). |
| `the 'start' input is offered, though it belongs only to anchor kinds other than 'offset'` | `test_only_the_selected_anchor_kinds_inputs_are_offered` | **The strongest state**: the code ran, against the live edit surface, and produced a wrong value. `_fields.html` renders all four anchor inputs unconditionally. |

**Two of these tests passed on their first run and were changed before
this manifest was written** — recorded here rather than quietly fixed.
`test_a_step_named_as_created_but_not_there_is_ignored` and
`test_a_named_step_the_offer_could_not_reveal_is_ignored` both assert
that *nothing* is said about a named step, and a page that renders no
notice at all satisfies that vacuously. Each now first asserts the
rule's **positive half** — a named step the narrowing hides, and
clearing it would reveal, *does* get the offer — so the absence
asserted afterwards is the rule applied rather than the notice being
absent. Both now fail, on that positive half.

## Assertion classification

Per assertion, the classification is written into the tests themselves
as `SPECIFIED` / `DERIVED` comments, in the idiom the sibling admin-page
tests established. Summarised:

**Specified** — traceable to a delta clause or scenario: that a create
control is rendered ahead of the gate tables and no create form within
or after them; that a landed create returns to the list under the active
narrowing; that an `active` create is last among its gate's active steps
and a `draft` holds no position and renders outside the gate's orderable
list; that a rejection re-renders the **create surface** with every
submitted value, every named assignee and the submitted discipline; that
a corrected resubmission's generated identifier carries that discipline;
that a create naming no discipline and a create naming `retired` are
refused without a create surface being rendered and persist nothing;
that the create surface offers no `retired` status; that a stale create
persists nothing and says the set changed; that the narrowing survives
both directions of the move to the create surface; and every clause of
the anchor requirement, including the retained-and-still-submitted half.

**Derived** — invented by this pass, and each is a correction point named
in its file's docstring:

- The addressing markers: the redirect `Location`'s `#step-<identifier>`
  fragment and the row's `id="step-<identifier>"`. `design.md` names
  both explicitly as the assertable markers of "addresses that step
  directly", so the *behaviour* is specified and only the spelling is
  derived. Correction point: `_ADDRESS_ID`.
- `created` as the query parameter carrying the created step's identity.
  `design.md` states the redirect shape; the spelling is the guess.
  Correction point: `_CREATED_PARAM`. The two landed-create tests assert
  the redirect carries it, so a rename surfaces there first.
- The notice's *wording* markers (`_OUTSIDE_WORDS`). Correcting a
  substring to the implemented wording is a fixture correction; dropping
  the assertion is not. The notice's **offer** is read behaviourally
  instead — a control carrying the `created` parameter, which
  `tasks.md` 3.12/3.14 make the offer's signature.
- Fault-wording markers on a rejected create (`brief`, and
  `assignee`/`person`), the same treatment the sibling tests record for
  the same faults.
- That a refusal with no rendered form and nothing persisted answers a
  `>= 400` status. The binding halves — nothing persisted, no create
  surface rendered — are asserted separately and unconditionally, so a
  project that answers a refusal differently loses only this line.
- `_HIDDEN_CLASSES` and `_ElementState`: how "rendered as not offered" is
  read off markup (`hidden`, `aria-hidden`, `display:none`,
  `visibility:hidden`, a hidden-ish class, or `input type="hidden"`),
  including inheritance from an ancestor element.
- `_plausible_value`: the window anchor's own input values, chosen from
  the rendered control so a rejection under `window` comes from the
  intended field fault and not from an anchor the write cannot parse.
- Two sanity guards marked `DERIVED` in place: that the gate's active
  steps *are* reorderable (so the draft's absence from the orderable
  list is about the draft), and that the page's read *does* return a
  retired step (so the retired case is the one the rule is written for).

**Deliberately untested** — identified and knowingly left uncovered:

- **Scroll position.** The delta's *so a browser lands on it rather than
  at the top* ends at the browser. `design.md` — Goals says so, and
  names the two server-observable markers instead; those are what these
  tests assert. Verifying that a browser actually scrolls is
  `tasks.md` 6.5, by hand.
- **`hx-boost="false"` on the three transitions** (`tasks.md` 3.6). No
  delta scenario states it; it is a mechanism protecting the fragment,
  and asserting the attribute would pin markup the spec does not fix.
  Verified by hand at 6.5.
- **The inline script re-applying the anchor state on change**
  (`tasks.md` 4.4). Liveness without a round trip is not observable in
  this stack — `design.md` says the requirement is written against the
  kind a surface *was rendered with* precisely so the server-rendered
  half is what the tests assert. Verified by hand at 6.5.
- **The identifier's dot-escaping in a CSS selector**
  (`tasks.md` 3.9/3.10). Browser-side; no server-observable difference.
- **The create surface's missing signed-out panel** (`design.md` —
  Risks). Accepted there as a known gap this change does not close, and
  `admin-session`'s absence-shaped refusal is already covered by
  `test_playbook_admin_page.py::test_no_session_means_no_surface`.

## Obsolete tests — candidates for human confirmation

The two `MODIFIED` deltas supersede behaviour, so this section is
applicable. The search was bounded to the dispatched test-path glob
`tests/**/test_*.py`; no earlier `test-manifest.md` was supplied to this
pass, so no scenario-to-test mapping was available beyond reading the
suite. **Everything below is a candidate, not a conclusion. Nothing here
was edited, deleted or disabled by this pass.**

### 1. `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py::test_a_created_step_appears_in_its_gate`

- **RESOLVED — removed during implementation, on the author's decision.**
  It was confirmed obsolete rather than merely suspected: with the change
  implemented it still *passed*, but only because a `draft` renders in the
  *Not served at this gate* block below its gate's table, so what it
  actually asserted was text position, not gate order. Its docstring went
  on reproducing the pre-change scenario. A comment stands in its place in
  the file recording why it went.
- **Superseded by:** MODIFIED *Steps can be created, retired and
  un-retired from the page* — the scenario *A created step appears in
  its gate*, whose `THEN` this change narrows from "the table shows it
  as the last step of its gate" to "a step created **`active`** …
  rendered as the last step of its **gate's active steps**", and extends
  with the addressing clause.
- **Evidence:** the test's own docstring reproduces the pre-change
  scenario verbatim ("WHEN a step is created from the page with valid
  fields / THEN the table shows it as the last step of its gate"), and
  its submission sets no status — `_fill(fields, name=…, gate="listable")`
  leaves the form's default, which after `redesign-step-fields` is
  `draft`. It then asserts the created step is last among the gate's
  rendered steps and precedes `hold.stock-ready`. Under the revised
  requirement a `draft` holds no position in its gate's order and renders
  among the non-active steps set apart from the served set, so that
  assertion states superseded behaviour whether or not it happens to
  still pass.
- **Also note, not superseded:** the same test finds the create control
  via `_control(page, contains=("new",))`, which matches the new
  `/steps/new` route — `tasks.md` 6.3 records that renaming the route
  breaks it — and it follows redirects by default, so the `200` → `303`
  change does not (`tasks.md` 6.2).
- **Suggested disposition, for a human to decide:** its coverage of the
  revised scenario is superseded by
  `test_playbook_admin_create_page.py::test_a_created_active_step_appears_in_its_gate_and_is_addressed`
  and
  `…::test_a_step_created_as_a_draft_is_addressed_where_it_renders`,
  which state the status explicitly in both directions.

### No other bearing test was found

Searched within the glob for tests exercising the create flow from the
page (`grep` for `steps/create`, `contains=("create"`, `contains=("new"`,
`def test_.*creat`) and for tests asserting on the anchor form inputs
(`anchor_kind`, `anchor_days`, `anchor_start`, `anchor_end`,
`anchor_cadence`). Distinguishing the two possible readings, as required:

- **The anchor requirement supersedes nothing, and this is "no such test
  exists"** rather than "none was found". The only hits on anchor field
  names are persistence and seed tests
  (`tests/unit/launch/infrastructure/driven/test_playbook_repository_rows.py`,
  `tests/integration/launch/test_playbook_seed.py`,
  `tests/integration/launch/test_seeded_step_fields.py`), which assert
  round-tripping and representation of anchor *kinds*, not what an
  authoring surface offers. No test in the suite asserts anything about
  the anchor fieldset's rendered inputs — the requirement is ADDED and
  had no prior coverage to supersede.
- **For the create flow, this is "none other was found by this
  search."** `test_a_created_step_appears_in_its_gate` above is the only
  page-tier create test. The application-tier create tests
  (`test_playbook_authoring.py`,
  `test_playbook_authoring_new_field_set.py`,
  `test_step_retirement_and_slots.py::test_a_created_active_step_appends_to_its_gate`
  and `::test_a_created_draft_holds_no_slot`) cover the *write*, which
  this change explicitly does not touch — `proposal.md`: "the authoring
  writes, their validation, and the persisted step set are untouched" —
  so they are not superseded. This pass has not seen the implementation
  and holds no requirement-to-test index, so a wider claim would be
  guesswork.

## Unresolved project questions

Answered here by assumption because this pass is a dispatched subagent
with no channel to ask on. Each names the tests that depend on it and the
single point at which the assumption is corrected.

| Question | Assumption taken | Depends on it | Correction point |
| --- | --- | --- | --- |
| Does the library carry a skill for this stack's idiom? | `ai-toolkit:testing` and `ai-toolkit:python` were both loaded; the latter's `references/testing.md` supplied the `pytest` idiom. **No skill covers FastAPI `TestClient` or HTML-surface testing**, so the floor plus the sibling tests' established idiom was used instead. Recorded as an absence rather than stalling. | Both files | — |
| What names the created step's identity in the redirect's query string? | `created` (`design.md` states the shape; the spelling is inferred) | Every create test; both "ignored" tests directly | `_CREATED_PARAM` |
| What `id` does a step's row carry? | `step-<identifier>` (`design.md`) | The four addressing tests | `_ADDRESS_ID` |
| What URL does the create control carry? | Something mentioning `new`, `create` or `add`; verified by following it to a page carrying a form with a name and an *editable* discipline field | All 17 create-surface tests | `_CREATE_HINTS`, `_create_form_of` / `_authoring_form_of` |
| How is "not offered" spelled in markup? | `hidden` / `aria-hidden` / `display:none` / `visibility:hidden` / a hidden-ish class / `input type="hidden"`, inherited from ancestors; **not** `disabled`, which the requirement forbids | All four anchor tests | `_HIDDEN_CLASSES`, `_element_hidden` |
| How does the notice word "falls outside the narrowing"? | Any of `_OUTSIDE_WORDS`, alongside the step being named | The two narrowing-hides tests | `_OUTSIDE_WORDS` |
| What status does a refusal answer with? | `>= 400`, asserted separately from the binding halves | The two refusal tests | The commented `DERIVED` line in each |
| Are the window anchor's inputs day offsets or dates? | Whatever the rendered control implies — a select's own option, else a value matching the input's `type`, defaulting to a day offset | `test_a_rejection_re_renders_against_the_submitted_anchor_kind`, `test_an_input_two_anchor_kinds_share_stays_offered_for_both` | `_plausible_value` |

The page module, the `steps` and roster seams, the guard seam, the
session cookie and the narrowing query-parameter names are **not** listed
as open questions here: they were invented by
`test_playbook_admin_page.py` and are satisfied by the implementation
today, so this pass inherited them as settled.

## Harness validation

Because 17 of the 20 tests stop at an absent route, their deeper
assertions are unexercised — the second failure state, which establishes
that the target is absent and nothing about whether the assertions are
any good. To keep those assertions from hiding a defect until the route
lands, the harness was exercised against the page as it stands today,
outside the test suite:

- The create payload `_valid_create_values` builds is **accepted** by the
  authoring write against the currently-inline create form, producing
  `mg.strategy.001` — so the field addressing, the assignee, the kind and
  the anchor are all right, and the generated identifier really carries
  the discipline as its second segment.
- The two-fault payload `_rejecting` builds is **rejected**, and both
  DERIVED wording markers (`brief`, and `assignee`/`person`) are present
  in the response — so those markers are not a guess that will fail as a
  broken test.
- The field-by-field echo comparison used by
  `test_a_rejected_create_keeps_every_submitted_value` and
  `test_a_stale_create_is_surfaced_not_silently_dropped` was run against
  the **existing edit** rejection path, which already echoes submitted
  values: zero mismatches. So the comparison is sound rather than
  brittle.
- A `window` create with `_plausible_value`'s inputs writes
  `WindowAnchor(start=-7, end=-3)` — the anchor tests will not fail on an
  unparseable anchor.
- A create naming no discipline, and one naming `retired`, both
  **persist today** — confirming those two tests fail on a wrong value
  rather than on a mis-built request.

## Verification run alongside this pass

- `uv run ruff check` — clean on both files.
- `uv run ruff format --check` — clean on both files.
- `uv run mypy .` — `Success: no issues found in 259 source files`
  (a stale `.mypy_cache` reported four phantom errors; a clean run has
  none).
- `uv run lint-imports --config .importlinter` — 17 contracts kept, 0
  broken. Neither file opens a new dependency on `access`; the roster
  double is a local fake, as in the sibling tests.

## What the implementation must make pass

`uv run pytest tests/unit/launch/infrastructure/driving/test_playbook_admin_create_page.py tests/unit/launch/infrastructure/driving/test_playbook_admin_anchor_inputs.py`
— 20 tests, all currently failing — while `uv run pytest` keeps its 821
passing tests passing.
