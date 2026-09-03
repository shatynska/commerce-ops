## Context

See `proposal.md` — *Why*. What this adds is the shape of the cell as #157 left it, and why two of its three problems are the same problem.

```html
<summary class="evidence-summary">        <!-- display: flex, a ROW -->
  <div class="finding-result">…</div>     <!-- ┐                        -->
  <div class="finding-divide"></div>      <!-- ├ three flex items       -->
  <div class="finding-comment">…</div>    <!-- ┘ → three narrow columns -->
  <span class="evidence-clamp">…</span>   <!-- a fourth                 -->
  <!-- chevron, ::after -->
</summary>
```

The summary was written for one child and a chevron; `display: flex` with a default row direction was correct for that and is wrong for four. The parts also clamp separately — `.finding-comment` two lines, `.evidence-clamp` two more, the provenance not at all — so the chevron opens a portion of a cell rather than the cell.

Both fall out of the same restructuring: put the two *inside* the bounded container. They stack because they are blocks in normal flow — provided nothing lays that container's children out in a row, which is the condition the delta now states rather than assumes — and they open with everything else because there is one bound.

## Goals / Non-Goals

**Goals.** One container, one bound, two blocks, no rule; the chevron beside the text as it has always been; the common path's markup untouched and its rendering checked rather than assumed.

**Non-goals.** Everything in `proposal.md`'s list, plus: no new class beyond what already exists. `.finding-block`, added in an intermediate fix to give the three parts a line of their own inside the flex row, is not needed once they are inside the clamp — the wrapper existed to solve a problem this design does not have.

## Decisions

### The two go inside `.evidence-clamp`

**Chosen** over a wrapper that claims a whole flex line, which was the intermediate fix.

The wrapper works: `flex: 0 0 100%` on a container of the three parts, with `flex-wrap` on the summary, makes them stack. But it leaves two bounds and a chevron that wraps beneath the text unless the clamp is also told to grow — a second correction for a problem the first one caused. Putting the parts inside the clamp removes the wrapper, the wrap, and the second clamp together, and returns the summary to exactly two children, which is what it was written for.

### The two blocks stay inline elements made block by CSS, and the container keeps its tag

**Chosen** over `<p>` children, and over changing `.evidence-clamp` to a `<div>`.

`<p>` was the first instinct — they *are* a fact and an account of it — and it does not survive the markup. `.evidence-clamp` is a `<span>`, and `<p>` is not permitted inside one; making the container a `<div>` moves the problem rather than solving it, because the container sits inside `<summary>`, whose content model is phrasing content. Either way something is invalid, on a cell whose last shipped defect was a malformed tag that hid the record from assistive technology.

So the two are `<span>` elements carried to block by the stylesheet. That is why the delta states the requirement over "separate block-level elements" and fixes **no tag literal**: the tag is not what the requirement is about, and fixing one here would enforce more than the requirement supports.

The cost is that neither element is announced as a paragraph. It is not a regression — they were `<div>`s before, announced as nothing either — and it buys valid markup in the one cell where invalid markup has already cost something.

Changing the container's tag would also break the byte-exact pin over the no-finding path for no gain, since that path renders no finding at all.

### The clamp becomes a height, not a line count

`-webkit-line-clamp` clamps inline content. The two paragraphs are blocks, and block children of a `-webkit-box` are browser-dependent — the trap the previous change's review caught when `.finding-comment` sat inside the clamp with a line-count on it.

So `max-height: calc(2 * 1.5em)` with `overflow: hidden`, lifted to `max-height: none` when the disclosure is open. Two lines' worth, expressed as a height the browser applies to blocks.

The cost is that the bound is a computed height rather than a literal line count, so a future change to the cell's line height must move with it. That is why the delta states the requirement as "a bound the browser applies to block content" rather than naming a property: the property is an implementation of the rule, and a later author may find a better one.

### The separating rule goes, and the accessibility clause is re-grounded rather than dropped

The rule was specified to keep the distinction off colour alone, and it did that. So does a paragraph break: two blocks beginning on two lines are as visible to a reader who sees no colour as a drawn rule between them.

What the rule cost was legibility of the column it sat in. A hairline inside a scanned table cell reads as furniture — the cell already has borders, and a third horizontal line inside it competes with them.

**The clause is not deleted.** The delta keeps "the distinction SHALL be carried by structure, not only by colour" and restates the structure as the break, then says outright that no separating element is required and none may be relied on. Deleting the clause and letting colour carry the distinction is the one option here that should not be taken, and saying so in the spec is cheaper than rediscovering it.

`finding-divide` and its regression test go with it. The test asserting the three parts share a wrapper goes too: the wrapper is gone by design, not by accident, and a test asserting a structure the change deliberately removed would have to be deleted rather than updated — which is what makes it obsolete rather than failing.

## Risks / Trade-offs

**A long value crowds the comment out of the closed state.** → Real, and accepted: the sub-category path fills most of the first of two lines. The fact is what the column is for, and the comment is one press away. Raised with the user against the rendered page rather than argued from here.

**A computed height is more fragile than a line count.** → It is, and the delta says so by stating the rule rather than the property. The mitigation is that the closed height is visible on any page with a finding on it, so a drift is seen rather than reported.

**The common path could regress through the stylesheet rather than the markup.** → The byte-exact pin proves the *markup* of a no-finding cell is unchanged, and that is all it proves. The rules this change edits reach `.evidence-clamp`, which is on that cell too, so its bounding mechanism and its width behaviour do change. The delta states the obligation over what a reader sees rather than over the markup, and verification looks at a no-finding cell rather than inferring from the pin.

**The provenance is now behind the disclosure on rows that carry a finding.** → Real, and it is what the reconciling clause in the delta exists to answer rather than to wave away. Nothing is lost from the response and one control reveals it, which is the shape this capability's evidence already takes. A reader scanning for who recorded what now presses once on those rows. Accepted deliberately, because the alternative is the split disclosure the user rejected on sight.

## Migration Plan

None. Presentation only: no schema, no data, no configuration. Deploy is the ordinary branch → PR → merge path, and a rollback is the previous rendering with no state to unwind.

## Open Questions

- **Should the dossier adopt the same treatment?** It renders results from a different store and has never shown a finding field. Out of scope here for the third time, and increasingly worth its own change rather than a mention.
