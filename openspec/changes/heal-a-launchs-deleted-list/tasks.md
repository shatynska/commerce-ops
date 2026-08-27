## 1. Read a list's own state from ClickUp

- [ ] 1.1 Add a read of a single list to `shared/infrastructure/driven/clickup_client.py`, returning whether ClickUp reports the list as deleted. The client has no such call today; `create_list` and `list_tasks` are the shapes to follow.
- [ ] 1.2 Let a non-successful response and an unreachable ClickUp both propagate, per `design.md` — Decision 4, so a `404` is never returned as "deleted". The client's no-suppression requirement covers this read as it covers the other four.

## 2. Replace a list and its mappings in one transaction

- [ ] 2.1 Add one operation to `launch/infrastructure/driven/clickup_mapping.py` that records a new list identifier for a launch **and** deletes that launch's task mappings in a single commit (`design.md` — Decision 3). Do not build it as two calls: every existing method on the repository commits for itself.
- [ ] 2.2 Exempt the mappings of playbook-defined steps whose recorded outcome settles work, so finished work is not re-projected (`design.md` — Decisions 2a, 2b). The caller evaluates this against `playbook.authored_steps` — not `served_steps`, not the projectable subset — and hands the store the mappings to spare. Judge it hazard-independently, as `automation_pass.py:404` does, not through `_is_terminal`: a hazard re-authored after the outcome was recorded must not unfinish the work. The store must not judge it at all — that needs the step definition, which the mapping repository has no business holding.
- [ ] 2.3 Discard the mapping of any step the playbook no longer defines, along with the rest. This branch is defensive: `playbook-authoring` forbids deleting a step, and a retired step is still authored, so only a pre-Postgres mapping or an unsanctioned edit reaches it.
- [ ] 2.4 Confirm the operation leaves nothing half-done when the transaction fails — the launch stays recorded against its old list with its mappings intact.

## 3. Verify the list before using it

- [ ] 3.1 In `_ensure_list` (`launch/infrastructure/driven/clickup_sync.py`), read the list's state from ClickUp before returning a recorded identifier, unconditionally and once per pass (`design.md` — Decision 1). Do not add a second probe in `reconcile_launch`, which reads the same recorded list.
- [ ] 3.2 Pass the playbook (or the exempt set computed from it) into `_ensure_list`, which today carries no playbook and carries a `steps` parameter its body never reads — replace that dead argument rather than adding a sixth. Where ClickUp reports the list deleted, mint a replacement in the configured folder and record it through the operation from 2.1. Where no parent folder is configured, the launch fails the way one needing a list already does, rather than returning its dead identifier — the probe must sit so that path is still reached.
- [ ] 3.3 Leave the graduated short-circuit ahead of the check, so a graduated launch's list is never read.
- [ ] 3.4 Leave `converge_launch`'s loop untouched, including the terminal guard at `clickup_sync.py:537`. Re-projection already works from an empty list read; the discard is not what drives it, and the spec forbids relying on it that way.

## 4. Verify against the specification

- [ ] 4.1 Run the tests derived from both delta specs and confirm each scenario is observed — in particular *Finished work is not re-projected into the replacement list*, *Finished work of a step the launch is not held to survives the replacement*, *A mapping for an undefined step is discarded*, *A list whose state cannot be established is not healed*, and *The replacement and the discard cannot come apart*.
- [ ] 4.2 Confirm the client's new read is exercised without reaching the live API, including its failure scenarios.
- [ ] 4.3 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the unit + agents tier; run the integration tier before pushing.

## 5. Confirm against the deployment

- [ ] 5.1 After merge and deploy, confirm `TestProductName0` receives a list and its steps project into it.
- [ ] 5.2 Confirm `launch.clickup.completion_pass` records a success, moving `last_success` off `07:20:00Z` — the measurement `proposal.md` opens on, and the evidence the launch converged rather than being walked past.
- [ ] 5.3 Confirm the replacement list's name carries the bare SKU, not the value object's repr — PR #81 ships that fix ahead of this change, and this launch's list is the only creation left to prove it on.
- [ ] 5.4 Confirm no task was created for any step of that launch whose outcome was already recorded terminal.
