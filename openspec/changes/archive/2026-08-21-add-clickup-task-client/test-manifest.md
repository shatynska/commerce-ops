# Test manifest: add-clickup-task-client

Written by `openspec-test-writer`, strictly from
`specs/clickup-task-client/spec.md`'s `#### Scenario:` blocks (the change's
only capability, entirely `ADDED` -- no `specsRoot` comparison was needed or
performed). **Not** an OpenSpec-schema artifact: it will not appear among
`openspec instructions apply`'s context files and must be read on purpose
before implementing. See also
`ai-toolkit`'s `rules/test-manifest.md` (this library's own testing rule fragment, which
directs reading this manifest before implementation) -- that fragment's
import path is machine-local, so this pointer, and the one in the dispatch
report, are the two ways to reach it.

Test file: `tests/unit/shared/infrastructure/driven/test_clickup_client.py`
(unit tier -- outbound HTTP is faked via `httpx.MockTransport`; no real I/O).

## Baseline

Full-suite baseline taken before writing any test: `uv run pytest -q` →
**110 passed, 22 skipped, 0 failed** (the 22 skips are
`tests/integration/products/` skipping on absent `DATABASE_URL`, pre-existing
and unrelated to this change). After adding this file:
`uv run pytest -q --continue-on-collection-errors` →
**110 passed, 22 skipped, 1 error** -- the 1 error is this file's own
collection failing on `ModuleNotFoundError:
commerce_ops.shared.domain.clickup`, i.e. the absent implementation target.
Nothing pre-existing regressed.

## Scenario accounting (10 of 10 scenarios covered)

| # | Requirement | Scenario | Test(s) |
|---|---|---|---|
| 1 | A task can be created in a given list | Task created with a name only | `test_create_task_with_name_only` |
| 2 | A task can be created in a given list | Task created with a name and description | `test_create_task_with_name_and_description` |
| 3 | An existing task can be updated with caller-supplied fields | Task updated with one field | `test_update_task_with_one_field` |
| 4 | An existing task can be updated with caller-supplied fields | Task updated with multiple fields | `test_update_task_with_multiple_fields` |
| 5 | An existing task can be updated with caller-supplied fields | Task updated with no fields | `test_update_task_with_no_fields` |
| 6 | A failed ClickUp request is surfaced to the caller | ClickUp rejects a create request | `test_create_task_rejected_by_clickup_raises` |
| 7 | A failed ClickUp request is surfaced to the caller | ClickUp rejects an update request | `test_update_task_rejected_by_clickup_raises` |
| 8 | A failed ClickUp request is surfaced to the caller | ClickUp is unreachable | `test_create_task_when_clickup_is_unreachable_raises` (named path), plus DERIVED extra coverage `test_update_task_when_clickup_is_unreachable_raises` for the update path the same WHEN clause also names |
| 9 | Authentication is configured independently of any one caller | Credential absent until first use | `test_importing_the_module_does_not_require_a_configured_credential` (import half only -- see note below) |
| 10 | Authentication is configured independently of any one caller | Credential absent at call time | `test_create_task_without_a_configured_credential_raises_before_any_request` (named path), plus DERIVED extra coverage `test_update_task_without_a_configured_credential_raises_before_any_request` for the update path |

All 10 `#### Scenario:` blocks in `specs/clickup-task-client/spec.md` are
accounted for above; none are recorded as uncovered.

**Note on scenario 9** ("Credential absent until first use"): its WHEN
clause names two triggers -- "the client module is imported, **or** the
application starts". Only the import half is testable for this change:
`proposal.md`'s Impact section states this change wires up no FastAPI
routes and no `main.py` change ("No consumer is wired up yet ... No FastAPI
routes, no `main.py` wiring"), so there is no application-startup path that
reaches this module yet. This is recorded here rather than silently
dropped; a later change that wires a consumer in should add the
startup-half test then.

**Supplementary, not itself a `#### Scenario:` block** (`tasks.md` 5.6):
`test_clickup_client_module_satisfies_the_writer_port_structurally` --
verifies `ClickUpTaskWriter` structurally accepts the concrete adapter,
mirroring how `ProductRepository`/`ProductNameReader` is verified elsewhere
in this repo (`tests/unit/products/application/test_daily_digest.py`'s
`test_reader_satisfies_the_port_structurally`).

## Assertion classification

- **Specified** (traces directly to a scenario's WHEN/THEN): the outgoing
  request's method, URL path, and JSON body content for each create/update
  scenario; that a `ClickUpTask`-shaped identifier+URL comes back on
  success; that an exception (not a returned value) results from each
  failure scenario; that no request reaches `httpx.AsyncClient.send` when
  the credential is absent at call time; that importing the module with no
  credential configured does not fail.
- **Derived** (inferred, not itself stated by a scenario -- each flagged
  inline in the test file at the point it's asserted):
  - The returned value's type is asserted `isinstance(..., ClickUpTask)`
    (design.md names this type; the spec text itself only says "identifier
    and URL").
  - "An empty body" (scenario 5) is read as an empty JSON object (`{}`),
    the natural encoding of an empty `fields` mapping as this endpoint's
    JSON body -- the spec does not pin the wire encoding of "empty".
  - Every `pytest.raises` is scoped to bare `Exception`, not a specific
    type: no artifact names one (design.md's Risks section names
    `httpx.HTTPStatusError`/`KeyError` as the *expected mechanism*, but
    Risks is not itself a requirement), so narrowing would impose a
    contract nobody agreed to.
  - The two "unreachable"/"credential absent at call time" extra tests
    covering the `update_task` path, beyond the one path each scenario's
    WHEN clause names first, since both scenarios' WHEN clauses name
    "create-task or update-task"/"created or updated" generically and
    `update_task` is an independent code path that could diverge.
- **Deliberately untested**: none within this file's scope -- every
  scenario got at least one test; see the Impact-section note above for
  the one scenario-half left untestable by this change's own boundaries
  (recorded, not silently dropped).

## Names and shapes assumed but not fixed by any artifact (INVENTED)

Recorded in full in the test file's own module docstring; summarized here:

- A module-level `get_client() -> httpx.AsyncClient` cached factory in
  `clickup_client.py` (mirroring `omni_agent/infrastructure/driving/
  slack.py`'s `get_slack_client()`, which design.md explicitly says this
  change's construction "mirrors"). This is the seam the tests substitute
  a `httpx.MockTransport`-backed client through. Tests assert this factory
  exists by name before relying on it (`install_transport`'s `assert
  original is not None`), so a differently-named or differently-shaped
  seam fails loudly and distinguishably rather than silently attempting a
  real network call.
- That the adapter is module-level functions (`create_task`, `update_task`)
  rather than a class -- affects only the structural-compatibility test's
  shape (module object assigned to the `ClickUpTaskWriter`-typed variable,
  vs. an instance).
- Whether `CLICKUP_API_TOKEN` is read inside `get_client()` or inside
  `create_task`/`update_task` themselves -- the "Credential absent at call
  time" tests call the real, unpatched functions specifically so whichever
  path is real gets exercised.

If any of these differ from the real implementation, correcting the
`getattr`/`monkeypatch.setattr` target in the test file is a **fixture
correction** (per `ai-toolkit:testing`'s failure-state taxonomy) -- the
postconditions each test asserts (request method/path/body, returned
identifier+URL, that a failure raises rather than returns, that no request
is sent) are what trace to the spec and must survive any such correction
unweakened.

## Obsolete tests

**Not applicable.** `clickup-task-client` is a wholly `ADDED` capability --
the change carries no `MODIFIED`, `REMOVED`, or `RENAMED` delta, so there is
no superseded behavior and no search for a bearing existing test was
performed or needed.

## Unresolved project questions

- **Async test plugin.** As already recorded in
  `tests/integration/products/conftest.py`'s own docstring for this
  project: `pyproject.toml` declares neither `pytest-asyncio` nor an
  `asyncio_mode`; `anyio` is an installed transitive dependency and
  auto-registers a pytest plugin, so this file follows the existing
  in-repo convention of `@pytest.mark.anyio` plus a locally defined,
  `asyncio`-pinned `anyio_backend` fixture. Not re-litigated here since it
  is already an established (if still project-unconfirmed) pattern.
- **The `get_client()` factory's exact name/shape**, per the INVENTED
  section above -- no `AGENTS.md`/`CLAUDE.md` convention answers this;
  `design.md`'s "mirrors slack.py" language is the closest thing to
  guidance, and is what this pass followed.

## Verification run

`uv run ruff check` / `uv run ruff format --check`, both clean, on this test
file specifically (project-wide `ruff`/`mypy`/`lint-imports` were not run
project-wide, since this pass touches only this one new file and the
targets it imports do not exist yet -- a project-wide `mypy`/`lint-imports`
run would fail on that absence alone, which is expected and not this pass's
concern to resolve).
