## Why

The test suite is **162,335 lines against 23,629 lines of source** — a ratio of roughly 7:1 — and almost none of it is shared. There are 272 test files and **four** `conftest.py` files, two of which exist only for the Slack listener-draining wrapper and one of which is the blanket-skip fixture `restore-the-skipped-unit-tests` deletes.

So each test file builds the world from scratch. Eleven files define their own `_FakeSession`. Twenty-nine define a `_world`, a `_FakeSession`, a `_RecordingSlackApi` or a `_StubPlaybook` of their own. Individual unit-test files reach 2,535 lines (`test_clickup_field_configuration_check.py`), 2,367 (`test_launch_admin_list.py`), 2,345 (`test_automation_pass_repeat_backoff.py`).

This is not a style complaint. It has already caused a concrete failure, twice over, in the last week.

**It converted one signature change into a 24-test outage.** `thread-launch-slack-notifications` gave `run_automation_pass` a required keyword-only `establish_thread`. Exactly one harness needed updating — `_run_pass` in `test_automation_pass_repeat_backoff.py:1146-1183` — and because that harness is 2,345 lines into a file nobody wanted to open, the cheaper-looking move was to skip the file. Every test in it stopped running, and the reason recorded against them was untrue. `restore-the-skipped-unit-tests` fixes that instance; nothing prevents the next one, and the next signature change will meet the same 2,345 lines.

**It makes doubles incomplete, and incomplete doubles have leaked into production code.** When each file writes its own stand-in, each writes the minimum that file needs. Production code then grows tolerances for the shortfall, and says so:

- `gate_progression_job.py:256` — *"Whatever `crossed` the cascade reported, tolerating a caller's fake that models less than the real `LaunchProgressed` does"*
- `gate_progression_job.py:266` — `_awaiting_gate` probes `("awaiting_gate", "gate_id", "current_gate")` for one value
- `clickup_sync.py:128-136` — `_roster_people` probes three shapes for one reader
- `automated_decisions.py:86-90` — *"three spellings"* for one person lookup
- `playbook_authoring.py:243-253` — `person_identifier` probes `("identifier", "id", "person_id")`

`automation_pass.py` alone carries 35 `: Any` annotations and 13 `getattr` probes, under `mypy strict = true`. Strict mode is satisfied nominally and buys nothing where the types are `Any`, and the reason the types are `Any` is partly the boundary (`.importlinter` forbids naming catalog's types) and partly that a `Protocol` would fail against the doubles as written. `unify-launch-adapter-dependencies` proposes typing the boundary collaborators as protocols and explicitly cannot delete these tolerances, because deleting a tolerance is only safe once the doubles it tolerates are complete. This change is what makes them complete.

**It is the tax on every future change.** Each of the seven other changes proposed alongside this one lists test files as its largest surface area. That will keep being true.

## What Changes

- **A `tests/support/` package holding the builders every tier already writes by hand**: a launch, a step definition, a playbook, a product, a roster person; one fake session; one recording Slack API; one recording ClickUp client. Named and typed against the real thing, so a double that stops matching its subject fails at the seam rather than being absorbed by a `getattr` in production code.
- **The builders are complete by construction, not minimal.** A `_world` that models `LaunchProgressed` fully is what allows `gate_progression_job._crossed` to read one attribute instead of three. Completeness is the point of the exercise; a builder that models only what its first caller needed reproduces the problem in one file instead of twenty-nine.
- **Migration is incremental and per-file, not a rewrite.** `design.md` fixes the order and the stopping rule. The files that pay most, first: the six over 1,800 lines, and the ones whose harnesses broke this week. A file is migrated when its own tests are unchanged in what they assert and shorter in how they arrange it — a migration that changes an assertion is not a migration and must be raised as a finding instead.
- **The rule for new tests is recorded** in `AGENTS.md`'s Testing Strategy section, alongside the tier definitions it already carries: a new test uses the shared builders, and a new bespoke fake is a signal that a builder is missing rather than a licence to write a twelfth `_FakeSession`.
- Explicitly **not** in scope: deleting or weakening any assertion; changing which tier any test runs in; reducing the number of tests; `tests/integration/conftest.py`, whose 283 lines of database resolution are genuinely shared already and work; the `slack_asgi_app` draining wrapper, which is correct and merely duplicated between two conftests and can be hoisted as part of this or not at all.
- Explicitly **not** in scope: removing the production-code tolerances the incomplete doubles caused. This change makes that removal safe; performing it belongs with `unify-launch-adapter-dependencies`, where the types those tolerances stand in for are being defined. Doing both here would mean editing `src/` inside a change whose whole claim is that it does not.
- Explicitly **not** a goal: reducing the line count for its own sake. Some of the 162k lines are long because the behaviour is subtle and the docstrings carry the reasoning, which is this project's convention and is worth keeping. What is being removed is arrangement, not explanation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/` and `AGENTS.md`. Every requirement the suite covers is unchanged and every test must still assert exactly what it asserts today — that is the acceptance criterion, not an aside. `.openspec.yaml` therefore sets `skip_specs: true`, following `isolate-tests-from-the-shared-runner` (2026-08-25), the nearest precedent for a change wholly inside `tests/`.

## Impact

- **New**: `tests/support/` — builders, fakes, and the protocols they satisfy.
- **Reduced**: the eleven files defining `_FakeSession`, and the twenty-nine defining a bespoke `_world` / `_RecordingSlackApi` / `_StubPlaybook`. The six files over 1,800 lines are where the change is felt.
- `tests/unit/launch/infrastructure/driving/conftest.py` and `tests/unit/omni_agent/infrastructure/driving/conftest.py` — the duplicated `_DrainsDeferredListeners` wrapper, if `design.md` hoists it.
- `AGENTS.md` — Testing Strategy gains the rule for new tests.
- **Ordering against the other proposed changes.** This one touches nearly every test file and will conflict with anything else editing tests. `restore-the-skipped-unit-tests` should land **first** — it is small, it is urgent, and migrating a file that is currently skipped would mean migrating a file nobody has seen run. Everything else should land before this or well after it, not alongside.
- No change to `src/`, to the schema, to CI configuration, or to any deployed behaviour. The commit-time gate runs the same tests and should not get slower; if it gets meaningfully faster, that is a bonus and not a claim being made here.
