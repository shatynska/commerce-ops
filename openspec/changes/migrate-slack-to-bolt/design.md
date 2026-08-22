## Context

See `proposal.md` for motivation. This change was split out of `revise-foundation-for-launch-mvp` after review found two of its load-bearing premises false. Both were then verified directly against the installed library and the existing test files. The corrected findings drive most of the decisions below, so they are stated first.

### Verified finding 1 — `AsyncApp` always calls `auth.test` when given a token

The parent change's design asserted that constructing the app with `token_verification_enabled=False` would mean "no Slack call happens until there is something to send". That is wrong three times over, established by reading `slack-bolt` 1.30.0:

- `AsyncApp.__init__` has **no `token_verification_enabled` parameter at all**. The flag exists on the synchronous `App`, not the async one.
- `AsyncSingleTeamAuthorization.__init__` hardcodes `self.auth_test_result = None`, and its `async_process` does `if self.auth_test_result is None: self.auth_test_result = await req.context.client.auth_test()`. So the call is always made, on the first request that reaches the middleware.
- The only requests that skip it are `url_verification` and `ssl_check` (via `_is_no_auth_required`), and the three events in `no_auth_test_events = ["app_uninstalled", "tokens_revoked", "team_access_revoked"]`. **`app_mention` is not among them.**

Consequences if left unaddressed: the unit tier would make an outbound Slack call with a fake token, contrary to `deploy-pipeline`'s "Pull Request Validation Gate" running "without any host connection"; Bolt would then return 401 and every `slack-trigger` success-path test would fail. In production, the first mention after every container restart would depend on Slack being reachable at that moment.

### Verified finding 2 — the existing endpoint tests are not black-box

The parent change asserted `slack-trigger`'s tests "exercise verification, the challenge, acknowledgement and failure visibility from the outside". They do not. In `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`:

- The `slack_client` fixture does `original = getattr(slack_adapter, "get_slack_client", None)` and then `assert original is not None`, with a message citing design.md. It couples to the adapter's internal factory **by name**.
- `_RecordingAnswerQuestion.__call__` is `def`, returning `str`. `_RecordingSlackClient.chat_postMessage` is `def`, returning `dict`. Awaiting either yields `TypeError`, which the adapter's broad `except` swallows — so the failure message posts instead of the answer, and three tests fail while appearing to test the failure path.

So this change modifies that file. It says so plainly rather than discovering it during implementation.

## Goals / Non-Goals

**Goals:**
- Replace hand-rolled Slack request handling with Bolt, preserving every behavior `slack-trigger` specifies.
- Make no outbound Slack call during the PR-validation gate, and none at container start.
- Stop blocking the event loop on outbound Slack calls and model invocation.
- Establish one construction pattern the second Slack app will reuse.

**Non-Goals:**
- No inbound routes for `product_agent` — the helper exists for them, the routes do not.
- No change to `omni_agent`'s graph structure, model choice, or tool set.
- No improvement to the durability of deferred work.
- No change to any environment variable, or to either Slack app's configuration.
- No weakening of any existing test: doubles become awaitable, assertions do not change.

## Decisions

**The Bolt app is constructed with a custom `authorize` callable and no `token`.** This is forced by Verified Finding 1. `AsyncApp`'s middleware installation reads:

```
if self._token:                              →  AsyncSingleTeamAuthorization   (calls auth.test)
elif self._async_authorize is not None:      →  AsyncMultiTeamsAuthorization   (calls your callable)
else:                                        →  raise BoltError
```

`if self._token:` wins over `elif self._async_authorize`, so **passing both a token and an `authorize` silently ignores the `authorize`** and the `auth.test` call happens anyway. The app must therefore be constructed *without* `token`, with an `authorize` coroutine returning a fixed `AuthorizeResult` carrying the bot token. That result is what downstream listeners' injected `client` is built from, so the token still reaches every outbound call — it simply arrives by declaration instead of by round-trip.

This is a real trade-off, not a free win: Bolt calls `auth.test` in order to learn `bot_user_id` and `bot_id`, which it uses for self-event filtering and which listeners can read from context. Supplying a fixed `AuthorizeResult` means those fields are whatever we put in them. Nothing in `slack-trigger` depends on either, and the alternative is an unconditional network call in the request path, so the trade is worth making — but it is recorded because a later feature that needs `bot_user_id` will need to revisit it.

**Bolt's self-event filtering is left at its default, and `slack-trigger`'s "No Sender Identity Restriction" is unaffected.** Bolt drops events authored by the app's own bot user, which today's adapter does not. That requirement is about not restricting *which workspace members* may trigger Omni; dropping the bot's own messages is loop prevention, not authorization, and a bot answering its own posts is a defect rather than a capability. Recorded because a task in the parent change asserted no sender-based filter was introduced, which was imprecise.

**An event with no registered listener is acknowledged rather than 404'd.** Bolt's default response when nothing matches is 404. The current adapter returns `{"ok": True}` for any `event_callback`. Slack treats a non-2xx as a delivery failure and retries up to three times, so the default would turn "a newly subscribed event type has no handler yet" from silence into a retry storm. Only `app_mention` is subscribed today, so there is no live impact — which is precisely why it should be fixed now, while it costs one catch-all listener. This is the one genuine behavior difference the migration introduces, so it gets a requirement rather than a comment.

**A request arriving while the signing secret is absent or empty is rejected with 401.** Today's route catches `KeyError`/`ValueError` from constructing the verifier and treats the request as unverified. Bolt raises `slack_bolt.error.BoltError` for an empty or malformed signing secret, and the absent case still surfaces as `KeyError` from the factory's own `os.environ[...]`. Both are caught and both yield 401. `internal-trigger`'s fail-closed precedent and `slack-trigger`'s "Slack Request Authenticity Is Verified" point the same way: unverifiable means rejected. `test_slack_events_route_is_registered` posts an unsigned `{}` with no secrets present and requires a response that is neither 404 nor 405, so this path stays exercised.

**Bolt construction stays lazy, behind a cached factory.** `test_main_slack_wiring.py` runs `commerce_ops.main` in a fresh interpreter with `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN` and `OPENAI_API_KEY` removed and requires the import to succeed; it also runs the lifespan and `/health` with those absent. So no `AsyncApp` may be constructed at import time or at startup — only on first request, exactly as the `SignatureVerifier`/`WebClient` factories it replaces are today. That file is not modified.

**`answer_question` becomes a coroutine, and the compiled graph is built once.** LangGraph compiles to an object that is safe to reuse across invocations; rebuilding it per message also rebuilds the `ChatOpenAI` client. The graph is built lazily on first use behind the same cached-factory pattern, so importing still requires no `OPENAI_API_KEY`. Invocation moves to `ainvoke`, which is what lets the Bolt listener be a coroutine rather than occupying a thread.

The alternative considered was keeping `answer_question` synchronous and dispatching it with `asyncio.to_thread` from the listener. That would preserve the existing synchronous test double untouched and still keep the event loop free. It was rejected: it keeps a synchronous wrapper around an inherently async graph, and it preserves a seam whose only value is that a test currently uses it. Correcting the double is a smaller and more honest cost than shaping production code around it.

**The test doubles become awaitable; every assertion is preserved.** This is a fixture correction, not a weakened test. `_RecordingAnswerQuestion.__call__` and `_RecordingSlackClient.chat_postMessage` become `async def`, recording exactly what they record now and returning exactly what they return now. The `slack_client` fixture's `assert original is not None` on `get_slack_client` is the one structural change: under Bolt, listeners receive an injected `client`, so the substitution seam moves. The fixture is updated to substitute at the new seam, and the tests' postconditions — what was posted, to which channel, with what text — are untouched.

The same applies to `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`, whose `post_monitoring_message` double is synchronous. Left alone, `await None` would raise `TypeError` inside `_attempt_post`'s broad `except Exception`, be logged, and every assertion would still pass — the tests would go green while no longer proving delivery happened. That silent-pass is the reason this correction is a task rather than an implementation detail.

**One Bolt app per Slack app, built by a shared helper.** There are two Slack apps with separate credentials, and `README.md`'s module-boundary contract states each module owns its own driving adapters including its own Slack credentials. Each module therefore constructs its own instance from its own variables. The construction pattern carries no business logic and belongs in the Shared Kernel alongside `trigger_guard.py`, which is there for the same reason and is the direct precedent.

## Risks / Trade-offs

- [Risk] The custom `AuthorizeResult` carries placeholder `bot_user_id`/`bot_id` → self-event filtering keys off `bot_user_id`, so a wrong value could let the bot answer itself. Mitigated by giving the listener its own guard on the event's `bot_id`/`subtype` rather than relying solely on Bolt's filter, and by a test covering a bot-authored `app_mention`.
- [Risk] Bolt owns verification and dispatch, so a future Bolt change could alter `slack-trigger`'s observable behavior → mitigated by `slack-trigger`'s scenario tests continuing to run against the new implementation, and by pinning `slack-bolt` with a compatible-release constraint rather than an open upper bound.
- [Risk] Modifying two test files while claiming behavior is preserved is exactly where a regression hides → mitigated by making the corrections mechanical and reviewable: `def` → `async def` on the doubles, and one fixture seam. Any assertion change in the diff is out of scope for this change and should fail review.
- [Trade-off] `aiohttp` enters the image alongside `httpx`. Accepted: it is Bolt's own dependency, and the alternative is Bolt's synchronous app, which reintroduces the blocking this change exists partly to fix.
- [Trade-off] Acknowledging unhandled events means a genuinely misrouted event is silently absorbed rather than retried. Accepted: it matches today's behavior, and a retry storm is the worse failure.

## Migration Plan

No environment variable changes, no Slack app reconfiguration (the Events Request URL is unchanged), no schema change, no deploy-pipeline change.

The rollout risk is concentrated in one place: whether the custom `authorize` construction genuinely prevents the `auth.test` call. That is verified by an explicit test asserting no outbound HTTP is attempted while handling a signed `app_mention` with a fake token — not by inspection, since the whole reason this decision exists is that inspection of the documentation gave the wrong answer once already.

`add-product-creation-clickup-task` is revised as part of this change, so it lands on Bolt's `command`/`view_submission`/`views.open` rather than the hand-rolled parsing its current design.md commits to.
