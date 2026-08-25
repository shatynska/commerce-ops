# Test manifest — `reorder-steps-under-filters`

Written before implementation, from the change's delta specs alone. No
implementation source for the behaviour under test was read: the
`MODIFIED` deltas were reconciled against
`openspec/specs/playbook-admin/spec.md` and
`openspec/specs/playbook-authoring/spec.md`, not against
`playbook_admin.py` or `playbook_authoring.py`.

**This file is not part of the OpenSpec schema.** It will not appear
among `openspec instructions apply`'s context files, and must be opened
on purpose by whoever implements the change.

## Files written

| File | Tier | Tests |
| --- | --- | --- |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_filtered_moves.py` | unit | 17 |
| `tests/unit/launch/application/test_playbook_reorder_pinned_version.py` | unit | 3 |

Both are new files. **This pass adds tests and never subtracts:** no
existing test was edited, deleted, disabled, or weakened, and nothing was
written outside `tests/**/test_*.py` except this manifest.

Placement follows `AGENTS.md` — Testing Strategy: the change touches no
real I/O, so both files sit in the unit tier, mirroring the layer under
test (`.../infrastructure/driving/`, `.../application/`).

Run a single test with, for example:

```
uv run pytest "tests/unit/launch/infrastructure/driving/test_playbook_admin_filtered_moves.py::test_a_filtered_move_lands_against_the_visible_step_it_names"
```

## Baseline

`uv run pytest tests/unit tests/agents` — **665 passed, 0 failed**, taken
before any test below was written.

This is a **scoped** baseline, and the scope is the two tiers these
tests are written into. `tests/integration` was not run: it needs a live
Postgres and `DATABASE_URL` is unset in this environment. No claim below
about a failing test rests on the integration tier.

After this pass: `uv run pytest tests/unit tests/agents` — **668 passed,
17 failed**. Every one of the 665 baseline tests still passes; the 17
failures and the 3 additional passes are all new tests, accounted for
individually below.

## Scenario accounting

**28 `#### Scenario:` blocks across the two delta specs; 28 accounted
for.** 19 are covered by tests written in this pass, 9 by tests that
already exist and are reproduced verbatim by their `MODIFIED` block.

### `playbook-admin` — ADDED: *The narrowed view survives every write and every move between views* (5 of 5 new)

All in `test_playbook_admin_filtered_moves.py`.

| Scenario | Test |
| --- | --- |
| An accepted write keeps the narrowing | `test_an_accepted_write_keeps_the_narrowing` |
| A rejected list-level write keeps the narrowing | `test_a_rejected_list_level_write_keeps_the_narrowing` |
| A rejected edit keeps the narrowing without leaving the form | `test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form` |
| Opening and leaving an edit form preserves the narrowing | `test_opening_and_leaving_an_edit_form_preserves_the_narrowing` |
| Un-retiring keeps the retired steps visible | `test_un_retiring_keeps_the_retired_steps_visible` |

*A rejected list-level write keeps the narrowing* is written against a
**retirement**, as the delta states it. That is deliberate and was not
"corrected" to a creation: `proposal.md` — Sequencing records that
`add-step-page` moves creation onto its own surface, so a rejected
creation stops being an example of a write that re-renders the list.

### `playbook-admin` — MODIFIED: *The step table shows the live set whole* (1 of 5 new)

| Scenario | Test |
| --- | --- |
| The whole live set is one page | already covered — `test_playbook_admin_page.py::test_the_whole_live_set_is_one_page` |
| Filters narrow without altering | already covered — `test_playbook_admin_page.py::test_filters_narrow_without_altering` |
| Search matches description text | already covered — `test_playbook_admin_page.py::test_search_matches_description_text` |
| Retired steps are reachable but set apart | already covered — `test_playbook_admin_page.py::test_retired_steps_are_reachable_but_set_apart` |
| A position is read against the whole gate | `test_playbook_admin_filtered_moves.py::test_a_position_is_read_against_the_whole_gate` |

The four already-covered scenarios are reproduced word for word by the
`MODIFIED` block and their tests pass at the baseline, so they were not
duplicated. They must continue to pass.

### `playbook-admin` — MODIFIED: *A gate's steps can be reordered from the page* (10 of 12 new)

All new ones in `test_playbook_admin_filtered_moves.py`.

| Scenario | Test |
| --- | --- |
| A move sticks | already covered — `test_playbook_admin_page.py::test_a_move_sticks` |
| A filtered move lands against the visible step it names | `test_a_filtered_move_lands_against_the_visible_step_it_names` |
| A filtered move upwards lands against the visible step above the one it passes | `test_a_filtered_move_upwards_lands_against_the_visible_step_above` |
| A filtered move disturbs nothing else | `test_a_filtered_move_disturbs_nothing_else` |
| A move to the head of a narrowed list stops at the first visible step | `test_a_move_to_the_head_of_a_narrowed_list_stops_at_the_first_visible` |
| A move to the end of a narrowed list stops at the last visible step | `test_a_move_to_the_end_of_a_narrowed_list_stops_at_the_last_visible` |
| A move that changes nothing persists nothing | `test_a_move_that_changes_nothing_persists_nothing` |
| Reordering is unavailable under a description search | `test_reordering_is_unavailable_under_a_description_search` |
| Reordering is unavailable while retired steps are shown | `test_reordering_is_unavailable_while_retired_steps_are_shown` |
| A move submitted where reordering is unavailable is refused | `test_a_move_submitted_where_reordering_is_unavailable_is_refused` |
| A move submitted from a superseded list is rejected | `test_a_move_submitted_from_a_superseded_list_is_rejected` |
| A stale move leaves truth on the page | already covered — `test_playbook_admin_page.py::test_a_stale_move_leaves_truth_on_the_page` |

### `playbook-authoring` — MODIFIED: *A gate's steps can be reordered* (3 of 6 new)

All new ones in `test_playbook_reorder_pinned_version.py`.

| Scenario | Test |
| --- | --- |
| A moved step is served in its new slot | already covered — `test_playbook_reorder.py::test_a_moved_step_is_served_in_its_new_slot` |
| A stale reorder is rejected whole | already covered — `test_playbook_reorder.py::test_a_stale_reorder_is_rejected_whole` |
| A reorder never leaves the step's own gate | already covered — `test_playbook_reorder.py::test_a_reorder_never_leaves_the_steps_own_gate` |
| A supplied view is not retried past | `test_a_supplied_view_is_not_retried_past` |
| A supplied view that does not match is refused whichever way it differs | `test_a_supplied_view_that_does_not_match_is_refused_either_way` |
| A reorder without a supplied view still resolves concurrency | `test_a_reorder_without_a_supplied_view_still_resolves_concurrency` |

### Uncovered scenarios

**None.** Every scenario in both delta specs is covered by at least one
named test above. No `REMOVED` or `RENAMED` delta appears in this change,
so no scenario is accounted for by an operation instead of a test.

### One test that maps to no scenario

`test_playbook_admin_filtered_moves.py::test_the_pages_order_agrees_with_the_authoring_writes_order`
— **derived throughout**, written for `tasks.md` 3.1 and `design.md` —
Risks (*"the two sort keys are equal today but written out separately,
and no test pins them"*). No delta scenario states it. It compares the
order the page renders a gate's live steps in against the order the
authoring reorder write leaves them in, without either being told the
other's answer.

## Assertion classification

Per assertion group, in the vocabulary the testing standard fixes.

### Specified

Traceable to a stated requirement in a delta spec, or (where noted) to
`tasks.md` / `design.md`:

- Every **expected full-gate ordering** after a move. These are not
  invented values: the scenario fixes where the moved step lands
  ("immediately after that visible step", "immediately before the first
  visible step", "ahead of those hidden steps"), and the requirement's
  own invariant — *"Every step other than the moved one SHALL keep its
  relative order, steps the filter is hiding included"* — fixes
  everything else. Exactly one ordering satisfies both.
  `design.md` — Decisions was used only to read the coordinate frame
  (`target_index` counts the gate's live steps preceding the moved step
  once it has been removed), never as a source of expected values.
- `store.saves == []` wherever a scenario says "nothing is persisted".
- The absence of steps a filter excludes from a re-rendered page, and
  the presence of the narrowing on the page's own controls, for every
  narrowing scenario.
- Each visible step rendering its position among its gate's live steps
  and the gate's live count, unchanged by the filter.
- No **live** reorder control under a description search or while
  retired steps are shown.
- A single control reaching a view that leaves the search behind / hides
  retired steps ("offers to ... in one action"), read behaviourally
  rather than by link wording.
- `StaleStepSetError` as the authoring rejection — named by `tasks.md`
  4.2.
- In `test_a_reorder_without_a_supplied_view_still_resolves_concurrency`,
  that the write re-reads and gets through. **Traces to `tasks.md` 4.2
  and `design.md`** (*"when absent, keep today's re-read-and-recompute
  behaviour so no existing caller changes meaning"*), not to the
  scenario, which states it permissively (*may*). Recorded here rather
  than left implicit, because an implementation that removed the retry
  wholesale would satisfy the scenario's letter and break the change's
  stated obligation.

### Derived

Invented by this pass; no stated requirement covers them. Each is a
correction point rather than an obligation:

- **Fault- and notice-wording markers.** That a page stating reordering
  is unavailable mentions the reason (`search`, `retired`), a reorder
  word, and an unavailability word (`_UNAVAILABLE_WORDS`,
  `_REORDER_WORDS`); that a stale-move notice contains "changed" (the
  marker `test_playbook_admin_page.py` already uses for the stale edit
  and the stale move). Correcting a substring to the implemented wording
  is a fixture correction; dropping the assertion is not.
- **The rendered form of a position** — `3 / 7` or `3 of 7`
  (`_POSITION_PATTERN`). The requirement fixes that a position and a
  count are rendered, not how they are spelled.
- **HTTP 200 on a refused no-op move**, in
  `test_a_move_that_changes_nothing_persists_nothing`: the requirement
  says nothing is persisted, not what status the page answers with.
- **No other gate is disturbed**, in
  `test_a_filtered_move_disturbs_nothing_else` — that is the authoring
  reorder's own requirement, unchanged by this change, asserted here as
  a cheap guard.
- The whole of
  `test_the_pages_order_agrees_with_the_authoring_writes_order`, as
  recorded above.
- **Sanity guards** explicitly marked DERIVED in the tests: that a
  narrowed view is not simply empty, so an absence assertion cannot pass
  vacuously.

### Deliberately untested

- **`tasks.md` 3.10** — that the new move route rides `_require_admin`
  and refuses with the app's own 404. Not restated as a new test:
  `test_playbook_admin_page.py::test_no_session_means_no_surface` already
  covers the guard's response shape for the page router, and the
  `admin-session` requirement it derives from is not part of this
  change's deltas. If the implementation introduces the move route
  outside the existing dependency, that is a review question, not one
  this pass can observe without duplicating an existing test.
- **`tasks.md` 3.9** — that `reorder_step`'s `InvalidPlaybookError` and
  bare `ValueError` render rather than escaping as a 500. No delta
  scenario states it, and the fixtures here cannot reach an
  out-of-range index through the page once the server computes the index
  itself. Left to the implementer's own verification step.
- **The seeded 97-step set** (`tasks.md` 6.4). A manual check by its
  own statement; nothing here substitutes for it.
- **`tests/integration`.** This change touches no real I/O, so no
  integration-tier test was written. The existing
  `tests/integration/launch/test_playbook_ordering_live.py` calls
  `reorder_step` with no supplied view and must keep passing unchanged —
  that is the point of the parameter being optional.

## Obsolete tests

**Applicable** — the change carries `MODIFIED` deltas on two
capabilities, so this list is not "not applicable".

**No bearing test was found, and in this case that is stronger than a
negative search result.** Both `MODIFIED` blocks reproduce every
pre-existing requirement sentence and every pre-existing scenario of
their capability verbatim; comparing each delta against the requirement
as it currently stands under `openspec/specs/` shows the change adds
paragraphs and scenarios without contradicting any existing one. There
is therefore no superseded behaviour for an entry to bear on.

Search performed, for the record: `tests/**/test_*.py` (the dispatched
glob), matching on `reorder`, `unretire`, `display_order`, `move_up`,
`move_down`, `Stale`, `retry`, `concurren`. No earlier
`test-manifest.md` was supplied to this pass, so none was used as a
scenario-to-test mapping. The candidates the search surfaced and why
each is **not** an obsolete entry:

| Test | Why not obsolete |
| --- | --- |
| `test_playbook_admin_page.py::test_a_move_sticks` | Its scenario is reproduced verbatim by the `MODIFIED` block. Its assertions are not superseded. |
| `test_playbook_admin_page.py::test_a_stale_move_leaves_truth_on_the_page` | Same — reproduced verbatim. |
| `test_playbook_reorder.py::test_a_stale_reorder_is_rejected_whole` | Reproduced verbatim; it exercises the no-supplied-view path, whose behaviour `tasks.md` 4.2 preserves. |
| `tests/integration/launch/test_playbook_ordering_live.py` | Calls `reorder_step` with no supplied view; the new parameter is optional and that path is unchanged. |
| `tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py` | Domain-level; this change states no domain change (`design.md` — Non-Goals). |

**One flag that is not an obsolete entry, and must not be treated as
one.** `test_a_move_sticks` and `test_a_stale_move_leaves_truth_on_the_page`
discover the reorder control by the substrings `up`/`top` in its URL,
and submit it carrying no set version. `tasks.md` 3.5 replaces `_move`
with a single route, and 3.4 adds a required version field. If those
tests then fail, the failure is in their **discovery fixture**, not in
what they assert — their assertions trace to scenarios this delta
reproduces verbatim. Correct the discovery; do not delete or weaken the
assertions. Raised here as a **candidate for human confirmation**, on
the evidence that both tests locate their control by
`_control(page, contains=("listing.zeta", "up"))` while `design.md` —
*The client names a neighbour and a version* removes the direction from
what the move posts.

## Unresolved project questions

Each was raised by this pass and has no recorded answer in `AGENTS.md`,
`CLAUDE.md`, `README.md` or `pyproject.toml`. A dispatched subagent has
no channel to ask on, so each is recorded with the assumption taken, the
tests that depend on it, and where to correct it.

1. **No stack skill covers this library's testing idiom beyond
   `pytest`.** `ai-toolkit`'s skill list carries `python` (whose
   `references/testing.md` covers `pytest`) and no FastAPI/Starlette/
   Jinja skill. Assumption: the `TestClient`-over-a-monkeypatched-module
   idiom that `test_playbook_admin_page.py` and `test_clickup_webhook.py`
   already use is the project's convention, and was followed unchanged.
   Depends on it: all of `test_playbook_admin_filtered_moves.py`.

2. **The supplied-view parameter's name on `reorder_step`.** No artifact
   fixes one; `tasks.md` 4.1 says only "an optional expected set
   version". Assumption: `expected_version=`, following the store
   protocol's own `save(..., expected_version=)`. Correction point:
   `_reorder_pinned` in `test_playbook_reorder_pinned_version.py`, the
   only place it is written. Depends on it:
   `test_a_supplied_view_is_not_retried_past`,
   `test_a_supplied_view_that_does_not_match_is_refused_either_way`.

3. **That "no supplied view" is expressed by omitting the parameter**
   rather than by passing `None`. Correction point: `_reorder_unpinned`.
   Depends on it:
   `test_a_reorder_without_a_supplied_view_still_resolves_concurrency`.

4. **How a move control is discovered on the page.** Two strategies are
   tried, in order: the control carries the named neighbour's identifier
   in a field value or its URL (`design.md`'s stated transport), else
   the direction spellings `up`/`top` and `down`/`bottom`
   (`test_playbook_admin_page.py`'s existing vocabulary — and what the
   pre-change page in fact renders). Correction point: `_move_control`.
   Depends on it: every filtered-move test.

5. **How "the reorder controls are inert" is read off the markup.**
   Assumption: a control is inert if it is absent, or carries
   `disabled` / `aria-disabled="true"` on the form, on a submit button
   inside it, or on the link. Correction point: `_ControlParser`.
   Depends on it: `test_reordering_is_unavailable_under_a_description_search`,
   `test_reordering_is_unavailable_while_retired_steps_are_shown`.

6. **Query-parameter names for the narrowing** — `gate`, `discipline`,
   `q`, `retired`. Inherited from `test_playbook_admin_page.py`, which
   the implementation already satisfies, so this is the least uncertain
   of the six. Correction points: `_FILTER_PARAMS`, `_RETIRED_PARAM`.

7. **That a step's edit form is its own page, reached by following a GET
   control and carrying a link back to the list.** `design.md` — *One
   `_filters_of(request)` helper* names `edit.html:39`'s back link, so
   the page exists; what is assumed is that it is reachable by following
   the first list-returning GET control on it. If the implemented edit
   page carries more than one link back to the list, `_back_to_list`
   takes the first in document order. Correction point: `_open_edit`,
   `_back_to_list`. Depends on it: the two edit-round-trip tests.

8. **Where a test manifest belongs, and whether anything reads it.**
   `AGENTS.md` names the test-writing step in its workflow but records
   no manifest convention and imports no `rules/` fragment directing
   that one be read. This file is at the location the dispatch fixed;
   nothing in the repository points at it.

## Expected first-run state, test by test

The page module and its routes already exist, so the admin tests do not
fail at import: they exercise behaviour this change ADDS against the
pre-change page, and each failure below was observed to be a **wrong
value** — the assertions ran and discriminated.

**17 failing** (state 1, code produced a wrong value — except the two
noted):

- `test_an_accepted_write_keeps_the_narrowing` — the re-render widens to
  the whole set.
- `test_a_rejected_list_level_write_keeps_the_narrowing` — same.
- `test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form` —
  the back link drops the gate filter.
- `test_opening_and_leaving_an_edit_form_preserves_the_narrowing` — same.
- `test_un_retiring_keeps_the_retired_steps_visible` — the re-render
  drops the gate and discipline filters.
- `test_a_position_is_read_against_the_whole_gate` — no position is
  rendered at all.
- `test_a_filtered_move_lands_against_the_visible_step_it_names` — the
  move swaps with the hidden neighbour.
- `test_a_filtered_move_upwards_lands_against_the_visible_step_above` —
  same.
- `test_a_move_to_the_head_of_a_narrowed_list_stops_at_the_first_visible`
  — same.
- `test_a_move_to_the_end_of_a_narrowed_list_stops_at_the_last_visible` —
  same.
- `test_a_move_that_changes_nothing_persists_nothing` — the move is
  persisted.
- `test_reordering_is_unavailable_under_a_description_search` — live
  controls are rendered.
- `test_reordering_is_unavailable_while_retired_steps_are_shown` — same.
- `test_a_move_submitted_where_reordering_is_unavailable_is_refused` —
  the move is persisted.
- `test_a_move_submitted_from_a_superseded_list_is_rejected` — the move
  is persisted against the newer set.
- `test_a_supplied_view_is_not_retried_past` — **state 2, absent
  target**: `TypeError: reorder_step() got an unexpected keyword
  argument 'expected_version'`. Its assertions have not been exercised.
- `test_a_supplied_view_that_does_not_match_is_refused_either_way` —
  state 2, same reason.

**3 passing on the first run.** Each was investigated rather than
recorded as coverage:

- `test_a_reorder_without_a_supplied_view_still_resolves_concurrency` —
  passes because the behaviour it pins already exists and `tasks.md` 4.2
  requires it be preserved. It is a **regression pin**, not new
  coverage; it fails if the retry is removed wholesale rather than only
  for the supplied-view path.
- `test_the_pages_order_agrees_with_the_authoring_writes_order` — passes
  because the two sort keys agree today. That is exactly what
  `tasks.md` 3.1 asks be pinned so drift surfaces as a failure.
- `test_a_filtered_move_disturbs_nothing_else` — passes because its
  scenario states an **invariant** rather than a placement, and the
  pre-change whole-gate move satisfies that invariant too. It cannot
  discriminate this change by construction; it guards against a new
  filter-aware implementation breaking the invariant while satisfying
  the placement scenarios. The scenario's discriminating force lives in
  the five placement tests beside it.

The other five placement tests were each checked to be discriminating:
`test_a_move_to_the_end_of_a_narrowed_list_stops_at_the_last_visible`
originally coincided with pre-change behaviour, and its fixture was
given a hidden step *between* the two visible ones — still exactly the
scenario's WHEN — so that it now fails against the pre-change page.

## What the implementation must make pass

`uv run pytest tests/unit tests/agents` back to **0 failed**, with all
665 baseline tests and all 20 tests above passing, and
`uv run pytest tests/integration` unchanged.

Task-to-test map, for running only what a task must satisfy:

| `tasks.md` | Tests |
| --- | --- |
| 1.1–1.4, 1.7 | `test_an_accepted_write_keeps_the_narrowing`, `test_a_rejected_list_level_write_keeps_the_narrowing`, `test_un_retiring_keeps_the_retired_steps_visible` |
| 1.5 | `test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form`, `test_opening_and_leaving_an_edit_form_preserves_the_narrowing` |
| 1.3, 1.6 | `test_un_retiring_keeps_the_retired_steps_visible` |
| 2.1–2.3 | `test_a_position_is_read_against_the_whole_gate` |
| 3.1 | `test_the_pages_order_agrees_with_the_authoring_writes_order` |
| 3.2, 3.5, 3.7, 3.11 | the five placement tests plus `test_a_filtered_move_disturbs_nothing_else` |
| 3.3 | `test_a_move_that_changes_nothing_persists_nothing` |
| 3.4, 3.6, 4.4, 4.6 | `test_a_move_submitted_from_a_superseded_list_is_rejected` |
| 4.1, 4.2, 4.5 | `test_a_supplied_view_is_not_retried_past`, `test_a_supplied_view_that_does_not_match_is_refused_either_way`, `test_a_reorder_without_a_supplied_view_still_resolves_concurrency` |
| 5.1, 5.2, 5.4 | `test_reordering_is_unavailable_under_a_description_search`, `test_reordering_is_unavailable_while_retired_steps_are_shown` |
| 5.3 | `test_a_move_submitted_where_reordering_is_unavailable_is_refused` |

## One repository observation, not a finding about this change

`uv run mypy .` on the pristine tree — with both new files removed —
already reports
`tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py:89:
error: Module "commerce_ops.launch.infrastructure.driving" has no
attribute "playbook_admin"`. It does not reproduce when that file is
checked alone, so it appears to be an ordering or cache effect of the
whole-tree run. The new admin test file uses the same import and
inherits the same error. Pre-existing; not introduced here, and not
fixed here — fixing it would be a change outside this change's scope.
