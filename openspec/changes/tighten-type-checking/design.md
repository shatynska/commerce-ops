## Context

See proposal.md — Why, for the defect and the measured fallout. Constraints that shape the approach:

- `mypy` is invoked as `uv run mypy .` from two places (`.pre-commit-config.yaml`'s `mypy` hook and `.github/workflows/ci.yml`'s `mypy` step). Neither passes flags, so all configuration must live in `pyproject.toml` to apply in both.
- The tree has no untyped third-party stubs problem today: `types-PyYAML` is already a dev dependency, and `mypy --strict` reports no `import-untyped` errors — so no `ignore_missing_imports` escape hatch is needed as part of this change.
- Two deliberate, currently-effective `# type: ignore`s exist in `src/` and `strict` leaves both alone: `settings.py`'s `call-arg` on `Settings()` (with a comment explaining that `BaseSettings` populates its fields from the environment, so passing them as keyword arguments would defeat the model), and `playbook_loader.py:129`'s `arg-type` (an error code already reported in default mode, so `warn_unused_ignores` has no quarrel with it).
- `tests/unit/shared/application/test_settings.py:411–419` carries a nine-line comment whose only purpose is explaining the four ignores at lines 420–423. It asserts mypy reports those errors; the measurement says it does not. Whichever way that resolves, the comment and the ignores stand or fall together.

## Goals / Non-Goals

**Goals:**

- Unannotated function bodies are checked.
- Existing annotations are enforced rather than decorative.
- The gate's report matches what it actually verified.

**Non-Goals:**

- **Adding annotations to unannotated code.** There is almost none — `strict`'s `disallow_untyped_defs` produced zero errors on this tree, because every function is already annotated. This change turns on enforcement; it is not an annotation campaign.
- **Deciding what `answer_question` returns for non-string message content.** Held with a scoped ignore and split into its own change — see Decisions.
- **Filling `pyproject.toml`'s placeholder `description`.** Noticed while editing that file, and unrelated to type checking. Per AGENTS.md's scope rule it becomes separate work rather than riding along.
- **Enabling the pydantic mypy plugin.** See Decisions.
- **Type-checking coverage metrics or a ratchet.** With 10 errors total, a ratchet is machinery for a problem that does not exist. Fix them and turn the gate on.
- **Changing how or where mypy is invoked.** Both call sites stay as they are.

## Decisions

### `strict = true`, rather than enumerating individual flags

`strict` is a moving set — it gains checks as mypy versions advance, which is the desired direction for a gate whose purpose is to catch what the author did not think to check. Enumerating today's flags would pin the gate to today's understanding and require a deliberate edit to ever benefit from a new check.

The usual argument against `strict` is that a version bump can break the build on code that did not change. That argument is weak here: `mypy` is pinned `>=2.3.1` in a committed `uv.lock`, so a new check arrives only when the lockfile is deliberately updated, in a change that can absorb the fallout.

**Alternative considered — a graduated subset** (`check_untyped_defs` and `disallow_untyped_defs` only). This was the expected recommendation before the fallout was measured; it exists to make a large migration affordable in stages. With 10 mechanical errors there is no migration to stage, and the graduated option's only lasting effect would be leaving the remaining strict checks permanently off with no record of why.

### The `comparison-overlap` finding gets a narrow ignore, not a rewrite or a deletion

`test_the_two_opening_modes_are_distinct` asserts `GateOpening.REQUIRES_CONFIRMATION is not GateOpening.AUTOMATIC`. mypy is right that this is statically decidable *given the enum as it is defined today* — and that is precisely the property the test guards. Its docstring says so: the two scenarios above it "would both pass if `GateOpening` collapsed to a single value."

So the assertion is a tautology under the current definition and a genuine failure under the change it guards against. Deleting it would remove a guard because a type checker observed that the guard currently holds. It gets `# type: ignore[comparison-overlap]` — error-code-scoped, so any other typing fault on that line still surfaces — with a comment recording that the tautology is the point.

This is one of two judgment calls in the change — the other is the decision immediately below, to hold `use_cases.py:27` rather than fix it. The remaining eight findings are mechanical.

### The `Any` return in `use_cases.py` is held with a scoped ignore, and split into its own change

`answer_question` ends with `return result["messages"][-1].content`, which LangChain types as `Any`, in a function declared `-> str`. `strict`'s `warn_return_any` flags it correctly: nothing establishes that the value is a `str`, and LangChain's message content can be a list of content blocks rather than a string.

This is a real latent defect rather than a typing nuisance — a multimodal or structured response would return a list into a `str`-typed function, and the first symptom would be in Slack. **That is exactly why it is not fixed here.** Fixing it means deciding what the ops team sees when content is not a string, and the two candidate answers are meaningfully different:

- **Raise.** `slack.py:141` catches broadly and posts `_FAILURE_MESSAGE`, so the user sees a failure for a call the model completed successfully. That sits badly against `omni-agent`'s recorded "Model failure is surfaced, not masked", which scopes failure reporting to a failed model call.
- **Coerce** (`str()`, or joining the text blocks). The user sees a serialized structure or a lossy join. Whether that qualifies as "a non-empty response produced by the language model" under `omni-agent`'s "Answer a single question" is not settled by any recorded requirement.

Neither answer follows from the existing specs, so choosing one inside a tooling change would be inventing a requirement — and because this change carries no deltas, the `openspec-test-writer` pass that AGENTS.md requires to derive tests from deltas would never run against it. The decision would be made and tested by the same person from the same assumption, which is the shared blind spot the workflow exists to prevent.

The line therefore gets `# type: ignore[no-any-return]`, error-code-scoped, naming the follow-on change **`specify-non-string-message-content`** — which tasks.md 2.5 requires be proposed before this change is archived, so the comment cites a tracked obligation rather than a dangling name. This is the same instrument the change already uses for `test_playbook_loader.py:219`, and it is honest in a way `cast(str, ...)` would not be: an ignore asserts nothing about the value, while a cast asserts something not known to be true.

A property worth naming, because it makes the deferral self-cleaning rather than a hole: `strict` enables `warn_unused_ignores`. If a later change fixes the return properly and leaves the ignore behind, the gate reports the now-useless ignore. The suppression cannot quietly outlive the problem it suppresses.

**The same property has a sharp edge.** If a LangChain or LangGraph release types `.content` more precisely, the ignore becomes unused and the build fails inside an unrelated dependency bump — where the obvious local fix is to delete the ignore, which silently adopts whatever behavior the new types imply, resolving by accident the product decision this change split out to avoid deciding by accident. The correct response to that failure is to land `specify-non-string-message-content`, not to delete the ignore. Recorded here and in Risks so whoever meets it knows which move is which.

**Alternative considered — resolve it here with a delta on `omni-agent`.** Rejected: it turns a tooling change into a behavioral one, pulls in a test-derivation pass, and delays turning the gate on. The proposal's own argument is that every change written before this one is written under the weaker gate — which argues for landing it sooner, mechanically, not later with a product decision attached.

**Note the defect is latent, not live.** `build_production_graph` pins `ChatOpenAI(model="gpt-4o-mini")` with no multimodal input and no structured output, so `.content` is a `str` in every path exercised today. There is time to specify it properly.

### Not enabling the pydantic mypy plugin

Pydantic ships a mypy plugin that understands generated `__init__` signatures, which would make `settings.py`'s one `# type: ignore[call-arg]` unnecessary. Rejected for now: the plugin changes how every model in the tree is checked, in exchange for removing a single, documented, correctly-scoped ignore comment. That trade is not worth making inside a change whose purpose is to turn on a gate — and the ignore is already the clearer of the two, since it explains itself in place.

## Risks / Trade-offs

- **The measured 10 errors are a snapshot against `main`; other proposed changes may land first and change the count.** → Task 1.1 re-runs `mypy --strict` and works from that output rather than from proposal.md's list. If the count has grown substantially, that is itself information worth reporting before proceeding.
- **`strict` will make future changes cost slightly more to write**, particularly around untyped third-party surfaces like LangChain. → That is the change's purpose, and the `use_cases.py` finding is the argument for it: the cost falls on the author of the risky line rather than on whoever debugs it in Slack.
- **A future `mypy` version bump can surface new errors on unmodified code.** → Bounded by the committed lockfile: it happens only in a deliberate dependency update, where it is in scope.
- **A LangChain/LangGraph bump could make the held ignore unused before its follow-on change lands**, failing the build in an unrelated change whose obvious local fix resolves the deferred product decision by accident. → The correct response is to land `specify-non-string-message-content`, not to delete the ignore; stated in Decisions so the choice is not made under bump-time pressure.
- **The measurement covered the repository root, including `alembic/`** — `uv run mypy .` reaches `alembic/env.py` and the versions directory, both fully annotated, with zero errors there. Recorded so "5 in `src/`, 5 in `tests/`" is not read as leaving a third tree unmeasured, and so future generated migrations are known to be strict-checked.

## Migration Plan

1. Re-run `uv run mypy --strict .` and record the current error list.
2. Fix `src/` errors, then `tests/` errors.
3. Add `[tool.mypy]` with `strict = true` to `pyproject.toml`.
4. Run `uv run mypy .` (no flags, as the hook and CI invoke it) and confirm it now reports what step 1 reported and is clean.
5. Run the full suite. No step touches runtime behavior — that is the property the held `use_cases.py` ignore preserves — so an unchanged suite is the expected result, not a weak signal.

Rollback is reverting the commit. No runtime dependency, schema, or external contract is involved.
