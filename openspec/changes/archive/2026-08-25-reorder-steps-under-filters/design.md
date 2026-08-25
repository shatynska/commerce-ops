## Context

See `proposal.md` — Why. The constraints that shape the approach:

- `reorder_step` (`playbook_authoring.py:307`) takes a `target_index`
  that is 0-based **among the gate's full live steps**, removes the step
  and re-inserts it once, and documents the invariant this change needs:
  *"the unmoved steps keep their relative order."* Its position logic is
  correct as it stands; only its handling of a caller-supplied view
  changes.
- Its `_WRITE_ATTEMPTS` loop currently resolves a version conflict by
  re-loading and recomputing. That is safe only because `target_index`
  is supplied by a caller who computed it against nothing in particular.
  It stops being safe here.
- The page's sort key (`_render_page`, `playbook_admin.py:287-293`) is
  `(display_order, identifier)`. `_slot_of` (`playbook_authoring.py:169`)
  is `int(getattr(row, "display_order", 0))` with the same tiebreak. The
  two agree **on live steps**. They do not agree on the rendered list
  when retired steps are shown: retired rows keep a stale `display_order`
  that `retire_step` never clears and that `reorder_step` renumbers only
  live steps around. No test pins this equivalence today; task 3.1 adds
  one.
- The admin page is server-rendered Jinja with HTMX as progressive
  enhancement — `hx-boost="true"` on `<body>` (`page.html:10`), which
  swaps the whole document on every action.
- The project is pure Python with no Node toolchain
  (`AGENTS.md` — Development Tooling).
- The guard is one dependency, `_require_admin`, and refusal is the
  app's own 404. Nothing in this change may create a route outside it.

## Goals / Non-Goals

**Goals:**

- Keep the filter-carrying logic in exactly one place, so the class of
  bug being fixed here cannot recur route by route.
- Keep filter awareness out of the application and domain layers.
- Make a reorder's real effect legible when a filter hides part of it.
- Define a move by one rule, not one rule per control.

**Non-Goals:**

- Reordering by dragging, and with it fragment rendering, out-of-band
  swaps and any new front-end asset. Deferred to a follow-on change; see
  `proposal.md` — Deferred.
- Any change to the domain's coherence rules, the step schema, the
  meaning of `display_order`, or `reorder_step`'s position logic. The
  application-layer change is confined to how a supplied view is
  honoured.
- A "move to position N" input.
- Client-side state not derivable from the URL. The filter stays in the
  query string, which is what makes it survivable and shareable.

## Decisions

### One move rule: come to rest after a named visible step

A move names the visible step it should come to rest **after**, or names
the head of the visible list. Both reorder controls express themselves in
that vocabulary, so there is one rule and one code path.

`target_index` counts **how many of the gate's live steps precede the
moved step once it has been removed from the order.** Writing `G` for the
gate's live steps in authored order, `V` for the visible subsequence of
`G`, and `G∖S` for `G` without the moved step `S`:

| the move names | `target_index` |
| --- | --- |
| come to rest after visible step `P` | `index of P in G∖S` + 1 |
| the head of the visible list | `index in G∖S` of the first element of `V` other than `S` |

The two controls in terms of that vocabulary, for `S = V[j]`:

| control | names | inert when |
| --- | --- | --- |
| move down | come to rest after `V[j+1]` | `j` is last |
| move up | come to rest after `V[j-2]`, or the head when `j == 1` | `j` is first |

Worked example — `●` visible under the filter, `○` hidden by it:

```
before                     move down on A            after
  0 ○                      names "after B"             0 ○
  1 ● A  ←                 B is at 3 in G∖A            1 ○
  2 ○                      target_index = 4            2 ○
  3 ○                                                  3 ● B
  4 ● B                                                4 ● A   ← moved
  5 ○                                                  5 ○
  6 ● C                                                6 ● C
```

The narrowed view shows exactly the swap requested. `A` crossed two
hidden steps, which the instruction *required* — `B` was below them —
and nothing else moved.

**Superseded by this decision.** An earlier draft specified "the position
closest to the one it holds that produces the requested arrangement" and
gave the two controls raw indices into `G`. Those are two different
rules: for a move up they place the step on opposite sides of any hidden
steps preceding the named neighbour, so the persisted order — and the
new position column — differed depending on which control was used, while
the narrowed view looked identical either way. "Come to rest after a
named step" is one formula, is what a move means to the person making it,
and is what dragging will express unchanged in the follow-on.

**Alternative rejected — swap `display_order` with the next visible
step.** Same narrowed view, but it moves two steps instead of one and
does not generalise to a drop between arbitrary neighbours.

**Alternative rejected — reorder against the whole gate, ignoring the
filter.** Today's behaviour (`_move`, `playbook_admin.py:469`). Once
filters survive a write it reads as a broken button: the step swaps with
a hidden neighbour and the visible list does not change.

### A move that changes nothing is not a write

A move that would leave the **visible order** as it already stands
performs no write. The test is on the resulting visible order, not on
whether the rule yields an index — because it usually does, and applying
it moves the step anyway.

Take `G = [S●, h○, h○, B●]` with the middle two hidden, and a move of `S`
to the head. The head rule names the first element of `V` other than
`S` — that is `B`, at index 2 in `G∖S` — so `target_index = 2` and the
set becomes `[h, h, S, B]`. The visible order is unchanged, `S●` then
`B●`, while `S` has slid from 1/4 to 3/4 in the persisted order and
crossed two steps the admin could not see. Only when `|V| == 1` does the
rule genuinely have no value; the harmful case is the one where it has a
perfectly good one.

### Reordering is unavailable under a search, and while retired steps show

Two views cannot give a move an honest meaning:

- **Description search.** Gate and discipline select a structurally
  meaningful subset of a gate; a text match selects an incidental one
  whose members may be scattered across the whole gate, so a single move
  can cross twenty unmatched steps while one visible row changes places.
- **Retired steps shown.** A retired step holds no slot in `gate_live`.
  It can neither be moved — `reorder_step` raises for exactly this — nor
  be named as the step to come to rest after, because it has no position
  in `G`. Retired rows also carry stale `display_order` values, so their
  rendered interleaving among live steps is arbitrary. Under this view
  the rendered list is simply not a subsequence of `G`, and every formula
  above is undefined.

In both, the controls go inert and the page says why, with the view
leavable in one action. **Alternative rejected for the retired case —
keep reordering live and skip retired rows when computing `V`.** It
preserves an affordance nobody asked for under a view meant for
un-retiring, at the cost of reordering live steps around retired rows
sitting at arbitrary positions. One rule with two inert views beats one
rule with an exception.

The restriction is enforced server-side as well as rendered, so it does
not rest on the controls alone.

### The client names a neighbour and a version; the server computes the index

The move posts `step_id`, the identifier of the visible step to come to
rest after (empty for the head), and the set version the page it was made
on was rendered from. The server re-derives `G` and `V` and computes
`target_index` itself. The client never computes or submits an index.

**Producing the version.** `_render_page` currently discards the version
it loads (`records, _version = await steps.load()`,
`playbook_admin.py:269`). It must instead put it in the page context, and
each move control must carry it, or there is nothing for the move to
submit and the pin below is unenforceable.

Naming a neighbour keeps the trust boundary where the rest of the page
already puts it, but it does **not** on its own make the move safe
against a concurrent write — which an earlier draft claimed. The route
loads the set to compute the index; `reorder_step` loads again to apply
it; without the checks below, a write landing between the two is
invisible to both. Today's `_move` has the same window but computes ±1,
so a stale index is wrong by one slot; a named neighbour may have moved
anywhere in the gate, so the misplacement would be unbounded — silent,
and recoverable only by noticing it. That is what the two checkpoints
exist to close.

**One version, two checkpoints.** Three loads sit between rendering a
page and persisting a move — the render, the adapter's own load when it
computes the index, and `reorder_step`'s. Each gap admits a different
staleness:

```
  render      →   admin clicks   →   adapter loads   →   reorder_step loads
  version v                          version v'          version v''

              v ≠ v'  → the list the admin read is stale; the named
                        neighbour and the visible order they acted on
                        no longer describe the set. Reject.

              v'≠ v'' → the index is stale; it was computed against a
                        set this write is not the one applying to.
                        Reject.
```

The adapter rejects unless `v' == v`, computes the index against that
load, and passes the same version to `reorder_step`, which rejects unless
`v'' == v'`. After the first check the value is the same number
throughout, so "the version the page was rendered from" and "the version
the position was computed from" name one thing — but both checks must
exist, or a move computed from a set the admin never saw is applied on
their behalf.

The simpler-looking alternative — pass the adapter's own POST-time load
version straight through — is what this decision exists to forbid: that
version is always current, so the pin always passes, the race stays open,
and nothing fails visibly.

**Transport: a hidden field on the move control.** The version is a
concurrency token, not view state: only the move submits it and no link
needs it, so unlike the filter it has no reason to be shareable or
bookmarkable. This is not the case "Alternative rejected — hidden form
inputs" below refuses; that one is about the *filter*, which has to serve
links as well as forms and belongs in the URL for exactly that reason.
Note that the transport buys no replay-safety of its own — a hidden field
in a page restored from history re-submits exactly as a query string
would. What makes a replayed move harmless is the first checkpoint.

### The supplied version is honoured, not retried past

`reorder_step` gains an optional expected set version. When supplied, a
version that is not the one the write reads is rejected rather than
retried — in either direction, so a value the caller does not hold cannot
be passed off as a view of the set; when absent, today's
re-read-and-recompute behaviour is unchanged, so no existing caller
changes meaning.

The retry has to go, not just the race: retrying re-reads the set and
reapplies a `target_index` computed against the view the caller has
already lost. That is precisely the unbounded misplacement above, arrived
at by a different route.

This is a `playbook-authoring` change, which the earlier draft listed as
a Non-Goal. It is the right one to drop: the capability's existing
requirement already says *"a reorder concurrent with another accepted
write on a stale view of the set SHALL be rejected without persisting
anything"*, and its existing scenario is written in terms of a reorder
"submitted against a version of the step set" — which no caller can do
today. The change makes an existing requirement reachable rather than
adding a new obligation. The boundary that Non-Goal protected — filter
awareness staying out of the application layer — is untouched: a set
version is not a filter.

### One `_filters_of(request)` helper, and the filter on every link and action

The bug being fixed is duplication: the read route reads four query
parameters and every write route forgets them. One helper returns the
four values; every route that renders reads them through it. This also
removes `unretire`'s hardcoded `show_retired=True`
(`playbook_admin.py:463-466`), the same bug with a different default.

The filter travels as a query string appended to every form `action`
**and every link that leaves the list** — the edit link (`page.html:72`),
the retired-toggle links (`page.html:48,50`) and the edit form's back
link (`edit.html:39`). Missing the links was the earlier draft's gap:
the edit round trip leaves the list through an anchor, so `edit_form`
and `_render_edit` must carry the filter for `edit.html`'s own action to
have anything to append.

**Alternative rejected — hidden form inputs.** Mixes view state into the
POST body next to authored values, cannot serve the links at all, and
has to be repeated per form rather than composed once into a URL.

**Alternative rejected — Post/Redirect/Get.** Cleaner HTTP, and it would
fix resubmit-on-refresh. But `playbook-admin` requires a rejected write
to re-render with its full fault list and the submitted values still in
the form, which a redirect cannot carry without a flash cookie or faults
in the query string.

## Risks / Trade-offs

- **A filtered move crosses hidden steps invisibly** → the position
  column shows each step's index within its whole gate, so a move that
  changes `12/65` to `15/65` is readable even though one visible row
  moved. This is why the column is in scope rather than a nicety.
- **The adapter's ordering could drift from `reorder_step`'s** → the two
  sort keys are equal today but written out separately, and no test pins
  them. Task 3.1 adds one, so a change to either surfaces as a failure
  rather than as silently misplaced steps.
- **A move still returns the admin to the top of the list** → accepted
  for this change; fragment rendering belongs with dragging. Mitigated by
  the filter now surviving, so the list returned to is a narrowed one.
- **Reordering unavailable in two views** → an admin who searched to find
  a step must clear the search to move it, and cannot reorder while
  reviewing retired steps. Accepted as the cost of one predictable rule;
  both states are explained and leavable in one action.
- **A pinned version makes conflicts visible that were silently absorbed**
  → the set version is global to the whole step set, not per gate, so
  *any* accepted write — a create, an edit, a move in an unrelated gate —
  invalidates every move control rendered before it. Two admins working
  the same set will now see a stale notice where the retry previously hid
  the conflict. That is the point, and it costs one click to re-read, but
  it fires more often than "the same gate" would suggest.
- **Filtered nudges are not invertible** → moving a step down and back up
  under a filter does not restore its position. With
  `G = [A●, h○, B●]`, a move down gives `[h, B, A]` and a move back up
  gives `[h, A, B]`, not the original `[A, h, B]`: `A` reads 1/3, then
  3/3, then 2/3. Every guarantee holds — nothing but `A` ever moves — but
  an admin correcting a mis-click will see the position column settle
  somewhere new. Accepted, and visible, which is the best available
  outcome: the alternative is a move that hides the same drift.

## Migration Plan

None. No schema change, no migration, no persisted-data change.
`reorder_step`'s new parameter is optional and its absent-version
behaviour is unchanged, so the application layer stays backward
compatible. The change is deployable and revertible as a code change
alone.
