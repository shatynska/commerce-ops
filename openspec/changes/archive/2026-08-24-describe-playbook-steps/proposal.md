## Why

A step definition carries an identifier and a provenance citation, but nothing that says what the work *is*. The reference document's wording — "Main image scroll-stopping, unlike others" — is left behind in `docs/reference/product-launch.md`, which no running code reads. The consequence surfaces where the work actually reaches a person: a projected ClickUp task is named `lp.creative.008 · creative`, so whoever picks it up has to look the code up in a markdown file before they know what they were asked to do.

Now is the moment because `author-playbook-steps` has just made this concrete — 92 tasks per launch will be created under codes — and because no launch has started yet, so no task named the old way exists to migrate.

## What Changes

- **BREAKING** (internal): `StepDefinition` gains a required `description` — the step's work stated in one line. Required rather than optional, because a step nobody can read is the defect this change exists to remove; an optional field would let the gap persist silently.
- All 97 shipped steps carry the description their reference row states, transcribed from the same row the identifier and provenance already point at.
- A projected ClickUp task is named from the step's description with its identifier appended — `Main image scroll-stopping, unlike others · lp.creative.008` — so the list reads as work while a task can still be traced to its step by eye.
- The discipline drops out of the task name. It is recoverable from the identifier's own second segment (`lp.creative.008`), and spending name width on a word already encoded there costs the reader the wording this change exists to surface.
- A task's name is set once, at creation, and never rewritten — unlike its due date, which the system keeps in step with the launch schedule. A person may legitimately retitle a task in their own list, and no pass should undo that.
- A composed name too long for the task system is shortened — the description cut, then `…`, then ` · ` and the identifier in full — with the full description carried in the task's body in that case only — a task whose name fits is created without a body — so no step fails to project because its wording is long. ClickUp's limit was measured at 2048 characters (it rejects rather than truncates), and the longest name the reference document can produce is 271, so this is a guarantee held in reserve rather than a live failure being fixed.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `launch-playbook`: a step definition's declared attributes gain a required description; the shipped playbook's authored set gains the obligation that each step's description states its reference row's work.
- `launch-clickup-sync`: the projected task's name is specified as the step's description followed by its identifier, where the requirement previously said only "a task named for the step"; the name is additionally fixed at creation, and shortened rather than allowed to fail when it exceeds the task system's limit.

## Impact

- `src/commerce_ops/launch/domain/launch_playbook.py` — one field on `StepDefinition`, and a coherence rule rejecting an empty description.
- `src/commerce_ops/launch/infrastructure/driven/playbook_loader.py` — reads the new key.
- `src/commerce_ops/launch/infrastructure/driven/playbook_v1.yaml` — 97 new `description` lines.
- `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py` — `_task_name` composes description and identifier, shortens an over-long name, and passes the full description as the created task's body.
- `src/commerce_ops/launch/infrastructure/driven/playbook_loader.py` also needs its missing-key path closed: a `KeyError` there is currently caught by neither of the loader's two handlers, so an absent key aborts the load without naming the step.
- Tests: roughly sixteen per-file `_step(**overrides)` factories each need a default description, plus the shipped-playbook and task-naming assertions.
- **No data migration.** Task names are cosmetic to the sync, which maps a step to its task by recorded task id and never by name; and `launch_positions` was empty at the earlier check and is re-confirmed by task 1.2 before the YAML is edited. If a launch has started since, its existing tasks keep their old names and the list carries both namings — accepted rather than migrated.
- `docs/domain-map.md` — the `StepDefinition` attribute list is enumerated there and gains the field.
