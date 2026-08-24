## 1. Pre-authoring check

- [ ] 1.1 Confirm ClickUp's actual task-name limit and record it. Today's worst composed name is 225 characters (`lp.listing.019`); the worst across all 358 reference rows is 271 (`lp.strategy.023`), so the shortening rule in the `launch-clickup-sync` delta applies to future authoring whatever the limit proves to be. Record the confirmed number in design.md Decision 4, and express it in `clickup_sync.py` as a named constant rather than a bare literal.

## 2. The field

- [ ] 2.1 Add the required `description` to `StepDefinition` in `launch/domain/launch_playbook.py`, and add the load-time coherence faults for an **empty** description and for one spanning more than one line, named per step, alongside the existing step faults. An absent key is not observable here — a required dataclass field cannot be missing — so that case belongs to the loader, in 2.2.
- [ ] 2.2 Read the new key in `playbook_loader.py` without defaulting it, and make an absent key surface as a per-step fault naming the step. Note that the loader currently catches only `InvalidPlaybookError` and `ValueError` around `_build_step_definition`, so a missing key raises an uncaught `KeyError` and aborts the whole load unnamed — that path must be closed for the delta's "rejected by name" scenario to hold, and it protects every other required key too.
- [ ] 2.3 Give each per-file `_step(**overrides)` test factory a default description so existing tests construct a valid step (roughly sixteen files; a one-line default each). Also update the loader-level fixtures that supply a step as a raw mapping rather than through the dataclass — `_TWO_FAULTY_STEPS_YAML` in `tests/unit/launch/infrastructure/test_playbook_loader.py` and the raw playbook text in `tests/unit/launch/application/test_report_undecided_rule_policies.py` — which would otherwise fail on the new required key for reasons unrelated to what they assert. Do not weaken any existing assertion to accommodate the new field.

## 3. The descriptions

- [ ] 3.1 Extract each shipped step's description from its reference row in `docs/reference/product-launch.md` — the text line above the row's metadata line — applying the trimming rule in design.md Decision 3 (trailing whitespace, then any trailing `;` `:` `,` `.`, repeating; nothing else stripped — a closing quote, parenthesis or `+` is content and stays).
- [ ] 3.2 Author the 97 descriptions into `playbook_v1.yaml`, and update the file's header comment to record that a step now states its own work.
- [ ] 3.3 Load the shipped playbook once through the existing loader and resolve any coherence faults the authoring introduced.

## 4. The task name

- [ ] 4.1 Compose `_task_name` in `clickup_sync.py` as the step's description followed by ` · ` and its identifier, dropping the discipline per design.md Decision 4.
- [ ] 4.2 Shorten a composed name that would exceed the limit recorded in 1.1, preserving the identifier, and pass the step's full description as the created task's body. Set the name at creation only — do not add any pass that rewrites an existing task's name (design.md Decision 5).

## 5. Tests

- [ ] 5.1 Add unit tests for the new specified behaviour: a step definition reads back its description; a playbook declaring an empty description, one omitting it entirely, and one whose description contains a line break are each rejected with a fault naming the step and aggregated alongside other faults; every shipped step's description re-derives exactly from the text of the reference row its identifier names, reduced by the trimming rule in design.md Decision 3 (not a raw-text comparison — roughly 17 rows are trimmed, and a raw comparison would fail on them and invite weakening the assertion); a projected task is named description-then-identifier; a mapped task whose name was edited in ClickUp still resolves to its step and is not duplicated; an edited name is not restored when the step's description has changed; an over-long composed name is shortened with the identifier preserved and the full description carried in the task body.

## 6. Verification and record

- [ ] 6.1 Run `uv run pytest tests/unit tests/agents`, mypy, ruff, and import-linter; run `tests/integration` before push.
- [ ] 6.2 Update `docs/domain-map.md`: add the description to the `StepDefinition` attribute list, and record that a projected ClickUp task is named from it while the step-to-task association remains the recorded mapping, never the name.
