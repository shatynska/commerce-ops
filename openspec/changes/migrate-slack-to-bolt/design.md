## Context

See `proposal.md` for motivation. This change was split out of `revise-foundation-for-launch-mvp` after review found two of its load-bearing premises false. Both were then verified directly against the installed library and the existing test files. The corrected findings drive most of the decisions below, so they are stated first.

### Verified finding 1 — `AsyncApp` always calls `auth.test` when given a token

The parent change's design asserted that constructing the app with `token_verification_enabled=False` would mean "no Slack call happens until there is something to send". That is wrong three times over, established by reading `slack-bolt` 1.30.0:

- `AsyncApp.__init__` has **no `token_verification_enabled` parameter at all**. The flag exists on the synchronous `App`, not the async one.
- `AsyncSingleTeamAuthorization.__init__` hardcodes `self.auth_test_result = None`, and its `async_process` does `if self.auth_test_result is None: self.auth_test_result = await req.context.client.auth_test()`. So the call is always made, on the first request that reaches the middleware.
- The only requests that skip it are `url_verification` and `ssl_check` (via `_is_no_auth_required`), and the three events in `no_auth_test_events = ["app_uninstalled", "tokens_revoked", "team_access_revoked"]`. **`app_mention` is not among them.**

Consequences if left unaddressed: the unit tier would make an outbound Slack call with a fake token, Slack would reject it, Bolt would return 401, and every `slack-trigger` success-path test would fail — an outcome that does not depend on any pipeline detail. It also contradicts `AGENTS.md`'s testing strategy, under which `tests/unit` is the fast, mocked tier and real I/O belongs to `tests/integration`. In production, the first mention after every container restart would depend on Slack being reachable at that moment.

`deploy-pipeline`'s "Pull Request Validation Gate" is **not** the authority for this. Its "SHALL run without any host connection" sits beside "SHALL NOT declare access to the deploy SSH credential", and both its scenarios name the *deploy host* specifically; it says nothing about outbound calls to Slack. The requirement below stands on the two grounds above instead.

### Verified finding 2 — the existing endpoint tests are not black-box

The parent change asserted `slack-trigger`'s tests "exercise verification, the challenge, acknowledgement and failure visibility from the outside". They do not. In `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`:

- The `slack_client` fixture does `original = getattr(slack_adapter, "get_slack_client", None)` and then `assert original is not None`, with a message citing design.md. It couples to the adapter's internal factory **by name**.
- `_RecordingAnswerQuestion.__call__` is `def`, returning `str`. `_RecordingSlackClient.chat_postMessage` is `def`, returning `dict`. Awaiting either yields `TypeError`, which the adapter's broad `except` swallows — so the failure message posts instead of the answer, and three tests fail while appearing to test the failure path.

So this change modifies that file. It says so plainly rather than discovering it during implementation.

### Verified finding 3 — Bolt acknowledges before running the listener, and the ordering the existing test measures survives

`AsyncApp.__init__` takes `process_before_response: bool = False` (`slack_bolt/app/async_app.py:116`), documented as "True if this app runs on Function as a Service". The parameter is left at its default and is **not** passed.

The constructor default alone does not settle what the existing ordering test measures, so the runner was read as well. `AsyncioListenerRunner.run`'s non-`process_before_response` branch (`slack_bolt/listener/asyncio_runner.py`) does:

```
if listener.auto_acknowledgement:
    await ack()                 # acknowledge immediately in case of Events API
...
_f: Future = asyncio.ensure_future(run_ack_function_asynchronously(...))
```

So the acknowledgement is produced first, and the listener is *scheduled* — not awaited — as an asyncio task. This differs from `BackgroundTasks` in a way that matters: the task is created **during dispatch**, before the response reaches the wire, whereas FastAPI runs background tasks strictly after. Reading alone therefore cannot establish that the ASGI `http.response.start` event still precedes the listener's first journal entry; that depends on when the loop first yields.

It was settled empirically instead, against `slack-bolt` 1.30.0 in a throwaway environment, reproducing the existing test's shape: an ASGI wrapper journalling `response_started`, a **non-suspending** `answer_question` double journalling `omni_invoked` (the adversarial case — a double that never awaits real I/O is the one most likely to run early), and a non-suspending post double. Over 20 consecutive runs, the journal was `['response_started', 'omni_invoked']` every time, and the post double recorded exactly one call every time.

Two conclusions follow, and both shape section 6:

- The ordering assertion holds unchanged, so no assertion in that test needs to move.
- The listener also *completes* before the `TestClient` block exits, so **no synchronisation barrier is needed**. An earlier draft of this change assumed one would be; that assumption is withdrawn.

This is recorded at this depth because it is the last Bolt behaviour this change relies on, and the change exists because two Bolt defaults were assumed wrongly from documentation. A constructor docstring was the standard that produced the `token_verification_enabled` error; it is not the standard used here.

### Verified finding 4 — with a fixed `AuthorizeResult`, Bolt's self-event filter never fires

`ignoring_self_events_enabled` defaults to `True` (`async_app.py:133`), but the middleware it installs decides via `IgnoringSelfEvents._is_self_event`:

```
(user_id is not None and user_id == auth_result.bot_user_id)
or (bot_id is not None and bot_id == auth_result.bot_id)
```

Because this change constructs the app without `token`, `auth_result` is the fixed `AuthorizeResult` we supply, whose `bot_user_id`/`bot_id` are placeholders that never equal a real Slack ID. **Neither comparison can ever be true, so the filter is effectively disabled.**

Two consequences, in opposite directions:

- The listener-level guard is not defence in depth — it is the *only* thing preventing the bot answering its own posts. It therefore gets a requirement, not a comment.
- A placeholder of `None` cannot cause a *false* drop: both branches are `is not None`-guarded on the incoming value, so a real `user_id` never matches a `None` `bot_user_id`. The risk runs one way only.

### Verified finding 5 — Bolt has a dedicated non-listener path for unhandled requests

`AsyncApp.async_dispatch` builds its response by running whichever listeners match. Only if none produced one does it fall through to `resp = BoltResponse(status=404, body={"error": "unhandled request"})` (`async_app.py:652`). So the 404 is real, and it is reached strictly *after* listener matching has already failed.

`AsyncApp.__init__` takes `raise_error_for_unhandled_request: bool = False` (`async_app.py:117`), documented as "True if you want to raise exceptions for unhandled requests and use `@app.error` listeners instead of the built-in handler, which ... returns 404 to Slack". With it enabled, Bolt raises `BoltUnhandledRequestError`, passes it to the registered error handler, and returns the response object the handler leaves behind (`async_app.py:653-665`).

The handler's return value is honoured: `AsyncCustomListenerErrorHandler.handle` copies a returned `BoltResponse`'s `status`, `headers` and `body` onto the shared response before dispatch returns it (`async_listener_error_handler.py:50-53`). Returning `BoltResponse(status=200)` from `@app.error` is therefore sufficient, and no mutation of the passed-in response is required.

One obligation comes with it: `@app.error` is the handler for **every** listener error, not only unhandled requests. It must branch on `isinstance(error, BoltUnhandledRequestError)` and return nothing for any other error, leaving the response as Bolt left it.

Whether that matters depends on the request class, and both halves are worth stating because this helper is built for a second module. On the **events** path it changes nothing Slack observes: `process_before_response` is at its default, so the acknowledgement is already decided by the time a listener error arrives, and the real obligation there is the log (see the Decisions section). On the **slash-command and interactivity** paths, which respond after the listener runs, an unconditional `BoltResponse(status=200)` genuinely would convert a failure into an apparent success. Returning nothing for unrecognised errors is correct on both, which is why the task states it as an unconditional rule rather than one qualified by request class.

### Verified finding 6 — the injected client is not `app.client`, and substituting the wrong one attempts real HTTP

The ordering spike also established where the outbound seam actually is. Bolt builds the `client` it injects into a listener from the `AuthorizeResult`'s bot token, so it is a *different* `AsyncWebClient` instance from `app.client`. Substituting `app.client.chat_postMessage` leaves the injected client untouched: the listener then calls the real method, attempts outbound HTTP to Slack, and the post double records nothing — observed directly, as zero recorded posts while the answer double still journalled.

That failure is silent in exactly the way this change is trying to eliminate: the listener's own `except` would swallow the resulting error, the test's ordering assertion would still pass, and the unit tier would be making a real outbound Slack call. The substitution must therefore happen at the seam the injected client is built from — patching `AsyncWebClient.chat_postMessage` itself, rather than any one instance. Task 6.2 names this.

### Verified finding 7 — `AsyncApp` falls back to `SLACK_BOT_TOKEN`, which would defeat the `authorize` construction

The decision below turns on constructing the app with no `token`, so that `if self._token:` is false and the `authorize` branch is taken. That is not the same as *passing no token argument*. The constructor reads:

```
if signing_secret is None:
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
token = token or os.environ.get("SLACK_BOT_TOKEN")       # async_app.py:219
...
self._token: Optional[str] = token                       # async_app.py:232
```

So omitting the argument does **not** guarantee `self._token` is falsy. If `SLACK_BOT_TOKEN` is present in the process environment, Bolt adopts it, `AsyncSingleTeamAuthorization` installs, the `authorize` callable is silently ignored, and the `auth.test` call this whole change exists to remove comes back. No argument value prevents this — `token=None` and `token=""` both fall through to the same `or`.

This project does not use that name; its variables are `OMNI_AGENT_SLACK_BOT_TOKEN` and `PRODUCT_AGENT_SLACK_BOT_TOKEN`. The guarantee is therefore currently satisfied by accident of naming, not by construction, and nothing records the constraint. Two consequences:

- The helper **refuses to build when `SLACK_BOT_TOKEN` is present**, so the failure is loud at construction rather than silent at the first mention. This uses only public API — no reliance on Bolt's private `_token`.
- For `SLACK_SIGNING_SECRET` it **logs a warning and continues**, deliberately not failing. The asymmetry is the point: an ambient bot token provably defeats the central guarantee, while the signing-secret fallback is unreachable here because a secret is always passed explicitly. Failing hard on it would buy protection against a hypothetical future edit at the price of taking down every Slack request — including the `url_verification` challenge Slack itself issues, breaking an existing requirement — whenever a base image or a co-tenant integration happens to export a stock name. That trade is not worth making for a fallback that cannot currently fire. The warning is diagnostic only and confers no protection; nothing depends on it.

**Both checks are membership tests (`"NAME" in os.environ`), never value reads, and that is load-bearing.** `runtime-configuration`'s "A variable read by the application but not declared is detected" is enforced by a drift test that scans the source for `os.environ[...]`, `os.environ.get(...)` and `os.getenv(...)`, and that direction "admits no exemption at all". These two names must never be declared — the whole point is that they must be absent — so a value read would put the change in unresolvable conflict with an existing capability: declare them and contradict the constraint, or read them and fail the drift test.

A membership test resolves it, and not by evasion. The distinction is real and matches what the drift test governs: that check exists to catch *variables the runtime requires*, and reading a value is what makes a variable a requirement. These are variables the runtime **forbids**; asserting a name's absence asserts nothing about a value the application consumes. Verified against `tests/unit/shared/application/test_settings_env_drift.py`: its `_EnvReadCollector` implements only `visit_Subscript` and `visit_Call`, so a membership test — an `ast.Compare` — is never recorded. Confirmed by running the collector over both idioms: `os.environ.get("SLACK_SIGNING_SECRET")` is recorded, `"SLACK_BOT_TOKEN" in os.environ` is not.

This also settles what the guard checks. It fires on **presence, not on a truthy value** — deliberately. An empty `SLACK_BOT_TOKEN` cannot defeat the guarantee (Bolt's `token or os.environ.get(...)` leaves `self._token` falsy either way), so raising on it is stricter than the guarantee strictly requires. It is still the right rule: a deployment that sets this name at all has done something this change declares invalid, the value may become non-empty without the deployment changing again, and the alternative — reading the value to decide — is exactly the drift-test conflict above. Presence is both the safer rule and the only one available.
- The constraint is stated in the Impact list, and a test sets `SLACK_BOT_TOKEN` in the environment and asserts the guarantee still holds.

The same `or` applies to `SLACK_SIGNING_SECRET`, though less dangerously: this change always passes a signing secret explicitly, so `signing_secret is None` is false and the fallback is unreachable. The guard names it only so an operator sees the warning if the deployment ever acquires it; it prevents nothing today, and is not relied on.

### Verified finding 8 — a `url_verification` challenge never invokes `authorize`

`AsyncMultiTeamsAuthorization.async_process` returns early when `_is_no_auth_required(req)` is true, and that predicate is `_is_url_verification(req) or _is_ssl_check(req)` (`slack_bolt/middleware/authorization/internals.py:38-39`). So a challenge is answered without the `authorize` callable running at all.

This is what lets the bot token be evaluated *per request* rather than up front when the app is built — which is what keeps `slack-trigger`'s "Endpoint Responds to Slack's URL Verification Challenge" true when the token is absent. See the credentials decision below.

### Verified finding 9 — neither `authorize` route produces 401; a `before_authorize` middleware does

An earlier draft said an `app_mention` with the bot token absent "fails in `authorize` and Bolt answers 401". That was asserted without citation and is false. Both available `authorize` behaviours were run against `slack-bolt` 1.30.0:

| `authorize` behaviour, token absent | `app_mention` | `url_verification` |
|---|---|---|
| returns `None` | **200** | challenge echoed |
| raises | **500** | challenge echoed |
| `before_authorize` middleware returning 401 | **401** | challenge echoed |

Returning `None` lands in `AsyncMultiTeamsAuthorization`'s else branch, which ends at `_build_user_facing_error_response(...)` — and that builds `BoltResponse(status=200, ...)` (`async_internals.py:17-22`). Raising escapes the middleware's `except SlackApiError` and is caught by `async_dispatch`'s outer handler as a 500. So the two obvious routes produce exactly the two outcomes "A Request That Cannot Be Handled With Available Credentials Is Rejected" forbids: an acknowledgement, and a server error.

The response must therefore be emitted before authorization runs. `AsyncApp.__init__` takes `before_authorize` (`async_app.py:125`), a public parameter for a global middleware installed after request verification and immediately before authorization (`async_app.py:418`). A middleware there can short-circuit by returning a `BoltResponse` without calling `next()`, exactly as `AsyncRequestVerification` does.

Two ordering details decide the middleware's predicate.

`AsyncUrlVerification` is installed at position **6**, *after* authorization (`async_app.py:458`). A `before_authorize` middleware at position 3 therefore runs before the challenge is answered and must exempt it itself. `AsyncSslCheck`, by contrast, is at position **1** and short-circuits an SSL check before position 3 is ever reached — so `ssl_check` needs no exemption here. (It would not have worked anyway: `AsyncSslCheck` detects it as `body["ssl_check"] == "1"`, a form-encoded field, not as `body["type"]`.) Only `url_verification` is exempted, and design that says otherwise would be exempting a case that cannot arrive.

The second detail is the one that keeps this requirement from colliding with the other requirements in this same delta. A delivered event the system will not answer — because its type has no handler, or because it is bot-authored — is answered by acknowledgement alone and needs no reply token. Rejecting it would contradict the requirement that governs it *and* make Slack retry an event nothing was ever going to answer, which is the retry storm this design rejects elsewhere.

**The module supplies a predicate over the request body, `will_reply(body) -> bool`, not a list of exempt cases.** The middleware requires the token exactly when that predicate is true. This is deliberate and was arrived at the hard way: two earlier drafts enumerated exemptions instead — first `url_verification` alone, then `url_verification` plus non-reply-bearing event types — and each enumeration turned out to be one case short, because "requests that need a reply credential" is not a list anyone can finish from the outside. A predicate makes the requirement's own scoping sentence true by construction rather than by inventory, and the next request class that replies without being foreseen fails closed rather than silently.

`omni_agent`'s predicate returns False for an `event_callback` whose event type has **no registered reply-producing listener**, and for an `app_mention` carrying `bot_id` or a bot-authored `subtype`; everything else is true, so a slash command or interactivity payload still requires the token. The Shared Kernel helper stays free of any module's vocabulary — more so than with a set, since it no longer needs to know that "event type" is the discriminator at all.

Two limits on the fail-closed property, stated rather than assumed. It holds for an unforeseen *request class*: anything the predicate does not recognise as reply-free is treated as replying. It does **not** hold automatically for an unforeseen *event type* — a predicate written as a whitelist of literal type names would exempt a newly-registered listener's type and let its reply fail silently, which is the inventory problem relocated rather than solved. Keying the predicate on whether a reply-producing listener is registered, rather than on a literal name, is what makes the property real for event types too, and is why it is specified that way.

A predicate that raises — a body shape it cannot traverse — is treated as **True**, requiring the token. An exception escaping `before_authorize` would reach Bolt's outer handler as a 500, which this requirement forbids; failing closed keeps a malformed-but-authentic body on the 401-or-pass path.

The bot-authorship condition consequently appears twice: in this predicate and in the listener guard of task 3.5. That duplication is accepted rather than factored out. They answer different questions at different layers — "will a reply be attempted, so is a credential required" before authorization, and "should this event produce a reply" at dispatch — and the listener guard must stand alone regardless, because Verified Finding 4 makes it the sole defence against the bot answering itself. A shared helper predicate is the obvious way to keep them from drifting.

Verified end to end against `slack-bolt` 1.30.0, with the token absent: person-authored `app_mention` → 401, unhandled `event_callback` → 200, challenge → echoed. With the token present: `app_mention` → 200. With it present but **empty**: 401. The single `if not token` predicate covers absent and empty together, which is why the requirement covers both rather than absence alone.

## Goals / Non-Goals

**Goals:**
- Replace hand-rolled Slack request handling with Bolt, preserving every behavior `slack-trigger` specifies.
- Make no outbound Slack call from the unit tier, and none at container start.
- Stop blocking the event loop on outbound Slack calls and model invocation.
- Establish one construction pattern the second Slack app will reuse.

**Non-Goals:**
- No inbound routes for `product_agent` — the helper exists for them, the routes do not.
- No change to `omni_agent`'s graph structure, model choice, or tool set.
- No improvement to the durability of deferred work.
- No change to any environment variable, or to either Slack app's configuration.
- No weakening of any existing test. No assertion, expected value or postcondition changes anywhere. Exactly three kinds of change occur: the doubles in both files become awaitable, one substitution seam moves, and one test's *explanatory prose* — a docstring and a failure message that describe `BackgroundTasks` as the deferral mechanism — is corrected to describe Bolt's. Its assertions are untouched; see the ordering-test note below.

## Decisions

**The Bolt app is constructed with a custom `authorize` callable and no `token`.** This is forced by Verified Finding 1. `AsyncApp`'s middleware installation reads:

```
if self._token:                              →  AsyncSingleTeamAuthorization   (calls auth.test)
elif self._async_authorize is not None:      →  AsyncMultiTeamsAuthorization   (calls your callable)
else:                                        →  raise BoltError
```

`if self._token:` wins over `elif self._async_authorize`, so **passing both a token and an `authorize` silently ignores the `authorize`** and the `auth.test` call happens anyway. The app must therefore be constructed *without* `token`, with an `authorize` coroutine returning a fixed `AuthorizeResult` carrying the bot token. That result is what downstream listeners' injected `client` is built from, so the token still reaches every outbound call — it simply arrives by declaration instead of by round-trip.

This is a real trade-off, not a free win: Bolt calls `auth.test` in order to learn `bot_user_id` and `bot_id`, which it uses for self-event filtering and which listeners can read from context. Supplying a fixed `AuthorizeResult` means those fields are whatever we put in them. Nothing in `slack-trigger` depends on either, and the alternative is an unconditional network call in the request path, so the trade is worth making — but it is recorded because a later feature that needs `bot_user_id` will need to revisit it.

**The migration introduces three behavior differences, and each gets a requirement.** They are the unhandled-event acknowledgement, the bot-authored-event guard, and the rejection of a request whose credentials are absent — each below. Two existing requirements are narrowed to stay consistent with them: "Slack App Mention Triggers Omni" is scoped to person-authored mentions, and "No Sender Identity Restriction (Deferred)" records that bot-authorship is not a sender restriction. Everything else `slack-trigger` specifies is preserved as-is.

The first of those narrowings was missed in an earlier draft, which restated only the second. That was the wrong one to restate alone: "No Sender Identity Restriction" is the requirement the guard is *compatible* with, while "Slack App Mention Triggers Omni" — unconditional in its original text — is the one it actually excepts.

**An event with no registered listener is acknowledged rather than 404'd.** Bolt's default response when nothing matches is 404. The current adapter returns `{"ok": True}` for any `event_callback`. Slack treats a non-2xx as a delivery failure and retries up to three times, so the default would turn "a newly subscribed event type has no handler yet" from silence into a retry storm. Only `app_mention` is subscribed today, so there is no live impact — which is precisely why it should be fixed now, while it costs one constructor argument and one error handler.

**This is done with `raise_error_for_unhandled_request=True` and an `@app.error` handler, not with a catch-all listener.** A catch-all registered alongside `app_mention` would make listener match order decide whether the real handler ever runs; a catch-all that acknowledged first would silently disable `slack-trigger`'s "Slack App Mention Triggers Omni" while every acknowledgement test stayed green. Verified Finding 5 shows Bolt's unhandled-request path runs strictly *after* listener matching has failed, so the `@app.error` route cannot shadow a real listener by construction rather than by test.

The scenario asserting that a handled event type still reaches its handler, and tasks 3.8 and 7.7, are kept anyway. They no longer guard a hazard this design creates, but they pin the property the requirement actually cares about, and they would catch a future regression that reintroduced one.

The handler must branch on `isinstance(error, BoltUnhandledRequestError)`, and for every other error it must **log**. Status is the wrong lever here: with `process_before_response` at its default, an events listener's error arrives after the acknowledgement has already been decided, so leaving the status alone changes nothing Slack observes. What registering `@app.error` actually displaces is Bolt's default error handler, whose contribution is the log entry. An error handler that recognised only unhandled requests and returned silently for everything else would therefore delete the only remaining trace of a failed answer post — Slack unreachable, a revoked token — without changing any status. Preserving that log is the obligation; the status branch is not.

**A bot-authored `app_mention` is acknowledged but not answered, via a listener-level guard.** Verified Finding 4 establishes that the fixed `AuthorizeResult` disables Bolt's own self-event filter outright, so this guard is the sole mechanism, not a backstop. It checks the event's own `bot_id`/`subtype` — properties of how the message was authored — and never the sender's identity.

This is recorded as a requirement rather than a comment for two reasons. It is a genuine behavior difference from today's adapter, which has no such filter. And a task in the parent change asserted that no sender-based filter was introduced, which was imprecise: the distinction between "authored by a program" and "authored by this particular person" is exactly what makes the guard compatible with "No Sender Identity Restriction", and leaving it unstated is what made the earlier claim wrong. That requirement is restated in the delta to make the carve-out explicit, so its "any workspace member" text no longer reads as contradicted by the code.

The alternative was to supply a real `bot_user_id`/`bot_id` from configuration so Bolt's own filter works, making the guard unnecessary. Rejected: it requires a new environment variable, which contradicts this change's "no environment variable is added" boundary and pulls `runtime-configuration`'s declaration requirement into a change that otherwise touches no configuration. The guard costs one condition and is directly testable; the variable costs a declaration, a deploy-time secret and a drift-test entry. If a later feature needs a genuine `bot_user_id` in context, that is the point to revisit this — and Verified Finding 4 is the record of what revisiting it would fix.

**A request arriving while the signing secret is absent or empty is rejected with 401, and each module's own adapter reads its credentials directly from the environment.** Today's route catches `KeyError`/`ValueError` from constructing the verifier and treats the request as unverified. Under Bolt the two cases split, and an earlier draft of this change described them wrongly — it claimed Bolt raises `slack_bolt.error.BoltError` for an empty or malformed signing secret. It does not. `AsyncApp.__init__` falls back to `os.environ.get("SLACK_SIGNING_SECRET", "")` when none is supplied (`async_app.py:217-222`) and construction succeeds; the only `BoltError` raises in that constructor concern an invalid `client` type, OAuth conflicts, and the case where neither `token` nor `authorize` is given. So:

- **Empty signing secret** — the adapter treats it exactly as absent and answers 401 itself. **Corrected during implementation:** an earlier draft of this design claimed Bolt answered 401 natively here, on the strength of `request_verification.py:63-64`'s `_build_error_response`. That path is never reached. `slack_sdk.signature.SignatureVerifier` raises `ValueError("signing_secret must not be empty.")` (`slack_sdk/signature/__init__.py:41`) before any signature is compared, and it escapes Bolt's verification middleware as a **500** — the outcome this capability's credential requirement forbids as explicitly as it forbids an acknowledgement. Observed directly: the empty-secret test failed with a 500 until the adapter handled the case. The requirement was right; only this rationale was wrong.
- **Absent signing secret** — the same 401, from the same check. Absence and emptiness are one branch (`if not secret`) rather than two, because they are indistinguishable in effect and now reach the same outcome by the same route.
- **Absent bot token** — the `before_authorize` credential gate, per Verified Finding 9. Unchanged. `internal-trigger`'s fail-closed precedent and `slack-trigger`'s "Slack Request Authenticity Is Verified" point the same way: unverifiable means rejected. `test_slack_events_route_is_registered` posts an unsigned `{}` with no secrets present and requires a response that is neither 404 nor 405, so this path stays exercised.

The helper still needs no failure contract **for a credential fault** — it takes a signing secret, builds an app, and raises nothing of its own on account of a credential's value. What changed with the correction above is only *where* the empty case is answered: in the adapter, beside the absent case, rather than inside Bolt. It does raise one precondition error, unrelated to credentials: the `SLACK_BOT_TOKEN` half of the forbidden-environment guard of Verified Finding 7. That guard fires only in a deployment this change declares invalid, and because construction is lazy it fires on the first Slack request; the resulting **500** is the correct answer there, since a runtime carrying that name is misconfigured in a way no per-request status can express, and a 401 would misreport it as an authenticity problem. In that state the `url_verification` challenge fails too — stated here rather than left to emerge, since it is the one case where this change knowingly breaks an existing requirement, and the remedy is to fix the environment. Narrowing the hard failure to that one name, rather than both, is what keeps this blast radius proportionate to the guarantee it protects.

The helper lives in `shared/infrastructure/driving/` and has no HTTP context, so it could not return a status anyway; the adapter, which does have the request, catches the `KeyError` from its own signing-secret read and answers 401. This is simpler than the named-error contract an earlier draft specified, which rested on the false `BoltError` premise above.

The helper takes the credentials as parameters and holds no opinion about where they come from; the module that calls it does the reading. For `omni_agent` that is a direct `os.environ[...]` read of `OMNI_AGENT_SLACK_SIGNING_SECRET` and `OMNI_AGENT_SLACK_BOT_TOKEN` in its own adapter, not a call to `get_settings()`. The adapter is therefore also what owns turning an absent or empty credential into a 401: the read is where the failure originates, so the catch belongs beside it rather than only around construction inside the helper. This is the same shape `slack.py` uses today (`get_signature_verifier`, `get_slack_client`) and is preserved deliberately rather than by omission:

- `runtime-configuration`'s "Every Variable The Runtime Requires Is Declared In One Place" governs the *declaration's completeness*, and states outright that it "does NOT require that every read go through the declaration: a module MAY read a variable directly where per-request tolerance of absence is itself required behavior." Rejecting an unverifiable request with 401 rather than raising is precisely that behavior, and it is the same carve-out `trigger_guard.py` already relies on.
- That carve-out is squarely about the **signing secret**, whose absence makes the request unverifiable and so must fail closed per request. It is read **on every inbound request**, before the cached factory is consulted — not once when the app is built. The requirement's scenario is phrased per request, and a per-construction read would evaluate it once per process, leaving a warm process verifying against a secret the environment no longer has. The read is cheap; the cache still spares the `AsyncApp` construction itself.
- The **bot token** is evaluated **per request, in a `before_authorize` middleware** — not when the app is built, and not inside `authorize`. Two earlier drafts got this wrong in different ways. The first read both credentials together up front, which would have answered a `url_verification` challenge with 401 whenever the token was absent, breaking "Endpoint Responds to Slack's URL Verification Challenge". The second moved the read into `authorize`, which fixed the challenge but produced a 200 on absence rather than a 401 — an acknowledgement of an event that can never be answered, which is the precise outcome the requirement exists to prevent. Verified Finding 9 records both, with the measurements.

  The middleware passes through a `url_verification` challenge — necessary, because `AsyncUrlVerification` runs *after* authorization — and any request the module's `will_reply` predicate rejects, and otherwise returns 401 when the token is absent or empty. It needs no `ssl_check` branch, for the reasons in Verified Finding 9.

  `authorize` needs no token-absence branch of its own, but not because every request reaching it carries a token — a carved-out request reaches it with the token still absent. It needs none because such a request never uses the injected client: it is acknowledged and dropped without a reply. `authorize` therefore builds its `AuthorizeResult` from whatever the accessor returns, empty string included, and that result is simply never exercised. Anything stronger — asserting a token, raising on absence — would turn a carved-out request into the 500 this requirement forbids.

That split also keeps the failure honest. The token's absence is a server-side misconfiguration rather than an authenticity failure, so 401 is not a perfect description of it — but the alternative, acknowledging an event that can never be answered, tells Slack the work is done when nothing was delivered. 401 at least makes the failure visible in Slack's own delivery log.

A 401 does cost retries, which is the same consequence used above to argue *against* Bolt's 404 default for unhandled events. The two cases differ, and the difference is why the answer differs. A retried unhandled event can never succeed, so its retries are pure waste. A retried mention succeeds as soon as the token is restored, so the retries are the mechanism by which the backlog delivers itself — and the requests they retry are exactly the ones a person is waiting on. That is worth the cost here and is not worth it there. The startup check declaring both variables (`settings.py`) is what surfaces a missing token by name.
- Completeness is unaffected: both variables are already declared in `shared/application/settings.py` as required `NonEmpty` fields, so the startup check still reports them by name, and the drift test still sees the source reading them.

Routing these through `get_settings()` instead would raise a `ValidationError` on an absent secret at first request, turning a 401 into a 500 and contradicting the fail-closed requirement. That is why the direct read stays.

**Bolt construction stays lazy, behind a cached factory.** `test_main_slack_wiring.py` runs `commerce_ops.main` in a fresh interpreter with `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN` and `OPENAI_API_KEY` removed and requires the import to succeed; it also runs the lifespan and `/health` with those absent. So no `AsyncApp` may be constructed at import time or at startup — only on first request, exactly as the `SignatureVerifier`/`WebClient` factories it replaces are today. That file is not modified.

**`answer_question` becomes a coroutine, and the compiled graph is built once.** LangGraph compiles to an object that is safe to reuse across invocations; rebuilding it per message also rebuilds the `ChatOpenAI` client. The graph is built lazily on first use behind the same cached-factory pattern, so importing still requires no `OPENAI_API_KEY`. Invocation moves to `ainvoke`, which is what lets the Bolt listener be a coroutine rather than occupying a thread.

Reusing the compiled graph does not give it memory. `omni-agent`'s "No state across invocations" holds because the graph is compiled without a checkpointer: state lives in the per-invocation input and is discarded when `ainvoke` returns, so two mentions cannot observe each other regardless of whether they share a compiled object. Task 4.3 confirms this rather than leaving it inferred — caching an object and keeping it stateless are independent properties, and only one of them is visible in the diff.

The alternative considered was keeping `answer_question` synchronous and dispatching it with `asyncio.to_thread` from the listener. That would preserve the existing synchronous test double untouched and still keep the event loop free. It was rejected: it keeps a synchronous wrapper around an inherently async graph, and it preserves a seam whose only value is that a test currently uses it. Correcting the double is a smaller and more honest cost than shaping production code around it.

**The test doubles become awaitable; every assertion is preserved.** This is a fixture correction, not a weakened test. `_RecordingAnswerQuestion.__call__` and `_RecordingSlackClient.chat_postMessage` become `async def`, recording exactly what they record now and returning exactly what they return now. The `slack_client` fixture's `assert original is not None` on `get_slack_client` is the one structural change: under Bolt, listeners receive an injected `client`, so the substitution seam moves. The fixture is updated to substitute at the new seam, and the tests' postconditions — what was posted, to which channel, with what text — are untouched.

**The ordering test keeps every assertion it has.** `test_app_mention_is_acknowledged_before_answer_generation` establishes the acknowledgement ordering through an ASGI wrapper that journals `response_started` when the response headers go out, against `omni_invoked` journalled by the `answer_question` double. That is mechanism-agnostic: it observes the ordering itself, not the machinery producing it, and Verified Finding 3 establishes that Bolt at its default acknowledges before running the listener, so the ordering it asserts still holds.

What is `BackgroundTasks`-specific is only the prose around it — `_ResponseStartRecorder`'s docstring, which explains the ordering in terms of FastAPI running background tasks after the response is sent, and the failure message asserting the generation "must be scheduled as a background task". Both describe a mechanism that is no longer the one in use, and both are corrected. Nothing else in the file changes for this test: Verified Finding 3 establishes empirically that both the ordering and the two postconditions hold under Bolt with non-suspending doubles, so no synchronisation barrier is required.

The same applies to `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`, whose `post_monitoring_message` double is synchronous. Left alone, `await None` would raise `TypeError` inside `_attempt_post`'s broad `except Exception`, be logged, and every assertion would still pass — the tests would go green while no longer proving delivery happened. That silent-pass is the reason this correction is a task rather than an implementation detail.

**One Bolt app per Slack app, built by a shared helper.** There are two Slack apps with separate credentials, and `README.md`'s module-boundary contract states each module owns its own driving adapters including its own Slack credentials. Each module therefore constructs its own instance from its own variables. The construction pattern carries no business logic and belongs in the Shared Kernel alongside `trigger_guard.py`, which is there for the same reason and is the direct precedent.

## Risks / Trade-offs

- [Risk] The custom `AuthorizeResult` carries placeholder `bot_user_id`/`bot_id`, which Verified Finding 4 shows disables Bolt's self-event filter entirely → the bot would answer its own posts, and could enter a reply loop with another bot. Mitigated by the listener-level guard on the event's `bot_id`/`subtype`, which is the sole mechanism rather than a second line of defence, by the requirement covering it, and by a test asserting a bot-authored `app_mention` produces no reply. The inverse failure — a placeholder wrongly matching and dropping genuine events — is ruled out by the middleware's `is not None` guards, established in the same finding.
- [Risk] Bolt owns verification and dispatch, so a future Bolt change could alter `slack-trigger`'s observable behavior → mitigated by `slack-trigger`'s scenario tests continuing to run against the new implementation, and by pinning `slack-bolt` with a compatible-release constraint rather than an open upper bound.
- [Risk] Modifying two test files while claiming behavior is preserved is exactly where a regression hides → mitigated by making the corrections mechanical and reviewable: `def` → `async def` on the doubles, one fixture seam, and one docstring plus one failure message re-worded to name Bolt's deferral instead of FastAPI's. Any change to an assertion, an expected value or a postcondition is out of scope for this change.
- [Risk] The `@app.error` handler is Bolt's handler for *every* listener error, so one that recognised only unhandled requests would silently drop the rest → mitigated by branching on `BoltUnhandledRequestError` and **logging** every other error, pinned by task 7.10's assertion on the log record. Status is not the mitigation here and the existing failure-path tests are not either: with the acknowledgement already decided, status cannot distinguish the cases, and task 3.4's own `except` handles the `answer_question` failure without the error ever reaching `@app.error`.
- [Trade-off] `aiohttp` enters the image alongside `httpx`, and this project must declare and carry it itself. It is not transitive: `slack-bolt` 1.30.0 requires only `slack_sdk<4,>=3.38.0`, and `slack-sdk` declares `aiohttp` under its `optional` extra alone. Accepted: Bolt's async app and `AsyncWebClient` both need it, and the alternative is Bolt's synchronous app, which reintroduces the blocking this change exists partly to fix. Because it is a direct dependency rather than an inherited one, it is pinned here like any other.
- [Trade-off] Acknowledging unhandled events means a genuinely misrouted event is silently absorbed rather than retried. Accepted: it matches today's behavior, and a retry storm is the worse failure.

## Migration Plan

No environment variable changes, no Slack app reconfiguration (the Events Request URL is unchanged), no schema change, no deploy-pipeline change.

The rollout risk is concentrated in one place: whether the custom `authorize` construction genuinely prevents the `auth.test` call. That is verified by an explicit test asserting no outbound HTTP is attempted while handling a signed `app_mention` with a fake token — not by inspection, since the whole reason this decision exists is that inspection of the documentation gave the wrong answer once already.

`add-product-creation-clickup-task` is **not** revised as part of this change. It is recorded as a dependency: it is unimplemented, its Slack-handling decisions are superseded by this migration, and it must be revised via `openspec-update-change` before it is implemented. Editing another change's planning artifacts from inside this one would fold a second, independent concern into this change's completion criteria, against the scope-control rule in `AGENTS.md`. Nothing is unwound by deferring it, because nothing was built.
