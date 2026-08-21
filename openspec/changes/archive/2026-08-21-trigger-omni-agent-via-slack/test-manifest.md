# Test manifest — `trigger-omni-agent-via-slack`

Tests derived from this change's delta specs **before** any implementation
existed, by an agent that did not read (and must not read) the implementation
of the behavior under test.

This file is **not** part of the OpenSpec schema — it will not appear among
`openspec instructions apply`'s context files and must be opened on purpose
before implementing.

**This pass added tests and subtracted nothing.** No existing test file was
edited, deleted, disabled, or moved. No implementation code was written.

## Files written

| Path | Contents |
| --- | --- |
| `tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py` | Import-time / wiring regression guards (tasks 5.1, 6.1) |
| `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py` | All six `slack-trigger` delta scenarios |
| `openspec/changes/trigger-omni-agent-via-slack/test-manifest.md` | This file |

Tier placement follows `AGENTS.md`'s `tests/unit/<module>/<layer>/`
convention (module `shared`, layer `infrastructure/driving`), mirroring the
target module `src/commerce_ops/shared/infrastructure/driving/slack.py`.
`tests/unit/test_health.py` predates that convention and was left where and
as it is. No `__init__.py` files were added to the new directories — they
fall outside the dispatched test-path glob `tests/**/test_*.py`, and the
existing `tests/unit/products/**` directories work without them under this
project's pytest configuration.

## Baseline

**Scoped baseline**, taken before any test was written.

- Command: `uv run pytest tests/unit tests/agents --ignore=tests/unit/products`
- Result: **7 passed**.
- Scope and why it is scoped: the full `uv run pytest` is **already red**
  before this pass, aborting during collection with three errors —
  `tests/unit/products/domain/test_launch_playbook.py`,
  `tests/unit/products/domain/test_timing_anchor.py`, and
  `tests/unit/products/infrastructure/test_playbook_loader.py`, all
  `ModuleNotFoundError: No module named
  'commerce_ops.products.domain.launch_playbook'`. Those belong to the
  separate, in-flight `add-launch-playbook` change and are untracked working-
  tree files. They were not touched, and the baseline excludes them so this
  change's accounting is attributable.

## Run after writing (state of each new test)

`uv run pytest tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py tests/unit/test_health.py`
→ 1 failed, 4 passed.

`uv run pytest tests/unit/shared` → collection error on
`test_slack_events_endpoint.py`: `ImportError: cannot import name 'slack'
from 'commerce_ops.shared.infrastructure.driving'`.

Per `ai-toolkit:testing`'s four states:

- **State 2 — the target does not exist yet.** Every test in
  `test_slack_events_endpoint.py` (the whole module fails to import), plus
  `test_slack_events_route_is_registered` (which does execute, and fails on
  `POST /slack/events` returning 404). **The assertions in
  `test_slack_events_endpoint.py` have never executed.** This establishes
  only that the target is absent — it establishes nothing about whether
  those assertions are correct. They must be read on their first real run
  against the implementation, and a first-run pass of the whole module is
  the expected outcome only if the implementation is genuinely complete.
- **State 4 by construction — passing before implementation.**
  `test_main_imports_without_slack_secrets_in_environment` and
  `test_health_endpoint_still_serves_without_slack_secrets` pass today.
  This is not an alarm and not scenario coverage: both are deliberate
  regression guards whose subject (eager construction of
  `SignatureVerifier`/`WebClient` at import time) does not exist yet. Their
  job is to keep passing after the adapter lands. Recorded here so nobody
  mistakes them for evidence that a scenario is covered.

Independent fixture check (does **not** touch the target): the signing
helpers in `test_slack_events_endpoint.py` were verified against a real
`slack_sdk.signature.SignatureVerifier` — the valid case verifies, and all
four negative cases (`no-signature-headers`, `signed-with-wrong-secret`,
`body-tampered-after-signing`, `replayed-stale-timestamp`) fail
verification. This removes the most likely state-3 (broken test) risk from
the verification tests, without establishing anything about the endpoint.

Tooling: `uv run ruff check` and `uv run ruff format --check` pass on both
new files. `uv run mypy .` reports exactly one new error —
`Module "commerce_ops.shared.infrastructure.driving" has no attribute
"slack"` — which is the same absent-target fact and disappears when the
module lands. (The four other `mypy .` errors are pre-existing, from the
`add-launch-playbook` test files.)

## Scenario accounting

Nine `#### Scenario:` blocks exist across this change's two delta specs.
All nine are accounted for below: six covered, three uncovered with reasons.

### `slack-trigger` (ADDED — 6 scenarios, 6 covered)

| # | Requirement / Scenario | Covering test(s) |
| --- | --- | --- |
| 1 | Slack App Mention Triggers Omni / *Mention receives an answer in the same channel* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_mention_receives_an_answer_in_the_same_channel` |
| 2 | Slack Request Authenticity Is Verified / *Unsigned or forged request is rejected* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_request_failing_signature_verification_is_rejected` (4 params: `no-signature-headers`, `signed-with-wrong-secret`, `body-tampered-after-signing`, `replayed-stale-timestamp`) |
| 3 | Endpoint Responds to Slack's URL Verification Challenge / *Challenge request is echoed back* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_url_verification_challenge_is_echoed_back` |
| 4 | Slack Events Are Acknowledged Within Slack's Timeout / *Slow answer generation does not delay the acknowledgement* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_app_mention_is_acknowledged_before_answer_generation` |
| 5 | Answer Generation Failure Is Visible in Slack / *Omni-agent invocation fails* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_omni_agent_invocation_failure_posts_a_message_to_the_channel` |
| 6 | No Sender Identity Restriction (Deferred) / *Any member in the channel can trigger Omni* | `tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_any_workspace_member_can_trigger_omni` (2 params: `arbitrary-member`, `another-arbitrary-member`) |

Runner selection, e.g.:

```
uv run pytest "tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_mention_receives_an_answer_in_the_same_channel"
uv run pytest "tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py::test_request_failing_signature_verification_is_rejected[signed-with-wrong-secret]"
```

### `deploy-pipeline` (MODIFIED — 3 scenarios, 0 covered)

| # | Scenario | Status | Reason |
| --- | --- | --- | --- |
| 7 | *Deploy step updates the running container* | **Uncovered** | States a property of the production host after a GitHub Actions run. Retained verbatim from the pre-change spec — the MODIFIED delta does not alter it. None of this project's three tiers (`tests/unit` mocked, `tests/agents` stubbed-LLM, `tests/integration` real I/O such as Postgres) executes the deploy workflow or reaches the host, so no test here can observe it. Verified by the workflow run itself and by the spec's own post-deploy health check. |
| 8 | *Image tag reaches the host without being committed* | **Uncovered** | Same reason as #7; also retained verbatim from the pre-change spec. |
| 9 | *Runtime secrets reach the container without being committed* | **Uncovered — deliberately, see below** | New in this change. |

**Scenario 9 is not meaningfully testable at this project's test tiers, and
no weak test was invented for it.** Its stated outcome is that the rendered
file's values "SHALL be present in the running container's process
environment after the deploy completes" — a property of the production host
after a GitHub Actions run against `production`-scoped secrets. The only
thing reachable from a pytest tier is the *shape of two config files*:
asserting `.github/workflows/deploy.yml`'s "Render .env" step names
`OMNI_AGENT_SLACK_SIGNING_SECRET`/`OMNI_AGENT_SLACK_BOT_TOKEN`/`OPENAI_API_KEY`, and that
`docker-compose.yml`'s `app` service carries `env_file: .env`. That was
considered and rejected:

- It asserts none of what the scenario states. The scenario's subject is the
  container's process environment; a file-content match is a proxy that can
  hold while the outcome fails — most obviously because task 2.1 (creating
  the GitHub Actions secrets) is manual and outside this repository, so the
  workflow can reference secrets that do not exist and render empty values.
- `tasks.md` already records 2.2 and 2.3 as done, so such a test would pass
  on its first run — state 4, an alarm, not coverage.
- It would pin the workflow file's literal text, failing on unrelated,
  correct edits to it.

Verification for this scenario belongs to the deploy run itself: the
existing "Deploy Is Verified by Checking the Health Endpoint" requirement,
plus a manual confirmation after the first deploy that the container's
environment carries the three values (and, per design.md's own risk note,
that `/opt/commerce-ops/.env`'s host-side permissions match the `umask 077`
expectation).

### Not a scenario — regression guards

`tasks.md` 6.1 is a regression guard, not a delta scenario. It is covered by
`tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py::test_main_imports_without_slack_secrets_in_environment`
and `::test_health_endpoint_still_serves_without_slack_secrets`. Its subject
is the **pre-existing, unmodified** `deploy-pipeline` requirement "Pull
Request Validation Gate", which runs `tests/unit` and `tests/agents` with no
production-scoped secret and "without any host connection".
`::test_slack_events_route_is_registered` covers task 5.1 (wiring), which is
likewise implementation-shaped rather than a scenario.

## Assertion classification

Per `ai-toolkit:testing`: **specified** traces to a stated requirement
(delta spec, or a decision fixed in `design.md`); **derived** was inferred by
the test author; **deliberately untested** was identified and left uncovered
on purpose.

| Assertion | Class | Note |
| --- | --- | --- |
| Answer posted to the *originating* channel (`posted["channel"] == CHANNEL`) | Specified | Spec: "in that same channel" |
| omni-agent's answer text reaches the channel (containment, not equality) | Specified (containment is derived) | Containment chosen so added formatting is not failed; the answer reaching the channel is what is specified |
| omni-agent invoked exactly once per mention | Derived | Spec says the mention triggers omni-agent; "exactly once" is the test author's reading |
| Question passed to omni-agent has the `<@BOTID>` token stripped | Specified (design.md) | design.md: "The mention's bot-ID token is stripped… before it's passed to omni_agent" |
| Stripped question compared after `.strip()` | Derived | Whitespace left behind by stripping the token is pinned nowhere; deliberately not constrained |
| omni-agent invoked as `graph.invoke({"messages": [HumanMessage(...)]})` | Specified (design.md, via `add-omni-agent`) | Enforced indirectly by `_question_from`, which raises a descriptive `AssertionError` on any other shape |
| A request failing signature verification is rejected | Specified | Spec: "SHALL reject the request" |
| "Rejected" read as HTTP 4xx (not a specific code) | Derived | No status code is pinned in the spec or design.md; a 2xx fails, 400/401/403 all pass |
| omni-agent not invoked on a failed-verification request | Specified | Spec: "SHALL NOT invoke omni-agent" |
| Nothing posted to Slack on a failed-verification request | Derived | Not stated; a rejected request producing channel traffic would be a defect worth catching |
| The four invalid-signature variants are each rejected | Specified (the requirement) / Derived (the variant set) | Spec says "fails Slack's signature verification"; which four ways it can fail is the test author's enumeration |
| `url_verification` responds 200 with the same challenge value | Specified | Spec: "respond with the same challenge value it received" |
| The challenge comes back in a JSON body under key `challenge` | Specified (design.md) | design.md: "returns `{"challenge": ...}`". Paired with a weaker `challenge in response.text` so the spec-level guarantee is separately readable |
| No omni-agent call and no Slack post on a `url_verification` request | Derived | A handshake is not an event |
| Acknowledgement precedes the omni-agent invocation (strict ordering) | Specified | The mechanism the spec's acknowledgement-window requirement reduces to; asserted as ordering rather than elapsed time on purpose (see below) |
| Acknowledgement status is 2xx | Derived (design.md says 200) | Asserted as a 2xx range rather than exactly 200 |
| The answer is posted separately, after acknowledgement | Specified | Spec: "SHALL post the answer separately once it is ready" |
| On omni-agent failure, exactly one message is posted, to the originating channel, with non-empty text | Specified | Spec: "post a message to the originating channel… rather than posting nothing" |
| The wording of the failure message | **Deliberately untested** | Neither spec nor design.md pins any phrasing ("a short failure message"). Asserting words would impose a contract nobody agreed to. Consequence, stated plainly: this test cannot distinguish a proper failure notice from a message that wrongly reads as a successful answer. If the implementer wants that guaranteed, the wording needs pinning in the spec or design first |
| The HTTP response is still 2xx when the background task fails | Derived | Follows from the failure occurring after the response is sent |
| Two arbitrary, unrelated senders are both processed identically | Specified | Spec: "any member… the same as any other" |
| "No identity check is performed anywhere" | **Deliberately untested** as a negative | Only observable by reading the implementation, which this pass must not do. Covered in the strongest externally observable form instead: neither sender is known, configured, or allow-listed, and both get answers |
| `commerce_ops.main` imports with `OMNI_AGENT_SLACK_SIGNING_SECRET`/`OMNI_AGENT_SLACK_BOT_TOKEN`/`OPENAI_API_KEY` absent | Specified (`deploy-pipeline`, unmodified requirement) + design.md's lazy-factory decision | Run in a subprocess because the module is already imported in-process |
| `GET /health` still returns 200 with those variables absent | Derived | Guards design.md's stated intent that registering the Slack router not couple `/health` to Slack |
| `POST /slack/events` exists (neither 404 nor 405) | Specified (design.md fixes the path) | Asserted behaviorally; see project question 7 |

**Why acknowledgement is asserted as ordering, not elapsed time.** A
wall-clock assertion ("responded in under 3 seconds") is flaky and cannot
distinguish "fast enough on this machine today" from "acknowledged
independently of how long generation takes", which is what the requirement
states. FastAPI runs `BackgroundTasks` only after the response is sent, so
recording the ASGI `http.response.start` message against the moment
omni-agent is invoked gives a deterministic, machine-independent ordering
assertion for exactly the property required. No `sleep` is used: it would
add runtime without adding evidence.

## Obsolete tests

**Applicable** — this change carries a `MODIFIED` delta
(`deploy-pipeline`: "Deploy Delivers the Compose File and Triggers the
Host-Side Deploy Script").

**Result: no bearing test found, and none is expected to exist.** Both
statements are made deliberately, because they are different claims:

1. *Searched and found none.* The search was bounded to the dispatched
   test-path glob `tests/**/test_*.py` — seven files:
   `tests/agents/omni_agent/test_graph.py`,
   `tests/integration/test_placeholder.py`,
   `tests/unit/products/domain/test_launch_playbook.py`,
   `tests/unit/products/domain/test_timing_anchor.py`,
   `tests/unit/products/infrastructure/test_playbook_loader.py`,
   `tests/unit/test_health.py`, `tests/unit/test_placeholder.py`. A
   case-insensitive search across them for `deploy`, `.env`, `IMAGE_TAG`,
   `compose`, `workflow`, and `docker` returned exactly one hit: a docstring
   line in `tests/unit/test_health.py` citing the `deploy-health-endpoint`
   change's `health-check` delta spec as the source of *those* tests. That
   is a provenance comment about a different capability, not a test bearing
   on the `deploy-pipeline` requirement. No earlier `test-manifest.md` path
   was supplied to this pass, so no scenario-to-test mapping from a previous
   pass was drawn on.
2. *Nothing could be obsolete.* Comparing the delta against the existing
   requirement in `openspec/specs/deploy-pipeline/spec.md` shows the change
   is **purely additive**: both pre-existing scenarios ("Deploy step updates
   the running container", "Image tag reaches the host without being
   committed") are carried over **verbatim**, and the requirement text gains
   clauses ("carrying this application's runtime secrets", "with the
   container's process environment populated from the rendered file's
   runtime secrets") without removing or altering any prior clause. One new
   scenario is added. No previously specified behavior is superseded, so no
   test could have been rendered obsolete by it.

No entry is therefore offered for confirmation, and nothing is proposed for
deletion. **No existing test was edited, deleted, or disabled by this pass.**

## Unresolved project questions

Recorded rather than silently assumed. This pass ran as a dispatched
subagent with no channel to ask on; each entry names the assumption taken
and the tests that depend on it. Where the implementation makes a different
but equally valid choice, the fix is to reconcile with the implementer — not
to weaken the assertion to match whatever appeared.

1. **How the route obtains the Slack client.** `design.md` fixes the
   `lru_cache`-wrapped `get_slack_client()` factory as "the seam tests
   substitute fakes through", but not whether the route calls it directly or
   resolves it through FastAPI's `Depends`. *Assumption:* both, covered
   simultaneously — the `slack_client` fixture monkeypatches the module
   attribute **and** registers `app.dependency_overrides[get_slack_client]`.
   *Depends on it:* every test in `test_slack_events_endpoint.py`. If
   neither substitution takes effect, tests will attempt a live Slack call
   and fail on network/auth — read that as this question being unanswered,
   not as a defect in the assertions.
2. **How the adapter reaches `build_production_graph`.** Direct
   (`from … import build_production_graph`) or via the module. *Assumption:*
   both — `install_graph` patches the name on the adapter module and on
   `commerce_ops.omni_agent.application.graph`, and asserts that at least
   one binding was found. *Depends on it:* every test that exercises a
   mention.
3. **The rejection status code for a failed signature check.** Not pinned
   anywhere. *Assumption:* any 4xx. *Depends on it:*
   `test_request_failing_signature_verification_is_rejected`.
4. **The failure message's wording.** Not pinned anywhere. *Assumption:* only
   that a non-empty message reaches the originating channel. Classified
   deliberately untested above, with its consequence stated.
5. **Whitespace left after stripping `<@BOTID>`.** Not pinned. *Assumption:*
   irrelevant — the observed question is compared with `.strip()` applied.
6. **The `url_verification` response body's shape.** `design.md` says
   `{"challenge": …}`; the spec only requires the value come back.
   *Assumption:* design.md's shape, asserted alongside a weaker containment
   check.
7. **Whether the challenge handshake is also signature-verified.**
   `design.md` orders verification before the `url_verification` branch, and
   Slack does sign challenge requests. *Assumption:* the test signs its
   challenge request, so it passes under either ordering — this pass does
   not force the decision.
8. **Test-file placement and `__init__.py`.** `AGENTS.md` gives
   `tests/unit/<module>/<layer>/` but the repository has both conventions in
   it (`tests/unit/test_health.py` at the tier root, `tests/unit/products/**`
   nested and without `__init__.py`). *Assumption:* nested per `AGENTS.md`,
   no `__init__.py` (outside the dispatched glob; test module basenames are
   unique tree-wide, which is what pytest's default import mode needs).
