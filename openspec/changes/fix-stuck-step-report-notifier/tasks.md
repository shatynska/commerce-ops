## 1. Add the port

- [x] 1.1 Add `ThreadReplyNotifier` to `src/commerce_ops/launch/application/ports.py`: `async def post_monitoring_message(self, *, channel: str, text: str, thread_ts: str | None = None) -> object: ...`, alongside the module's other consumer-owned ports. **Correction found during task 2.3's `mypy --strict` run**: `launch`'s own `post_monitoring_message` returns `str` (the posted `ts`), not `None` — the return type is `object`, matching `SteadyStateStamper`'s existing convention in this same file for "caller does not use the return value."
- [x] 1.2 Re-export it from `src/commerce_ops/launch/application/__init__.py` (import and `__all__`), matching how the module's other five `ports.py` Protocols are already re-exported — this module's public surface, not `.ports` directly, is what every `launch.infrastructure.driving` file imports from.

## 2. Retype the call chain

- [x] 2.1 `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`: change the module global at line 146 from `notifier: MonitoringNotifier | None = None` to `notifier: ThreadReplyNotifier | None = None`; import `ThreadReplyNotifier` from `launch.application` (its `__init__.py`, per task 1.2 — not the `.ports` submodule, matching every sibling import in this file) and drop the now-unused `MonitoringNotifier` import if nothing else in the file needs it.
- [x] 2.2 Change `notifier: Any` to `notifier: ThreadReplyNotifier | None` (not bare `ThreadReplyNotifier` — see below) on `run_automation_pass` (`:260`), `_walk_launch` (`:376`), `_note_repeat` (`:503`) and `_report_stuck_step` (`:599`).
- [x] 2.3 Run `mypy --strict` over `automation_pass.py` and confirm it is clean — this is the check that would have caught the original defect had the type not been erased to `Any`. **Correction found here and applied**: a bare `ThreadReplyNotifier` on the four signatures fails `mypy --strict` at `resolve_automated_steps:1007`, since the module global stays `ThreadReplyNotifier | None` and `_report_stuck_step` already has an explicit `if notifier is None: ...` branch (`:611`) — the `Optional` has to be threaded through every hop, not narrowed away. `design.md` D3 corrected to match.

## 3. Fix the injection

- [x] 3.1 `src/commerce_ops/worker.py`: import `commerce_ops.launch.infrastructure.driven.slack_notifier`, aliased (e.g. `launch_slack_notifier`) to avoid colliding with `briefing`'s `slack_notifier` already imported there.
- [x] 3.2 Change `automation_pass.notifier = slack_notifier` (`:90`) to inject the aliased `launch` module instead of `briefing`'s. Leave `overdue_check.notifier` and `clickup_sync_job.notifier` (both `briefing`'s, both message-only callers) untouched.

## 4. Tighten the test doubles

- [x] 4.1 `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py`: narrow `_CapturingNotifier.post_monitoring_message(self, **kwargs: Any)` to `post_monitoring_message(self, *, channel: str, text: str, thread_ts: str | None = None) -> None`, recording the three fields as before; correct its docstring (`:159-160`), which currently claims it matches `MonitoringNotifier`, to name `ThreadReplyNotifier` instead.
- [x] 4.2 `tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py`: the same narrowing and docstring correction on its `_CapturingNotifier`.
- [x] 4.3 `tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py`: narrow `_FakeNotifier.post_monitoring_message` to the same three-keyword shape only, dropping the positional-message branch and the `post`/`notify` aliases that exist only to cover call shapes this notifier is never actually called under; also correct `__call__` (`:796-798`), which still calls `self.post_monitoring_message(text)` positionally and would break under the narrowed signature — remove it alongside `post`/`notify` unless something in the file actually invokes the fake as a callable (grep confirms nothing does today). Keep `.messages`/`.attempts`/`.refuse` and `_DeliveryRefused` as they are, since those are what the file's assertions read.
- [x] 4.4 Update that file's docstring (lines ~66-71, ~769-785) to drop the "pins no call shape" framing now that it pins one deliberately, and to say why: it is `ThreadReplyNotifier` specifically, not `MonitoringNotifier`, because `launch`'s own notifier is now what worker.py injects.

## 5. Verify

- [x] 5.1 Run `uv run pytest tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py` and confirm green. 41 passed.
- [x] 5.2 Run the full `uv run pytest` unit+agents tier and `mypy --strict` to confirm nothing elsewhere regresses from the narrowed types. 2482 passed; `mypy --strict src/` clean across all 142 source files.
- [x] 5.3 Confirmed via `inspect.signature(...).bind(...)`, mirroring `docs/deferred-work.md`'s own demonstration: `launch`'s own `post_monitoring_message` now binds `channel=`/`text=`/`thread_ts=` cleanly (the module `worker.py` injects after this fix), while `briefing`'s still correctly raises `TypeError: missing a required argument: 'message'` on the same call (the module it used to inject) — proof the swap resolves the original defect.
