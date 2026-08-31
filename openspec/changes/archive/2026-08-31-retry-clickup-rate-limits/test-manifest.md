# Test manifest — `retry-clickup-rate-limits`

Not an OpenSpec-schema artifact — `openspec instructions apply` will not surface
this file among its context files. Read it on purpose before implementing.
Written by `ai-toolkit:openspec-test-writer`, strictly before implementation,
against the change's approved delta spec only — never against
`src/commerce_ops/shared/infrastructure/driven/clickup_client.py`'s current
source.

New file added, additive only: `tests/unit/shared/infrastructure/driven/test_clickup_client_retry.py`.
No existing test file was edited, deleted, or disabled.

## Baseline

Full baseline (`tests/unit` + `tests/agents`, matching this project's own
pre-commit tier and the precedent every sibling test file in this module
records): `uv run pytest tests/unit tests/agents -q` — **1727 passed, 0
failed**, taken before the new file was added.

After adding the new file: `uv run pytest tests/unit tests/agents -q` —
**1735 passed, 22 failed**. The 8 additional passes and the 22 failures are
both in `test_clickup_client_retry.py`, and both are the expected first-run
state, per `ai-toolkit:testing`'s failure-state taxonomy:

- **22 failed** — every test asserting behavior that does not exist yet
  (succeeds-on-retry, budget-exhausted, and the three Retry-After/backoff
  scenarios), each failing on `httpx.HTTPStatusError: 429 Too Many Requests`
  propagating on the first attempt, exactly as the pre-change client does
  today. This is state 1 (wrong value against existing code, not an absent
  target): the eight operations and `get_client()` already exist from
  earlier changes, so what fails is the retry behavior, not a missing
  module.
- **8 passed** — `test_a_non_429_failure_is_not_retried`, one per operation.
  This is *not* an absent-target situation either: "a non-429 failure is not
  retried" is what the client already does today (it raises immediately on
  any non-success status), so this test passing on first run establishes
  that the behavior already holds, not an alarm — the target already exists
  for this particular assertion, unlike the other 22.

`tests/integration` was not run: this change touches no I/O this project's
integration tier covers (Postgres), and every sibling test file for this
module records baselines against `tests/unit`/`tests/agents` only.

## Scenario accounting

15 `#### Scenario:` blocks in the delta; all 15 accounted for below.

### MODIFIED — "A failed ClickUp request is surfaced to the caller" (9 scenarios, as revised: "... other than 429")

| # | Scenario | New test | Pre-existing test (still valid, not obsolete) |
|---|---|---|---|
| 1 | ClickUp rejects a create request | `test_clickup_client_retry.py::test_a_non_429_failure_is_not_retried[create_task]` | `test_clickup_client.py::test_create_task_rejected_by_clickup_raises` |
| 2 | ClickUp rejects an update request | `...test_a_non_429_failure_is_not_retried[update_task]` | `test_clickup_client.py::test_update_task_rejected_by_clickup_raises` |
| 3 | ClickUp rejects a create-list request | `...test_a_non_429_failure_is_not_retried[create_list]` | `test_clickup_client_list_and_read.py::test_a_rejected_create_list_request_raises` |
| 4 | ClickUp rejects a read of a list's tasks | `...test_a_non_429_failure_is_not_retried[list_tasks]` | `test_clickup_client_list_and_read.py::test_a_rejected_read_of_a_lists_tasks_raises` |
| 5 | ClickUp rejects a read of a list's own state | `...test_a_non_429_failure_is_not_retried[read_list_state]` | `test_clickup_client_list_state.py::test_a_rejected_read_of_a_lists_own_state_raises[not-found\|unauthorized\|server-error]` |
| 6 | ClickUp is unreachable | **none written** — see reason below | `test_clickup_client.py::test_create_task_when_clickup_is_unreachable_raises` / `test_update_task_when_clickup_is_unreachable_raises`; `test_clickup_client_list_and_read.py::test_create_list_when_clickup_is_unreachable_raises` / `test_list_tasks_when_clickup_is_unreachable_raises`; `test_clickup_client_list_state.py::test_reading_a_lists_state_when_clickup_is_unreachable_raises[connect\|timeout]`; `test_clickup_client_tags.py::test_add_task_tag_when_clickup_is_unreachable_raises`; `test_clickup_client_custom_fields.py::test_the_new_operations_raise_when_clickup_is_unreachable` |
| 7 | ClickUp rejects a tag write | `...test_a_non_429_failure_is_not_retried[add_task_tag]` | `test_clickup_client_tags.py::test_a_rejected_tag_write_raises` |
| 8 | ClickUp rejects a read of a folder's Custom Fields | `...test_a_non_429_failure_is_not_retried[folder_fields]` | `test_clickup_client_custom_fields.py::test_a_rejected_read_of_a_folders_custom_fields_raises` |
| 9 | ClickUp rejects a Custom Field write | `...test_a_non_429_failure_is_not_retried[set_task_field]` | `test_clickup_client_custom_fields.py::test_a_rejected_custom_field_write_raises` |

**Scenario 6 reason for no new test:** its WHEN/THEN text is byte-for-byte
identical between the delta and `openspec/specs/clickup-task-client/spec.md`
(confirmed by direct comparison) — a connection failure carries no status
code at all, so this change's 429-specific carve-out cannot touch it, and it
is not "revised." Per this pass's own contract, a MODIFIED requirement's
scenario earns a new test when the scenario states behavior *the change
introduces*; this one states behavior the change leaves untouched, and its
pre-existing coverage (listed above) is not superseded, so no new test is
owed for it distinct from scenarios 1–5/7–9, which the delta genuinely
narrows.

**Scenarios 1–5, 7–9 note:** one new parametrized test
(`test_a_non_429_failure_is_not_retried`) serves double duty — it is both
new, delta-derived coverage for the ADDED requirement's own "A non-429
failure is not retried" scenario (#15) and the coverage that makes these
eight MODIFIED scenarios hold *as revised*, since the revised wording
("non-success status other than 429") is exactly what it asserts, per
operation. This is recorded so the reasoning is visible rather than the test
being silently double-booked.

### ADDED — "A rate-limited request is retried before it is surfaced" (6 scenarios)

| # | Scenario | Test(s) |
|---|---|---|
| 10 | A rate-limited request succeeds on retry | `test_a_rate_limited_request_succeeds_on_retry[create_task\|update_task\|create_list\|list_tasks\|read_list_state\|add_task_tag\|folder_fields\|set_task_field]` (8 parametrizations, one per operation) |
| 11 | A `Retry-After` header is honored | `test_a_retry_after_header_is_honored[create_task\|list_tasks]` (the "at least that long" half) and `test_a_retry_after_header_larger_than_the_cap_is_capped[create_task\|list_tasks]` (the "no longer than the fixed maximum wait" half) |
| 12 | No `Retry-After` header falls back to the client's own backoff | `test_no_retry_after_header_falls_back_to_the_clients_own_backoff` |
| 13 | An unparseable `Retry-After` header falls back to the client's own backoff | `test_an_unparseable_retry_after_header_falls_back_identically_to_no_header` |
| 14 | A request exhausts its retry budget and still fails | `test_a_request_exhausts_its_retry_budget_and_still_fails[create_task\|update_task\|create_list\|list_tasks\|read_list_state\|add_task_tag\|folder_fields\|set_task_field]` (8 parametrizations) |
| 15 | A non-429 failure is not retried | `test_a_non_429_failure_is_not_retried[create_task\|update_task\|create_list\|list_tasks\|read_list_state\|add_task_tag\|folder_fields\|set_task_field]` (8 parametrizations; same test as scenarios 1–5/7–9 above) |

**Count check:** 9 MODIFIED + 6 ADDED = 15 scenarios; all 15 rows above. ✓

**Scoping note on scenarios 11–13 (not parametrized across all 8
operations):** design.md describes the retry/backoff wait as one internal
helper every operation routes through, not per-operation behavior — unlike
the retry-*outcome* scenarios (10, 14, 15), which the ADDED requirement's own
text makes an explicit per-operation obligation ("Every operation this
capability offers is covered identically ... a caller cannot tell them
apart"), no equivalent sentence is made about the wait's *timing*
specifically. Scenarios 11–13 are tested on two representative operations
(`create_task`, a write, and `list_tasks`, a read) rather than all eight.
Recorded here as a deliberate proportionality choice, not a gap — an
implementation that keyed the wait to the operation rather than the shared
helper design.md describes would only be caught by widening this
parametrization, which is a straightforward follow-up if that turns out to
matter.

## Assertion classification

- **Specified:** no error raised across an intervening 429 (scenario 10);
  captured-request-count == 1 and "does not retry" for a non-429 failure
  (15); the Retry-After wait is at least the header's value (11); the wait
  is no longer than the fixed maximum, as a *rule* (11); the retry budget is
  bounded — a persistent 429 eventually fails (14); a positive wait occurs
  with no header present (12); the unparseable-header wait equals the
  no-header wait (13); no error is raised for the unparseable header itself
  (13).
- **Derived** (from `design.md`'s Decisions, not the spec delta's own text):
  the exact retry budget of 4 attempts (14); the exact 10-second cap on the
  Retry-After wait (11); that a retried request making exactly 2 requests
  (1 failed + 1 succeeding) is the observable proxy for "succeeded on
  retry" (10); that no wait is issued when a non-429 failure is correctly
  not retried (15, an implication of "does not retry" rather than its literal
  text); that the retry wait is reached via `asyncio.sleep` accessed as a
  module attribute, which `capture_sleep` patches (all timing tests) — see
  Unresolved project questions.
- **Deliberately untested**, recorded in the new file's own closing comment
  block: the exact multi-step backoff sequence (1s, 2s, 4s) design.md names
  for consecutive no-header retries — only the fallback *rule* is asserted,
  not that specific sequence; and what `add_task_tag`/`set_task_field`
  return on a retried success — untested for the same reason every sibling
  file already leaves it untested on the non-retried path (no scenario
  commits to a return shape for either).

## Obsolete tests

**Not applicable in the sense of "tests to delete or rewrite" — none
found, and the search establishes that none exists, not merely that this
search missed one.**

Searched within the dispatched test-path glob (`tests/**/test_*.py`) only:
`grep -rn "429" tests/` returned **no hits anywhere in the existing suite**,
and — before writing any new test — the five existing files covering this
module (`test_clickup_client.py`, `test_clickup_client_list_and_read.py`,
`test_clickup_client_list_state.py`, `test_clickup_client_tags.py`,
`test_clickup_client_custom_fields.py`) were read in full. Every one of
their non-success-status failure tests scripts a status other than 429
(400, 401, 404, 422, 500) — none scripts a bare 429 as the rejection this
requirement's earlier wording covered. Because today's client treats every
non-success status identically (immediate `raise_for_status()`, no
distinction for 429), and no existing test happens to have picked 429 as
its example status, **no existing test's assertions are contradicted or
superseded by this change's carve-out** — every one of them continues to
hold exactly as written under the requirement as revised. This is recorded
as "no such test exists," not "none was found by this search": the search
was exhaustive over the relevant files (a full read, not a keyword grep
alone) and over the whole test-path glob (the grep).

## Unresolved project questions

1. **The retry wait's reach for monkeypatching.** `capture_sleep` (in the
   new file) monkeypatches `asyncio.sleep` as a module attribute, assuming
   the implementation calls it as `asyncio.sleep(...)` (per `design.md`'s
   Decisions: "Implemented with `asyncio.sleep` and a small loop"). If the
   real implementation imports it differently (e.g.
   `from asyncio import sleep as _sleep`), the patch target needs
   correcting — a fixture correction, not a change to what any test
   asserts. All timing-dependent tests (scenarios 11, 12, 13, and every
   `capture_sleep`-consuming assertion in 10/14/15) depend on this.
2. **`read_list_state`'s exact exported name.** No artifact before this
   change pinned one spelling; this change's own `tasks.md` 2.5 calls it
   `read_list_state`, which the new file's `_list_state_operation()` tries
   first among the same candidate spellings `test_clickup_client_list_state.py`
   already lists. If the real export differs, correcting the candidate list
   is a fixture correction. Every `read_list_state`-parametrized test case
   in scenarios 10, 14, and 15 depends on this.
3. No other unresolved project question arose. `AGENTS.md`/`CLAUDE.md` name
   `uv run pytest` as the test command and `tests/unit`/`tests/agents`/
   `tests/integration` as the tiers; this file follows the existing
   convention every sibling test file in this module already established
   (anyio backend pinned to asyncio, `get_client()` substitution seam,
   `pytest.raises(Exception)` scoped narrowly) without needing a new
   decision.

## What the implementation step must make pass

Every test in `tests/unit/shared/infrastructure/driven/test_clickup_client_retry.py`
that currently fails (22 of its 30 test cases, enumerated under Scenario
accounting above) must pass once the bounded 429-retry-with-backoff lands,
without any of the 8 currently-passing cases regressing and without
modifying any pre-existing test in this module.
