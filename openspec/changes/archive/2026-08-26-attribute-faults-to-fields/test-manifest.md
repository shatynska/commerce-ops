# Test manifest — `attribute-faults-to-fields`

Written before any implementation, from the change's delta specs alone.
Not an artifact the OpenSpec schema knows about: it will **not** appear
among `openspec instructions apply`'s context files, and has to be read
on purpose before implementing.

Every test named here lives in one new file:

```
tests/unit/launch/infrastructure/driving/test_playbook_admin_fault_attribution.py
```

Select an individual test with, for example:

```
uv run pytest "tests/unit/launch/infrastructure/driving/test_playbook_admin_fault_attribution.py::test_a_fault_about_one_field_marks_that_field"
```

## Baseline

Full suite, taken at the worktree root before any test was written:

```
uv run pytest      →  921 passed, 0 failed, 0 skipped   (34.09s)
```

The `tests/integration` tier was **collected and run**, not skipped —
84 of the 921. Full, not scoped.

After this pass:

```
uv run pytest      →  923 passed, 31 failed   (36.11s)
```

Every one of the 31 failures is in the new file. No previously passing
test changed state: 921 + the 2 new passes = 923.

Also run clean on the new file: `uv run ruff check`,
`uv run ruff format --check`, and `uv run mypy .` (260 source files,
no issues).

## The pass is additive only

This pass added one test file and nothing else. No existing test was
edited, deleted, disabled, or weakened, and no implementation was
written — no module, no function, no stub. Nothing was written outside
the dispatched test-path glob `tests/**/test_*.py` except this manifest.

## Failure states, per `ai-toolkit:testing`

29 of the 31 failures are **state 1** — the code ran and produced a
wrong value. The routes, both authoring surfaces and every provocation
execute; what is absent is the marking. Confirmed rather than assumed:
each of the 23 exhaustiveness cases passes its own "this provocation
reached a rule at all" guard, and each was checked to report the exact
fault its inventory entry names (evidence table below).

The remaining 2 are also state 1, on a different assertion: the create
surface renders `step 'mg.strategy.001' …` today, so the
identifier-stripping test fails on a wrong value, and the two
"reports both faults" tests fail with the two defects `proposal.md`
names — the anchor's raise discarding the enum faults, and the
discipline being parsed after the shared helper has already raised.

**No failure is state 2 or state 3.** Nothing fails at import, no
fixture probe fires, and no `pytest.fail` correction point is reached.

**One test is expected to pass on its first run**, and is recorded as
such rather than counted as coverage of new behaviour —
`test_a_fault_about_the_step_set_marks_no_field`, together with its
exhaustiveness twin `[a gate left with no active blocking step]`.
Nothing is marked yet and the gate-holding fault already renders at page
level, so the assertion already holds. This is the "the behaviour
already exists" branch of state 4, not the "asserts nothing" branch: its
positive half (something *is* reported at page level) discriminates, and
its negative half guards against attribution later over-reaching onto a
fault that concerns no control. Both are kept deliberately.

## Scenario accounting

**29 scenarios in the change's delta specs; 29 accounted for below.**
11 covered by this pass; 18 recorded as reproduced-unchanged and covered
elsewhere, per `tasks.md` 2.1's explicit scoping.

### ADDED — *A rejected write names the fields its faults concern* (7)

| Scenario | Test |
|---|---|
| A fault about one field marks that field | `test_a_fault_about_one_field_marks_that_field` |
| A fault about a combination marks every field in it | `test_a_fault_about_a_combination_marks_every_field_in_it` |
| A fault about the step set marks no field | `test_a_fault_about_the_step_set_marks_no_field` |
| Attribution never shortens the fault list | `test_attribution_never_shortens_the_fault_list` |
| A field two faults concern carries both | `test_a_field_two_faults_concern_carries_both` |
| An unparseable anchor value marks the input it came from | `test_an_unparseable_anchor_value_marks_the_input_it_came_from` |
| Both authoring surfaces attribute alike | `test_both_authoring_surfaces_attribute_alike` |

Two normative sentences the requirement states without a scenario of
their own are asserted inside
`test_a_fault_about_a_combination_marks_every_field_in_it`: that marking
renders adjacent to a control the surface does not offer, and that it
does not change whether the control is offered.

### ADDED — *Every rule an authoring write can provoke attributes its fault* (1)

| Scenario | Test |
|---|---|
| No rule an authoring write can provoke is unattributed by accident | `test_no_rule_an_authoring_write_can_provoke_is_unattributed_by_accident` — 23 parametrised cases, ids below |

### MODIFIED — *A step can be edited in place* (5)

| Scenario | Test |
|---|---|
| A clean edit lands | **Not covered here.** Reproduced verbatim from the served spec; covered by `test_playbook_admin_step_fields.py` (`tasks.md` 2.1) |
| A rejected edit shows every fault | **Not covered here.** Reproduced verbatim; covered by `test_playbook_admin_step_fields.py::test_a_form_rejected_by_validation_shows_every_fault_with_the_typed_values` |
| Faults from different sources arrive together | `test_faults_from_different_sources_arrive_together` |
| A create wrong in a field and in its discipline reports both | `test_a_create_wrong_in_a_field_and_in_its_discipline_reports_both` |
| A stale edit is surfaced, not silently dropped | **Not covered here.** Reproduced verbatim; covered by `test_playbook_admin_step_fields.py` |

### MODIFIED — *Steps can be created, retired and un-retired from the page* (16)

| Scenario | Test |
|---|---|
| A rejected create does not name the step it did not persist | `test_a_rejected_create_does_not_name_the_step_it_did_not_persist` |
| Creating is reachable regardless of how large the set is | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A created step appears in its gate | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A step created as a draft is addressed where it renders | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A created step the narrowing keeps visible is still identified | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A create the narrowing would hide is not left looking lost | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A step named as created but not there is ignored | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A draft the narrowing would hide is named like any other step | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A named step the offer could not reveal is ignored | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A rejected create keeps every submitted value | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A rejected create keeps every assignee that was named | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A rejected create keeps the submitted discipline | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A create naming no discipline is refused, not defaulted | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A create naming a retired status is refused | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A stale create is surfaced, not silently dropped | **Not covered here.** Reproduced unchanged; `test_playbook_admin_create_page.py` |
| A blocked retirement explains itself | **Not covered here.** Reproduced unchanged; `test_playbook_admin_page.py` |

The reason is the same for all 15: `tasks.md` 2.1 scopes this pass to the
new scenarios, and the rest are reproduced from the served spec with no
rule change. This is a recorded decision, not an omission — if any of
those blocks turns out to have been edited rather than reproduced, this
pass under-covered the change and should be re-run.

## The exhaustiveness sweep: the 23 cases and the fault each provokes

Case ids, selectable individually — e.g.

```
uv run pytest "tests/unit/launch/infrastructure/driving/test_playbook_admin_fault_attribution.py::test_no_rule_an_authoring_write_can_provoke_is_unattributed_by_accident[unrecognised scope]"
```

Each was run before this manifest was written and confirmed to reach the
rule it names. The "fault reported today" column is **evidence that the
payload provokes the intended rule**, not an assertion any test makes:
nothing in the file is keyed on fault wording.

Structurally attributed, adapter-raised (11), all on the create surface:

| Case id | Fields asserted marked | Fault reported today |
|---|---|---|
| `unrecognised scope` | `scope` | `scope: '…' is not a recognised value` |
| `unrecognised kind` | `kind` | `kind: '…' is not a recognised value` |
| `unrecognised status` | `status` | `status: '…' is not a recognised value` |
| `unrecognised hazard` | `hazard` | `hazard: '…' is not a recognised value` |
| `unrecognised discipline` | `discipline` | `'…' is not a valid Discipline` |
| `unparseable anchor_days` | `anchor_days` | `timing anchor: invalid literal for int() …` |
| `unparseable anchor_start` | `anchor_start` | `timing anchor: invalid literal for int() …` |
| `unparseable anchor_end` | `anchor_end` | `timing anchor: invalid literal for int() …` |
| `unrecognised cadence` | `anchor_cadence` | `timing anchor: '…' is not a valid Cadence` |
| `unknown anchor kind` | `anchor_kind` | `timing anchor: unknown kind '…'` |
| `window end precedes start` | `anchor_start`, `anchor_end` | `timing anchor: window anchor end offset -7 precedes its start offset -3` |

The three `invalid literal for int()` rows are the whole point of
`tasks.md` 1.1: they are indistinguishable today, and the three cases
differ only in which box carried the bad value.

Text-keyed, crossing from the domain or the application (11), all on the
create surface:

| Case id | Fields asserted marked | Fault reported today |
|---|---|---|
| `declares unknown gate` | `gate` | `step '…' declares unknown gate '…'` |
| `has an empty name` | `name` | `step '…' has an empty name — …` |
| `name spanning more than one line` | `name` | `step '…' has a name spanning more than one line — …` |
| `prohibited-tactic cannot block its gate` | `hazard`, `blocking` | `step '…' is classified 'prohibited-tactic' and cannot block its gate` |
| `automated, beyond draft, no automation brief` | `kind`, `status`, `automation_brief` | `step '…' is automated and beyond draft (status 'active') but carries no automation brief` |
| `automated and active but names no handler` | `kind`, `status`, `handler` | `step '…' is automated and active but names no handler — …` |
| `human step cannot carry an automation brief` | `kind`, `automation_brief` | `step '…' is a human step and cannot carry an automation brief` |
| `human step cannot name a handler` | `kind`, `handler` | `step '…' is a human step and cannot name a handler` |
| `names assignee the roster does not carry` | `assignees` | `step '…' names assignee '…', whom the roster does not carry` |
| `active human step names no active assignee` | `kind`, `status`, `assignees` | `step '…' is an active human step and names no assignee who is active on the roster — …` |
| `names handler no registered use case answers to` | `handler` | `step '…' names handler '…', which no registered use case answers to` |

Recognised, held at page level (1), on the **edit** surface, because a
create adds a step to a gate and can never take away the gate's last
blocking step:

| Case id | Fields asserted marked | Fault reported today |
|---|---|---|
| `a gate left with no active blocking step` | none — asserted page-level, and that **no** field is marked | `gate 'listable' has no active blocking step attached — …` |

`automated, beyond draft, no automation brief` provokes two faults at
once (the no-handler rule fires alongside). The case asserts only the
three fields its own rule concerns, so the extra fault neither weakens
nor breaks it.

The seven rules `design.md` records as unprovokable by any write are
deliberately absent: the four `_gate_sequence_faults` produces,
`_gate_condition_faults`'s empty-threshold description, duplicate step
identifier, and `StepDefinition.__post_init__`'s unrecognised
discipline. `tasks.md` 3.6 says not to attempt them, and a rule that
cannot be provoked cannot be checked by provoking it.

### What the sweep does not catch

Stated in the test's own docstring as well as here, per `tasks.md` 3.7:
it catches a rule **reworded**, not a rule **added**. Nothing enumerates
the rule set mechanically, so a coherence rule introduced later is
simply missing from `_PROVOCATIONS` and nothing goes red. The eleven
adapter-raised faults are exempt from that limit only because
`tasks.md` 1.3a makes the fields a required argument of the carrier, so
mypy refuses a new adapter fault that decides none — if 1.3a is
implemented with a default, this exemption is void and the manifest is
wrong about it.

## Assertion classification

### Specified

Every assertion below traces to a sentence in the delta or, where noted,
to `design.md`/`tasks.md`, which the delta itself defers to for the
inventory.

- A fault about one field marks that field, and no other field is marked
  with it.
- A fault about a combination marks **every** field in the combination.
- A fault about the step set or a gate marks no field and renders at
  page level.
- Marking renders adjacent to a control the surface does not offer, and
  does not change whether it is offered (asserted as: the automation
  brief is still `disabled` on a `human` step in the rejection).
- A field named by more than one fault is marked once and carries all of
  them.
- Attribution is additional, never a filter: a fault marked on a field
  is still rendered in the surface's own fault list.
- An unparseable anchor input marks the input it came from and neither
  of the anchor's others.
- Both authoring surfaces attribute alike.
- Every rule in `design.md`'s inventory is attributed to the fields that
  inventory records, and the one recognised page-level fault is not
  attributed to any.
- A submission wrong in an enum and in the anchor reports both; a create
  wrong in a field and in its discipline reports both.
- A create's step-level fault names no generated identifier, and no
  reported fault still opens with the literal `step '`.
- Nothing is persisted by any rejection (`store.saves == []`).

### Derived — recorded here because nobody agreed to them

1. **What "the field's own control carries the fault text" means in
   markup.** The delta fixes the observable but not the rendering. This
   file reads a control's own region as *the largest element containing
   that control and no other*, plus what the control points at
   explicitly (`aria-describedby`, `aria-errormessage`, `aria-details`,
   `title`, `aria-label`, `data-fault`, `data-error`) and any element
   carrying a `data-*` attribute whose value is the control's name.
   Correction point: `_marking_of`.

   Two consequences follow, and both are deliberate. A fault rendered
   into a wrapper shared by two controls attributes to **neither** —
   which is what forces *An unparseable anchor value marks the input it
   came from* to be honoured per-input rather than per-anchor-group. And
   the page-level fault list attributes to nothing, which is what makes
   the two negative scenarios assertable at all.

2. **Marking is read differentially** — the same surface rendered clean
   and rejected, with the difference taken as what the field was marked
   with. Chosen so that no assertion is keyed on any fault's wording,
   which is the coupling `design.md` warns the text-keyed half carries.
   The cost: a marking whose text a *clean* render already carries would
   be invisible to these tests.

3. **Text inside a control is excluded everywhere** — a `<select>`'s
   option labels, a `<textarea>`'s contents. Those are submitted values,
   not something the surface says, and including them would make the
   differential read a changed value as a marking.

4. **`input type="hidden"` is not a control** for attribution. It is a
   routing value nobody types, so no fault concerns it; counting it
   would also split the field groups the whole reading rests on. A
   consequence: if a not-offered anchor input is rendered as
   `type="hidden"` rather than as a visible input inside a hidden
   wrapper, the negative half of the anchor scenario passes vacuously
   for that input. The positive half is asserted on an input that is
   offered, so the scenario still discriminates.

5. **"Both faults are reported" is read as a superset relation** against
   what each fault reports on its own, not as a fragment count. The
   count reading was written first and rejected on evidence: the fault
   list carries its own heading, so a one-fault rejection already yields
   two fragments and the count would have been satisfied vacuously.

6. **`_NOT_A_VALUE` / `_NOT_A_NUMBER`** — nothing is asserted about how a
   refused value is echoed back, only that submitting it is refused.

7. **`mg.` as the generated-identifier namespace**, taken from
   `test_playbook_admin_create_page.py`, which asserts it of a landed
   create. Correction point: `_GENERATED_NAMESPACE`.

   **Corrected at implementation time, with the author's agreement.** As
   written, `test_a_rejected_create_does_not_name_the_step_it_did_not_persist`
   scanned the whole response body for `mg.`. The create surface's own
   help text spells the generated shape — `mg.<discipline>.<seq>` — and
   has since `add-step-page`, so that assertion fails on a clean create
   surface carrying no fault at all and cannot tell an unstripped fault
   from the page explaining itself. It is now asserted over `reported`,
   which is the delta's own wording (*"the **reported fault** does not
   identify that step…"*). Confirmed still discriminating: with the
   stripping disabled the assertion fails. Nothing else in the file
   changed.

8. **`assert response.status_code < 500`** on a rejection. The delta
   says a rejection re-renders; it fixes no status code.

9. **The seeded fixture** — one active blocking step per gate plus two
   ordinary `listable` steps — so that an edit aimed at `listing.zeta`
   provokes only the rule under test, while `hold.listable` is the step
   whose unblocking provokes the gate-holding fault.

### Deliberately untested

- **Presentation of a marked field** — colour, placement, iconography.
  `design.md` assigns it to `admin-presentation-vocabulary`, sequenced
  after this change.
- **The step list's rejections** (retire, un-retire, status change,
  move). The delta binds the two surfaces carrying the authorable form
  and says list-level rejections keep rendering exactly as they do; no
  test here touches `page.html`. `tasks.md` 6.5 asks for that to be
  confirmed at implementation time — it is a non-regression check
  against the existing suite, not a new test this pass owes.
- **Client-side validation** — a stated non-goal.
- **A rule added to the domain later** — see *What the sweep does not
  catch*.
- **The exact text a fault renders.** Deliberate, not an oversight:
  keying on wording is what `design.md` identifies as the fragility the
  two-tier split exists to reduce, and a test that pinned the wording
  would relocate the coupling rather than remove it.

## Unresolved project questions

Read in this repository's `AGENTS.md` and `CLAUDE.md`: the test command
(`uv run pytest`), the three-tier layout, the test-path glob, and the
`httpx2` form-encoding trap were all recorded there and are followed.
The following had no recorded answer, were resolved by assumption, and
are surfaced rather than settled silently.

| Question | Assumption taken | Tests depending on it |
|---|---|---|
| How a marked control is expressed in markup | The region reading in *Derived* 1 | All 11 marking tests and all 22 attributing sweep cases |
| Which module attribute the page reads the roster through | `_install_roster` probes `roster`, `read_roster`, `people`, `roster_reader` and fails loudly if none — inherited from the sibling admin tests | Every test in the file |
| How the create surface is reached from the list | A live GET control whose URL mentions `new`/`create`/`add`, leading to a form carrying both a name and a discipline field — inherited from `test_playbook_admin_create_page.py` | Every create-surface test |
| The session cookie, the guard seam, the `steps` seam | `admin_session`, `verify_admin_session`, `steps` — inherited, and already satisfied by the implementation | Every test in the file |
| Whether the manifest is reachable from a convention file | It is **not**. This repository's `AGENTS.md` carries the managed `ai-toolkit:development-workflow` block, which names the test-writer dispatch but says nothing about a `test-manifest.md`. Nothing in the repo points at this file | Nothing — but whoever implements will not find this manifest unless told, which is why the writer's report names its path |

None of these was resolvable by asking: this pass ran as a dispatched
subagent with no channel to ask on.

## Obsolete tests

Searched: every file matching the dispatched glob `tests/**/test_*.py`,
for the fault texts the two `MODIFIED` requirements bear on
(`timing anchor`, `not a recognised value`, `is not a valid Discipline`,
`unknown kind`), for the generated-identifier namespace `mg.`, and for
`step '` in the adapter tests. No earlier `test-manifest.md` was
supplied to this pass, so none was used as a scenario-to-test map.

**No bearing test was found by this search** — and for the two strongest
candidates the evidence supports the stronger claim that none exists:

- *Superseded by:* MODIFIED *A step can be edited in place*, whose new
  "every fault across all the values the surface itself parses"
  paragraph changes what a submission wrong in both an enum and the
  anchor reports. **Evidence:** no test in the glob matches
  `timing anchor` or `not a recognised value` as asserted text — the
  only hits are docstrings in `test_playbook_admin_anchor_inputs.py` and
  `test_playbook_admin_create_page.py` describing the requirement, not
  asserting a fault. This corroborates `design.md`'s own note under
  *Risks / Trade-offs*: "There is no existing adapter test for
  `timing anchor:` or `not a recognised value`."
- *Superseded by:* MODIFIED *Steps can be created, retired and
  un-retired from the page*, whose new paragraph forbids a create's
  step-level fault naming the generated identifier. **Evidence:** no
  adapter test asserts a `step '…'` prefix or an `mg.` identifier in a
  rejection body. The `mg.` hits in
  `tests/unit/launch/application/test_playbook_authoring*.py` are
  application-layer assertions about identifiers the write *generates*,
  which this change does not touch — the stripping is adapter-side —
  and the `mg.` hit at `test_playbook_admin_create_page.py:1037` is on a
  **landed** create's identifier, not a rejected one, so it is not
  superseded either.

**Every entry above is a candidate for human confirmation**, not a
conclusion — and here every entry is a negative one, so what needs
confirming is the absence rather than a deletion. Nothing in this
manifest asks for a test to be removed or rewritten, and this pass
removed none.

One adjacent risk, recorded as a risk and **not** as an obsolete-test
entry, because nothing about it is superseded: `_fields.html` is shared,
and `test_playbook_admin_anchor_inputs.py` reads each anchor input's
hidden/disabled state by walking its ancestors. If marking is
implemented by introducing a wrapper element around a control, those
tests could change state for a reason unrelated to what they assert.
That would be a signal to look at the markup, never a licence to
weaken them.
