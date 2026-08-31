# Test manifest — shift-clickup-completions-to-webhook

Not an OpenSpec-schema artifact: `openspec instructions apply` will not
surface this file among its context files. Read it on purpose before
implementing — it names exactly which tests each implementation task must
make pass.

Written by a dispatch of `openspec-test-writer`, strictly before
implementation. New tests only; nothing pre-existing was edited, deleted, or
weakened. See the report accompanying this manifest for the full account of
what was and was not read.

## Scenario coverage

The delta spec (`specs/launch-clickup-sync/spec.md`) carries exactly one
ADDED requirement — *The webhook subscription is registered as an
idempotent, non-blocking deploy step* — and exactly eight
`#### Scenario:` blocks. All eight are covered below; none is uncovered.

Test file: `tests/unit/test_register_clickup_webhook.py`.

| # | Scenario | Test(s) |
|---|---|---|
| 1 | A first registration creates a subscription and surfaces its secret | `test_a_first_registration_creates_a_subscription_and_surfaces_its_secret` |
| 2 | An existing matching subscription is not recreated | `test_an_existing_matching_subscription_is_not_recreated` |
| 3 | A recreated subscription surfaces its secret exactly as a first registration does | `test_a_recreated_subscription_surfaces_its_secret_exactly_as_a_first_registration_does` |
| 4 | A changed launch folder gets its own fresh subscription | `test_a_changed_launch_folder_gets_its_own_fresh_subscription` |
| 5 | An ambiguous workspace takes no action | `test_an_ambiguous_workspace_takes_no_action[zero-teams]`, `test_an_ambiguous_workspace_takes_no_action[more-than-one-team]` |
| 6 | A missing public endpoint takes no action | `test_a_missing_public_endpoint_takes_no_action` |
| 7 | A registration failure does not block the deployment | `test_a_registration_failure_does_not_block_the_deployment`, plus DERIVED extra coverage `test_a_registration_failure_at_the_create_call_does_not_block_the_deployment_either` |
| 8 | Starting the server performs no registration | `test_starting_the_server_performs_no_registration_of_its_own` |

Every scenario has at least one test named above. Count: 8 scenarios, 8
rows, 10 test executions (2 of them parametrizations of scenario 5's one
test).

## Assertion classification

**SPECIFIED** (traces to the requirement's stated text or a named
scenario's WHEN/THEN):

- A subscription is created only when no match exists (scenarios 1, 3, 4).
- The idempotency check matches on **both** `endpoint` and `folder_id`, not
  endpoint alone (scenario 2's positive match; scenario 4's negative one).
- A created/matched subscription is scoped to the configured launch folder
  and to task status change events (scenario 1's THEN).
- The create request itself carries no caller-supplied secret (requirement
  prose: "the system never supplies its own").
- Every create — first-ever or a recreation — logs the ClickUp-returned
  secret at warning level, naming that `CLICKUP_WEBHOOK_SECRET` must be
  set/updated to match (scenarios 1, 3, 4).
- A changed folder's prior subscription is left as it is — neither deleted
  nor modified (scenario 4).
- An ambiguous workspace (zero or more than one team) takes no action
  beyond logging — no existing-subscription check, no create (scenario 5).
- A missing `admin_base_url` takes no action beyond logging — no create
  (scenario 6).
- Any ClickUp call failure is logged as a warning naming the reason, and
  the deployment proceeds — read as `main()` returning `0` (scenario 7).
- Starting the server performs no registration of its own (scenario 8).

**DERIVED** (inferred; no stated requirement fixes it directly), each
labelled at its assertion site in the test file:

- The specific event name `"taskStatusUpdated"` (from `tasks.md` 1.5; the
  spec text itself says only "task status change events").
- Reading "does not block the deployment" / "prevent the server from
  serving" as `main()` returning `0` — the CLI-entry-point analogue of how
  `test_clickup_sync_job_schedule.py`/`test_clickup_sync_job_stand_down.py`
  read a job body's raise/return as its outcome signal, and how
  `test_preflight.py` reads a process's exit code.
- The result of a healthy run also being exit `0` (asserted as a guard
  alongside scenario 1, not itself scenario 1's stated outcome).
- Extra coverage of scenario 7 at the create-call failure site specifically
  (mirroring `test_clickup_client.py`'s create/update split for its own
  generically-worded failure scenario).
- The realistic ClickUp wire shapes used in the test double (`GET
  /api/v2/team`, `GET .../webhook`, the create response) — best-effort
  reconstructions per `tasks.md`'s own wording, not fixed by any artifact.
  See "Unresolved project questions" below.

**Deliberately untested**, recorded with reason (also in the test file's
own closing comment block):

- The exact internal collaborator/helper names `main()` is built from.
  `tasks.md` calls only for "a thin `main()`/CLI entry over testable helper
  functions," naming none of them. Every test observes the step only from
  its two edges — the HTTP calls it makes and the process exit
  status/log records it produces — which needs no internal name.
- Which of `get_settings()` or direct `os.environ` reads the step's three
  optional settings, and the exact internal call order between team
  resolution and the `admin_base_url` guard. Recorded below as an
  unresolved project question.
- What token scope/permission `CLICKUP_API_TOKEN` needs for webhook
  management — `design.md`'s own Open Questions leaves this open
  deliberately, stating no branch of the answer changes the design.
- Retry behaviour on a failed ClickUp call. No scenario states one, and
  `design.md` names no retry.

## Obsolete tests

**Not applicable.** This change's delta carries no `MODIFIED`, `REMOVED`,
or `RENAMED` requirement — it is purely `ADDED` (one new requirement, zero
touched). No existing test bears on superseded behaviour, so no obsolete-
test search was owed and none was performed.

## Unresolved project questions

1. **Whether the step reads its three optional settings
   (`CLICKUP_API_TOKEN`, `CLICKUP_LAUNCH_FOLDER_ID`, `ADMIN_BASE_URL`)
   through `get_settings()` (whole-model validation) or directly from
   `os.environ`** (the pattern `clickup_webhook.py` already uses for its
   own analogous optional setting, `CLICKUP_WEBHOOK_SECRET`, and the
   pattern `runtime-configuration`'s own docstring names as legitimate:
   "a module may read a variable directly where routing it through the
   declaration would defeat required behavior"). `design.md`'s prose
   (`settings.admin_base_url`) reads like `get_settings()` usage; the
   closest actual precedent in the codebase reads the other way. **No test
   here depends on which is true** — `_baseline_environment()` in the test
   file sets every other required `Settings` field to a disposable value
   regardless, so either reading path is satisfied identically. Flagged so
   whoever implements can settle it deliberately rather than by accident.
2. **The call order between team resolution and the `admin_base_url`
   guard.** `tasks.md` 1.2 (team resolution) precedes 1.3 (the
   `admin_base_url` guard), but that ordering is `tasks.md`'s only, not
   the spec text's — the spec states both guards' outcomes independently
   and pins no sequence between them. `test_a_missing_public_endpoint_takes_no_action`
   supplies an unambiguous, resolvable team regardless, so its assertions
   (no subscription created, the gap logged) hold under either order.
3. **Exact ClickUp wire JSON shapes** for `GET /api/v2/team`, `GET
   .../webhook`, and the create response's secret field — no project
   artifact fixes these; the test file's `_team_response`,
   `_webhook_list_response`, `_create_response` are this pass's
   best-effort reconstruction of ClickUp's public API (the create response
   deliberately carries the secret at two plausible locations to avoid
   committing to one). Correcting these to match ClickUp's real, current
   API shape if this project's own contract differs is a fixture
   correction (failure state 3 in `ai-toolkit:testing`), not a change to
   what any test asserts.

No project convention question arose beyond the above — this repository's
`AGENTS.md` names the runner (`uv run pytest`), the tiering
(`tests/unit`/`tests/agents`/`tests/integration`), and the test-path glob
explicitly, and this file matches the sibling precedent
(`test_clickup_sync_job_schedule.py`, `test_clickup_client.py`,
`test_seed_playbook.py`, `test_preflight.py`) closely enough that no
runner/stack-specific gap needed asking about. No skill matching this
stack beyond `ai-toolkit:testing` and general Python/pytest idiom applies;
none was loaded beyond it.

## Baseline

`uv run pytest tests/unit tests/agents` — **1689 passed, 0 failed**,
recorded before this file's tests were added.

After adding `tests/unit/test_register_clickup_webhook.py`: **1690
passed, 9 errors** (`ModuleNotFoundError` from the `register_main` fixture,
which imports the not-yet-written `commerce_ops.register_clickup_webhook`
lazily — see that file's own module docstring for why the import is
deferred to a fixture rather than module scope). The one new passing test
is `test_starting_the_server_performs_no_registration_of_its_own`, a
regression guard independent of the missing module (`commerce_ops.main`
does not reference it today, and is not expected to until this change's
own task wires it in).

No test outside `tests/unit/test_register_clickup_webhook.py` changed
status. `uv run ruff check`, `uv run ruff format --check`, and
`uv run mypy .` were run against the new file; the only `mypy` finding
against it is the expected "module is installed, but missing library
stubs" against the not-yet-created `commerce_ops.register_clickup_webhook`
import, which resolves once that module exists.

## What the implementation must satisfy

- `src/commerce_ops/register_clickup_webhook.py` must exist, exposing a
  `main() -> int` entry point (`tasks.md` 1.1/1.8), reachable via
  `python -m commerce_ops.register_clickup_webhook`.
- Every test above must pass without weakening or altering any existing
  test in the suite.
- `test_starting_the_server_performs_no_registration_of_its_own` must
  **keep** passing once `main.py`/the Dockerfile chain change — it is a
  regression guard, not new behaviour to introduce.
