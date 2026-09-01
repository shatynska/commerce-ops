## Why

Forty-four unit-tier tests do not run, and the reason recorded against them is false for forty-two of them.

Two `conftest.py` files carry a **duplicated autouse fixture** that skips seven whole files by matching their filenames:

- `tests/unit/conftest.py:8-29` — *"Skip unit-tier tests that incorrectly require a real database. These tests should be moved to the integration tier where they can properly use a real database. For now we skip them to unblock CI."*
- `tests/unit/launch/infrastructure/driving/conftest.py:58-77` — the same seven filenames, the same mechanism, a differently worded message.

The seven files hold 40 test functions; parametrisation brings the reported count to 44. Because the match is on the filename, every test in each file is skipped, not merely a database-dependent subset.

I disabled both fixtures and ran the tier. What is actually there:

| | count | actual cause |
|---|---|---|
| Pass unchanged | **18** | nothing wrong with them at all |
| Fail | **24** | `TypeError: run_automation_pass() missing 1 required keyword-only argument: 'establish_thread'` |
| Fail | **2** | genuinely reach a database, and only because of one testability regression |

The 24 are all in `test_automation_pass_repeat_backoff.py`. They fail in the harness, not in an assertion: `thread-launch-slack-notifications` gave `run_automation_pass` a new required keyword-only argument, and `_run_pass` (`:1146-1183`) was never told about it. That file's harness already has the mechanism for exactly this — `_argument_for(_BACKOFF_ARGUMENT_NAMES)` and `_accepted_parameters()` exist so a collaborator can be supplied only where the entry point accepts it — so the correction is small and the harness was designed to receive it. Nothing about these 24 has anything to do with a database.

The 2 are `test_slack_entry_ack_and_failure_visibility.py::test_a_slow_transaction_does_not_miss_the_acknowledgement_window` and `test_slack_entry_unready_playbook.py::test_a_start_against_a_ready_playbook_is_unaffected`. These do fail on `RuntimeError: DATABASE_URL is not set`, but not because a unit test was wrongly written against a database — the adapter path they exercise was substitutable until `launch_thread_delivery.establish_thread_and_resolve_mention` began opening its own `transaction()` inside the Slack listener. The test did not move; the seam did.

The remaining 18 pass and were never broken.

What this costs is not hypothetical. `test_automation_pass_repeat_backoff.py` is 2,345 lines covering the repeat-detection, cool-off, cool-off-independence and stuck-step-reporting rules of `launch-step-automation` — the whole of the backoff behaviour is currently unverified on every commit and in CI. `test_slack_entry_request_verification.py`'s six tests cover Slack request-signature verification, and they are in the passing 18: signature verification has been running unasserted for no reason at all.

The git trail shows this was arrived at by widening rather than by diagnosis — `1c25b12` → `ecf4904` → `3cdfb4b` → `1267062` → `8f88d12`, five commits over one afternoon, each adding filenames to the list. `AGENTS.md`'s *Verification before any completion claim* and the `testing` standard's rule against weakening a test to reach green were both bypassed, and the pytest hook's own `-rs` output (`pyproject.toml:66`, added precisely so a skip cannot hide) reports the skips on every run with nobody reading them.

## What Changes

- **Both autouse skip fixtures are deleted.** `tests/unit/conftest.py` loses its only content and the file goes with it; `tests/unit/launch/infrastructure/driving/conftest.py` keeps `slack_asgi_app` and the `_DrainsDeferredListeners` wrapper, which are unrelated and correct.
- **`test_automation_pass_repeat_backoff.py`'s `_run_pass` is taught about `establish_thread`**, through the argument-discovery mechanism the harness already carries, and supplies a stand-in for it. No assertion in the file changes; the 24 tests are failing on the way in, not on what they check.
- **The 2 genuinely database-bound tests are made substitutable again**, by whichever of two routes `design.md` settles: substituting `slack_entry`'s module-level `establish_thread_and_resolve_mention` binding the way the module's own `__all__` (`slack_entry.py:86`) already anticipates, or moving those two tests to `tests/integration/launch/`. The first is preferred — it keeps the test at the tier its subject belongs to — and it stops being necessary at all if `inject-the-thread-anchor-poster` lands first, which is noted there.
- **A guard is added so a whole file cannot be skipped by name again.** The mechanism is `design.md`'s to choose; the obligation is that a skip must name the individual test and carry a reason that is true of it, and that a filename-matched blanket skip fails the tier rather than passing it quietly.
- Explicitly **not** in scope: rewriting, splitting, or reducing any of the seven files; the shared-harness duplication that made the 24-test breakage a single-file catastrophe in the first place (`share-the-unit-test-harness`); and any change to `src/`. If a restored test turns out to assert something wrong, that is a finding to raise, not a licence to edit the assertion inside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/` only. Every requirement the restored tests cover is already specified and already correct — `launch-step-automation`'s backoff and stuck-step rules, `launch-entry`'s modal contract, field validation, request verification and unready-playbook refusal — and none of them is being changed. What is wrong is that the suite stopped checking them. `.openspec.yaml` therefore sets `skip_specs: true`, following `isolate-tests-from-the-shared-runner` (2026-08-25), which is the same shape: a defect wholly inside `tests/`, with the temptation to invent a requirement in order to have a delta to write, and the same answer — the requirement would describe a fault that does not exist in the system being specified.

## Impact

- `tests/unit/conftest.py` — deleted in full.
- `tests/unit/launch/infrastructure/driving/conftest.py:58-77` — the duplicate fixture removed; the file's remaining contents untouched.
- `tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py:1146-1183` — `_run_pass` supplies `establish_thread`.
- `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py`, `test_slack_entry_unready_playbook.py` — the two tests named above.
- Untouched, and restored purely by the fixtures' removal: `test_slack_entry_field_validation.py`, `test_slack_entry_modal_contract.py`, `test_slack_entry_no_clickup_projection.py`, `test_slack_entry_request_verification.py`, and the passing remainder of the two files above.
- **The commit-time gate gets slower and stricter.** 44 more tests run on every commit and in CI. That is the point.
- No change to `src/`, to the schema, to CI configuration, or to any deployed behaviour. `pyproject.toml`'s `addopts = "-rs"` stays as it is — it was already reporting this correctly.
