# Test manifest — `module-boundary-conventions`

Not an OpenSpec-schema artifact; `openspec instructions apply` will not surface
this file among its context files. Read it on purpose before implementing.

## Scope of this pass

The proposal names three capability areas (see `proposal.md` - Capabilities):

- `slack-trigger` and `omni-agent`: explicitly **no delta** — behavior is
  unchanged by the `slack.py` relocation, so nothing to derive tests from
  here. The two existing tests that physically move
  (`tests/unit/shared/infrastructure/driving/test_slack_events_endpoint.py`,
  `tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py`) are
  implementation-tracked (`tasks.md` 2.7), not a delta-spec scenario, and are
  out of this pass's scope per the dispatch instructions. They are untouched
  by this pass.
- `deploy-pipeline`: the one capability with a spec-level delta — MODIFIED
  requirement "Pull Request Validation Gate"
  (`specs/deploy-pipeline/spec.md` in this change root vs.
  `openspec/specs/deploy-pipeline/spec.md` as it stands today).

Everything below concerns `deploy-pipeline`'s MODIFIED requirement only, since
it is the only source of scenarios in this change.

## Scenario accounting

Both scenarios under the MODIFIED "Pull Request Validation Gate" requirement
are enumerated and accounted for. Both are **uncovered by any test in this
pass**, for the same reason.

### Scenario: Pull request with a failing check is blocked

> WHEN a pull request fails `ruff`, `mypy`, `lint-imports`, or either pytest
> tier THEN the validation job SHALL fail and report the failure on the pull
> request, without attempting to reach the deploy host

**Uncovered. Reason:** this scenario describes the behavior of a GitHub
Actions job definition (`.github/workflows/ci.yml`) — that a PR fails when
one of its steps fails, and that no deploy-host connection is attempted. That
is CI/CD orchestration behavior, not application code. This project's three
pytest tiers (`tests/unit/<module>/<layer>/`, `tests/agents/<module>/`,
`tests/integration/<module>/`, per `AGENTS.md`'s Testing Strategy) are
defined to mirror the module/layer architecture of application code under
`src/commerce_ops`; none of them has any existing precedent for asserting
GitHub Actions workflow behavior, and a workflow job's actual pass/fail
semantics on a real pull request cannot be observed by running pytest
in-repo at all — only by GitHub Actions itself. Parsing `ci.yml` with a YAML
library and asserting a `lint-imports` step's mere *presence* would be a
different, much weaker claim than what the scenario states (that a failing
check actually blocks the PR without a host connection), would exercise a
testing mechanism this project has never adopted, and was flagged in the
dispatch as something not to force. No test was written for this scenario in
any pytest tier.

### Scenario: Validation requires no deploy secret

> WHEN the validation job runs on a pull request THEN it SHALL complete
> without reading the deploy SSH private key or any host-reachability secret

**Uncovered. Reason:** same as above — this is a property of the GitHub
Actions job's declared permissions/secrets access, not of application code
reachable from a pytest process in this repository. No test was written for
this scenario.

**Total: 2 scenarios in the delta spec, 2 accounted for (0 covered, 2
uncovered with reason). No test files were created by this pass.**

## Assertion classification (specified / derived / deliberately untested)

Not applicable — no assertions were written, since no test was created. Both
scenarios are recorded as uncovered above rather than represented by any
placeholder assertion.

## Obsolete tests

MODIFIED delta present (`deploy-pipeline`'s "Pull Request Validation Gate"),
so this section is applicable — not "not applicable."

**Search performed** (bounded to the dispatched test-path glob
`tests/**/test_*.py`, per the identification rule — no earlier
`test-manifest.md` path was supplied for this dispatch, so none was
consulted): grepped the whole `tests/` tree, case-insensitively, for
`ruff`, `mypy`, `lint-imports`, `deploy-pipeline`, `ci.yml`, `pull request`,
`validation gate`, `github actions`, `workflow`.

**Result:** one incidental hit —
`tests/unit/shared/infrastructure/driving/test_main_slack_wiring.py`, whose
module docstring mentions the `deploy-pipeline` spec's "Pull Request
Validation Gate" requirement as background for why two of its regression
guards exist (`test_main_imports_without_slack_secrets_in_environment`,
`test_health_endpoint_still_serves_without_slack_secrets` — asserting that
`commerce_ops.main` imports and `/health` still serves with Slack/OpenAI
secrets absent from the environment). Read against the actual delta: those
guards assert behavior around the *unmodified* "no production-scoped
secrets, no host connection" property of the validation gate, not the
enumerated check list the delta changes (adding `lint-imports`). Nothing in
that file asserts or depends on the specific set of checks the job runs, so
adding `lint-imports` to that list does not make its assertions false. **No
bearing test was found by this search** — distinguished here from "no such
test exists," since the search is bounded to the test-path glob and cannot
rule out something outside it. This is a candidate list with zero entries by
finding, not by scope exclusion: **not applicable would be the wrong label**
because a MODIFIED delta is present; the correct statement is that the
bounded search found nothing to list.

## Unresolved project questions

- **Question:** does this project have any adopted mechanism for testing
  GitHub Actions workflow definitions (e.g., `actionlint`, a YAML-schema
  assertion, a dedicated CI-config test tier) outside the three pytest tiers
  `AGENTS.md` defines?
  **Answer found in convention files:** none. `AGENTS.md`'s Testing Strategy
  section defines only the three module/layer-mirroring pytest tiers and
  names no CI-config-testing tool or convention.
  **Assumption taken:** the two `deploy-pipeline` scenarios above are left
  uncovered by any test in this pass rather than approximated by a pytest
  test parsing `.github/workflows/ci.yml`'s contents — consistent with the
  dispatch's explicit instruction not to force such a test.
  **Tests depending on this assumption:** none — no test was written for
  either scenario, so nothing is built on top of the assumption; it governs
  only the decision to write zero tests here.

## Baseline

Scoped baseline taken (not full-suite; scoped to the tiers relevant to this
pass, since no application code is touched by this dispatch's target and
`tests/integration` requires I/O this pass has no reason to touch):

```
uv run pytest tests/unit tests/agents -q
```
Result: **79 passed**, 0 failed, prior to any change made in this pass. No
test file was added, edited, or deleted by this pass, so this baseline is
also the expected post-pass result — re-running the same command should
still show 79 passed with nothing new introduced.

`tests/integration` was not run as part of this baseline: this pass added no
integration-tier test and touches nothing that tier covers.

## Files touched by this pass

None under `tests/`. This manifest
(`openspec/changes/module-boundary-conventions/test-manifest.md`) is the only
file this pass wrote.
