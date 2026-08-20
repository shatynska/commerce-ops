# Test manifest — deploy-health-endpoint

Written by `openspec-test-writer`, ahead of implementation, from this change's
delta specs. **This file is not an OpenSpec-schema artifact** — it will not
appear among `openspec instructions apply`'s context files and must be read on
purpose before implementing. It is referenced from the library's own
`rules/` fragment that directs it be read before implementation, and from the
dispatch report accompanying this pass.

Both delta specs in this change (`specs/health-check/spec.md`,
`specs/deploy-pipeline/spec.md`) carry only `## ADDED Requirements` — this is
the first change in this repository to introduce product-facing specs, and
`openspec/specs/` is empty. There is no `MODIFIED`/`REMOVED`/`RENAMED` delta
to compare against, so no implementation was read to derive any of this.

## Baseline

**Full baseline taken** before writing any test: `uv run pytest -q` →
`3 passed in 0.01s` (the three tier placeholders: `tests/unit/test_placeholder.py`,
`tests/agents/test_placeholder.py`, `tests/integration/test_placeholder.py`).

After adding `tests/unit/test_health.py`:
`uv run pytest -q --continue-on-collection-errors` →
`3 passed, 1 error` — the error is a collection-time `ModuleNotFoundError: No
module named 'fastapi'` at `tests/unit/test_health.py:23` (`from
fastapi.testclient import TestClient`). This is the expected **absent-target**
failure state (state 2, per `ai-toolkit:testing`): neither FastAPI nor
`src/commerce_ops/` exist yet (tasks.md section 1 has not been implemented).
It establishes only that the target is absent — nothing about whether the
assertions in the new test are correct — and is **not** a regression: the
three pre-existing placeholder tests still pass unchanged. Without
`--continue-on-collection-errors`, plain `uv run pytest` reports `1 error
during collection` and halts before running the other tiers, which is
ordinary pytest collection-error behavior, not evidence of a broken suite.

## Scenario coverage — `health-check` capability

Source: `specs/health-check/spec.md`. Both requirements `ADDED`.

### Requirement: Liveness Endpoint Available

- **Scenario: Health check returns success when the service is running**
  — covered by `tests/unit/test_health.py::test_health_returns_success_when_running`.
  - `assert response.status_code == 200` — **specified** (scenario's THEN
    clause, verbatim).
  - `assert response.headers["content-type"].startswith("application/json")`
    — **derived**: interprets "a JSON body" as a JSON-typed HTTP response;
    no delta-spec text names the `Content-Type` header specifically.
  - `assert isinstance(body, dict)` — **derived**: a JSON *body* is assumed
    to be a JSON object rather than e.g. a bare string or number.
  - `_assert_healthy_response` → `assert body.get("status") == "ok"` —
    **derived, and flagged as an unresolved project question** (see below).
    The scenario requires a body "indicating the service is healthy" but
    pins no schema; neither `tasks.md` nor `design.md` name one either.
    `{"status": "ok"}` was assumed as a common, minimal convention.

### Requirement: Health Check Has No External Dependencies

- **Scenario: Health check succeeds independent of database availability**
  — covered by
  `tests/unit/test_health.py::test_health_succeeds_with_no_database_configured`.
  - Precondition ("no database connection exists or is configured") is
    made explicit by `monkeypatch.delenv`-ing a set of conventional
    Postgres/`DATABASE_URL` env-var names before the request — **derived**:
    this repository has no settings/config module yet, so these exact
    variable names are an assumption about what a future one would
    plausibly use, not a stated contract. Flagged as an unresolved project
    question (see below).
  - `assert response.status_code == 200` and the `_assert_healthy_response`
    check — **specified**, reusing the same successful-response contract as
    the first scenario ("the endpoint SHALL still return the successful
    response described above").

**Scenario count for `health-check`: 2 of 2 accounted for, both covered by a
named test.**

## Scenario coverage — `deploy-pipeline` capability

Source: `specs/deploy-pipeline/spec.md`. All six requirements `ADDED`,
11 scenarios total. Per the dispatch's explicit steer, these describe
GitHub Actions/infrastructure behavior rather than application code; I
exercised the judgment the dispatch invited on which (if any) have a
meaningful automated-pytest equivalent. **None were written.** Every
scenario below is accounted for as uncovered, with its own reason — not
lumped into one blanket reason — because two different kinds of "not
testable" are in play:

- **(A) Pure runtime/infrastructure outcome** — the behavior only exists once
  a real GitHub Actions run executes against real GHCR/Tailscale/host state
  (or a real branch-protection rule), which cannot be observed from a pytest
  process in this repository. These map to `tasks.md`'s own Verification
  section (8.2, running the real workflow; 8.3, manually requesting the
  public URL) as the intended, operational check.
- **(B) In-principle declarative, but the concrete shape is unspecified** — a
  small subset of these requirements (no-secret-access, tailnet-before-SSH
  step ordering, single-SSH-connection, the `concurrency` group) are, in the
  abstract, properties of the workflow YAML's own declared structure once it
  exists, and could be parsed rather than executed (a real PyYAML `6.0.3` is
  present in this project's `.venv` as a transitive dependency, so the tooling
  gap isn't the blocker). What blocks a meaningful test is that neither the
  delta spec nor `tasks.md`/`design.md` pin the workflow's job names, step
  names, or secret names — `tasks.md` 5.5 names only *what* secrets are
  needed ("the deploy SSH private key, the Tailscale OAuth client ID/secret,
  and the deploy host's tailnet address"), never their literal secret names,
  and 3.1 says `.github/workflows/ci.yml` "(or similar)". A structural test
  would have to invent a specific secret/step/job name to search for —
  exactly the kind of unstated constraint `testing`'s derived-assertion
  discipline exists to flag, and one the implementer never agreed to. A test
  built on an invented name would most likely fail for reasons unrelated to
  actual compliance the moment a differently-but-reasonably-named workflow is
  written, which is a false negative, not evidence about the behavior.

| Requirement | Scenario | Reason uncovered |
|---|---|---|
| Pull Request Validation Gate | Pull request with a failing check is blocked | (A) real branch-protection enforcement across a live PR (task 3.2 is a GitHub repo *setting*, not committed config) |
| Pull Request Validation Gate | Validation requires no deploy secret | (B) declarative in principle, but no spec-pinned secret name to assert the absence of |
| Merge to Main Builds and Publishes an Image | Successful merge produces a pulled-able image | (A) requires an actual push to GHCR |
| Deploy Reaches the Host Over a Private Tailnet Using an App-Scoped Key | Deploy job joins the tailnet before SSH | (B) declarative step-ordering in principle, but no spec-pinned step names to locate |
| Deploy Reaches the Host Over a Private Tailnet Using an App-Scoped Key | Deploy key is scoped to this application only | (A) property of SSH key material and `authorized_keys` binding provisioned in the sibling `/infrastructure` repo — outside this repo entirely |
| Deploy Reaches the Host Over a Private Tailnet Using an App-Scoped Key | Deploy uses exactly one SSH connection | (B) declarative in principle, but no spec-pinned step/job names to count against |
| Deploy Delivers the Compose File and Triggers the Host-Side Deploy Script | Deploy step updates the running container | (A) requires actual host container state after a real deploy |
| Deploy Delivers the Compose File and Triggers the Host-Side Deploy Script | Image tag reaches the host without being committed | (A) "generated fresh for that run" is a runtime property; the adjacent, weaker claim "not committed to the repository" could be checked via git-tracked-file inspection, but doing so tests repo hygiene, not this scenario's actual WHEN/THEN, so no test was written for it either — recorded as deliberately untested rather than approximated |
| Deploy Is Verified by Checking the Health Endpoint | Deploy run fails if the health check does not succeed | (A) requires a live workflow run against a live host |
| Deploy Is Verified by Checking the Health Endpoint | Deploy run succeeds only once the health check passes | (A) requires a live workflow run against a live host |
| Serialized Deploys | Two merges in quick succession deploy in order | (A) the actual queueing behavior across two live runs is runtime; the declared `concurrency:` block itself is (B)-shaped but again has no spec-pinned key name to assert |

**Scenario count for `deploy-pipeline`: 11 of 11 accounted for, all
uncovered with a stated reason (A or B per scenario above); 0 covered by a
test.**

## Total scenario count

2 (`health-check`) + 11 (`deploy-pipeline`) = **13 scenarios**, all 13
accounted for above (2 covered, 11 uncovered-with-reason).

## Obsolete tests

**Not applicable.** Both delta specs in this change are `ADDED`-only; there
is no `MODIFIED` or `REMOVED` delta to supersede any existing test's basis
against. (For completeness: a search of the dispatched test-path glob,
`tests/**/test_*.py`, for anything already bearing on health-check or
deploy-pipeline behavior found only the three generic tier placeholders —
`tests/unit/test_placeholder.py`, `tests/agents/test_placeholder.py`,
`tests/integration/test_placeholder.py` — none of which assert anything
about this change's behavior. No earlier `test-manifest.md` path was
supplied to this dispatch to draw on either.)

## Unresolved project questions

1. **Exact JSON schema of the `GET /health` success body.** The delta spec
   requires "a JSON body indicating the service is healthy" without naming a
   schema, and no planning artifact (`proposal.md`, `design.md`, `tasks.md`)
   pins one either. **Assumption taken:** `{"status": "ok"}`. **Tests
   depending on it:** both tests in `tests/unit/test_health.py`, via the
   shared `_assert_healthy_response` helper. If implementation settles on a
   different shape, that assertion (an explicitly labeled *derived*
   assertion, not a *specified* one) is the one to revisit — not a reason to
   weaken or delete the surrounding test.
2. **Conventional env-var names for "no database configured."** No
   settings/config module exists yet in this repository, so there is no
   stated contract for what env vars a future Postgres configuration would
   read. **Assumption taken:** `DATABASE_URL`, `POSTGRES_HOST`,
   `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
   **Test depending on it:**
   `test_health_succeeds_with_no_database_configured`. This project's
   `AGENTS.md`/`CLAUDE.md` record no convention answering either of these
   two questions, so per the testing floor's non-interactive discharge rule,
   both are recorded here rather than assumed silently.
3. **No skill matched this stack precisely.** `python` (general Python
   traps/pytest idiom) was loaded and applied; no more specific skill for
   FastAPI/`TestClient` testing exists in this library's roster. Recorded
   per the dispatch contract's instruction to note the absence rather than
   stall or load a near-miss.

## Additive-only confirmation

This pass added one file, `tests/unit/test_health.py`, inside the dispatched
test-path glob (`tests/**/test_*.py`), plus this manifest at
`<changeRoot>/test-manifest.md`. No existing test was edited, deleted, or
disabled. No implementation code, dependency, or configuration file (e.g.
`pyproject.toml`, `.github/workflows/`) was created or modified — including
where the code under test does not yet exist, per the testing floor's
absent-target rule.
