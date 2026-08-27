## 1. Narrow the use cases' roster collaborator

- [ ] 1.1 Import `RosterReader` and `UnreadableRosterError` into `launch/application/automated_decisions.py` from its sibling `playbook_authoring` (design.md — Decision 2). Do not redefine either, and do not import `clickup_sync`'s `RosterReader`, which is `Any`.
- [ ] 1.2 Replace `_person_for`'s three-spelling probe with a single `list_people()` read, raising `UnreadableRosterError` — naming the type supplied and the shape expected — when the collaborator does not answer it. Never returned as a `Decision`.
- [ ] 1.3 Leave the roster read where it is, after `results.pending_for`: "before the deciding identity is judged" means the shape check does not move ahead of the already-settled lookup, so a repeat press on a settled result keeps answering "already decided" even on a mis-wired deployment. State this in the function, since it is observable and a reader would otherwise reorder it.
- [ ] 1.4 Keep the "known" and "active" halves as two distinct refusals evaluated in `launch` over the full roster, deactivated entries included (design.md — Decision 2). The existing refusal wording for both is unchanged.
- [ ] 1.5 Type the `roster` parameter of `accept_automated_result` and `reject_automated_result` as `RosterReader`, replacing `Any`.
- [ ] 1.6 Export `RosterReader` and `UnreadableRosterError` from `launch/application/__init__.py`, adding both to `__all__` (design.md — Decision 2). The infrastructure adapter may reach them no other way, and task 2.1 puts `RosterReader` in its declared type.

## 2. Wire the adapter and type the injection point

- [ ] 2.1 Declare `automation_confirmation.read_people` as `RosterReader | None = None` and update the comment above it to say a reader is expected, not "the same one the admin pages get" (design.md — Decision 3).
- [ ] 2.2 Narrow `_roster_or_fail` to return `RosterReader`, and change the error it raises for the pre-injection window from `RuntimeError` to `UnreadableRosterError`, preserving its message (design.md — Decision 4). Without this the un-injected deployment escapes task 3.1's catch and answers the decider with silence.
- [ ] 2.3 In `main.py`, define a roster reader over `access`'s public `list_people`, shaped like `worker.py._RosterReader`, and inject it at the site that currently assigns `roster` directly (design.md — Decision 1). Record in its docstring why the near-duplicate with `worker.py` is deliberate.
- [ ] 2.4 Have that reader resolve the module-level `roster` global inside `list_people()`, not capture it at construction — otherwise the store is bound before any test can reach it and task 4.5's seam does not exist. Note this differs from `worker.py._RosterReader`, which constructs a fresh `PostgresRoster()` per call and so has no global to resolve; `main.py` already holds one at line 77 and the reader should use it.
- [ ] 2.5 Confirm `uv run mypy` reports nothing — and, as a one-off check before 2.3 lands, that reverting 2.3's injection to the bare store makes mypy fail at that line with `[assignment]`. That failure is the guarantee decision 3 buys; if it does not appear, the type is wrong.

## 3. Answer a mis-wiring without blaming the decider

- [ ] 3.1 In `_handle_decision`, catch `UnreadableRosterError` by its own type — never a bare `except Exception` — log it at `exception` level, and return a sentence saying the decision could not be processed and the fault has been reported. After task 2.2 this one catch covers both wiring faults, the mis-shaped collaborator and the absent one.
- [ ] 3.2 Verify that sentence contains no clause about the decider's identity, roster entry or authority, and that it is distinguishable from every `Decision.reason` a genuine refusal produces.
- [ ] 3.3 Leave both Bolt listeners' `ack()`-first ordering untouched: a mis-wired deployment must still acknowledge within Slack's timeout.
- [ ] 3.4 Confirm no wiring fault can now leave the listener without calling `respond` — the failure mode design.md Decision 4 forbids, and the one the pre-change `RuntimeError` produced.

## 4. Tests

- [ ] 4.1 Dispatch `ai-toolkit:openspec-test-writer` against this change's delta spec before any of groups 1–3 are applied, per `AGENTS.md`. Every scenario under the modified requirement is its input — the two carried over unchanged included, since the double they run against is narrowed by 4.2.
- [ ] 4.2 Narrow `_FakeRoster` in `tests/unit/launch/application/test_automated_result_decisions.py` to `list_people` alone, and update that file's header note, which currently records answering-to-everything as deliberate (design.md — Decision 5). Change no assertion and no test subject.
- [ ] 4.3 Add a `RosterStore`-shaped double — `load`/`save` only — for the mis-shaped-collaborator scenarios, and cover the absent-collaborator scenario with no collaborator at all.
- [ ] 4.4 Cover the positive seam scenario by importing `commerce_ops.main` and driving a decision through `automation_confirmation.read_people` **as injected**, asserting a roster person is resolved (design.md — Decision 6). Do not rebuild the reader: a double of the right shape passes at the moment `main.py` regresses, which is how this fault shipped. Precedent for importing `main` in the unit tier without a database: `tests/unit/launch/infrastructure/driving/test_main_monitoring_wiring.py`.
- [ ] 4.5 Substitute at the **store** — `commerce_ops.main.roster` — and nowhere lower. Substituting `commerce_ops.main.list_people` replaces the reader's entire body, so a reader closed over the wrong store, or over nothing, would still pass; that is the same escape 4.4 exists to close, one level down. Leaving the reader's call into `access`'s real `list_people` intact is what makes the assertion about the wiring rather than about the stub.
- [ ] 4.6 Cover the adapter's behaviour from group 3: the reply each wiring fault produces, that both produce the same one, and that the fault is logged.

## 5. Verification

- [ ] 5.1 Run `uv run pytest` across `tests/unit` and `tests/agents`; the pre-commit hook runs the whole tree, so an unrelated red test blocks the commit.
- [ ] 5.2 Run `uv run mypy`, `uv run ruff check`, `uv run ruff format --check` and the `import-linter` contracts — the last because group 2 touches a module the roster-boundary contracts govern.
- [ ] 5.3 Confirm against a live deployment that a pending result already sitting in Slack becomes decidable on the existing message, without re-delivery (design.md — Migration Plan).

## 6. Archive

- [ ] 6.1 Dispatch `ai-toolkit:openspec-change-reviewer` and address its findings before implementing; re-dispatch until approved.
- [ ] 6.2 `openspec archive restore-automated-decisions --yes` as the last commit before the merge, per `AGENTS.md`.
