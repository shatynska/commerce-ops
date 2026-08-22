# test-manifest.md — `migrate-slack-to-bolt`

Written before implementation, from the change's delta specs at
`openspec/changes/migrate-slack-to-bolt/specs/slack-trigger/spec.md` and the
existing capability spec at `openspec/specs/slack-trigger/spec.md`. No
implementation source was read.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among `openspec instructions apply`'s context files, and must be opened
on purpose before implementing.

This pass **adds tests and never subtracts**. No existing test file was
edited, deleted or disabled, and no implementation code was written.

---

## Baseline

Full baseline, taken with the dispatched test command before any file was
written:

```
uv run pytest
→ 157 passed, 22 skipped in 5.91s
```

The 22 skips are `tests/integration` (no Postgres reachable here); they were
skipped before this pass and are skipped after it.

After this pass:

```
uv run pytest
→ 157 passed, 22 skipped, 23 errors in 6.18s
```

The 157/22 are unchanged — nothing that passed before this pass fails now. All
23 errors are the new tests, all in the **target-does-not-exist-yet** state:

```
ModuleNotFoundError: No module named
'commerce_ops.shared.infrastructure.driving.slack_app'
```

raised from the autouse cache-reset fixture. That establishes the target is
absent and **nothing more** — the assertions in these tests have never
executed, so their quality is still unverified. `slack-bolt` and `aiohttp` are
also not yet installed (tasks 1.1–1.3), so nothing here has been exercised
against Bolt at all.

**No new test passed on its first run.** Had one, it would be an alarm, not
coverage.

Also run clean over the whole `tests/` tree with the new files in place:

```
uv run ruff check tests/            → All checks passed!
uv run ruff format --check tests/   → 33 files already formatted
uv run mypy .                       → Success: no issues found in 73 source files
```

---

## Files added

All three are unit tier, mirroring the layer under test
(`AGENTS.md`: `tests/unit/<module>/<layer>/`), and all reach Slack only
through substituted seams — no test here can make an outbound call.

| File | Covers |
|---|---|
| `tests/unit/omni_agent/infrastructure/driving/test_slack_event_dispatch_under_bolt.py` | Unhandled-event acknowledgement, bot-authorship guard, and both MODIFIED requirements |
| `tests/unit/omni_agent/infrastructure/driving/test_slack_no_credential_verification_call.py` | The no-credential-call requirement, and the forbidden-environment guard that protects it |
| `tests/unit/omni_agent/infrastructure/driving/test_slack_credential_absence_rejection.py` | The five scenarios of the credential-rejection requirement, as seven cases |

Helper code (payload builders, the signing helper, the doubles, the
cache-reset discovery) is **duplicated across the three files** rather than
shared. That is forced, not preferred: this pass may write only inside
`tests/**/test_*.py`, so a `conftest.py` or a `_helpers.py` was not available
to it. Factoring it out is a legitimate follow-up for whoever implements.

---

## Scenario accounting

15 `#### Scenario:` blocks in the delta specs. 15 accounted for. **0
uncovered.**

Prefix every identifier below with
`uv run pytest "tests/unit/omni_agent/infrastructure/driving/"` to run it.

### ADDED — An Event With No Registered Handler Is Still Acknowledged (2)

| Scenario | Test |
|---|---|
| An event type with no handler is acknowledged | `test_slack_event_dispatch_under_bolt.py::test_event_type_with_no_handler_is_acknowledged` |
| A handled event type still reaches its handler | `test_slack_event_dispatch_under_bolt.py::test_handled_event_type_still_reaches_its_handler` |

### ADDED — Handling An Event Requires No Credential Verification Call To Slack (3)

| Scenario | Test |
|---|---|
| Handling a mention makes no credential-verification call | `test_slack_no_credential_verification_call.py::test_handling_a_mention_makes_no_credential_verification_call` |
| No credential-verification call at startup | `test_slack_no_credential_verification_call.py::test_startup_makes_no_credential_verification_call` |
| Inbound handling is unaffected by Slack being unreachable | `test_slack_no_credential_verification_call.py::test_inbound_handling_is_unaffected_by_slack_being_unreachable` |

### ADDED — Bot-Authored Events Do Not Trigger A Reply (2)

| Scenario | Test |
|---|---|
| A bot-authored mention receives no reply | `test_slack_event_dispatch_under_bolt.py::test_bot_authored_mention_is_acknowledged_and_receives_no_reply` (ids `carries-bot-id`, `carries-bot-message-subtype`, `carries-both`) |
| A person's mention is unaffected by the bot-authorship check | `test_slack_event_dispatch_under_bolt.py::test_person_authored_mention_is_unaffected_by_the_bot_authorship_check` |

### ADDED — A Request That Cannot Be Handled With Available Credentials Is Rejected (5)

| Scenario | Test |
|---|---|
| The signing secret is absent or empty | `test_slack_credential_absence_rejection.py::test_request_is_rejected_when_the_signing_secret_is_absent` **and** `::test_request_is_rejected_when_the_signing_secret_is_empty` |
| The credential needed to reply is absent or empty | `test_slack_credential_absence_rejection.py::test_person_authored_mention_is_rejected_when_the_bot_token_is_absent` **and** `::test_person_authored_mention_is_rejected_when_the_bot_token_is_empty` |
| A request needing no reply credential is unaffected | `test_slack_credential_absence_rejection.py::test_url_verification_challenge_is_answered_when_the_bot_token_is_absent` |
| An event that is only acknowledged is unaffected | `test_slack_credential_absence_rejection.py::test_unhandled_event_is_acknowledged_when_the_bot_token_is_absent` |
| An event that is deliberately not answered is unaffected | `test_slack_credential_absence_rejection.py::test_bot_authored_mention_is_acknowledged_when_the_bot_token_is_absent` (ids `carries-bot-id`, `carries-bot-message-subtype`) |

Absence and emptiness are separate tests in the first two rows because
design.md records them as reaching their outcome by **different routes** — the
secret's absence via the adapter's own `KeyError` catch, its emptiness via
Bolt's `AsyncRequestVerification`, the token's absence or emptiness via the
`before_authorize` middleware. Seven cases in total, matching tasks.md 7.8.

### MODIFIED — Slack App Mention Triggers Omni (1)

| Scenario (as revised) | Test |
|---|---|
| Mention receives an answer in the same channel (person-authored) | `test_slack_event_dispatch_under_bolt.py::test_person_mention_receives_an_answer_in_the_same_channel` |

A new test was written for the revised scenario, as for an `ADDED` one. The
pre-existing `test_slack_events_endpoint.py::test_mention_receives_an_answer_in_the_same_channel`
covers the same postconditions; it is neither replaced nor edited by this pass.

### MODIFIED — No Sender Identity Restriction (Deferred) (2)

| Scenario (as revised) | Test |
|---|---|
| Any member in the channel can trigger Omni | `test_slack_event_dispatch_under_bolt.py::test_any_human_member_can_trigger_omni` (ids `arbitrary-member`, `another-arbitrary-member`) |
| No member is privileged over another *(added by this change)* | `test_slack_event_dispatch_under_bolt.py::test_no_member_is_privileged_over_another` |

---

## Tests written that cover no scenario

Both trace to `tasks.md`, not to a delta-spec scenario. They are listed
separately so that "the spec requires this" and "the plan requires this" stay
distinguishable.

| Test | Traces to | If the project disagrees |
|---|---|---|
| `test_slack_no_credential_verification_call.py::test_ambient_generic_bot_token_cannot_reinstate_the_credential_call` | tasks.md 7.9 / 2.2a; design.md Verified Finding 7 | The *no-identity-call* half of it is specified; only the `500` status and the guard's existence are derived |
| `test_slack_event_dispatch_under_bolt.py::test_listener_error_other_than_unhandled_request_is_logged` | tasks.md 7.11 / 2.4a; design.md Verified Finding 5 | Wholly derived. Revisit this test, not the requirement |

---

## Assertion classification

### Specified (trace to a delta-spec scenario)

- A success status for an unhandled `event_callback`; omni-agent not invoked.
- The `app_mention` handler runs for a handled type, exactly once.
- No identity/credential-verification method is called while handling a
  mention, and the answer post is not preceded by one.
- No outbound Slack call during startup.
- An authentic request is verified, accepted and acknowledged while Slack is
  unreachable, failing only at delivery; an unsigned one is still rejected.
- A bot-authored `app_mention` is acknowledged, invokes omni-agent zero times
  and posts nothing.
- A person-authored `app_mention` is processed and its answer posted to the
  originating channel; the mention token is stripped from the question.
- `401` when the signing secret is absent or empty, with omni-agent not
  invoked; `401` when the reply token is absent or empty.
- Challenge echoed, unhandled event acknowledged, bot-authored mention
  acknowledged — none of them `401` — while the reply token is absent.
- Two different members' mentions are processed identically.

### Derived (labelled inline in each test)

- **`401` is what "respond as unauthorized" means.** The scenarios say
  "unauthorized"; `401` comes from design.md and tasks.md 2.2b, which name it
  throughout. `_assert_unauthorized` states both forbidden alternatives (a
  `2xx` acknowledgement, a `5xx`) in its failure message.
- **`reaction_added` as the unhandled event type.** The requirement names no
  type. Only `app_mention` is subscribed today, so any other serves; the type
  itself is not what is asserted.
- **`IDENTITY_VERIFICATION_METHODS` is a set, not just `auth.test`.** The
  requirement is stated about the *purpose* of a call, so a single-name check
  would be satisfiable by swapping `auth.test` for `bots.info`. The set is an
  interpretation of "establish or validate its own identity or credentials".
- **The answer post must be the *first* outbound call.** Chosen over
  `methods == ["chat.postMessage"]` deliberately: the requirement says it "does
  not restrict outbound calls a capability makes to do its work", so forbidding
  *later* calls would impose a constraint the requirement disclaims.
- **Containment, not equality, on the posted text**, so an implementation
  adding surrounding formatting is not failed for it. Carried over from the
  pre-existing endpoint tests' own convention.
- **`500` for the forbidden-`SLACK_BOT_TOKEN` environment** (design.md,
  tasks.md 2.2a), together with `raise_server_exceptions=False` on that
  client so the status is observable as a response rather than re-raised.
- **Nothing is posted to Slack on a rejected or unhandled request.** The
  scenarios say what must not be invoked; "and nothing reached the channel"
  is the test author's addition.

### Deliberately untested, with the reason

- **The wording of any failure message.** Neither spec nor design.md pins
  phrasing, so asserting words would impose a contract nobody agreed to. The
  pre-existing endpoint test makes the same call for the same reason.
- **The `@app.error` handler's status for a recognised
  `BoltUnhandledRequestError` vs. any other error.** design.md is explicit
  that with `process_before_response` at its default, the acknowledgement is
  already decided by the time a listener error arrives, so status cannot
  distinguish them. Asserted on the log record instead.
- **`ssl_check` handling.** design.md's Verified Finding 9 establishes it
  short-circuits at middleware position 1 and is detected by
  `body["ssl_check"]`, not by `type`, so a `before_authorize` exemption for it
  would be exempting a case that cannot arrive. Testing it would pin a path
  that does not exist.
- **That the signing-secret read happens per request rather than per
  construction** (tasks.md 3.11). Distinguishing them from outside requires
  observing a warm process across an environment change with no cache reset in
  between — which is precisely the vacuous-pass shape `_require_cold_cache`
  exists to prevent. Left to review of the diff.
- **`answer_question`'s statelessness across invocations** (tasks.md 4.3).
  That belongs to the `omni-agent` capability, not to this delta, and its
  scenario lives in another spec.
- **Durability of deferred work across a restart.** Named out of scope by
  proposal.md.
- **A present-but-rejected bot token.** The requirement says so explicitly:
  establishing it would need the identity call its sibling requirement forbids.

---

## Unresolved project questions

Recorded rather than resolved: this pass ran as a dispatched subagent with no
channel to ask on. Each names the assumption taken and what depends on it.

1. **The cached Bolt-app factory's reset seam has no name.** tasks.md 2.6a
   requires one; no artifact says what it is called.
   *Assumption:* it is discoverable as either an `lru_cache`-wrapped callable
   exposing `cache_clear()`, or a zero-argument callable named `reset_*` /
   `clear_*`, in `omni_agent...driving.slack` or
   `shared.infrastructure.driving.slack_app`. `_reset_slack_caches` scans for
   both. `_require_cold_cache` asserts at least one seam was found, so a
   naming choice outside that shape fails loudly instead of letting a test
   observe a stale app.
   *Depends on it:* every test in all three files (via the autouse fixture);
   critically, all seven cases in `test_slack_credential_absence_rejection.py`
   and both environment-sensitive tests in
   `test_slack_no_credential_verification_call.py`.

2. **The shared helper's module path is assumed to be
   `commerce_ops.shared.infrastructure.driving.slack_app`.** proposal.md's
   Impact list names `shared/infrastructure/driving/slack_app.py`; the import
   path follows from the package layout, not from a statement.
   *Depends on it:* the cache-reset helper in all three files. A different
   path is a one-line change to `_MODULES_WITH_CACHED_FACTORIES` in each.

3. **The project declares no async test runner.** `pyproject.toml` has no
   `pytest-asyncio` or `anyio` plugin, and every existing test is synchronous.
   *Assumption:* keep every new test synchronous and drive the app through
   `TestClient`, which is also the right level for these scenarios.
   *Depends on it:* all 23 tests. If an async runner is later adopted, none of
   these needs to change.

4. **Whether a test may synchronise on Bolt's scheduled listener task.**
   design.md's Verified Finding 3 says no barrier is needed; it also says
   Bolt *schedules* rather than awaits the listener, which makes a negative
   assertion ("nothing was posted") capable of passing because the listener
   has not run yet.
   *Assumption:* a best-effort `_drain()` (one further `GET /health`
   round-trip) before negative assertions, plus — where one is available — a
   **sequenced positive control**: the suppressed or unhandled event is
   delivered first and a person's mention second, so the negative is only
   asserted once the loop has demonstrably run past it. Neither weakens any
   assertion.
   *Depends on it:* `test_event_type_with_no_handler_is_acknowledged`,
   `test_bot_authored_mention_is_acknowledged_and_receives_no_reply`, the
   `slack_api.posts == []` assertions throughout
   `test_slack_credential_absence_rejection.py`, and
   `test_listener_error_other_than_unhandled_request_is_logged`.

5. **`_drain()` couples these tests to `GET /health`.** No convention covers
   how a test should let scheduled work settle. If `/health` ever moves, three
   files need a one-line edit.

6. **The `@app.error` log's logger name and level are not pinned.**
   *Assumption:* any record at `ERROR` or above emitted during the request
   satisfies tasks.md 2.4a. Narrowing it to a named logger would pin a
   contract no artifact states.
   *Depends on it:* `test_listener_error_other_than_unhandled_request_is_logged`.

---

## Obsolete tests — candidates for human confirmation

**Search bound:** `tests/**/test_*.py`, the dispatched glob, and nowhere else.
No earlier `test-manifest.md` path was supplied to this pass, so no
scenario-to-test mapping from a previous change was consulted, and none was
searched for. Two `MODIFIED` requirements were compared against
`openspec/specs/slack-trigger/spec.md` as it currently stands; no
implementation source was read.

**No test in the glob asserts behaviour this change supersedes, and none
should be deleted.** That is a finding, not an empty list: `grep` over the glob
for `bot_id`, `subtype`, `auth.test`, `workspace member` and `any member`
returns nothing outside the files this pass just added and the two entries
below. In particular, no existing test asserts that a *bot-authored* mention is
answered — which is the only assertion the narrowing of "Slack App Mention
Triggers Omni" would have invalidated.

What the two `MODIFIED` requirements do supersede is **scenario prose quoted
inside two existing tests**, whose assertions remain correct. Both are in
`tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`.

| Candidate | Superseding delta | Evidence | Action implied |
|---|---|---|---|
| `test_slack_events_endpoint.py::test_mention_receives_an_answer_in_the_same_channel` | MODIFIED "Slack App Mention Triggers Omni" | Its docstring quotes the pre-change WHEN, "WHEN the bot is `@mentioned` in a Slack channel with a question". The delta narrows that to "WHEN a person `@mentions` the bot". Its payload carries no `bot_id` and no `subtype`, so **every assertion still holds** under the narrowed requirement | Docstring drift only. **Do not delete, do not rewrite the assertions** |
| `test_slack_events_endpoint.py::test_any_workspace_member_can_trigger_omni` (both params) | MODIFIED "No Sender Identity Restriction (Deferred)" | Its docstring quotes "WHEN any member of the Slack workspace mentions the bot"; the delta reads "any **human** member", and adds the bot-authorship carve-out. Both senders are arbitrary human IDs carrying no bot markers, so **every assertion still holds** | Docstring drift only. **Do not delete, do not rewrite the assertions** |

**These entries are candidates for human confirmation, not conclusions**, and
they carry a conflict the confirmer must resolve rather than this pass:

> `tasks.md` section 6 governs this file and permits exactly three kinds of
> edit to it — the doubles' sync/async shape, one substitution seam, and
> `_ResponseStartRecorder`'s docstring plus one failure message. **Correcting
> these two docstrings is not among them.** This pass therefore reports the
> drift and proposes no edit. Deciding whether section 6's enumeration should
> be widened is `openspec-update-change`'s call, not this pass's — and it is a
> prose question with no assertion attached either way.

The same file's `_ResponseStartRecorder` docstring and the
`BackgroundTasks` failure message are *already* covered by tasks.md 6.3, so
they are not listed as findings here.

---

## What the implementation step must make pass

Run the three new files together:

```
uv run pytest tests/unit/omni_agent/infrastructure/driving/test_slack_event_dispatch_under_bolt.py \
              tests/unit/omni_agent/infrastructure/driving/test_slack_no_credential_verification_call.py \
              tests/unit/omni_agent/infrastructure/driving/test_slack_credential_absence_rejection.py
```

They will keep erroring at fixture setup until
`commerce_ops.shared.infrastructure.driving.slack_app` exists and `slack-bolt`
and `aiohttp` are installed. That is the expected first outcome, not a defect
to repair by stubbing the module.

Task-to-test index, for running exactly what a given task must satisfy:

| tasks.md | Test |
|---|---|
| 2.6a (reset seam) | every test in all three files, via `_require_cold_cache` / the autouse fixture |
| 3.5, 7.5 | `test_bot_authored_mention_is_acknowledged_and_receives_no_reply` |
| 3.8, 7.7 | `test_handled_event_type_still_reaches_its_handler` |
| 3.11, 7.8 | all seven cases in `test_slack_credential_absence_rejection.py` |
| 7.1 | `test_event_type_with_no_handler_is_acknowledged` |
| 7.2 | `test_handling_a_mention_makes_no_credential_verification_call` |
| 7.3 | `test_startup_makes_no_credential_verification_call` |
| 7.4 | `test_inbound_handling_is_unaffected_by_slack_being_unreachable` |
| 7.6 | `test_person_authored_mention_is_unaffected_by_the_bot_authorship_check`, `test_person_mention_receives_an_answer_in_the_same_channel` |
| 7.9 | `test_ambient_generic_bot_token_cannot_reinstate_the_credential_call` |
| 7.10 | `test_no_member_is_privileged_over_another`, `test_any_human_member_can_trigger_omni` |
| 7.11 | `test_listener_error_other_than_unhandled_request_is_logged` |

One standing instruction, from `ai-toolkit:testing` and repeated here because
this is the file the implementer opens: **if an assertion above does not hold
against the real implementation, do not adjust the assertion.** A specified
assertion that does not match means the code is wrong. Where the assertion is
labelled derived, reconsidering it is allowed — and is recorded as a change to
a derived assertion, never performed as a repair. tasks.md 6.3a already states
the same rule for the ordering test, and extends it here: if Verified Finding 3
turns out to be wrong, the finding is what must be corrected.
