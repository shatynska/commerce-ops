## Why

`automation_pass._report_stuck_step` posts through its injected `notifier` with `channel=`/`text=`/`thread_ts=` keyword arguments — the shape `launch`'s own `slack_notifier.post_monitoring_message` takes. `worker.py` instead injects `briefing`'s notifier, whose `post_monitoring_message(message: str)` cannot bind those keywords. Every call raises `TypeError`, caught by `_report_stuck_step`'s own `except Exception` and logged as a warning; the backoff record is never stamped as reported, so the next pass tries again and fails the same way. `launch-step-automation`'s *A step whose handler has stopped making progress is reported once* already requires this delivery — the implementation is what is failing to meet it, not the wording. A stuck step is never reported to anybody, silently, right now. Recorded in `docs/deferred-work.md` ("The stuck-step report cannot reach the notifier the worker injects") as worth its own change ahead of the tidy-ups queue, because the harm is ongoing.

## What Changes

- `worker.py` injects `launch`'s own notifier (`commerce_ops.launch.infrastructure.driven.slack_notifier`) into `automation_pass.notifier`, instead of `briefing`'s — its `post_monitoring_message(*, channel, text, blocks=None, thread_ts=None)` is the shape `_report_stuck_step` already assumes.
- `_report_stuck_step`'s `notifier: Any` parameter — and the `notifier: Any` signatures it is threaded through on the way to the call — is narrowed to the `Protocol` the call actually requires, so a future mismatch between what is injected and what is called is a `mypy --strict` failure rather than a swallowed `TypeError`. The module-level global is itself typed `MonitoringNotifier` today, and that is *also* the wrong shape — `MonitoringNotifier.post_monitoring_message(message: str)` cannot bind the call either; it happens to go uncaught only because the value is erased to `Any` at the first hop into `_report_stuck_step`. This change corrects the global's own declared type, not only the hops after it.
- The test doubles standing in for the notifier in the affected tests are tightened to the real collaborator's shape, so a future regression is caught by a `TypeError` in the test itself rather than by a double that tolerates a call the real notifier cannot.

No behavior described by any spec changes: `launch-step-automation` already requires that this report be delivered. This is a defect in the code failing to meet that requirement, not a gap in what is required.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — see Why. `skip_specs: true` is set in this change's `.openspec.yaml` accordingly.

## Impact

- `src/commerce_ops/worker.py` — the `automation_pass.notifier` wiring line.
- `src/commerce_ops/launch/infrastructure/driving/automation_pass.py` — `_report_stuck_step`'s `notifier: Any` parameter, and every `notifier: Any` signature between the module global and that call, narrowed to a typed port.
- Possibly `src/commerce_ops/shared/application/ports.py` (`MonitoringNotifier`) or a new port, depending on which shape (`launch`'s three-keyword call, or a shared one) the narrowed type should name — a design decision, not settled here.
- Tests substituting a notifier double for `automation_pass`: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py`, `test_stuck_step_report_submitter_fallback.py`, and `test_automation_pass_repeat_backoff.py`'s `_FakeNotifier` — the last one deliberately accepts *both* the message-only positional call and the channel/text/thread_ts keyword call ("this double's own docstring says it is satisfied structurally and pins no call shape"), which is exactly the tolerance that let this defect ship unnoticed.
- One-time effect at deploy: every step that has been silently stuck and unreported since the defect shipped becomes reportable — its backoff record has never been stamped as reported, so the first pass after deploy delivers the report it always owed.
