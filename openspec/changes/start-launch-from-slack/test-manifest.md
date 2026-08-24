# Test manifest — `start-launch-from-slack`

Written by the `openspec-test-writer` role, strictly from
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md` (all
six requirements ADDED), `proposal.md`, `design.md`, and `tasks.md` — never
from an implementation, because the adapter this change describes
(`launch/infrastructure/driving/slack_entry.py`) does not exist yet at any
point in this pass. This file is **not** an OpenSpec-schema artifact — it
will not appear among `openspec instructions apply`'s context files and
must be read on purpose before implementing. `AGENTS.md`'s workflow rule
points here via the library's own binding for "derive tests from the
approved specification deltas."

## Files written

Unit tier (`tests/unit/launch/infrastructure/driving/`):

- `conftest.py` — the `slack_asgi_app` drain-wrapper fixture, mirroring
  `tests/unit/omni_agent/infrastructure/driving/conftest.py`'s.
- `test_slack_entry_request_verification.py` — Requirement 5.
- `test_slack_entry_modal_contract.py` — Requirement 1 (modal-shape half
  only).
- `test_slack_entry_field_validation.py` — Requirement 3 (inline-validation
  half only).
- `test_slack_entry_ack_and_failure_visibility.py` — Requirement 4.
- `test_slack_entry_no_clickup_projection.py` — Requirement 6.

Integration tier (`tests/integration/launch/`), real Postgres, skips when
`DATABASE_URL` is unset:

- `test_slack_entry_start.py` — Requirement 1 (persistence half),
  Requirement 2, Requirement 3 (persistence half), plus one DERIVED case
  for Requirement 4's requirement-body text.

No file outside this list, and outside the dispatched test-path glob
(`tests/**/test_*.py`), was written or edited, except this manifest itself.
**No existing test file was edited, deleted, or disabled.** No
implementation was written anywhere.

## Scenario accounting (12 of 12)

### Requirement: A launch is started from Slack in one interaction

| Scenario | Test(s) | Level |
|---|---|---|
| A launch is started with a date | `test_a_launch_is_started_with_a_date` | integration |
| A launch is started without a date | `test_a_launch_is_started_without_a_date` | integration |
| The playbook version is never user input | `test_the_modal_contains_no_playbook_version_field` (modal-shape half) + `test_a_launch_is_started_with_a_date`'s `_read(launch, "version")` assertion (pinned-version half) | unit + integration |

### Requirement: Registration and start are atomic

| Scenario | Test(s) | Level |
|---|---|---|
| A rejected start leaves no product behind | `test_a_rejected_start_leaves_no_product_behind` | integration |

### Requirement: Rejections are surfaced where the user is

| Scenario | Test(s) | Level |
|---|---|---|
| A missing required field keeps the modal open | `test_a_missing_required_field_keeps_the_modal_open[missing-sku]`, `test_a_missing_required_field_keeps_the_modal_open[missing-name]` | unit |
| A duplicate SKU is rejected with nothing persisted | `test_a_duplicate_sku_is_rejected_with_nothing_persisted` | integration |

### Requirement: Acknowledgement is independent of persistence, and a post-acknowledgement failure is visible

| Scenario | Test(s) | Level |
|---|---|---|
| A slow transaction does not miss the acknowledgement window | `test_a_slow_transaction_does_not_miss_the_acknowledgement_window` | unit |
| A post-acknowledgement failure reaches the user | `test_a_post_acknowledgement_failure_reaches_the_user` (visibility half) + `test_a_rejected_start_leaves_no_product_behind` (nothing-is-persisted half — same underlying mechanism as Requirement 2's scenario, cross-referenced rather than re-asserted against a real store a second time) | unit + integration |

### Requirement: Requests are verified before anything is acted on

| Scenario | Test(s) | Level |
|---|---|---|
| An unverifiable request is rejected | `test_an_unverifiable_slash_command_is_rejected`, `test_an_unverifiable_view_submission_is_rejected` | unit |
| No configured secret rejects everything | `test_no_configured_secret_rejects_a_slash_command`, `test_no_configured_secret_rejects_a_view_submission` | unit |
| An absent reply credential rejects rather than strands | `test_slash_command_is_rejected_when_the_bot_token_is_absent`, `test_view_submission_is_rejected_when_the_bot_token_is_absent` | unit |

### Requirement: Entry never projects work

| Scenario | Test(s) | Level |
|---|---|---|
| A started launch touches no external tracker | `test_a_successful_submission_makes_no_clickup_call` | unit |

**Count check:** 12 `#### Scenario:` blocks in the delta spec; 12 accounted
for above, each by at least one named test. None uncovered.

## DERIVED tests (no `#### Scenario:` block of their own)

Recorded here, not silently mixed in with specified coverage:

- `test_slash_command_opens_a_modal` — precondition guard; without it, the
  modal-shape assertions in the same file would be vacuously true of a
  modal that was never opened.
- `test_the_modal_carries_the_required_and_optional_fields` — DERIVED from
  the requirement's own body text (fields the modal must collect), not
  from a scenario.
- `test_a_complete_submission_is_not_rejected_inline` — DERIVED positive
  control for the missing-field tests in the same file.
- `test_a_post_commit_delivery_failure_leaves_the_commit_standing`
  (integration) — DERIVED from the requirement-body sentence "A failure to
  deliver a message after a successful commit leaves the commit standing,"
  which names no scenario of its own.

## Assertion classification (specified / derived / deliberately untested)

- **Specified**: every assertion tied to a scenario's own WHEN/THEN
  language in the tables above — acknowledgement status, what is/is not
  persisted, what is/is not called, message delivery to the submitting
  user, the modal's absent version field, the pinned playbook version, the
  presence/absence of a launch date.
- **Derived**: the four tests listed above in full; plus, within
  scenario-backed tests: the ack-timing wall-clock proxy
  (`SLOW_PERSISTENCE_SECONDS` / `ACK_SHOULD_RETURN_WITHIN_SECONDS` in
  `test_slack_entry_ack_and_failure_visibility.py`, documented in that
  file's own docstring as a proxy, not a proof of Slack's literal 3-second
  window); the "no playbook-version field" search being broader than one
  named field (searches all block/action ids and label text for
  "version"/"playbook"); the marketplace-preselection assertion
  (`initial_option` present) in `test_slack_entry_modal_contract.py`.
- **Deliberately untested**: exact wording of any outcome message (success
  confirmation, duplicate-SKU rejection, missing-date confirmation) —
  asserted only by loose containment (`"already"`, `"no date"`, etc.) or
  non-emptiness, never pinned to an exact string, since no artifact fixes
  one. The slash command's literal name and the modal's `callback_id` are
  placeholders (see Unresolved project questions) rather than assertions,
  so nothing here treats them as specified.

## Obsolete tests

**Not applicable.** Every requirement in this change's delta spec is
`ADDED`; there is no `MODIFIED`, `REMOVED`, or `RENAMED` delta, so there is
no existing behavior this change supersedes and no candidate search was
performed.

## Unresolved project questions (assumptions taken, and what depends on them)

No artifact in this change (`proposal.md`, `design.md`, `tasks.md`, the
delta spec) fixes the following. Each is INVENTED, following the closest
established precedent in this codebase where one exists, and recorded here
so implementation can correct it as a **fixture correction** (not a
requirement change) if the real shape differs — per `ai-toolkit:testing`'s
failure-state 3, this is expected to happen at least once, since the
adapter genuinely does not exist yet.

1. **Route path**: `/product_agent/slack/events`. Assumed by generalizing
   the one existing precedent for this exact shared registry
   (`omni_agent`'s `/omni_agent/slack/events`) by app identity, since
   design.md says this adapter is registered "via the shared `slack_app`
   registry" — the same composition mechanism. Every unit and integration
   test in this file set depends on this.
2. **Bot-token env var name**: `PRODUCT_AGENT_SLACK_BOT_TOKEN`. Assumed by
   the `<IDENTITY>_SLACK_<KIND>` convention `OMNI_AGENT_SLACK_BOT_TOKEN`
   already establishes. (The signing-secret var,
   `PRODUCT_AGENT_SLACK_SIGNING_SECRET`, is not an assumption — it is
   named literally in `proposal.md` and `tasks.md` 1.1.)
3. **Slash command name**: `/start-launch`. `design.md`'s own Open
   Questions section states this is "cosmetic, decided at implementation
   with the team," so no test asserts the literal string carries meaning —
   it is a placeholder for "the registered slash command."
4. **Modal `callback_id`**: `start_launch_modal`.
5. **Field block/action ids**: `sku`, `name`, `asin`, `launch_date`,
   `marketplace` (block id == action id, one field per block). Chosen to
   match the spec's own field vocabulary as closely as possible.
6. **Catalog-registrar injection point's attribute name**: tried, in order,
   `register_catalog_product`, `catalog_registrar`, `register_product` —
   mirroring `test_daily_briefing_job.py`'s `NOTIFIER_ATTRIBUTES`
   multi-candidate pattern for the same kind of uncertainty (`tasks.md` 2.3
   fixes that a module-global injection point exists, "on
   `daily_briefing_job.py`'s pattern," but not its spelling). Tests that
   need this attribute fail loudly (an `assert ... , "... exposes none
   of ..."` message) if none of the three exists, rather than silently
   skipping.
7. **`start_launch`'s import name into the adapter module**: NOT an
   assumption — `tasks.md` 2.2 names `launch.application.start_launch`
   literally as the collaborator the transaction runs, and this codebase's
   own collaborator-patching convention (`daily_briefing_job.py`'s
   `run_daily_briefing`) is to import it by name into the calling module's
   namespace, which is what every `monkeypatch.setattr(module,
   "start_launch", ...)` call here relies on.
8. **`read_launch`'s call shape** (`tests/integration/launch/
   test_slack_entry_start.py` only): confirmed via `inspect.signature`
   against the actual, already-existing use case
   (`commerce_ops.launch.application.use_cases.read_launch`) rather than
   guessed — `(launches, playbooks, *, product_id, as_of, scope)`. This is
   reading a pre-existing collaborator's public signature (introduced by
   an earlier, already-implemented change), not the implementation of the
   change under test; the same reflection approach
   `test_scope_aware_launch_reads.py` already uses for the same function.
9. **Persisted launch record's attribute names** for playbook version and
   launch date: read through the same multi-candidate `_read` helper
   `test_scope_aware_launch_reads.py` established
   (`version`/`playbook_version`/`pinned_version`,
   `launch_date`/`date`), reused rather than re-invented.
10. **No FastAPI/Slack-Bolt-specific skill exists in this session's
    available-skills list.** Per the dispatch contract, this absence is
    recorded here rather than silently proceeding as though a matching
    skill had been consulted: `python` and `ai-toolkit:testing` were
    loaded (see below) and supplied the floor; Slack Bolt/FastAPI
    version-specific idiom was drawn from this repository's own existing
    Slack-adapter tests (`tests/unit/omni_agent/infrastructure/driving/`),
    read as permitted (within the test-path glob), not from an external
    skill.

## Skills loaded

`ai-toolkit:testing` and `python` were loaded via the `Skill` tool partway
through this pass (after most test files were already drafted from the
floor as paraphrased in this role's own dispatch contract, which tracks
`testing`'s baseline/four-states/provenance rules closely) and confirmed
against, rather than before the first file was written as the contract
prescribes. Re-reading them afterward produced no change to what had
already been written — the baseline, failure-state, and
specified/derived/deliberately-untested discipline they describe is what
this manifest already followed — but the ordering itself is recorded
here as a deviation from the prescribed sequence, not smoothed over.

## Baseline

**Full baseline taken**, scoped to the pre-commit tier (`tests/unit` +
`tests/agents`, matching `AGENTS.md`'s own commit-time hook), run twice:

- **Before** this pass's new files (all five new unit files excluded via
  `--ignore`): `584 passed`, 0 failed.
- **After** this pass's new files: `584 passed, 11 failed, 4 errors` — the
  15 new unit tests, every one failing for the single, expected reason
  (`commerce_ops.launch.infrastructure.driving.slack_entry does not exist
  yet`), confirmed by inspecting each failure's message individually. No
  pre-existing test's outcome changed.

Commands run:

```
uv run ruff check tests/unit/launch/infrastructure/driving/ tests/integration/launch/test_slack_entry_start.py
uv run ruff format --check tests/unit/launch/infrastructure/driving/ tests/integration/launch/test_slack_entry_start.py
uv run mypy .
uv run pytest tests/unit tests/agents -q
uv run pytest tests/integration/launch/test_slack_entry_start.py --collect-only -q
uv run pytest tests/integration/launch/test_slack_entry_start.py -q   # DATABASE_URL unset -> 5 skipped
```

`tests/integration/launch/test_slack_entry_start.py` was **written but not
run against a real database** — `DATABASE_URL` is not set in this worktree
(no Postgres available). All 5 tests there collect cleanly and skip with
the standard tier message; none were executed against real data, and none
should be reported as passing. Per this tier's own convention (see
`tests/integration/catalog/test_catalog_products.py`), running them
requires the compose file's `postgres` service and `alembic upgrade head`.

## What the implementation step must make pass

Once `openspec-apply-change` lands `tasks.md` section 2 (the entry
adapter), every test named above must be re-run:

1. `uv run pytest tests/unit/launch/infrastructure/driving/test_slack_entry_request_verification.py tests/unit/launch/infrastructure/driving/test_slack_entry_modal_contract.py tests/unit/launch/infrastructure/driving/test_slack_entry_field_validation.py tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py tests/unit/launch/infrastructure/driving/test_slack_entry_no_clickup_projection.py` — all 15 must pass.
2. With `DATABASE_URL` pointed at a migrated Postgres:
   `uv run pytest tests/integration/launch/test_slack_entry_start.py` — all
   5 must pass.
3. Wherever an assumption in "Unresolved project questions" above turns
   out wrong (a different route, a different injection-point name, a
   different `read_launch` call shape having since changed, etc.),
   correcting the test's fixture/helper to match the real shape is
   expected and in-scope for that step — the postconditions each test
   asserts (drawn from this file's Scenario accounting table) are what
   must survive unweakened, per `ai-toolkit:testing`'s failure-state 3.
