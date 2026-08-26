# Test manifest — `tag-tasks-with-gate-and-discipline`

Written by `openspec-test-writer` from the change's delta specs alone, in a
worktree rewound to the commit before any of this change's implementation
landed. No implementation source for the behaviour under test was read.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and has to be
opened on purpose.

## Baseline

Scoped baseline, taken before any test was written:

```
uv run pytest tests/unit tests/agents     →  1064 passed, 0 failed
```

Scoped to the two unit tiers because every test this pass adds is unit-tier
(`AGENTS.md`, Testing Strategy) and the integration tier needs a database
this environment does not resolve. `tests/integration` was **not** run, and
no claim here rests on it.

Re-run after the tests were added, with `--continue-on-collection-errors`
(see *Expected first-run state* below):

```
uv run pytest tests/unit tests/agents --continue-on-collection-errors
  →  1064 passed, 12 failed, 2 errors
```

The passing count is unchanged. Every failure and both errors come from the
three files this pass added.

## Expected first-run state

All three files are expected to be red until the implementation lands, and
each is red for the *absent-target* reason (`ai-toolkit:testing` failure
state 2), not because a test is broken:

| File | First-run state |
|---|---|
| `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py` | **collection error** — `ImportError: cannot import name 'add_task_tag'` |
| `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py` | 12 failed — the pass composes no tags at all |
| `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py` | 1 error — `monkeypatch.setattr(clickup_client, "add_task_tag", …)` fails strictly on the absent operation |

`uv run mypy .` reports exactly six errors, all in the client file and all
naming an absent target: `add_task_tag` missing, `create_task` having no
`tags` keyword, and `ClickUpTaskState` having no `tags` attribute. That is
the same three absences stated a second way, and it is the cheapest check
that the implementation has landed all of task 1.

**Note for whoever runs the suite next.** A module-level import of an absent
name halts *collection*, so `uv run pytest tests/unit tests/agents` stops at
the client file and never reaches the other 1064 tests. Pass
`--continue-on-collection-errors` until task 1.4 lands. This is the idiom
this directory already uses for test-first work
(`test_clickup_client_list_and_read.py` did the same for `create_list` and
`list_tasks`), kept rather than softened because a guarded import would blur
the absent-target signal into something less legible.

### Confirming the tests discriminate (`tasks.md` 3.1c)

Six of the projection tests assert an *absence* — no tag write, no removal.
On the first draft of this pass, all six **passed** against a system with no
tagging at all, which `ai-toolkit:testing` names an alarm rather than a
result. Each now carries a **control step** in the same playbook whose task
must be observed created carrying both of its tags
(`_assert_the_pass_did_tag`), so the test fails on an absent target and its
absence assertion only becomes readable once the pass genuinely tags. That
control is the reason these tests are red today rather than green.

That is not a substitute for `tasks.md` 3.1c. The mutation check named there
still has to be run against these files once the implementation exists.

## Scenario accounting

43 `#### Scenario:` blocks across the two delta specs — 29 in
`launch-clickup-sync`, 14 in `clickup-task-client`. Each is accounted for
exactly once below.

Test identifiers are runner-selectable as written, e.g.

```
uv run pytest "tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py::test_a_hand_removed_tag_is_added_back"
```

Files are abbreviated below:

- **SYNC** = `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py`
- **JOB** = `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py`
- **CLIENT** = `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py`

### `launch-clickup-sync` — ADDED: *A projected task carries its step's gate and discipline as tags* (9 scenarios)

| Scenario | Covered by |
|---|---|
| A newly projected task carries both tags | `SYNC::test_a_newly_projected_task_carries_both_tags` |
| An existing untagged task gains its tags | `SYNC::test_an_existing_untagged_task_gains_its_tags` |
| A task already carrying its tags is left alone | `SYNC::test_a_task_already_carrying_its_tags_is_left_alone` |
| A person's own tags are never touched | `SYNC::test_a_persons_own_tags_are_never_touched` |
| A step moved between gates keeps its original gate tag | `SYNC::test_a_step_moved_between_gates_keeps_its_original_gate_tag` |
| A hand-removed tag is added back | `SYNC::test_a_hand_removed_tag_is_added_back` |
| A step that has left the projection is not tagged | `SYNC::test_a_step_that_has_left_the_projection_is_not_tagged[status-retired]`, `[status-in-development]`, `[kind-automated]`, `[hazard-prohibited-tactic]`, `[undefined]` |
| No tag is written during a stand-down | `JOB::test_no_tag_is_written_during_a_stand_down` |
| A tag that cannot be set on a task is reported, not fatal | `SYNC::test_a_tag_that_cannot_be_set_is_reported_and_not_fatal` |

Notes on two of them:

- **A step that has left the projection is not tagged** is parametrised over
  all four grounds and not a subset, deliberately. The requirement
  *references* `A step that is not active leaves the loop` rather than
  paraphrasing it, on the stated ground that "a rule naming fewer would
  leave the rest undefined"; a parametrisation covering fewer would
  reintroduce that gap. The fifth case (`undefined`) is the step the served
  playbook does not define, which arrives on the projection requirement's
  own ground — and it is the one that catches a backfill driven from the
  *mapping* rather than from the playbook's served steps.
- **No tag is written during a stand-down** sits at the job level because
  the stand-down declines before the pass body is entered, so
  `converge_launch` has no stand-down state to be tested in. The existing
  `test_clickup_sync_job_stand_down.py` already entails it on today's shape;
  the new test adds the one thing that file cannot catch — a tag backfill
  written into the *job body*, outside `converge_launch`, which would run
  whether or not the passes did.

### `launch-clickup-sync` — MODIFIED: *Human steps are projected as tasks carrying their name, description and assignees* (20 scenarios)

**All 20 accounted for as: unchanged, already covered, no new test.**

Verified by diff: the delta's scenario block for this requirement is byte-
identical to the baseline's under `openspec/specs/launch-clickup-sync/`
(one trailing newline apart). The modification is confined to one clause of
the assignee paragraph — "Assignees are the one **retained** field where
that reading is right", plus a sentence noting that the tag rule reaches the
same reading by another route and does not qualify it.

That clause changes no observable behaviour: it narrows the *scope of a
claim about* the retained-field reading, and the tag rule it defers to
retains nothing at all. No new test is owed, and no existing assertion is
superseded (see *Obsolete tests* below).

The 20 stay covered where they already are, in
`tests/unit/launch/infrastructure/driven/`:
`test_clickup_projection_step_fields.py`, `test_clickup_sync_projection.py`,
`test_clickup_sync_wording_heal.py`, `test_clickup_task_naming.py`,
`test_clickup_task_name_composition.py`,
`test_clickup_non_active_steps_leave_loop.py`,
`test_clickup_automated_steps_leave_loop.py`. None was touched.

### `clickup-task-client` — ADDED: *A task can be created carrying tags* (2 scenarios)

| Scenario | Covered by |
|---|---|
| Task created with tags | `CLIENT::test_a_task_is_created_carrying_the_supplied_tags` |
| Task created without tags | `CLIENT::test_a_create_without_tags_sends_no_tags_field_at_all` |

### `clickup-task-client` — ADDED: *A tag can be added to an existing task* (2 scenarios)

| Scenario | Covered by |
|---|---|
| A tag is added to a task | `CLIENT::test_a_tag_is_added_to_a_task_with_no_space_request_first` |
| Adding a tag twice is not an error | `CLIENT::test_adding_a_tag_the_task_already_carries_is_not_an_error` |

### `clickup-task-client` — MODIFIED: *The tasks of a list can be read* (4 scenarios)

| Scenario | Covered by |
|---|---|
| Tasks returned with status and due date | **Unchanged, already covered** — verbatim from the baseline; `test_clickup_client_list_and_read.py::test_tasks_are_returned_with_status_closed_judgement_and_due_date`. Its payloads carry **no** `tags` key, so it doubles as the guard that the extended parse tolerates a payload from before tags were read. |
| Tasks returned with their tags | `CLIENT::test_tasks_are_returned_with_their_tag_names` (+ `CLIENT::test_a_task_payload_without_a_tags_key_reads_without_erroring` for the derived tolerance half) |
| An empty list reads as empty | **Unchanged, already covered** — `test_clickup_client_list_and_read.py::test_an_empty_list_reads_as_empty_rather_than_erroring` |
| A multi-page list is read completely | **Unchanged, already covered** — `test_clickup_client_list_and_read.py::test_a_multi_page_list_is_read_completely` |

### `clickup-task-client` — MODIFIED: *A failed ClickUp request is surfaced to the caller* (6 scenarios)

| Scenario | Covered by |
|---|---|
| ClickUp rejects a create request | **Unchanged, already covered** — `test_clickup_client.py` |
| ClickUp rejects an update request | **Unchanged, already covered** — `test_clickup_client.py` |
| ClickUp rejects a create-list request | **Unchanged, already covered** — `test_clickup_client_list_and_read.py::test_a_rejected_create_list_request_raises` |
| ClickUp rejects a read of a list's tasks | **Unchanged, already covered** — `test_clickup_client_list_and_read.py::test_a_rejected_read_of_a_lists_tasks_raises` |
| ClickUp is unreachable | `CLIENT::test_add_task_tag_when_clickup_is_unreachable_raises` — the **new operation's** path only. The scenario is verbatim, but its requirement's enumeration now names a fifth operation and "any of the client's requests" reaches it. The four existing paths stay covered by the two existing files. |
| ClickUp rejects a tag write | `CLIENT::test_a_rejected_tag_write_raises` |

## Assertion classification

`ai-toolkit:testing` requires every assertion to be **specified**,
**derived**, or **deliberately untested**. Each is labelled inline at its
assertion in the test files; this is the summary of the derived and
deliberately-untested ones, which are the two that oblige review.

### Derived (inferred; no scenario states them)

| Assertion | Where | Why derived |
|---|---|---|
| The endpoint path carries the list id / the task id | CLIENT (create, add-tag) | The scenarios say "ClickUp receives a create-task request **for that list**" / "an add-tag request **for that task**"; the path is how that is observed. Follows the convention `test_clickup_client.py` already set. |
| A payload omitting the `tags` key reads as carrying no tags | `CLIENT::test_a_task_payload_without_a_tags_key_reads_without_erroring` | No scenario states it. Asserted because `tasks.md` 1.1 defaults `tags` to empty precisely so "existing constructions stay valid", and a task ClickUp answers without the key must not become an error on a pass that used to work. |
| A tag object carrying no `name` does not cost the task its named tags | same test | `tasks.md` 1.2 says to tolerate one; no artifact says what it *becomes*, so only "the named tags survive" is asserted. |
| Tags are never sent on an update body | `SYNC` — the fake's `update_task` asserts it | `design.md`: "Tags do not ride `PUT /task/{id}`". A design measurement, not a scenario. Stated as a fixture guard rather than a test of its own so it costs no scenario slot. |
| A tag write failure is caught **per tag**, so the launch's *other* work is still projected | `SYNC::test_a_tag_that_cannot_be_set_is_reported_and_not_fatal` | The scenario says the pass "continues and still succeeds"; that the pass still projects a *different* step's task is the design's "costs tags and nothing else" made checkable, and is one reading further than the scenario's words. |
| The warning names the step, the tag and the task by **substring containment** | same test | The requirement fixes the three facts; no artifact fixes the wording or order. |
| A control step's task is created carrying both tags, in every absence-asserting test | `SYNC`, `_assert_the_pass_did_tag` | Not a requirement — a guard against the fourth failure state. See *Confirming the tests discriminate* above. |
| The pass reaches for nothing space-shaped or removal-shaped, read off the fake's probe record | `SYNC`, `_assert_nothing_space_level` / `_assert_nothing_removed` | The requirement's words ("SHALL NOT maintain, seed, or verify any tag vocabulary", "SHALL NOT remove a tag") are specified; that a *word-matched attribute probe* is the right observation of them is derived. A method named outside `_SPACE_WORDS`/`_REMOVAL_WORDS` would slip past. |

### Deliberately untested (identified, knowingly uncovered, with the reason)

Recorded in full at the foot of each test file. In summary:

- **A graduated launch's tasks are never tagged or backfilled.** Stated
  inside the tag requirement but on another requirement's ground, and
  carrying no `#### Scenario:` of its own. `test_clickup_sync_projection.py::test_a_graduated_launch_is_left_alone`
  already asserts a graduated launch causes *no ClickUp call whatever*,
  which subsumes a tag write.
- **That the add-if-missing judgement costs no extra read.** A `design.md`
  Goal ("the tags a pass judges against arrive in the task list it already
  fetches"), stated in Goals rather than in any scenario.
- **Tag colour and ordering.** A named Non-Goal.
- **Whether `add_task_tag` returns anything.** The requirement constrains
  only the failing path ("no result").
- **`Authentication is configured independently of any one caller` over
  `add_task_tag`.** That requirement is unmodified by this delta and its
  scenarios name "a task is created or updated" — the same reading
  `test_clickup_client_list_and_read.py` recorded for the two operations it
  added.
- **Removing a tag.** No removal operation exists on either the client or
  the projection; the fakes offer none, so an implementation reaching for
  one fails rather than being asserted about.
- **Tags on the launch list itself, or on metric conditions.** Named
  non-goals with no task-shaped thing to assert the absence of. (The
  automated-step half of that non-goal *is* covered, by the `kind-automated`
  departure case.)

## Obsolete tests

**No bearing test was found, and the distinction matters:** this is "none
was found by this bounded search", not "no such test exists".

The search was bounded to the dispatched test-path glob `tests/**/test_*.py`
within this worktree. No earlier `test-manifest.md` path was supplied, so no
scenario-to-test index was available to widen it.

What was searched, and what it found:

- `grep -rn "tags\|tag_" tests/ --include=test_*.py` → **no hit at all**.
  Not one test in the suite mentions a tag.
- `grep -rn "space" tests/ --include=test_*.py` → hits only on the English
  word ("a space, a middle dot, a space" in the name-separator tests,
  "whitespace", "namespace"). No test bears on a ClickUp *space*.

Read against each MODIFIED delta:

| MODIFIED requirement | Superseded behaviour | Bearing tests |
|---|---|---|
| `launch-clickup-sync` / *Human steps are projected as tasks…* | The clause "Assignees are the one field where that reading is right" is narrowed to "the one **retained** field". Nothing observable changes: the qualifier bounds a claim about the retained-field reading, and the tag rule it defers to retains nothing. All 20 scenarios are byte-identical to the baseline. | **None.** No existing assertion tests the claim as a claim; the assignee tests assert the behaviour, which is unchanged. |
| `clickup-task-client` / *The tasks of a list can be read* | Purely additive: the read now also reports each task's tag names. Nothing previously returned stops being returned. | **None.** `test_clickup_client_list_and_read.py`'s read tests assert on `.id`, `.status`, `.closed`, `.due_date` and are unaffected. |
| `clickup-task-client` / *A failed ClickUp request is surfaced to the caller* | Purely additive: the enumeration gains a fifth operation. | **None.** The four existing rejection tests each name one of the four original operations. |

`tasks.md` 1.6 removes the seeding code "and their tests". Those tests do
not exist in this worktree — it is rewound to before any of this change's
implementation landed — so there is nothing here to list. **Whoever
reconciles this manifest against the branch it was rewound from must check
that separately**, on the branch: any test of `create_space_tag`,
`space_tags`, `space_id_for_folder`, `tag_vocabulary`,
`ensure_tag_vocabulary` or `tags_ready` is superseded by the deletion of the
premise those symbols rested on, and `tasks.md` 3.0a is explicit that a
green suite established nothing about that removal — it has to be verified
by grep.

Nothing above is a conclusion. Every entry that reaches this list in a
future pass is a **candidate for human confirmation**, never a licence to
delete.

## Unresolved project questions

Each was taken as an assumption because this pass is non-interactive and has
no channel to ask on. None is resolved silently; each names the tests that
depend on it. Every one is a **fixture correction** if wrong — not a licence
to weaken what the test asserts.

| Question | Assumption taken | Tests depending on it |
|---|---|---|
| `add_task_tag`'s call shape. `tasks.md` 1.4 fixes the two argument *names*; nothing fixes positional vs keyword. | Called positionally, `add_task_tag(task_id, tag_name)`. Single correction point: `CLIENT::_add_tag`, and `_FakeClickUp.add_task_tag` in SYNC (which accepts either). | All four CLIENT tag tests; all SYNC backfill tests. |
| Whether the projection's ClickUp **port** exposes the same `add_task_tag`, or reaches it another way. | It is a method on the injected `clickup` collaborator, alongside `create_list`/`create_task`/`update_task`/`list_tasks`. | Every SYNC test asserting a tag write. |
| `converge_launch`'s signature. Inherited from `test_clickup_projection_step_fields.py`; no artifact fixes it. | `converge_launch(launch=, playbook=, clickup=, mapping=, read_product=, roster=, folder_id=)`. Correction point: `SYNC::_converge`. | Every SYNC test. |
| The exception type a failed tag write raises. No artifact names one. | Any `Exception`; CLIENT scopes `pytest.raises(Exception)` to the single call, SYNC's fake raises its own `_TagWriteRefused` and the pass is required only to *survive* it. | `CLIENT::test_a_rejected_tag_write_raises`, `SYNC::test_a_tag_that_cannot_be_set_is_reported_and_not_fatal`. |
| The warning record's wording. The requirement fixes three facts, not a format. | Substring containment of the step identifier, the tag name and the task identifier in the joined `WARNING`-or-above messages — the same reading `test_clickup_projection_step_fields.py` already took for the assignee warning. | `SYNC::test_a_tag_that_cannot_be_set_is_reported_and_not_fatal`. |
| Which level the stand-down tag scenario belongs at. `AGENTS.md` fixes the tier directories but not which layer observes a stand-down. | The job body, following `test_clickup_sync_job_stand_down.py`. | `JOB::test_no_tag_is_written_during_a_stand_down`. |
| Whether the container of the create body's `tags` claim is a list of names or of objects. | Neither is pinned; `_tag_names` reads both, and the assertion is on the names. | `CLIENT::test_a_task_is_created_carrying_the_supplied_tags`, `SYNC::test_a_newly_projected_task_carries_both_tags`. |
| Whether a test-first module-level import of an absent name — which halts pytest *collection* for the whole tree, and so the pre-commit hook with it — is acceptable in this project. | Yes: `test_clickup_client_list_and_read.py` set that precedent and documented it. Kept rather than softened, because a guarded import blurs the absent-target signal. | `CLIENT` (the whole file). |

## This pass is additive only

It adds three test files and this manifest. It edited, deleted or disabled
**no** existing test, wrote no implementation, and created no stub to make a
test execute. The 1064 tests that passed at baseline still pass, unchanged.

Files written:

- `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py`
- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py`
- `openspec/changes/tag-tasks-with-gate-and-discipline/test-manifest.md` (this file)

`uv run ruff check` and `uv run ruff format` are clean on all three test
files. `uv run mypy .` reports only the six absent-target errors listed
above.
