## 1. The vendored data file

- [x] 1.1 Add `alembic/data/playbook_reference.yaml` carrying 352 steps — every ID-bearing row of `docs/reference/product-launch.md` except the six that restate a gate's authored metric condition (`lp.inventory.040`, `lp.inventory.041`, `lp.strategy.033`, `lp.strategy.025`, `lp.ppc.048`, `lp.finance.036`, as `test_playbook_seed.py` already records them). Leave `playbook_v1.yaml` untouched — `d2f8b3c64e17` still reads it on any environment built from scratch
- [x] 1.2 Each row carries: `identifier` (the reference row ID), authored `name` (≤80 chars, leading marker and numeric thresholds preserved), `description` (the row's text under the trimming rule), `gate`, `discipline` (the row's AGENT, lowercased), `scope`, `timing_anchor`, `blocking`, `kind: human`, `needs_confirmation: false`, `status: draft`, `hazard`, `assignees: []`, `provenance` (the row's SOURCE). **No `display_order`**: `playbook-authoring` gives a slot only to an `active` step, `_place` zeroes it on any non-active write, and every seeded step is a draft — a seeded slot would be a state no write can produce and would decay unevenly during the very review this change enables
- [x] 1.3 Derive every row's `timing_anchor` from its `WHEN` by the closed mapping design.md records, taking care with the two forward-counting values: `Day 1` is offset **0** and `Day 60+` is `open-ended(59)`, because the convention is zero-based and the source is one-based
- [x] 1.4 Commit the authored names as their own reviewable input — 352 lines of `identifier: name` — which the generator merges. They cannot be generated from the row text, so they are the one part of the file a person writes and a person reviews
- [x] 1.5 Carry the earlier human pass across unchanged for the 97 rows it covered — its `gate`, `scope`, `blocking` and `hazard`, not the rule's answer
- [x] 1.6 Derive the other 255 rows' gates by the three-stage rule design.md now records in full; leave their `blocking` false and their `hazard` none
- [x] 1.7 Commit the generator that produces the file, so a reviewer can re-run the rules rather than trust 352 rows by inspection
- [x] 1.8 Set `scope: market` on exactly the 12 identifiers design.md enumerates, and `product` on the rest — seven carry an `EU:` prefix, five name a marketplace without one, and no regular expression separates the second group from rows that merely mention a country

## 2. The preparation step

- [x] 2.1 Add `src/commerce_ops/seed_playbook.py` modelled on `seed_admin.py`: its own process, its own engine disposed before exit, exit status as the whole interface, the reason on stderr on failure. Invoke as `python -m commerce_ops.seed_playbook` like its two neighbours — no console script, since `pyproject.toml` declares none
- [x] 2.2 **Add what is missing; never touch what is there.** Load the stored records, carry every one across untouched, append each vendored step no stored record names, and persist the whole candidate through `PlaybookRepository.save` — which gives the atomic swap and the set-version advance. Ask only about identity: whether a stored row *differs* from its vendored counterpart is not a question this step may act on, because the difference is indistinguishable from an authored edit
- [x] 2.3 Where nothing is missing, write nothing and exit zero. This is what makes the step idempotent, and idempotence is why it needs no arming signal — its condition is readable from the stored set, as the roster seeder's is from the roster
- [x] 2.4 Refuse to write a set the domain would reject: construct `LaunchPlaybook` over the candidate first and report every fault at once rather than one per run
- [x] 2.5 Say in the step's own output how many steps it added and how many it left alone, and say so distinctly when it added none — a silent no-op is indistinguishable from a broken step
- [x] 2.6 Add the step to the start chain in the image's `CMD` (`Dockerfile`), after `seed_admin` and **before** `check_step_handlers`, so the handler check reports against the set about to be served. The `app` service declares no `command`, so `docker-compose.yml` is not where the chain lives
- [x] 2.7 No migration, no settings declaration and no `deploy.yml` render: the step takes no runtime variable

## 3. Tests

- [x] 3.1 The vendored file parses and constructs a `LaunchPlaybook` over `framework_gates()` with no faults
- [x] 3.2 Every ID-bearing row of the reference document appears exactly once except the six metric restatements, which appear not at all; no extra identifiers; 352 in total
- [x] 3.3 Every `description` equals its reference row's text under the trimming rule — the property that keeps the reference text checkable
- [x] 3.4 Every `name` is non-empty, single-line and ≤80 characters
- [x] 3.5 A row whose text begins `TOS RISK:`, `EU:` or `NOTE:` has a name beginning with the same marker
- [x] 3.6 Where a reference row states a numeric threshold, its authored name carries that number
- [x] 3.7 Every step is `draft`, `human`, needs no confirmation and names no assignee
- [x] 3.8 At least one `prohibited-tactic` and one `compliance-obligation` step exist, and no `prohibited-tactic` step has a true blocking flag
- [x] 3.9 Every timing-anchor kind and every discipline of the shared vocabulary is represented, and every anchor equals its row's `WHEN` under the recorded mapping
- [x] 3.10 Each identifier's second segment equals its declared discipline
- [x] 3.11 The 97 rows the human pass covered keep that pass's `gate`, `scope`, `blocking` and `hazard`
- [x] 3.12 An empty set receives every vendored step
- [x] 3.13 A set already carrying every vendored step receives nothing — the idempotence the chain depends on
- [x] 3.14 A stored step the vendored set names, which has been renamed, activated and assigned, keeps all three and its attribution
- [x] 3.15 A stored `retired` step whose identifier the vendored set names is still `retired` afterwards, with `retired_by` and `retired_on` unchanged
- [x] 3.16 A stored `mg.*` step the vendored set does not name survives with status and attribution unchanged
- [x] 3.17 A vendored step no stored step names is added, and no other stored step is altered
- [x] 3.18 The generator's output equals the committed vendored file, so the recorded rules and the data cannot drift
- [x] 3.19 The `Dockerfile` chain runs the step after `seed_admin` and before `check_step_handlers`, asserted at text level
- [ ] 3.20 Integration: the step runs against Postgres, adds the missing rows, and a second run adds nothing — with the tier's shared step set snapshotted and restored in the idiom `test_playbook_readiness_live.py` uses

## 4. Existing tests the change inverts

- [x] 4.1 Rewrite `tests/integration/launch/test_seeded_step_fields.py`. Its assertions are not wrong — they remain true of the **migration-era** set a database built from scratch still receives — but "seeded" now scopes to the preparation step's set, so each test must say which of the two coexisting sets it targets. `step.description is None`, seeded `human` steps being `active`, and automated steps being present all hold of the 97-row migration seed and none of the 352-row set
- [x] 4.2 Rewrite `tests/integration/launch/test_playbook_seed.py` the same way — its `name`-re-derives assertion holds of the migration seed and of `description` in the new set
- [x] 4.3 Record which assertions were retired and what supersedes each in `openspec/changes/seed-the-reference-step-set/test-manifest.md`, rather than deleting them silently

## 5. Verification

- [x] 5.1 `uv run pytest tests/unit tests/agents`
- [x] 5.2 `uv run pytest tests/integration` against `commerce_ops_test`
- [x] 5.3 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy .`
- [x] 5.4 `uv run lint-imports`
- [x] 5.5 Run the step against a scratch database and confirm: 352 stored, 0 served, the playbook not ready, and the admin surface listing every step
- [x] 5.6 Run it again immediately and confirm it writes nothing — the idempotence the chain depends on
- [x] 5.7 Plant an `lp.*` step that has been renamed, activated and assigned, plus a retired one and an `mg.*` one, run the step, and confirm all three are exactly as they were
- [x] 5.8 Confirm `alembic upgrade head` on a database built from scratch still applies `d2f8b3c64e17` from `playbook_v1.yaml`
