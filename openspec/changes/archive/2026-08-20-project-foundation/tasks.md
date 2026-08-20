## 1. README.md

- [x] 1.1 Create `README.md` with an `<!-- ai-toolkit:project-foundation -->` / `<!-- /ai-toolkit:project-foundation -->` delimited section.
- [x] 1.2 Within it, add `## What it is`, `## Problem`, `## Audience`, `## Scope`, `## Non-Goals`, `## Technology`, `## Architecture`, populated from design.md's Identity, Scope, Non-Goals, Technology, and Architecture sections.

## 2. AGENTS.md

- [x] 2.1 Append a new, separate, unmanaged section to `AGENTS.md` (outside the existing `<!-- ai-toolkit:development-workflow v1 -->` block), delimited with `<!-- ai-toolkit:project-foundation -->` / `<!-- /ai-toolkit:project-foundation -->`.
- [x] 2.2 Within it, add `## Testing Strategy` and `## Development Tooling`, populated from design.md's Testing Strategy and Development Tooling sections (including the test command and test-path glob).

## 3. Development tooling deliverable

- [x] 3.1 Extend `.gitignore` with Python/uv-stack exclusions: `__pycache__/`, `*.pyc`, `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `build/`, `.env`. Do **not** ignore `uv.lock` — it is committed for reproducible installs, per standard `uv` practice.

## 4. Close out

- [x] 4.1 Verify every design.md section is filled (no placeholder text remains).
- [x] 4.2 Note: this change is exempt from test authoring — the test command and test-path glob it defines (`uv run pytest`, `tests/**/test_*.py`) are outputs of this change, not inputs available before it. No tests are written as part of this change.
- [x] 4.3 Archive this change once the above are complete, marking foundation as established.
