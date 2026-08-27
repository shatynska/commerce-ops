## 1. The probe

- [x] 1.1 Change the `Dockerfile`'s `HEALTHCHECK` start period from `5s` to `60s`, leaving `--interval=10s`, `--timeout=3s`, `--retries=3` and the probe command exactly as they are.
- [x] 1.2 Extend the comment above the `HEALTHCHECK` so it explains the *timing* as well as the command choice: what the window is for, that the chain below it is what consumes it, that it is sized against the deploy's own start-to-healthy figure, and that a step added to that chain obliges someone to re-read that figure. Today the comment argues only why the probe calls the venv's interpreter directly.

## 2. The guard

- [x] 2.1 Add a text-level test asserting the `Dockerfile`'s `HEALTHCHECK` declares a start period of at least 60 seconds, following `tests/unit/test_dockerfile_runtime_sync.py` — same way of locating the repository root, same explicit docstring about what a text-level guard does and does not establish.
- [x] 2.2 Add a text-level test asserting the probe's interval is 10 seconds and its retry count is 3, which the delta now fixes as the steady-state contract — so that a future edit cannot buy start-up tolerance out of the liveness signal, the trade `design.md` — Decisions rejects.
- [x] 2.3 Write `openspec/changes/let-the-start-chain-finish/test-manifest.md`, mapping each scenario in the delta spec to its test. Record plainly which scenarios no test in this repository covers and why: no pytest tier here has a built image, so *A chain slower than the probe's failure budget still deploys*, *A start that never completes still fails the deploy*, *A restarted container is granted the window again* and *The declared window clears the measured interval* are verified by the deploy and by Docker's own semantics, not by pytest.

## 3. Records

- [x] 3.1 Record in `docs/deferred-work.md` that the start chain takes ~25s on the host against 1.8s locally, with the per-step local figures, the note that this is what made one added process enough to break the deploy, and the fact that the chain's own duration on the host has never been measured — only the start-to-healthy interval that bounds it.
- [x] 3.2 Record in `docs/deferred-work.md` that `seed_playbook` and `check_step_handlers` emit no `INFO` records in production: run as `python -m`, their module logger is `__main__`, which sits under root at `WARNING` rather than under `commerce_ops` at `INFO`. `ERROR` records are unaffected. Name it as a defect awaiting its own change, not as something this change fixes.

## 4. Verification

- [x] 4.1 Run `uv run pytest tests/unit tests/agents`, `ruff check`, `ruff format --check`, `mypy` and `lint-imports`.
- [x] 4.2 Run `openspec validate let-the-start-chain-finish --strict`.
- [x] 4.3 Confirm by inspection that `docker-compose.yml`, `.github/workflows/deploy.yml` and every file under `src/` are untouched by this change.
- [ ] 4.4 After merge, read `Started` → `Healthy` out of the deploy run's log and record it in the `docs/deferred-work.md` entry from 3.1, per `design.md` — Migration Plan. The delta requires the window to exceed that reading by at least two probe intervals, so a reading at or below 40s leaves the shipped 60s compliant; above 40s means the window must grow and a follow-up change is owed. Expect ~36.5s on a pre-25.0 Docker engine, or nearer ~30s on 25.0+ where a 5s start-interval applies by default — both are correct results, not anomalies. See `design.md` — Migration Plan.
