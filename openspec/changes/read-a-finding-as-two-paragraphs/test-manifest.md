# Test manifest — `read-a-finding-as-two-paragraphs`

**Authored by the implementer, not by an independent author.** `AGENTS.md`
makes a separate test author the default and requires a stated reason where
that is not done; the reason is the user's direction for this change, recorded
in `tasks.md` §1 along with what it costs and the two compensations required in
exchange. Both compensations were met and are evidenced below.

All tests live in
`tests/unit/launch/infrastructure/driving/test_launch_detail_finding_rendering.py`.

## 1. Every scenario, accounted for

| Scenario (delta) | Test |
| --- | --- |
| The field and value lead the outcome | `test_the_field_and_value_lead_the_outcome` |
| The result carries no leading prose | `test_the_result_carries_no_leading_prose` |
| The field reads as an admin's words | `test_the_field_reads_as_an_admins_words` |
| A field with no supplied wording still renders | `test_a_field_with_no_supplied_wording_still_renders` |
| An empty value renders as readable text | `test_an_empty_value_renders_as_visible_text`, `test_an_empty_value_is_distinguishable_from_no_finding_at_all` |
| The distinction survives without colour | `test_the_distinction_survives_without_colour`, `test_the_result_and_comment_are_separate_block_level_elements`, `test_a_rule_makes_the_finding_s_two_parts_blocks` |
| No separating element is required | `test_no_separating_element_is_required` |
| No rule lays the two out in a row | `test_no_rule_lays_the_finding_out_in_a_row` |
| The whole outcome opens together | `test_the_whole_outcome_is_bounded_together` |
| The bound is not a count of lines | `test_the_bound_is_not_a_count_of_lines` |
| A recording with no carried finding is rendered unchanged | `test_a_recording_with_no_carried_finding_is_rendered_unchanged`, `test_the_common_path_is_undisturbed_on_a_page_that_also_carries_findings` |
| The evidence and provenance are still rendered | `test_the_evidence_and_provenance_are_still_rendered` |

**Uncovered scenarios: none.** All twelve are covered by at least one named test.

## 2. Obsolete tests

Two groups, deleted rather than adjusted, and for two different reasons — the
distinction matters, because only the first is obsoleted *by this delta*.

### Obsoleted by the modified scenario

- The `finding-divide` assertions inside `test_the_distinction_survives_without_colour`:
  the divide's position between result and comment, the two `_is_inside` checks
  against it, and the inverse-containment assertion added in
  `separate-the-result-from-the-comment`.
- `DIVIDE_MARKER` and its use in the no-finding marker sweep.

The scenario they derive from is replaced. The new requirement says outright
that no separating element is required and none may be relied on, so a test
asserting one would be asserting against the spec. Adjusting them to pass would
have meant re-deriving from the implementation.

### Never fixed by any requirement

- Nothing. The `finding-block` wrapper that `tasks.md` 1.6a anticipated never
  reached `main` — it existed only on an unpushed branch whose work this change
  supersedes. **Task 1.6a is therefore moot, not done**, and is recorded here so
  the next reader does not go looking for a deletion that never happened.

## 3. The two compensations, evidenced

`tasks.md` §1 required the intent-carrying assertions to be verified failing
against the live markup before being kept. Run before any implementation
existed:

```
FAILED test_no_separating_element_is_required
FAILED test_the_whole_outcome_is_bounded_together
FAILED test_no_rule_lays_the_finding_out_in_a_row
FAILED test_the_bound_is_not_a_count_of_lines
```

Two more guards were added after `/code-review` and verified the same way, by
reintroducing the exact defect each was written for:

- `test_a_rule_makes_the_finding_s_two_parts_blocks` — the two parts are spans,
  so their block-ness lives wholly in the stylesheet and nothing asserted it.
- `test_the_served_stylesheet_is_brace_balanced` — verified failing against the
  restored production defect (§4).

## 4. A production defect this change also fixes

`/code-review` found `main.container table th, main.container table td {` left
unclosed in the served stylesheet. Bisected to `cadc188`, the merge resolution
in `separate-the-result-from-the-comment`: a splice that kept both sides of a
conflict dropped one closing brace. Balanced before that commit, unbalanced
after, and **shipped to production**.

Everything after the break nests inside it. The finding's own rules still
matched by accident under CSS Nesting and would be discarded outright by an
engine without it — leaving the fact and the account run together on one line
with the distinction carried by nothing, which is the exact defect this change
exists to remove.

No test could see it: the rules were textually present, so a stylesheet
assertion that a rule *reaches* a selector passes either way. That is why the
brace-balance guard is a separate test rather than a stronger assertion inside
another.

## 5. Deliberately untested

- **How it looks.** Weight, spacing, which token, and whether the closed cell
  reads as two lines. `design.md` leaves these open on purpose and `tasks.md`
  3.7/3.7a settle them by looking at the rendered page. Two defects in this cell
  have now shipped past a green suite, and both were found that way.
- **That a browser lays the two blocks one below the other.** The stylesheet is
  asserted not to lay them out in a row and to make them blocks; whether a given
  engine then stacks them is the browser's contract, not this code's.
