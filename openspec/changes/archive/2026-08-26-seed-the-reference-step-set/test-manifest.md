# Test manifest — seed-the-reference-step-set

## What covers what

| requirement / scenario | covered by |
|---|---|
| The seeded set represents every ID-bearing row except the six restatements | `tests/unit/launch/test_playbook_reference_set.py::test_every_reference_row_appears_except_the_restatements` |
| `description` re-derives from its row under the closed trimming rule | `…::test_every_description_re_derives_from_its_row`, `…::test_no_other_character_is_stripped` |
| `name` is authored, single-line, ≤80 characters | `…::test_every_name_is_a_single_short_line` |
| A row's leading marker survives into its name | `…::test_a_rows_leading_marker_survives_into_its_name` |
| A numeric threshold survives into its name | `…::test_a_numeric_threshold_survives_into_its_name` |
| Every seeded step is an unowned `human` draft, holding no slot | `…::test_every_step_is_an_unowned_human_draft` |
| Hazard coverage kept; prohibited tactics never block | `…::test_both_hazards_are_present_and_prohibited_tactics_never_block` |
| Every anchor kind and every discipline represented | `…::test_every_anchor_kind_and_discipline_is_represented` |
| Timing anchors follow the closed `WHEN` mapping, zero-based | `…::test_the_timing_anchor_follows_its_rows_when` |
| Identifier's second segment is its discipline | `…::test_each_identifier_carries_its_discipline` |
| The human pass is carried across unchanged | `…::test_the_human_pass_is_carried_across_unchanged` |
| A seeded playbook is not ready | `…::test_the_vendored_set_constructs_a_playbook` |
| The rules and the data cannot drift | `…::test_the_committed_file_is_what_the_generator_produces` |
| Replaces what the vendored set names | `tests/unit/test_seed_playbook.py::test_a_named_row_is_replaced_by_its_vendored_definition` |
| A step outside the vendored set survives | `…::test_a_step_the_vendored_set_does_not_name_survives` |
| A retired step is not returned to draft | `…::test_a_retired_step_is_not_returned_to_draft` |
| An un-retired step is replaced like any other named row | `…::test_an_un_retired_step_is_replaced_like_any_other_named_row` |
| Nothing stored is absent from the candidate | `…::test_nothing_stored_is_ever_absent_from_the_candidate` |
| Chain position: after `seed_admin`, before `check_step_handlers` | `…::test_the_start_chain_runs_the_step_in_its_specified_position` |
| The arming token is optional, and rendered from a secret | `…::test_the_arming_token_is_declared_as_an_optional_setting`, `…::test_the_arming_token_is_rendered_from_a_secret` |

## Assertions retired, and what supersedes them

Nothing was deleted. Round 3 of review established why: the two existing
integration files assert properties that remain **true of the migration-era
97-row set**, which `d2f8b3c64e17` still seeds on any database built from
scratch. Two seeded sets now coexist, answering different requirements, and
the files were ambiguous about which one they described.

Both now state their subject and stand down where the other set is installed,
via an autouse fixture that skips when `playbook_step_set.applied_seed_token`
is non-null.

| file | assertion | still true of | superseded for the new set by |
|---|---|---|---|
| `test_seeded_step_fields.py` | seeded `human` steps are `active` | migration seed | `test_every_step_is_an_unowned_human_draft` |
| `test_seeded_step_fields.py` | automated steps are present, carrying briefs | migration seed | the coverage requirement no longer asks it of the seed |
| `test_seeded_step_fields.py` | migrated steps carry no description | migration seed | `test_every_description_re_derives_from_its_row` |
| `test_playbook_seed.py` | every `name` re-derives from its reference row | migration seed | `test_every_description_re_derives_from_its_row` — the property moved fields |
| `test_playbook_seed.py` | BUILD THE LISTING is fully represented | both | `test_every_reference_row_appears_except_the_restatements` |

## Not covered

- **The step's end-to-end run against a live database** (tasks 3.12-3.14,
  3.18, 3.19): the composition, the token consumption and the atomic swap are
  covered at unit level over `compose()` and the settings, but no integration
  test runs `seed_playbook.main()` against Postgres. Writing one means
  mutating the tier's shared step set, which task 3.22 requires be done with
  snapshot-and-restore in the idiom `test_playbook_readiness_live.py` uses.
  Recorded as a gap rather than claimed as coverage.
- **These tests were written by the implementer**, not derived independently
  from the delta specs as `AGENTS.md` asks. They therefore share whatever
  assumptions the implementation makes; the `openspec-test-writer` pass that
  would have caught a divergence between spec and code did not run.
