## Why

commerce-ops has been initialized (git, OpenSpec, workflow conventions) but has no recorded identity, scope, or technical direction. This change establishes that foundation once, before normal feature development begins, per `rules/project-foundation.md`.

## What Changes

- Record the project's identity (what it is, the problem it solves, its audience), initial scope, and non-goals.
- Record the technology stack (Python, FastAPI, LangGraph, Slack Bolt/Web API, Postgres), architecture (modular monolith with DDD-bounded domain modules, a ports-and-adapters layering inside each, a marketplace-adapter layer, and Slack as a first-class conversational, notification, and approval interface alongside the HTTP API), testing strategy (pytest, mocked LLM agent tests), and development tooling (uv, ruff, mypy).
- Extend `.gitignore` with Python/uv-stack exclusions, since this is the first point the stack is known.
- Write the identity/scope/non-goals/technology/architecture decisions into `README.md` (create it) and the testing-strategy/development-tooling decisions into a new, unmanaged section of `AGENTS.md`.

This change is exempt from the workflow's test-authoring step: the test command and test-path glob it defines are outputs of this change, not inputs available before it runs.

## Capabilities

This change establishes project foundation (identity, scope, technology, architecture, testing strategy, tooling) rather than system behavior. No spec deltas apply; `skip_specs: true` is set in this change's `.openspec.yaml`.

### New Capabilities

None.

### Modified Capabilities

None.

## Impact

- New: `README.md` at repo root.
- Modified: `AGENTS.md` (new unmanaged section), `.gitignore` (Python/uv exclusions).
- No code yet — this change records decisions that later changes (e.g. the first domain module) will build on.
