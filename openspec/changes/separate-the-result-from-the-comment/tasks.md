## 1. Tests derived from the delta specs

Written before the implementation, from the deltas' scenarios rather than from the code, by an author other than whoever writes the implementation (`AGENTS.md`, *Test design before implementation*).

- [x] 1.1 `tests/unit/launch/domain/` — a recorded outcome carries a finding's field, value and comment, readable back beside its outcome, evidence and provenance (*A recording carries the finding that produced it*).
- [x] 1.2 A recording made with no finding carries none, and its outcome, evidence and provenance are unchanged (*A recording made with no finding carries none*, *The outcome and the evidence are unaffected by what is kept beside them*).
- [x] 1.3 **Absent is not empty.** A recording carrying nothing and a recording carrying a finding whose value is `[]` (and whose value is `""`) are distinguishable when read back (*An absent finding is distinguishable from an empty value*). This is the assertion the whole change turns on — an implementation that stores an empty value as `NULL`, or reads `NULL` as an empty finding, passes every other test in this section.
- [x] 1.4 A finding whose **value** is absent or null is not readable as a present finding, and a finding whose **comment** is absent is carried as such, distinct from an empty-text comment (*A finding with no comment is carried as such*, and the delta's one-spelling-of-empty clause).
- [x] 1.5 A recording whose stored finding cannot be read reports carrying none, and every other fact about the recording is still returned — the read does not fail (*An unreadable stored finding does not fail the read*).
- [x] 1.6 A later recording replaces the carried finding along with the outcome, **including replacing a carried finding with none** (*A later recording replaces the carried finding*). Cover the replace-with-none row explicitly: an implementation that only ever writes a finding leaves a stale one behind, which reads as a fact the new outcome never established.
- [x] 1.7 Evidence is byte-identical whether or not a finding is carried (*Evidence is unchanged by what is carried beside it*).
- [x] 1.8 A carried finding reaches the launch report on the step entry the recording belongs to (*A carried finding reaches the launch report*). Assert against the report, not against the page — the page reads only what the report carries.
- [x] 1.9 `tests/unit/launch/infrastructure/` — the `launch_step_progress` row mapping round-trips a carried finding, and maps a `NULL` column to "carries nothing" rather than to an empty finding (*A recording made before this capability reads as carrying nothing*).
- [x] 1.10 `tests/unit/launch/` — a supported finding written to its sink for a step naming **no confirmer** is kept on the recording the pass makes, with **the sink's** field name (*A written finding is kept with the field it was written to*, *The field's name is not the handler's to supply*). Assert the field name comes from the registration: register a sink under a field name the handler never mentions, and assert that name is what is kept.
- [x] 1.11 **The confirmable path, end to end.** A supported finding with a terminal outcome for a step naming a confirmer is stored with the pending result, and the recording made when a member accepts carries the field, value and comment (*A confirmable step's finding survives until the result is accepted*). This is the row the first draft of this change got wrong, and the only row that exercises what `lp.strategy.006` actually does — a suite passing without it would report a working mechanism that produces nothing on the page.
- [x] 1.12 A member **rejecting** a pending result produces a recording carrying no finding (*A rejected result keeps no finding*).
- [x] 1.13 A handler writing a finding and proposing a **non-terminal** outcome has that outcome recorded directly, carrying the finding (*A non-terminal outcome keeps the finding it wrote*).
- [x] 1.14 A supported finding for a step naming no sink keeps nothing and writes nothing; a `Failure` finding keeps nothing; a finding whose write does not succeed is not kept (*A finding for a step naming no sink…*, *A failure finding keeps nothing*, *A finding whose write did not succeed is not kept*).
- [x] 1.15 `tests/unit/launch/infrastructure/` — the detail page renders a carried finding's field and value **ahead of** the comment, the result element carrying `finding-result` and the comment `finding-comment` (*The field and value lead the outcome*), with nothing preceding the field in that result (*The result carries no leading prose*). Assert the ordering by position in the rendered response, not by both being present.
- [x] 1.16 The field renders as the wording the carried finding holds, and as the field's own name where it holds none (*The field reads as an admin's words*, *A field with no supplied wording still renders*). Assert the page resolves nothing itself — the wording comes off the record.
- [x] 1.17 An empty value renders as **visible text** standing for emptiness inside the result, and a step carrying nothing renders differently from one carrying an empty value (*An empty value renders as readable text*). Assert the text is present, not merely an element: an element carrying a class and no text is the failure the clause names. The page-level counterpart of 1.3.
- [x] 1.18 The result and the comment are separate block-level elements with a separating element carrying `finding-divide` between them (*The distinction survives without colour*). Assert the separating element's presence and its position between the two, so a rendering distinguished only by a colour declaration fails.
- [x] 1.18a A finding stored with a pending result follows the recording's own rules — one spelling of an empty value, an absent comment kept absent, an unreadable stored finding read as none — and an unreadable stored finding **does not fail the acceptance** (*An unreadable stored finding does not fail an acceptance*). The store this change adds is the one whose failure loses a member's decision.
- [x] 1.18b The value kept at acceptance is the one written when the handler ran, and the sink is not re-read (*The value kept is the value as written*). Change the product's value between the hold and the acceptance, and assert the recording carries the earlier one.
- [x] 1.19 A recording carrying no finding renders exactly as before this change (*A recording with no carried finding is rendered unchanged*). Pin against the current rendering: this is the common path and the one a regression reaches first.
- [x] 1.20 The verbatim evidence and the provenance are still rendered for a step whose recording carries a finding (*The evidence and provenance are still rendered*).
- [x] 1.21 `tests/integration/launch/` — both `finding` columns round-trip through Postgres, and rows written before the migration read back as carrying nothing.

## 2. Implementation

- [x] 2.1 Alembic revision: add `finding jsonb NULL` to `launch_step_progress` **and** to `automated_step_results`. No backfill — absent is the correct reading for every existing row. The down revision drops both.
- [x] 2.2 Add `FindingSink` to `launch/application/ports.py`: a frozen value carrying the recording callable, the storage field name, and the wording an admin reads. Leave `SubCategoryRecorder` named and typed as it is — widening it belongs to the change that adds a second sink with a different value type.
- [x] 2.3 `worker.py`: register `{"lp.listing.007": FindingSink(_record_sub_category, "sub_category", "Sub-category")}`.
- [x] 2.4 `automation_pass._record_finding`: on a successful write, answer the field name and value written alongside its existing boolean. Keep nothing on a `Failure`, on a step with no sink, or on a failed write.
- [x] 2.5 Where the pass records the outcome itself — no confirmer, or a non-terminal outcome — carry the finding onto that recording as `{"field": ..., "reads_as": ..., "value": ..., "comment": ...}` — four keys, the wording among them (`design.md`, *The wording travels on the finding, not through a registry*). `NULL` is the whole of "carries nothing"; an empty value lives **inside** a finding that exists.
- [x] 2.6 Where the pass holds a pending result, store the finding on it. This is the hop that makes the change work for `lp.strategy.006`; without it the compliance step renders nothing (`design.md`, *The finding travels with the pending result*).
- [x] 2.7 The accept path carries the stored finding onto the recording it makes, **without re-reading the sink** — the value asserted is the one the member was shown. The reject path carries none. Leave the recording/settlement atomicity as it stands; if carrying the finding turns out to require reworking it, stop and raise it as its own change rather than widening this one (`design.md`, Open Questions).
- [x] 2.8 Both repositories and their row mappings: write the column, read it back, map `NULL` to "carries nothing", treat an absent-or-null **value** as no finding, keep an absent **comment** distinct from empty text, and report an unreadable stored finding as none **without failing the read** — and, on the pending-result store, without failing the acceptance.
- [x] 2.9 A later recording replaces the carried finding, including replacing it with none.
- [x] 2.10 `launch_admin.py`: carry the finding onto the step's view row, so the template reads a value rather than reaching into a record. Take the field's wording **off the carried finding**; add no registry on the admin side. Confirm the report's step entry already carries the finding (`design.md`, Context) rather than adding a projection that duplicates one.
- [x] 2.11 `launch.html`: render the field's wording and value first with no leading prose, then the comment, then the evidence and provenance already rendered. Result element carries `finding-result`, comment element `finding-comment`. Keep the two-line clamp and the `<details>` disclosure.
- [x] 2.12 The stylesheet rule for the separating element and the two blocks. The structural separation is fixed by the delta; weight, spacing and which token is used are not, and are settled at 3.7. Scoped so it reaches no other admin surface; the page carries no styling of its own, which `launch-admin` forbids.
- [x] 2.13 `vocabulary.css`: add a token for an established fact if none exists, with its dark-mode counterpart, beside the existing `--danger-*` set. No literal colours in the template.
- [x] 2.14 Touch no handler. Every existing handler keeps its signature and its output.

## 3. Verification

- [x] 3.1 `uv run pytest tests/unit tests/agents` green.
- [x] 3.2 `uv run pytest tests/integration` green — against a seeded database, not a skipped tier reporting green (`AGENTS.md`, *Working in a git worktree*).
- [x] 3.3 `uv run mypy .` green.
- [x] 3.4 `uv run ruff check` and `uv run ruff format --check` clean.
- [x] 3.5 `uv run lint-imports --config .importlinter` green.
- [x] 3.6 `openspec validate separate-the-result-from-the-comment --strict` passes.
- [ ] 3.7 **Look at it.** Run the admin surface locally and read the Outcome column for both steps, in both themes. The appearance is a visual decision `design.md` deliberately leaves open within the delta's constraints; the marker names are not, and are already fixed. Settle the appearance here.
- [x] 3.8 `/code-review` over the change's diff, per `AGENTS.md`, *Independent review before completion*.

## 4. Archive

- [ ] 4.1 `openspec archive separate-the-result-from-the-comment --yes` as the last commit before the merge.
