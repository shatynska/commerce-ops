# Test manifest — `restore-automated-decisions`

Written by `ai-toolkit:openspec-test-writer` from the change's delta spec
before any of `tasks.md` groups 1–3 were applied (`tasks.md` 4.1). This
file is **not** an artifact the OpenSpec schema defines, so
`openspec instructions apply` will not surface it among a change's
context files — it has to be read on purpose.

This pass is **additive only**: it added two test files and edited,
deleted or disabled nothing. `tests/unit/launch/application/
test_automated_result_decisions.py` was read but not touched;
`tasks.md` 4.2's narrowing of its `_FakeRoster` is implementation work
and is deliberately left undone (see *Unresolved project questions*, Q1).

No file under `src/` was written or modified.

## Baseline

`uv run pytest` at the worktree root, before either new file existed:

```
1155 passed, 0 failed, 96 skipped in 41.85s
```

Full-suite, not scoped. The 96 skips are the whole `tests/integration`
tier, which finds no `DATABASE_URL` in this worktree and says so per
test; that is this environment's normal state, recorded so a later
comparison does not read it as a regression.

- Commit: `ea9f31b`, clean tree, 2026-08-27.
- Worktree: `/home/shatynska/projects/commerce-ops/.claude/worktrees/slack-decision-identity-refused`

After this pass, the same command reports **9 failed, 1160 passed, 96
skipped**. The arithmetic closes exactly: 1160 − 1155 = the 5 new tests
expected to pass, and the 9 failures are the 9 new tests expected to
fail. No pre-existing test changed state.

## Files added

| File | Tier | Carries |
|---|---|---|
| `tests/unit/launch/application/test_automated_decision_roster_shape.py` | `tests/unit/launch/application/` | Scenarios 1, 2, 3; the use-case halves of 4 and 5; the requirement's read-ordering statement |
| `tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py` | `tests/unit/launch/infrastructure/driving/` | Scenario 6 whole; the adapter halves of 4 and 5 |

Both are runnable by path or by node id with `uv run pytest`.

## Scenario accounting

Six `#### Scenario:` blocks appear under the one MODIFIED requirement.
All six are accounted for; **six covered, none uncovered**.

### 1. An unknown identity cannot decide — COVERED

- `tests/unit/launch/application/test_automated_decision_roster_shape.py::test_an_unknown_identity_cannot_decide[accepting]`
- `tests/unit/launch/application/test_automated_decision_roster_shape.py::test_an_unknown_identity_cannot_decide[rejecting]`

Already covered by
`tests/unit/launch/application/test_automated_result_decisions.py::test_an_unknown_identity_cannot_decide`.
Re-covered here because the delta carries the scenario forward while
narrowing the collaborator it is judged against: the existing test runs
against `_FakeRoster`, which answers six read spellings at once and so
cannot observe the shape this delta states. The new pair runs against
`_ReaderRoster` — `list_people` and nothing else.

**Expected first-run state: PASS.** A regression guard, not coverage of
new behaviour. Actual: PASS.

### 2. A deactivated person cannot decide — COVERED

- `…test_automated_decision_roster_shape.py::test_a_deactivated_person_cannot_decide[accepting]`
- `…test_automated_decision_roster_shape.py::test_a_deactivated_person_cannot_decide[rejecting]`

Same reasoning as scenario 1. Kept distinct from it because "known" and
"active" are two facts decided in `launch` over the full roster,
deactivated entries included (`design.md` — Decision 2).

**Expected first-run state: PASS.** Actual: PASS.

### 3. A collaborator that cannot answer who the roster carries is refused by name — COVERED

- `…test_automated_decision_roster_shape.py::test_a_collaborator_that_cannot_answer_is_refused_by_name[accepting]`
- `…test_automated_decision_roster_shape.py::test_a_collaborator_that_cannot_answer_is_refused_by_name[rejecting]`

Both verdicts, because the proposal names two use cases taking the
collaborator and a fix applied to `accept` alone would leave `reject`
refusing every identity.

**Expected first-run state: FAIL.** Actual: FAIL, on
`assert outcome.raised is not None` — the decision returns
`Decision(refused=True, reason='the roster does not know that Slack
identity, so the decision was not recorded')` instead of raising.
`ai-toolkit:testing` failure state 1: the code ran and produced a wrong
value.

### 4. An absent collaborator is refused the same way, not silently — COVERED, in two halves

Use-case half — that both wiring faults are one error:

- `…test_automated_decision_roster_shape.py::test_an_absent_collaborator_is_refused_the_same_way`

Adapter half — the error's type, and that the decider is answered:

- `tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py::test_an_absent_collaborator_raises_the_named_wiring_error`
- `…test_automated_decision_wiring.py::test_a_wiring_fault_answers_the_decider_rather_than_falling_silent`

**Expected first-run state: FAIL, all three.** Actual: FAIL.

- The use-case test fails on `with_nothing.raised is not None` — nothing
  raises for either fault today.
- The adapter type test fails on
  `type(caught.value) is not RuntimeError`, quoting the real message:
  `RuntimeError('a decision arrived on an automated result, but no
  roster reader was injected; \`main.py\` supplies one after the routers
  are mounted')`. That is `tasks.md` 2.2's target exactly — the message
  survives, the type changes.
- The reply test fails on `answer.escaped is None`, having observed that
  same `RuntimeError` escape the decision listener with nothing sent to
  the decider. That is the forbidden outcome the scenario names, observed
  rather than inferred (failure state 1).

### 5. A mis-wiring is never reported as an unknown identity — COVERED, in two halves

Use-case half — the fault is not resolvable into a statement about the
decider:

- `…test_automated_decision_roster_shape.py::test_a_mis_wiring_is_never_reported_as_an_unknown_identity[accepting]`
- `…test_automated_decision_roster_shape.py::test_a_mis_wiring_is_never_reported_as_an_unknown_identity[rejecting]`

Adapter half — the reply carries no clause about the decider, and the
fault reaches operators:

- `…test_automated_decision_wiring.py::test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators`

**Expected first-run state: FAIL, all three.** Actual: FAIL.

- The use-case pair fails on `not _blames_the_identity(outcome.text)`,
  quoting the production sentence verbatim. The decider in those tests is
  Alice, whom the roster carries as active, which is what makes the
  failure a statement about the mis-wiring rather than about her.
- The adapter test fails on its non-vacuity guard (`answer.answered`):
  there is no reply at all today, so the "does not say" assertions would
  otherwise pass by silence.

### 6. A person the roster carries can decide through the wiring production supplies — COVERED

- `…test_automated_decision_wiring.py::test_a_roster_person_can_decide_through_the_injected_collaborator`

This is the one `design.md` — Decision 6 constrains most tightly. It
imports `commerce_ops.main`, reads
`automation_confirmation.read_people` **as injected** (never rebuilt),
and substitutes at the store — `commerce_ops.main.roster` — and nowhere
lower, per `tasks.md` 4.5. The roster rows are produced by driving
`access`'s own `create_person`, so the injected reader adapts real rows
through `access`'s real `list_people`.

`store.loads >= 1` is asserted for a specific reason: a reader that
captured a different store at construction, or closed over nothing,
would answer an empty roster and refuse Alice while never touching the
substituted store. The read count is what distinguishes "the wiring
works" from "something answered" — and it is the assertion `tasks.md`
2.4's construction-versus-call-time requirement lives or dies on.

**Expected first-run state: FAIL.** Actual: FAIL, on
`assert store.loads >= 1` — `read_people` is the `PostgresRoster` store
today, `_person_for` finds none of its spellings on it, and the
substituted store is never read.

## Assertion provenance

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. Assertions are annotated inline in both files with
`# SPECIFIED:` comments; what follows is the summary and the exceptions.

**Specified** — traced to the delta's own text or to a task/design
decision this change fixes:

- The refusal, non-recording and still-standing pending row for an
  unknown and for a deactivated identity (delta, scenarios 1 and 2).
- That an unanswerable collaborator is **raised**, not returned as a
  decision refusal, and that the error names both the collaborator
  supplied and the shape expected (delta, scenario 3).
- That absent and mis-shaped collaborators raise the **same** error
  (`design.md` — Decision 4).
- That the decider is told their decision was not processed, that the
  decision does not fail without an answer, and that the reply contains
  no clause about their identity (delta, scenarios 4 and 5;
  `tasks.md` 3.1, 3.2).
- That the fault is logged at `exception` level — "reported where
  operators see faults" (delta, scenario 5; `design.md` — Decision 4).
- That the person is resolved and the decision judged on its merits
  through the injected collaborator (delta, scenario 6).
- That the shape check does not move ahead of the settled lookup
  (requirement statement, third paragraph; `tasks.md` 1.3). Stated in the
  requirement rather than in a scenario, and carried by
  `test_the_shape_check_does_not_move_ahead_of_the_settled_lookup`.
  Expected first-run state PASS; actual PASS — a regression guard against
  the tempting hoist.
- That `UnreadableRosterError` is reachable on
  `commerce_ops.launch.application`'s public surface (`tasks.md` 1.6).
  Asserted in one test only; see *Deliberately not pinned* below.

**Derived** — inferred, with no stated requirement behind them:

- `store.loads >= 1` in the scenario-6 test. The delta says the person is
  resolved through the collaborator production supplies; that the
  *substituted store* is read is this author's reading of what makes that
  observable rather than assumed. It is the strongest assertion in the
  file and the one most likely to be argued with, so it is flagged here
  rather than left to look specified.
- `assert answer.answered` in
  `test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators`.
  A non-vacuity guard, not a requirement: without it, an empty reply
  satisfies every "does not say" assertion beside it.
- `assert str(caught.value).strip()` in
  `test_an_absent_collaborator_raises_the_named_wiring_error` — read from
  `tasks.md` 2.2's "preserving its message", which fixes that a message
  survives but not what it says.
- In the scenario-6 test, that exactly one outcome is recorded and the
  row leaves `pending`. The delta says "judged on its merits"; what
  merits produce for an accepted result is a *different* requirement's
  business (*Accepting records the proposed outcome*), already covered by
  `test_automated_result_decisions.py`. Used here only as the observable
  that the decision was judged at all.

**Deliberately untested**, recorded rather than omitted:

- **That `read_people`'s declared type makes a store-shaped injection a
  `mypy` error at the assigning line** (`design.md` — Decision 3,
  `tasks.md` 2.5). This is the durable half of the change and no runtime
  assertion can observe it; a pytest test pretending to would pass for
  the wrong reason. It is verified by `uv run mypy` and by `tasks.md`
  2.5's one-off check that reverting the injection *does* produce
  `[assignment]` at that line. Whoever implements must actually perform
  that one-off check — this pass cannot, because it would require
  writing the implementation first.
- **The mis-shaped collaborator's reply, driven at the adapter.** The
  shape check sits after the settled lookup (`tasks.md` 1.3), so reaching
  it needs the pending-result store to answer with a real pending row,
  which this tier's permissive substitution cannot do and for which no
  artifact fixes a shape. What makes the two faults answer alike is that
  they raise one type (asserted at the use case) and that one catch
  handles it (asserted at the adapter through the absent-collaborator
  route). See Q4.
- **The two Bolt listeners' `ack()`-first ordering** (`tasks.md` 3.3).
  Unchanged by this delta and already covered for this app's listeners by
  `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py`.
- **The verified `product_agent` surface** and **acknowledgement within
  Slack's timeout**, both carried by the requirement's second paragraph
  unchanged. Covered by
  `test_slack_entry_request_verification.py` and the file above, as
  `test_automated_result_decisions.py` already records.

**Deliberately not pinned:** the wiring error's class, in every test that
can avoid pinning it.
`test_an_absent_collaborator_is_refused_the_same_way` compares the two
faults' types to each other rather than to a name, so it survives the
class being spelled differently than `tasks.md` 1.6 says. Only
`test_a_collaborator_that_cannot_answer_is_refused_by_name` and the
adapter's type test name `UnreadableRosterError`, because `tasks.md` 1.6
makes that export a deliverable of this change.

## Obsolete tests

**No existing test was found that asserts behaviour this delta
supersedes.** The list is applicable — the change carries a MODIFIED
delta — but it is empty, and empty for the first reason rather than the
second: the modified requirement is a strict superset of the archived one
(`openspec/specs/launch-step-automation/spec.md`), carrying both prior
scenarios forward verbatim and adding four. Nothing it states was true
before and is false now, so no assertion anywhere can have been written
against superseded behaviour.

The search that establishes this, with its bounds stated so its reach can
be judged:

- Scope: `tests/**/test_*.py` — the dispatched test-path glob, and
  nowhere else.
- Method: (a) the archived requirement read against the delta, clause by
  clause, to establish what changed at all; (b) `grep` across the glob for
  `_person_for`, `person_for_slack_identity`, `read_people`,
  `roster_or_fail`, and for the production refusal wording "the roster
  does not know". Six files matched, two of them written by this pass.
- No earlier `test-manifest.md` was supplied to this dispatch and none
  exists at this change root, so no scenario-to-test map from a previous
  pass was available to draw on.

The four pre-existing matches, and why none is an entry:

| File | Why it is not obsolete |
|---|---|
| `tests/unit/launch/application/test_automated_result_decisions.py` | Its two roster tests assert the unknown and inactive refusals, both carried forward verbatim. Its `_FakeRoster` is *narrowed* by `tasks.md` 4.2 — that is an edit to a double, not to an assertion, and `design.md` — Decision 5 says so explicitly. See Q1. |
| `tests/unit/launch/application/test_authoring_roster_collaborator_shape.py` | Covers the sibling seam in `playbook-authoring`, which `restore-admin-step-writes` closed. Untouched by this delta, which changes no `playbook-authoring` requirement. |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_roster.py` | Same — the admin-page seam, a different capability. |
| `tests/integration/launch/test_playbook_authoring_roster_live.py` | Same — and the source of `design.md` — Decision 6's cited reasoning, not a subject of it. |

If a reader believes an entry belongs here anyway, the thing to check is
whether any test asserts that the *three-spelling probe* accepts more
than one spelling. None was found; `_FakeRoster`'s six spellings are a
property of a double, asserted by nothing.

## Unresolved project questions

Each records the assumption taken and which tests depend on it. None was
resolved silently; this pass runs non-interactively and has no channel to
ask on.

**Q1 — `_FakeRoster`'s narrowing (`tasks.md` 4.2) is left undone.**
`AGENTS.md` records no convention on whether a test-writing pass may edit
an existing test file, and this pass's own bound forbids it outright:
never edit, delete or disable an existing test. *Assumption:* the
narrowing is implementation work, belonging to whoever applies groups
1–3. *Consequence:* until it lands, the two carried-over scenarios are
covered twice — once against the six-spelling double (existing file) and
once against the narrowed one (new file). *Depends on it:* nothing
breaks either way; the new tests do not read `_FakeRoster`. Note for the
implementer: `design.md` — Decision 5 says no existing test should fail
once `_FakeRoster` narrows, and that if one does, it is a finding to
report rather than to fix by re-widening the double.

**Q2 — the adapter's collaborator seam names are fixed by no artifact.**
`AGENTS.md` records the tiers and the test command but nothing about how
a driving module's collaborators are substituted. *Assumption:* the
convention every other file in
`tests/unit/launch/infrastructure/driving/` follows — a module-level
`session` provider substituted with `monkeypatch.setattr` (see
`test_clickup_webhook.py`), plus module-level persistence classes
substituted by name. Both are expressed as probed lists —
`_SESSION_SEAM_NAMES`, `_PERSISTENCE_SUFFIXES` — and were confirmed to
drive the entry point as far as the roster resolution before this pass
was reported, so the faults the two reply tests observe are the real
wiring faults and not unmet collaborators of the tests' own.
*Depends on it:* `test_a_wiring_fault_answers_the_decider_rather_than_falling_silent`
and `test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators`.
If a later change breaks the arrangement, correct those lists — never
the assertions.

**Q3 — the adapter's entry-point and resolver names, and the entry
point's call shape.** `_roster_or_fail` and `_handle_decision` are named
in this change's own artifacts but in no spec. *Assumption:* those names,
probed over alternatives, with the entry point driven by a pool of
plausible Bolt and parsed-decision arguments filtered by its implemented
signature — the pattern
`test_automation_confirmation_delivery.py::_deliver` established for the
same module. Correction points: `_RESOLVER_NAMES`, `_ENTRY_NAMES`,
`_drive_decision`. *Depends on it:* the three adapter tests.

**Q4 — how the mis-shaped collaborator's *reply* would be observed.**
Not answerable from the artifacts: it needs the pending-result
repository's shape. *Assumption:* that asserting one raised type at the
use case and one catch at the adapter is what the requirement's "the same
named wiring error" and `design.md` — Decision 4's "one catch, one reply
and one scenario" together establish. *Depends on it:* nothing asserts
the mis-shaped reply directly; it is recorded above as deliberately
untested.

**Q5 — the wording markers.** `_EXPECTED_SHAPE_NAMES` (how a message
"identifies the shape expected"), `_BLAMES_THE_IDENTITY` (how a refusal
blames the decider), `_SAYS_NOT_PROCESSED` (how a reply says the decision
did not land). No artifact fixes phrasing. *Assumption:* each read from
the artifacts' own language, with one safeguard —
`test_a_mis_wiring_is_never_reported_as_an_unknown_identity` asserts that
a **genuine** unknown-identity refusal matches one of
`_BLAMES_THE_IDENTITY`'s markers before asserting that the mis-wiring
does not, so the negative cannot pass vacuously. `_SAYS_NOT_PROCESSED`
carries no such safeguard, because no reply of that kind exists yet to
check it against; it is the marker list most likely to need correcting
once `tasks.md` 3.1's sentence is written. *Depends on it:* the two
adapter reply tests and the two use-case mis-wiring tests.

**Q6 — the decision use cases' names and call shape.** Carried over from
`test_automated_result_decisions.py`, which probes for them rather than
importing them, and whose probe passes today. *Assumption:* the same
probe and the same keyword set. Correction points: `_decide` in the
application file, `_accept` in the driving file — deliberately identical,
so the two correct together. *Depends on it:* every test in this pass.

## What the implementation must make pass

Nine node ids, grouped by the task that should turn each green. All
runnable individually with `uv run pytest <node id>`.

**After `tasks.md` group 1 (the use case's shape and its named error):**

```
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_collaborator_that_cannot_answer_is_refused_by_name[accepting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_collaborator_that_cannot_answer_is_refused_by_name[rejecting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_an_absent_collaborator_is_refused_the_same_way
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_mis_wiring_is_never_reported_as_an_unknown_identity[accepting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_mis_wiring_is_never_reported_as_an_unknown_identity[rejecting]
```

Task 1.6's export is what
`test_a_collaborator_that_cannot_answer_is_refused_by_name` reaches
`UnreadableRosterError` through; without it that test fails with a
message saying so rather than with an import error.

**After group 2 (the adapter's typed injection point and `main.py`'s
reader):**

```
tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py::test_an_absent_collaborator_raises_the_named_wiring_error
tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py::test_a_roster_person_can_decide_through_the_injected_collaborator
```

The second is the one `tasks.md` 2.4 exists for: a reader capturing
`roster` at construction rather than resolving it inside `list_people()`
leaves `store.loads` at zero and this test red, which is the whole point
of substituting at the store.

**After group 3 (the adapter answers the fault without blaming the
decider):**

```
tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py::test_a_wiring_fault_answers_the_decider_rather_than_falling_silent
tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py::test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators
```

**Must stay green** — five new tests already passing, plus the whole
pre-existing suite:

```
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_an_unknown_identity_cannot_decide[accepting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_an_unknown_identity_cannot_decide[rejecting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_deactivated_person_cannot_decide[accepting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_a_deactivated_person_cannot_decide[rejecting]
tests/unit/launch/application/test_automated_decision_roster_shape.py::test_the_shape_check_does_not_move_ahead_of_the_settled_lookup
```

A regression in any of those five means the narrowing went further than
the delta states: the first four say the two carried-over refusals
survive the collaborator being narrowed to one shape, and the fifth says
the shape check was not hoisted ahead of the settled lookup.

## Verification run alongside this pass

- `uv run pytest` — 9 failed, 1160 passed, 96 skipped (as accounted for
  above).
- `uv run ruff check` and `uv run ruff format --check` on both new files
  — clean.
- `uv run mypy .` — `Success: no issues found in 317 source files`.

`import-linter` was not run: this pass added no module under `src/` and
touched no import the contracts govern. `tasks.md` 5.2 still requires it
once group 2 lands.
