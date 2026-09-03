## 1. Tests derived from the delta spec

**Exemption, stated rather than assumed.** `AGENTS.md` requires an author other than the implementer to derive tests from the approved deltas, and requires a stated reason where that is not done. The reason here is the user's direction: for this change, no separate test author is dispatched and the review loop is bounded at one pass rather than the usual six. Both are recorded here so the next reader of this change sees the deviation and its cause rather than inferring one.

What that costs is independence — the implementer already has an implementation in mind, and assertions written afterwards tend to describe it. Two compensations are required and are not optional: every assertion below names the scenario it derives from, and the two that carry the change's intent (1.2 and 1.3) are verified to **fail against the current live markup** before being kept.

This is a `MODIFIED` requirement, so some existing tests are **obsolete** rather than failing — they assert a structure the change deliberately removes. They are identified in `test-manifest.md`, not silently edited.

- [x] 1.1 The result and the comment are separate elements, neither containing the other, and the result precedes the comment by position in the rendered response (*The distinction survives without colour*). Assert **no tag literal** — the delta fixes none, and a test enforcing one would enforce more than the requirement supports (`design.md`, *The two blocks stay inline elements made block by CSS*).
- [x] 1.2 A rendering with **no element between** the two satisfies the requirement (*No separating element is required*). This is the assertion that would fail against the superseded spec, and it is what makes the change's intent testable rather than merely stated.
- [x] 1.3 The result, the comment, the verbatim evidence and the provenance all sit inside **one** container carrying `evidence-clamp`, and none of them is bounded independently (*The whole outcome opens together*). Assert containment in the rendered response against that marker, which the delta now fixes for exactly this reason.
- [x] 1.3a `tests/unit/launch/infrastructure/driving/` — over the **served stylesheet**, in the idiom this capability already uses for stylesheet obligations: no rule reaching the container of a finding's result and comment lays its children out in a row (*No rule lays the two out in a row*), and the rule bounding `evidence-clamp` does not bound it by a count of lines (*The bound is not a count of lines*). The first of these is the assertion that would have caught the columns defect; markup-level assertions could not, and did not.
- [x] 1.4 The unchanged clauses still hold, against the new markup: field and value lead with nothing before them; the wording comes off the record and falls back to the field name; an empty value renders as visible text; both markers are carried; the evidence and provenance are still rendered (*The field and value lead the outcome*, *The result carries no leading prose*, *The field reads as an admin's words*, *A field with no supplied wording still renders*, *An empty value renders as readable text*, *The evidence and provenance are still rendered*).
- [x] 1.5 A recording carrying no finding renders the same facts in the same order (*A recording with no carried finding is rendered unchanged*). The existing byte-exact pin covers the **markup** and must still pass without being re-captured — but it proves only that much, and the rules this change edits reach that cell too, so the rendering itself is checked at 3.7 rather than inferred from the pin.
- [x] 1.6 Identify as obsolete, in `test-manifest.md`, every existing assertion over `finding-divide`. The modified scenario replaces the one they derive from, so they assert a structure this change removes on purpose and are deleted, never adjusted to pass.
- [x] 1.6a **Moot, and recorded as such in `test-manifest.md` rather than ticked as done.** The wrapper never reached `main` — it lived only on an unpushed branch this change supersedes — so there was nothing to delete. Kept here so a reader does not go looking. The assertions over the `finding-block` wrapper cover structure **no requirement ever fixed** — it came from an intermediate fix, appears in no served spec, and is deleted along with the wrapper. Recording the two under one heading would claim a provenance the delta does not have.

## 2. Implementation

- [x] 2.1 `launch.html`: move the finding's parts inside `.evidence-clamp`. Remove the `finding-divide` element and the `.finding-block` wrapper.
- [x] 2.1a **The container keeps its tag and the two parts stay `<span>`.** `.evidence-clamp` is a `<span>` inside a `<summary>`; a `<p>` child of a span is invalid, and making the container a `<div>` only moves the problem, since `<summary>` takes phrasing content. Both are carried to block by the stylesheet instead. This cell has already shipped one malformed tag that hid the record from assistive technology; it does not get a second (`design.md`, *The two blocks stay inline elements made block by CSS*).
- [x] 2.2 `vocabulary.css`: remove `.finding-divide` and `.finding-block`, and remove the `flex-wrap` from `.evidence-summary` — it existed only so the wrapper could claim a line, and with the wrapper gone it lets the chevron wrap beneath the text.
- [x] 2.3 Give `.evidence-clamp` `flex: 1` and keep `min-width: 0`, so it takes the row's width and the chevron stays beside it. Without the floor at zero a long value pushes the chevron off the row.
- [x] 2.4 Change the clamp from `-webkit-line-clamp` to a `max-height` of two lines with `overflow: hidden`, lifted to `max-height: none` when the disclosure is open. A line-count clamp is defined over inline content and the parts are blocks (`design.md`, *The clamp becomes a height, not a line count*).
- [x] 2.5 Style the two: `display: block` on each, the result in `--fact-ink` and heavier, the comment in `--ink`, with spacing that reads as a paragraph break rather than as a gap. No rule between them, and no rule laying the container's children out in a row.
- [x] 2.6 Delete the obsolete tests section 1.6 identifies. Do not adjust them to pass — they assert what this change removes.
- [x] 2.7 Touch nothing that records, stores or carries a finding. This change is presentation.

## 3. Verification

- [x] 3.1 `uv run pytest tests/unit tests/agents` green.
- [x] 3.2 `uv run pytest tests/integration` green — against a seeded database, not a skipped tier reporting green (`AGENTS.md`, *Working in a git worktree*).
- [x] 3.3 `uv run mypy .` green.
- [x] 3.4 `uv run ruff check` and `uv run ruff format --check` clean.
- [x] 3.5 `uv run lint-imports --config .importlinter` green.
- [x] 3.6 `openspec validate read-a-finding-as-two-paragraphs --strict` passes.
- [ ] 3.7 **Look at it.** Render the real page and read the Outcome column closed and open, in both themes. Two defects in this cell have now shipped past a green suite — a divider tag that hid the record from assistive technology, and three parts laid out as columns — and both were found by looking. Check in particular that the chevron sits beside the text, that the closed cell is two lines, and that opening it reveals the evidence and provenance too.
- [ ] 3.7a **Look at a row carrying no finding**, closed and open, in both themes. The byte pin proves that path's markup unchanged and nothing more; the rules this change edits reach its bounding container as well, so the one path no assertion covers for *rendering* is the common one.
- [x] 3.8 `/code-review` over the change's diff, per `AGENTS.md`, *Independent review before completion*.

## 4. Archive

- [ ] 4.1 `openspec archive read-a-finding-as-two-paragraphs --yes`, in a follow-up commit or PR as this repository does.
