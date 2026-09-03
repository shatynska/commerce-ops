## 1. Add the port

- [ ] 1.1 Add `ThreadReplyNotifier` to `src/commerce_ops/launch/application/ports.py`: `async def post_monitoring_message(self, *, channel: str, text: str, thread_ts: str | None = None) -> None: ...`, alongside the module's other consumer-owned ports.
- [ ] 1.2 Re-export it from `src/commerce_ops/launch/application/__init__.py` (import and `__all__`), matching how the module's other five `ports.py` Protocols are already re-exported — this module's public surface, not `.ports` directly, is what every `launch.infrastructure.driving` file imports from.

## 2. Retype the call chain

- [ ] 2.1 `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`: change the module global at line 146 from `notifier: MonitoringNotifier | None = None` to `notifier: ThreadReplyNotifier | None = None`; import `ThreadReplyNotifier` from `launch.application` (its `__init__.py`, per task 1.2 — not the `.ports` submodule, matching every sibling import in this file) and drop the now-unused `MonitoringNotifier` import if nothing else in the file needs it.
- [ ] 2.2 Change `notifier: Any` to `notifier: ThreadReplyNotifier` on `run_automation_pass` (`:260`), `_walk_launch` (`:376`), `_note_repeat` (`:503`) and `_report_stuck_step` (`:599`).
- [ ] 2.3 Run `mypy --strict` over `automation_pass.py` and confirm it is clean — this is the check that would have caught the original defect had the type not been erased to `Any`.

## 3. Fix the injection

- [ ] 3.1 `src/commerce_ops/worker.py`: import `commerce_ops.launch.infrastructure.driven.slack_notifier`, aliased (e.g. `launch_slack_notifier`) to avoid colliding with `briefing`'s `slack_notifier` already imported there.
- [ ] 3.2 Change `automation_pass.notifier = slack_notifier` (`:90`) to inject the aliased `launch` module instead of `briefing`'s. Leave `overdue_check.notifier` and `clickup_sync_job.notifier` (both `briefing`'s, both message-only callers) untouched.

## 4. Tighten the test doubles

- [ ] 4.1 `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py`: narrow `_CapturingNotifier.post_monitoring_message(self, **kwargs: Any)` to `post_monitoring_message(self, *, channel: str, text: str, thread_ts: str | None = None) -> None`, recording the three fields as before; correct its docstring (`:159-160`), which currently claims it matches `MonitoringNotifier`, to name `ThreadReplyNotifier` instead.
- [ ] 4.2 `tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py`: the same narrowing and docstring correction on its `_CapturingNotifier`.
- [ ] 4.3 `tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py`: narrow `_FakeNotifier.post_monitoring_message` to the same three-keyword shape only, dropping the positional-message branch and the `post`/`notify` aliases that exist only to cover call shapes this notifier is never actually called under; also correct `__call__` (`:796-798`), which still calls `self.post_monitoring_message(text)` positionally and would break under the narrowed signature — remove it alongside `post`/`notify` unless something in the file actually invokes the fake as a callable (grep confirms nothing does today). Keep `.messages`/`.attempts`/`.refuse` and `_DeliveryRefused` as they are, since those are what the file's assertions read.
- [ ] 4.4 Update that file's docstring (lines ~66-71, ~769-785) to drop the "pins no call shape" framing now that it pins one deliberately, and to say why: it is `ThreadReplyNotifier` specifically, not `MonitoringNotifier`, because `launch`'s own notifier is now what worker.py injects.

## 5. Verify

- [ ] 5.1 Run `uv run pytest tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py` and confirm green.
- [ ] 5.2 Run the full `uv run pytest` unit+agents tier and `mypy --strict` to confirm nothing elsewhere regresses from the narrowed types.
- [ ] 5.3 Manually trace (or add a small script under the scratchpad, not committed) that `commerce_ops.launch.infrastructure.driven.slack_notifier` (the module now injected) satisfies `ThreadReplyNotifier` structurally — confirming the fix actually binds, mirroring the `inspect.signature(...).bind(...)` check `docs/deferred-work.md` used to demonstrate the original failure.
