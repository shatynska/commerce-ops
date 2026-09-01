## Why

Forty-four unit-tier tests do not run, and the reason recorded against them — *"Unit test requires database"* — is false for every one of them.

Two `conftest.py` files carry a **duplicated autouse fixture** that skips seven whole files by matching their filenames:

- `tests/unit/conftest.py:8-29` — *"Skip unit-tier tests that incorrectly require a real database. These tests should be moved to the integration tier where they can properly use a real database. For now we skip them to unblock CI."*
- `tests/unit/launch/infrastructure/driving/conftest.py:58-77` — the same seven filenames, the same mechanism, a differently worded message.

The seven files hold 40 test functions; parametrisation brings the reported count to 44. Because the match is on the filename, every test in each file is skipped, not merely a database-dependent subset.

I disabled both fixtures and ran the tier (measured 2026-09-01, on this branch rebased onto `main` at `125d92a`). What is actually there:

| | count | actual cause |
|---|---|---|
| Pass | **19** | 18 with nothing wrong with them at all; 1 green through a swallowed database error — see below |
| Fail | **24** | three harness gaps in one file, none of them a database |
| Fail | **1** | one collaborator that stopped being substitutable |

The 24 are all in `test_automation_pass_repeat_backoff.py`, and they fail in the harness rather than in an assertion. **17** fail on `TypeError: run_automation_pass() missing 1 required keyword-only argument: 'establish_thread'`: `thread-launch-slack-notifications` gave the pass a new required argument, and `_run_pass` (`:1146-1183`) was never told about it. That file's harness already has the mechanism for exactly this — `_argument_for(_BACKOFF_ARGUMENT_NAMES)` and `_accepted_parameters()` exist so a collaborator can be supplied only where the entry point accepts it — so the correction is small and the harness was designed to receive it.

The remaining **7** are the stuck-step report tests, and they survive that correction. Both of their causes sit inside `_report_stuck_step`'s own `try/except`, which is why neither leaves a trace in the failure: `launches_channel()` reads `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` from the environment directly and raises `KeyError` when it is unset, and `_FakeNotifier.post_monitoring_message` takes one positional `message` where production calls it with `channel`, `text` and `thread_ts`. Each is swallowed into a warning, so seven tests fail on an empty message list with nothing naming why.

The 1 is `test_slack_entry_ack_and_failure_visibility.py::test_a_slow_transaction_does_not_miss_the_acknowledgement_window`. It does fail on `RuntimeError: DATABASE_URL is not set`, but not because a unit test was wrongly written against a database — the adapter path it exercises was substitutable until `launch_thread_delivery.establish_thread_and_resolve_mention` began opening its own `transaction()` inside the Slack listener. The test did not move; the seam did. That module's own docstring still says it is imported at module level *so that a unit test can substitute it*.

`test_slack_entry_unready_playbook.py::test_a_start_against_a_ready_playbook_is_unaffected` was the second such test when this proposal was first written, and it now passes — **but not because anything was fixed.** `main` gained `c48a70f` in between, which added the direct-message fallback a thread failure now takes. That test substitutes only `slack_entry.transaction` and sets no launches channel, so the same `RuntimeError: DATABASE_URL is not set` is still raised on every run, swallowed by `slack_entry.py:579`, and its `assert slack_api.posts` is then satisfied by the fallback DM. Verified by running it: the error appears in the captured log of a passing test.

It is therefore green through an exception-swallowing fallback rather than through the delivery `launch-entry` specifies, which is the same defect this change exists to remove and would leave one restored test unable to catch a regression in threaded delivery. It gets the same seam substitution as the ack test rather than being left alone.

Both of these are recorded because the count moved while this proposal sat on a branch, and because the first reading of "it passes now" was wrong — which is the argument for re-measuring at implementation time rather than trusting these numbers.

The other 18 pass and were never broken.

With both fixtures deleted and those harness corrections applied, the commit-time tier is **2023 passed, 0 skipped** — 1979 + 44, with no assertion in any of the seven files changed. That figure was measured before the fifth correction (the unready file, below), which changes how one already-passing test passes without moving the total.

What this costs is not hypothetical. `test_automation_pass_repeat_backoff.py` is 2,345 lines covering the repeat-detection, cool-off, cool-off-independence and stuck-step-reporting rules of `launch-step-automation`, and its repeat-detection and cool-off rules are verified nowhere else — they are unchecked on every commit and in CI. The stuck-step half is partly covered by `test_stuck_step_report_to_thread_reply.py` and `test_stuck_step_report_submitter_fallback.py`, which do run today; that overlap is noted rather than claimed as a gap, and it is itself input to `share-the-unit-test-harness`. `test_slack_entry_request_verification.py`'s six tests cover Slack request-signature verification, and they are among the passing 19: signature verification has been running unasserted for no reason at all.

The git trail shows this was arrived at by widening rather than by diagnosis — `1c25b12` → `ecf4904` → `3cdfb4b` → `1267062` → `8f88d12`, five commits over one afternoon, each adding filenames to the list. `AGENTS.md`'s *Verification before any completion claim* and the `testing` standard's rule against weakening a test to reach green were both bypassed, and the pytest hook's own `-rs` output (`pyproject.toml:66`, added precisely so a skip cannot hide) reports the skips on every run with nobody reading them.

## What Changes

- **Both autouse skip fixtures are deleted**, with no residue — no narrowed list, no commented-out list. `tests/unit/launch/infrastructure/driving/conftest.py` keeps `slack_asgi_app` and the `_DrainsDeferredListeners` wrapper, which are unrelated and correct; `tests/unit/conftest.py` goes with its fixture, having held nothing else.
- **`test_automation_pass_repeat_backoff.py`'s `_run_pass` is taught about `establish_thread`**, through the argument-discovery mechanism the harness already carries, and supplies a stand-in returning no mention — which is what keeps every reported message's text identical to what the file's existing assertions expect.
- **That file's two remaining harness gaps are closed**: an autouse fixture sets `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID`, as three sibling files already do, and `_FakeNotifier` is widened to the call shape production uses while keeping the one it has.
- **The two thread-bound tests are made substitutable again** — the failing one and the one passing through the swallowed error — by substituting the seam *beneath* the preamble — `launch_thread_delivery`'s own `transaction`, `LaunchRepository` and lock — rather than `establish_thread_and_resolve_mention` itself. `design.md` Decision 2 settles this and records why the cheaper route is rejected: the anchor message is posted inside `ensure_launch_thread`, so substituting the whole preamble would force a spec-derived two-post assertion down to one.
- **A guard is added so a whole file cannot be skipped by name again**: no skipped test in `tests/unit` or `tests/agents` fails the run. `design.md` Decision 3 settles the mechanism and records the two narrower rules rejected — one fragile under test selection, one unenforceable. Zero-tolerance is chosen mainly because it cannot be satisfied by widening a list, which is exactly how this defect grew. It is *satisfied on this machine* rather than simply true: two conditional skips already exist in the tier, neither of which fires where the rule is enforced. `design.md` Decision 3 inventories them and a task forces the case rather than resting on the argument.
- Explicitly **not** in scope: rewriting, splitting, or reducing any of the seven files; the shared-harness duplication that made the 24-test breakage a single-file catastrophe in the first place (`share-the-unit-test-harness`); and any change to `src/`. If a restored test turns out to assert something wrong, that is a finding to raise, not a licence to edit the assertion inside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/` only. Every requirement the restored tests cover is already specified and already correct — `launch-step-automation`'s backoff and stuck-step rules, `launch-entry`'s modal contract, field validation, request verification and unready-playbook refusal — and none of them is being changed. What is wrong is that the suite stopped checking them. `.openspec.yaml` therefore sets `skip_specs: true`, following `isolate-tests-from-the-shared-runner` (2026-08-25), which is the same shape: a defect wholly inside `tests/`, with the temptation to invent a requirement in order to have a delta to write, and the same answer — the requirement would describe a fault that does not exist in the system being specified.

## Impact

- `tests/unit/conftest.py` — deleted; the skip fixture was its only content.
- `tests/conftest.py` — **new**, holding the zero-skip guard, path-filtered to `tests/unit` and `tests/agents`. One level up rather than in the deleted file, because `tests/agents` has no conftest of its own and a hook under `tests/unit/` is simply not loaded by `uv run pytest tests/agents` (`design.md` Decision 3).
- `tests/unit/launch/infrastructure/driving/conftest.py:58-77` — the duplicate fixture removed; the file's remaining contents untouched.
- `tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py` — `_run_pass` (`:1146-1183`) supplies `establish_thread`; `_FakeNotifier` (`:761-782`) widened; an autouse fixture sets the launches channel.
- `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py` — the `sessionless` fixture (`:268-271`) extended to `launch_thread_delivery`, and `_FakeSlackResponse` completed with a `ts`.
- `tests/unit/launch/infrastructure/driving/test_slack_entry_unready_playbook.py` — the same seam substitution and launches-channel `setenv`, so its one thread-bound test stops passing through a swallowed `RuntimeError`.
- Untouched, and restored purely by the fixtures' removal: `test_slack_entry_field_validation.py`, `test_slack_entry_modal_contract.py`, `test_slack_entry_no_clickup_projection.py`, `test_slack_entry_request_verification.py`, and the passing remainder of the ack and unready files.
- **The commit-time gate gets slower and stricter.** 44 more tests run on every commit and in CI — roughly +13s measured (46s → 59s). That is the point.
- **Three seams are worked around and left standing**, all of them production code reaching for a global: `launch_thread_delivery`'s own `transaction()`, `thread_establishment`'s `lru_cache`d `AsyncWebClient`, and `launches_channel`'s direct `os.environ` read. All three are `inject-the-thread-anchor-poster`'s scope, and this change records what each one costs a test as input to it.
- No change to `src/`, to the schema, to CI configuration, or to any deployed behaviour. `pyproject.toml`'s `addopts = "-rs"` stays as it is — it was already reporting this correctly.
