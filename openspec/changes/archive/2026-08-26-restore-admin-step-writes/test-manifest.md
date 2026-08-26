# Test manifest — `restore-admin-step-writes`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-26, from the
change's delta specs alone, before any of the change was implemented.

**This file is not part of the OpenSpec schema.** It does not appear
among `openspec instructions apply`'s context files, so whoever
implements this change has to open it on purpose. Nothing in
`AGENTS.md`'s managed block points at it either — recorded below as an
unresolved project question.

---

## Baseline

`uv run pytest` at the worktree root, branch `restore-admin-step-writes`,
commit `a9414ba`, clean tree, immediately before any test here was
written:

```
985 passed in 39.07s
```

0 failed, 0 skipped — the integration tier included, so no tier was
silently absent from the number. Re-run by this pass at the same commit
and reproduced exactly.

**State after this pass** (same command, same commit, tests added only):

```
26 failed, 992 passed, 1 skipped in 40.64s
```

Every one of the 26 failures is in a file this pass created. No
pre-existing test changed outcome. The 7 additional passes are the
regression guards listed below; the 1 skip is this pass's own, and says
why in its own message.

`uv run mypy .`, `uv run ruff check`, `uv run ruff format --check` and
`uv run lint-imports --config .importlinter` are all clean with these
files in place.

---

## Files added

| File | Covers |
| --- | --- |
| `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py` | `playbook-authoring` MODIFIED — the four appended scenarios |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_roster.py` | `playbook-admin` ADDED Req A (3 scenarios) + the surface half of `playbook-authoring` case 3 (`tasks.md` 5.4) |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_write_failure_notice.py` | `playbook-admin` ADDED Req B (9 scenarios, server-observable halves) + `tasks.md` 5.5 |
| `tests/integration/launch/test_playbook_authoring_roster_live.py` | `playbook-authoring` cases 1 and 3 against the real adapters (`tasks.md` 5.1, 5.2) |

No existing test file was edited, deleted or disabled. **This pass adds
tests and never subtracts.**

---

## Scenario accounting

The change's delta specs carry **22** `#### Scenario:` blocks: 10 in
`playbook-authoring` (6 carried forward verbatim + 4 appended) and 12 in
`playbook-admin` (3 + 9). All 22 are accounted for below, each exactly
once.

### `playbook-authoring` — MODIFIED *Every write is validated as the playbook it would produce*

The six scenarios the delta carries forward **verbatim** from
`openspec/specs/playbook-authoring/spec.md` are already covered. They are
accounted for by naming their existing tests, not by duplicating them.

| Scenario | Covered by (runner-selectable) | First run |
| --- | --- | --- |
| A rejected write reports all faults and persists nothing | `tests/unit/launch/application/test_step_assignee_preconditions.py::test_a_rejected_write_reports_all_faults_and_persists_nothing` | pre-existing, green |
| Retiring a gate's last blocking step is rejected | `tests/unit/launch/application/test_step_retirement_and_slots.py::test_retiring_a_gates_last_active_blocking_step_is_rejected` | pre-existing, green |
| What a write cannot persist, a load cannot see | `tests/unit/launch/application/test_step_assignee_preconditions.py::test_what_a_write_cannot_persist_a_load_cannot_see` | pre-existing, green |
| An untouched unowned step does not block an unrelated write | `tests/unit/launch/application/test_step_assignee_preconditions.py::test_an_untouched_unowned_step_does_not_block_an_unrelated_write` | pre-existing, green |
| Editing an unowned step requires giving it an owner | `tests/unit/launch/application/test_step_assignee_preconditions.py::test_editing_an_unowned_step_requires_giving_it_an_owner` | pre-existing, green |
| A roster change does not break an accepted set | `tests/unit/launch/application/test_step_assignee_preconditions.py::test_a_roster_change_does_not_break_an_accepted_set` | pre-existing, green |

The four **appended** scenarios:

| Scenario | Covered by | First run |
| --- | --- | --- |
| A collaborator of the wrong shape is refused by name | `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py::test_a_collaborator_of_the_wrong_shape_is_refused_by_name[create]` `[update]` `[retire]` `[unretire]` `[change_status]` — and, against the real adapter, `tests/integration/launch/test_playbook_authoring_roster_live.py::test_the_real_roster_store_is_refused_by_name` | **6 FAIL** |
| A mis-wiring is not reported as a rejection of the submission | `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py::test_a_mis_wiring_is_not_reported_as_a_rejection_of_the_submission`; surface half: `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_roster.py::test_a_mis_wired_collaborator_is_not_rendered_as_a_fault_of_the_submission` | **FAIL** / guard PASS |
| A mis-shaped collaborator never passes for an absent one | `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py::test_a_mis_shaped_collaborator_never_passes_for_an_absent_one` | **FAIL** |
| No roster is still a permitted case | `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py::test_no_roster_is_still_a_permitted_case` | guard PASS |

Case 1 of the collaborator's three cases — a roster that *does* answer the
stated shape — is additionally exercised against the real adapters by
`tests/integration/launch/test_playbook_authoring_roster_live.py::test_a_write_judged_against_the_live_roster_lands`, which **skips** here
(see *Uncovered*).

### `playbook-admin` — ADDED *Every write is judged against the same roster the page reads*

| Scenario | Covered by | First run |
| --- | --- | --- |
| A write names a person the page offered | `…/test_playbook_admin_writes_reach_the_roster.py::test_a_write_names_a_person_the_page_offered` | **FAIL** |
| Each write reaches the roster | `…/test_playbook_admin_writes_reach_the_roster.py::test_each_write_reaches_the_roster[create]` `[save_edit]` `[retire]` `[unretire]` `[change_status]` | **5 FAIL** |
| A roster refusal is explicable from the page | `…/test_playbook_admin_writes_reach_the_roster.py::test_a_roster_refusal_is_explicable_from_the_page` | **FAIL** |

### `playbook-admin` — ADDED *A write that fails is never silent*

All nine are in
`tests/unit/launch/infrastructure/driving/test_playbook_admin_write_failure_notice.py`.
Where a scenario has a browser half this project cannot execute, the
server half is named here and the browser half is listed under
*Uncovered* — never folded into the covering test as though it had been
asserted.

| Scenario | Covered by | Half | First run |
| --- | --- | --- | --- |
| An unanticipated failure is reported | `::test_an_unanticipated_failure_is_reported[the step list]` `[the edit surface]` | server: the page ships a handler for the response-error event and the wording it would render | **2 FAIL** |
| A failure with no response is reported too | `::test_a_failure_with_no_response_is_reported_too[the step list]` `[the edit surface]` | server: all three events bound | **2 FAIL** |
| The report does not claim what the page cannot know | `::test_the_report_does_not_claim_what_the_page_cannot_know[the step list]` `[the edit surface]` | server: the shipped copy makes the permitted claim and not the forbidden one | **2 FAIL** |
| A failed write does not read as a successful one | `::test_a_failed_write_does_not_read_as_a_successful_one` | whole (server-observable in full) | guard PASS |
| A failed write does not read as an unsubmitted one | `::test_a_failed_write_does_not_read_as_an_unsubmitted_one[the step list]` `[the edit surface]` | server: handler and container ship together, and the handler addresses the container | **2 FAIL** |
| The report is observable in the response | `::test_the_report_is_observable_in_the_response[the step list]` `[the edit surface]` | whole | **2 FAIL** |
| An ended session says so | `::test_an_ended_session_says_so[the step list]` `[the edit surface]` | server: the 404 reading and the wording | PASS / **FAIL** — see *Partly satisfied* |
| The guard's refusal stays indistinguishable | `::test_the_guards_refusal_stays_indistinguishable` | server half (`tasks.md` 5.5); the client half is the absence of a marker, which the same test asserts | guard PASS |
| A failure is visible on a submission the page does not enhance | `::test_a_failure_is_visible_on_a_submission_the_page_does_not_enhance` | server: the submission is un-enhanced, and a failed one answers a status the browser can render | guard PASS |

One test covers no scenario of its own and is recorded here so it is not
mistaken for one:
`::test_which_submissions_the_page_enhances_is_fixed` covers the
requirement's paragraph fixing the enhanced set, which two scenarios
above are scoped by.

---

## Uncovered, with reasons

Nothing below is an omission; each is a decision.

1. **Every browser half of *A write that fails is never silent*.** That
   the notice *appears* when htmx raises `htmx:responseError`,
   `htmx:sendError` or `htmx:timeout`; that the container acquires
   `write-failed` at that moment; that the page visibly changes; that an
   ended session's notice renders; and that an un-enhanced submission's
   failure reaches the admin through the browser's own error page,
   scripting off included.
   **Reason:** this project has three Python test tiers and no
   JavaScript tier (`AGENTS.md` — *Testing Strategy*), so no tier here
   executes the listener. `tasks.md` 5.3 draws this line explicitly and
   assigns the browser halves to `tasks.md` 6.3 and 6.4, by hand. The
   server halves are covered above; they are not presented as the
   browser halves.

2. **`tests/integration/launch/test_playbook_authoring_roster_live.py::test_a_write_judged_against_the_live_roster_lands`
   skipped on this machine.** The live roster carries nobody, the empty
   local roster `design.md` — *Risks* names. The test reads the roster
   first and skips with that reason rather than asserting against an
   empty one, and it adds nobody to a shared database to avoid the skip.
   **This is the coverage `tasks.md` 6.2's manual verification depends
   on**: seed an active person and re-run before believing the fixed
   path works.

3. **The roster admin surface.** It includes the same header partial and
   will therefore carry the notice container, but `design.md` — *Goals*
   places it out of scope (it boosts nothing). No test here asserts
   anything about it, in either direction.

---

## Assertion classification

Per-assertion labels live beside the assertions (`# SPECIFIED:` /
`# DERIVED …`) and each file's docstring carries a *what is INVENTED*
section naming its own correction points. Summarised:

**SPECIFIED** — traces to a delta clause:

- the refusal is raised, is not `InvalidPlaybookError`, and names both
  the collaborator supplied and the shape expected;
- nothing is persisted by a refused write, and the served version does
  not move;
- case 3 never collapses into case 2, and case 2 remains permitted with
  the load-side rules still evaluated in full;
- each of the five writes reaches a roster it can read, and a roster
  refusal names the person it concerns;
- the literal markers `write-failure-notice` and `write-failed`, and
  that the second never outruns the occurrence;
- all three htmx events bound, not one;
- the report says the write did not complete, says what is shown may be
  stale, directs a reload, and never claims nothing was saved;
- an unauthorised write route answers exactly as an unregistered route;
- the enhanced set is the step list and the edit surface, and not the
  create surface.

**DERIVED** — inferred, no delta clause fixes it:

| Derived choice | Where | Correction point |
| --- | --- | --- |
| The refusal's exception **class** (the delta fixes only "a named error") | both roster-shape files | `_refusal_of`; the integration file's inline assertions |
| `list_people` as the spelling of "the shape expected" | both roster-shape files | `_EXPECTED_SHAPE_NAMES` |
| Markers read as **class tokens** (the reading this capability already uses for `just-created`) | failure-notice file | `_carries` |
| Enhancement read as htmx `hx-boost` | failure-notice file | `_is_enhanced` |
| Every **phrasing** set for the notice's copy | failure-notice file | `_DID_NOT_COMPLETE`, `_MAY_BE_STALE`, `_RELOAD`, `_SESSION_ENDED`, `_WAY_BACK`, `_CLAIMS_NOTHING_SAVED` |
| A roster refusal "names the person" by rendering the identifier | writes-reach-the-roster file | `_names_the_person` |
| Control-discovery vocabulary (which control is edit / retire / unretire / status / create) | both driving files | the `_*_HINTS` constants |
| Page seams `steps`, `roster`, `verify_admin_session`; the `admin_session` cookie | both driving files | `_signed_client` / `_app` |
| The step-store and roster-store double shapes; the `handlers=` collaborator | all four files | as the sibling files already record them |

Correcting a derived **phrasing or spelling** to the implemented one is a
fixture correction and is fine. Dropping the assertion, or widening it
until it cannot fail, is not — each of these is the only thing standing
between a shipped clause and an unshipped one.

**Deliberately untested** — the *Uncovered* list above, in full.

---

## Obsolete tests

**A superseding delta exists** (`playbook-authoring` is `MODIFIED`), so
this list is applicable and was searched for.

**Result: no bearing test was found by this search.** Stated precisely —
this is "the search found none", not a claim that none could exist. Every
entry below would have been a candidate for human confirmation; there are
none to mark.

What was searched, and how:

1. **Within the dispatched test-path glob `tests/**/test_*.py` and
   nowhere else.** No earlier `test-manifest.md` path was supplied to
   this pass, so no scenario-to-test map was available to draw on.
2. **The narrowing the delta introduces** — `_read_people` dropping the
   callable and the iterable branches for one named shape — supersedes
   any test handing an authoring write a collaborator that is *only*
   callable or *only* iterable. Every roster double under `tests/` was
   enumerated (`grep` for `class _FakeRoster` / `class _Roster` /
   `class _RosterStore` / `list_people` across `tests/`): **sixteen
   reader doubles, every one of which exposes `list_people()`**, several
   exposing `people` and `__call__` as additional aliases *on top of* it
   rather than instead of it. None is invalidated by the narrowing,
   which is what `design.md` — *The roster collaborator gets one shape*
   predicted and `tasks.md` 2.5 asks to confirm. The store-shaped
   `_FakeRosterStore` doubles that also exist (under
   `tests/unit/access/` and in
   `tests/unit/launch/application/test_step_assignee_preconditions.py`)
   are passed to `access`'s own roster use cases, never as an authoring
   write's `roster=`; every `roster=` call site in `tests/` was
   checked.
3. **The six carried-forward scenarios are unchanged in wording**, so
   the tests covering them (named above) are not superseded — the
   requirement gained paragraphs, it did not revise theirs.
4. **The existing signed-out listener** the change replaces (see the
   finding below) was searched for by its own copy — `nothing was
   saved`, `Signed out`, `session has ended`, `Mint a fresh`,
   `responseError` — across `tests/**/test_*.py`. **No test asserts any
   of it.** Replacing that listener therefore supersedes no test.

---

## Findings for whoever implements this

Neither is a test; both were established while deriving tests, and both
bear on the implementation.

1. **`page.html` already ships a listener, and it says the forbidden
   thing.** The step list — and only the step list — binds
   `htmx:responseError` and, on a `404`, replaces the whole document
   body with: *"Signed out … This admin session has ended and **nothing
   was saved**. Mint a fresh link with the Slack command and reopen the
   page."*
   - It claims exactly what *The report does not claim what the page
     cannot know* forbids, so that scenario has a live violation to
     remove, not merely an absence to fill.
   - It lives on `page.html`, not on the shared header partial, so the
     edit surface has nothing at all — which is what
     `design.md` — *The listener lives in the shared header partial*
     is correcting.
   - It binds one event of three, and it destroys the page to display a
     string, which `design.md` rejects as an alternative.
   - The same copy exists on the roster admin surface
     (`access/…/roster_admin.py`, `templates/roster.html`). That surface
     is out of scope for this change; the copy is noted only so its
     presence is not mistaken for the playbook page's.

2. **`PostgresRoster()` takes no session and opens its own connection
   pool**, binding it to whichever event loop first touches it. Reading
   the roster through it from an integration test leaves the pool bound
   past that module and breaks a later test in the same tier
   (`tests/integration/launch/test_slack_entry_start.py`, *"attached to a
   different loop"*) — observed and then avoided while writing these
   tests. The new integration file uses `PostgresRoster()` only where the
   write is refused before any connection is opened, and reads through
   `RosterRepository(session)` otherwise. Worth knowing before adding
   further integration coverage of this seam.

---

## Unresolved project questions

Each was answered by assumption because this pass runs non-interactively
with no channel to ask on. Each names what depends on it.

1. **Nothing in `AGENTS.md` directs a reader to `test-manifest.md`.** Its
   managed `ai-toolkit:development-workflow` block names the test-writing
   step but not this file, and no `rules/` fragment is imported by
   `AGENTS.md` or `CLAUDE.md`.
   *Assumption taken:* the manifest is reachable only by being named in
   the dispatching agent's report.
   *Depends on it:* whether the implementation step sees any of this at
   all.

2. **The refusal's exception class.** No artifact chooses one.
   *Assumption taken:* assert the delta's stated properties (raised, not
   the fault-carrying type, names both sides) and pin no class.
   *Depends on it:* every test in
   `test_authoring_roster_collaborator_shape.py` and the integration
   refusal test. If the implementation introduces a named class, these
   tests still pass — deliberately.

3. **How the page marks the notice container, and what the notice says.**
   The delta fixes the marker *tokens* and the *content* of the report,
   not the markup mechanism or the words.
   *Assumption taken:* markers are class tokens (this capability's
   existing reading for `just-created`); wording is matched against
   generous phrasing sets scoped to the notice's own region — the
   container's subtree plus the page's scripts — so unrelated page copy
   can neither satisfy nor break a clause.
   *Depends on it:* all six failing tests in
   `test_playbook_admin_write_failure_notice.py`.

4. **Whether `tasks.md` 5.1's "add a case to
   `test_playbook_authoring_live.py`" may be read as a new sibling
   file.** This pass is additive-only and does not edit existing test
   files.
   *Assumption taken:* a new file,
   `tests/integration/launch/test_playbook_authoring_roster_live.py`,
   satisfies 5.1's intent while leaving that file's `roster=None` cases —
   the suite's only coverage of the permitted no-roster path — untouched,
   which 5.1 itself insists on.
   *Depends on it:* whether `tasks.md` 5.1 is ticked by this file or
   still expects an edit to its neighbour. `tasks.md` was not modified by
   this pass.

---

## A note on why the driving-tier failures are trustworthy

The seven failures in `test_playbook_admin_writes_reach_the_roster.py`
all present the same way — the write answers `500` and persists nothing —
which is also how a badly built harness would present. It was checked:
with the store-shaped collaborator swapped for a reader-shaped one and
nothing else changed, **all eight tests in that file pass**. The control
discovery, the payload construction and the assertions are therefore
sound, and what fails is the adaptation the change adds. The swap was a
throwaway diagnostic and is not part of the suite.
