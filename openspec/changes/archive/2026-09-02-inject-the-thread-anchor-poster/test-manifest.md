# Test manifest — `inject-the-thread-anchor-poster`

Derived from `specs/launch-instance/spec.md` in this change directory — one
`MODIFIED` delta on the requirement *A launch record establishes and persists
its Slack thread once*. Derived from the delta's scenarios only. No
implementation source for the behaviour under test was read: the pre-change
`thread_establishment.py` composes the anchor from caller-supplied strings and
degrades to empty ones, which is the behaviour this delta reverses, so reading
it would have reproduced the shape the change exists to remove. What was
superseded was established by comparing the delta against
`openspec/specs/launch-instance/spec.md`:501-528, not against code.

This file is **not** an artifact the OpenSpec schema knows about, so it does
not appear among `openspec instructions apply`'s context files and has to be
opened on purpose.

---

## Baseline

Taken before any test was written, on this worktree, with no database
configured (`.env.test` absent — the integration tier skips and says so):

| Run | Result |
| --- | --- |
| `uv run pytest` (full) | **2064 passed, 135 skipped, 0 failed** |
| `uv run pytest tests/unit/launch` (scoped) | **1294 passed, 0 skipped, 0 failed** |

Both were green, so every failure reported below is attributable to the new
tests and to nothing pre-existing.

Test command: `uv run pytest`. Tests may be selected individually by the
`file::test_name` identifiers used throughout this document.

---

## Scenario coverage — all 10 accounted for

The delta states ten `#### Scenario:` blocks. Ten are accounted for; none is
uncovered.

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | The submitter is recorded at launch start | *existing, unchanged by this delta* — `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_submitter_is_persisted_on_launch` |
| 2 | The thread reference starts absent | *existing, unchanged by this delta* — `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_thread_reference_starts_absent` |
| 3 | The first per-product Slack message establishes the thread reference | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_the_first_message_establishes_the_thread_reference` |
| 4 | The anchor names the product the system resolved, not what the caller held | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_the_anchor_names_the_product_the_system_resolved`<br>`tests/unit/launch/application/test_thread_anchor_resolution.py::test_the_operation_accepts_no_product_facts_from_its_caller`<br>`tests/unit/launch/infrastructure/driven/test_launch_thread_delivery_supplies_no_product_facts.py::test_the_delivery_seam_takes_no_product_facts`<br>`tests/unit/launch/infrastructure/driven/test_launch_thread_delivery_supplies_no_product_facts.py::test_the_delivery_seam_still_names_the_launch_and_the_step` |
| 5 | A product that cannot be read refuses establishment | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_product_read_that_fails_refuses_establishment`<br>`tests/unit/launch/application/test_thread_anchor_resolution.py::test_an_unconfigured_product_reader_refuses_establishment` |
| 6 | A product that resolves to nothing refuses establishment | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_product_that_resolves_to_nothing_refuses_establishment` |
| 7 | A refused establishment leaves the next delivery free to establish | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_refused_establishment_leaves_the_next_delivery_free` |
| 8 | A concurrent race to establish the thread produces exactly one anchor | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_concurrent_race_produces_exactly_one_anchor` |
| 9 | Establishing an already-set thread reference changes nothing | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_an_already_set_thread_reference_is_reused` |
| 10 | A launch with a thread never reads its product | `tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_launch_with_a_thread_never_reads_its_product`<br>`tests/unit/launch/application/test_thread_anchor_resolution.py::test_a_launch_with_a_thread_is_unaffected_by_an_absent_reader` |

**Notes on the mapping.**

- Scenarios 1 and 2 are domain-entity facts about `Launch`. The delta restates
  them verbatim and changes nothing about them, so they are accounted for by
  the existing tests that already cover them rather than duplicated. Both
  pass today and must keep passing.
- Scenario 5's clause reads *"A product that is unreadable, absent, or whose
  reader is not configured are one case and SHALL be treated alike"*. Two of
  those three land here (a read that raises, and no reader configured); the
  third — the read answering nothing — is scenario 6's own wording and is
  asserted there. The split is between the tests, not between the cases: all
  three assert the same three outcomes.
- Scenario 10 has two tests because the two ways a product can fail to be
  resolvable reach the early return by different routes. An implementation
  that validated `read_product is not None` *before* the early return would
  pass the first and fail the second.

---

## Files written

Two, both inside the dispatched test-path glob `tests/**/test_*.py`:

- `tests/unit/launch/application/test_thread_anchor_resolution.py` — 13 tests.
- `tests/unit/launch/infrastructure/driven/test_launch_thread_delivery_supplies_no_product_facts.py`
  — 2 tests.

Plus this manifest, at the one path outside the glob the pass permits.

No existing test file was edited, deleted, or disabled.

---

## First-run state

Run immediately after writing, against the un-implemented tree:

**12 failed, 2 passed.**

| Test | State | What it establishes |
| --- | --- | --- |
| `test_thread_anchor_resolution.py::test_the_operation_accepts_no_product_facts_from_its_caller` | 1 — code produced a wrong value | The assertion executed. `ensure_launch_thread` today takes `product_name`, `product_sku`, `product_marketplace` and `db_session`. |
| `test_thread_anchor_resolution.py::test_the_first_message_establishes_the_thread_reference` | 2 — target absent | `_call_shape` fails its bind: no `post_anchor`/`read_product` port exists. Assertions did not execute. |
| `…::test_the_anchor_names_the_product_the_system_resolved` | 2 — target absent | as above |
| `…::test_a_product_read_that_fails_refuses_establishment` | 2 — target absent | as above |
| `…::test_an_unconfigured_product_reader_refuses_establishment` | 2 — target absent | as above |
| `…::test_a_product_that_resolves_to_nothing_refuses_establishment` | 2 — target absent | as above |
| `…::test_a_refused_establishment_leaves_the_next_delivery_free` | 2 — target absent | as above |
| `…::test_a_concurrent_race_produces_exactly_one_anchor` | 2 — target absent | as above |
| `…::test_an_already_set_thread_reference_is_reused` | 2 — target absent | as above |
| `…::test_a_launch_with_a_thread_never_reads_its_product` | 2 — target absent | as above |
| `…::test_a_launch_with_a_thread_is_unaffected_by_an_absent_reader` | 2 — target absent | as above |
| `test_launch_thread_delivery_supplies_no_product_facts.py::test_the_delivery_seam_takes_no_product_facts` | 1 — code produced a wrong value | The seam exists and today accepts all three product facts. |

The two that **passed** on their first run are not failure state 4 (the alarm),
and neither is recorded as coverage of new behaviour:

- `test_thread_anchor_resolution.py::test_the_fixture_product_is_the_real_aggregate`
  — a guard on this file's own fixture, asserting it hands the port a real
  `catalog.domain.product.Product` rather than a double. Passing now and after
  is its correct behaviour.
- `test_launch_thread_delivery_supplies_no_product_facts.py::test_the_delivery_seam_still_names_the_launch_and_the_step`
  — a regression guard on the half of the seam the delta does **not** change.
  It is paired with the failing test beside it so that making that one pass by
  gutting the seam fails this one.

Nine of the eleven state-2 failures are the same absent target: the four ports
do not exist yet. Per `ai-toolkit:testing`, that establishes absence and
nothing more — none of their assertions has yet been exercised, and their
first *real* result comes on the run after the signature lands.

`ruff check`, `ruff format --check` and `uv run mypy .` are clean across the
whole tree with these two files present (463 source files, no issues). The
operation under test is deliberately held as `Any`
(`_ensure_launch_thread`) so that the shape check is made at runtime by the
test and reported by the test, rather than by `mypy` — which would report
"not implemented yet" and "implemented wrongly" identically.

---

## Assertion classification

### Specified — traces to the delta

- An anchor message is posted on the establishing delivery, and its reference
  is persisted on the launch record.
- The anchor names the product's name, SKU and marketplace **as answered by
  the product-resolution port**, on a call that supplies no product facts.
- The product is resolved exactly once per launch, at establishment time.
- A read that raises, a reader that is not configured, and a read answering
  nothing each: post no anchor, persist no thread reference, save nothing, and
  fail the delivery.
- A launch whose establishment was refused establishes normally on a later
  delivery whose read succeeds, with a complete anchor.
- Two concurrent establishing calls post exactly one anchor and settle on one
  shared reference.
- A launch already carrying a reference reuses it, posts nothing, saves
  nothing, and resolves no product — including when its product cannot be
  resolved at all.
- `establish_thread_and_resolve_mention` accepts no product facts from its
  caller (delta clause 2: *"SHALL NOT be composed from product facts supplied
  by whichever delivery path happens to be establishing the thread"*).

### Derived — inferred, no delta clause covers it

Every one of these obliges the implementation to satisfy something the
specification does not state. Each names its correction point.

| Derived assertion | Basis | Correction point |
| --- | --- | --- |
| The four ports are named `hold_lock`, `channel`, `post_anchor`, `read_product`, and the operation is callable as `(launch_store, product_id, *, <ports>)` | `tasks.md` 2.2/2.3/3.1 — the implementation's plan, not the spec | `_LOCK_PARAM_NAMES`, `_CHANNEL_PARAM_NAMES`, `_POSTER_PARAM_NAMES`, `_READER_PARAM_NAMES`, `_call_shape` |
| The poster's contract is `(channel, text) -> ts` | `tasks.md` 2.2 | `_RecordingPoster.__call__` (tolerant of positional or keyword passing) |
| The product reader is nullary | `tasks.md` 3.1; the adapter binds the session | `_RecordingReader.__call__` (tolerant of extra arguments) |
| Refusal is signalled by **raising**, and the exception is a `RuntimeError` | the delta says the delivery "fails and is reported"; `tasks.md` 3.4 chooses the type | `_REFUSAL` |
| The refusal's message names the product identifier | `tasks.md` 3.4 | the one assertion in `test_a_product_read_that_fails_refuses_establishment` |
| `ensure_launch_thread` no longer takes `db_session` | `tasks.md` 2.3 / `design.md`; not a delta clause | `test_the_operation_accepts_no_product_facts_from_its_caller`, second assertion — labelled inline as derived |
| The poster is handed the channel the `channel` port resolves | `design.md`'s two-ports decision; the delta does not mention the channel | the `channel == CHANNEL_ID` assertion in `test_the_anchor_names_the_product_the_system_resolved` |
| The seam is spelled `establish_thread_and_resolve_mention`, and the forbidden parameters `product_name` / `product_sku` / `product_marketplace` | `tasks.md` 4.1 and the four call sites as they stand | `_SEAM_NAMES`, `_FORBIDDEN`, `_PERMITTED` |
| The resolved product exposes `name`, `sku.value`, `marketplace_id.value` | taken from the real `catalog.domain.product.Product`, which is what the roots' readers answer — not invented, but not spec-stated either | `PRODUCT` |

### Deliberately untested — identified and left uncovered, with the reason

- **The refusal rolls back the surrounding `transaction()`, leaving nothing
  half-established in Postgres** (`tasks.md` 3.6). Not stated by the delta,
  which speaks of what is persisted on the launch record — asserted at the
  store instead. A real rollback needs a real database and belongs to
  `tasks.md` 8.5 / 8.7's integration verification.
- **Establishment holds exactly one pooled connection** (`tasks.md` 8.6).
  A resource-consumption property of the design's session-bound reader, not a
  behaviour any delta scenario states. Explicitly the implementer's
  verification obligation and needs a live engine to observe.
- **The anchor's wording, and that it names the launch date.** The delta says
  outright that *"What the anchor names is unchanged and is stated by
  `launch-entry`"* and that its clause "governs only where those values come
  from". Asserting the wording here would pin something out of scope;
  `launch-entry`'s own scenarios cover it.
- **That the four driving adapters keep their own catalog reads for their
  message bodies** (`tasks.md` 5.2–5.4). No delta scenario states it; the
  existing adapter tests already cover those bodies and must keep passing.
- **End-to-end delivery through Slack.** Out of level: every stated outcome is
  observable at the application call.

---

## Obsolete tests

**Bounded search.** Searched `tests/**/test_*.py` — the dispatched glob — and
nowhere else. No earlier `test-manifest.md` was supplied, so no
scenario-to-test index was available; the search was by grep over the glob for
`ensure_launch_thread`, `establish_thread_and_resolve_mention`,
`thread_establishment`, `slack_thread_id`, `_get_slack_client`,
`product_name` / `product_sku` / `product_marketplace`, and anchor-body
strings.

**Every entry below is a candidate for human confirmation, not a conclusion.**
None was edited, deleted, or disabled by this pass.

### 1. `tests/unit/launch/application/test_thread_establishment_race.py::test_first_message_establishes_thread`

- **Superseded by:** `MODIFIED` `launch-instance`, clause 2 — *"The anchor
  message SHALL be composed from the launch's product as the system resolves
  it at establishment time … and SHALL NOT be composed from product facts
  supplied by whichever delivery path happens to be establishing the thread"*
  — and its scenario *The anchor names the product the system resolved, not
  what the caller held*.
- **Evidence:** the test's `_call` helper passes `PRODUCT_NAME`,
  `PRODUCT_SKU`, `PRODUCT_MARKETPLACE` as positional arguments, and the test
  then asserts `PRODUCT_NAME in anchor["text"]`, `PRODUCT_SKU in
  anchor["text"]`, `PRODUCT_MARKETPLACE in anchor["text"]`. Those three
  assertions are satisfied precisely by composing the anchor from what the
  caller held, which the delta now forbids.
- **Candidate for human confirmation.** Its *other* assertions — one anchor,
  the returned reference persisted — are not superseded and are re-asserted
  under the new call shape in
  `test_thread_anchor_resolution.py::test_the_first_message_establishes_the_thread_reference`.

### 2. `tests/unit/launch/application/test_thread_establishment_race.py::test_concurrent_race_produces_one_anchor`

- **Superseded by:** the same clause, **incidentally only**.
- **Evidence:** the scenario it asserts (*A concurrent race … produces exactly
  one anchor*) is carried into the delta **unchanged**, and its assertions are
  still correct. What is superseded is the shared `_call` helper it reaches the
  operation through, which passes a session and three product strings the
  operation no longer takes. It will fail on a `TypeError` at the call, not on
  a wrong assertion.
- **Candidate for human confirmation.** This is a case where the *assertion*
  survives and only the *call* is superseded. The delta's requirement is
  re-asserted under the new shape in
  `test_thread_anchor_resolution.py::test_a_concurrent_race_produces_exactly_one_anchor`,
  so nothing is lost if it is retired — but retiring it is a bigger step than
  the evidence alone justifies, and `tasks.md` 7.6 explicitly says a test
  asserting the race produces one anchor "was not [pinning the defect] and
  must keep passing untouched". Reconciling those two readings is a human call.

### 3. `tests/unit/launch/application/test_thread_establishment_race.py::test_serial_establishment_is_idempotent`

- **Superseded by:** the same clause, **incidentally only** — identical
  situation to entry 2.
- **Evidence:** asserts *Establishing an already-set thread reference changes
  nothing*, which the delta carries unchanged, but reaches it through the same
  superseded `_call` helper.
- **Candidate for human confirmation.** Re-asserted under the new shape in
  `test_thread_anchor_resolution.py::test_an_already_set_thread_reference_is_reused`.

### 4. `tests/unit/launch/application/test_thread_establishment_race.py` — the `slack_client` fixture and `_CapturingSlackClient`

- **Superseded by:** *not the delta.* By `design.md`'s decision and
  `tasks.md` 2.1/7.2 — the Slack client leaves `launch/application/`, so
  `monkeypatch.setattr(thread_establishment, "_get_slack_client", …)` has
  nothing left to patch.
- **Evidence:** the fixture's own docstring names `_get_slack_client()` as
  "the only reachable seam"; `tasks.md` 2.1 deletes that function, and
  `tasks.md` 7.8 strikes the corresponding row from `docs/deferred-work.md`'s
  *Three seams a unit test has to work around, measured* table.
- **Recorded here explicitly because its basis is a design decision, not a
  spec clause** — a reader should not mistake it for a scenario-driven
  finding. **Candidate for human confirmation.**

### Searched and found nothing — stated so it is not read as an empty list

- **The three `_install_thread_establishment` doubles** in
  `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py`,
  `…/test_automation_confirmation_delivery.py` and
  `…/test_automation_confirmation_to_thread_reply.py` substitute the seam with
  `async def _fake(*args, **kwargs)`, so dropping three of its arguments does
  not reach them. **Not obsolete** — they should keep passing untouched, and a
  failure in any of them after the change is a signal, not an expected edit.
- **No test anywhere in the glob asserts on the anchor's body text** other than
  entry 1. Grep for `anchor`, `SKU:`, `Marketplace:` and `Launch Date` over
  `tests/` returns nothing else bearing on it. This is *"no such test exists"*,
  established by that search, not *"none was found"*.
- **`PRODUCT_AGENT_SLACK_BOT_TOKEN` fixtures** (`tasks.md` 7.7). Twenty-odd
  files set it, every one of them for a reason this change does not touch —
  settings drift checks, preflight, `launches_channel()` reading the
  environment, and the Slack entry adapter's own notifier. None is set *solely*
  to satisfy `thread_establishment._get_slack_client()`, and no cache-reset
  list naming `thread_establishment` exists in the glob. Nothing to retire;
  recorded because `tasks.md` 7.7 asks for the check and the answer is "none",
  which is worth having in writing.

---

## Unresolved project questions

The conventions read: `AGENTS.md`, `CLAUDE.md` (which imports it) and the
`README.md` Architecture section named in the dispatch. They fix the runner
(`uv run pytest`), the three tiers, the path glob, and the tooling. They do not
answer the following, and this pass has no channel to ask on, so each is
recorded with the assumption taken and the tests that depend on it.

1. **Do the port names in `tasks.md` bind the tests?** `AGENTS.md` requires
   tests to be derived from the approved delta specs, "not from implementation
   code" — and `tasks.md` is neither. The delta fixes no signature at all, so
   *some* shape had to be assumed to make a call.
   **Assumption taken:** `tasks.md` 2.2/2.3/3.1's names and shapes, entered
   through a runtime probe (`_call_shape`, `_parameter`) that fails naming the
   real signature rather than silently binding to a parameter the operation
   ignores.
   **Tests depending on it:** all eleven behavioural tests in
   `test_thread_anchor_resolution.py`. If the implementation lands different
   names, correcting the four `*_PARAM_NAMES` tuples is the intended repair —
   and it is a fixture correction, not a weakening: no assertion changes.

2. **Which exception type signals a refusal?** The delta says only that the
   delivery "fails and is reported". `AGENTS.md` records no project convention
   on domain-vs-builtin exception types.
   **Assumption taken:** `RuntimeError`, per `tasks.md` 3.4 and the
   neighbouring `RuntimeError(f"no launch found for product …")` already in
   the module.
   **Tests depending on it:** the four refusal tests, through `_REFUSAL`.

3. **What "and is reported" requires beyond the raise.** The delta hands the
   handling to each caller's own existing rule and specifies no log line, so
   nothing here asserts one. Contrast
   `test_mention_resolution_namespace.py`, which had to invent
   "reported = a `WARNING`-or-above log record" for the roster reader and
   recorded that invention. This pass declined to invent the same thing again
   for the product reader, because here the raise *is* the report to the
   caller.
   **Assumption taken:** raising, and nothing about logging, is what the
   scenarios require. If the project wants a log assertion, it is an addition,
   not a correction.

4. **Whether the delta's scenarios also want integration-tier coverage.**
   `AGENTS.md` puts real-I/O tests in `tests/integration/<module>/` but says
   nothing about which specification scenarios must reach that tier.
   **Assumption taken:** none written here — every stated outcome is
   observable at the application call, which is `ai-toolkit:testing`'s level
   rule. `tasks.md` 8.5–8.7's database checks remain the implementer's
   verification obligations and are **not** discharged by this manifest.

---

## What the implementation must make pass

Run, after implementing:

```
uv run pytest tests/unit/launch/application/test_thread_anchor_resolution.py \
              tests/unit/launch/infrastructure/driven/test_launch_thread_delivery_supplies_no_product_facts.py
```

All 15 must pass, and the rest of the suite must stay at its baseline of
2064 passed / 135 skipped — plus whatever `tasks.md` 7.6's corrections to
`test_thread_establishment_race.py` change, which are the implementer's
judgment and not this pass's.

Per task, the tests that must go from failing to passing:

| `tasks.md` task | Tests it must satisfy |
| --- | --- |
| 2.2 (`post_anchor` port), 2.3 (`db_session` removed, nullary `hold_lock`) | `test_thread_anchor_resolution.py::test_the_operation_accepts_no_product_facts_from_its_caller`, and the bind in every other test in that file |
| 3.1 (read after lock, after early return) | `…::test_a_launch_with_a_thread_never_reads_its_product`, `…::test_a_launch_with_a_thread_is_unaffected_by_an_absent_reader`, `…::test_a_concurrent_race_produces_exactly_one_anchor` (its `reads == 1` assertion) |
| 3.3 (compose from the read) | `…::test_the_anchor_names_the_product_the_system_resolved`, `…::test_the_first_message_establishes_the_thread_reference` |
| 3.4 (refuse on absent / raising / `None`) | `…::test_a_product_read_that_fails_refuses_establishment`, `…::test_an_unconfigured_product_reader_refuses_establishment`, `…::test_a_product_that_resolves_to_nothing_refuses_establishment` |
| 3.6 (nothing persisted on refusal — its in-memory half) | the three refusal tests' `slack_thread_id is None` / `not store.saves` assertions, and `…::test_a_refused_establishment_leaves_the_next_delivery_free` |
| 4.1 (seam drops the three product facts) | `test_launch_thread_delivery_supplies_no_product_facts.py::test_the_delivery_seam_takes_no_product_facts`, with `…::test_the_delivery_seam_still_names_the_launch_and_the_step` as the guard against over-removal |

Tasks 5.x, 6.x and 8.x carry no test in this manifest. 5.x is covered
indirectly — the four adapters' existing tests must keep passing — and 6.3's
composition-root arity check and 8.5–8.7's database checks are verification
obligations the implementer discharges directly, as those tasks state.
